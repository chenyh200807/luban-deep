from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from deeptutor.services.learner_state.heartbeat.store import LearnerHeartbeatJob
from deeptutor.services.learner_state.runtime import (
    LearnerHeartbeatExecutor,
    LearnerStateRuntime,
    LearnerStateRuntimeConfig,
    _default_heartbeat_hint_resolver,
)


class _FakeFlusher:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def flush_once(self, *, limit: int = 20):
        self.calls.append(limit)
        return None


class _FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    async def run_once(self, *, limit: int | None = None):
        self.calls.append(limit)
        return []


class _FakeWriter:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeTutorBotManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return "heartbeat response"


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self._learning_plan_service = SimpleNamespace(
            list_plans=lambda: [
                {
                    "user_id": "student_demo",
                    "source_bot_id": "bot_alpha",
                    "status": "in_progress",
                    "updated_at": 200.0,
                },
                {
                    "user_id": "student_demo",
                    "source_bot_id": "bot_beta",
                    "status": "ready",
                    "updated_at": 100.0,
                },
            ]
        )

    def read_snapshot(self, _user_id: str):
        return type(
            "Snapshot",
            (),
            {
                "profile": {
                    "focus_topic": "地基基础承载力",
                    "exam_date": "2026-09-19",
                    "difficulty_preference": "hard",
                },
                "progress": {
                    "today": {"today_done": 2, "daily_target": 10},
                    "knowledge_map": {"weak_points": ["沉降控制"]},
                    "last_practiced_at": "2026-04-15T10:00:00+08:00",
                },
            },
        )()

    def read_goals(self, _user_id: str):
        return [{"title": "本周完成 20 道案例题", "progress": 8, "deadline": "2026-04-20"}]

    def list_memory_events(self, _user_id: str, limit: int | None = 50):
        _ = limit
        return [
            SimpleNamespace(source_bot_id="bot_beta", source_feature="guide"),
            SimpleNamespace(source_bot_id="bot_alpha", source_feature="turn"),
        ]


async def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("timeout waiting for condition")
        await asyncio.sleep(0)


def test_runtime_start_and_stop_runs_background_loops() -> None:
    flusher = _FakeFlusher()
    scheduler = _FakeScheduler()
    writer = _FakeWriter()
    runtime = LearnerStateRuntime(
        flusher=flusher,
        heartbeat_scheduler=scheduler,
        writer=writer,
        config=LearnerStateRuntimeConfig(
            outbox_flush_interval_seconds=3600,
            heartbeat_interval_seconds=3600,
            outbox_flush_limit=7,
            heartbeat_limit=3,
        ),
    )

    async def _run() -> None:
        await runtime.start()
        await _wait_until(lambda: flusher.calls and scheduler.calls)
        await runtime.stop()

    asyncio.run(_run())

    assert flusher.calls == [7]
    assert scheduler.calls == [3]
    assert writer.closed is True
    assert runtime.is_running is False


def test_learner_heartbeat_executor_uses_tutorbot_manager_send_message() -> None:
    manager = _FakeTutorBotManager()
    executor = LearnerHeartbeatExecutor(
        tutorbot_manager=manager,
        learner_state_service=_FakeLearnerStateService(),
    )
    job = LearnerHeartbeatJob(
        job_id="job_1",
        user_id="student_demo",
        bot_id="bot_alpha",
        channel="heartbeat",
        policy_json={"cadence": "daily"},
        next_run_at=datetime.now(timezone.utc),
        last_run_at=None,
        last_result_json=None,
        failure_count=0,
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    result = asyncio.run(executor(job))

    assert result["message"] == "heartbeat response"
    assert result["delivery_state"] == "sent"
    assert result["delivery"]["state"] == "sent"
    assert result["delivery"]["message"] == "heartbeat response"
    assert result["audit"]["job_id"] == "job_1"
    assert result["audit"]["status"] == "ok"
    assert manager.calls[0]["bot_id"] == "bot_alpha"
    assert manager.calls[0]["session_metadata"]["user_id"] == "student_demo"
    assert manager.calls[0]["session_metadata"]["source"] == "learner_heartbeat"
    prompt = manager.calls[0]["content"]
    assert "当前作战方案" in prompt
    assert "今日主攻：地基基础承载力" in prompt
    assert "优先任务：" in prompt
    assert "地基基础承载力" in prompt
    assert "沉降控制" in prompt
    assert "本周完成 20 道案例题" in prompt


def test_default_heartbeat_hint_resolver_collects_active_plan_recent_interaction_and_overlay(
    monkeypatch,
) -> None:
    service = _FakeLearnerStateService()
    resolver = _default_heartbeat_hint_resolver(service)

    class _FakeOverlayService:
        def resolve_heartbeat_inputs(self, bot_id: str, user_id: str):
            if bot_id == "bot_alpha" and user_id == "student_demo":
                return {
                    "heartbeat_override_candidate": {
                        "priority_bonus": 8,
                        "cadence": "review",
                    }
                }
            return {"heartbeat_override_candidate": {}}

    monkeypatch.setattr(
        "deeptutor.services.learner_state.overlay_service.get_bot_learner_overlay_service",
        lambda: _FakeOverlayService(),
    )

    jobs = [
        LearnerHeartbeatJob(
            job_id="job_1",
            user_id="student_demo",
            bot_id="bot_alpha",
            channel="heartbeat",
            policy_json={"cooldown_hours": 4},
            next_run_at=datetime.now(timezone.utc),
            last_run_at=datetime(2026, 4, 16, 8, 0, tzinfo=timezone.utc),
            last_result_json=None,
            failure_count=0,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        LearnerHeartbeatJob(
            job_id="job_2",
            user_id="student_demo",
            bot_id="bot_beta",
            channel="heartbeat",
            policy_json={},
            next_run_at=datetime.now(timezone.utc),
            last_run_at=None,
            last_result_json=None,
            failure_count=0,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]

    hints = asyncio.run(resolver("student_demo", jobs))

    assert hints.active_plan_bot_id == "bot_alpha"
    assert hints.learner_goal_urgency_by_bot_id["bot_alpha"] >= 1
    assert hints.recent_interaction_source_by_bot_id["bot_alpha"] == "turn"
    assert hints.recent_interaction_source_by_bot_id["bot_beta"] == "guide"
    assert hints.overlay_heartbeat_override_by_bot_id["bot_alpha"]["priority_bonus"] == 8
    assert hints.recently_contacted_until_by_bot_id["bot_alpha"] == datetime(
        2026, 4, 16, 12, 0, tzinfo=timezone.utc
    )
