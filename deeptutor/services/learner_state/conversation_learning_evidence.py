from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any


_TZ = timezone(timedelta(hours=8))
_SIGNAL_TYPES = {
    "answer_explanation",
    "concept_explain",
    "mistake_explain",
    "still_confused",
    "home_prompt_clicked",
}


def build_learning_evidence_from_conversation_turn(
    *,
    user_id: str,
    turn_ref: str,
    user_question: str,
    assistant_answer: dict[str, Any] | str,
    learning_signal_type: str = "answer_explanation",
    subject_id: str = "",
    training_intent_id: str | None = None,
    prompt_intent: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    signal_type = str(learning_signal_type or "").strip()
    if signal_type not in _SIGNAL_TYPES:
        signal_type = "answer_explanation"
    assistant = _assistant_dict(assistant_answer)
    intent = dict(prompt_intent or {}) if isinstance(prompt_intent, dict) else {}
    summary = _summary(assistant)
    concept_label = str(assistant.get("concept_label") or intent.get("concept_label") or "").strip()
    error_label = str(assistant.get("error_label") or intent.get("error_label") or "").strip()
    if not summary or not (concept_label or error_label):
        return None
    normalized_subject_id = str(subject_id or intent.get("subject_id") or "").strip()
    normalized_training_intent_id = str(
        training_intent_id
        if training_intent_id is not None
        else intent.get("training_intent_id")
        or ""
    ).strip()
    redacted_question, redacted = redact_learning_question(user_question)
    payload = {
        "event_type": "learning_evidence",
        "memory_kind": "learning_evidence",
        "evidence_source": "conversation_synthesis",
        "learning_signal_type": signal_type,
        "subject_id": normalized_subject_id,
        "training_intent_id": normalized_training_intent_id or None,
        "conversation_turn_ref": str(turn_ref or "").strip(),
        "user_question": redacted_question,
        "user_question_redacted": redacted,
        "assistant_explanation_summary": summary,
        "concept": {"label": concept_label},
        "error": {"label": error_label},
        "evidence_level": "exposed",
        "confidence": 0.45 if signal_type != "still_confused" else 0.3,
        "source_refs": list(assistant.get("source_refs") or []),
        "quality": {
            "detail_ready": bool(summary and concept_label),
            "progress_countable": False,
            "truth_eligible": False,
            "missing_fields": [] if concept_label else ["concept_label"],
            "degraded_reason": "conversation_signal_not_grading_truth",
        },
    }
    return {
        "user_id": str(user_id or "").strip(),
        "source_feature": "conversation_synthesis",
        "source_id": str(turn_ref or "").strip(),
        "source_bot_id": None,
        "memory_kind": "learning_evidence",
        "payload_json": payload,
        "dedupe_key": _dedupe_key(user_id=user_id, turn_ref=turn_ref, payload=payload),
        "created_at": datetime.now(_TZ).isoformat(),
        **payload,
    }


def write_conversation_learning_evidence_event(
    *,
    learner_state_service: Any,
    user_id: str,
    turn_ref: str,
    user_question: str,
    assistant_answer: dict[str, Any] | str,
    learning_signal_type: str = "answer_explanation",
    subject_id: str = "",
    training_intent_id: str | None = None,
    prompt_intent: dict[str, Any] | None = None,
) -> Any | None:
    event = build_learning_evidence_from_conversation_turn(
        user_id=user_id,
        turn_ref=turn_ref,
        user_question=user_question,
        assistant_answer=assistant_answer,
        learning_signal_type=learning_signal_type,
        subject_id=subject_id,
        training_intent_id=training_intent_id,
        prompt_intent=prompt_intent,
    )
    if event is None:
        return None
    return learner_state_service.append_memory_event(
        str(user_id or "").strip(),
        source_feature=event["source_feature"],
        source_id=event["source_id"],
        source_bot_id=None,
        memory_kind="learning_evidence",
        payload_json=event["payload_json"],
        dedupe_key=event["dedupe_key"],
    )


def redact_learning_question(text: str) -> tuple[str, bool]:
    original = str(text or "")
    redacted = original
    redacted = re.sub(r"1\d{10}", "[REDACTED_PHONE]", redacted)
    redacted = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", redacted)
    redacted = re.sub(r"\b\d{17}[\dXx]\b", "[REDACTED_ID]", redacted)
    redacted = re.sub(r"([\u4e00-\u9fff]{2,4})(同学|老师|先生|女士)?(?=[:：,，\\s])", "[REDACTED_NAME]", redacted, count=1)
    return redacted, redacted != original


def _assistant_dict(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {"summary": str(value or "")}


def _summary(assistant: dict[str, Any]) -> str:
    text = str(assistant.get("summary") or assistant.get("text") or assistant.get("content") or "").strip()
    text = re.sub(r"^(我来解释一下|简单来说|这里需要注意的是)[:：，,\\s]*", "", text)
    return text[:200].strip()


def _dedupe_key(*, user_id: str, turn_ref: str, payload: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(user_id or "").strip(),
            str(turn_ref or "").strip(),
            str(payload.get("learning_signal_type") or ""),
            str(payload.get("assistant_explanation_summary") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


__all__ = [
    "build_learning_evidence_from_conversation_turn",
    "redact_learning_question",
    "write_conversation_learning_evidence_event",
]
