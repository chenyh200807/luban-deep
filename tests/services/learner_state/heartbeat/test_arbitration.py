from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.heartbeat import (
    LearnerHeartbeatArbitrationHints,
    LearnerHeartbeatArbitrator,
)
from deeptutor.services.learner_state.heartbeat.store import LearnerHeartbeatJob


def _job(job_id: str, user_id: str, bot_id: str, *, minutes_ago: int = 0) -> LearnerHeartbeatJob:
    now = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
    created_at = now - timedelta(minutes=minutes_ago + 5)
    updated_at = now - timedelta(minutes=minutes_ago + 1)
    return LearnerHeartbeatJob(
        job_id=job_id,
        user_id=user_id,
        bot_id=bot_id,
        channel="heartbeat",
        policy_json={"enabled": True, "consent": True},
        next_run_at=now - timedelta(minutes=minutes_ago),
        last_run_at=None,
        last_result_json=None,
        failure_count=0,
        status="active",
        created_at=created_at,
        updated_at=updated_at,
    )


def test_arbitrator_single_job_wins_directly() -> None:
    arbitrator = LearnerHeartbeatArbitrator()
    job = _job("job_1", "student_1", "bot_a")

    result = arbitrator.arbitrate("student_1", [job], now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.winner_job_id == "job_1"
    assert result.winner_bot_id == "bot_a"
    assert result.suppressed_bot_ids == ()
    assert result.reasons
    assert result.decisions[0].reasons


def test_arbitrator_uses_hints_to_choose_winner() -> None:
    arbitrator = LearnerHeartbeatArbitrator()
    jobs = [
        _job("job_1", "student_1", "bot_a"),
        _job("job_2", "student_1", "bot_b"),
    ]
    hints = LearnerHeartbeatArbitrationHints(
        active_plan_bot_id="bot_b",
        learner_goal_urgency_by_bot_id={"bot_a": 8, "bot_b": 2},
        recent_interaction_source_by_bot_id={"bot_b": "manual"},
        overlay_heartbeat_override_by_bot_id={"bot_b": {"priority_bonus": 8}},
    )

    result = arbitrator.arbitrate("student_1", jobs, hints=hints, now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.winner_bot_id == "bot_b"
    assert result.winner_job_id == "job_2"
    assert result.suppressed_bot_ids == ("bot_a",)
    assert "active_plan_match:+50" in result.decisions[0].reasons or "active_plan_match:+50" in result.decisions[1].reasons
    assert "overlay_priority=8=>+8" in result.reasons or any("overlay_priority=8=>+8" in item for item in result.decisions[0].reasons)
    assert result.suppressed_reasons["bot_a"]


def test_arbitrator_suppresses_recently_contacted_job() -> None:
    arbitrator = LearnerHeartbeatArbitrator()
    jobs = [
        _job("job_1", "student_1", "bot_a"),
        _job("job_2", "student_1", "bot_b"),
    ]
    future = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc) + timedelta(hours=2)
    hints = LearnerHeartbeatArbitrationHints(
        recently_contacted_until_by_bot_id={"bot_a": future},
        learner_goal_urgency_by_bot_id={"bot_b": 1},
    )

    result = arbitrator.arbitrate("student_1", jobs, hints=hints, now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.winner_bot_id == "bot_b"
    assert result.suppressed_bot_ids == ("bot_a",)
    assert "recently_contacted_cooldown_until" in result.suppressed_reasons["bot_a"][0]


def test_arbitrator_returns_explainable_reasons() -> None:
    arbitrator = LearnerHeartbeatArbitrator()
    jobs = [
        _job("job_1", "student_1", "bot_a"),
        _job("job_2", "student_1", "bot_b"),
    ]
    hints = LearnerHeartbeatArbitrationHints(
        active_plan_bot_id="bot_a",
        recent_interaction_source_by_bot_id={"bot_a": "learner_reply"},
    )

    result = arbitrator.arbitrate("student_1", jobs, hints=hints, now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.reasons
    assert result.decisions
    assert result.decisions[0].reasons
    assert result.decisions[0].score_breakdown
    assert result.suppressed_reasons
