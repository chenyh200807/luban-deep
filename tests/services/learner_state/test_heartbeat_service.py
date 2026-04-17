from __future__ import annotations

import json

from deeptutor.services.learner_state.service import LearnerStateService


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

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"


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


class _DisabledCoreStoreStub:
    is_configured = False


def _make_service(tmp_path):
    return LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_FakeMemberService(),
        core_store=_DisabledCoreStoreStub(),
    )


def test_learner_state_seed_creates_default_heartbeat_job(tmp_path) -> None:
    service = _make_service(tmp_path)

    service.build_context("student_demo", language="zh")

    jobs_path = tmp_path / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json"
    assert jobs_path.exists()

    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["bot_id"] == "construction-exam-coach"
    assert jobs[0]["channel"] == "heartbeat"
    assert jobs[0]["status"] == "active"
    assert jobs[0]["policy_json"]["consent"] is False


def test_learner_state_ensure_default_job_get_due_jobs_and_record_run_result(tmp_path) -> None:
    service = _make_service(tmp_path)

    job = service.ensure_default_job(
        "student_demo",
        policy_json={"consent": True, "interval_hours": 1},
        next_run_at="2026-04-14T10:00:00+08:00",
    )

    due_jobs = service.get_due_jobs(
        user_id="student_demo",
        now="2026-04-14T12:00:00+08:00",
    )
    heartbeat_due_jobs = service._heartbeat_job_service.get_due_jobs(
        user_id="student_demo",
        now="2026-04-14T12:00:00+08:00",
    )
    assert [item.job_id for item in due_jobs] == [job.job_id]
    assert [item.job_id for item in due_jobs] == [item.job_id for item in heartbeat_due_jobs]

    failed = service.record_run_result(
        user_id="student_demo",
        job_id=job.job_id,
        success=False,
        result_json={"error": "timeout"},
        finished_at="2026-04-14T12:05:00+08:00",
    )
    assert failed.failure_count == 1
    assert failed.last_result_json["success"] is False
    assert failed.last_result_json["error"] == "timeout"
    assert failed.last_result_json["delivery"]["state"] == "failed"
    assert failed.last_result_json["audit"]["status"] == "error"

    due_after_failure = service.get_due_jobs(
        user_id="student_demo",
        now="2026-04-14T12:06:00+08:00",
    )
    assert due_after_failure == []

    success = service.record_run_result(
        user_id="student_demo",
        job_id=job.job_id,
        success=True,
        result_json={"sent": True},
        finished_at="2026-04-14T13:05:00+08:00",
    )
    assert success.failure_count == 0
    assert success.last_result_json["success"] is True
    assert success.last_result_json["sent"] is True
    assert success.last_result_json["delivery"]["state"] == "sent"
    assert success.last_result_json["audit"]["status"] == "ok"


def test_learner_state_record_run_result_persists_heartbeat_arbitration_event(tmp_path) -> None:
    service = _make_service(tmp_path)

    job = service.ensure_default_job(
        "student_demo",
        policy_json={"consent": True, "interval_hours": 1},
        next_run_at="2026-04-14T10:00:00+08:00",
    )

    updated = service.record_run_result(
        user_id="student_demo",
        job_id=job.job_id,
        success=True,
        result_json={
            "sent": True,
            "arbitration": {
                "winner_job_id": job.job_id,
                "winner_bot_id": "construction-exam-coach",
                "suppressed_bot_ids": ["review-bot"],
                "reasons": ["active_plan_match:+50"],
                "decisions": [
                    {
                        "job_id": job.job_id,
                        "bot_id": "construction-exam-coach",
                        "score": 50,
                    }
                ],
            },
        },
        finished_at="2026-04-14T13:05:00+08:00",
    )

    assert updated.last_result_json["arbitration"]["winner_job_id"] == job.job_id
    events = service.list_memory_events("student_demo", limit=10)
    arbitration_events = [event for event in events if event.memory_kind == "heartbeat_arbitration"]
    assert arbitration_events
    assert arbitration_events[-1].payload_json["winner_job_id"] == job.job_id
    assert arbitration_events[-1].payload_json["suppressed_bot_ids"] == ["review-bot"]


def test_learner_state_lists_heartbeat_history_and_arbitration_history(tmp_path) -> None:
    service = _make_service(tmp_path)

    job = service.ensure_default_job(
        "student_demo",
        policy_json={"consent": True, "interval_hours": 1},
        next_run_at="2026-04-14T10:00:00+08:00",
    )
    service.record_run_result(
        user_id="student_demo",
        job_id=job.job_id,
        success=True,
        result_json={
            "sent": True,
            "arbitration": {
                "winner_job_id": job.job_id,
                "winner_bot_id": "construction-exam-coach",
                "suppressed_bot_ids": ["review-bot"],
                "reasons": ["active_plan_match:+50"],
                "decisions": [],
            },
        },
        finished_at="2026-04-14T13:05:00+08:00",
    )

    history = service.list_heartbeat_history("student_demo", limit=10)
    arbitration = service.list_heartbeat_arbitration_history("student_demo", limit=10)

    assert any(item["memory_kind"] == "heartbeat_delivery" for item in history)
    assert any(item["memory_kind"] == "heartbeat_arbitration" for item in history)
    assert arbitration
    assert arbitration[-1]["payload_json"]["winner_job_id"] == job.job_id
