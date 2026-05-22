from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref
from deeptutor.services.learner_state.redaction import redact_chat_text
from deeptutor.services.session import build_user_owner_key
from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label

_HISTORY_CONTEXT_BLOCK_RE = re.compile(
    r"\[\s*history\s*context\s*\].*?\[\s*/\s*history\s*context\s*\]",
    re.IGNORECASE | re.DOTALL,
)
_INTERNAL_IDENTIFIER_RE = re.compile(
    r"\b(?:trace_id|trace|event_id|evt_id|openid|user_id|session_uid|kid)\s*[:=]\s*[A-Za-z0-9_\-]+",
    re.IGNORECASE,
)


def build_attempt_detail_read_model(
    *,
    user_id: str,
    learner_state_service: Any,
    attempt_ref: str,
    session_store: Any | None = None,
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
    historical_explanation = _historical_assistant_explanation(
        event=event,
        payload=payload,
        session_store=session_store,
        user_id=normalized_user,
    )
    if historical_explanation:
        explanation["full_text"] = _sanitize_history_text(historical_explanation)
        explanation["source"] = "history_assistant"
    question = {
        "question_id": question_id,
        "stem": _question_stem(payload),
        "options": _option_items(payload.get("options")),
        "type": str(payload.get("question_type") or payload.get("type") or "").strip(),
    }
    answer = {
        "user_answer": _answer_text(payload.get("user_answer")),
        "correct_answer": _answer_text(payload.get("correct_answer")),
        "score_awarded": payload.get("score_awarded"),
        "max_score": payload.get("max_score"),
        "result_label": "答对" if is_correct else "答错",
    }
    diagnosis = {
        "concept_label": concept,
        "error_label": error,
        "detail": _diagnosis(errors),
    }

    return {
        "ok": True,
        "attempt_ref": str(attempt_ref or ""),
        "question": question,
        "answer": answer,
        "explanation": explanation,
        "diagnosis": diagnosis,
        "conversation": {
            "title": question["stem"] or "本次作答复盘",
            "turns": _conversation_turns(question=question, answer=answer, explanation=explanation, diagnosis=diagnosis),
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


def _conversation_turns(
    *,
    question: dict[str, Any],
    answer: dict[str, Any],
    explanation: dict[str, Any],
    diagnosis: dict[str, Any],
) -> list[dict[str, str]]:
    question_content = _question_content(question)
    answer_content = str(answer.get("user_answer") or "").strip()
    system_content = _system_explanation_content(answer=answer, explanation=explanation, diagnosis=diagnosis)
    turns = [
        {"role": "system", "label": "系统出题", "content": question_content},
        {"role": "student", "label": "学员作答", "content": answer_content},
        {"role": "system", "label": "系统解析", "content": system_content},
    ]
    return [turn for turn in turns if str(turn.get("content") or "").strip()]


def _question_content(question: dict[str, Any]) -> str:
    stem = str(question.get("stem") or "").strip()
    option_lines = [
        f"{str(item.get('key') or '').strip()}. {str(item.get('text') or '').strip()}".strip()
        for item in _safe_list(question.get("options"))
        if isinstance(item, dict) and (str(item.get("key") or "").strip() or str(item.get("text") or "").strip())
    ]
    return "\n".join([stem, *option_lines]).strip()


def _system_explanation_content(
    *,
    answer: dict[str, Any],
    explanation: dict[str, Any],
    diagnosis: dict[str, Any],
) -> str:
    full_text = str(explanation.get("full_text") or "").strip()
    if full_text:
        return full_text
    result = str(answer.get("result_label") or "").strip()
    correct = str(answer.get("correct_answer") or "").strip()
    first_line = result
    if correct:
        first_line = f"{first_line}。正确答案：{correct}" if first_line else f"正确答案：{correct}"
    lines = [
        first_line,
        str(explanation.get("summary") or "").strip(),
        str(explanation.get("why_user_wrong") or "").strip(),
    ]
    error_label = str(diagnosis.get("detail") or diagnosis.get("error_label") or "").strip()
    if error_label:
        lines.append(f"错因：{error_label}")
    return "\n".join(line for line in lines if line).strip()


def _explanation_payload(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "summary": str(value.get("summary") or value.get("text") or value.get("content") or "").strip(),
            "why_user_wrong": str(value.get("why_user_wrong") or value.get("diagnosis") or "").strip(),
            "full_text": str(value.get("full_text") or "").strip(),
            "source": str(value.get("source") or "").strip(),
        }
    return {"summary": str(value or "").strip(), "why_user_wrong": "", "full_text": "", "source": ""}


def _historical_assistant_explanation(
    *,
    event: Any,
    payload: dict[str, Any],
    session_store: Any | None,
    user_id: str,
) -> str:
    if session_store is None:
        return ""
    session_id = str(payload.get("session_id") or payload.get("conversation_id") or "").strip()
    turn_ids = _attempt_turn_ids(event=event, payload=payload)
    if session_id:
        session = _load_session(session_store, session_id)
        if isinstance(session, dict):
            content = _assistant_content_for_turn(_safe_list(session.get("messages")), turn_ids)
            if content:
                return content
    return _assistant_content_from_owner_sessions(
        session_store=session_store,
        user_id=user_id,
        turn_ids=turn_ids,
    )


def _load_session(session_store: Any, session_id: str) -> Any:
    loader = getattr(session_store, "get_session_with_messages", None)
    if not callable(loader):
        return None
    return _resolve_maybe_async(loader(session_id))


def _assistant_content_from_owner_sessions(
    *,
    session_store: Any,
    user_id: str,
    turn_ids: set[str],
) -> str:
    if not turn_ids:
        return ""
    lister = getattr(session_store, "list_sessions_by_owner", None)
    if not callable(lister):
        return ""
    sessions = _resolve_maybe_async(
        lister(build_user_owner_key(user_id), source="wx_miniprogram", limit=20)
    )
    for row in _safe_list(sessions):
        if not isinstance(row, dict):
            continue
        session_id = str(row.get("id") or row.get("session_id") or "").strip()
        session = _load_session(session_store, session_id) if session_id else row
        if not isinstance(session, dict):
            continue
        content = _assistant_content_for_turn(_safe_list(session.get("messages")), turn_ids)
        if content:
            return content
    return ""


def _resolve_maybe_async(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    return asyncio.run(value)


def _attempt_turn_ids(*, event: Any, payload: dict[str, Any]) -> set[str]:
    candidates = {
        _base_turn_id(payload.get("turn_id")),
        _base_turn_id(payload.get("source_id")),
        _base_turn_id(getattr(event, "source_id", "")),
    }
    return {item for item in candidates if item}


def _base_turn_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("turn:"):
        text = text[len("turn:") :]
    if text.startswith("turn_") and ":" in text:
        text = text.split(":", 1)[0]
    return text.strip()


def _assistant_content_for_turn(messages: list[Any], turn_ids: set[str]) -> str:
    if not turn_ids:
        return ""
    assistant_messages = [
        item
        for item in messages
        if isinstance(item, dict) and str(item.get("role") or "").strip() == "assistant"
    ]
    for message in reversed(assistant_messages):
        message_turn_id = _message_turn_id(message)
        if message_turn_id and _base_turn_id(message_turn_id) in turn_ids:
            return str(message.get("content") or "").strip()
    return ""


def _sanitize_history_text(text: str) -> str:
    cleaned = _HISTORY_CONTEXT_BLOCK_RE.sub("", str(text or ""))
    cleaned = _INTERNAL_IDENTIFIER_RE.sub("", cleaned)
    cleaned = redact_chat_text(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _message_turn_id(message: dict[str, Any]) -> str:
    events = _safe_list(message.get("events"))
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        direct = str(event.get("turn_id") or "").strip()
        if direct:
            return direct
        metadata = _safe_dict(event.get("metadata"))
        if str(metadata.get("turn_id") or "").strip():
            return str(metadata.get("turn_id") or "").strip()
        nested = _safe_dict(metadata.get("metadata"))
        if str(nested.get("turn_id") or "").strip():
            return str(nested.get("turn_id") or "").strip()
    metadata = _safe_dict(message.get("metadata"))
    return str(metadata.get("turn_id") or "").strip()


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
            return _error_code_label(code)
    return ""


def _error_code_label(code: str) -> str:
    labels = {
        "M01": "知识点不熟",
        "M02": "关键词误读",
        "M03": "概念混淆",
        "M04": "选项陷阱",
        "M05": "审题方向错误",
        "M06": "多选漏选",
        "M07": "多选错选",
        "M08": "规范数字混淆",
        "M09": "题干条件提取不完整",
        "M10": "用常识替代规范判断",
    }
    return labels.get(str(code or "").strip().upper(), "错因")


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
