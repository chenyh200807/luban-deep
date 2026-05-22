from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.prescription_outcome_read_model import (
    build_prescription_outcomes_read_projection,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def _event(
    *,
    event_id: str,
    training_intent_id: str = "intent_a",
    phase: str = "verification_probe",
    status: str = "verified",
    score_ratio: float | None = 1.0,
    evidence_source: str = "construction_grading",
    days_ago: int = 0,
) -> LearnerStateEvent:
    payload = {
        "event_type": "learning_evidence",
        "evidence_source": evidence_source,
        "training_intent_id": training_intent_id,
        "prescription_phase": phase,
        "prescription_result": {"status": status},
    }
    if score_ratio is not None:
        payload["score_ratio"] = score_ratio
        payload["prescription_result"]["score_ratio"] = score_ratio
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature=evidence_source,
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json=payload,
    )


def test_verification_probe_with_full_score_marks_verified() -> None:
    outcomes = build_prescription_outcomes_read_projection(
        events=[_event(event_id="evt_verified", score_ratio=1.0)]
    )

    assert outcomes[0]["status"] == "verified"
    assert outcomes[0]["training_intent_id"] == "intent_a"
    assert outcomes[0]["evidence_refs"] == ["evt_verified"]
    assert outcomes[0]["next_required_action"] == "maintain"


def test_failed_verification_probe_marks_not_verified_with_retry_action() -> None:
    outcomes = build_prescription_outcomes_read_projection(
        events=[_event(event_id="evt_failed", status="not_verified", score_ratio=0.0)]
    )

    assert outcomes[0]["status"] == "not_verified"
    assert outcomes[0]["next_required_action"] == "retry_verification_probe"


def test_missing_training_intent_id_is_unlinked_not_verified() -> None:
    outcomes = build_prescription_outcomes_read_projection(
        events=[
            _event(
                event_id="evt_unlinked",
                training_intent_id="",
                status="verified",
                score_ratio=1.0,
            )
        ]
    )

    assert outcomes[0]["status"] == "unlinked_training_evidence"
    assert outcomes[0]["training_intent_id"] == ""
    assert outcomes[0]["next_required_action"] == "link_to_training_intent"


def test_conversation_only_probe_does_not_verify_prescription() -> None:
    outcomes = build_prescription_outcomes_read_projection(
        events=[
            _event(
                event_id="evt_chat",
                evidence_source="conversation_synthesis",
                status="verified",
                score_ratio=1.0,
            )
        ]
    )

    assert outcomes[0]["status"] == "not_verified"
    assert outcomes[0]["next_required_action"] == "complete_verification_probe"
