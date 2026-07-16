from __future__ import annotations

import asyncio
import json

import httpx

from deeptutor.services.learner_state.supabase_store import (
    LearnerStateSupabaseClient,
    LearnerStateSupabaseCoreStore,
    LearnerStateSupabaseSyncCoreStore,
)


def _make_client(requests: list[dict[str, object]], state: dict[str, object]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "json": json.loads(body) if body else None,
            }
        )

        table = request.url.path.rsplit("/", 1)[-1]
        params = dict(request.url.params)
        if request.method == "GET":
            if table == "user_profiles":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                row = dict(state["user_profiles"].get(user_id, {}))
                return httpx.Response(200, json=[row] if row else [], request=request)
            if table == "user_stats":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                row = dict(state["user_stats"].get(user_id, {}))
                return httpx.Response(200, json=[row] if row else [], request=request)
            if table == "user_goals":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                rows = [
                    dict(row)
                    for row in state["user_goals"]
                    if str(row.get("user_id", "")).strip() == user_id
                ]
                rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
                return httpx.Response(200, json=rows, request=request)
            if table == "learner_summaries":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                row = dict(state.get("learner_summaries", {}).get(user_id, {}))
                return httpx.Response(200, json=[row] if row else [], request=request)
            if table == "learner_memory_events":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                event_id = str(params.get("event_id", "")).replace("eq.", "")
                rows = [
                    dict(row)
                    for row in state.get("learner_memory_events", [])
                    if str(row.get("user_id") or "") == user_id
                    and (not event_id or str(row.get("event_id") or "") == event_id)
                ]
                return httpx.Response(200, json=rows[: int(params.get("limit", 100) or 100)], request=request)

        if request.method == "POST":
            payload = json.loads(body or "[]")
            row = dict(payload[0] if isinstance(payload, list) and payload else payload)
            if table == "user_profiles":
                state["user_profiles"][row["user_id"]] = row
            elif table == "user_stats":
                state["user_stats"][row["user_id"]] = row
            elif table == "user_goals":
                goals = state["user_goals"]
                if row.get("id") in (None, ""):
                    numeric_ids = [
                        int(item.get("id", 0) or 0)
                        for item in goals
                        if str(item.get("id", "")).strip().isdigit()
                    ]
                    row["id"] = max(numeric_ids + [0]) + 1
                goals[:] = [item for item in goals if str(item.get("id", "")).strip() != str(row.get("id", "")).strip()]
                goals.append(row)
            elif table == "learner_summaries":
                state.setdefault("learner_summaries", {})[row["user_id"]] = row
            return httpx.Response(200, json=[row], request=request)

        if request.method == "DELETE" and table == "user_goals":
            goal_id = str(params.get("id", "")).replace("eq.", "")
            state["user_goals"][:] = [row for row in state["user_goals"] if str(row.get("id", "")).strip() != goal_id]
            return httpx.Response(200, json=[], request=request)

        return httpx.Response(400, json={"error": "unsupported"}, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")


def test_profile_read_write_and_merge_uses_user_id_filter() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {
            "student_demo": {
                "user_id": "student_demo",
                "summary": "基础画像",
                "attributes": {"tier": "vip"},
                "last_updated": "2026-04-15T10:00:00+08:00",
            }
        },
        "user_stats": {},
        "user_goals": [],
        "learner_summaries": {},
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        profile = await store.read_profile("student_demo")
        assert profile["summary"] == "基础画像"

        updated = await store.merge_profile("student_demo", {"attributes": {"tier": "gold"}, "summary": "更新画像"})
        assert updated["attributes"]["tier"] == "gold"
        assert updated["summary"] == "更新画像"

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_profiles"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[0]["params"]["limit"] == "1"
    assert requests[2]["path"] == "/rest/v1/user_profiles"
    assert requests[2]["params"]["on_conflict"] == "user_id"
    assert state["user_profiles"]["student_demo"]["summary"] == "更新画像"

    asyncio.run(transport_client.aclose())


def test_stats_read_write_and_merge_uses_user_id_filter() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {
            "student_demo": {
                "user_id": "student_demo",
                "mastery_level": 2,
                "total_attempts": 10,
                "error_count": 3,
            }
        },
        "user_goals": [],
        "learner_summaries": {},
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        stats = await store.read_stats("student_demo")
        assert stats["mastery_level"] == 2

        updated = await store.merge_stats("student_demo", {"mastery_level": 3, "last_practiced_at": "2026-04-15"})
        assert updated["mastery_level"] == 3
        assert updated["last_practiced_at"] == "2026-04-15"

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_stats"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[2]["path"] == "/rest/v1/user_stats"
    assert requests[2]["params"]["on_conflict"] == "user_id"
    assert state["user_stats"]["student_demo"]["mastery_level"] == 3
    assert state["user_stats"]["student_demo"]["tag"] == ""

    asyncio.run(transport_client.aclose())


def test_stats_preserves_home_personalization_projection_inside_knowledge_map() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [],
        "learner_summaries": {},
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)
    projection = {
        "source_status": {
            "fallback_used": False,
            "learning_report": "projection",
            "home_projection_contract": "canonical_taxonomy_v1",
            "topic_authority": "learner_state.home_personalization.canonical_taxonomy",
        },
        "today_focus": {"title": "今日焦点：防水工程"},
        "recommended_prompts": [
            {
                "prompt_type": "practice_prompt",
                "text": "用 3 道题训练防水工程",
                "intent": {"source": "learner_state.home_personalization", "concept_label": "防水工程"},
            }
        ],
    }

    async def _run() -> None:
        saved = await store.upsert_stats(
            "student_demo",
            {
                "mastery_level": 2,
                "knowledge_map": {"weak_points": ["防水工程"]},
                "home_personalization": projection,
            },
        )
        assert saved["home_personalization"]["today_focus"]["title"] == "今日焦点：防水工程"

        read_back = await store.read_stats("student_demo")
        assert read_back["home_personalization"]["today_focus"]["title"] == "今日焦点：防水工程"
        assert read_back["projections"]["home_personalization"]["recommended_prompts"][0]["text"] == (
            "用 3 道题训练防水工程"
        )

    asyncio.run(_run())
    row = state["user_stats"]["student_demo"]
    assert row["knowledge_map"]["projections"]["home_personalization"]["today_focus"]["title"] == (
        "今日焦点：防水工程"
    )

    asyncio.run(transport_client.aclose())


def test_goals_list_upsert_and_delete_use_goal_primary_key() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [
            {
                "id": "goal_2",
                "user_id": "student_demo",
                "goal_type": "review",
                "title": "复习承载力",
                "created_at": "2026-04-15T10:20:00+08:00",
            },
            {
                "id": "goal_1",
                "user_id": "student_demo",
                "goal_type": "study",
                "title": "学习沉降控制",
                "created_at": "2026-04-15T10:10:00+08:00",
            },
        ],
        "learner_summaries": {},
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        goals = await store.read_goals("student_demo")
        assert [goal["id"] for goal in goals] == ["goal_2", "goal_1"]

        saved = await store.upsert_goal(
            {
                "user_id": "student_demo",
                "goal_type": "study",
                "title": "完成本周案例题",
                "target_node_codes": ["node_a"],
            }
        )
        assert saved["user_id"] == "student_demo"
        assert saved["title"] == "完成本周案例题"
        await store.delete_goal(saved["id"])

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_goals"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[0]["params"]["order"] == "created_at.desc"
    assert requests[1]["path"] == "/rest/v1/user_goals"
    assert requests[1]["params"]["on_conflict"] == "id"
    assert requests[2]["path"] == "/rest/v1/user_goals"
    assert requests[2]["params"]["id"].startswith("eq.")
    assert len(state["user_goals"]) == 2

    asyncio.run(transport_client.aclose())


def test_read_compiled_learning_truth_uses_summary_structured_json() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [],
        "learner_summaries": {
            "student_demo": {
                "user_id": "student_demo",
                "summary_md": "## 学习事实编译",
                "summary_structured_json": {
                    "learning_brain": {
                        "subject": "construction_exam_learning_truth",
                        "weak_points": [{"concept_id": "1A432000", "error_code": "E04"}],
                        "typed_graph": {},
                    },
                },
            }
        },
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        projection = await store.read_compiled_learning_truth("student_demo")
        assert projection["subject"] == "construction_exam_learning_truth"
        assert projection["weak_points"][0]["error_code"] == "E04"

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/learner_summaries"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[0]["params"]["limit"] == "1"

    asyncio.run(transport_client.aclose())


def test_write_compiled_learning_truth_key_merges_summary_structured_json() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [],
        "learner_summaries": {
            "student_demo": {
                "user_id": "student_demo",
                "summary_md": "## 既有摘要",
                "summary_structured_json": {
                    "guide_completion": {"guide_id": "guide_42"},
                    "learning_brain": {
                        "subject": "old",
                        "weak_points": [{"concept_id": "old"}],
                    },
                },
            }
        },
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        saved = await store.write_compiled_learning_truth(
            "student_demo",
            {
                "subject": "construction_exam_learning_truth",
                "weak_points": [{"concept_id": "1A432000", "error_code": "E04"}],
                "synthesis_run": {"output_projection_hash": "sha256:new"},
            },
        )
        assert saved["synthesis_run"]["output_projection_hash"] == "sha256:new"

    asyncio.run(_run())
    post = [request for request in requests if request["method"] == "POST"][-1]
    assert post["path"] == "/rest/v1/learner_summaries"
    assert post["params"]["on_conflict"] == "user_id"
    structured = post["json"][0]["summary_structured_json"]
    assert structured["guide_completion"]["guide_id"] == "guide_42"
    assert structured["learning_brain"]["weak_points"][0]["error_code"] == "E04"

    asyncio.run(transport_client.aclose())


def test_sync_write_compiled_learning_truth_key_merges_summary_structured_json() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "json": json.loads(body) if body else None,
            }
        )
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "user_id": "student_demo",
                        "summary_md": "## 既有摘要",
                        "summary_structured_json": {
                            "guide_completion": {"guide_id": "guide_42"},
                            "learning_brain": {"subject": "old"},
                        },
                    }
                ],
                request=request,
            )
        if request.method == "POST":
            return httpx.Response(200, json=json.loads(body), request=request)
        return httpx.Response(400, json={"error": "unsupported"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")
    store = LearnerStateSupabaseSyncCoreStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    saved = store.write_compiled_learning_truth(
        "student_demo",
        {
            "subject": "construction_exam_learning_truth",
            "weak_points": [{"concept_id": "1A432000", "error_code": "E04"}],
            "synthesis_run": {"output_projection_hash": "sha256:new"},
        },
    )

    post = [request for request in requests if request["method"] == "POST"][-1]
    structured = post["json"][0]["summary_structured_json"]
    assert saved["synthesis_run"]["output_projection_hash"] == "sha256:new"
    assert structured["guide_completion"]["guide_id"] == "guide_42"
    assert structured["learning_brain"]["weak_points"][0]["error_code"] == "E04"


def test_read_learning_evidence_event_uses_user_event_and_memory_kind_filters() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [],
        "learner_summaries": {},
        "learner_memory_events": [
            {
                "event_id": "evt_direct",
                "user_id": "student_demo",
                "source_feature": "construction_grading",
                "memory_kind": "learning_evidence",
                "payload_json": {"event_type": "learning_evidence"},
            }
        ],
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        row = await store.read_learning_evidence_event("student_demo", "evt_direct")
        assert row is not None
        assert row["event_id"] == "evt_direct"

    asyncio.run(_run())
    assert requests[-1]["path"] == "/rest/v1/learner_memory_events"
    assert requests[-1]["params"]["user_id"] == "eq.student_demo"
    assert requests[-1]["params"]["event_id"] == "eq.evt_direct"
    assert requests[-1]["params"]["memory_kind"] == "eq.learning_evidence"
    assert requests[-1]["params"]["limit"] == "1"

    asyncio.run(transport_client.aclose())


def test_sync_full_learning_evidence_read_pages_past_postgrest_row_cap() -> None:
    requests: list[dict[str, str]] = []
    rows = [
        {
            "event_id": f"evt_{index:04d}",
            "user_id": "student_demo",
            "memory_kind": "learning_evidence",
            "created_at": f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
            "payload_json": {"event_type": "learning_evidence"},
        }
        for index in range(1201)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests.append(params)
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 500))
        return httpx.Response(200, json=rows[offset : offset + limit], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = LearnerStateSupabaseSyncCoreStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    projected = store.read_learning_evidence_events("student_demo", limit=None, since=None)

    assert len(projected) == 1201
    assert [request["offset"] for request in requests] == ["0", "500", "1000"]
    client.close()


def test_sync_retest_probe_claim_and_completion_read_use_narrow_rpcs() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append({"path": request.url.path, "json": payload})
        if request.url.path.endswith("/claim_luban_retest_probe"):
            return httpx.Response(
                200,
                json={
                    "status": "acquired",
                    "completion_id": payload["p_completion_id"],
                    "request_hash": payload["p_request_hash"],
                    "claim_event_id": "claim-event",
                },
                request=request,
            )
        if request.url.path.endswith("/read_luban_retest_completion_events"):
            return httpx.Response(
                200,
                json=[
                    {
                        "event_id": "terminal-event",
                        "user_id": payload["p_user_id"],
                        "source_feature": "assessment_testset",
                        "source_id": f"{payload['p_completion_id']}:terminal",
                        "memory_kind": "learning_evidence",
                        "payload_json": {
                            "retest_completion_id": payload["p_completion_id"],
                            "completion_terminal": True,
                        },
                        "dedupe_key": "terminal-key",
                        "created_at": "2026-07-16T00:00:00+00:00",
                    }
                ],
                request=request,
            )
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = LearnerStateSupabaseSyncCoreStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    claim = store.claim_retest_probe(
        user_id="student_demo",
        probe_id="probe-1",
        cycle_anchor="cycle-1",
        completion_id="completion-1",
        request_hash="a" * 64,
    )
    events = store.read_retest_completion_events(
        user_id="student_demo",
        completion_id="completion-1",
    )

    assert claim["status"] == "acquired"
    assert events[0]["event_id"] == "terminal-event"
    assert requests == [
        {
            "path": "/rest/v1/rpc/claim_luban_retest_probe",
            "json": {
                "p_user_id": "student_demo",
                "p_probe_id": "probe-1",
                "p_cycle_anchor": "cycle-1",
                "p_completion_id": "completion-1",
                "p_request_hash": "a" * 64,
            },
        },
        {
            "path": "/rest/v1/rpc/read_luban_retest_completion_events",
            "json": {
                "p_user_id": "student_demo",
                "p_completion_id": "completion-1",
            },
        },
    ]
    client.close()
