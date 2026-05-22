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
_NON_LEARNING_RE = re.compile(
    r"(你好|您好|早上好|晚上好|谢谢|再见|登录|支付|会员|余额|订单|页面|按钮|打不开|系统繁忙|稍后再试|网络异常)"
)
_ERROR_FALLBACK_RE = re.compile(r"(抱歉|出错|失败|暂时无法|稍后再试|系统繁忙|网络异常)")
_STILL_CONFUSED_RE = re.compile(r"(还是不懂|还是没懂|还是没听懂|没听明白|仍困惑|仍然困惑|不理解|没理解)")
_MISTAKE_RE = re.compile(r"(为什么错|哪里错|错因|错题|漏选|怎么区分|如何区分|怎么训练|如何训练)")
_CONCEPT_RE = re.compile(r"(概念|是什么|讲解|解释|知识点|原理)")
def build_learning_evidence_from_conversation_turn(
    *,
    user_id: str,
    turn_ref: str,
    user_question: str,
    assistant_answer: dict[str, Any] | str,
    learning_signal_type: str | None = None,
    subject_id: str = "",
    training_intent_id: str | None = None,
    prompt_intent: dict[str, Any] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    assistant = _assistant_dict(assistant_answer)
    intent = dict(prompt_intent or {}) if isinstance(prompt_intent, dict) else {}
    summary = _summary(assistant)
    combined_text = "\n".join([str(user_question or ""), summary])
    if _should_skip_conversation(user_question=user_question, summary=summary, intent=intent):
        return None
    signal_type = _learning_signal_type(
        explicit=learning_signal_type,
        prompt_intent=intent,
        text=combined_text,
        structured_answer=_has_structured_learning_fields(assistant),
    )
    refs = _source_refs(assistant=assistant, explicit=source_refs)
    concept_label = _concept_label(assistant=assistant, intent=intent, refs=refs, text=combined_text)
    error_label = _error_label(assistant=assistant, intent=intent, text=combined_text)
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
        "source_refs": refs,
        "quality": {
            "detail_ready": bool(summary and concept_label),
            "progress_countable": False,
            "truth_eligible": False,
            "stable_truth_eligible": False,
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
    learning_signal_type: str | None = None,
    subject_id: str = "",
    training_intent_id: str | None = None,
    prompt_intent: dict[str, Any] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
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
        source_refs=source_refs,
    )
    if event is None:
        return None
    written = learner_state_service.append_memory_event(
        str(user_id or "").strip(),
        source_feature=event["source_feature"],
        source_id=event["source_id"],
        source_bot_id=None,
        memory_kind="learning_evidence",
        payload_json=event["payload_json"],
        dedupe_key=event["dedupe_key"],
    )
    _write_home_projection(
        learner_state_service=learner_state_service,
        user_id=user_id,
        payload=event["payload_json"],
    )
    return written


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


def _should_skip_conversation(*, user_question: str, summary: str, intent: dict[str, Any]) -> bool:
    if intent:
        return False
    question = str(user_question or "").strip()
    answer = str(summary or "").strip()
    if not question or not answer:
        return True
    if _ERROR_FALLBACK_RE.search(answer):
        return True
    if _NON_LEARNING_RE.fullmatch(question) or _NON_LEARNING_RE.fullmatch(answer):
        return True
    return False


def _learning_signal_type(
    *,
    explicit: str | None,
    prompt_intent: dict[str, Any],
    text: str,
    structured_answer: bool,
) -> str:
    explicit_signal = str(explicit or "").strip()
    if explicit_signal in _SIGNAL_TYPES:
        return explicit_signal
    if prompt_intent:
        return "home_prompt_clicked"
    if _STILL_CONFUSED_RE.search(text):
        return "still_confused"
    if structured_answer:
        return "answer_explanation"
    if _MISTAKE_RE.search(text):
        return "mistake_explain"
    if _CONCEPT_RE.search(text):
        return "concept_explain"
    return "answer_explanation"


def _has_structured_learning_fields(assistant: dict[str, Any]) -> bool:
    return any(
        key in assistant
        for key in ("concept_label", "error_label", "concept", "error", "source_refs")
    )


def _concept_label(*, assistant: dict[str, Any], intent: dict[str, Any], refs: list[dict[str, Any]], text: str) -> str:
    raw_concept = assistant.get("concept")
    nested = raw_concept.get("label") if isinstance(raw_concept, dict) else ""
    label = str(
        assistant.get("concept_label")
        or intent.get("concept_label")
        or nested
        or _concept_from_refs(refs)
        or ""
    ).strip()
    if label:
        return label
    match = re.search(r"([\u4e00-\u9fff]{2,12})(?:概念|知识点|多选题|为什么|怎么|如何)", text)
    return _normalize_concept_phrase(str(match.group(1)).strip()) if match else ""


def _error_label(*, assistant: dict[str, Any], intent: dict[str, Any], text: str) -> str:
    raw_error = assistant.get("error")
    nested = raw_error.get("label") if isinstance(raw_error, dict) else ""
    label = str(
        assistant.get("error_label")
        or intent.get("error_label")
        or nested
        or ""
    ).strip()
    if label:
        return label
    if "多选" in text and "漏选" in text:
        return "多选漏选"
    if "漏选" in text:
        return "漏选"
    if "混淆" in text:
        return "概念混淆"
    if "审题" in text:
        return "审题错误"
    return ""


def _source_refs(*, assistant: dict[str, Any], explicit: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for value in (assistant.get("source_refs"), explicit):
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                refs.append(dict(item))
    return refs[:8]


def _concept_from_refs(refs: list[dict[str, Any]]) -> str:
    for ref in refs:
        label = str(ref.get("concept_label") or ref.get("concept") or ref.get("knowledge_title") or "").strip()
        if label:
            return label
    return ""


def _normalize_concept_phrase(value: str) -> str:
    text = str(value or "").strip(" ，,。？?：:")
    for suffix in ("多选题", "单选题", "案例题", "判断题", "题"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
            break
    return text.strip(" ，,。？?：:")


def _write_home_projection(*, learner_state_service: Any, user_id: str, payload: dict[str, Any]) -> None:
    try:
        from deeptutor.services.learner_state.home_personalization import (
            build_home_personalization_projection_from_learning_signal,
            write_home_personalization_projection,
        )

        projection = build_home_personalization_projection_from_learning_signal(payload)
        write_home_personalization_projection(
            learner_state_service,
            user_id=user_id,
            projection=projection,
        )
    except Exception:
        return


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
