from __future__ import annotations

import asyncio
import json

from deeptutor.services.learner_state.service import LearnerStateEvent, LearnerStateOutboxService, LearnerStateService


class _PathServiceStub:
    def __init__(self, root):
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_user_root(self):
        return self._root

    def get_tutor_state_root(self):
        return self._root / "tutor_state"

    def get_learner_state_root(self):
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _FakeMemberService:
    def get_profile(self, user_id: str):
        return {
            "user_id": user_id,
            "display_name": "陈同学",
            "tier": "vip",
            "status": "active",
            "difficulty_preference": "medium",
            "explanation_style": "detailed",
            "daily_target": 30,
            "review_reminder": True,
            "level": 7,
            "points": 240,
            "exam_date": "2026-09-19",
            "focus_topic": "地基基础承载力",
            "focus_query": "承载力和沉降控制怎么区分",
        }

    def get_today_progress(self, user_id: str):
        return {"today_done": 6, "daily_target": 30, "streak_days": 4}

    def get_chapter_progress(self, user_id: str):
        return [
            {"chapter_id": "ch_1", "chapter_name": "地基基础", "done": 12, "total": 30},
            {"chapter_id": "ch_2", "chapter_name": "结构构造", "done": 8, "total": 30},
        ]


def _make_service(tmp_path):
    return LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_FakeMemberService(),
    )


def test_learner_state_build_context_seeds_profile_summary_progress(tmp_path) -> None:
    service = _make_service(tmp_path)

    context = service.build_context("student_demo", language="zh")
    profile_path = tmp_path / "learner_state" / "student_demo" / "PROFILE.json"
    summary_path = tmp_path / "learner_state" / "student_demo" / "SUMMARY.md"
    progress_path = tmp_path / "learner_state" / "student_demo" / "PROGRESS.json"

    assert "学员级长期状态" in context
    assert "地基基础承载力" in context
    assert "今日进度" in context
    assert profile_path.exists()
    assert summary_path.exists()
    assert progress_path.exists()

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    summary = summary_path.read_text(encoding="utf-8")

    assert profile["display_name"] == "陈同学"
    assert progress["today"]["today_done"] == 6
    assert "当前学习概览" in summary


def test_learner_state_write_progress_and_refresh_from_turn(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    service.build_context("student_demo", language="zh")
    service.merge_progress("student_demo", {"today": {"today_done": 8}})

    async def _rewrite_stream(**_kwargs):
        yield (
            "## 当前学习概览\n"
            "- 已完成一轮概念巩固。\n\n"
            "## 稳定偏好\n"
            "- 继续保持详细讲解。\n\n"
            "## 待持续观察\n"
            "- 继续关注承载力与沉降控制的区分。"
        )

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _rewrite_stream)

    result = asyncio.run(
        service.refresh_from_turn(
            user_id="student_demo",
            user_message="我总是把承载力和沉降控制混在一起。",
            assistant_message="先区分极限承载能力和正常使用阶段的沉降控制，再做两道案例题。",
            session_id="session_1",
            capability="chat",
            language="zh",
        )
    )

    summary_path = tmp_path / "learner_state" / "student_demo" / "SUMMARY.md"
    events_path = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"

    assert result.changed is True
    assert "已完成一轮概念巩固" in result.content
    assert "沉降控制" in summary_path.read_text(encoding="utf-8")

    event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(event_lines) == 1
    event = json.loads(event_lines[0])
    assert event["memory_kind"] == "turn"
    assert event["payload_json"]["assistant_message"].startswith("先区分极限承载能力")

    pending = service.outbox_service.list_pending("student_demo", limit=10)
    assert len(pending) == 2
    event_types = {item.event_type for item in pending}
    assert "turn" in event_types
    assert "summary_refresh" in event_types


def test_learner_state_skips_low_signal_turn_writeback(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    service.build_context("student_demo", language="zh")
    before_summary = service.read_summary("student_demo")

    async def _unexpected_stream(**_kwargs):
        raise AssertionError("low-signal turn should not trigger summary rewrite")
        yield ""

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _unexpected_stream)

    result = asyncio.run(
        service.refresh_from_turn(
            user_id="student_demo",
            user_message="你好",
            assistant_message="你好，我在。",
            session_id="session_hello",
            capability="chat",
            language="zh",
        )
    )

    events_path = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"
    assert result.changed is False
    assert service.read_summary("student_demo") == before_summary
    assert not events_path.exists()


def test_learner_state_learning_plan_store_tracks_plan_and_pages(tmp_path) -> None:
    service = _make_service(tmp_path)

    async def _run():
        await service.upsert_learning_plan(
            user_id="student_demo",
            plan_id="session_demo",
            source_bot_id="bot_alpha",
            source_material_refs_json=[
                {"kind": "user_input", "content": "请帮我设计一个学习计划。"},
            ],
            knowledge_points_json=[
                {
                    "knowledge_title": "地基基础承载力",
                    "knowledge_summary": "梳理极限承载力与正常使用阶段控制。",
                }
            ],
            status="initialized",
            current_index=-1,
        )
        await service.update_learning_plan_page(
            user_id="student_demo",
            plan_id="session_demo",
            page_index=0,
            page_status="ready",
            html_content="<div class='page'>学习页面</div>",
            error_message="",
            source_bot_id="bot_alpha",
        )
        await service.upsert_learning_plan(
            user_id="student_demo",
            plan_id="session_demo",
            source_bot_id="bot_alpha",
            knowledge_points_json=[
                {
                    "knowledge_title": "地基基础承载力",
                    "knowledge_summary": "梳理极限承载力与正常使用阶段控制。",
                }
            ],
            status="completed",
            current_index=0,
            completion_summary_md="## 完成总结\n- 已完成本次 guided learning。",
        )

    asyncio.run(_run())

    plan_path = tmp_path / "workspace" / "guide" / "learning_plans" / "session_demo.json"
    pages_path = tmp_path / "workspace" / "guide" / "learning_plan_pages" / "session_demo.json"

    assert plan_path.exists()
    assert pages_path.exists()

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    pages = json.loads(pages_path.read_text(encoding="utf-8"))

    assert plan["session_id"] == "session_demo"
    assert plan["user_id"] == "student_demo"
    assert plan["status"] == "completed"
    assert plan["current_index"] == 0
    assert plan["source_bot_id"] == "bot_alpha"
    assert plan["summary"].startswith("## 完成总结")
    assert plan["source_material_refs_json"][0]["kind"] == "user_input"

    assert pages[0]["session_id"] == "session_demo"
    assert pages[0]["page_status"] == "ready"
    assert pages[0]["html"] == "<div class='page'>学习页面</div>"
    assert pages[0]["updated_at"]


def test_learner_state_outbox_enqueue_and_status_transitions(tmp_path) -> None:
    outbox = LearnerStateOutboxService(path_service=_PathServiceStub(tmp_path))
    payload = {
        "event_id": "evt_1",
        "source_feature": "progress",
        "source_id": "progress_1",
        "source_bot_id": "bot_a",
        "memory_kind": "progress",
        "payload_json": {"done": 1},
    }

    first = outbox.enqueue(
        id="evt_1",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:00+08:00",
    )
    second = outbox.enqueue(
        id="evt_1_dup",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:01+08:00",
    )

    assert first.id == second.id
    assert len(outbox.list_pending("student_demo")) == 1
    failed = outbox.mark_failed(first.id, last_error="network down")
    assert failed is not None
    assert failed.status == "pending"
    assert failed.retry_count == 1

    failed_view = outbox.enqueue(
        id="evt_1_retry",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:02+08:00",
    )
    assert failed_view.status == "pending"
    assert failed_view.retry_count == 1

    sent = outbox.mark_sent(first.id)
    assert sent is not None
    assert sent.status == "sent"


def test_learner_state_guide_completion_enqueues_outbox_event(tmp_path) -> None:
    service = _make_service(tmp_path)

    event = asyncio.run(
        service.record_guide_completion(
            user_id="student_demo",
            guide_id="guide_42",
            notebook_name="地基基础",
            summary="已完成本次引导并收口关键误区。",
            knowledge_points=[
                {
                    "knowledge_title": "承载力和沉降控制",
                    "knowledge_summary": "先分清极限承载和正常使用极限状态。",
                    "user_difficulty": "medium",
                }
            ],
            source_bot_id="bot_a",
        )
    )

    pending = service.outbox_service.list_pending("student_demo")

    assert len(pending) == 1
    item = pending[0]
    assert item.id == event.event_id
    assert item.event_type == "guide_completion"
    assert item.payload_json["source_feature"] == "guide"
    assert item.payload_json["payload_json"]["summary"] == "已完成本次引导并收口关键误区。"
    assert (
        item.payload_json["payload_json"]["knowledge_points"][0]["knowledge_title"]
        == "承载力和沉降控制"
    )
