"""
Deep Question Capability
========================

Multi-agent question generation pipeline: Idea -> Evaluate -> Generate -> Validate.
Wraps the existing ``AgentCoordinator``.
"""

from __future__ import annotations

import base64
import re
import tempfile
from typing import Any

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.trace import merge_trace_metadata
from deeptutor.services.construction_grading.deep_question_adapter import (
    attach_deep_question_grading_result,
)
from deeptutor.services.construction_grading.writeback import write_grading_error_events
from deeptutor.services.question_followup import (
    apply_followup_action_to_context,
    answers_match,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    normalize_question_followup_context,
    resolve_submission_attempt,
    should_reveal_reference_material,
)
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.semantic_router import (
    apply_active_object_transition,
    build_active_object_from_question_context,
    build_turn_semantic_decision,
    normalize_active_object,
    normalize_suspended_object_stack,
    normalize_turn_semantic_decision,
    question_context_from_active_object,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


_GENERATION_TOPIC_ANCHOR_MARKERS = (
    "刚才",
    "上面",
    "这些",
    "这几个",
    "这个概念",
    "几个概念",
    "类似",
    "相关",
    "同类",
    "继续",
    "再来",
    "不要超纲",
    "围绕这个",
    "围绕刚才",
)
_GENERATION_REQUEST_STRIP_PATTERNS = (
    r"好[,，]?",
    r"那你现在",
    r"现在",
    r"请",
    r"麻烦你",
    r"麻烦",
    r"给我",
    r"帮我",
    r"我想",
    r"想",
    r"继续出",
    r"继续来一道",
    r"继续",
    r"再来一道",
    r"再来一题",
    r"再来",
    r"再出一道",
    r"再出",
    r"来一道",
    r"来一题",
    r"来",
    r"出题",
    r"出",
    r"考我",
    r"刷题",
    r"测我",
    r"[0-9一二两三四五六七八九十几]+(?:道|题|个题目|个小题)?",
    r"单选题",
    r"多选题",
    r"选择题",
    r"判断题",
    r"案例题",
    r"简答题",
    r"题目",
    r"很简单的",
    r"简单的",
    r"很简单",
    r"简单",
    r"容易的",
    r"容易",
)
_CURRENT_QUESTION_ANCHOR_MARKERS = (
    "这道题",
    "这题",
    "同类题",
    "类似题",
    "同类型题",
    "按这题",
    "围绕这题",
    "照着这题",
)
_MCQ_QUESTION_TYPES = {
    "choice",
    "single_choice",
    "multiple_choice",
    "multi_choice",
    "mcq",
    "judge",
    "judgment",
}
_QUESTION_BANK_METADATA_KEYS = (
    "exact_question",
    "questions_bank",
    "question_bank_row",
    "question_row",
    "source_question",
    "recovered_question_context",
)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clip_text(value: Any, *, limit: int = 280) -> str:
    text = _compact_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _append_unique(parts: list[str], candidate: Any) -> None:
    text = _compact_text(candidate)
    if not text or text in parts:
        return
    parts.append(text)


def _training_signal_text_from_context(question_context: dict[str, Any]) -> str:
    grading_result = (
        question_context.get("construction_grading_result")
        if isinstance(question_context.get("construction_grading_result"), dict)
        else {}
    )
    signal = grading_result.get("next_training_signal") if isinstance(grading_result, dict) else {}
    if not isinstance(signal, dict) or not signal:
        return ""
    parts: list[str] = []
    for key in ("concept", "focus", "mode"):
        value = _compact_text(signal.get(key))
        if value:
            parts.append(f"{key}={value}")
    error_codes = [
        _compact_text(error.get("error_code"))
        for error in list(grading_result.get("error_events") or [])
        if isinstance(error, dict) and _compact_text(error.get("error_code"))
    ]
    if error_codes:
        parts.append(f"error_codes={','.join(error_codes[:4])}")
    return "；".join(parts)


def _compiled_training_signal_text_from_context(question_context: dict[str, Any]) -> str:
    truth = question_context.get("compiled_learning_truth")
    if not isinstance(truth, dict):
        return ""
    weak_points = list(truth.get("weak_points") or [])
    parts: list[str] = []
    for item in weak_points[:3]:
        if not isinstance(item, dict):
            continue
        decay_state = _compact_text(item.get("decay_state"))
        if decay_state and decay_state != "active":
            continue
        if item.get("superseded_by_event_ids"):
            continue
        evidence_level = _compact_text(item.get("evidence_level"))
        if evidence_level not in {"L1_repeated", "L2_confirmed", "L3_mastery_signal"}:
            continue
        policy_action = "stable_personalization" if evidence_level in {"L2_confirmed", "L3_mastery_signal"} else "diagnostic_hint"
        concept = _compact_text(item.get("concept_id"))
        error_code = _compact_text(item.get("error_code"))
        training = item.get("recommended_training") if isinstance(item.get("recommended_training"), dict) else {}
        focus = _compact_text(training.get("focus"))
        mode = _compact_text(training.get("mode"))
        signal_parts: list[str] = []
        if concept:
            signal_parts.append(f"concept={concept}")
        if focus:
            signal_parts.append(f"focus={focus}")
        if mode:
            signal_parts.append(f"mode={mode}")
        if error_code:
            signal_parts.append(f"error_codes={error_code}")
        if signal_parts:
            signal_parts.append(f"evidence_level={evidence_level}")
            signal_parts.append(f"policy_action={policy_action}")
            parts.append("；".join(signal_parts))
    return " | ".join(parts)


def _question_context_generation_anchor(question_context: dict[str, Any] | None) -> str:
    raw_context = question_context if isinstance(question_context, dict) else {}
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return ""
    if (
        "compiled_learning_truth" not in normalized
        and isinstance(raw_context.get("compiled_learning_truth"), dict)
    ):
        normalized = dict(normalized)
        normalized["compiled_learning_truth"] = raw_context["compiled_learning_truth"]

    items = normalized.get("items") or []
    contexts = [normalized, *[item for item in items if isinstance(item, dict)]]
    concentrations: list[str] = []
    knowledge_parts: list[str] = []
    question_parts: list[str] = []
    training_parts: list[str] = []

    for item in contexts:
        _append_unique(concentrations, item.get("concentration"))
        _append_unique(knowledge_parts, _clip_text(item.get("knowledge_context"), limit=220))
        _append_unique(question_parts, _clip_text(item.get("question"), limit=160))
        training_signal = _training_signal_text_from_context(item)
        if training_signal:
            _append_unique(
                training_parts,
                f"上一轮错因训练信号：{training_signal}；下一题优先从现有题库选择同考点、同错因的相似题。",
            )
        compiled_training_signal = _compiled_training_signal_text_from_context(item)
        if compiled_training_signal:
            _append_unique(
                training_parts,
                f"长期错因训练信号：{compiled_training_signal}；下一题优先从现有题库选择同考点、同错因的相似题。",
            )

    anchor_lines: list[str] = []
    if concentrations:
        anchor_lines.append(f"当前考点：{'；'.join(concentrations[:4])}")
    if training_parts:
        anchor_lines.append("；".join(training_parts[:3]))
    if knowledge_parts:
        anchor_lines.append(f"当前知识锚点：{'；'.join(knowledge_parts[:2])}")
    elif question_parts:
        anchor_lines.append(f"当前题目内容：{'；'.join(question_parts[:2])}")
    return "\n".join(anchor_lines)


def _active_object_generation_anchor(active_object: dict[str, Any] | None) -> str:
    normalized = normalize_active_object(active_object)
    if not normalized:
        return ""

    question_anchor = _question_context_generation_anchor(
        question_context_from_active_object(normalized)
    )
    if question_anchor:
        return question_anchor

    snapshot = normalized.get("state_snapshot") if isinstance(normalized.get("state_snapshot"), dict) else {}
    object_type = str(normalized.get("object_type") or "").strip()
    anchor_lines: list[str] = []

    if object_type == "open_chat_topic":
        title = _clip_text(snapshot.get("title"), limit=80)
        summary = _clip_text(snapshot.get("compressed_summary"), limit=220)
        if summary:
            anchor_lines.append(f"当前会话摘要：{summary}")
        elif title:
            anchor_lines.append(f"当前会话主题：{title}")
        return "\n".join(anchor_lines)

    if object_type in {"guide_page", "study_plan"}:
        current_page = snapshot.get("current_page") if isinstance(snapshot.get("current_page"), dict) else {}
        knowledge_title = _clip_text(current_page.get("knowledge_title"), limit=80)
        knowledge_summary = _clip_text(current_page.get("knowledge_summary"), limit=220)
        summary = _clip_text(snapshot.get("summary"), limit=180)
        if knowledge_title:
            anchor_lines.append(f"当前学习主题：{knowledge_title}")
        if knowledge_summary:
            anchor_lines.append(f"当前学习摘要：{knowledge_summary}")
        if summary:
            anchor_lines.append(f"计划上下文：{summary}")
        return "\n".join(anchor_lines)

    return ""


def _conversation_generation_anchor(conversation_context_text: str) -> str:
    text = _clip_text(conversation_context_text, limit=240)
    if not text:
        return ""
    return f"最近对话摘要：{text}"


def _suspended_stack_generation_anchor(
    suspended_object_stack: list[dict[str, Any]] | None,
) -> str:
    for item in normalize_suspended_object_stack(suspended_object_stack):
        normalized = normalize_active_object(item)
        if not normalized:
            continue
        object_type = str(normalized.get("object_type") or "").strip()
        if object_type in {"question_set", "single_question"}:
            continue
        anchor = _active_object_generation_anchor(normalized)
        if anchor:
            return anchor
    return ""


def _topic_needs_authoritative_anchor(topic: str) -> bool:
    normalized = _compact_text(topic).lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in _GENERATION_TOPIC_ANCHOR_MARKERS):
        return True
    if not looks_like_practice_generation_request(normalized):
        return False
    residue = normalized
    for pattern in _GENERATION_REQUEST_STRIP_PATTERNS:
        residue = re.sub(pattern, " ", residue, flags=re.IGNORECASE)
    residue = re.sub(r"[，。！？、,.!?\-:：\s]+", "", residue)
    return not residue


def _prefers_current_question_anchor(topic: str) -> bool:
    normalized = _compact_text(topic).lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in _CURRENT_QUESTION_ANCHOR_MARKERS):
        return True
    if "概念" in normalized or "知识点" in normalized:
        return False
    return looks_like_practice_generation_request(normalized)


def _resolve_generation_topic(
    *,
    raw_topic: str,
    active_object: dict[str, Any] | None,
    suspended_object_stack: list[dict[str, Any]] | None,
    followup_question_context: dict[str, Any] | None,
    conversation_context_text: str,
) -> str:
    topic = _compact_text(raw_topic)
    if not topic:
        return ""
    if not _topic_needs_authoritative_anchor(topic):
        return topic

    normalized_active_object = normalize_active_object(active_object)
    active_object_type = str((normalized_active_object or {}).get("object_type") or "").strip()
    question_anchor = _question_context_generation_anchor(followup_question_context)
    if not question_anchor and active_object_type in {"question_set", "single_question"}:
        question_anchor = _active_object_generation_anchor(normalized_active_object)

    broader_anchor = _suspended_stack_generation_anchor(suspended_object_stack)
    if not broader_anchor and active_object_type not in {"question_set", "single_question"}:
        broader_anchor = _active_object_generation_anchor(normalized_active_object)
    if not broader_anchor:
        broader_anchor = _conversation_generation_anchor(conversation_context_text)

    anchor = (
        question_anchor or broader_anchor
        if _prefers_current_question_anchor(topic)
        else broader_anchor or question_anchor
    )
    if not anchor:
        return topic
    return (
        f"{topic}\n\n"
        "请严格围绕以下当前学习锚点出题，不要偏题，不要超纲；如果锚点里没有出现某个新概念，不要自行引入：\n"
        f"{anchor}"
    )


def _should_use_followup_anchor_generation(
    *,
    raw_topic: str,
    mode: str,
    num_questions: int,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(mode or "").strip().lower() != "custom":
        return False
    if int(num_questions or 1) > 3:
        return False
    normalized_context = normalize_question_followup_context(followup_question_context)
    if not normalized_context:
        return False
    items = normalized_context.get("items") if isinstance(normalized_context.get("items"), list) else []
    if not items:
        return False
    return _topic_needs_authoritative_anchor(raw_topic)


def _should_use_lightweight_followup_generation(
    *,
    selected_mode: str,
    raw_topic: str,
    num_questions: int,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(selected_mode or "").strip().lower() != "fast":
        return False
    return _should_use_followup_anchor_generation(
        raw_topic=raw_topic,
        mode="custom",
        num_questions=num_questions,
        followup_question_context=followup_question_context,
    )


def _should_use_lightweight_topic_generation(
    *,
    selected_mode: str,
    raw_topic: str,
    resolved_topic: str,
    num_questions: int,
    question_type: str,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(selected_mode or "").strip().lower() != "fast":
        return False
    if normalize_question_followup_context(followup_question_context):
        return False
    if int(num_questions or 1) > 3:
        return False
    normalized_question_type = str(question_type or "").strip().lower()
    if normalized_question_type and normalized_question_type not in {"choice", "judge", "judgment"}:
        return False
    if not _topic_needs_authoritative_anchor(raw_topic):
        return False
    return resolved_topic != _compact_text(raw_topic)


def _grading_items(question_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized = normalize_question_followup_context(question_context) or {}
    raw_items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    items = [
        item
        for item in (
            normalize_question_followup_context(candidate)
            for candidate in raw_items
            if isinstance(candidate, dict)
        )
        if item
    ]
    return items or ([normalized] if normalized else [])


def _is_mcq_grading_context(question_context: dict[str, Any] | None) -> bool:
    items = _grading_items(question_context)
    if not items:
        return False
    for item in items:
        question_type = str(item.get("question_type") or "").strip().lower()
        if question_type in _MCQ_QUESTION_TYPES:
            continue
        options = item.get("options")
        if isinstance(options, dict) and options:
            continue
        return False
    return True


def _mcq_correct_answer_present(question_context: dict[str, Any] | None) -> bool:
    items = _grading_items(question_context)
    return bool(items) and all(str(item.get("correct_answer") or "").strip() for item in items)


def _question_identity(value: Any) -> str:
    text = _compact_text(value).lower()
    return re.sub(r"[\s。！？!?，,、：:；;（）()\[\]【】\"'“”‘’]+", "", text)


def _question_bank_context_candidates(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    raw_metadata = metadata if isinstance(metadata, dict) else {}
    containers.append(raw_metadata)
    nested = raw_metadata.get("metadata")
    if isinstance(nested, dict):
        containers.append(nested)

    candidates: list[dict[str, Any]] = []
    for container in containers:
        for key in _QUESTION_BANK_METADATA_KEYS:
            value = container.get(key)
            if isinstance(value, dict):
                candidates.extend(_coerce_question_bank_contexts(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        candidates.extend(_coerce_question_bank_contexts(item))
    return candidates


def _coerce_question_bank_contexts(value: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_question_followup_context(value)
    if normalized:
        return [normalized]

    exact_summary = build_choice_result_summary_from_exact_question(value)
    if exact_summary:
        exact_context = build_question_followup_context_from_result_summary(
            exact_summary,
            "",
            reveal_answers=True,
            reveal_explanations=True,
        )
        if exact_context:
            return [exact_context]

    question = str(
        value.get("question")
        or value.get("stem")
        or value.get("question_stem")
        or value.get("question_text")
        or ""
    ).strip()
    correct_answer = str(value.get("correct_answer") or value.get("answer") or "").strip()
    options = _coerce_mcq_options(value.get("options"))
    if not question or not correct_answer:
        return []
    row = {
        "question_id": str(value.get("question_id") or value.get("id") or value.get("chunk_id") or "").strip(),
        "question": question,
        "question_type": "choice",
        "options": options,
        "correct_answer": correct_answer,
        "explanation": str(value.get("explanation") or value.get("analysis") or "").strip(),
        "difficulty": str(value.get("difficulty") or "").strip(),
        "concentration": str(value.get("concentration") or value.get("testing_focus") or "").strip(),
        "knowledge_context": str(value.get("knowledge_context") or "").strip(),
        "multi_select": bool(len(re.findall(r"[A-E]", correct_answer.upper())) > 1),
    }
    normalized_row = normalize_question_followup_context(row)
    return [normalized_row] if normalized_row else []


def _coerce_mcq_options(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, dict):
        options = {
            str(key).strip().upper()[:1]: str(value or "").strip()
            for key, value in raw.items()
            if str(key).strip() and str(value or "").strip()
        }
        return options or None
    if isinstance(raw, list):
        options: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("label") or "").strip().upper()[:1]
            value = str(item.get("text") or item.get("value") or item.get("content") or "").strip()
            if key and value and key not in options:
                options[key] = value
        return options or None
    return None


def _candidate_question_items(candidate_context: dict[str, Any]) -> list[dict[str, Any]]:
    items = candidate_context.get("items") if isinstance(candidate_context.get("items"), list) else []
    normalized_items = [
        item
        for item in (
            normalize_question_followup_context(candidate)
            for candidate in items
            if isinstance(candidate, dict)
        )
        if item
    ]
    return normalized_items or ([candidate_context] if candidate_context else [])


def _match_question_bank_item(
    target: dict[str, Any],
    candidate_contexts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target_id = str(target.get("question_id") or target.get("id") or "").strip()
    target_question = _question_identity(
        target.get("question") or target.get("stem") or target.get("question_text")
    )
    for candidate_context in candidate_contexts:
        for candidate in _candidate_question_items(candidate_context):
            if not str(candidate.get("correct_answer") or "").strip():
                continue
            candidate_id = str(candidate.get("question_id") or candidate.get("id") or "").strip()
            if target_id and candidate_id and target_id == candidate_id:
                return candidate
            candidate_question = _question_identity(
                candidate.get("question") or candidate.get("stem") or candidate.get("question_text")
            )
            if target_question and candidate_question and target_question == candidate_question:
                return candidate
    return None


def _fill_missing_mcq_authority(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    filled = dict(target)
    had_correct_answer = bool(str(filled.get("correct_answer") or "").strip())
    recovered_correct_answer = False
    for key in (
        "correct_answer",
        "explanation",
        "options",
        "question_type",
        "multi_select",
        "difficulty",
        "concentration",
        "knowledge_context",
    ):
        if key == "correct_answer" or not filled.get(key):
            value = source.get(key)
            if value not in (None, "", {}):
                filled[key] = value
                if key == "correct_answer" and not had_correct_answer:
                    recovered_correct_answer = True
    if recovered_correct_answer:
        filled["is_correct"] = None
        filled.pop("score", None)
        filled.pop("construction_grading_result", None)
    return filled


def _recover_missing_mcq_authority(
    question_context: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, bool]:
    normalized = normalize_question_followup_context(question_context) or dict(question_context or {})
    if not _is_mcq_grading_context(normalized):
        return normalized, "", True
    if _mcq_correct_answer_present(normalized):
        return normalized, "active_object", True

    candidates = _question_bank_context_candidates(metadata)
    if not candidates:
        return normalized, "missing", False

    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    if items:
        recovered_items: list[dict[str, Any]] = []
        changed = False
        for item in items:
            normalized_item = normalize_question_followup_context(item) if isinstance(item, dict) else None
            if not normalized_item:
                continue
            if str(normalized_item.get("correct_answer") or "").strip():
                recovered_items.append(normalized_item)
                continue
            source_item = _match_question_bank_item(normalized_item, candidates)
            if source_item is None:
                recovered_items.append(normalized_item)
                continue
            recovered_items.append(_fill_missing_mcq_authority(normalized_item, source_item))
            changed = True
        if changed:
            recovered = dict(normalized)
            recovered["items"] = recovered_items
            return recovered, "questions_bank", _mcq_correct_answer_present(recovered)
        return normalized, "missing", False

    source_item = _match_question_bank_item(normalized, candidates)
    if source_item is None:
        return normalized, "missing", False
    recovered = _fill_missing_mcq_authority(normalized, source_item)
    return recovered, "questions_bank", _mcq_correct_answer_present(recovered)


def _mcq_trace_fields(
    question_context: dict[str, Any] | None,
    *,
    authority_source: str,
    correct_answer_present: bool,
) -> dict[str, Any]:
    if not _is_mcq_grading_context(question_context):
        return {}
    source = str(authority_source or "").strip() or (
        "active_object" if correct_answer_present else "missing"
    )
    return {
        "grading_kernel": "mcq",
        "correct_answer_present": bool(correct_answer_present),
        "question_authority_source": source,
    }


def _render_missing_mcq_authority_feedback() -> str:
    return (
        "当前选择题缺少标准答案，不能稳定判分；我不会让模型猜答案。\n\n"
        "请重新生成题目，或提交带标准答案的题卡后再批改。"
    )


def _clear_blocked_grading_state(question_context: dict[str, Any]) -> dict[str, Any]:
    cleared = dict(question_context or {})
    cleared["is_correct"] = None
    cleared.pop("construction_grading_result", None)
    cleared.pop("score", None)
    cleared["diagnosis"] = "AUTHORITY_MISSING"
    items = cleared.get("items") if isinstance(cleared.get("items"), list) else []
    if items:
        cleared_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cleared_item = dict(item)
            cleared_item["is_correct"] = None
            cleared_item.pop("construction_grading_result", None)
            cleared_item.pop("score", None)
            cleared_items.append(cleared_item)
        cleared["items"] = cleared_items
    return cleared


def _should_use_deterministic_grading_feedback(
    *,
    selected_mode: str,
    question_context: dict[str, Any] | None,
) -> bool:
    # selected_mode is a presentation choice. Objective grading authority lives
    # in the normalized question context and should not depend on renderer mode.
    _ = selected_mode
    items = _grading_items(question_context)
    if not items:
        return False
    for item in items:
        question_type = str(item.get("question_type") or "").strip().lower()
        if question_type not in {
            "choice",
            "single_choice",
            "multiple_choice",
            "multi_choice",
            "mcq",
            "judge",
            "judgment",
        }:
            return False
        if item.get("is_correct") is None:
            return False
        if not str(item.get("correct_answer") or "").strip():
            return False
    return True


def _render_deterministic_grading_feedback(question_context: dict[str, Any] | None) -> str:
    items = _grading_items(question_context)
    if not items:
        return ""
    if len(items) == 1:
        item = items[0]
        is_correct = item.get("is_correct") is True
        lines = [
            "## 📊 阅卷结论",
            f"**结果：** {'正确' if is_correct else '错误'}",
            f"**你的答案：** {_format_answer_with_option_text(item, item.get('user_answer'))}",
            f"**正确答案：** {_format_answer_with_option_text(item, item.get('correct_answer'))}",
        ]
        explanation = _objective_explanation(item)
        if explanation:
            lines.extend(["", "## 🧐 解析", explanation])
        return "\n".join(lines).strip()

    total = len(items)
    correct_count = sum(1 for item in items if item.get("is_correct") is True)
    lines = [
        "## 📊 阅卷结论",
        f"**得分：** {correct_count}/{total}题",
        (
            "**整体判断：** 全部答对。"
            if correct_count == total
            else "**整体判断：** 重点回看错题。"
        ),
    ]
    for index, item in enumerate(items, 1):
        is_correct = item.get("is_correct") is True
        lines.extend(
            [
                "",
                f"### 第{index}题：{'正确' if is_correct else '错误'}",
                f"- 你的答案：{_format_answer_with_option_text(item, item.get('user_answer'))}",
                f"- 正确答案：{_format_answer_with_option_text(item, item.get('correct_answer'))}",
            ]
        )
        explanation = _objective_explanation(item)
        if explanation:
            lines.append(f"- 解析：{explanation}")
    return "\n".join(lines).strip()


def _objective_items(question_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = _grading_items(question_context)
    objective_items: list[dict[str, Any]] = []
    for item in items:
        question_type = str(item.get("question_type") or "").strip().lower()
        if question_type not in {
            "choice",
            "single_choice",
            "multiple_choice",
            "multi_choice",
            "mcq",
            "judge",
            "judgment",
        }:
            return []
        if not str(item.get("correct_answer") or "").strip():
            return []
        objective_items.append(item)
    return objective_items


def _reference_items(question_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = _grading_items(question_context)
    reference_items: list[dict[str, Any]] = []
    for item in items:
        if not str(item.get("correct_answer") or "").strip():
            return []
        reference_items.append(item)
    return reference_items


def _format_answer_with_option_text(question_context: dict[str, Any], answer: Any) -> str:
    raw_answer = str(answer or "").strip()
    if not raw_answer:
        return "未作答"
    options = question_context.get("options") or {}
    if not isinstance(options, dict) or not options:
        return raw_answer
    letters = re.findall(r"[A-E]", raw_answer.upper())
    if not letters:
        return raw_answer
    parts: list[str] = []
    for letter in letters:
        option_text = str(options.get(letter) or options.get(letter.lower()) or "").strip()
        parts.append(f"{letter}（{option_text}）" if option_text else letter)
    return "、".join(parts) if parts else raw_answer


def _answer_letters(answer: Any) -> list[str]:
    return re.findall(r"[A-E]", str(answer or "").upper())


def _option_entries(question_context: dict[str, Any]) -> list[tuple[str, str]]:
    options = question_context.get("options") or {}
    if not isinstance(options, dict) or not options:
        return []
    entries: list[tuple[str, str]] = []
    for letter in "ABCDE":
        text = str(options.get(letter) or options.get(letter.lower()) or "").strip()
        if text:
            entries.append((letter, text))
    return entries


def _answer_text_without_letter(question_context: dict[str, Any], answer: Any) -> str:
    entries = dict(_option_entries(question_context))
    parts = [
        entries.get(letter, "").strip()
        for letter in _answer_letters(answer)
        if entries.get(letter, "").strip()
    ]
    return "、".join(parts).strip()


def _objective_explanation(question_context: dict[str, Any]) -> str:
    explanation = str(question_context.get("explanation") or "").strip()

    correct = _format_answer_with_option_text(question_context, question_context.get("correct_answer"))
    user_answer = str(question_context.get("user_answer") or "").strip()
    is_correct = question_context.get("is_correct")
    correct_letters = set(_answer_letters(question_context.get("correct_answer")))
    user_letters = set(_answer_letters(user_answer))

    lines: list[str] = []
    if explanation:
        lines.extend(["**标准解析：**", explanation, ""])

    lines.extend(
        [
            "**核心判断：**",
            f"正确选项是 {correct}。",
        ]
    )
    if user_answer and is_correct is False:
        lines.append(
            f"你选择的是 {_format_answer_with_option_text(question_context, user_answer)}，"
            "与题干要求或规范口径不一致。"
        )

    option_lines = _objective_option_analysis_lines(question_context, correct_letters, user_letters)
    if option_lines:
        lines.extend(["", "**逐项解析：**", *option_lines])

    if user_answer and is_correct is False:
        lines.extend(["", "**你为什么会错：**", _objective_wrong_reason(question_context)])

    lines.extend(
        [
            "",
            "**采分点：**",
            "- 抓住题干限定词，先判断它问的是对象、顺序、数值、范围还是做法是否妥当。",
            "- 对照正确选项中的规范关键词，不用相近概念替代标准表述。",
            "- 排除与题干对象不一致、顺序颠倒、数值范围错误或绝对化的干扰项。",
            "",
            "**易错点：**",
            "- 看到熟悉词就选，忽略题干真正限定的工程部位或构造要求。",
            "- 把“可以/应当/不得”“同时/顺序”“不小于/不大于”等关键词看反。",
            "- 多选或判断类题容易漏选一个正确约束，或把相关但不属于本题问法的选项带入。",
            "",
            "**记忆口诀：**",
            _objective_memory_tip(question_context),
        ]
    )
    return "\n".join(line for line in lines if line is not None).strip()


def _objective_option_analysis_lines(
    question_context: dict[str, Any],
    correct_letters: set[str],
    user_letters: set[str],
) -> list[str]:
    entries = _option_entries(question_context)
    if not entries:
        return []
    lines: list[str] = []
    for letter, text in entries:
        selected = letter in user_letters
        correct = letter in correct_letters
        if correct and selected:
            verdict = "正确且你已选中"
            reason = "它直接对应题干要求和标准答案，应保留。"
        elif correct:
            verdict = "正确项"
            reason = "它是本题应抓住的规范口径，答题时不能漏掉。"
        elif selected:
            verdict = "误选项"
            reason = "它看起来相关，但没有命中本题限定，属于典型干扰项。"
        else:
            verdict = "排除项"
            reason = "它与本题标准结论不一致，不能作为正确答案。"
        lines.append(f"- {letter}. {text}：{verdict}。{reason}")
    return lines


def _objective_wrong_reason(question_context: dict[str, Any]) -> str:
    user = _format_answer_with_option_text(question_context, question_context.get("user_answer"))
    correct = _format_answer_with_option_text(question_context, question_context.get("correct_answer"))
    return (
        f"你把 {user} 当成答案，说明判断时更受选项表面相关性影响；"
        f"但本题评分只认 {correct} 对应的标准表述。复盘时先圈题干限定词，"
        "再逐项核对选项是否完整、准确、没有改变对象或顺序。"
    )


def _objective_memory_tip(question_context: dict[str, Any]) -> str:
    correct_text = _answer_text_without_letter(question_context, question_context.get("correct_answer"))
    if correct_text:
        return f"先看题干限定，再背正确项关键词：{correct_text}。"
    return "题干限定先圈出，规范关键词再对应；相近说法不等于正确答案。"


def _split_reference_answer_points(answer: str) -> list[str]:
    compact = _compact_text(answer)
    if not compact:
        return []
    matches = re.findall(r"(?:^|[；;。]\s*)(\d+[\.、]\s*[^；;。]+)", compact)
    if matches:
        return [match.strip() for match in matches if match.strip()]
    parts = [part.strip() for part in re.split(r"[；;]\s*", compact) if part.strip()]
    return parts[:6] if len(parts) > 1 else [compact]


def _first_evidence_line(question_context: dict[str, Any]) -> str:
    knowledge_context = str(question_context.get("knowledge_context") or "").strip()
    for line in knowledge_context.splitlines():
        candidate = _compact_text(line)
        if not candidate:
            continue
        if "§" in candidate or candidate.startswith("【"):
            return candidate
    return ""


def _reference_explanation(question_context: dict[str, Any]) -> str:
    explanation = str(question_context.get("explanation") or "").strip()
    if explanation:
        return explanation

    question_type = str(question_context.get("question_type") or "").strip().lower()
    if question_type in {
        "choice",
        "single_choice",
        "multiple_choice",
        "multi_choice",
        "mcq",
        "judge",
        "judgment",
    }:
        return _objective_explanation(question_context)

    answer = str(question_context.get("correct_answer") or "").strip()
    points = _split_reference_answer_points(answer)
    lines: list[str] = []
    evidence_line = _first_evidence_line(question_context)
    if evidence_line:
        lines.append(f"依据：{evidence_line}")
    if points:
        lines.append("本题按参考答案的关键点给分：")
        lines.extend(f"- {point}" for point in points)
    else:
        lines.append("本题应先写出规范或教材中的关键结论，再结合题干说明理由。")
    lines.append("作答时建议分点写，先判断或列结论，再补对应规范理由，避免只写泛泛描述。")
    return "\n".join(lines).strip()


def _should_render_deterministic_reference_feedback(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    return bool(
        should_reveal_reference_material(user_message, question_context)
        and _reference_items(question_context)
    )


def _render_deterministic_reference_feedback(question_context: dict[str, Any] | None) -> str:
    items = _reference_items(question_context)
    if not items:
        return ""
    if len(items) == 1:
        item = items[0]
        objective = bool(_objective_items(item))
        answer_label = "正确答案" if objective else "参考答案"
        return "\n".join(
            [
                "## ✅ 答案与解析",
                f"**{answer_label}：** {_format_answer_with_option_text(item, item.get('correct_answer'))}",
                "",
                "## 🧐 解析",
                _reference_explanation(item),
            ]
        ).strip()

    lines = ["## ✅ 答案与解析"]
    for index, item in enumerate(items, 1):
        objective = bool(_objective_items(item))
        answer_label = "正确答案" if objective else "参考答案"
        lines.extend(
            [
                "",
                f"### 第{index}题",
                f"- {answer_label}：{_format_answer_with_option_text(item, item.get('correct_answer'))}",
                f"- 解析：{_reference_explanation(item)}",
            ]
        )
    return "\n".join(lines).strip()


def _learner_user_id_from_context(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    billing_context = metadata.get("billing_context") if isinstance(metadata.get("billing_context"), dict) else {}
    return str(
        metadata.get("user_id")
        or billing_context.get("user_id")
        or context.config_overrides.get("user_id")
        or ""
    ).strip()


def _source_bot_id_from_context(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return str(
        metadata.get("bot_id")
        or context.config_overrides.get("bot_id")
        or ""
    ).strip()


def _write_grading_error_events_for_context(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    source_id: str,
) -> int:
    user_id = _learner_user_id_from_context(context)
    grading_result = graded_context.get("construction_grading_result")
    if not user_id or not isinstance(grading_result, dict) or not grading_result:
        return 0
    try:
        from deeptutor.services.learner_state import get_learner_state_service

        return write_grading_error_events(
            learner_state_service=get_learner_state_service(),
            user_id=user_id,
            grading_result=grading_result,
            source_id=source_id,
            source_bot_id=_source_bot_id_from_context(context) or None,
            include_success_events=True,
        )
    except Exception:
        return 0


class DeepQuestionCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="deep_question",
        description="Fast question generation (Template batches -> Generate).",
        stages=["ideation", "generation"],
        tools_used=["rag", "web_search", "code_execution"],
        cli_aliases=["quiz"],
        request_schema=get_capability_request_schema("deep_question"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        from deeptutor.agents.question.coordinator import AgentCoordinator
        from deeptutor.services.llm.config import get_llm_config
        from deeptutor.services.path_service import get_path_service

        llm_config = get_llm_config()
        kb_name = context.knowledge_bases[0] if context.knowledge_bases else None
        turn_id = str(context.metadata.get("turn_id", "") or context.session_id or "deep-question")
        output_dir = get_path_service().get_task_workspace("deep_question", turn_id)

        overrides = context.config_overrides
        force_generate_questions = bool(overrides.get("force_generate_questions", False))
        active_object = normalize_active_object(context.metadata.get("active_object")) or (
            build_active_object_from_question_context(
                context.metadata.get("question_followup_context"),
                source_turn_id=turn_id,
            )
        )
        suspended_object_stack = normalize_suspended_object_stack(
            context.metadata.get("suspended_object_stack")
        )
        turn_semantic_decision = normalize_turn_semantic_decision(
            context.metadata.get("turn_semantic_decision")
        ) or {}
        followup_question_context = question_context_from_active_object(active_object) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        followup_action = (
            context.metadata.get("question_followup_action")
            if isinstance(context.metadata.get("question_followup_action"), dict)
            else None
        )
        semantic_router_mode = str(context.metadata.get("semantic_router_mode") or "").strip().lower()
        selected_mode = str(context.metadata.get("selected_mode") or "").strip().lower()
        allow_legacy_followup_fallback = semantic_router_mode != "primary"
        next_action = str(turn_semantic_decision.get("next_action") or "").strip()
        raw_user_message = str(
            context.metadata.get("raw_user_message") or context.user_message or ""
        ).strip()
        if (
            not force_generate_questions
            and isinstance(followup_question_context, dict)
            and followup_question_context.get(
            "question"
            )
            and next_action != "route_to_generation"
        ):
            should_resolve_submission = (
                (next_action == "route_to_grading" and followup_action is None)
                or (not next_action and allow_legacy_followup_fallback)
            )
            if should_resolve_submission:
                target_context, submission = resolve_submission_attempt(
                    raw_user_message,
                    followup_question_context,
                )
                if target_context and submission:
                    followup_question_context = target_context
                    followup_action = self._followup_action_from_submission(submission)
                    next_action = "route_to_grading"
            action_context = None
            if next_action == "route_to_grading":
                action_context = apply_followup_action_to_context(
                    followup_question_context,
                    followup_action,
                )
            if action_context is not None:
                authority_source = ""
                correct_answer_present = True
                if _is_mcq_grading_context(action_context):
                    (
                        action_context,
                        authority_source,
                        correct_answer_present,
                    ) = _recover_missing_mcq_authority(action_context, context.metadata)
                    if not correct_answer_present:
                        blocked_context = _clear_blocked_grading_state(action_context)
                        await self._emit_missing_mcq_authority_result(
                            stream=stream,
                            blocked_context=blocked_context,
                            turn_id=turn_id,
                            active_object=active_object,
                            suspended_object_stack=suspended_object_stack,
                            turn_semantic_decision=turn_semantic_decision,
                            user_message=raw_user_message,
                        )
                        return

                from deeptutor.agents.question.agents.submission_grader_agent import (
                    SubmissionGraderAgent,
                )

                if (action_context.get("items") or []) and len(action_context.get("items") or []) > 1:
                    graded_context = self._build_batch_submission_context(
                        action_context,
                        None,
                    )
                else:
                    graded_context = self._build_submission_context(
                        action_context,
                        str(action_context.get("user_answer") or "").strip(),
                        raw_submission=raw_user_message,
                    )
                async with stream.stage("generation", source=self.name):
                    if _should_use_deterministic_grading_feedback(
                        selected_mode=selected_mode,
                        question_context=graded_context,
                    ):
                        answer = _render_deterministic_grading_feedback(graded_context)
                    else:
                        agent = SubmissionGraderAgent(
                            language=context.language,
                            api_key=llm_config.api_key,
                            base_url=llm_config.base_url,
                            api_version=llm_config.api_version,
                        )
                        agent.set_trace_callback(self._build_trace_bridge(stream))
                        answer = await agent.process(
                            user_message=raw_user_message,
                            question_context=graded_context,
                            history_context=str(
                                context.metadata.get("conversation_context_text", "") or ""
                            ).strip(),
                        )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_active_object = build_active_object_from_question_context(
                        graded_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    result_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "grading",
                        "question_id": graded_context.get("question_id", ""),
                        "user_answer": graded_context.get("user_answer", ""),
                        "is_correct": graded_context.get("is_correct"),
                        "question_followup_context": normalize_question_followup_context(
                            graded_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_grading",
                            active_object=result_active_object or active_object,
                            question_context=graded_context,
                            user_message=raw_user_message,
                        ),
                        **_mcq_trace_fields(
                            graded_context,
                            authority_source=authority_source,
                            correct_answer_present=correct_answer_present,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        result_payload["metadata"] = {"cost_summary": cost_meta}
                    grading_result = graded_context.get("construction_grading_result")
                    if isinstance(grading_result, dict) and grading_result:
                        _write_grading_error_events_for_context(
                            context=context,
                            graded_context=graded_context,
                            source_id=f"{turn_id}:{graded_context.get('question_id') or 'grading'}",
                        )
                        result_payload["construction_grading_result"] = grading_result
                    await stream.result(result_payload, source=self.name)
                return

            if next_action == "route_to_followup_explainer":
                async with stream.stage("generation", source=self.name):
                    if _should_render_deterministic_reference_feedback(
                        context.user_message,
                        followup_question_context,
                    ):
                        answer = _render_deterministic_reference_feedback(
                            followup_question_context
                        )
                    else:
                        from deeptutor.agents.question.agents.followup_agent import FollowupAgent

                        agent = FollowupAgent(
                            language=context.language,
                            api_key=llm_config.api_key,
                            base_url=llm_config.base_url,
                            api_version=llm_config.api_version,
                        )
                        agent.set_trace_callback(self._build_trace_bridge(stream))
                        answer = await agent.process(
                            user_message=context.user_message,
                            question_context=followup_question_context,
                            history_context=str(
                                context.metadata.get("conversation_context_text", "") or ""
                            ).strip(),
                        )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

            if allow_legacy_followup_fallback and self._prefer_followup_without_semantic_decision(
                turn_semantic_decision=turn_semantic_decision,
                followup_action=followup_action,
                question_context=followup_question_context,
                user_message=context.user_message,
            ):
                async with stream.stage("generation", source=self.name):
                    if _should_render_deterministic_reference_feedback(
                        context.user_message,
                        followup_question_context,
                    ):
                        answer = _render_deterministic_reference_feedback(
                            followup_question_context
                        )
                    else:
                        from deeptutor.agents.question.agents.followup_agent import FollowupAgent

                        agent = FollowupAgent(
                            language=context.language,
                            api_key=llm_config.api_key,
                            base_url=llm_config.base_url,
                            api_version=llm_config.api_version,
                        )
                        agent.set_trace_callback(self._build_trace_bridge(stream))
                        answer = await agent.process(
                            user_message=context.user_message,
                            question_context=followup_question_context,
                            history_context=str(
                                context.metadata.get("conversation_context_text", "") or ""
                            ).strip(),
                        )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

            if allow_legacy_followup_fallback:
                target_context, submission = resolve_submission_attempt(
                    raw_user_message,
                    followup_question_context,
                )
                if target_context and submission:
                    if submission.get("kind") == "batch":
                        action_context = self._build_batch_submission_context(
                            target_context,
                            submission.get("answers"),
                        )
                    else:
                        user_answer = str(submission.get("answer") or "").strip()
                        action_context = self._build_submission_context(
                            target_context,
                            user_answer,
                            raw_submission=raw_user_message,
                        )
                    authority_source = ""
                    correct_answer_present = True
                    if _is_mcq_grading_context(action_context):
                        (
                            recovered_context,
                            authority_source,
                            correct_answer_present,
                        ) = _recover_missing_mcq_authority(action_context, context.metadata)
                        if not correct_answer_present:
                            blocked_context = _clear_blocked_grading_state(recovered_context)
                            await self._emit_missing_mcq_authority_result(
                                stream=stream,
                                blocked_context=blocked_context,
                                turn_id=turn_id,
                                active_object=active_object,
                                suspended_object_stack=suspended_object_stack,
                                turn_semantic_decision=turn_semantic_decision,
                                user_message=raw_user_message,
                            )
                            return
                        if submission.get("kind") == "batch":
                            graded_context = self._build_batch_submission_context(
                                recovered_context,
                                None,
                            )
                        else:
                            graded_context = self._build_submission_context(
                                recovered_context,
                                str(recovered_context.get("user_answer") or "").strip(),
                                raw_submission=raw_user_message,
                            )
                    else:
                        graded_context = action_context

                    from deeptutor.agents.question.agents.submission_grader_agent import (
                        SubmissionGraderAgent,
                    )
                    async with stream.stage("generation", source=self.name):
                        if _should_use_deterministic_grading_feedback(
                            selected_mode=selected_mode,
                            question_context=graded_context,
                        ):
                            answer = _render_deterministic_grading_feedback(graded_context)
                        else:
                            agent = SubmissionGraderAgent(
                                language=context.language,
                                api_key=llm_config.api_key,
                                base_url=llm_config.base_url,
                                api_version=llm_config.api_version,
                            )
                            agent.set_trace_callback(self._build_trace_bridge(stream))
                            answer = await agent.process(
                                user_message=raw_user_message,
                                question_context=graded_context,
                                history_context=str(
                                    context.metadata.get("conversation_context_text", "") or ""
                                ).strip(),
                            )
                        if answer:
                            await stream.content(answer, source=self.name, stage="generation")
                        result_active_object = build_active_object_from_question_context(
                            graded_context,
                            source_turn_id=turn_id,
                            previous_active_object=active_object,
                        )
                        result_payload: dict[str, Any] = {
                            "response": answer or "",
                            "mode": "grading",
                            "question_id": graded_context.get("question_id", ""),
                            "user_answer": graded_context.get("user_answer", ""),
                            "is_correct": graded_context.get("is_correct"),
                            "question_followup_context": normalize_question_followup_context(
                                graded_context
                            )
                            or {},
                            "active_object": result_active_object or {},
                            "suspended_object_stack": suspended_object_stack,
                            "turn_semantic_decision": turn_semantic_decision
                            or self._default_turn_semantic_decision(
                                next_action="route_to_grading",
                                active_object=result_active_object or active_object,
                                question_context=graded_context,
                                user_message=raw_user_message,
                            ),
                            **_mcq_trace_fields(
                                graded_context,
                                authority_source=authority_source,
                                correct_answer_present=correct_answer_present,
                            ),
                        }
                        cost_meta = self._collect_cost_summary("question")
                        if cost_meta:
                            result_payload["metadata"] = {"cost_summary": cost_meta}
                        grading_result = graded_context.get("construction_grading_result")
                        if isinstance(grading_result, dict) and grading_result:
                            _write_grading_error_events_for_context(
                                context=context,
                                graded_context=graded_context,
                                source_id=f"{turn_id}:{graded_context.get('question_id') or 'grading'}",
                            )
                            result_payload["construction_grading_result"] = grading_result
                        await stream.result(result_payload, source=self.name)
                    return

                async with stream.stage("generation", source=self.name):
                    if _should_render_deterministic_reference_feedback(
                        context.user_message,
                        followup_question_context,
                    ):
                        answer = _render_deterministic_reference_feedback(
                            followup_question_context
                        )
                    else:
                        from deeptutor.agents.question.agents.followup_agent import FollowupAgent

                        agent = FollowupAgent(
                            language=context.language,
                            api_key=llm_config.api_key,
                            base_url=llm_config.base_url,
                            api_version=llm_config.api_version,
                        )
                        agent.set_trace_callback(self._build_trace_bridge(stream))
                        answer = await agent.process(
                            user_message=context.user_message,
                            question_context=followup_question_context,
                            history_context=str(
                                context.metadata.get("conversation_context_text", "") or ""
                            ).strip(),
                        )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

        mode = str(overrides.get("mode", "custom") or "custom").strip().lower()
        raw_topic = str(overrides.get("topic") or context.user_message or "").strip()
        topic = _resolve_generation_topic(
            raw_topic=raw_topic,
            active_object=active_object,
            suspended_object_stack=suspended_object_stack,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
            conversation_context_text="\n\n".join(
                part
                for part in [
                    str(context.metadata.get("conversation_context_text", "") or "").strip(),
                    str(context.memory_context or "").strip(),
                ]
                if part
            ),
        )
        num_questions = int(overrides.get("num_questions", 1) or 1)
        difficulty = str(overrides.get("difficulty", "") or "")
        question_type = str(overrides.get("question_type", "") or "")
        preference = str(overrides.get("preference", "") or "")
        reveal_answers = bool(overrides.get("reveal_answers", False))
        reveal_explanations = bool(overrides.get("reveal_explanations", reveal_answers))
        lightweight_generation = bool(overrides.get("lightweight_generation", False))
        lightweight_followup_generation = _should_use_lightweight_followup_generation(
            selected_mode=selected_mode,
            raw_topic=raw_topic,
            num_questions=num_questions,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
        )
        lightweight_topic_generation = _should_use_lightweight_topic_generation(
            selected_mode=selected_mode,
            raw_topic=raw_topic,
            resolved_topic=topic,
            num_questions=num_questions,
            question_type=question_type,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
        )
        lightweight_generation = (
            lightweight_generation
            or lightweight_followup_generation
            or lightweight_topic_generation
        )
        require_explanation = reveal_explanations
        history_context = str(
            context.metadata.get("conversation_context_text", "") or ""
        ).strip()
        enabled_tools = set(
            self.manifest.tools_used
            if context.enabled_tools is None
            else context.enabled_tools
        )
        if lightweight_followup_generation or lightweight_topic_generation:
            tool_flags_override = {
                "rag": False,
                "web_search": False,
                "code_execution": False,
            }
        else:
            tool_flags_override = {
                "rag": "rag" in enabled_tools,
                "web_search": "web_search" in enabled_tools,
                "code_execution": "code_execution" in enabled_tools,
            }

        coordinator = AgentCoordinator(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            api_version=llm_config.api_version,
            kb_name=kb_name,
            language=context.language,
            output_dir=str(output_dir),
            tool_flags_override=tool_flags_override,
            enable_idea_rag="rag" in enabled_tools,
        )

        _trace_bridge = self._build_trace_bridge(stream)

        # Bridge ws_callback to StreamBus
        async def _ws_bridge(update: dict[str, Any]) -> None:
            update_type = update.get("type", "")
            inner = str(update.get("stage", "") or "")
            if update_type == "result" or inner in {"generation", "complete"}:
                stage = "generation"
            elif inner in {"parsing", "extracting", "ideation"}:
                stage = "ideation"
            else:
                stage = "generation" if update_type == "question_update" else "ideation"
            message = self._format_bridge_message(update_type, update)
            metadata = {
                key: value
                for key, value in update.items()
                if key not in {"type", "message"}
            }
            if "question_id" in update:
                metadata.setdefault("trace_id", str(update.get("question_id")))
                metadata.setdefault(
                    "label",
                    f"Generate {self._humanize_question_id(update.get('question_id'))}",
                )
            elif "batch" in update:
                metadata.setdefault("trace_id", f"batch-{update.get('batch')}")
                metadata.setdefault("label", f"Batch {update.get('batch')}")
            metadata["update_type"] = update_type
            metadata.setdefault("phase", stage)
            await stream.progress(
                message=message,
                source=self.name,
                stage=stage,
                metadata=merge_trace_metadata(metadata, {"trace_kind": "progress"}),
            )

        coordinator.set_ws_callback(_ws_bridge)
        if hasattr(coordinator, "set_trace_callback"):
            coordinator.set_trace_callback(_trace_bridge)

        if mode == "mimic":
            result = await self._run_mimic_mode(
                coordinator=coordinator,
                context=context,
                stream=stream,
                overrides=overrides,
            )
            if not result:
                return
        else:
            if not topic:
                await stream.error("Topic is required for custom question generation.", source=self.name)
                return

            async with stream.stage("ideation", source=self.name):
                await stream.thinking("Generating question templates...", source=self.name, stage="ideation")

            if _should_use_followup_anchor_generation(
                raw_topic=raw_topic,
                mode=mode,
                num_questions=num_questions,
                followup_question_context=(
                    followup_question_context if isinstance(followup_question_context, dict) else None
                ),
            ):
                result = await coordinator.generate_from_followup_context(
                    user_topic=topic,
                    preference=preference,
                    num_questions=num_questions,
                    followup_question_context=followup_question_context,
                    difficulty=difficulty,
                    question_type=question_type,
                    history_context=history_context,
                    require_explanation=require_explanation,
                    lightweight_generation=lightweight_followup_generation,
                )
            else:
                result = await coordinator.generate_from_topic(
                    user_topic=topic,
                    preference=preference,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    question_type=question_type,
                    history_context=history_context,
                    lightweight_generation=lightweight_generation,
                    require_explanation=require_explanation,
                )

        content = self._render_summary_markdown(
            result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
        )
        if content:
            await stream.content(content, source=self.name, stage="generation")

        presentation = build_canonical_presentation(
            content=content or "",
            result_summary=result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
        )
        result_payload: dict[str, Any] = {
            "response": content or "No questions generated.",
            "mode": mode,
            "question_followup_context": (
                build_question_followup_context_from_result_summary(
                    result,
                    content or "",
                    reveal_answers=reveal_answers,
                    reveal_explanations=reveal_explanations,
                )
                or build_question_followup_context_from_presentation(
                    presentation,
                    content or "",
                    reveal_answers=reveal_answers,
                    reveal_explanations=reveal_explanations,
                )
                or {}
            ),
        }
        result_payload["active_object"] = (
            build_active_object_from_question_context(
                result_payload["question_followup_context"],
                source_turn_id=turn_id,
                previous_active_object=active_object,
            )
            or {}
        )
        result_payload["turn_semantic_decision"] = turn_semantic_decision or self._default_turn_semantic_decision(
            next_action="route_to_generation",
            active_object=result_payload["active_object"] or active_object,
            question_context=result_payload["question_followup_context"],
            user_message=context.user_message,
        )
        transitioned_active_object, transitioned_stack = apply_active_object_transition(
            previous_active_object=active_object,
            previous_suspended_object_stack=suspended_object_stack,
            turn_semantic_decision=result_payload["turn_semantic_decision"],
            resolved_active_object=result_payload["active_object"],
        )
        result_payload["active_object"] = transitioned_active_object or {}
        result_payload["suspended_object_stack"] = transitioned_stack
        if presentation:
            result_payload["presentation"] = presentation
        cost_meta = self._collect_cost_summary("question")
        if cost_meta:
            result_payload["metadata"] = {"cost_summary": cost_meta}
        await stream.result(result_payload, source=self.name)

    async def _emit_missing_mcq_authority_result(
        self,
        *,
        stream: StreamBus,
        blocked_context: dict[str, Any],
        turn_id: str,
        active_object: dict[str, Any] | None,
        suspended_object_stack: list[dict[str, Any]] | None,
        turn_semantic_decision: dict[str, Any] | None,
        user_message: str,
    ) -> None:
        answer = _render_missing_mcq_authority_feedback()
        await stream.content(answer, source=self.name, stage="generation")
        result_active_object = build_active_object_from_question_context(
            blocked_context,
            source_turn_id=turn_id,
            previous_active_object=active_object,
        )
        await stream.result(
            {
                "response": answer,
                "mode": "grading",
                "grading_blocked": True,
                "question_id": blocked_context.get("question_id", ""),
                "user_answer": blocked_context.get("user_answer", ""),
                "is_correct": None,
                "question_followup_context": normalize_question_followup_context(blocked_context)
                or {},
                "active_object": result_active_object or {},
                "suspended_object_stack": suspended_object_stack,
                "turn_semantic_decision": turn_semantic_decision
                or self._default_turn_semantic_decision(
                    next_action="route_to_grading",
                    active_object=result_active_object or active_object,
                    question_context=blocked_context,
                    user_message=user_message,
                ),
                **_mcq_trace_fields(
                    blocked_context,
                    authority_source="missing",
                    correct_answer_present=False,
                ),
            },
            source=self.name,
        )

    @staticmethod
    def _followup_action_from_submission(submission: dict[str, Any]) -> dict[str, Any]:
        if submission.get("kind") == "batch":
            return {
                "intent": "answer_questions",
                "answers": submission.get("answers") or [],
            }
        return {
            "intent": "answer_questions",
            "answers": [
                {
                    "question_id": submission.get("question_id", ""),
                    "answer": str(submission.get("answer") or "").strip(),
                }
            ],
        }

    async def _prepare_grading_context_or_emit_blocked(
        self,
        *,
        stream: StreamBus,
        action_context: dict[str, Any],
        metadata: dict[str, Any],
        turn_id: str,
        active_object: dict[str, Any] | None,
        suspended_object_stack: list[dict[str, Any]] | None,
        turn_semantic_decision: dict[str, Any] | None,
        raw_user_message: str,
    ) -> tuple[dict[str, Any], str, bool] | None:
        authority_source = ""
        correct_answer_present = True
        working_context = action_context
        if _is_mcq_grading_context(working_context):
            (
                working_context,
                authority_source,
                correct_answer_present,
            ) = _recover_missing_mcq_authority(working_context, metadata)
            if not correct_answer_present:
                blocked_context = _clear_blocked_grading_state(working_context)
                await self._emit_missing_mcq_authority_result(
                    stream=stream,
                    blocked_context=blocked_context,
                    turn_id=turn_id,
                    active_object=active_object,
                    suspended_object_stack=suspended_object_stack,
                    turn_semantic_decision=turn_semantic_decision,
                    user_message=raw_user_message,
                )
                return None

        if (working_context.get("items") or []) and len(working_context.get("items") or []) > 1:
            graded_context = self._build_batch_submission_context(
                working_context,
                None,
            )
        else:
            graded_context = self._build_submission_context(
                working_context,
                str(working_context.get("user_answer") or "").strip(),
                raw_submission=raw_user_message,
            )
        return graded_context, authority_source, correct_answer_present

    async def _emit_grading_result(
        self,
        *,
        stream: StreamBus,
        context: UnifiedContext,
        llm_config: Any,
        turn_id: str,
        active_object: dict[str, Any] | None,
        suspended_object_stack: list[dict[str, Any]] | None,
        turn_semantic_decision: dict[str, Any] | None,
        graded_context: dict[str, Any],
        raw_user_message: str,
        selected_mode: str,
        authority_source: str,
        correct_answer_present: bool,
    ) -> None:
        async with stream.stage("generation", source=self.name):
            if _should_use_deterministic_grading_feedback(
                selected_mode=selected_mode,
                question_context=graded_context,
            ):
                answer = _render_deterministic_grading_feedback(graded_context)
            else:
                from deeptutor.agents.question.agents.submission_grader_agent import (
                    SubmissionGraderAgent,
                )

                agent = SubmissionGraderAgent(
                    language=context.language,
                    api_key=llm_config.api_key,
                    base_url=llm_config.base_url,
                    api_version=llm_config.api_version,
                )
                agent.set_trace_callback(self._build_trace_bridge(stream))
                answer = await agent.process(
                    user_message=raw_user_message,
                    question_context=graded_context,
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )
            if answer:
                await stream.content(answer, source=self.name, stage="generation")
            result_active_object = build_active_object_from_question_context(
                graded_context,
                source_turn_id=turn_id,
                previous_active_object=active_object,
            )
            result_payload: dict[str, Any] = {
                "response": answer or "",
                "mode": "grading",
                "question_id": graded_context.get("question_id", ""),
                "user_answer": graded_context.get("user_answer", ""),
                "is_correct": graded_context.get("is_correct"),
                "question_followup_context": normalize_question_followup_context(
                    graded_context
                )
                or {},
                "active_object": result_active_object or {},
                "suspended_object_stack": suspended_object_stack,
                "turn_semantic_decision": turn_semantic_decision
                or self._default_turn_semantic_decision(
                    next_action="route_to_grading",
                    active_object=result_active_object or active_object,
                    question_context=graded_context,
                    user_message=raw_user_message,
                ),
                **_mcq_trace_fields(
                    graded_context,
                    authority_source=authority_source,
                    correct_answer_present=correct_answer_present,
                ),
            }
            cost_meta = self._collect_cost_summary("question")
            if cost_meta:
                result_payload["metadata"] = {"cost_summary": cost_meta}
            grading_result = graded_context.get("construction_grading_result")
            if isinstance(grading_result, dict) and grading_result:
                _write_grading_error_events_for_context(
                    context=context,
                    graded_context=graded_context,
                    source_id=f"{turn_id}:{graded_context.get('question_id') or 'grading'}",
                )
                result_payload["construction_grading_result"] = grading_result
            await stream.result(result_payload, source=self.name)

    async def _emit_followup_result(
        self,
        *,
        stream: StreamBus,
        context: UnifiedContext,
        llm_config: Any,
        turn_id: str,
        active_object: dict[str, Any] | None,
        suspended_object_stack: list[dict[str, Any]] | None,
        turn_semantic_decision: dict[str, Any] | None,
        followup_question_context: dict[str, Any],
        force_default_decision: bool = False,
    ) -> None:
        async with stream.stage("generation", source=self.name):
            if _should_render_deterministic_reference_feedback(
                context.user_message,
                followup_question_context,
            ):
                answer = _render_deterministic_reference_feedback(
                    followup_question_context
                )
            else:
                from deeptutor.agents.question.agents.followup_agent import FollowupAgent

                agent = FollowupAgent(
                    language=context.language,
                    api_key=llm_config.api_key,
                    base_url=llm_config.base_url,
                    api_version=llm_config.api_version,
                )
                agent.set_trace_callback(self._build_trace_bridge(stream))
                answer = await agent.process(
                    user_message=context.user_message,
                    question_context=followup_question_context,
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )
            if answer:
                await stream.content(answer, source=self.name, stage="generation")
            result_active_object = build_active_object_from_question_context(
                followup_question_context,
                source_turn_id=turn_id,
                previous_active_object=active_object,
            )
            default_decision = self._default_turn_semantic_decision(
                next_action="route_to_followup_explainer",
                active_object=result_active_object or active_object,
                question_context=followup_question_context,
                user_message=context.user_message,
            )
            followup_payload: dict[str, Any] = {
                "response": answer or "",
                "mode": "followup",
                "question_id": followup_question_context.get("question_id", ""),
                "question_followup_context": normalize_question_followup_context(
                    followup_question_context
                )
                or {},
                "active_object": result_active_object or {},
                "suspended_object_stack": suspended_object_stack,
                "turn_semantic_decision": (
                    default_decision
                    if force_default_decision
                    else turn_semantic_decision or default_decision
                ),
            }
            cost_meta = self._collect_cost_summary("question")
            if cost_meta:
                followup_payload["metadata"] = {"cost_summary": cost_meta}
            await stream.result(followup_payload, source=self.name)

    @staticmethod
    def _default_turn_semantic_decision(
        *,
        next_action: str,
        active_object: dict[str, Any] | None,
        question_context: dict[str, Any] | None,
        user_message: str,
    ) -> dict[str, Any]:
        items = (question_context or {}).get("items") or []
        if next_action == "route_to_grading":
            relation = (
                "revise_answer_on_active_object"
                if any(marker in str(user_message or "") for marker in ("改", "更正", "修正", "订正"))
                else "answer_active_object"
            )
            allowed_patch = "append_answer_slots" if len(items) > 1 else "update_answer_slot"
            reason = "deep_question 按当前 active object 完成答题/批改。"
        elif next_action == "route_to_followup_explainer":
            relation = "ask_about_active_object"
            allowed_patch = "no_state_change"
            reason = "deep_question 按当前 active object 完成题目追问解释。"
        else:
            relation = (
                "continue_same_learning_flow" if active_object is not None else "switch_to_new_object"
            )
            allowed_patch = "set_active_object"
            reason = "deep_question 生成了新的题目对象并更新 active object。"
        return build_turn_semantic_decision(
            relation_to_active_object=relation,
            next_action=next_action,
            allowed_patch=allowed_patch,
            confidence=1.0,
            reason=reason,
            active_object=active_object,
        )

    @staticmethod
    def _prefer_followup_without_semantic_decision(
        *,
        turn_semantic_decision: dict[str, Any] | None,
        followup_action: dict[str, Any] | None,
        question_context: dict[str, Any] | None,
        user_message: str,
    ) -> bool:
        if turn_semantic_decision or followup_action:
            return False
        if not isinstance(question_context, dict) or not question_context.get("question"):
            return False
        if not (
            question_context.get("user_answer")
            or question_context.get("is_correct") is not None
            or question_context.get("explanation")
        ):
            return False
        text = str(user_message or "").strip().lower()
        if not text:
            return False
        followup_markers = (
            "why",
            "wrong",
            "explain",
            "because",
            "?",
            "为什么",
            "错在哪",
            "解析",
            "讲解",
            "思路",
            "哪里不对",
        )
        return any(marker in text for marker in followup_markers)

    @staticmethod
    def _build_submission_context(
        question_context: dict[str, Any],
        user_answer: str,
        *,
        raw_submission: str = "",
    ) -> dict[str, Any]:
        graded_context = dict(question_context)
        correct_answer = str(question_context.get("correct_answer", "") or "").strip()
        is_correct = answers_match(user_answer, correct_answer, graded_context)
        graded_context["user_answer"] = str(user_answer or "").strip()
        graded_context["is_correct"] = is_correct
        graded_context["score"] = 100 if is_correct else 0
        graded_context["diagnosis"] = DeepQuestionCapability._diagnose_choice_submission(
            question_context=question_context,
            user_answer=user_answer,
            raw_submission=raw_submission,
        )
        return attach_deep_question_grading_result(graded_context)

    @staticmethod
    def _build_batch_submission_context(
        question_context: dict[str, Any],
        answers: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        graded_context = dict(question_context)
        if answers:
            graded_context = apply_followup_action_to_context(
                question_context,
                {
                    "intent": "answer_questions",
                    "answers": answers,
                    "preserve_other_answers": False,
                },
            ) or dict(question_context)
        items = graded_context.get("items") or []
        correct_count = sum(1 for item in items if isinstance(item, dict) and item.get("is_correct") is True)
        total_count = len(items)
        graded_context["score"] = int((correct_count / total_count) * 100) if total_count else 0
        if total_count and correct_count == total_count:
            graded_context["diagnosis"] = "CORRECT"
        elif correct_count:
            graded_context["diagnosis"] = "PARTIAL"
        else:
            graded_context["diagnosis"] = "CONFUSION"
        return attach_deep_question_grading_result(graded_context)

    @staticmethod
    def _diagnose_choice_submission(
        *,
        question_context: dict[str, Any],
        user_answer: str,
        raw_submission: str = "",
    ) -> str:
        correct_answer = str(question_context.get("correct_answer", "") or "").strip().upper()
        normalized_answer = str(user_answer or "").strip().upper()
        if not normalized_answer:
            return "INVALID"
        if not correct_answer:
            return "INVALID"
        if answers_match(normalized_answer, correct_answer, question_context):
            return "CORRECT"
        if normalized_answer not in {"A", "B", "C", "D"} and correct_answer not in {"A", "B", "C", "D"}:
            return "CONFUSION"

        raw_text = str(raw_submission or "").strip().lower()
        if any(marker in raw_text for marker in ("手滑", "看错", "粗心", "点错", "写错")):
            return "SLIP"

        combined = " ".join(
            str(question_context.get(key, "") or "")
            for key in ("question", "explanation", "knowledge_context", "concentration")
        ).lower()

        negative_stem_markers = (
            "不应",
            "不宜",
            "不得",
            "不能",
            "错误",
            "不正确",
            "除外",
            "不属于",
            "不是",
            "严禁",
        )
        has_numeric_signal = bool(
            re.search(r"\d+(?:\.\d+)?\s*(?:%|‰|℃|mm|cm|m|km|kg|kN|MPa|d|h|min|天|小时|分钟|万元|元)", combined)
            or re.search(r"第[一二三四五六七八九十0-9]+", combined)
        )
        calc_markers = (
            "计算",
            "合计",
            "总工期",
            "持续时间",
            "流水节拍",
            "流水步距",
            "费用",
            "金额",
            "面积",
            "体积",
            "概率",
            "比率",
            "产值",
        )
        if has_numeric_signal and any(marker in combined for marker in calc_markers):
            return "CALC_ERROR"
        if has_numeric_signal:
            return "MEMORY_DECAY"
        if any(marker in combined for marker in negative_stem_markers):
            return "OVERSIGHT"
        return "CONFUSION"

    @staticmethod
    def _collect_cost_summary(module_name: str) -> dict[str, Any] | None:
        from deeptutor.agents.base_agent import BaseAgent
        stats = BaseAgent._shared_stats.get(module_name)
        if not stats or not stats.calls:
            return None
        s = stats.get_summary()
        stats.reset()
        return {
            "total_cost_usd": s.get("cost_usd", 0),
            "total_tokens": s.get("total_tokens", 0),
            "total_calls": s.get("calls", 0),
        }

    async def _run_mimic_mode(
        self,
        coordinator,
        context: UnifiedContext,
        stream: StreamBus,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        paper_path = str(overrides.get("paper_path", "") or "").strip()
        max_questions = int(overrides.get("max_questions", 10) or 10)
        pdf_attachment = next(
            (
                attachment
                for attachment in context.attachments
                if attachment.filename.lower().endswith(".pdf")
                or attachment.type == "pdf"
                or attachment.mime_type == "application/pdf"
            ),
            None,
        )

        if pdf_attachment and pdf_attachment.base64:
            async with stream.stage("ideation", source=self.name):
                await stream.thinking(
                    "Parsing uploaded exam paper and extracting templates...",
                    source=self.name,
                    stage="ideation",
                )

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp_pdf:
                temp_pdf.write(base64.b64decode(pdf_attachment.base64))
                temp_pdf.flush()
                return await coordinator.generate_from_exam(
                    exam_paper_path=temp_pdf.name,
                    max_questions=max_questions,
                    paper_mode="upload",
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )

        if paper_path:
            async with stream.stage("ideation", source=self.name):
                await stream.thinking(
                    "Loading parsed exam paper and extracting templates...",
                    source=self.name,
                    stage="ideation",
                )
            return await coordinator.generate_from_exam(
                exam_paper_path=paper_path,
                max_questions=max_questions,
                paper_mode="parsed",
                history_context=str(
                    context.metadata.get("conversation_context_text", "") or ""
                ).strip(),
            )

        await stream.error(
            "Mimic mode requires either an uploaded PDF or a parsed exam directory.",
            source=self.name,
        )
        return {}

    @staticmethod
    def _format_bridge_message(update_type: str, update: dict[str, Any]) -> str:
        """Build a human-readable progress line from a coordinator ws_callback."""
        if update_type == "progress":
            stage = update.get("stage", "")
            status = update.get("status", "")
            cur = update.get("current", "")
            tot = update.get("total", "")
            qid = update.get("question_id", "")
            batch = update.get("batch", "")
            parts = [f"[{stage}]" if stage else ""]
            if status:
                parts.append(status)
            if cur != "" and tot:
                parts.append(f"({cur}/{tot})")
            if batch:
                parts.append(f"batch={batch}")
            if qid:
                parts.append(f"question={qid}")
            return " ".join(p for p in parts if p) or update_type

        if update_type == "templates_ready":
            count = update.get("count", 0)
            batch = update.get("batch", "")
            templates = update.get("templates", [])
            prefix = f"Templates ready (batch {batch}): {count}" if batch else f"Templates ready: {count}"
            lines = [prefix]
            for t in templates:
                if isinstance(t, dict):
                    lines.append(
                        f"  [{t.get('question_id','')}] {t.get('concentration','')[:80]} "
                        f"({t.get('question_type','')}/{t.get('difficulty','')})"
                    )
            return "\n".join(lines)

        if update_type == "question_update":
            qid = DeepQuestionCapability._humanize_question_id(update.get("question_id", ""))
            current = update.get("current", "")
            total = update.get("total", "")
            return f"Generating {qid} ({current}/{total})"

        if update_type == "result":
            qid = DeepQuestionCapability._humanize_question_id(update.get("question_id", ""))
            idx = update.get("index", "")
            q = update.get("question", {})
            qt = q.get("question_type", "") if isinstance(q, dict) else ""
            diff = q.get("difficulty", "") if isinstance(q, dict) else ""
            success = update.get("success", True)
            ordinal = ""
            if isinstance(idx, int):
                ordinal = f"#{idx + 1}, "
            return f"{qid} done ({ordinal}{qt}/{diff}, success={success})"

        return update.get("message", update_type)

    @staticmethod
    def _humanize_question_id(question_id: Any) -> str:
        raw = str(question_id or "").strip()
        match = re.fullmatch(r"q_(\d+)", raw.lower())
        if match:
            return f"Question {match.group(1)}"
        return raw or "Question"

    def _render_summary_markdown(
        self,
        summary: dict[str, Any],
        *,
        reveal_answers: bool = False,
        reveal_explanations: bool = False,
    ) -> str:
        results = summary.get("results", []) if isinstance(summary, dict) else []
        if not results:
            return ""

        lines: list[str] = []
        for idx, item in enumerate(results, 1):
            qa_pair = item.get("qa_pair", {}) if isinstance(item, dict) else {}
            question = qa_pair.get("question", "")
            if not question:
                continue

            lines.append(f"### Question {idx}\n")
            lines.append(question)

            options = qa_pair.get("options", {})
            if isinstance(options, dict) and options:
                for key, value in options.items():
                    lines.append(f"- {key}. {value}")

            answer = qa_pair.get("correct_answer", "")
            if reveal_answers and answer:
                lines.append(f"\n**Answer:** {answer}")

            explanation = qa_pair.get("explanation", "")
            if reveal_explanations and explanation:
                lines.append(f"\n**Explanation:** {explanation}")

            lines.append("")

        return "\n".join(lines).strip()

    def _build_trace_bridge(self, stream: StreamBus):
        async def _trace_bridge(update: dict[str, Any]) -> None:
            event = str(update.get("event", "") or "")
            stage = str(update.get("phase") or update.get("stage") or "generation")
            base_metadata = {
                key: value
                for key, value in update.items()
                if key
                not in {"event", "state", "response", "chunk", "result", "tool_name", "tool_args"}
            }

            if event == "llm_call":
                state = str(update.get("state", "running"))
                label = str(update.get("label", "") or "")
                if state == "running":
                    await stream.progress(
                        message=label,
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "running"},
                        ),
                    )
                    return
                if state == "streaming":
                    chunk = str(update.get("chunk", "") or "")
                    if chunk:
                        await stream.thinking(
                            chunk,
                            source=self.name,
                            stage=stage,
                            metadata=merge_trace_metadata(
                                base_metadata,
                                {"trace_kind": "llm_chunk"},
                            ),
                        )
                    return
                if state == "complete":
                    was_streaming = update.get("streaming", False)
                    if not was_streaming:
                        response = str(update.get("response", "") or "")
                        if response:
                            await stream.thinking(
                                response,
                                source=self.name,
                                stage=stage,
                                metadata=merge_trace_metadata(
                                    base_metadata,
                                    {"trace_kind": "llm_output"},
                                ),
                            )
                    await stream.progress(
                        message="",
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "complete"},
                        ),
                    )
                    return
                if state == "error":
                    await stream.error(
                        str(update.get("response", "") or "LLM call failed."),
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "error"},
                        ),
                    )
                    return

            if event == "tool_call":
                await stream.tool_call(
                    tool_name=str(update.get("tool_name", "") or "tool"),
                    args=update.get("tool_args", {}) or {},
                    source=self.name,
                    stage=stage,
                    metadata=merge_trace_metadata(
                        base_metadata,
                        {"trace_kind": "tool_call"},
                    ),
                )
                return

            if event == "tool_result":
                state = str(update.get("state", "complete"))
                result = str(update.get("result", "") or "")
                if state == "error":
                    await stream.error(
                        result,
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "tool_result"},
                        ),
                    )
                    return
                await stream.tool_result(
                    tool_name=str(update.get("tool_name", "") or "tool"),
                    result=result,
                    source=self.name,
                    stage=stage,
                    metadata=merge_trace_metadata(
                        base_metadata,
                        {"trace_kind": "tool_result"},
                    ),
                )

        return _trace_bridge
