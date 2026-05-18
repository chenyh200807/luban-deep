from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)


def write_grading_error_events(
    *,
    learner_state_service: Any,
    user_id: str,
    grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any],
    source_id: str,
    source_bot_id: str | None = None,
) -> int:
    """Write grading error events through the existing LearnerStateService authority."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return 0
    if isinstance(grading_result, dict) and grading_result.get("type") == "batch":
        count = 0
        for index, item in enumerate(list(grading_result.get("items") or []), 1):
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("question_id") or f"item-{index}").strip()
            count += write_grading_error_events(
                learner_state_service=learner_state_service,
                user_id=normalized_user_id,
                grading_result=item,
                source_id=f"{source_id}:{question_id}",
                source_bot_id=source_bot_id,
            )
        return count

    payload_json = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=source_id,
    )
    if not payload_json["quality"]["writeback_eligible"]:
        return 0
    dedupe_key = build_learning_evidence_dedupe_key(
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    learner_state_service.append_memory_event(
        normalized_user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind="learning_evidence",
        payload_json=payload_json,
        dedupe_key=dedupe_key,
    )
    return 1
