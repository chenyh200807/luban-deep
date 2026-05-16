from __future__ import annotations

import hashlib
import json
from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult


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

    result_payload = _grading_result_payload(grading_result)
    errors = list(result_payload.get("error_events") or [])
    if not errors:
        return 0
    question_type = str(result_payload.get("type") or result_payload.get("question_type") or "").strip()
    kind = "case_error_event" if question_type == "case" else "mcq_error_event"
    score_awarded = result_payload.get("score_awarded")
    max_score = result_payload.get("max_score")
    score_ratio = None
    try:
        max_score_float = float(max_score or 0)
        if max_score_float > 0:
            score_ratio = float(score_awarded or 0) / max_score_float
    except (TypeError, ValueError):
        score_ratio = None
    payload_json = {
        "event_type": "construction_grading_error",
        "source": "construction_grading",
        "question_type": question_type or kind.replace("_error_event", ""),
        "question_id": str(result_payload.get("question_id") or "").strip(),
        "user_answer": str(result_payload.get("user_answer") or "").strip(),
        "score_awarded": score_awarded,
        "max_score": max_score,
        "score_ratio": score_ratio,
        "grading_mode": result_payload.get("grading_mode"),
        "error_events": errors,
        "errors": errors,
        "next_training_signal": dict(result_payload.get("next_training_signal") or {}),
    }
    dedupe_key = _grading_error_dedupe_key(
        user_id=normalized_user_id,
        memory_kind=kind,
        payload_json=payload_json,
    )
    learner_state_service.append_memory_event(
        normalized_user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind=kind,
        payload_json=payload_json,
        dedupe_key=dedupe_key,
    )
    return 1


def _grading_result_payload(
    grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(grading_result, dict):
        payload = dict(grading_result)
    else:
        payload = grading_result.to_dict()
        if isinstance(grading_result, CaseGradingResult):
            payload["type"] = "case"
        elif isinstance(grading_result, MCQGradingResult):
            payload["type"] = "mcq"
    payload["error_events"] = [_error_event_payload(error) for error in payload.get("error_events") or []]
    return payload


def _error_event_payload(error: Any) -> dict[str, Any]:
    if hasattr(error, "to_dict"):
        return dict(error.to_dict())
    if isinstance(error, dict):
        return dict(error)
    return {"diagnosis": str(error or "").strip()}


def _grading_error_dedupe_key(
    *,
    user_id: str,
    memory_kind: str,
    payload_json: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "user_id": user_id,
            "memory_kind": memory_kind,
            "question_type": payload_json.get("question_type"),
            "question_id": payload_json.get("question_id"),
            "user_answer": payload_json.get("user_answer"),
            "error_events": payload_json.get("error_events") or [],
            "score_awarded": payload_json.get("score_awarded"),
            "max_score": payload_json.get("max_score"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
