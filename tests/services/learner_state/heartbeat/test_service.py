from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.heartbeat import LearnerHeartbeatService


class _PathServiceStub:
    def __init__(self, root):
        self.project_root = root


def _service(tmp_path, current):
    return LearnerHeartbeatService(
        path_service=_PathServiceStub(tmp_path),
        clock=lambda: current[0],
    )


def test_upsert_pause_resume_and_mark_run_round_trip(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    first = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "quiet_hours": ["22:00", "08:00"]},
        next_run_at=current[0] + timedelta(minutes=15),
    )
    current[0] = current[0] + timedelta(minutes=5)
    second = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": False, "quiet_hours": ["21:00", "09:00"]},
        next_run_at=current[0] + timedelta(hours=1),
    )

    assert first.job_id == second.job_id
    assert first.created_at == second.created_at
    assert second.policy_json["enabled"] is False
    assert second.next_run_at == current[0] + timedelta(hours=1)

    paused = service.pause_job(first.job_id)
    assert paused is not None
    assert paused.status == "paused"

    current[0] = current[0] + timedelta(minutes=1)
    resumed = service.resume_job(first.job_id)
    assert resumed is not None
    assert resumed.status == "active"

    current[0] = current[0] + timedelta(minutes=2)
    marked = service.mark_run(
        job_id=first.job_id,
        next_run_at=current[0] + timedelta(days=1),
        last_result_json={"status": "sent", "reason": "due"},
        failure_count=0,
    )

    assert marked is not None
    assert marked.last_run_at == current[0]
    assert marked.last_result_json == {"status": "sent", "reason": "due"}
    assert marked.next_run_at == current[0] + timedelta(days=1)
    assert marked.failure_count == 0
    assert marked.status == "active"

    store_path = tmp_path / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json"
    payload = json.loads(store_path.read_text(encoding="utf-8"))
    assert payload["jobs"][0]["job_id"] == first.job_id
    assert payload["jobs"][0]["user_id"] == "student_1"
    assert payload["jobs"][0]["channel"] == "web"


def test_list_due_jobs_filters_paused_and_orders_by_next_run(tmp_path) -> None:
    current = [datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)]
    service = _service(tmp_path, current)

    first = service.upsert_job(
        user_id="student_1",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True},
        next_run_at=current[0] - timedelta(minutes=10),
    )
    second = service.upsert_job(
        user_id="student_2",
        bot_id="bot_alpha",
        channel="wx",
        policy_json={"enabled": True},
        next_run_at=current[0] - timedelta(minutes=5),
    )
    third = service.upsert_job(
        user_id="student_3",
        bot_id="bot_beta",
        channel="web",
        policy_json={"enabled": True},
        next_run_at=current[0] + timedelta(minutes=20),
    )

    service.pause_job(second.job_id)

    due = service.list_due_jobs()
    assert [job.job_id for job in due] == [first.job_id]
    assert due[0].channel == "web"
    assert third.job_id not in {job.job_id for job in due}

