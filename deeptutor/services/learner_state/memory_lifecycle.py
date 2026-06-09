from __future__ import annotations

from typing import Any

LIFECYCLE_STAGE_EVIDENCE_LEDGER = "evidence_ledger"
LIFECYCLE_STAGE_SHORT_TERM = "short_term_learning_memory"
LIFECYCLE_STAGE_STABLE_CLAIM = "stable_learner_claim"
LIFECYCLE_STAGE_CANONICAL_TRUTH = "canonical_learner_truth"

_STABLE_LEVELS = {"L1_repeated", "L2_confirmed", "L2_real_retest", "L3_mastery_signal"}


def lifecycle_stage_for_evidence_level(level: Any) -> str:
    text = str(level or "").strip()
    if text == "L0_observed":
        return LIFECYCLE_STAGE_SHORT_TERM
    if text in _STABLE_LEVELS:
        return LIFECYCLE_STAGE_STABLE_CLAIM
    return LIFECYCLE_STAGE_EVIDENCE_LEDGER
