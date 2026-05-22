from __future__ import annotations

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
)


def _state_item(**overrides):
    item = {
        "node_id": "1A412010",
        "label": "防火门构造",
        "state": "weak",
        "ability_dimension": "code_application",
        "error_code": "E02",
        "evidence_refs": ["evt_miss_1", "evt_miss_2"],
        "last_observed_at": "2026-05-18T08:00:00+08:00",
        "forgetting_risk": 0.8,
    }
    item.update(overrides)
    return item


def test_needs_revalidation_creates_one_probe_intent_per_day() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(), _state_item(node_id="1A413020", label="地基处理")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    active = [item for item in queue["items"] if item["status"] == "active"]
    queued = [item for item in queue["items"] if item["status"] == "queued"]

    assert len(queue["items"]) == 1
    assert len(active) == 1
    assert queued == []
    assert active[0]["kind"] == "revalidation_probe"
    assert active[0]["intent"]["intent_version"] == 2
    assert active[0]["intent"]["prescription_steps"][-1]["phase"] == "verification_probe"
    assert active[0]["evidence_refs"] == ["evt_miss_1", "evt_miss_2"]
    assert queue["source_status"]["daily_capacity"] == 1
    assert queue["source_status"]["due_count"] == 2
    assert queue["source_status"]["suppressed_due_count"] == 1


def test_recent_observation_not_due_yet_is_not_enqueued() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(last_observed_at="2026-05-21T08:00:00+08:00")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"] == []
    assert "not_due" in queue["source_status"]["blocked_reasons"]


def test_declined_probe_is_pushed_back_one_day() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        declined_probe_ids=["rvp_student_demo_1A412010_code_application_E02"],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"][0]["status"] == "deferred"
    assert queue["items"][0]["next_available_at"] == "2026-05-23T09:00:00+08:00"


def test_verified_outcome_removes_probe_from_queue() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        prescription_outcomes=[
            {
                "training_intent_id": "rvp_student_demo_1A412010_code_application_E02",
                "status": "verified",
                "evidence_refs": ["evt_verified"],
            }
        ],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"] == []
    assert "already_verified" in queue["source_status"]["blocked_reasons"]


def test_unverified_weak_observation_uses_three_day_cadence() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(state="weak", last_observed_at="2026-05-19T08:00:00+08:00")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"][0]["status"] == "active"
