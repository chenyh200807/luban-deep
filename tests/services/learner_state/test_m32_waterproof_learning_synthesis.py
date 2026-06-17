"""M32 Task 4: repeated point-level grading evidence must become an EXPLAINABLE
LearnerClaim — one that answers "what kind of mistake (error_code) + which answer span
(evidence_span) backs it". Uses the CANONICAL GradingErrorEvent shape (error_code /
severity / concept_tag / evidence / diagnosis — see construction_grading/schema.py), so
the test reflects the real pipeline rather than a hand-rolled payload. A single observed
miss must NOT be promoted to mastery."""
from __future__ import annotations

from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth

CONCEPT = "waterproof_term"


def _event(event_id: str, *, error: dict, observed_at: str = "2026-06-07T10:00:00+08:00") -> LearnerStateEvent:
    payload = {
        "event_type": "learning_evidence",
        "turn_id": f"turn_{event_id}",
        "question_id": "waterproof_case_001",
        "question_type": "case",
        "score_awarded": 0.0,
        "max_score": 1.0,
        "grading_mode": "curated_rubric",
        "error_events": [error],
        "next_training_signal": {"concept": CONCEPT, "focus": "防水 exact_required 术语", "mode": "case_repair"},
        "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
    }
    return LearnerStateEvent(
        event_id=event_id,
        user_id="qa_m32_waterproof",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=observed_at,
        payload_json=payload,
    )


# Canonical GradingErrorEvent.to_dict() shape — the answer span lives in `evidence`.
CANONICAL_ERROR = {
    "error_code": "near_synonym_not_accepted",
    "severity": 0.8,
    "concept_tag": CONCEPT,
    "evidence": "普通防水砂浆处理",
    "diagnosis": "",
}


def _claim(projection: dict) -> dict:
    claims = projection["observed_candidates"]
    assert claims, "expected an observed claim from the waterproof miss"
    return claims[0]


def test_claim_is_explainable_from_canonical_grader_error_event() -> None:
    claim = _claim(synthesize_learning_truth([_event("evt1", error=CANONICAL_ERROR)]))
    assert claim["concept_id"] == CONCEPT
    # error_code carries the mistake type on the canonical pipeline (no redundant 2nd key).
    assert claim["error_code"] == "near_synonym_not_accepted"
    assert "mistake_type" not in claim
    # the answer span is surfaced from the canonical `evidence` field.
    assert claim["evidence_span"] == "普通防水砂浆处理"
    # with no separate prose diagnosis, the evidence span answers "证据来自哪段作答".
    assert claim["diagnosis"] == "普通防水砂浆处理"


def test_legacy_error_without_span_keeps_claim_byte_identical() -> None:
    """A legacy error with no evidence/diagnosis must NOT add empty diagnostic keys —
    append-only parity with the evidence side."""
    legacy = {"error_code": "omitted", "concept_tag": CONCEPT}
    claim = _claim(synthesize_learning_truth([_event("evt_legacy", error=legacy)]))
    assert "evidence_span" not in claim
    assert "diagnosis" not in claim


def test_single_observed_miss_is_not_promoted_to_mastery() -> None:
    projection = synthesize_learning_truth([_event("evt1", error=CANONICAL_ERROR)])
    claim = _claim(projection)
    assert claim["evidence_level"] == "L0_observed"
    assert projection["weak_points"] == []  # one miss != repeated weakness


def test_chain_grading_result_to_explainable_claim() -> None:
    """End-to-end loop hop: grader result -> build_learning_evidence_payload (Task 3)
    -> synthesize_learning_truth (Task 4) -> explainable claim, with the answer span
    surviving every layer on the canonical GradingErrorEvent shape."""
    from deeptutor.services.construction_grading.learning_evidence import (
        build_learning_evidence_payload,
    )

    grading_result = {
        "type": "case",
        "question_id": "waterproof_case_001",
        "user_answer": "普通防水砂浆处理",
        "score_awarded": 0,
        "max_score": 1,
        "error_events": [CANONICAL_ERROR],
        "next_training_signal": {"concept": CONCEPT, "focus": "防水 exact_required 术语", "mode": "case_repair"},
    }
    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1", session_id="s1")
    event = LearnerStateEvent(
        event_id="chain_evt1",
        user_id="qa_m32_waterproof",
        source_feature="construction_grading",
        source_id="turn:chain_evt1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="chain_evt1",
        created_at="2026-06-07T10:00:00+08:00",
        payload_json=payload,
    )
    claim = synthesize_learning_truth([event])["observed_candidates"][0]
    assert claim["concept_id"] == CONCEPT
    assert claim["error_code"] == "near_synonym_not_accepted"
    assert claim["evidence_span"] == "普通防水砂浆处理"
    assert claim["diagnosis"] == "普通防水砂浆处理"
