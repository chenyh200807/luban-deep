from __future__ import annotations

import hashlib
from typing import Any


_MODES = {"mcq_discrimination", "case_repair", "rubric_recall", "mixed_review"}


def build_learning_training_intent(
    *,
    user_id: str,
    concept_id: str = "",
    concept_label: str = "",
    error_code: str = "",
    error_label: str = "",
    attempt_refs: list[str] | None = None,
    question_count: int = 3,
    training_mode: str = "mixed_review",
    source: str = "learning_report",
    reason: str = "",
) -> dict[str, Any]:
    refs = [str(item or "").strip() for item in list(attempt_refs or []) if str(item or "").strip()]
    mode = str(training_mode or "").strip()
    if mode not in _MODES:
        mode = "mixed_review"
    count = max(1, min(int(question_count or 3), 5))
    payload = {
        "source": str(source or "learning_report").strip(),
        "training_intent_id": _intent_id(
            user_id=user_id,
            concept_id=concept_id,
            concept_label=concept_label,
            error_code=error_code,
            error_label=error_label,
            training_mode=mode,
        ),
        "concept_id": str(concept_id or "").strip(),
        "concept_label": str(concept_label or "").strip(),
        "error_code": str(error_code or "").strip(),
        "error_label": str(error_label or "").strip(),
        "training_mode": mode,
        "attempt_refs": refs[:5],
        "question_count": count,
        "reason": str(reason or "").strip(),
    }
    return payload


def _intent_id(**values: str) -> str:
    raw = "|".join(str(values.get(key) or "") for key in sorted(values))
    return "lti_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["build_learning_training_intent"]
