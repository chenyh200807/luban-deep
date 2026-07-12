"""M32 Task 6: a REAL retest pass updates the learner picture (recorded as an improvement
signal); a SIMULATED / preview retest must never be treated as real — no improved claim
without real retest evidence (simulated_retest_as_real == 0)."""
from __future__ import annotations

from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent

CONCEPT = "waterproof_term"
ERROR = "near_synonym_not_accepted"


def _event(event_id: str, *, payload: dict, observed_at: str) -> LearnerStateEvent:
    base = {"event_type": "learning_evidence", "turn_id": f"turn_{event_id}", "question_id": "waterproof_case_001",
            "question_type": "case"}
    base.update(payload)
    return LearnerStateEvent(
        event_id=event_id, user_id="qa_m32_waterproof", source_feature="construction_grading",
        source_id=f"turn:{event_id}", source_bot_id="construction-exam", memory_kind="learning_evidence",
        dedupe_key=event_id, created_at=observed_at, payload_json=base,
    )


def _miss(event_id: str, *, observed_at: str = "2026-06-07T10:00:00+08:00") -> LearnerStateEvent:
    return _event(event_id, observed_at=observed_at, payload={
        "score_awarded": 0.0, "max_score": 1.0,
        "error_events": [{"error_code": ERROR, "severity": 0.8, "concept_tag": CONCEPT,
                          "evidence": "普通防水砂浆处理", "diagnosis": ""}],
        "next_training_signal": {"concept": CONCEPT, "error_code": ERROR, "mode": "case_repair"},
    })


def _retest_pass(event_id: str, *, simulated: bool, observed_at: str = "2026-06-07T12:00:00+08:00") -> LearnerStateEvent:
    payload = {
        "score_awarded": 1.0, "max_score": 1.0, "error_events": [],
        "next_training_signal": {"concept": CONCEPT, "error_code": ERROR, "mode": "case_repair"},
    }
    if simulated:
        payload["qa_simulated"] = True  # project's explicit simulation marker
    return _event(event_id, observed_at=observed_at, payload=payload)


def test_real_retest_pass_recorded_as_improvement() -> None:
    proj = synthesize_learning_truth([
        _miss("m1"),
        _miss("m2", observed_at="2026-06-07T11:00:00+08:00"),
        _retest_pass("r1", simulated=False),
    ])
    signals = proj["improvement_signals"]
    assert any(s["concept_id"] == CONCEPT and s["error_code"] == ERROR for s in signals), signals


def test_simulated_retest_is_not_counted_as_real_improvement() -> None:
    proj = synthesize_learning_truth([_miss("m1"), _retest_pass("r1", simulated=True)])
    signals = proj["improvement_signals"]
    assert not any(s["concept_id"] == CONCEPT for s in signals), signals
    # the weakness claim is NOT cleared by a simulated retest
    claim = proj["observed_candidates"][0]
    assert claim["concept_id"] == CONCEPT
    assert claim["claim_status"] == "observed"  # not improved/stale


def test_preview_only_retest_does_not_promote() -> None:
    """A preview/candidate grade (claim_promotion_allowed=False, e.g. open-world) is not a
    confirmed real retest and must not auto-clear the weakness."""
    preview_pass = _event("r1", observed_at="2026-06-07T12:00:00+08:00", payload={
        "score_awarded": 1.0, "max_score": 1.0, "error_events": [],
        "claim_promotion_allowed": False, "preview_only": True,
        "next_training_signal": {"concept": CONCEPT, "error_code": ERROR, "mode": "case_repair"},
    })
    proj = synthesize_learning_truth([_miss("m1"), preview_pass])
    assert not any(s["concept_id"] == CONCEPT for s in proj["improvement_signals"])
