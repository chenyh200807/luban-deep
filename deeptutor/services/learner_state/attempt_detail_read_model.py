from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref
from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label


def build_attempt_detail_read_model(
    *,
    user_id: str,
    learner_state_service: Any,
    attempt_ref: str,
) -> dict[str, Any]:
    normalized_user = str(user_id or "").strip()
    ref = verify_attempt_ref(attempt_ref, user_id=normalized_user)
    if ref is None:
        return {"ok": False, "error": "invalid_attempt_ref"}

    reader = getattr(learner_state_service, "read_learning_evidence_event", None)
    if not callable(reader):
        return {"ok": False, "error": "reader_unavailable"}
    event = reader(normalized_user, ref["event_id"])
    if event is None:
        return {"ok": False, "error": "attempt_not_found"}

    payload = _safe_dict(getattr(event, "payload_json", {}))
    question_id = str(payload.get("question_id") or ref.get("question_id") or "").strip()
    errors = [item for item in _safe_list(payload.get("error_events") or payload.get("errors")) if isinstance(item, dict)]
    concept = _concept_label(_event_concept(payload, errors))
    error = _error_label(errors)
    is_correct = _is_correct(payload)
    explanation = _explanation_payload(payload.get("explanation") or payload.get("analysis") or payload.get("feedback"))

    return {
        "ok": True,
        "attempt_ref": str(attempt_ref or ""),
        "question": {
            "question_id": question_id,
            "stem": _question_stem(payload),
            "options": _option_items(payload.get("options")),
            "type": str(payload.get("question_type") or payload.get("type") or "").strip(),
        },
        "answer": {
            "user_answer": _answer_text(payload.get("user_answer")),
            "correct_answer": _answer_text(payload.get("correct_answer")),
            "score_awarded": payload.get("score_awarded"),
            "max_score": payload.get("max_score"),
            "result_label": "答对" if is_correct else "答错",
        },
        "explanation": explanation,
        "diagnosis": {
            "concept_label": concept,
            "error_label": error,
            "detail": _diagnosis(errors),
        },
        "next_training": _safe_dict(payload.get("next_training_signal")),
        "quality": _safe_dict(payload.get("quality")),
        "evidence_sources": [
            {"type": "attempt", "label": "当时作答"},
            {"type": "grading", "label": "本次批改"},
        ],
    }


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _question_stem(payload: dict[str, Any]) -> str:
    return str(
        payload.get("question_stem")
        or payload.get("stem")
        or payload.get("question_text")
        or payload.get("question")
        or ""
    ).strip()


def _option_items(options: Any) -> list[dict[str, str]]:
    if isinstance(options, dict):
        return [{"key": str(key), "text": str(value)} for key, value in sorted(options.items())]
    if isinstance(options, list):
        items: list[dict[str, str]] = []
        for item in options:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or "").strip()
                text = str(item.get("text") or item.get("content") or "").strip()
                if key or text:
                    items.append({"key": key, "text": text})
        return items
    return []


def _answer_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return "".join(str(item) for item in value)
    return str(value or "").strip()


def _explanation_payload(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "summary": str(value.get("summary") or value.get("text") or value.get("content") or "").strip(),
            "why_user_wrong": str(value.get("why_user_wrong") or value.get("diagnosis") or "").strip(),
        }
    return {"summary": str(value or "").strip(), "why_user_wrong": ""}


def _event_concept(payload: dict[str, Any], errors: list[dict[str, Any]]) -> str:
    signal = _safe_dict(payload.get("next_training_signal"))
    if str(signal.get("concept") or "").strip():
        return str(signal.get("concept") or "").strip()
    for error in errors:
        if str(error.get("concept_tag") or "").strip():
            return str(error.get("concept_tag") or "").strip()
    return ""


def _concept_label(value: str) -> str:
    text = str(value or "").strip()
    return str(display_taxonomy_label(text, fallback=text) or text).strip()


def _error_label(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        code = str(error.get("error_code") or "").strip().upper()
        if code:
            return code
    return ""


def _diagnosis(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        text = str(error.get("diagnosis") or error.get("evidence") or "").strip()
        if text:
            return text
    return ""


def _is_correct(payload: dict[str, Any]) -> bool:
    try:
        awarded = float(payload.get("score_awarded") or 0)
        max_score = float(payload.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return max_score > 0 and awarded >= max_score


__all__ = ["build_attempt_detail_read_model"]
