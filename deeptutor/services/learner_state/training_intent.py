"""Phase −1 / Batch C Task 6: training_intent v2.

``training_intent`` is the sole prescription authority for the learning
loop. v2 layers the 4-phase prescription spine on top of the v1 fields:

    [repair_root, expression_drill, transfer_case, verification_probe]

When ``evidence_refs`` is empty, v2 degrades to a single
``discovery_probe`` phase and ``status='degraded'`` so downstream UI
surfaces an honest "先来一次起步测评" rather than fabricating a repair
plan from nothing.

v1 callers (home_personalization, learning_report_read_model) keep
reading the legacy keys — ``concept_id``, ``concept_label``,
``error_code``, ``error_label``, ``training_mode``, ``training_intent_id``,
``attempt_refs``, ``question_count``, ``source``, ``reason`` — unchanged.
"""
from __future__ import annotations

import hashlib
from typing import Any


_MODES = {"mcq_discrimination", "case_repair", "rubric_recall", "mixed_review"}

_ABILITY_DIMENSIONS = frozenset({
    "question_reading",
    "code_application",
    "calculation",
    "expression",
    "transfer",
    "review_execution",
})

_FULL_PHASES = ("repair_root", "expression_drill", "transfer_case", "verification_probe")


def build_learning_training_intent(
    *,
    user_id: str,
    concept_id: str = "",
    concept_label: str = "",
    error_code: str = "",
    error_label: str = "",
    attempt_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    question_count: int = 3,
    training_mode: str = "mixed_review",
    source: str = "learning_report",
    reason: str = "",
    ability_dimension: str = "",
    behavior_state: str = "",
) -> dict[str, Any]:
    """Build the canonical training intent for a learner.

    See module docstring for the v1 ↔ v2 contract.
    """
    legacy_attempt_refs = _normalize_refs(attempt_refs)
    explicit_evidence = evidence_refs is not None
    evidence_refs_norm = (
        _normalize_refs(evidence_refs) if explicit_evidence else legacy_attempt_refs
    )

    full_mode = bool(evidence_refs_norm)

    mode = str(training_mode or "").strip()
    if mode not in _MODES:
        mode = "mixed_review"

    ability_dim_norm = str(ability_dimension or "").strip()
    if ability_dim_norm not in _ABILITY_DIMENSIONS:
        ability_dim_norm = ""

    behavior_state_norm = str(behavior_state or "").strip()

    raw_count = max(1, min(int(question_count or 3), 5))
    if full_mode:
        effective_count = max(raw_count, 4)
        prescription_steps = _full_prescription_steps(effective_count)
        success_criteria = {
            "requires_revalidation": True,
            "min_correct_probe_count": 1,
            "max_repeat_error_count": 0,
        }
        status = "active"
    else:
        effective_count = 1
        prescription_steps = [{"phase": "discovery_probe", "question_count": 1}]
        success_criteria = {
            "requires_revalidation": False,
            "min_correct_probe_count": 0,
            "max_repeat_error_count": 0,
        }
        status = "degraded"

    intent_id = _intent_id(
        user_id=user_id,
        concept_id=concept_id,
        concept_label=concept_label,
        error_code=error_code,
        error_label=error_label,
        training_mode=mode,
        ability_dimension=ability_dim_norm,
    )

    return {
        # ─── v1 fields ───────────────────────────────────────────────────
        "source": str(source or "learning_report").strip(),
        "training_intent_id": intent_id,
        "concept_id": str(concept_id or "").strip(),
        "concept_label": str(concept_label or "").strip(),
        "error_code": str(error_code or "").strip(),
        "error_label": str(error_label or "").strip(),
        "training_mode": mode,
        "attempt_refs": legacy_attempt_refs[:5],
        "question_count": effective_count,
        "reason": str(reason or "").strip(),
        # ─── v2 additive ─────────────────────────────────────────────────
        "intent_version": 2,
        "status": status,
        "ability_dimension": ability_dim_norm,
        "behavior_state": behavior_state_norm,
        "evidence_refs": evidence_refs_norm[:5],
        "prescription_steps": prescription_steps,
        "success_criteria": success_criteria,
    }


def _full_prescription_steps(total: int) -> list[dict[str, Any]]:
    """Distribute ``total`` across the 4 canonical phases.

    Floor of 1 per phase; extras above 4 go into repair_root (the phase
    that benefits most from depth). Total is capped at 5 to stay aligned
    with the v1 ``question_count`` ceiling.
    """
    capped = max(4, min(total, 5))
    counts = {phase: 1 for phase in _FULL_PHASES}
    extras = capped - 4
    counts["repair_root"] += extras
    return [{"phase": phase, "question_count": counts[phase]} for phase in _FULL_PHASES]


def _normalize_refs(refs: list[str] | None) -> list[str]:
    return [str(item or "").strip() for item in list(refs or []) if str(item or "").strip()]


def _intent_id(**values: str) -> str:
    raw = "|".join(str(values.get(key) or "") for key in sorted(values))
    return "lti_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["build_learning_training_intent"]
