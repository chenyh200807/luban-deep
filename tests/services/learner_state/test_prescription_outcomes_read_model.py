from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def test_active_outcome_preserves_navigation_target_without_replacing_intent_identity() -> None:
    event = _event(
        event_id="evt_first_run",
        phase="assigned",
        status="assigned",
        score_ratio=None,
        evidence_source="first_run_diagnostic",
    )
    event.payload_json.update(
        {
            "target_pack_id": "F16",
            "concept_label": "屋面卷材起鼓",
        }
    )

    outcome = build_prescription_outcomes_read_projection(events=[event])[0]

    assert outcome["training_intent_id"] == "intent_a"
    assert outcome["target_pack_id"] == "F16"
    assert outcome["concept_label"] == "屋面卷材起鼓"


def test_retest_item_cannot_verify_without_completion_terminal() -> None:
    item = _event(event_id="evt_item", status="verified", score_ratio=1.0)
    item.payload_json["retest_completion_id"] = "completion-1"
    item.payload_json["completion_terminal"] = False

    outcome = build_prescription_outcomes_read_projection(events=[item])[0]

    assert outcome["status"] != "verified"


def test_forged_retest_terminal_cannot_verify_prescription() -> None:
    forged = _event(
        event_id="evt_forged_terminal",
        status="verified",
        score_ratio=1.0,
        evidence_source="client_import",
    )
    forged.source_feature = "client_import"
    forged.source_id = "forged:terminal"
    forged.payload_json.update(
        {
            "retest_completion_id": "forged",
            "completion_terminal": True,
            "assessment_type": "luban_review_completion",
            "practice_mode": "review",
            "pack_id": "F16",
            "target_pack_id": "F16",
            "claim_promotion_allowed": True,
            "quality": {
                "authority": "client_claimed_complete",
                "writeback_eligible": True,
                "measurement_confidence": "high",
                "evidence_level": "L2_real_retest",
            },
        }
    )

    outcome = build_prescription_outcomes_read_projection(events=[forged])[0]

    assert outcome["status"] == "not_verified"
    assert outcome["next_required_action"] == "complete_verification_probe"


@pytest.mark.parametrize("evidence_source", ["assessment_testset", "client_import"])
def test_untrusted_probe_cannot_bypass_terminal_by_omitting_completion_id(
    evidence_source: str,
) -> None:
    forged = _event(
        event_id=f"evt_missing_terminal_{evidence_source}",
        status="verified",
        score_ratio=1.0,
        evidence_source=evidence_source,
    )

    outcome = build_prescription_outcomes_read_projection(events=[forged])[0]

    assert outcome["status"] == "not_verified"
    assert outcome["next_required_action"] == "complete_verification_probe"


def test_canonical_review_terminal_can_verify_prescription() -> None:
    item = _event(
        event_id="evt_canonical_item",
        status="verified",
        score_ratio=1.0,
        evidence_source="assessment_testset",
    )
    item.source_id = "canonical:q1"
    item.payload_json.update(
        {
            "retest_completion_id": "canonical",
            "request_hash": "canonical-request",
            "practice_mode": "review",
            "pack_id": "F16",
            "target_pack_id": "F16",
            "question_id": "q1",
            "is_correct": True,
            "score_awarded": 1.0,
            "max_score": 1.0,
        }
    )
    terminal = _event(
        event_id="evt_canonical_terminal",
        status="verified",
        score_ratio=1.0,
        evidence_source="assessment_testset",
    )
    terminal.source_feature = "assessment_testset"
    terminal.source_id = "canonical:terminal"
    terminal.payload_json.update(
        {
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "retest_completion_id": "canonical",
            "completion_terminal": True,
            "request_hash": "canonical-request",
            "assessment_type": "luban_review_completion",
            "practice_mode": "review",
            "pack_id": "F16",
            "target_pack_id": "F16",
            "claim_promotion_allowed": True,
            "score_awarded": 1.0,
            "max_score": 1.0,
            "item_event_refs": ["evt_canonical_item"],
            "quality": {
                "authority": "signed_variant_server_rescore",
                "writeback_eligible": True,
                "measurement_confidence": "high",
                "evidence_level": "L2_real_retest",
            },
        }
    )

    outcome = build_prescription_outcomes_read_projection(
        events=[item, terminal]
    )[0]

    assert outcome["status"] == "verified"
    assert outcome["next_required_action"] == "maintain"
