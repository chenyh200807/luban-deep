from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult


def write_grading_error_events(
    *,
    learner_state_service: Any,
    user_id: str,
    grading_result: CaseGradingResult | MCQGradingResult,
    source_id: str,
    source_bot_id: str | None = None,
) -> int:
    """Write grading error events through the existing LearnerStateService authority."""

    errors = list(getattr(grading_result, "error_events", []) or [])
    if not errors:
        return 0
    kind = "case_error_event" if isinstance(grading_result, CaseGradingResult) else "mcq_error_event"
    learner_state_service.append_memory_event(
        user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind=kind,
        payload_json={
            "question_id": getattr(grading_result, "question_id", ""),
            "score_awarded": getattr(grading_result, "score_awarded", None),
            "max_score": getattr(grading_result, "max_score", None),
            "grading_mode": getattr(grading_result, "grading_mode", None),
            "errors": [error.to_dict() for error in errors],
            "next_training_signal": dict(getattr(grading_result, "next_training_signal", {}) or {}),
        },
    )
    return 1
