from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from deeptutor.services.learner_state.heartbeat.store import LearnerHeartbeatJob
from deeptutor.services.learner_state.runtime import (
    LearnerHeartbeatExecutor,
    LearnerStateRuntime,
    LearnerStateRuntimeConfig,
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
    executor = LearnerHeartbeatExecutor(tutorbot_manager=manager)
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
    assert manager.calls[0]["bot_id"] == "bot_alpha"
    assert manager.calls[0]["session_metadata"]["user_id"] == "student_demo"
    assert manager.calls[0]["session_metadata"]["source"] == "learner_heartbeat"
