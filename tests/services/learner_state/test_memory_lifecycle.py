from __future__ import annotations

from deeptutor.services.learner_state.memory_lifecycle import (
    LIFECYCLE_STAGE_CANONICAL_TRUTH,
    LIFECYCLE_STAGE_EVIDENCE_LEDGER,
    LIFECYCLE_STAGE_SHORT_TERM,
    LIFECYCLE_STAGE_STABLE_CLAIM,
    lifecycle_stage_for_evidence_level,
)


def test_lifecycle_stage_for_evidence_levels() -> None:
    assert lifecycle_stage_for_evidence_level("L0_observed") == LIFECYCLE_STAGE_SHORT_TERM
    assert lifecycle_stage_for_evidence_level("L1_repeated") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L2_confirmed") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L2_real_retest") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L3_mastery_signal") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("") == LIFECYCLE_STAGE_EVIDENCE_LEDGER


def test_canonical_truth_stage_is_reserved_for_write_gate() -> None:
    assert LIFECYCLE_STAGE_CANONICAL_TRUTH == "canonical_learner_truth"
