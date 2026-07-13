from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from deeptutor.services.learner_state.heartbeat.service import LearnerHeartbeatService
from deeptutor.services.learning_plan import LearningPlanService
from deeptutor.services.learner_state.outbox import LearnerStateOutboxItem
from deeptutor.services.learner_state.supabase_writer import LearnerStateSupabaseWriter
from deeptutor.services.member_console.external_auth import ensure_external_auth_user


def _make_item(
    *,
    event_type: str,
    payload_json: dict,
    dedupe_key: str,
    item_id: str = "outbox_1",
    user_id: str = "student_demo",
    created_at: str = "2026-04-15T10:00:00+08:00",
) -> LearnerStateOutboxItem:
    return LearnerStateOutboxItem(
        id=item_id,
        user_id=user_id,
        event_type=event_type,
        payload_json=payload_json,
        dedupe_key=dedupe_key,
        status="pending",
        retry_count=0,
        created_at=created_at,
        last_error=None,
    )


def _make_client(
    requests: list[dict[str, object]],
    *,
    existing_summary_structured_json: dict | None = None,
    existing_user_row: dict | None = None,
) -> httpx.AsyncClient:
    summary_state = {"summary_structured_json": existing_summary_structured_json}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        request_json = json.loads(body) if body else None
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "headers": {key.lower(): value for key, value in request.headers.items()},
                "json": request_json,
            }
        )
        if request.method == "GET" and request.url.path == "/rest/v1/users":
            return httpx.Response(
                200,
                json=[existing_user_row] if existing_user_row is not None else [],
                request=request,
            )
        if request.method == "GET" and request.url.path == "/rest/v1/learner_summaries":
            structured = summary_state["summary_structured_json"]
            if structured is None:
                return httpx.Response(200, json=[], request=request)
            return httpx.Response(
                200,
                json=[{"summary_structured_json": structured}],
                request=request,
            )
        if request.method == "POST" and request.url.path == "/rest/v1/learner_summaries":
            row = dict((request_json or [{}])[0])
            if isinstance(row.get("summary_structured_json"), dict):
                summary_state["summary_structured_json"] = dict(row["summary_structured_json"])
        return httpx.Response(201, json=[{"ok": True}], request=request)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.supabase.co",
    )


def _write_requests(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    return [request for request in requests if request["method"] != "GET"]


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self.project_root = root

    def get_guide_dir(self) -> Path:
        path = self.project_root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


def test_write_item_turn_writes_learner_memory_event_only() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="turn",
        dedupe_key="turn:1",
        payload_json={
            "event_id": "evt_turn_1",
            "source_feature": "turn",
            "source_id": "session_1",
            "source_bot_id": "bot_alpha",
            "memory_kind": "turn",
            "payload_json": {
                "session_id": "session_1",
                "capability": "chat",
                "user_message": "你好",
                "assistant_message": "你好，我在。",
                "timestamp": "2026-04-15T10:00:00+08:00",
            },
            "created_at": "2026-04-15T10:00:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == ("users", "learner_memory_events")
    write_requests = _write_requests(requests)
    assert len(write_requests) == 2
    assert write_requests[0]["path"] == "/rest/v1/users"
    assert write_requests[0]["params"]["on_conflict"] == "id"
    assert write_requests[0]["json"][0]["id"] == "student_demo"
    assert write_requests[0]["json"][0]["createdAt"]
    assert "updatedAt" not in write_requests[0]["json"][0]
    request = write_requests[1]
    assert request["path"] == "/rest/v1/learner_memory_events"
    assert request["params"]["on_conflict"] == "dedupe_key"
    assert request["headers"]["apikey"] == "service-key"
    assert request["headers"]["authorization"] == "Bearer service-key"
    assert request["headers"]["prefer"] == "resolution=merge-duplicates,return=representation"
    assert request["json"][0]["memory_kind"] == "turn"
    assert request["json"][0]["payload_json"]["assistant_message"] == "你好，我在。"

    asyncio.run(client.aclose())


def test_new_eval_runner_user_mirror_inherits_canonical_machine_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(tmp_path / "users.json"))
    external_user = ensure_external_auth_user(
        "qa_eval_codex_learner_state",
        "StrongPass123",
    )
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="turn",
        dedupe_key="turn:eval-new",
        user_id=str(external_user["id"]),
        payload_json={"event_id": "evt_eval_new", "source_feature": "turn"},
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    user_write = next(
        request
        for request in _write_requests(requests)
        if request["path"] == "/rest/v1/users"
    )
    assert user_write["method"] == "POST"
    assert user_write["json"][0]["metadata"] == {
        "source": "learner_state_outbox",
        "mirror_reason": "learner_state_fk",
        "account_kind": "eval_runner",
        "actor_type": "machine",
        "created_by": "eval_runner",
        "is_internal_test": True,
        "runner": "codex",
        "agent_tool": "codex",
    }

    asyncio.run(client.aclose())


def test_existing_eval_runner_user_mirror_preserves_registration_time_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(tmp_path / "users.json"))
    external_user = ensure_external_auth_user(
        "qa_eval_claude_learner_state",
        "StrongPass123",
    )
    requests: list[dict[str, object]] = []
    client = _make_client(
        requests,
        existing_user_row={
            "metadata": {
                "source": "learner_state_outbox",
                "mirror_reason": "learner_state_fk",
                "retained_key": "retained_value",
            }
        },
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="turn",
        dedupe_key="turn:eval-existing",
        user_id=str(external_user["id"]),
        payload_json={"event_id": "evt_eval_existing", "source_feature": "turn"},
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    user_write = next(
        request
        for request in _write_requests(requests)
        if request["path"] == "/rest/v1/users"
    )
    assert user_write["method"] == "PATCH"
    assert "createdAt" not in user_write["json"]
    assert user_write["json"]["metadata"]["retained_key"] == "retained_value"
    assert user_write["json"]["metadata"]["account_kind"] == "eval_runner"
    assert user_write["json"]["metadata"]["actor_type"] == "machine"
    assert user_write["json"]["metadata"]["created_by"] == "eval_runner"
    assert user_write["json"]["metadata"]["is_internal_test"] is True

    asyncio.run(client.aclose())


def test_write_item_learning_evidence_writes_learner_memory_event() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="learning_evidence",
        dedupe_key="learning-evidence:1",
        payload_json={
            "event_id": "evt_learning_1",
            "source_feature": "construction_grading",
            "source_id": "turn_1",
            "source_bot_id": "construction-exam-coach",
            "memory_kind": "learning_evidence",
            "payload_json": {
                "event_type": "learning_evidence",
                "question_id": "q_case_1",
                "error_events": [{"concept_tag": "1A432000", "error_code": "E02"}],
            },
            "created_at": "2026-04-15T10:00:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == ("users", "learner_memory_events")
    write_requests = _write_requests(requests)
    assert write_requests[0]["path"] == "/rest/v1/users"
    assert write_requests[0]["json"][0]["id"] == "student_demo"
    assert write_requests[0]["json"][0]["createdAt"]
    assert "updatedAt" not in write_requests[0]["json"][0]
    request = write_requests[1]
    assert request["path"] == "/rest/v1/learner_memory_events"
    assert request["json"][0]["memory_kind"] == "learning_evidence"
    assert request["json"][0]["payload_json"]["error_events"][0]["error_code"] == "E02"

    asyncio.run(client.aclose())


def test_write_item_guide_completion_writes_summary_and_plan(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    path_service = _PathServiceStub(tmp_path)
    plan_service = LearningPlanService(path_service=path_service)
    plan_service.create_plan(
        session_id="guide_42",
        user_id="student_demo",
        source_bot_id="bot_alpha",
        notebook_name="地基基础",
        source_material_refs_json=[{"kind": "user_input", "content": "地基基础"}],
        status="completed",
        current_index=1,
        summary="## 完成总结\n- 已完成引导学习。",
        pages=[
            {
                "page_index": 0,
                "knowledge_title": "承载力",
                "knowledge_summary": "理解极限承载和正常使用状态。",
                "user_difficulty": "medium",
                "html": "<h1>承载力</h1>",
                "page_status": "ready",
            },
            {
                "page_index": 1,
                "knowledge_title": "沉降控制",
                "knowledge_summary": "避免把结构安全和使用性能混在一起。",
                "user_difficulty": "medium",
                "page_status": "failed",
                "page_error": "llm timeout",
            },
        ],
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
        path_service=path_service,
    )
    item = _make_item(
        event_type="guide_completion",
        dedupe_key="guide:guide_42:completion",
        payload_json={
            "event_id": "evt_guide_1",
            "source_feature": "guide",
            "source_id": "guide_42",
            "source_bot_id": "bot_alpha",
            "memory_kind": "guide_completion",
            "payload_json": {
                "guide_id": "guide_42",
                "notebook_name": "地基基础",
                "summary": "## 完成总结\n- 已完成引导学习。",
                "total_points": 2,
                "knowledge_points": [
                    {
                        "knowledge_title": "承载力",
                        "knowledge_summary": "理解极限承载和正常使用状态。",
                        "user_difficulty": "medium",
                    },
                    {
                        "knowledge_title": "沉降控制",
                        "knowledge_summary": "避免把结构安全和使用性能混在一起。",
                        "user_difficulty": "medium",
                    },
                ],
            },
            "created_at": "2026-04-15T10:00:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == (
        "users",
        "learner_memory_events",
        "learner_summaries",
        "learning_plans",
        "learning_plan_pages",
    )
    post_requests = [request for request in requests if request["method"] == "POST"]
    assert [request["path"] for request in post_requests] == [
        "/rest/v1/users",
        "/rest/v1/learner_memory_events",
        "/rest/v1/learner_summaries",
        "/rest/v1/learning_plans",
        "/rest/v1/learning_plan_pages",
    ]
    summary_body = post_requests[2]["json"][0]
    plan_body = post_requests[3]["json"][0]
    page_rows = post_requests[4]["json"]

    assert summary_body["user_id"] == "student_demo"
    assert summary_body["summary_md"].startswith("## 完成总结")
    assert summary_body["summary_structured_json"]["guide_completion"]["guide_id"] == "guide_42"
    assert summary_body["last_refreshed_from_feature"] == "guide_completion"
    assert plan_body["plan_id"] == "guide_42"
    assert plan_body["status"] == "completed"
    assert plan_body["completion_summary_md"].startswith("## 完成总结")
    assert plan_body["source_material_refs_json"][0]["kind"] == "user_input"
    assert plan_body["knowledge_points_json"][0]["knowledge_title"] == "承载力"
    assert len(page_rows) == 2
    assert page_rows[0]["plan_id"] == "guide_42"
    assert page_rows[0]["page_index"] == 0
    assert page_rows[0]["page_status"] == "ready"
    assert page_rows[0]["html_content"] == "<h1>承载力</h1>"
    assert page_rows[1]["page_index"] == 1
    assert page_rows[1]["page_status"] == "failed"
    assert page_rows[1]["error_message"] == "llm timeout"

    asyncio.run(client.aclose())


def test_write_item_learning_plan_page_syncs_single_page_and_parent_plan(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    path_service = _PathServiceStub(tmp_path)
    plan_service = LearningPlanService(path_service=path_service)
    plan_service.create_plan(
        session_id="guide_42",
        user_id="student_demo",
        source_bot_id="bot_alpha",
        notebook_name="地基基础",
        source_material_refs_json=[{"kind": "user_input", "content": "地基基础"}],
        status="learning",
        current_index=0,
        summary="",
        pages=[
            {
                "page_index": 0,
                "knowledge_title": "承载力",
                "knowledge_summary": "理解极限承载和正常使用状态。",
                "user_difficulty": "medium",
                "html": "<h1>承载力</h1>",
                "page_status": "ready",
            },
            {
                "page_index": 1,
                "knowledge_title": "沉降控制",
                "knowledge_summary": "避免把结构安全和使用性能混在一起。",
                "user_difficulty": "medium",
                "page_status": "failed",
                "page_error": "llm timeout",
            },
        ],
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
        path_service=path_service,
    )
    item = _make_item(
        event_type="learning_plan_page",
        dedupe_key="guide:guide_42:page:1",
        payload_json={
            "plan_id": "guide_42",
            "page_index": 1,
            "page_status": "failed",
            "error_message": "llm timeout",
            "generated_at": "2026-04-15T10:15:00+08:00",
            "source_feature": "guide",
            "source_id": "guide_42",
            "source_bot_id": "bot_alpha",
            "memory_kind": "learning_plan_page",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == ("users", "learning_plans", "learning_plan_pages")
    write_requests = _write_requests(requests)
    assert [request["path"] for request in write_requests] == [
        "/rest/v1/users",
        "/rest/v1/learning_plans",
        "/rest/v1/learning_plan_pages",
    ]
    plan_body = write_requests[1]["json"][0]
    page_body = write_requests[2]["json"][0]
    assert plan_body["plan_id"] == "guide_42"
    assert plan_body["status"] == "learning"
    assert page_body["plan_id"] == "guide_42"
    assert page_body["page_index"] == 1
    assert page_body["page_status"] == "failed"
    assert page_body["error_message"] == "llm timeout"

    asyncio.run(client.aclose())


def test_write_item_heartbeat_job_writes_heartbeat_jobs_only(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    path_service = _PathServiceStub(tmp_path)
    heartbeat_service = LearnerHeartbeatService(path_service=path_service)
    job = heartbeat_service.ensure_default_job(
        "student_demo",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 3},
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
        path_service=path_service,
    )
    item = _make_item(
        event_type="heartbeat_job",
        dedupe_key=f"heartbeat-job:{job.job_id}:{job.updated_at.isoformat()}",
        payload_json={
            "job_id": job.job_id,
            "source_feature": "heartbeat_job",
            "source_id": job.job_id,
            "source_bot_id": job.bot_id,
            "memory_kind": "heartbeat_job",
            "updated_at": job.updated_at.isoformat(),
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == ("users", "heartbeat_jobs")
    write_requests = _write_requests(requests)
    assert len(write_requests) == 2
    assert write_requests[0]["path"] == "/rest/v1/users"
    request = write_requests[1]
    assert request["path"] == "/rest/v1/heartbeat_jobs"
    assert request["params"]["on_conflict"] == "user_id,bot_id,channel"
    body = request["json"][0]
    assert body["job_id"] == job.job_id
    assert body["user_id"] == "student_demo"
    assert body["bot_id"] == "bot_alpha"
    assert body["channel"] == "web"
    assert body["status"] == "active"
    assert body["last_result_json"] == {}

    asyncio.run(client.aclose())


def test_write_item_heartbeat_job_preserves_structured_last_result_json(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    path_service = _PathServiceStub(tmp_path)
    heartbeat_service = LearnerHeartbeatService(path_service=path_service)
    job = heartbeat_service.ensure_default_job(
        "student_demo",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 3},
    )
    heartbeat_service.record_run_result(
        user_id="student_demo",
        job_id=job.job_id,
        success=True,
        result_json={"message": "heartbeat response"},
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
        path_service=path_service,
    )
    item = _make_item(
        event_type="heartbeat_job",
        dedupe_key=f"heartbeat-job:{job.job_id}:{job.updated_at.isoformat()}",
        payload_json={
            "job_id": job.job_id,
            "source_feature": "heartbeat_job",
            "source_id": job.job_id,
            "source_bot_id": job.bot_id,
            "memory_kind": "heartbeat_job",
            "updated_at": job.updated_at.isoformat(),
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    body = _write_requests(requests)[1]["json"][0]
    assert body["last_result_json"]["success"] is True
    assert body["last_result_json"]["delivery"]["state"] == "sent"
    assert body["last_result_json"]["audit"]["status"] == "ok"

    asyncio.run(client.aclose())


def test_write_item_summary_refresh_writes_summary_only() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="summary_refresh",
        dedupe_key="summary:session_1",
        payload_json={
            "user_id": "student_demo",
            "summary_md": "## 当前学习概览\n- 已完成一轮概念梳理。",
            "source_feature": "chat",
            "source_id": "session_1",
            "source_bot_id": "bot_alpha",
            "updated_at": "2026-04-15T10:10:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == ("users", "learner_summaries")
    write_requests = _write_requests(requests)
    assert len(write_requests) == 2
    assert write_requests[0]["path"] == "/rest/v1/users"
    request = write_requests[1]
    assert request["path"] == "/rest/v1/learner_summaries"
    assert request["json"][0]["summary_md"].startswith("## 当前学习概览")
    assert request["json"][0]["last_refreshed_from_feature"] == "chat"
    assert request["json"][0]["last_refreshed_from_turn_id"] == "session_1"
    assert "summary_structured_json" not in request["json"][0]

    asyncio.run(client.aclose())


def test_write_item_summary_refresh_preserves_structured_learning_truth() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="summary_refresh",
        dedupe_key="summary:learning-synthesis",
        payload_json={
            "user_id": "student_demo",
            "summary_md": "## 学习事实编译",
            "source_feature": "learning_synthesis",
            "source_id": "nightly_synthesis",
            "summary_structured_json": {
                "learning_brain": {
                    "subject": "construction_exam_learning_truth",
                    "weak_points": [{"concept_id": "1A432000"}],
                    "typed_graph": {},
                },
            },
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    request = requests[-1]
    assert request["path"] == "/rest/v1/learner_summaries"
    learning_brain = request["json"][0]["summary_structured_json"]["learning_brain"]
    assert learning_brain["subject"] == "construction_exam_learning_truth"
    assert learning_brain["weak_points"][0]["concept_id"] == "1A432000"

    asyncio.run(client.aclose())


def test_write_item_summary_refresh_key_merges_existing_guide_completion() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(
        requests,
        existing_summary_structured_json={
            "guide_completion": {
                "guide_id": "guide_42",
                "notebook_name": "地基基础",
            }
        },
    )
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="summary_refresh",
        dedupe_key="summary:learning-synthesis",
        payload_json={
            "summary_md": "## 学习事实编译",
            "source_feature": "learning_synthesis",
            "source_id": "nightly_synthesis",
            "summary_structured_json": {
                "learning_brain": {
                    "subject": "construction_exam_learning_truth",
                    "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
                },
            },
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    summary_post = [request for request in requests if request["path"] == "/rest/v1/learner_summaries"][-1]
    structured = summary_post["json"][0]["summary_structured_json"]
    assert structured["guide_completion"]["guide_id"] == "guide_42"
    assert structured["learning_brain"]["weak_points"][0]["error_code"] == "E02"

    asyncio.run(client.aclose())


def test_write_item_guide_completion_key_merges_existing_learning_brain(tmp_path) -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(
        requests,
        existing_summary_structured_json={
            "learning_brain": {
                "subject": "construction_exam_learning_truth",
                "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
            }
        },
    )
    path_service = _PathServiceStub(tmp_path)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
        path_service=path_service,
    )
    item = _make_item(
        event_type="guide_completion",
        dedupe_key="guide:guide_42:completion",
        payload_json={
            "event_id": "evt_guide_1",
            "source_feature": "guide",
            "source_id": "guide_42",
            "source_bot_id": "bot_alpha",
            "memory_kind": "guide_completion",
            "payload_json": {
                "guide_id": "guide_42",
                "notebook_name": "地基基础",
                "summary": "## 完成总结\n- 已完成引导学习。",
                "total_points": 1,
                "knowledge_points": [
                    {
                        "knowledge_title": "承载力",
                        "knowledge_summary": "理解极限承载和正常使用状态。",
                        "user_difficulty": "medium",
                    }
                ],
            },
            "created_at": "2026-04-15T10:00:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    summary_post = [
        request
        for request in requests
        if request["method"] == "POST" and request["path"] == "/rest/v1/learner_summaries"
    ][0]
    structured = summary_post["json"][0]["summary_structured_json"]
    assert structured["learning_brain"]["subject"] == "construction_exam_learning_truth"
    assert structured["guide_completion"]["guide_id"] == "guide_42"

    asyncio.run(client.aclose())


def test_write_item_guide_completion_without_summary_fails_before_network() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="guide_completion",
        dedupe_key="guide:guide_43:completion",
        payload_json={
            "event_id": "evt_guide_2",
            "source_feature": "guide",
            "source_id": "guide_43",
            "guide_id": "guide_43",
            "notebook_name": "地基基础",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is False
    assert "guide_id or summary" in (result.reason or "")
    assert requests == []

    asyncio.run(client.aclose())


def test_write_item_unknown_event_type_is_rejected_without_network() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="manual",
        dedupe_key="manual:1",
        payload_json={"event_id": "evt_manual_1"},
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is False
    assert "unsupported event_type" in (result.reason or "")


def test_write_item_overlay_patch_writes_overlay_tables_and_event_stream() -> None:
    requests: list[dict[str, object]] = []
    client = _make_client(requests)
    writer = LearnerStateSupabaseWriter(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    item = _make_item(
        event_type="overlay_patch",
        dedupe_key="overlay-sync:overlay_patch:student_demo:bot_alpha:2",
        payload_json={
            "bot_id": "bot_alpha",
            "user_id": "student_demo",
            "overlay_version": 2,
            "overlay_write_type": "patch",
            "overlay_write_reason": "guide",
            "source_feature": "guide",
            "source_id": "guide_42",
            "overlay_fields": ["active_plan_binding", "local_focus"],
            "promotion_candidate_count": 1,
            "overlay_snapshot": {
                "local_focus": {"knowledge_title": "承载力"},
                "active_plan_binding": {"plan_id": "plan_1", "current_index": 0},
                "teaching_policy_override": {},
                "heartbeat_override": {},
                "channel_presence_override": {},
                "local_notebook_scope_refs": ["nb_1"],
                "engagement_state": {"last_context_route": "guided_plan_continuation"},
                "promotion_candidates": [{"candidate_id": "cand_1"}],
                "working_memory_projection": "继续当前计划",
            },
            "created_at": "2026-04-15T10:00:00+08:00",
        },
    )

    result = asyncio.run(writer.write_item(item))

    assert result.ok is True
    assert result.written_tables == (
        "users",
        "learner_memory_events",
        "bot_learner_overlays",
        "bot_learner_overlay_events",
        "bot_learner_overlay_audit",
    )
    write_requests = _write_requests(requests)
    assert [request["path"] for request in write_requests] == [
        "/rest/v1/users",
        "/rest/v1/learner_memory_events",
        "/rest/v1/bot_learner_overlays",
        "/rest/v1/bot_learner_overlay_events",
        "/rest/v1/bot_learner_overlay_audit",
    ]
    overlay_body = write_requests[2]["json"][0]
    event_body = write_requests[3]["json"][0]
    audit_body = write_requests[4]["json"][0]
    assert overlay_body["bot_id"] == "bot_alpha"
    assert overlay_body["active_plan_id"] == "plan_1"
    assert overlay_body["working_memory_projection_md"] == "继续当前计划"
    assert event_body["patch_kind"] == "overlay_patch"
    assert event_body["payload_json"]["overlay_write_reason"] == "guide"
    assert audit_body["action"] == "overlay_patch"
    assert audit_body["fields_json"] == ["active_plan_binding", "local_focus"]

    asyncio.run(client.aclose())
