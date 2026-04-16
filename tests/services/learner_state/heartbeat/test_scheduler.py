from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.heartbeat.scheduler import LearnerHeartbeatScheduler
from deeptutor.services.learner_state.heartbeat.service import LearnerHeartbeatService


class _PathServiceStub:
    def __init__(self, root):
        self.project_root = root


def _service(tmp_path, current):
    return LearnerHeartbeatService(
        path_service=_PathServiceStub(tmp_path),
        clock=lambda: current[0],
    )


def test_scheduler_run_once_filters_due_jobs_and_respects_limit(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    first = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] - timedelta(minutes=10),
    )
    second = service.upsert_job(
        user_id="student_2",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] - timedelta(minutes=5),
    )
    future = service.upsert_job(
        user_id="student_3",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] + timedelta(hours=1),
    )
    service.pause_job(second.job_id)

    seen: list[str] = []

    async def _executor(job):
        seen.append(job.job_id)
        return {"delivered": True}

    scheduler = LearnerHeartbeatScheduler(service=service, executor=_executor)
    results = asyncio.run(scheduler.run_once(limit=1, now=current[0]))

    assert seen == [first.job_id]
    assert len(results) == 1
    assert results[0]["job_id"] == first.job_id
    assert results[0]["status"] == "ok"
    assert results[0]["job"]["job_id"] == first.job_id
    assert future.job_id not in seen
    assert second.job_id not in seen


def test_scheduler_run_once_records_success(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    job = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 3},
        next_run_at=current[0] - timedelta(minutes=1),
    )

    async def _executor(item):
        return {"message": f"sent:{item.job_id}"}

    scheduler = LearnerHeartbeatScheduler(service=service, executor=_executor)
    results = asyncio.run(scheduler.run_once(now=current[0]))

    assert len(results) == 1
    updated = results[0]["job"]
    assert updated["job_id"] == job.job_id
    assert datetime.fromisoformat(updated["last_run_at"]).astimezone(timezone.utc) == current[0]
    assert updated["failure_count"] == 0
    assert updated["status"] == "active"
    assert updated["last_result_json"]["success"] is True
    assert updated["last_result_json"]["message"] == f"sent:{job.job_id}"
    assert updated["last_result_json"]["delivery"]["state"] == "sent"
    assert updated["last_result_json"]["audit"]["job_id"] == job.job_id
    assert updated["next_run_at"] is not None

    due_after = service.list_due_jobs(now=current[0])
    assert due_after == []


def test_scheduler_run_once_records_failure_and_increments_failure_count(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    job = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] - timedelta(minutes=1),
    )

    async def _executor(_job):
        raise RuntimeError("channel unavailable")

    scheduler = LearnerHeartbeatScheduler(service=service, executor=_executor)
    results = asyncio.run(scheduler.run_once(now=current[0]))

    assert len(results) == 1
    updated = results[0]["job"]
    assert updated["job_id"] == job.job_id
    assert updated["failure_count"] == 1
    assert updated["status"] == "active"
    assert updated["last_result_json"]["success"] is False
    assert updated["last_result_json"]["error"] == "channel unavailable"
    assert updated["last_result_json"]["delivery"]["state"] == "failed"
    assert updated["last_result_json"]["audit"]["status"] == "error"
    assert updated["next_run_at"] is not None
    assert datetime.fromisoformat(updated["next_run_at"]) > current[0]


def test_scheduler_run_once_arbitrates_multi_bot_jobs_per_user(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    loser = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] - timedelta(minutes=2),
    )
    winner = service.upsert_job(
        user_id="student_1",
        bot_id="bot_beta",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 2},
        next_run_at=current[0] - timedelta(minutes=1),
    )

    executed: list[str] = []

    async def _executor(job):
        executed.append(job.job_id)
        return {"message": f"sent:{job.bot_id}"}

    def _hint_resolver(user_id: str, jobs):
        assert user_id == "student_1"
        assert {job.bot_id for job in jobs} == {"bot_alpha", "bot_beta"}
        return {"active_plan_bot_id": "bot_beta"}

    scheduler = LearnerHeartbeatScheduler(
        service=service,
        executor=_executor,
        hint_resolver=_hint_resolver,
        suppression_cooldown_minutes=20,
    )
    results = asyncio.run(scheduler.run_once(now=current[0]))

    assert executed == [winner.job_id]
    assert [item["status"] for item in results] == ["suppressed", "ok"]
    assert results[0]["job_id"] == loser.job_id
    assert results[1]["job_id"] == winner.job_id
    assert results[1]["arbitration"]["winner_job_id"] == winner.job_id
    assert results[1]["arbitration"]["winner_bot_id"] == "bot_beta"
    assert results[1]["arbitration"]["suppressed_bot_ids"] == ["bot_alpha"]

    loser_record = service._store.get_by_id(loser.job_id)
    winner_record = service._store.get_by_id(winner.job_id)
    assert loser_record is not None
    assert winner_record is not None
    assert loser_record.last_result_json["delivery"]["state"] == "suppressed"
    assert loser_record.last_result_json["audit"]["status"] == "suppressed"
    assert loser_record.last_result_json["arbitration"]["winner_job_id"] == winner.job_id
    assert loser_record.next_run_at is not None
    assert loser_record.next_run_at == current[0] + timedelta(minutes=20)
    assert winner_record.last_result_json["delivery"]["state"] == "sent"
    assert winner_record.last_result_json["arbitration"]["winner_bot_id"] == "bot_beta"
