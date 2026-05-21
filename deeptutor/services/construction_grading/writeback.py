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
    include_success_events: bool = False,
    training_intent_id: str | None = None,
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
                include_success_events=include_success_events,
                training_intent_id=training_intent_id,
            )
        return count

    payload_json = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=source_id,
    )
    if training_intent_id:
        payload_json["training_intent_id"] = str(training_intent_id or "").strip()
    if not payload_json["quality"]["writeback_eligible"]:
        if not include_success_events or not _is_success_learning_evidence(payload_json):
            return 0
        payload_json["quality"] = {
            **dict(payload_json.get("quality") or {}),
            "writeback_eligible": True,
            "writeback_reason": "success_improvement_signal",
        }
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
    _write_home_projection(
        learner_state_service=learner_state_service,
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    return 1


def _is_success_learning_evidence(payload_json: dict[str, Any]) -> bool:
    if payload_json.get("error_events") or payload_json.get("errors"):
        return False
    question_id = str(payload_json.get("question_id") or "").strip()
    signal = payload_json.get("next_training_signal") if isinstance(payload_json.get("next_training_signal"), dict) else {}
    concept = str((signal or {}).get("concept") or "").strip()
    try:
        score_awarded = float(payload_json.get("score_awarded") or 0)
        max_score = float(payload_json.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return bool(question_id and concept and max_score > 0 and score_awarded >= max_score)


def _write_home_projection(*, learner_state_service: Any, user_id: str, payload_json: dict[str, Any]) -> None:
    try:
        from deeptutor.services.learner_state.home_personalization import (
            build_home_personalization_projection_from_learning_signal,
            write_home_personalization_projection,
        )

        projection = build_home_personalization_projection_from_learning_signal(payload_json)
        write_home_personalization_projection(
            learner_state_service,
            user_id=user_id,
            projection=projection,
        )
    except Exception:
        return
