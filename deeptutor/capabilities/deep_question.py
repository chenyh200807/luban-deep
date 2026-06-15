"""
Deep Question Capability
========================

Multi-agent question generation pipeline: Idea -> Evaluate -> Generate -> Validate.
Wraps the existing ``AgentCoordinator``.
"""

from __future__ import annotations

import base64
import functools
import re
import tempfile
from typing import Any

from loguru import logger

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.trace import merge_trace_metadata
from deeptutor.services.citations import (
    CitationPolicy,
    answer_citations_enabled,
    apply_answer_citation_metadata,
)
from deeptutor.services.construction_grading.deep_question_adapter import (
    attach_deep_question_grading_result,
)
from deeptutor.services.construction_grading.writeback import write_grading_error_events
from deeptutor.services.question_followup import (
    answers_match,
    apply_followup_action_to_context,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    normalize_question_followup_context,
    requested_question_item_index,
    resolve_submission_attempt,
    should_block_unanswered_reference_reveal,
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
from deeptutor.services.security.tool_access import filter_end_user_tools
from deeptutor.tools.rag_tool import rag_search
from deeptutor.tutorbot.response_mode import looks_like_explicit_brevity_request
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
_POST_GRADING_GENERATION_COUNT_RE = re.compile(
    r"(?:再|继续|接着).{0,8}?([0-9]{1,2}|[一二两三四五六七八九十几])\s*(?:道|题|个题目|个小题)?"
)
_ZH_NUMERAL_COUNTS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "几": 3,
}
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


def _personalization_training_signal_text_from_context(question_context: dict[str, Any]) -> str:
    context = question_context.get("personalization_context")
    if not isinstance(context, dict):
        return ""
    intent = context.get("active_training_intent")
    if not isinstance(intent, dict) or not intent:
        return ""

    signal_parts: list[str] = []
    for source_key, label in (
        ("training_intent_id", "training_intent_id"),
        ("concept_id", "concept"),
        ("concept_label", "concept_label"),
        ("error_code", "error_codes"),
        ("error_label", "error_label"),
    ):
        value = _compact_text(intent.get(source_key))
        if value:
            signal_parts.append(f"{label}={value}")

    evidence_refs = intent.get("evidence_refs")
    if isinstance(evidence_refs, list):
        signal_parts.append(f"evidence_ref_count={len(evidence_refs)}")

    authority = context.get("authority") if isinstance(context.get("authority"), dict) else {}
    prescription = _compact_text(authority.get("prescription"))
    if prescription:
        signal_parts.append(f"prescription_authority={prescription}")
    return "；".join(signal_parts)


def _question_context_generation_anchor(question_context: dict[str, Any] | None) -> str:
    raw_context = question_context if isinstance(question_context, dict) else {}
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        if any(
            isinstance(raw_context.get(key), dict)
            for key in (
                "compiled_learning_truth",
                "personalization_context",
                "construction_grading_result",
            )
        ):
            normalized = dict(raw_context)
        else:
            return ""
    for key in ("compiled_learning_truth", "personalization_context"):
        if key not in normalized and isinstance(raw_context.get(key), dict):
            normalized = dict(normalized)
            normalized[key] = raw_context[key]

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
        personalization_signal = _personalization_training_signal_text_from_context(item)
        if personalization_signal:
            _append_unique(
                training_parts,
                f"个性化训练意图：{personalization_signal}；下一题优先从现有题库选择同考点、同错因的相似题。",
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


def _requested_post_grading_question_count(message: str) -> int:
    match = _POST_GRADING_GENERATION_COUNT_RE.search(str(message or ""))
    if not match:
        return 3
    raw = str(match.group(1) or "").strip()
    if raw.isdigit():
        return max(1, min(int(raw), 5))
    return max(1, min(_ZH_NUMERAL_COUNTS.get(raw, 3), 5))


def _build_post_grading_generation_ack(message: str) -> str:
    """Keep mixed-turn ordering clear: grade first, preserve practice as next action."""
    if not looks_like_practice_generation_request(str(message or "")):
        return ""
    count = _requested_post_grading_question_count(message)
    return (
        "### 下一步\n"
        f"你还说想继续练习。我已先完成批改，下一步可以继续给你出 {count} 题同类题。"
    )


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


def _grading_key_correct_answer(item: dict[str, Any] | None) -> str:
    """plan §Step 3.4 priority #1: lightweight batch / curated bank stash
    canonical answer in ``items[i].grading_key.correct_answer`` (hidden, server-side
    only). Exposed as a helper so ``_recover_missing_mcq_authority`` can promote
    the value onto the top-level ``correct_answer`` slot before downstream
    graders read it. ``_mcq_correct_answer_present`` itself stays strict on the
    top-level slot to avoid hiding the promotion step from the recovery path.
    """
    if not isinstance(item, dict):
        return ""
    grading_key = item.get("grading_key")
    if isinstance(grading_key, dict):
        return str(grading_key.get("correct_answer") or "").strip()
    return ""


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


def _promote_grading_key_correct_answer(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """plan §Step 3.4: promote hidden ``grading_key.correct_answer`` onto the
    top-level ``correct_answer`` field so downstream graders that still read the
    legacy slot can consume lightweight-batch authority without changing their
    own contract.

    Returns the input unchanged if no promotion was needed (already has a
    direct answer, or no grading_key source available).
    """
    if not isinstance(item, dict):
        return item
    if str(item.get("correct_answer") or "").strip():
        return item
    recovered = _grading_key_correct_answer(item)
    if not recovered:
        return item
    promoted = dict(item)
    promoted["correct_answer"] = recovered
    return promoted


def _recover_missing_mcq_authority(
    question_context: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, bool]:
    normalized = normalize_question_followup_context(question_context) or dict(question_context or {})
    if not _is_mcq_grading_context(normalized):
        return normalized, "", True
    if _mcq_correct_answer_present(normalized):
        return normalized, "active_object", True

    # plan §Step 3.4 priority #1: try promoting items[i].grading_key.correct_answer
    # to items[i].correct_answer before falling back to questions_bank match.
    raw_items = normalized.get("items") if isinstance(normalized.get("items"), list) else None
    if isinstance(raw_items, list) and raw_items:
        promoted_items: list[dict[str, Any]] = []
        any_promoted = False
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                promoted_items.append(raw_item)
                continue
            promoted = _promote_grading_key_correct_answer(raw_item)
            if promoted is not raw_item:
                any_promoted = True
            promoted_items.append(promoted)
        if any_promoted:
            promoted_context = dict(normalized)
            promoted_context["items"] = promoted_items
            if _mcq_correct_answer_present(promoted_context):
                return promoted_context, "grading_key", True
            normalized = promoted_context
    else:
        promoted = _promote_grading_key_correct_answer(normalized)
        if promoted is not normalized:
            if _mcq_correct_answer_present(promoted):
                return promoted, "grading_key", True
            normalized = promoted

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
            if len(recovered_items) == 1:
                for key, value in recovered_items[0].items():
                    if key != "items":
                        recovered[key] = value
            return recovered, "questions_bank", _mcq_correct_answer_present(recovered)
        return normalized, "missing", False

    source_item = _match_question_bank_item(normalized, candidates)
    if source_item is None:
        return normalized, "missing", False
    recovered = _fill_missing_mcq_authority(normalized, source_item)
    return recovered, "questions_bank", _mcq_correct_answer_present(recovered)


def _question_authority_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    authority_metadata = dict(metadata)
    trace_metadata = metadata.get("trace_metadata")
    if isinstance(trace_metadata, dict):
        authority_metadata.update(trace_metadata)
    return authority_metadata


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


def _apply_open_world_grading_state(graded_context: dict[str, Any]) -> dict[str, Any]:
    """MCQ authority 缺失时的开放世界判分状态。

    ``grade_mcq_submission`` 在无 authority 时返回 ``grading_source="llm_judge"`` 的
    占位结果（is_correct=False 是占位值不是判定）。这里把缺标准答案条目的确定性
    is_correct / score / 占位 construction_grading_result 清空为待裁决状态，最终判定
    交给 RAG-grounded SubmissionGraderAgent 开放世界裁决；已恢复 authority 的条目
    保留确定性判定不动。
    """
    updated = dict(graded_context or {})
    raw_items = updated.get("items") if isinstance(updated.get("items"), list) else None
    any_open_world = False
    if raw_items:
        cleared_items: list[Any] = []
        for item in raw_items:
            if isinstance(item, dict) and not str(item.get("correct_answer") or "").strip():
                cleared_item = dict(item)
                cleared_item["is_correct"] = None
                cleared_item.pop("score", None)
                cleared_item.pop("construction_grading_result", None)
                cleared_items.append(cleared_item)
                any_open_world = True
            else:
                cleared_items.append(item)
        updated["items"] = cleared_items
    if not str(updated.get("correct_answer") or "").strip():
        any_open_world = True
    if any_open_world:
        updated["is_correct"] = None
        updated.pop("score", None)
        updated.pop("construction_grading_result", None)
        updated["diagnosis"] = "OPEN_WORLD"
    return updated


def _should_use_deterministic_grading_feedback(
    *,
    selected_mode: str,
    question_context: dict[str, Any] | None,
    kb_name: str | None = None,
) -> bool:
    mode = str(selected_mode or "").strip().lower()
    if mode in {"deep", "smart"}:
        return False
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
    if str(kb_name or "").strip() and any(item.get("is_correct") is False for item in items):
        return False
    return True


def _build_grading_retrieval_query(question_context: dict[str, Any] | None) -> str:
    items = _grading_items(question_context)
    target = items[0] if len(items) == 1 else (question_context or {})
    parts: list[str] = []
    _append_unique(parts, target.get("question"))
    _append_unique(parts, target.get("concentration"))
    _append_unique(parts, target.get("knowledge_context"))
    _append_unique(parts, target.get("explanation"))
    options = target.get("options")
    if isinstance(options, dict):
        option_text = "；".join(
            f"{key}. {value}"
            for key, value in options.items()
            if str(key).strip() and str(value or "").strip()
        )
        _append_unique(parts, option_text)
    correct = _format_answer_with_option_text(target, target.get("correct_answer"))
    if correct:
        _append_unique(parts, f"标准答案：{correct}")
    if len(items) > 1:
        for item in items[:5]:
            _append_unique(parts, item.get("question"))
            _append_unique(parts, item.get("explanation"))
    query = " ".join(parts)
    return _clip_text(query, limit=900)


def _format_grading_grounding_context(rag_result: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(rag_result, dict):
        return "", []
    evidence_bundle = rag_result.get("evidence_bundle")
    evidence_bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}
    raw_blocks = evidence_bundle.get("content_blocks")
    blocks = [str(item or "").strip() for item in raw_blocks] if isinstance(raw_blocks, list) else []
    if not blocks:
        content = str(rag_result.get("content") or rag_result.get("answer") or "").strip()
        if content:
            blocks = [content]
    raw_sources = evidence_bundle.get("sources") or rag_result.get("sources")
    sources = [dict(item) for item in raw_sources if isinstance(item, dict)] if isinstance(raw_sources, list) else []
    lines: list[str] = []
    for index, block in enumerate(blocks[:4], 1):
        clipped = _clip_text(block, limit=900)
        if clipped:
            lines.append(f"[检索依据 {index}]\n{clipped}")
    if sources:
        lines.append("来源摘要：")
        for source in sources[:5]:
            title = str(source.get("title") or source.get("source") or "知识库片段").strip()
            source_type = str(source.get("source_type") or "").strip()
            chunk_id = str(source.get("chunk_id") or "").strip()
            content = _clip_text(source.get("content"), limit=180)
            meta = " / ".join(part for part in [source_type, chunk_id] if part)
            suffix = f"（{meta}）" if meta else ""
            lines.append(f"- {title}{suffix}: {content}")
    return "\n\n".join(lines).strip(), sources


def _format_general_knowledge_grounding(pack: dict[str, Any] | None) -> str:
    """Render a compiled TEACHING pack into LLM grounding text for general answers."""
    if not isinstance(pack, dict):
        return ""
    sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
    if not any(sources.get(key) for key in ("textbook", "standard", "lecture", "question")):
        return ""

    labels = {
        "textbook": "教材",
        "standard": "规范",
        "lecture": "讲义",
        "question": "真题",
    }
    lines = [
        "【编译教学上下文 - 仅供讲解，非官方答案，不得作为官方判分依据】",
        f"知识点路径：{pack.get('leaf_name_path') or pack.get('resolved_anchor') or ''}",
    ]
    # rich-leaf compiled context renders FIRST when present (flag-gated upstream in
    # compiled_knowledge.general_knowledge; absent keys -> byte-identical legacy rendering).
    # Multi-leaf "rich_leaf_contexts" (primary first, char-capped) or legacy single key —
    # the rendering policy lives in rich_leaf_runtime (single place).
    try:
        from deeptutor.services.construction_grading.rich_leaf_runtime import (
            format_rich_leaf_pack_grounding_lines,
        )

        lines.extend(format_rich_leaf_pack_grounding_lines(pack))
    except Exception:  # noqa: BLE001 — rich-leaf grounding must never break legacy rendering
        pass
    for source_key in ("textbook", "standard", "lecture", "question"):
        raw_items = sources.get(source_key) or []
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items[:6]:
            item = raw_item if isinstance(raw_item, dict) else {}
            preview = str(
                item.get("text_preview")
                or item.get("content_preview")
                or item.get("public_quote")
                or item.get("content")
                or item.get("text")
                or ""
            ).strip()
            if not preview:
                continue
            provenance = item.get("provenance")
            if isinstance(provenance, dict):
                provenance_label = " / ".join(
                    str(provenance.get(key) or "").strip()
                    for key in ("title", "source", "source_id", "stable_source_id", "span")
                    if str(provenance.get(key) or "").strip()
                )
            else:
                provenance_label = str(provenance or "").strip()
            if not provenance_label:
                provenance_label = str(
                    item.get("title")
                    or item.get("source")
                    or item.get("source_id")
                    or labels[source_key]
                ).strip()
            lines.append(f"- [{labels[source_key]}·{provenance_label}] {_clip_text(preview, limit=700)}")
    return "\n".join(lines) if len(lines) > 2 else ""


def _citation_sources_from_question_context(question_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = _grading_items(question_context)
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_source(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        source = dict(raw)
        content = (
            source.get("content")
            or source.get("public_quote")
            or source.get("rag_content")
            or source.get("text")
            or source.get("value")
        )
        if content in (None, "", [], {}):
            return
        if "public_quote" not in source:
            source["public_quote"] = content
        if "source_type" not in source and source.get("source"):
            source["source_type"] = str(source.get("source") or "").strip()
        identity = "|".join(
            str(source.get(key) or "").strip()
            for key in ("source_id", "stable_source_id", "stable_id", "chunk_id", "title", "public_quote")
        )
        if identity in seen:
            return
        seen.add(identity)
        sources.append(source)

    for container in [question_context or {}, *items]:
        for ref in container.get("evidence_refs") or []:
            append_source(ref)
        grading_result = (
            container.get("construction_grading_result")
            if isinstance(container.get("construction_grading_result"), dict)
            else {}
        )
        for ref in grading_result.get("evidence_refs") or []:
            append_source(ref)

    return sources[:8]


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
        item = _promote_grading_key_correct_answer(item) or item
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
        item = _promote_grading_key_correct_answer(item) or item
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


def _looks_like_option_mapping_challenge(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "旧题库",
            "这轮选项",
            "当前选项",
            "选项顺序",
            "没看我这轮",
            "没看选项",
            "字母对不上",
        )
    )


def _looks_like_wrong_cause_request(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "错因",
            "错在哪",
            "哪里错",
            "为什么错",
            "为什么不对",
            "为啥不对",
            "不对",
            "扣分",
            "怎么扣",
            "怎么判",
        )
    )


def _looks_like_missing_selection_check(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in ("漏没漏", "漏没", "漏了没", "有没有漏", "少没少"))


def _brief_option_focus(option_text: str, *, fallback: str) -> str:
    text = _compact_text(option_text)
    if not text:
        return fallback
    return text[:8] or fallback


def _named_option_letters(user_message: str, options: dict[str, str]) -> list[str]:
    """Option letters the learner explicitly names, in ABCDE order.

    A letter counts only when it is an existing option and appears standalone
    (not surrounded by other ASCII letters), so incidental letters inside English
    prose like "Cause" are never mistaken for an option reference.
    """

    text = str(user_message or "").upper()
    named: list[str] = []
    for letter in "ABCDE":
        if letter not in options:
            continue
        if re.search(rf"(?<![A-Z]){letter}(?![A-Z])", text):
            named.append(letter)
    return named


def _render_brief_wrong_cause(item: dict[str, Any], user_message: str = "") -> str:
    correct_letters = set(_answer_letters(item.get("correct_answer")))
    user_letters = set(_answer_letters(item.get("user_answer")))
    options = dict(_option_entries(item))
    # When the learner names a specific option ("A错在哪里"), answer about *that*
    # option using the question's own standard answer as the single authority.
    # Otherwise a correct-answer learner falls through to "没错，答案正确", which
    # reads as "A is fine" and misleads them about the named distractor.
    # Match a letter only when it stands alone (not inside an ASCII word), so
    # incidental letters in prose ("Cause") never count as an option reference.
    named_letters = _named_option_letters(user_message, options)
    named_distractors = [letter for letter in named_letters if letter not in correct_letters]
    if named_distractors:
        focus = "、".join(
            f"{letter}（{_brief_option_focus(options.get(letter, ''), fallback=f'{letter}项')}）"
            for letter in named_distractors
        )
        correct_text = "".join(sorted(correct_letters)) or "标准答案"
        tail = "均为" if len(named_distractors) > 1 else "是"
        return f"{focus}不在标准答案（{correct_text}）内，{tail}干扰项。"
    named_correct = [letter for letter in named_letters if letter in correct_letters]
    if named_correct:
        focus = "、".join(
            f"{letter}（{_brief_option_focus(options.get(letter, ''), fallback=f'{letter}项')}）"
            for letter in named_correct
        )
        tail = "都是正确选项" if len(named_correct) > 1 else "是正确选项"
        return f"{focus}{tail}，应选。"
    extra_letters = sorted(user_letters - correct_letters)
    missing_letters = sorted(correct_letters - user_letters)
    if extra_letters:
        focus = _brief_option_focus(
            options.get(extra_letters[0], ""),
            fallback=f"{extra_letters[0]}项",
        )
        return f"误选{focus}。"
    if missing_letters:
        focus = _brief_option_focus(
            options.get(missing_letters[0], ""),
            fallback=f"{missing_letters[0]}项",
        )
        return f"漏选{focus}。"
    if item.get("is_correct") is True:
        return "没错，答案正确。"
    return "错在选项判断。"


def _render_brief_missing_selection_check(item: dict[str, Any]) -> str:
    user_answer = "".join(_answer_letters(item.get("user_answer")))
    correct_answer = "".join(_answer_letters(item.get("correct_answer")))
    if item.get("is_correct") is True and user_answer:
        return f"没漏，{user_answer}都选对。"
    correct_letters = set(_answer_letters(item.get("correct_answer")))
    user_letters = set(_answer_letters(item.get("user_answer")))
    missing_letters = sorted(correct_letters - user_letters)
    if missing_letters:
        return f"漏选{''.join(missing_letters)}。"
    if correct_answer:
        return f"以标准答案{correct_answer}为准。"
    return "需要题目答案才能判断。"


def _render_targeted_brief_reference_feedback(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> str:
    if not looks_like_explicit_brevity_request(user_message):
        return ""
    items = _reference_items(question_context)
    if len(items) != 1:
        return ""
    item = items[0]
    if _looks_like_wrong_cause_request(user_message):
        return _render_brief_wrong_cause(item, user_message)
    # brevity + named option letter ("为什么A错？一句话", "那B呢？一句话") → brief option focus
    if _named_option_letters_from_item(user_message, item):
        return _render_brief_wrong_cause(item, user_message)
    if _looks_like_missing_selection_check(user_message):
        return _render_brief_missing_selection_check(item)
    return ""


def _looks_like_option_scoring_or_challenge_request(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "为什么",
            "为啥",
            "不对",
            "错",
            "扣分",
            "怎么扣",
            "怎么判",
            "怎么评分",
            "得几分",
            "给几分",
            "能拿",
            "如果",
            "假如",
            "要是",
        )
    )


def _named_option_letters_from_item(user_message: str, item: dict[str, Any]) -> list[str]:
    options = dict(_option_entries(item))
    if not options:
        return []
    return _named_option_letters(user_message, options)


def _render_targeted_option_reference_feedback(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> str:
    if not _looks_like_option_scoring_or_challenge_request(user_message):
        return ""
    # brevity requests defer to the brief path (already ran first); the verbose verdict
    # template does not honour "一句话" and should not override a brief answer.
    if looks_like_explicit_brevity_request(user_message):
        return ""
    items = _reference_items(question_context)
    if len(items) != 1:
        return ""
    item = items[0]
    options = dict(_option_entries(item))
    if not options:
        return ""
    named_letters = _named_option_letters_from_item(user_message, item)
    if not named_letters:
        return ""
    letter = named_letters[0]
    correct_letters = set(_answer_letters(item.get("correct_answer")))
    answer = _format_answer_with_option_text(item, item.get("correct_answer"))
    option = _format_answer_with_option_text(item, letter)
    verdict = (
        "它属于标准答案，会按正确项处理。"
        if letter in correct_letters
        else "它不属于标准答案；如果按这个选项作答，会判错，客观题通常不得分。"
    )
    explanation = _compact_text(str(item.get("explanation") or ""))
    lines = [
        f"{option}：{verdict}",
        f"本题标准答案是 {answer}，我不会因为追问或假设选项改写标准答案。",
    ]
    if explanation:
        lines.append(f"依据：{explanation}")
    return "\n".join(lines).strip()


def _render_brief_reference_feedback(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> str:
    items = _reference_items(question_context)
    if not items:
        return ""
    requested_index = requested_question_item_index(user_message, question_context)
    if requested_index is not None and 1 <= requested_index <= len(items):
        items = [items[requested_index - 1]]
    if len(items) == 1:
        item = items[0]
        objective = bool(_objective_items(item))
        answer_label = "正确答案" if objective else "参考答案"
        answer = _format_answer_with_option_text(item, item.get("correct_answer"))
        if objective and _looks_like_option_mapping_challenge(user_message):
            return f"不是，已按你这轮题面判断，正确答案是 {answer}。"
        explanation = _compact_text(_reference_explanation(item))
        if explanation:
            return f"{answer_label}是 {answer}：{explanation}"
        return f"{answer_label}是 {answer}。"

    parts: list[str] = []
    for index, item in enumerate(items, 1):
        objective = bool(_objective_items(item))
        answer_label = "正确答案" if objective else "参考答案"
        answer = _format_answer_with_option_text(item, item.get("correct_answer"))
        parts.append(f"第{index}题{answer_label}是 {answer}")
    return "；".join(parts) + "。"


def _render_deterministic_reference_feedback(
    question_context: dict[str, Any] | None,
    *,
    user_message: str = "",
) -> str:
    targeted_brief = _render_targeted_brief_reference_feedback(user_message, question_context)
    if targeted_brief:
        return targeted_brief
    targeted_option = _render_targeted_option_reference_feedback(user_message, question_context)
    if targeted_option:
        return targeted_option
    if looks_like_explicit_brevity_request(user_message):
        return _render_brief_reference_feedback(user_message, question_context)

    items = _reference_items(question_context)
    if not items:
        return ""
    requested_index = requested_question_item_index(user_message, question_context)
    if requested_index is not None and 1 <= requested_index <= len(items):
        items = [items[requested_index - 1]]
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


def _question_review_bank_hit(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    counters = (
        (summary.get("trace") or {}).get("lightweight_counters")
        if isinstance(summary.get("trace"), dict)
        else None
    )
    if isinstance(counters, dict) and int(counters.get("bank_hits") or 0) > 0:
        return True
    for item in list(summary.get("results") or []):
        if not isinstance(item, dict):
            continue
        qa_pair = item.get("qa_pair")
        if not isinstance(qa_pair, dict):
            continue
        grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
        metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
        if grading_key.get("source") == "questions_bank" or metadata.get("source") == "questions_bank":
            return True
    return False


def _question_review_variant_hit(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    for item in list(summary.get("results") or []):
        if not isinstance(item, dict):
            continue
        qa_pair = item.get("qa_pair")
        if not isinstance(qa_pair, dict):
            continue
        grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
        metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
        if (
            metadata.get("question_review_variant_mode") is True
            or metadata.get("source") == "similar_question_variant"
            or grading_key.get("source") == "similar_question_variant"
        ):
            return True
    return False


def _question_review_explanation_from_qa_pair(qa_pair: dict[str, Any]) -> str:
    explanation = str(qa_pair.get("explanation") or "").strip()
    if explanation:
        return explanation
    metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
    knowledge_context = str(metadata.get("knowledge_context") or qa_pair.get("knowledge_context") or "").strip()
    for marker in ("题库解析要点：", "【解析】", "解析："):
        if marker not in knowledge_context:
            continue
        tail = knowledge_context.split(marker, 1)[1].strip()
        if tail:
            return tail
    grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
    return str(grading_key.get("minimal_rationale") or "").strip()


def _question_review_renderable(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    for item in list(summary.get("results") or []):
        if not isinstance(item, dict):
            continue
        qa_pair = item.get("qa_pair") if isinstance(item.get("qa_pair"), dict) else {}
        question = str(qa_pair.get("question") or "").strip()
        options = qa_pair.get("options") if isinstance(qa_pair.get("options"), dict) else {}
        grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
        correct_answer = str(qa_pair.get("correct_answer") or grading_key.get("correct_answer") or "").strip()
        if question and len(options) >= 2 and correct_answer:
            return True
    return False


def _clamp_result_question_count(summary: dict[str, Any], max_questions: int) -> dict[str, Any]:
    """Keep rendered/generated question count aligned with upstream request."""

    if not isinstance(summary, dict):
        return summary
    try:
        limit = int(max_questions or 0)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        return summary
    results = summary.get("results")
    if not isinstance(results, list) or len(results) <= limit:
        return summary
    clamped = dict(summary)
    clamped["results"] = list(results[:limit])
    trace = dict(clamped.get("trace") or {})
    trace["requested_question_count"] = limit
    trace["generated_question_count"] = len(results)
    trace["clamped_question_count"] = len(results) - limit
    clamped["trace"] = trace
    return clamped


def _promote_question_review_result(summary: dict[str, Any]) -> dict[str, Any]:
    promoted = dict(summary)
    results: list[dict[str, Any]] = []
    for item in list(summary.get("results") or []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        qa_pair = dict(row.get("qa_pair") or {})
        grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
        if not str(qa_pair.get("correct_answer") or "").strip() and grading_key.get("correct_answer"):
            qa_pair["correct_answer"] = str(grading_key.get("correct_answer") or "").strip()
        explanation = _question_review_explanation_from_qa_pair(qa_pair)
        if explanation and not str(qa_pair.get("explanation") or "").strip():
            qa_pair["explanation"] = explanation
        metadata = dict(qa_pair.get("metadata") or {})
        metadata["question_review_mode"] = True
        qa_pair["metadata"] = metadata
        row["qa_pair"] = qa_pair
        results.append(row)
    promoted["results"] = results
    return promoted


def _render_missing_question_review_feedback(topic: str) -> str:
    focus = str(topic or "").strip() or "这道题"
    return (
        f"我还没有定位到“{focus}”对应的原题题干和选项，不能把它伪装成真题解析。\n\n"
        "请把完整题干和 A/B/C/D 选项发给我；我会按题目讲评模式给你拆解："
        "题干关键词、正确答案、逐项选项分析、易错点和下一步练法。"
    )


def _learner_user_id_from_context(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    billing_context = metadata.get("billing_context") if isinstance(metadata.get("billing_context"), dict) else {}
    config_overrides = getattr(context, "config_overrides", {}) or {}
    return str(
        metadata.get("user_id")
        or metadata.get("learner_user_id")
        or billing_context.get("user_id")
        or config_overrides.get("user_id")
        or ""
    ).strip()


def _source_bot_id_from_context(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    config_overrides = getattr(context, "config_overrides", {}) or {}
    return str(
        metadata.get("bot_id")
        or config_overrides.get("bot_id")
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


def _record_v1_grading_to_brain_for_question(
    *,
    context: UnifiedContext,
    v1_event: dict[str, Any] | None,
    graded_context: dict[str, Any],
    turn_id: str,
) -> dict[str, Any]:
    """Grading-to-Brain（练题路径）：薄委托到唯一 recorder seam
    （construction_grading.writeback.record_case_grading_to_brain，与 TutorBot
    loop 共用），返回 meta（writeback 标记 + personalization_context +
    next_best_action）。Fail-closed：失败返回 {}，绝不影响可见批改。"""
    if not isinstance(v1_event, dict) or v1_event.get("event_type") != "case_grading_completed":
        return {}
    user_id = _learner_user_id_from_context(context)
    if not user_id:
        return {}
    try:
        from deeptutor.services.construction_grading.writeback import (
            record_case_grading_to_brain,
        )
        from deeptutor.services.learner_state import get_learner_state_service

        meta = record_case_grading_to_brain(
            learner_state_service=get_learner_state_service(),
            user_id=user_id,
            grading_event=v1_event,
            source_id=f"{turn_id}:{graded_context.get('question_id') or 'grading'}",
            source_bot_id=_source_bot_id_from_context(context) or None,
            user_answer=str(graded_context.get("user_answer") or ""),
            question_stem=str(
                graded_context.get("question_stem")
                or graded_context.get("stem")
                or graded_context.get("question")
                or ""
            ),
            node_code=str(graded_context.get("node_code") or ""),
            session_id=str(getattr(context, "session_id", "") or ""),
        )
        return meta if isinstance(meta, dict) else {}
    except Exception:  # noqa: BLE001 — memory write must not break visible grading
        logger.warning("LUBAN_V1 deep_question Grading-to-Brain writeback failed", exc_info=True)
        return {}


def _runtime_shadow_flag_enabled(context: UnifiedContext) -> bool:
    """QA/test runtime-shadow flag. Default OFF -> legacy payload byte-identical."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_runtime_shadow")
        or context.config_overrides.get("grading_engine_runtime_shadow")
    )


def _case_rubric_v1_flag_enabled(context: UnifiedContext) -> bool:
    """case rubric-v1 grading flag. DEFAULT ON (full rollout, not gray) — V1 is the case-grading
    authority for every case turn that has rubric/reference authority. Only the emergency env kill
    switch ``LUBAN_CASE_RUBRIC_V1_ENABLED=false/0/off/no`` disables it.
    """
    import os

    return os.environ.get("LUBAN_CASE_RUBRIC_V1_ENABLED", "").strip().lower() not in (
        "false", "0", "off", "no")


def _record_v1_langfuse(
    *, event: dict[str, Any] | None, student_id: str, qid: Any, cg_type: str, status: str = "ok"
) -> None:
    """Mirror the V1 grading observation into Langfuse (gray-rollout). Thin wrapper: all client logic is
    in the langfuse adapter; best-effort, never raises (must not affect grading)."""
    try:
        from deeptutor.services.observability import get_langfuse_observability

        obs = get_langfuse_observability()
        if event and event.get("event_type") == "case_grading_completed":
            aw = float(event.get("awarded_score") or 0)
            mx = float(event.get("max_score") or 0)
            ratio = round(aw / mx, 4) if mx > 0 else 0.0
            obs.record_grading_event(
                name="luban_v1_grading",
                metadata={
                    "engine": "luban_case_rubric_v1",
                    "rubric_provenance": event.get("rubric_provenance"),
                    "awarded_score": aw, "max_score": mx, "score_ratio": ratio,
                    "scoring_points": len(event.get("scoring_points") or []),
                    "high_risk_review": event.get("high_risk_review"),
                    "official_score_allowed": False,
                    "student_id": student_id, "question_id": qid, "cg_type": cg_type,
                },
                score_value=ratio,
                score_comment=f"V1 {event.get('rubric_provenance')} {aw}/{mx}",
            )
        else:
            obs.record_grading_event(
                name="luban_v1_no_grade",
                metadata={"engine": "luban_case_rubric_v1", "status": status,
                          "student_id": student_id, "question_id": qid, "cg_type": cg_type},
            )
    except Exception:  # noqa: BLE001 — observability must never break grading
        logger.debug("LUBAN_V1 langfuse record skipped", exc_info=True)


async def _grade_case_rubric_v1(
    *, context: UnifiedContext, graded_context: dict[str, Any]
) -> dict[str, Any] | None:
    """Run rubric-v1 LLM-adjudicated case grading ONCE (Grading-to-Brain). Thin wrapper — all scoring
    logic lives in ``rubric_grader_v1`` (fat skill). NEXUS-LIKE / OPEN WORLD: V1 grades EVERY case
    question, not only the in-bank ones. The compiled rubric (``load_rubric``) is just higher-quality
    ammunition; when absent, scoring points are extracted on-the-fly from the question's OWN reference
    answer and graded the same per-point semantic way — it never drops back to the deterministic-keyword
    V0 path. Returns the GradingEvent (``event_type == case_grading_completed``), a marker dict
    (``{"status": "unavailable"/"no_reference", ...}``), or None when the gate is closed (caller leaves
    the legacy answer byte-identical). One-or-two awaited DeepSeek calls; never writes the DB / learner
    truth; official_score_allowed stays False."""
    if not _case_rubric_v1_flag_enabled(context):
        return None  # emergency kill switch only; default ON for all users (full rollout, not gray)
    student_id = _learner_user_id_from_context(context)
    cg = graded_context.get("construction_grading_result")
    cg_type = str((cg or {}).get("type") or "").lower()
    if cg_type not in ("case", "batch"):
        # Gray-rollout observability: V1 is on for this user but the turn is not subjective.
        logger.info("LUBAN_V1 skip: not subjective (cg_type=%r) student=%s qid=%s",
                    cg_type or "(none)", student_id,
                    graded_context.get("question_id") or (cg or {}).get("question_id"))
        return None  # only subjective single / multi-item turns
    try:
        import os

        from deeptutor.services.construction_grading import rubric_grader_v1 as _G

        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            logger.info("LUBAN_V1 unavailable: no DEEPSEEK_API_KEY")
            return {"status": "unavailable", "reason": "no_api_key"}
        from deeptutor.services.llm.factory import complete

        # LLM_BINDING=dashscope in production; without explicit base_url+binding,
        # factory.complete() falls back to get_llm_config() and routes DEEPSEEK_API_KEY
        # through dashscope's endpoint → 401. Bind DeepSeek's direct API so the key
        # reaches the correct endpoint.
        _complete_v1 = functools.partial(
            complete,
            base_url="https://api.deepseek.com",
            binding="deepseek",
        )

        if cg_type == "batch":
            event = await _grade_case_batch_v1(
                graded_context, student_id=student_id, complete=_complete_v1, key=key, _G=_G)
        else:
            event = await _grade_one_case_v1(
                graded_context, student_id=student_id, complete=_complete_v1, key=key, _G=_G)
        # Gray-rollout observability: did V1 actually grade, with what provenance/score?
        _qid = graded_context.get("question_id") or (cg or {}).get("question_id")
        if isinstance(event, dict) and event.get("event_type") == "case_grading_completed":
            _aw, _mx = event.get("awarded_score"), event.get("max_score")
            logger.info("LUBAN_V1 GRADED: provenance=%s score=%s/%s points=%d high_risk=%s "
                        "student=%s qid=%s cg_type=%s",
                        event.get("rubric_provenance"), _aw, _mx,
                        len(event.get("scoring_points") or []), event.get("high_risk_review"),
                        student_id, _qid, cg_type)
            _record_v1_langfuse(event=event, student_id=student_id, qid=_qid, cg_type=cg_type)
        else:
            logger.info("LUBAN_V1 no-grade: %s student=%s qid=%s",
                        (event or {}).get("status") if isinstance(event, dict) else "none",
                        student_id, _qid)
            _record_v1_langfuse(event=None, student_id=student_id, qid=_qid, cg_type=cg_type,
                                status=(event or {}).get("status") if isinstance(event, dict) else "none")
        return event
    except Exception:  # noqa: BLE001 — v1 must never break legacy (fail-closed)
        logger.warning("case_rubric_v1 grading failed; legacy answer unaffected", exc_info=True)
        return {"status": "unavailable", "reason": "exception"}


async def _grade_one_case_v1(
    ctx: dict[str, Any], *, student_id: str, complete: Any, key: str, _G: Any
) -> dict[str, Any] | None:
    """Grade ONE subjective question context with V1 (compiled rubric -> open-world reference). Reused by
    both the single-question and per-batch-item paths so there is exactly one grading core (no second
    judging logic). Returns a GradingEvent, a marker dict, or None (no gradable answer)."""
    import os as _os
    _v1_model = _os.environ.get("LLM_MODEL", "").strip() or "deepseek-chat"
    cg = ctx.get("construction_grading_result")
    qid = str(ctx.get("question_id") or (cg or {}).get("question_id") or "").strip()
    answer = str(ctx.get("user_answer") or "").strip()
    logger.warning(
        "LUBAN_DIAG _grade_one_case_v1: entered qid=%s answer_len=%d has_cg=%s",
        qid or "(none)", len(answer), bool(cg),
    )
    if not answer:
        return None
    # 1) governed compiled rubric (best ammunition) if in the bank
    points = _G.load_rubric(qid) if qid else []
    provenance = "compiled_rubric"
    logger.warning(
        "LUBAN_DIAG _grade_one_case_v1: tier1 qid=%s compiled_rubric_points=%d",
        qid or "(none)", len(points),
    )
    # 2) OPEN WORLD: no compiled rubric -> extract atomic scoring points on-the-fly from THIS question's
    #    own reference answer (Nexus-like, not a 173-question lookup); never falls back to V0 keywords.
    if not points:
        # Only explicit answer-key fields may become scoring authority. ``analysis`` is often RAG/
        # explanation text and can belong to a similar-but-different retrieved question; using it here
        # lets RAG become a hidden rubric authority. Without an explicit key, derive from THIS stem.
        reference = str(
            ctx.get("correct_answer")
            or (cg or {}).get("correct_answer")
            or ctx.get("reference_answer")
            or ""
        ).strip()
        stem = str(ctx.get("question_stem") or ctx.get("stem") or ctx.get("question") or "")
        logger.warning(
            "LUBAN_DIAG _grade_one_case_v1: tier2/3 has_reference=%s reference_len=%d has_stem=%s stem_len=%d",
            bool(reference), len(reference), bool(stem), len(stem),
        )
        if reference:
            points = await _G.extract_rubric_from_reference_async(reference, stem, complete, key, model=_v1_model)
            points = _G.normalize_points_to_nominal(
                points, nominal_total=float((cg or {}).get("max_score") or 0))
            provenance = "on_the_fly_reference"
        elif stem:
            # 3) STEM-ONLY: no reference answer at all — derive rubric from question stem via LLM
            #    domain knowledge (construction supervision / 一建). Third-tier path so V1 covers
            #    every case grading turn regardless of whether the question is in the bank.
            points = await _G.derive_rubric_from_stem_async(stem, complete, key, model=_v1_model)
            points = _G.normalize_points_to_nominal(
                points, nominal_total=float((cg or {}).get("max_score") or 0))
            provenance = "derived_from_stem"
        else:
            logger.warning("LUBAN_DIAG _grade_one_case_v1: no_reference fallback qid=%s", qid or "(none)")
            return {"status": "no_reference", "question_id": qid}
    logger.warning(
        "LUBAN_DIAG _grade_one_case_v1: post-tier points=%d provenance=%s qid=%s",
        len(points), provenance, qid or "(none)",
    )
    if not points:
        return {"status": "unavailable", "reason": "no_scoring_points"}
    # Wire the canonical typed object onto the live scoring path (foundation goes live): stamp the
    # canonical authority_source on each rubric point and build+validate the canonical
    # luban_grading_object.v1. This ARMS the G2 gate below (which keys on authority_source) — the
    # 3 official-derived sources were previously unstamped, so G2 was a no-op. Behaviour-preserving:
    # runtime grading fields (text/score/policy) are untouched, awarded scores do not move.
    points = _G.canonicalize_rubric_points(points, qid=qid, provenance=provenance)
    # G2 single-authority guard (load-bearing on the live scoring path): only official-answer-backed
    # points enter the correctness channel; any rich-leaf / textbook-cited point is demoted to
    # supporting and never scores — the 50x-volume rich-leaf points cannot impersonate the official
    # key. Behaviour-preserving for the current official-derived sources (compiled / reference / stem).
    points = _G.enforce_official_scoring_authority(points, provenance=provenance)
    if not points:
        return {"status": "unavailable", "reason": "no_official_scoring_points"}
    event = await _G.grade_with_batch_judge_async(
        qid=qid or "open_world", student_answer=answer, rubric_points=points,
        complete_fn=complete, api_key=key, student_id=student_id, model=_v1_model)
    # FAIL-SAFE: if the batch adjudication produced no trustworthy verdict at all (LLM down / malformed),
    # do NOT surface a 0/full score as authority — return a marker so the caller falls back to the legacy
    # diagnostic path (same as "no rubric"), exactly like an exception would.
    if event.get("degraded"):
        logger.info("LUBAN_V1 degraded (no trustworthy verdict); falling back to legacy qid=%s", qid)
        return {"status": "degraded", "reason": "no_verdict", "question_id": qid}
    event["rubric_provenance"] = provenance
    return event


async def _grade_case_batch_v1(
    graded_context: dict[str, Any], *, student_id: str, complete: Any, key: str, _G: Any
) -> dict[str, Any] | None:
    """Multi-item turns (type=="batch"): grade each subjective sub-item with the SAME V1 core and merge
    into one case_grading_completed event (deterministic sums), so render + same-source outcome work
    unchanged. Non-case sub-items (e.g. MCQ) are left to legacy. None if no sub-item was gradable.

    FAIL-SAFE: EVERY case sub-item must grade to a completed event. If even one degrades (no trustworthy
    verdict), the whole batch falls back to legacy — a half-graded case merged from only the survivors
    would render as a misleadingly "complete" score (e.g. 100% on a case where one sub-question was never
    judged), which is worse than a low score because it looks whole."""
    items = graded_context.get("items") or []
    case_items = [
        it for it in items
        if isinstance(it, dict)
        and str((it.get("construction_grading_result") or {}).get("type") or "").lower() == "case"
    ]
    sub_events: list[dict[str, Any]] = []
    for item in case_items:
        ev = await _grade_one_case_v1(item, student_id=student_id, complete=complete, key=key, _G=_G)
        if isinstance(ev, dict) and ev.get("event_type") == "case_grading_completed":
            sub_events.append(ev)
    # No gradable case sub-item, OR a partial batch (some sub-item degraded) -> legacy, never a merged
    # score built from only the survivors.
    if not sub_events or len(sub_events) != len(case_items):
        return None
    # Preserve real per-sub-question identity (NOT the literal "batch"): the parent case qid if present,
    # else the distinct sub-question qids joined — so to_learning_evidence's source_refs carry true
    # provenance instead of a placeholder. Tag each merged point with its origin qid too.
    parent_qid = str(graded_context.get("question_id") or "").strip()
    sub_qids = [q for q in (str(e.get("question_id") or "").strip() for e in sub_events) if q]
    merged_qid = parent_qid or ",".join(dict.fromkeys(sub_qids)) or "batch"
    merged_points = [
        dict(sp, source_qid=str(ev.get("question_id") or ""))
        for ev in sub_events for sp in (ev.get("scoring_points") or [])
    ]
    return {
        "event_type": "case_grading_completed",
        "student_id": student_id,
        "question_id": merged_qid,
        "scoring_points": merged_points,
        "awarded_score": round(sum(float(e.get("awarded_score") or 0) for e in sub_events), 2),
        "max_score": round(sum(float(e.get("max_score") or 0) for e in sub_events), 2),
        "high_risk_review": any(e.get("high_risk_review") for e in sub_events),
        "grading_source": "rubric_scored_v1",
        "answer_key_authority": "exam_reference_answer",
        "llm_adjudicated": True,
        "official_score_allowed": False,
        "rubric_provenance": "batch",
        "items": sub_events,
    }


def _case_rubric_v1_payload_from_event(
    event: dict[str, Any] | None, *, node_code: str = ""
) -> dict[str, Any] | None:
    """Pure: shape the structured ``luban_case_rubric_v1`` payload from a GradingEvent / marker (no LLM,
    no I/O). Appended alongside (never replacing) ``construction_grading_result``."""
    if not isinstance(event, dict):
        return None
    if event.get("event_type") == "case_grading_completed":
        from deeptutor.services.construction_grading import rubric_grader_v1 as _G
        return {
            "authority": "luban_case_rubric_v1", "status": "ok",
            "grading_event": event,
            "learning_evidence": _G.to_learning_evidence(event, node_code=node_code),
            "official_score_allowed": False,
        }
    # marker dict (no_rubric_open_world / unavailable)
    return {"authority": "luban_case_rubric_v1", **event, "official_score_allowed": False}


def _runtime_shadow_engine(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return str(
        metadata.get("grading_engine_runtime_shadow_mode")
        or metadata.get("grading_engine_runtime_shadow_engine")
        or context.config_overrides.get("grading_engine_runtime_shadow_mode")
        or context.config_overrides.get("grading_engine_runtime_shadow_engine")
        or "deepseek_fast"
    ).strip()


def _runtime_shadow_cache_student_id(context: UnifiedContext) -> str:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return str(
        metadata.get("grading_engine_runtime_shadow_cache_student_id")
        or context.config_overrides.get("grading_engine_runtime_shadow_cache_student_id")
        or ""
    ).strip()


def _maybe_attach_runtime_shadow(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """QA/test-only: append a non-production Luban shadow grading result.

    Thin wrapper — all scoring / artifact-gate / policy logic lives in
    ``runtime_shadow_adapter`` (fat skill). This only reads the flag + the real
    submission fields and appends ``luban_grading_engine_shadow``. It NEVER mutates
    the legacy ``construction_grading_result``, never writes the DB / Learning Brain,
    never calls the kernel or RAG. Any error fails closed (``engine_unavailable``);
    legacy always returns. The adapter itself refuses non-``qa_``/``test_`` students.
    """
    if not _runtime_shadow_flag_enabled(context):
        return
    student_id = _learner_user_id_from_context(context)
    question_id = str(graded_context.get("question_id") or "").strip()
    student_answer = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.runtime_shadow_adapter import (
            build_runtime_shadow_result,
        )

        result_payload["luban_grading_engine_shadow"] = build_runtime_shadow_result(
            question_id=question_id,
            student_id=student_id,
            student_answer=student_answer,
            engine=_runtime_shadow_engine(context),
            qa_shadow=True,
            prediction_student_id=_runtime_shadow_cache_student_id(context) or None,
        )
    except Exception as exc:  # noqa: BLE001 — shadow must never break legacy
        result_payload["luban_grading_engine_shadow"] = {
            "authority": "luban_grading_engine_shadow",
            "shadow_status": "engine_unavailable",
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True,
            "writeback_performed": False,
            "teacher_review_required": True,
        }


def _v1_beta_shadow_flag_enabled(context: UnifiedContext) -> bool:
    """v1 beta_shadow request flag. Default OFF -> legacy payload byte-identical, no beta key."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_v1_beta_shadow")
        or metadata.get("enable_luban_v1_beta_shadow")
        or context.config_overrides.get("grading_engine_v1_beta_shadow")
        or context.config_overrides.get("enable_luban_v1_beta_shadow")
    )


def _v1_beta_shadow_kill_switch_active() -> bool:
    """Env kill switch. ``LUBAN_V1_BETA_SHADOW_ENABLED=false`` (or 0/off/no) force-disables beta
    even when the request flag is on. Absence does NOT enable (the request flag is still required)."""
    import os

    return os.environ.get("LUBAN_V1_BETA_SHADOW_ENABLED", "").strip().lower() in (
        "false", "0", "off", "no",
    )


def _v1_beta_shadow_cohort_prefixes() -> tuple[str, ...]:
    """Limited-release cohort allowlist (user-id prefixes). Default = ``qa_`` / ``test_`` only, so
    production behaviour is unchanged. Ops may EXTEND it for a named internal/operator cohort via env
    ``LUBAN_V1_BETA_SHADOW_COHORT="qa_,test_,operator_"`` (comma-separated prefixes). The built-in
    ``qa_``/``test_`` cohort is always included; an empty/blank env value keeps the default."""
    import os

    base = ["qa_", "test_"]
    raw = os.environ.get("LUBAN_V1_BETA_SHADOW_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    # de-dupe, preserve order
    return tuple(dict.fromkeys(base + extra))


def _v1_beta_shadow_cohort_member(student_id: str) -> bool:
    return str(student_id).startswith(_v1_beta_shadow_cohort_prefixes())


def _maybe_attach_v1_beta_shadow(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Cohort-gated QA/test-only: append the non-production v1 beta_shadow result (append-only).

    Thin wrapper — ALL scoring / source / spec / list policy lives in ``beta_shadow_loader``
    (fat skill). This only reads the flag + kill switch + cohort allowlist + the real submission
    fields and appends ``luban_grading_engine_v1_beta_shadow``. It NEVER mutates the legacy
    ``construction_grading_result``, never writes the DB / Learning Brain truth / formal registry,
    never touches v0 / the kernel / RAG. Any error fails closed; legacy always returns. Only
    limited-release cohort members (default ``qa_`` / ``test_``) get a beta result.
    """
    if not _v1_beta_shadow_flag_enabled(context):
        return  # flag off -> legacy only
    if _v1_beta_shadow_kill_switch_active():
        result_payload["luban_grading_engine_v1_beta_shadow"] = {
            "authority": "luban_grading_engine_v1_beta_shadow",
            "shadow_status": "killed_by_switch",
            "not_production_grade": True,
            "writeback_performed": False,
        }
        return
    student_id = _learner_user_id_from_context(context)
    if not _v1_beta_shadow_cohort_member(student_id):
        return  # non-cohort (production / real student) -> never beta, legacy only
    question_id = str(graded_context.get("question_id") or "").strip()
    student_answer = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.beta_shadow_loader import (
            build_beta_shadow_payload,
        )

        result_payload["luban_grading_engine_v1_beta_shadow"] = build_beta_shadow_payload(
            question_id=question_id,
            student_id=student_id,
            student_answer=student_answer,
        )
    except Exception as exc:  # noqa: BLE001 — beta must never break legacy
        result_payload["luban_grading_engine_v1_beta_shadow"] = {
            "authority": "luban_grading_engine_v1_beta_shadow",
            "shadow_status": "beta_supply_unavailable",
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True,
            "writeback_performed": False,
            "teacher_review_required": True,
        }


def _pgo_shadow_flag_enabled(context: UnifiedContext) -> bool:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_pgo_shadow")
        or context.config_overrides.get("grading_engine_pgo_shadow")
    )


def _pgo_shadow_env_enabled() -> bool:
    import os

    return os.environ.get("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "").strip().lower() in (
        "true", "1", "on", "yes",
    )


def _pgo_shadow_cohort_member(student_id: str) -> bool:
    return str(student_id).startswith(("qa_", "test_", "operator_"))


def _maybe_attach_pgo_shadow(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Append-only PGO coverage shadow path.

    Thin wrapper only: it gates by request/env/cohort and delegates all PGO
    adapter/scoring semantics to ``per_question_grading_judge``. It never mutates
    ``construction_grading_result`` and never writes learner/brain state.
    """
    if not _pgo_shadow_flag_enabled(context):
        return
    key = "luban_case_rubric_pgo_shadow"
    if not _pgo_shadow_env_enabled():
        result_payload[key] = {
            "authority": key,
            "shadow_status": "killed_by_switch",
            "not_production_grade": True,
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "writeback_performed": False,
        }
        return
    student_id = _learner_user_id_from_context(context)
    if not _pgo_shadow_cohort_member(student_id):
        return
    try:
        from deeptutor.services.construction_grading.per_question_grading_judge import (
            build_pgo_shadow_payload,
        )

        result_payload[key] = build_pgo_shadow_payload(
            contract=graded_context.get("pgo_grading_contract"),
            point_verdicts=graded_context.get("pgo_point_verdicts"),
            question_id=str(graded_context.get("question_id") or ""),
            student_id=student_id,
        )
    except Exception as exc:  # noqa: BLE001 — shadow must never break legacy
        result_payload[key] = {
            "authority": key,
            "shadow_status": "engine_unavailable",
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True,
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "writeback_performed": False,
            "teacher_review_required": True,
        }


def _m35_artifact_shadow_flag_enabled(context: UnifiedContext) -> bool:
    """M35 scoring-artifact shadow flag. Default OFF -> legacy payload byte-identical."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_m35_artifact_shadow")
        or context.config_overrides.get("grading_engine_m35_artifact_shadow")
    )


def _m35_artifact_shadow_judge_enabled(context: UnifiedContext) -> bool:
    """Runtime-only M35 judge tier flag. Default OFF -> shape-only shadow."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_m35_artifact_shadow_judge")
        or context.config_overrides.get("grading_engine_m35_artifact_shadow_judge")
        or str(context.config_overrides.get("grading_engine_m35_artifact_shadow_tier") or "").strip()
        == "constrained_llm"
    )


def _m35_artifact_shadow_kill_switch_active() -> bool:
    """``LUBAN_M35_ARTIFACT_SHADOW_ENABLED=false`` force-disables the M35 shadow block."""
    import os

    return os.environ.get("LUBAN_M35_ARTIFACT_SHADOW_ENABLED", "").strip().lower() in (
        "false", "0", "off", "no",
    )


def _m35_artifact_shadow_cohort_prefixes() -> tuple[str, ...]:
    """Server-governed QA/operator-only cohort.

    Do not allow request or env-controlled real-student prefix expansion here:
    M35 shadow visibility is not a production/default authorization path.
    """
    return ("qa_", "test_", "operator_")


def _m35_artifact_shadow_cohort_member(student_id: str) -> bool:
    return str(student_id).startswith(_m35_artifact_shadow_cohort_prefixes())


def _m35_authenticated_user_id_from_context(context: UnifiedContext) -> str:
    """Server-authenticated user id for M35 visibility gates.

    Deliberately does not read billing_context, config_overrides, or learner
    display fields. Those are business context and can be request-shaped; they
    must not authorize shadow metadata for real students.
    """
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return str(metadata.get("authenticated_user_id") or "").strip()


def _maybe_attach_m35_artifact_shadow(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Append M35 scoring-artifact shadow metadata without changing legacy grading.

    Thin wrapper: this reads only flag/env kill switch/cohort and forwards the
    real case grading fields to ``m35_artifact_shadow``. No DB, RAG, learner truth,
    or WebSocket route is introduced here.
    """
    if not _m35_artifact_shadow_flag_enabled(context):
        return
    if _m35_artifact_shadow_kill_switch_active():
        return
    student_id = _m35_authenticated_user_id_from_context(context)
    if not _m35_artifact_shadow_cohort_member(student_id):
        return
    question_id = str(graded_context.get("question_id") or "").strip()
    student_answer = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.m35_artifact_shadow import (
            build_m35_artifact_shadow_payload,
            make_default_m35_artifact_shadow_judge,
        )

        judge_fn = (
            make_default_m35_artifact_shadow_judge()
            if _m35_artifact_shadow_judge_enabled(context)
            else None
        )
        result_payload["luban_m35_scoring_artifact_shadow"] = build_m35_artifact_shadow_payload(
            question_id=question_id,
            student_id=student_id,
            student_answer=student_answer,
            judge_tier="constrained_llm" if callable(judge_fn) else "shape_stub",
            judge_fn=judge_fn,
        )
    except Exception as exc:  # noqa: BLE001 - shadow must never break legacy grading.
        result_payload["luban_m35_scoring_artifact_shadow"] = {
            "authority": "grading_engine_m35_artifact_shadow",
            "shadow_status": "artifact_shadow_unavailable",
            "unavailable_reason": str(exc)[:200],
            "evaluation_tier": "shape_stub",
            "quality_claim_allowed": False,
            "verdict_ceiling": "NO-GO_OR_SHAPE_ONLY",
            "official_score_allowed": False,
            "production_write_count": 0,
            "canonical_truth_written": False,
            "writeback_performed": False,
            "db_write_count": 0,
            "remote_write_count": 0,
            "rag_lookup_count": 0,
            "point_matches": [],
        }


def _v1_controlled_runtime_flag_enabled(context: UnifiedContext) -> bool:
    """v1 controlled-runtime request flag. Default OFF -> legacy payload byte-identical."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_v1_controlled_runtime")
        or context.config_overrides.get("grading_engine_v1_controlled_runtime")
    )


def _v1_controlled_runtime_kill_switch_active() -> bool:
    """Env kill switch ``LUBAN_V1_CONTROLLED_RUNTIME_ENABLED=false`` force-disables controlled runtime."""
    import os

    return os.environ.get("LUBAN_V1_CONTROLLED_RUNTIME_ENABLED", "").strip().lower() in (
        "false", "0", "off", "no",
    )


def _v1_controlled_runtime_cohort_prefixes() -> tuple[str, ...]:
    """Controlled-runtime cohort allowlist. Default ``qa_``/``test_``/``operator_`` (production
    default still OFF — no flag means no controlled runtime). Extendable via env
    ``LUBAN_V1_CONTROLLED_RUNTIME_COHORT``. Real students are never in the default cohort."""
    import os

    base = ["qa_", "test_", "operator_"]
    raw = os.environ.get("LUBAN_V1_CONTROLLED_RUNTIME_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(dict.fromkeys(base + extra))


def _v1_controlled_runtime_cohort_member(student_id: str) -> bool:
    return str(student_id).startswith(_v1_controlled_runtime_cohort_prefixes())


def _maybe_attach_v1_controlled_runtime(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Controlled production runtime candidate (append-only). Promotes beta_shadow to
    ``controlled_runtime_candidate`` mode, gated on a loadable release_candidate registry + the
    controlled cohort. production default stays OFF; legacy ``construction_grading_result`` is never
    mutated; no production / canonical-truth write; fail-closed. ALL scoring + registry policy lives
    in ``beta_shadow_loader`` (fat skill); this wrapper only does flag / kill / cohort / append."""
    if not _v1_controlled_runtime_flag_enabled(context):
        return  # flag off -> legacy only (production default OFF)
    if _v1_controlled_runtime_kill_switch_active():
        result_payload["luban_grading_engine_v1_controlled_runtime"] = {
            "authority": "luban_grading_engine_v1_controlled_runtime",
            "mode": "controlled_runtime_candidate",
            "shadow_status": "killed_by_switch",
            "not_production_grade": True,
            "writeback_performed": False,
        }
        return
    student_id = _learner_user_id_from_context(context)
    if not _v1_controlled_runtime_cohort_member(student_id):
        return  # non-cohort (real student) -> legacy only
    question_id = str(graded_context.get("question_id") or "").strip()
    student_answer = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.beta_shadow_loader import (
            build_controlled_runtime_payload,
        )

        result_payload["luban_grading_engine_v1_controlled_runtime"] = build_controlled_runtime_payload(
            question_id=question_id,
            student_id=student_id,
            student_answer=student_answer,
        )
    except Exception as exc:  # noqa: BLE001 — controlled runtime must never break legacy
        result_payload["luban_grading_engine_v1_controlled_runtime"] = {
            "authority": "luban_grading_engine_v1_controlled_runtime",
            "mode": "controlled_runtime_candidate",
            "shadow_status": "release_candidate_registry_unavailable",
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True,
            "writeback_performed": False,
            "teacher_review_required": True,
        }


def _v1_llm_adjudication_flag_enabled(context: UnifiedContext) -> bool:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_v1_llm_adjudication")
        or context.config_overrides.get("grading_engine_v1_llm_adjudication")
    )


def _v1_llm_adjudication_limited_default_enabled(student_id: str) -> bool:
    import os

    enabled = os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED", "").strip().lower()
    if enabled not in ("1", "true", "on", "yes"):
        return False
    raw = os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT", "qa_,operator_")
    prefixes = [p.strip() for p in raw.split(",") if p.strip()]
    if not prefixes:
        prefixes = ["qa_", "operator_"]
    return str(student_id).startswith(tuple(prefixes))


def _v1_llm_adjudication_kill_switch_active() -> bool:
    import os

    return os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_ENABLED", "").strip().lower() in (
        "false", "0", "off", "no",
    )


def _v1_llm_adjudication_cohort_member(student_id: str) -> bool:
    import os

    base = ["qa_", "test_", "operator_"]
    raw = os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    return str(student_id).startswith(tuple(dict.fromkeys(base + extra)))


def _objective_candidate_flag_enabled(context: UnifiedContext) -> bool:
    """Objective candidate request flag (M25-B). Default OFF -> legacy payload byte-identical."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_objective_candidate")
        or context.config_overrides.get("grading_engine_objective_candidate")
    )


def _objective_candidate_cohort_member(student_id: str) -> bool:
    import os

    base = ["qa_", "test_", "operator_"]
    raw = os.environ.get("LUBAN_OBJECTIVE_CANDIDATE_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    return str(student_id).startswith(tuple(dict.fromkeys(base + extra)))


def _maybe_attach_objective_candidate(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Objective answer-key CANDIDATE lane (append-only, M25-B). Cohort-gated QA/test-only.

    Thin wrapper — ALL objective scoring / packet / authority policy lives in
    ``objective_runtime_adapter`` + ``objective_grader`` + ``objective_answer_key_compiler``
    (fat skills). This only reads the flag + cohort + real submission fields and appends
    ``luban_grading_engine_objective_candidate``. It NEVER mutates the legacy
    ``construction_grading_result``, never writes the DB / Learning Brain / registry, never
    claims official truth. answer_key is the sole authority; the LLM cannot decide correctness.
    Missing / malformed / tampered candidate bundle -> fail-closed; not-in-bank -> fail-open
    open-world diagnostic. Default OFF -> legacy byte-identical."""
    if not _objective_candidate_flag_enabled(context):
        return  # flag off -> legacy only
    student_id = _learner_user_id_from_context(context)
    if not _objective_candidate_cohort_member(student_id):
        return  # non-cohort (real student) -> legacy only
    question_id = str(graded_context.get("question_id") or "").strip()
    selected_option = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.objective_runtime_adapter import (
            build_objective_candidate_payload,
        )

        result_payload["luban_grading_engine_objective_candidate"] = build_objective_candidate_payload(
            question_id=question_id,
            selected_option=selected_option,
            learner_context={"student_id": student_id},
        )
    except Exception as exc:  # noqa: BLE001 — objective candidate must never break legacy
        result_payload["luban_grading_engine_objective_candidate"] = {
            "authority": "luban_grading_engine_objective_candidate",
            "mode": "objective_candidate",
            "status": "candidate_bundle_unavailable",
            "fail_closed": True,
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True,
            "writeback_performed": False,
        }


def _m31_governed_objective_flag_enabled(context: UnifiedContext) -> bool:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_m31_governed_objective")
        or context.config_overrides.get("grading_engine_m31_governed_objective")
    )


def _m31_governed_objective_kill_switch_active() -> bool:
    """Env kill switch ``LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED=false`` force-disables the governed lane."""
    import os

    return os.environ.get("LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED", "").strip().lower() in (
        "false", "0", "off", "no",
    )


def _m31_governed_objective_cohort_prefixes() -> tuple[str, ...]:
    """Cohort prefixes for the M31 governed objective lane. Base ``qa_/test_/operator_`` plus optional
    ``LUBAN_M31_GOVERNED_OBJECTIVE_COHORT``. Real students are never in the default cohort."""
    import os

    base = ["qa_", "test_", "operator_"]
    raw = os.environ.get("LUBAN_M31_GOVERNED_OBJECTIVE_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(dict.fromkeys(base + extra))


def _maybe_attach_m31_governed_objective(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """M31 governed objective release-candidate lane (append-only; flag + env kill switch + cohort).

    Thin wrapper — ALL governed loading / verification / scoring policy lives in
    ``objective_runtime_adapter`` (fat skill). This only reads the flag + cohort + real submission
    fields and appends ``luban_grading_engine_m31_governed_objective``. It NEVER mutates the legacy
    ``construction_grading_result``, never writes the DB / Learning Brain / registry, never publishes,
    never flips production default; the LLM cannot decide correctness. A governed signed hit scores
    in-bank objective answers as CONTROLLED release-truth (``official_score_allowed=True``); a miss /
    tamper falls through (in the fat skill) to the candidate / open-world lane. Default OFF -> legacy
    byte-identical."""
    if not _m31_governed_objective_flag_enabled(context):
        return  # flag off -> legacy only
    # canonical lane key/authority is owned by the fat skill (no duplicated string literal).
    from deeptutor.services.construction_grading.objective_runtime_adapter import (
        GOVERNED_AUTHORITY as KEY,
    )
    if _m31_governed_objective_kill_switch_active():
        result_payload[KEY] = {
            "authority": KEY,
            "mode": "governed_objective_release_candidate",
            "status": "killed_by_switch",
            "killed_by_switch": True,
            "not_production_grade": False,
            "writeback_performed": False,
        }
        return
    student_id = _learner_user_id_from_context(context)
    if not str(student_id).startswith(_m31_governed_objective_cohort_prefixes()):
        return  # non-cohort (real student) -> legacy only
    question_id = str(graded_context.get("question_id") or "").strip()
    selected_option = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.objective_runtime_adapter import (
            build_governed_objective_payload,
        )

        result_payload[KEY] = build_governed_objective_payload(
            question_id=question_id,
            selected_option=selected_option,
            learner_context={"student_id": student_id},
        )
    except Exception as exc:  # noqa: BLE001 — governed lane must never break legacy
        # classify only — never leak filesystem paths / raw exception text into client metadata.
        result_payload[KEY] = {
            "authority": KEY,
            "mode": "governed_objective_release_candidate",
            "status": "governed_bundle_unavailable",
            "fail_closed": True,
            "unavailable_reason": type(exc).__name__,
            "not_production_grade": False,
            "writeback_performed": False,
        }


def _textbook_knowledge_flag_enabled(context: UnifiedContext) -> bool:
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return bool(
        metadata.get("grading_engine_textbook_knowledge")
        or context.config_overrides.get("grading_engine_textbook_knowledge")
    )


def _textbook_knowledge_cohort_prefixes() -> tuple[str, ...]:
    import os

    base = ["qa_", "test_", "operator_"]
    raw = os.environ.get("LUBAN_TEXTBOOK_KNOWLEDGE_COHORT", "")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(dict.fromkeys(base + extra))


def _resolve_node_code_for_turn(context: UnifiedContext, graded_context: dict[str, Any]) -> tuple[str, str]:
    """Resolve (node_code, match_kind) for the turn's verbatim textbook context.

    Priority: an EXPLICIT node_code (graded_context / followup_question_context / metadata) wins with
    match_kind ``explicit``; otherwise AUTO-MAP the turn's question_id to a textbook node via
    ``node_code_for_question`` (match_kind ``exact`` / ``section``) so any in-bank turn gets textbook
    context. Returns ("","") when nothing resolves (caller attaches nothing)."""
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    fctx = metadata.get("followup_question_context") if isinstance(metadata.get("followup_question_context"), dict) else {}
    explicit = str(
        graded_context.get("node_code") or fctx.get("node_code") or metadata.get("textbook_node_code") or ""
    ).strip()
    if explicit:
        return (explicit, "explicit")
    question_id = str(graded_context.get("question_id") or fctx.get("question_id") or "").strip()
    if question_id:
        from deeptutor.services.construction_grading.textbook_knowledge_runtime import (
            node_code_for_question,
        )

        resolved = node_code_for_question(question_id)
        if resolved is not None:
            return resolved  # (node_code, "exact"|"section")
    return ("", "")


def _learner_weak_canonical_codes(graded_context: dict[str, Any]) -> list[str]:
    """The learner's active weak concepts mapped to canonical codes (for #3 targeted remediation).
    learner_state remains the weakness authority; this only READS + normalizes to canonical."""
    truth = graded_context.get("compiled_learning_truth")
    if not isinstance(truth, dict):
        return []
    concepts = [str(w.get("concept_id") or "") for w in (truth.get("weak_points") or [])
                if isinstance(w, dict) and str(w.get("decay_state") or "active") == "active"
                and not w.get("superseded_by_event_ids")]
    concepts = [c for c in concepts if c]
    if not concepts:
        return []
    try:
        from deeptutor.services.construction_grading.canonical_resolution import to_canonical_set
        return sorted(to_canonical_set(concepts))
    except Exception:  # noqa: BLE001 — resolution is best-effort; never break the teaching lane
        return []


def _maybe_attach_textbook_knowledge(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Attach verbatim-sourced 2026-textbook knowledge for the turn's node_code (append-only; flag +
    env kill switch + cohort; default OFF -> legacy byte-identical).

    Thin wrapper — ALL loading / verification / resolution lives in ``textbook_knowledge_runtime``
    (fat skill). This reads flag + cohort + node_code and appends ``luban_textbook_knowledge``. It
    NEVER mutates the legacy result, never writes DB / canonical truth; the signed knowledge is
    verbatim teaching/source context (grant_release stays False here — not an official score)."""
    import os

    KEY = "luban_textbook_knowledge"
    if not _textbook_knowledge_flag_enabled(context):
        return
    if os.environ.get("LUBAN_TEXTBOOK_KNOWLEDGE_ENABLED", "").strip().lower() in ("false", "0", "off", "no"):
        result_payload[KEY] = {"authority": KEY, "status": "killed_by_switch", "killed_by_switch": True}
        return
    student_id = _learner_user_id_from_context(context)
    if not str(student_id).startswith(_textbook_knowledge_cohort_prefixes()):
        return
    node, match_kind = _resolve_node_code_for_turn(context, graded_context)
    if not node:
        return  # no node to resolve (no explicit code + no confident question->node map) -> nothing
    try:
        from deeptutor.services.construction_grading.textbook_knowledge_runtime import (
            resolve_textbook_knowledge,
        )

        # the turn's question text focuses the coarse node to its most-relevant cards (finer granularity);
        # answered_incorrectly drives #6 prerequisite remediation (learner evidence, never written back)
        learner_context = {
            "student_id": student_id,
            "question_stem": str(graded_context.get("question_stem")
                                 or graded_context.get("stem")
                                 or graded_context.get("question")
                                 or graded_context.get("question_text") or ""),
            "user_answer": str(graded_context.get("user_answer") or ""),
            "answered_incorrectly": graded_context.get("is_correct") is False,
            # #3 precision: map the learner's active weak concepts -> canonical so prerequisite
            # remediation targets real gaps. learner_state stays the mastery/weakness authority.
            "weak_codes": _learner_weak_canonical_codes(graded_context),
        }
        payload = resolve_textbook_knowledge(node, learner_context=learner_context)
        if payload is not None:
            payload["node_match"] = match_kind  # explicit | exact | section (transparency for consumers)
            result_payload[KEY] = payload
    except Exception as exc:  # noqa: BLE001 — textbook lane must never break legacy
        result_payload[KEY] = {"authority": KEY, "status": "unavailable",
                               "unavailable_reason": type(exc).__name__}

    # Four-source teaching context (textbook + standard + lecture + question) for the SAME canonical
    # node, from the verify-gated unified supply. TEACHING tier only (official scoring stays verbatim).
    try:
        from deeptutor.services.construction_grading.canonical_knowledge_runtime import (
            resolve_canonical_knowledge,
        )

        four = resolve_canonical_knowledge(node, learner_context=learner_context)
        if four is not None:
            four["node_match"] = match_kind
            result_payload["luban_canonical_knowledge"] = four
    except Exception as exc:  # noqa: BLE001 — teaching lane must never break legacy
        result_payload["luban_canonical_knowledge"] = {
            "authority": "luban_canonical_knowledge", "status": "unavailable",
            "unavailable_reason": type(exc).__name__}


def _general_knowledge_cohort_prefixes() -> tuple[str, ...]:
    import os

    raw = os.environ.get("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", "")
    return tuple(prefix.strip() for prefix in raw.split(",") if prefix.strip())


def _general_knowledge_cohort_member(student_id: str) -> bool:
    prefixes = _general_knowledge_cohort_prefixes()
    return bool(prefixes) and str(student_id).startswith(prefixes)


def _general_knowledge_flag_value(context: UnifiedContext) -> bool | None:
    config_overrides = getattr(context, "config_overrides", {}) or {}
    if "general_knowledge_context" not in config_overrides:
        return None
    return bool(config_overrides.get("general_knowledge_context"))


def _has_active_question_context(followup_question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(
        followup_question_context if isinstance(followup_question_context, dict) else None
    )
    return bool(
        normalized
        and (
            normalized.get("question")
            or normalized.get("items")
        )
    )


def _maybe_attach_general_knowledge_context(
    *,
    context: UnifiedContext,
    result_payload: dict[str, Any],
) -> None:
    """Attach compiled four-source TEACHING context for a general knowledge turn.

    Thin wrapper: request override / optional cohort / kill only. Resolution policy lives in
    construction_grading.general_knowledge_context. This is append-only and
    never writes DB, canonical learner truth, or official grading fields.
    """
    import os

    key = "luban_general_knowledge_context"
    flag_value = _general_knowledge_flag_value(context)
    if flag_value is False:
        return
    if os.environ.get("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", "").strip().lower() in (
        "false",
        "0",
        "off",
        "no",
    ):
        result_payload[key] = {"authority": key, "status": "killed_by_switch", "killed_by_switch": True}
        return

    student_id = _learner_user_id_from_context(context)
    if flag_value is not True and not _general_knowledge_cohort_member(student_id):
        return

    try:
        from deeptutor.services.construction_grading.general_knowledge_context import (
            resolve_general_knowledge_context,
        )

        learner_context = {
            "student_id": student_id,
            "weak_codes": _learner_weak_canonical_codes({}),
        }
        pack = resolve_general_knowledge_context(
            str(getattr(context, "user_message", "") or ""),
            learner_context=learner_context,
        )
        if pack is not None:
            result_payload[key] = pack
    except Exception as exc:  # noqa: BLE001 - this teaching lane must never break legacy turns
        result_payload[key] = {
            "authority": key,
            "status": "unavailable",
            "unavailable_reason": type(exc).__name__,
        }


def _v1_llm_adjudication_dev_force_on() -> bool:
    """LOCAL TEST MODE ONLY: force v1 adjudication ON (bypass request-flag + cohort) when
    ``LUBAN_V1_LLM_ADJUDICATOR_DEV_FORCE_ON`` is truthy AND this is NOT a production environment.
    Default off -> zero production behaviour change. The kill switch still overrides it; legacy
    is never mutated; no production / canonical-truth write. For manual local testing only."""
    import os

    if os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_DEV_FORCE_ON", "").strip().lower() not in (
        "1", "true", "on", "yes",
    ):
        return False
    try:
        from deeptutor.services.runtime_env import is_production_environment

        if is_production_environment():
            return False  # never force-on in production, regardless of the flag
    except Exception:
        return False
    return True


def _maybe_attach_v1_llm_adjudication(
    *,
    context: UnifiedContext,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    """Runtime LLM adjudication candidate (append-only). DeepSeek-V4-flash primary + Qwen fallback,
    gated by a deterministic validator (the safety floor) in ``runtime_llm_adjudicator`` (fat skill).
    production default OFF; legacy ``construction_grading_result`` never mutated; no production /
    canonical-truth write; fail-closed. This thin wrapper only does flag / kill / cohort / append."""
    student_id = _learner_user_id_from_context(context)
    explicit_flag = _v1_llm_adjudication_flag_enabled(context)
    limited_default = _v1_llm_adjudication_limited_default_enabled(student_id)
    dev_force = _v1_llm_adjudication_dev_force_on()  # LOCAL TEST MODE: bypass flag + cohort (non-prod only)
    if not explicit_flag and not limited_default and not dev_force:
        return  # flag/default off -> legacy only
    if _v1_llm_adjudication_kill_switch_active():
        if limited_default and not explicit_flag and not dev_force:
            return  # default rollback path -> legacy only
        result_payload["luban_grading_engine_v1_llm_adjudication"] = {
            "authority": "luban_grading_engine_v1_llm_adjudication",
            "mode": "llm_adjudication_candidate", "shadow_status": "killed_by_switch",
            "not_production_grade": True, "writeback_performed": False,
        }
        return
    if not dev_force and not _v1_llm_adjudication_cohort_member(student_id):
        return  # non-cohort real student -> legacy only
    question_id = str(graded_context.get("question_id") or "").strip()
    student_answer = str(graded_context.get("user_answer") or "").strip()
    try:
        from deeptutor.services.construction_grading.runtime_llm_adjudicator import (
            build_llm_adjudication_payload,
        )

        payload = build_llm_adjudication_payload(
            question_id=question_id,
            student_id=student_id,
            student_answer=student_answer,
            personalization_context_pack=(
                context.metadata.get("personalization_context")
                if isinstance(context.metadata.get("personalization_context"), dict)
                else None
            ),
        )
        if limited_default and not explicit_flag:
            payload["limited_default_applied"] = True
            payload["trigger"] = "limited_default"
            payload["production_default"] = "limited_cohort_on"
        result_payload["luban_grading_engine_v1_llm_adjudication"] = payload
    except Exception as exc:  # noqa: BLE001 — adjudication must never break legacy
        if limited_default and not explicit_flag and not dev_force:
            return  # default rollback/fail-closed path -> legacy only
        result_payload["luban_grading_engine_v1_llm_adjudication"] = {
            "authority": "luban_grading_engine_v1_llm_adjudication",
            "mode": "llm_adjudication_candidate",
            "shadow_status": "adjudicator_unavailable",
            "unavailable_reason": str(exc)[:200],
            "not_production_grade": True, "writeback_performed": False,
            "teacher_review_required": True,
        }


def _attach_open_world_diagnostic(
    payload: dict[str, Any],
    *,
    followup_question_context: dict[str, Any] | None,
    user_message: str,
    answer: str,
) -> None:
    """M27 wrapper-side route/append for open-world diagnostic live integration.

    Pure routing: the compiled-context assembly and open-world labelling live in the fat skills
    (`compiled_context` + `open_world_diagnostic`). This attaches their output to the followup
    payload so the live `/api/v1/ws` followup surface reads the SAME unified schema as the other
    surfaces. It never decides correctness, never fabricates an official score / answer_key /
    textbook source. Best-effort: any failure leaves legacy followup behaviour untouched."""
    try:
        from deeptutor.services.construction_grading.compiled_context import (
            build_pack_from_question_context,
        )
        pack = build_pack_from_question_context(followup_question_context or {})
    except Exception:  # noqa: BLE001 — never break legacy followup
        return
    payload["compiled_context"] = pack.to_dict()
    # Open-world diagnostic ONLY when the question is not resolvable to canonical grading authority.
    if pack.official_score_allowed or pack.status == "resolved":
        return
    try:
        from deeptutor.services.construction_grading.open_world_diagnostic import (
            build_open_world_diagnostic,
        )
        diag = build_open_world_diagnostic(
            pack=pack, student_prompt=user_message, diagnosis_override=answer,
        )
    except Exception:  # noqa: BLE001
        return
    payload["open_world_diagnostic"] = diag.to_unified_schema()


def _learning_evidence_preview_disabled() -> bool:
    """Emergency kill switch for the gap_1 Learning-Brain preview emission.

    Default ENABLED so the live grading surface actually exercises the unified
    ``build_learning_evidence_from_context_pack`` consumer (production calls were 0).
    Set ``LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED=1`` to fall back to legacy
    byte-identical payloads."""
    import os

    return str(os.getenv("LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _maybe_attach_learning_evidence_preview(
    *,
    graded_context: dict[str, Any],
    result_payload: dict[str, Any],
    turn_id: str = "",
    session_id: str = "",
) -> None:
    """gap_1 / M28: emit a Learning-Brain PREVIEW from the SAME compiled context the
    grading surface used, so the live ``/api/v1/ws`` grading runtime — not only offline
    scripts — feeds ``build_learning_evidence_from_context_pack``.

    Thin wrapper: ALL policy lives in the fat skill (``learning_evidence``). This only
    routes the already-graded result + its compiled context into the consumer and
    appends the preview. It NEVER raises mastery (``mastery_raised`` is always False),
    NEVER writes canonical truth (``canonical_truth_written`` is always False), and
    NEVER mutates the legacy ``construction_grading_result``. The fat skill decides the
    per-question ``preview_only`` / ``claim_promotion_allowed`` flags from the pack's
    ``diagnostic_policy`` (governed/official questions may set them so the Learning Brain
    can promote; candidate/open-world questions stay preview). Best-effort: any failure
    leaves legacy behaviour untouched (fail-closed)."""
    if _learning_evidence_preview_disabled():
        return
    grading_result = graded_context.get("construction_grading_result")
    if not isinstance(grading_result, dict) or not grading_result:
        return
    try:
        compiled_context = grading_result.get("compiled_context")
        if not isinstance(compiled_context, dict) or not compiled_context:
            from deeptutor.services.construction_grading.compiled_context import (
                build_pack_from_question_context,
            )

            compiled_context = build_pack_from_question_context(graded_context).to_dict()
        from deeptutor.services.construction_grading.learning_evidence import (
            build_learning_evidence_from_context_pack,
        )

        preview = build_learning_evidence_from_context_pack(
            grading_result=grading_result,
            compiled_context=compiled_context,
            turn_id=turn_id,
            session_id=session_id,
        )
    except Exception:  # noqa: BLE001 — preview must never break legacy grading
        return
    result_payload["learning_evidence_preview"] = preview


class DeepQuestionCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="deep_question",
        description="Fast question generation (Template batches -> Generate).",
        stages=["ideation", "generation"],
        tools_used=["rag", "web_search"],
        cli_aliases=["quiz"],
        request_schema=get_capability_request_schema("deep_question"),
    )

    @staticmethod
    def _extract_latest_next_training_signal(
        active_object: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """plan §Batch E.1 Gap 6 — pull (concept, focus) from latest grading signal.

        Looks at active_object.state_snapshot for ``construction_grading_result``
        directly or inside items[i]; returns ``("", "")`` if nothing usable.
        """
        if not isinstance(active_object, dict):
            return "", ""
        snapshot = active_object.get("state_snapshot")
        if not isinstance(snapshot, dict):
            return "", ""

        def _signal_from(node: dict[str, Any]) -> dict[str, Any] | None:
            grading_result = node.get("construction_grading_result")
            if isinstance(grading_result, dict):
                signal = grading_result.get("next_training_signal")
                if isinstance(signal, dict):
                    return signal
            return None

        signal = _signal_from(snapshot)
        if not signal:
            for item in snapshot.get("items") or []:
                if isinstance(item, dict):
                    signal = _signal_from(item)
                    if signal:
                        break
        if not isinstance(signal, dict):
            return "", ""
        concept = str(signal.get("concept") or "").strip()
        focus = str(signal.get("focus") or "").strip()
        return concept, focus

    @staticmethod
    def _normalize_learning_training_intent(value: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        intent = {
            "source": str(value.get("source") or "learning_report").strip(),
            "training_intent_id": str(value.get("training_intent_id") or "").strip(),
            "concept_id": str(value.get("concept_id") or "").strip(),
            "concept_label": str(value.get("concept_label") or "").strip(),
            "error_code": str(value.get("error_code") or "").strip(),
            "error_label": str(value.get("error_label") or "").strip(),
            "training_mode": str(value.get("training_mode") or "").strip(),
        }
        try:
            intent["question_count"] = max(1, min(int(value.get("question_count") or 3), 5))
        except (TypeError, ValueError):
            intent["question_count"] = 3
        if not (intent["training_intent_id"] or intent["concept_id"] or intent["concept_label"] or intent["error_label"]):
            return {}
        return intent

    @staticmethod
    def _learning_training_intent_from_personalization_context(
        personalization_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(personalization_context, dict):
            return {}
        raw_intent = personalization_context.get("active_training_intent")
        if not isinstance(raw_intent, dict) or not raw_intent:
            return {}
        if raw_intent.get("active") is False:
            return {}
        state = str(
            raw_intent.get("status")
            or raw_intent.get("state")
            or raw_intent.get("intent_status")
            or ""
        ).strip().lower()
        if state in {"inactive", "stale", "superseded", "rejected", "closed", "completed"}:
            return {}
        intent = dict(raw_intent)
        intent.setdefault("source", "PersonalizationContextPack")
        if not intent.get("training_mode"):
            intent["training_mode"] = intent.get("mode") or intent.get("recommended_mode") or ""
        return DeepQuestionCapability._normalize_learning_training_intent(intent)

    @staticmethod
    def _resolve_learning_training_intent(
        *,
        overrides: dict[str, Any],
        metadata: dict[str, Any],
        followup_question_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        override_intent = DeepQuestionCapability._normalize_learning_training_intent(
            overrides.get("learning_training_intent")
            if isinstance(overrides.get("learning_training_intent"), dict)
            else None
        )
        if override_intent:
            return override_intent

        top_level = metadata.get("personalization_context") if isinstance(metadata, dict) else None
        intent = DeepQuestionCapability._learning_training_intent_from_personalization_context(
            top_level if isinstance(top_level, dict) else None
        )
        if intent:
            return intent

        nested = (
            followup_question_context.get("personalization_context")
            if isinstance(followup_question_context, dict)
            else None
        )
        return DeepQuestionCapability._learning_training_intent_from_personalization_context(
            nested if isinstance(nested, dict) else None
        )

    @staticmethod
    def _apply_learning_training_intent_to_topic(topic: str, intent: dict[str, Any]) -> str:
        if not isinstance(intent, dict) or not intent:
            return str(topic or "").strip()
        hint_parts = []
        for label, key in (
            ("concept", "concept_id"),
            ("concept_label", "concept_label"),
            ("error", "error_code"),
            ("error_label", "error_label"),
            ("training_mode", "training_mode"),
        ):
            value = str(intent.get(key) or "").strip()
            if value and value not in str(topic or ""):
                hint_parts.append(f"{label}={value}")
        if not hint_parts:
            return str(topic or "").strip()
        return (str(topic or "").strip() + "；" if str(topic or "").strip() else "") + "；".join(hint_parts)

    @staticmethod
    def _attach_learning_training_intent_to_active_object(
        active_object: dict[str, Any],
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(active_object, dict) or not isinstance(intent, dict) or not intent:
            return active_object
        updated = dict(active_object)
        snapshot = dict(updated.get("state_snapshot") or {})
        snapshot["training_intent_id"] = str(intent.get("training_intent_id") or "").strip()
        snapshot["learning_training_intent"] = dict(intent)
        updated["state_snapshot"] = snapshot
        return updated

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        from deeptutor.agents.question.coordinator import AgentCoordinator
        from deeptutor.services.llm.config import get_llm_config
        from deeptutor.services.path_service import get_path_service
        from deeptutor.services.question_lifecycle_skills import (
            project_question_lifecycle_scene_from_metadata,
        )

        # Capabilities are downstream readers of ChatOrchestrator's lifecycle
        # decision. Project skill names/trace from metadata, but never derive a
        # scene here; otherwise deep_question becomes a second route authority.
        lifecycle_scene = project_question_lifecycle_scene_from_metadata(context)

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
        # plan §Phase 5 / Batch E Gap 4 — 从 RAW context.metadata.active_object 直读 recent_outcomes
        # (normalize_active_object 会通过 normalize_question_followup_context drop 非标字段)
        # 这样 difficulty pacing 才能消费上一轮 grading 写入的滑动窗口。
        _raw_active_object = context.metadata.get('active_object') if isinstance(context.metadata, dict) else None
        if isinstance(_raw_active_object, dict):
            _raw_snap = _raw_active_object.get('state_snapshot')
            if isinstance(_raw_snap, dict):
                _hist = [bool(o) for o in (_raw_snap.get('recent_outcomes') or []) if isinstance(o, bool)]
                if _hist and isinstance(context.metadata, dict):
                    context.metadata.setdefault('recent_grading_outcomes', _hist)
        suspended_object_stack = normalize_suspended_object_stack(
            context.metadata.get("suspended_object_stack")
        )
        turn_semantic_decision = normalize_turn_semantic_decision(
            context.metadata.get("turn_semantic_decision")
        ) or {}
        followup_question_context = question_context_from_active_object(active_object) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        question_review_mode = bool(overrides.get("question_review_mode")) or (
            lifecycle_scene == "question_review"
            and not (
                isinstance(followup_question_context, dict)
                and followup_question_context.get("question")
            )
        )
        if question_review_mode and isinstance(context.metadata, dict):
            trace_meta = context.metadata.setdefault("trace_metadata", {})
            if isinstance(trace_meta, dict):
                trace_meta["question_lifecycle_scene"] = "question_review"
                trace_meta["review_mode"] = "question_review"
                trace_meta["reveal_allowed"] = True
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
                (
                    graded_context,
                    authority_source,
                    correct_answer_present,
                ) = await self._prepare_grading_context(
                    action_context=action_context,
                    metadata=context.metadata,
                    raw_user_message=raw_user_message,
                )
                await self._emit_grading_result(
                    stream=stream,
                    context=context,
                    llm_config=llm_config,
                    turn_id=turn_id,
                    active_object=active_object,
                    suspended_object_stack=suspended_object_stack,
                    turn_semantic_decision=turn_semantic_decision,
                    graded_context=graded_context,
                    raw_user_message=raw_user_message,
                    selected_mode=selected_mode,
                    authority_source=authority_source,
                    correct_answer_present=correct_answer_present,
                    kb_name=kb_name,
                )
                return

            if next_action == "route_to_followup_explainer":
                if self._is_unresolved_switch_followup(turn_semantic_decision):
                    # P1-Y: the learner referenced switching/returning to a DIFFERENT
                    # question ("回到刚才屋面那道") but the runtime could not resolve it,
                    # so the decision fell back to a followup on the current (stale)
                    # active object. Do NOT answer the stale question as if it were the
                    # referenced one — clarify instead (no context-guess authority grab).
                    await self._emit_unresolved_switch_clarification(
                        stream=stream,
                        turn_id=turn_id,
                        active_object=active_object,
                        suspended_object_stack=suspended_object_stack,
                        turn_semantic_decision=turn_semantic_decision,
                    )
                    return
                await self._emit_followup_result(
                    stream=stream,
                    context=context,
                    llm_config=llm_config,
                    turn_id=turn_id,
                    active_object=active_object,
                    suspended_object_stack=suspended_object_stack,
                    turn_semantic_decision=turn_semantic_decision,
                    followup_question_context=followup_question_context,
                    raw_user_message=raw_user_message,
                )
                return

            if allow_legacy_followup_fallback and self._prefer_followup_without_semantic_decision(
                turn_semantic_decision=turn_semantic_decision,
                followup_action=followup_action,
                question_context=followup_question_context,
                user_message=context.user_message,
            ):
                await self._emit_followup_result(
                    stream=stream,
                    context=context,
                    llm_config=llm_config,
                    turn_id=turn_id,
                    active_object=active_object,
                    suspended_object_stack=suspended_object_stack,
                    turn_semantic_decision=turn_semantic_decision,
                    followup_question_context=followup_question_context,
                    raw_user_message=raw_user_message,
                    force_default_decision=True,
                )
                return

            if allow_legacy_followup_fallback:
                target_context, submission = resolve_submission_attempt(
                    raw_user_message,
                    followup_question_context,
                )
                if target_context and submission:
                    action_context = apply_followup_action_to_context(
                        target_context,
                        self._followup_action_from_submission(submission),
                    )
                    (
                        graded_context,
                        authority_source,
                        correct_answer_present,
                    ) = await self._prepare_grading_context(
                        action_context=action_context,
                        metadata=context.metadata,
                        raw_user_message=raw_user_message,
                    )
                    await self._emit_grading_result(
                        stream=stream,
                        context=context,
                        llm_config=llm_config,
                        turn_id=turn_id,
                        active_object=active_object,
                        suspended_object_stack=suspended_object_stack,
                        turn_semantic_decision=turn_semantic_decision,
                        graded_context=graded_context,
                        raw_user_message=raw_user_message,
                        selected_mode=selected_mode,
                        authority_source=authority_source,
                        correct_answer_present=correct_answer_present,
                        kb_name=kb_name,
                    )
                    return

                await self._emit_followup_result(
                    stream=stream,
                    context=context,
                    llm_config=llm_config,
                    turn_id=turn_id,
                    active_object=active_object,
                    suspended_object_stack=suspended_object_stack,
                    turn_semantic_decision=turn_semantic_decision,
                    followup_question_context=followup_question_context,
                    raw_user_message=raw_user_message,
                )
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
        learning_training_intent = self._resolve_learning_training_intent(
            overrides=overrides,
            metadata=context.metadata,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
        )
        if learning_training_intent:
            topic = self._apply_learning_training_intent_to_topic(topic, learning_training_intent)
            if isinstance(context.metadata, dict):
                trace_meta = context.metadata.setdefault("trace_metadata", {})
                if isinstance(trace_meta, dict):
                    trace_meta["learning_training_intent_id"] = learning_training_intent.get("training_intent_id")
        num_questions = int(overrides.get("num_questions", 1) or 1)
        if learning_training_intent.get("question_count"):
            num_questions = int(learning_training_intent["question_count"])
        difficulty = str(overrides.get("difficulty", "") or "")
        question_type = str(overrides.get("question_type", "") or "")
        preference = str(overrides.get("preference", "") or "")
        reveal_answers = bool(overrides.get("reveal_answers", False))
        reveal_explanations = bool(overrides.get("reveal_explanations", reveal_answers))
        if question_review_mode:
            reveal_answers = True
            reveal_explanations = True
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
            or question_review_mode
        )

        # plan §Phase 5 / Batch E.1 Gap 6 — lightweight 出题入口主动消费 latest
        # next_training_signal。来源优先级：
        #   1. active_object.state_snapshot.construction_grading_result.next_training_signal
        #   2. active_object.state_snapshot.items[i].construction_grading_result.next_training_signal
        # 把 concept / focus 拼到 topic（如尚未出现），以便 coordinator anchor 命中 weak point。
        next_training_signal_consumed = False
        if lightweight_generation:
            consumed_concept, consumed_focus = self._extract_latest_next_training_signal(active_object)
            hint_parts: list[str] = []
            if consumed_concept and consumed_concept not in topic:
                hint_parts.append(f"上一轮薄弱点 concept={consumed_concept}")
            if consumed_focus and consumed_focus not in topic:
                hint_parts.append(f"focus={consumed_focus}")
            if hint_parts:
                topic = (topic + "；" if topic else "") + "；".join(hint_parts)
                next_training_signal_consumed = True
                if isinstance(context.metadata, dict):
                    trace_meta = context.metadata.setdefault("trace_metadata", {})
                    if isinstance(trace_meta, dict):
                        trace_meta["practice_generation.next_training_signal_consumed"] = True
                        if consumed_concept:
                            trace_meta["practice_generation.next_training_signal_concept"] = consumed_concept

        require_explanation = reveal_explanations
        has_active_question_context = _has_active_question_context(
            followup_question_context if isinstance(followup_question_context, dict) else None
        )
        general_knowledge_result_payload: dict[str, Any] = {}
        if not has_active_question_context:
            _maybe_attach_general_knowledge_context(
                context=context,
                result_payload=general_knowledge_result_payload,
            )
        general_knowledge_grounding = _format_general_knowledge_grounding(
            general_knowledge_result_payload.get("luban_general_knowledge_context")
        )
        history_context = "\n\n".join(
            part
            for part in [
                str(context.metadata.get("conversation_context_text", "") or "").strip(),
                general_knowledge_grounding,
            ]
            if part
        ).strip()
        enabled_tools = set(
            filter_end_user_tools(
                self.manifest.tools_used
                if context.enabled_tools is None
                else context.enabled_tools
            )
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
                    allow_lightweight_fallback=not question_review_mode,
                    allow_similar_source_variant=question_review_mode,
                )

        if question_review_mode:
            result = _promote_question_review_result(result)
            if _question_review_renderable(result):
                if isinstance(context.metadata, dict):
                    trace_meta = context.metadata.setdefault("trace_metadata", {})
                    if isinstance(trace_meta, dict):
                        trace_meta["question_review.bank_hit"] = _question_review_bank_hit(result)
                        trace_meta["question_review.renderable"] = True
                        trace_meta["question_review.variant_mode"] = _question_review_variant_hit(result)
            else:
                if isinstance(context.metadata, dict):
                    trace_meta = context.metadata.setdefault("trace_metadata", {})
                    if isinstance(trace_meta, dict):
                        trace_meta["question_review.bank_hit"] = False
                        trace_meta["question_review.renderable"] = False
                        trace_meta["question_review.variant_mode"] = False
                        trace_meta["question_review.degraded_reason"] = "missing_question_bank_hit"
                content = _render_missing_question_review_feedback(topic)
                if not answer_citations_enabled():
                    await stream.content(content, source=self.name, stage="generation")
                await self._emit_result_with_citations(
                    stream,
                    {
                        "response": content,
                        "mode": mode,
                        "question_followup_context": {},
                        "active_object": {},
                        "turn_semantic_decision": self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=active_object,
                            question_context=None,
                            user_message=context.user_message,
                        ),
                        "metadata": {
                            "question_lifecycle_scene": "question_review",
                            "review_mode": "missing_question",
                        },
                    },
                )
                return

        result = _clamp_result_question_count(result, num_questions)

        # plan §Phase 0 Step 0.3 (B3) — single-writer trace 字段。
        # coordinator 在 result["trace"]["lightweight_counters"] 累加；
        # 这里 capability 一次性 flush 到 context.metadata.trace_metadata。
        if isinstance(context.metadata, dict):
            trace_meta = context.metadata.setdefault("trace_metadata", {})
            if isinstance(trace_meta, dict):
                counters = (
                    (result.get("trace") or {}).get("lightweight_counters") if isinstance(result.get("trace"), dict) else None
                )
                if isinstance(result.get("trace"), dict):
                    trace = result["trace"]
                    if trace.get("clamped_question_count"):
                        trace_meta["practice_generation.generated_question_count"] = int(
                            trace.get("generated_question_count") or 0
                        )
                        trace_meta["practice_generation.clamped_question_count"] = int(
                            trace.get("clamped_question_count") or 0
                        )
                if isinstance(counters, dict):
                    trace_meta["practice_generation.llm_calls"] = int(counters.get("llm_calls") or 0)
                    trace_meta["practice_generation.retriever_calls"] = int(counters.get("retriever_calls") or 0)
                    trace_meta["practice_generation.bank_hits"] = int(counters.get("bank_hits") or 0)
                    trace_meta["practice_generation.generated_explanation"] = bool(counters.get("generated_explanation"))
                    trace_meta["practice_generation.lightweight_batch_fallback"] = str(
                        counters.get("lightweight_batch_fallback") or "none"
                    )

        content = self._render_summary_markdown(
            result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
            review_mode=question_review_mode,
        )
        generation_citation_enabled = answer_citations_enabled()
        if content and not generation_citation_enabled:
            await stream.content(content, source=self.name, stage="generation")

        presentation = build_canonical_presentation(
            content=content or "",
            result_summary=result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
            review_mode=question_review_mode,
        )
        result_payload: dict[str, Any] = {
            "response": content or "No questions generated.",
            "mode": mode,
        }
        if question_review_mode:
            result_payload["question_followup_context"] = {}
            result_payload["active_object"] = {}
        else:
            result_payload["question_followup_context"] = (
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
            )
            trace_metadata = _question_authority_metadata(context.metadata)
            if result_payload["question_followup_context"] and trace_metadata:
                recovered_context, _, _ = _recover_missing_mcq_authority(
                    result_payload["question_followup_context"],
                    trace_metadata,
                )
                result_payload["question_followup_context"] = recovered_context
            result_payload["active_object"] = (
                build_active_object_from_question_context(
                    result_payload["question_followup_context"],
                    source_turn_id=turn_id,
                    previous_active_object=active_object,
                )
                or {}
            )
        if learning_training_intent:
            result_payload["active_object"] = self._attach_learning_training_intent_to_active_object(
                result_payload["active_object"],
                learning_training_intent,
            )
            result_payload["learning_training_intent"] = dict(learning_training_intent)
        result_payload["turn_semantic_decision"] = turn_semantic_decision or self._default_turn_semantic_decision(
            next_action="route_to_followup_explainer" if question_review_mode else "route_to_generation",
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
        if learning_training_intent and result_payload["active_object"]:
            result_payload["active_object"] = self._attach_learning_training_intent_to_active_object(
                result_payload["active_object"],
                learning_training_intent,
            )
        result_payload["suspended_object_stack"] = transitioned_stack
        if presentation:
            result_payload["presentation"] = presentation
        if general_knowledge_result_payload:
            result_payload.update(general_knowledge_result_payload)
        cost_meta = self._collect_cost_summary("question")
        if cost_meta:
            result_payload["metadata"] = {"cost_summary": cost_meta}
        await self._emit_result_with_citations(
            stream,
            result_payload,
            stage="generation",
            emit_content_when_enabled=bool(content),
        )

    async def _emit_result_with_citations(
        self,
        stream: StreamBus,
        result_payload: dict[str, Any],
        *,
        stage: str = "generation",
        sources: list[dict[str, Any]] | None = None,
        emit_content_when_enabled: bool = True,
    ) -> None:
        if "response" in result_payload:
            citation_enabled = answer_citations_enabled()
            citation_metadata: dict[str, Any] = {}
            result_payload["response"] = apply_answer_citation_metadata(
                citation_metadata,
                response=str(result_payload.get("response") or ""),
                sources=sources or [],
                policy=CitationPolicy(surface="student"),
                enabled=citation_enabled,
            )
            result_payload.update(citation_metadata)
            if citation_enabled and emit_content_when_enabled:
                await stream.content(
                    str(result_payload["response"] or ""),
                    source=self.name,
                    stage=stage,
                )
        await stream.result(result_payload, source=self.name)

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

    async def _prepare_grading_context(
        self,
        *,
        action_context: dict[str, Any],
        metadata: dict[str, Any],
        raw_user_message: str,
    ) -> tuple[dict[str, Any], str, bool]:
        authority_source = ""
        correct_answer_present = True
        working_context = action_context
        if _is_mcq_grading_context(working_context):
            (
                working_context,
                authority_source,
                correct_answer_present,
            ) = _recover_missing_mcq_authority(
                working_context,
                _question_authority_metadata(metadata),
            )
            if not correct_answer_present:
                # 开放世界判分：authority 三路兜底（active_object / grading_key /
                # questions_bank）全部落空时不拒答——判定权交给 RAG-grounded
                # grader agent，trace 标 open_world，不冒充题库标准答案。
                authority_source = "open_world"

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
        if not correct_answer_present:
            graded_context = _apply_open_world_grading_state(graded_context)
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
        kb_name: str | None,
    ) -> None:
        async with stream.stage("generation", source=self.name):
            citation_enabled = answer_citations_enabled()
            grounding_context = ""
            grounding_sources: list[dict[str, Any]] = []
            grounding_error = ""
            content_streamed = False
            # plan §Phase 4 Step 4.2 / Gap 4 — agent trace_collector 必须在
            # 所有分支可见（确定性反馈分支不进 agent.process，但 Gap 5 仍要
            # 输出 progressive_disclosure）。
            grader_trace: dict[str, Any] = {}
            # Grading-to-Brain V1 (flag + cohort, default off): adjudicate the compiled rubric ONCE,
            # up front, so the SAME event both (a) renders the student-facing answer (same-source: the
            # words read can never disagree with the score) and (b) feeds the structured payload below.
            # When V1 takes over we skip the legacy SubmissionGraderAgent LLM call entirely.
            v1_event = await _grade_case_rubric_v1(context=context, graded_context=graded_context)
            v1_render: str | None = None
            # Grading-to-Brain：先录制（写证据 + 构建 PCP），再渲染——练题反馈
            # 与聊天入口同样携带个性化语气（同一 recorder seam）。
            _g2b_meta = _record_v1_grading_to_brain_for_question(
                context=context,
                v1_event=v1_event,
                graded_context=graded_context,
                turn_id=turn_id,
            )
            if isinstance(v1_event, dict) and v1_event.get("event_type") == "case_grading_completed":
                from deeptutor.services.construction_grading.rubric_grader_v1 import (
                    render_case_rubric_feedback,
                )

                _stem = str(graded_context.get("question_stem") or graded_context.get("stem")
                            or graded_context.get("question") or "")
                _g2b_pcp = (
                    _g2b_meta.get("personalization_context")
                    if isinstance(_g2b_meta.get("personalization_context"), dict)
                    else None
                )
                v1_render = render_case_rubric_feedback(
                    v1_event,
                    question_stem=_stem,
                    personalization_context_pack=_g2b_pcp,
                )
            if v1_render is not None:
                answer = v1_render
                # SAME-SOURCE: when V1 renders the student answer, is_correct/score/diagnosis must come
                # from the SAME event (not V0), so recorded state (recent_outcomes / projection /
                # observability) can never disagree with what the student read.
                from deeptutor.services.construction_grading.rubric_grader_v1 import (
                    derive_outcome_from_event,
                )

                _v1_outcome = derive_outcome_from_event(v1_event)
                graded_context["is_correct"] = _v1_outcome["is_correct"]
                graded_context["score"] = _v1_outcome["score"]
                graded_context["diagnosis"] = _v1_outcome["diagnosis"]
            elif _should_use_deterministic_grading_feedback(
                selected_mode=selected_mode,
                question_context=graded_context,
                kb_name=kb_name,
            ):
                answer = _render_deterministic_grading_feedback(graded_context)
            else:
                async def _content_sink(chunk: str) -> None:
                    nonlocal content_streamed
                    if not chunk:
                        return
                    if citation_enabled:
                        return
                    content_streamed = True
                    await stream.content(chunk, source=self.name, stage="generation")

                retrieval_query = _build_grading_retrieval_query(graded_context)
                if kb_name and retrieval_query:
                    try:
                        rag_result = await rag_search(
                            retrieval_query,
                            kb_name=kb_name,
                            intent="question_grading_explanation",
                            question_type=str(graded_context.get("question_type") or "grading").strip(),
                            routing_metadata={
                                "capability": "deep_question",
                                "grading_kernel": _mcq_trace_fields(
                                    graded_context,
                                    authority_source=authority_source,
                                    correct_answer_present=correct_answer_present,
                                ).get("grading_kernel")
                                or "grading",
                                "answer_authority": authority_source or "active_object",
                            },
                        )
                        grounding_context, grounding_sources = _format_grading_grounding_context(rag_result)
                    except Exception as exc:
                        grounding_error = str(exc)
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
                # plan §Phase 4 Step 4.2 / Gap 4 — pass shared trace_collector
                # (see above) so the agent can write explanation_section_miss &
                # parsed sections back into single-writer trace.
                answer = await agent.process(
                    user_message=raw_user_message,
                    question_context=graded_context,
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                    grounding_context=grounding_context,
                    on_content_chunk=_content_sink,
                    trace_collector=grader_trace,
                )
            post_grading_next_action = _build_post_grading_generation_ack(raw_user_message)
            if post_grading_next_action:
                answer = (
                    (answer or "").rstrip()
                    + "\n\n"
                    + post_grading_next_action
                ).strip()
            if answer and not content_streamed and not citation_enabled:
                await stream.content(answer, source=self.name, stage="generation")
            elif post_grading_next_action and not citation_enabled:
                await stream.content(
                    "\n\n" + post_grading_next_action,
                    source=self.name,
                    stage="generation",
                )
            result_active_object = build_active_object_from_question_context(
                graded_context,
                source_turn_id=turn_id,
                previous_active_object=active_object,
            )
            # plan §Phase 5 / Batch E Gap 4 — push is_correct 到 active_object
            # state_snapshot.recent_outcomes 滑动窗口（最近 5）；下一轮 capability
            # run 时从同一 active_object 读，不另建 learner_state 字段。
            _current_outcome = graded_context.get('is_correct')
            if isinstance(result_active_object, dict) and isinstance(_current_outcome, bool):
                _snap = result_active_object.get('state_snapshot')
                if isinstance(_snap, dict):
                    # prev outcomes 来源优先级：
                    # 1) context.metadata.recent_grading_outcomes (由 run 入口从 raw active_object 注入)
                    # 2) result_active_object.state_snapshot.recent_outcomes (已透传)
                    # 3) active_object.state_snapshot.recent_outcomes (可能被 normalize 丢)
                    _prev_outcomes = []
                    if isinstance(context.metadata, dict):
                        _meta_prev = context.metadata.get('recent_grading_outcomes')
                        if isinstance(_meta_prev, list):
                            _prev_outcomes = [bool(o) for o in _meta_prev if isinstance(o, bool)]
                    if not _prev_outcomes:
                        _existing = _snap.get('recent_outcomes')
                        if isinstance(_existing, list):
                            _prev_outcomes = [bool(o) for o in _existing if isinstance(o, bool)]
                    if not _prev_outcomes and isinstance(active_object, dict):
                        _prev_snap = active_object.get('state_snapshot')
                        if isinstance(_prev_snap, dict):
                            _prev_outcomes = [bool(o) for o in (_prev_snap.get('recent_outcomes') or []) if isinstance(o, bool)]
                    _new_outcomes = [bool(_current_outcome)] + _prev_outcomes
                    _snap['recent_outcomes'] = _new_outcomes[:5]
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
                "grading_explanation_grounded": bool(grounding_context),
                "grading_grounding_sources": grounding_sources[:5],
            }
            if grounding_error:
                result_payload["grading_grounding_error"] = grounding_error[:240]
            # Grading-to-Brain：渲染前已录制（同一 recorder seam）。只把公开
            # 投影并入结果——v1_event 有效即合并，不依赖 legacy grading_result
            # 守卫（防"写了证据但客户端无回执"的幽灵写）。
            from deeptutor.services.construction_grading.writeback import (
                public_grading_to_brain_meta,
            )

            result_payload.update(public_grading_to_brain_meta(_g2b_meta))
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
                # QA/test-only Luban shadow (default off; legacy untouched above).
                _maybe_attach_runtime_shadow(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # rubric-v1 structured payload (flag+cohort; append-only GradingEvent + learning_evidence;
                # legacy construction_grading_result intact). Reuses the event already graded up top —
                # no second LLM call. When V1 is on, the answer above is rendered from this same event.
                _v1_payload = _case_rubric_v1_payload_from_event(
                    v1_event,
                    node_code=str(graded_context.get("node_code")
                                  or (grading_result or {}).get("node_code") or ""),
                )
                if _v1_payload is not None:
                    result_payload["luban_case_rubric_v1"] = _v1_payload

                # PGO coverage shadow (default off; env kill switch + cohort; append-only;
                # missing live PGO supply fails closed instead of inferring from legacy score).
                _maybe_attach_pgo_shadow(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # QA/test-only Luban v1 beta_shadow (default off; flag + env kill switch;
                # append-only; legacy construction_grading_result untouched above).
                _maybe_attach_v1_beta_shadow(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # M35 scoring-artifact shadow drill (default off; env kill switch + cohort;
                # append-only; legacy construction_grading_result untouched).
                _maybe_attach_m35_artifact_shadow(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # Controlled production runtime candidate (default off; flag + env kill switch +
                # cohort + release_candidate registry; append-only; legacy untouched).
                _maybe_attach_v1_controlled_runtime(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # Runtime LLM adjudication candidate (default off; flag + env kill switch + cohort;
                # DeepSeek/Qwen adjudication gated by deterministic validator; append-only).
                _maybe_attach_v1_llm_adjudication(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # Objective answer-key CANDIDATE lane (M25-B; default off; flag + cohort; answer_key
                # is sole authority, LLM cannot decide correctness; append-only; candidate_unverified;
                # fail-closed on tamper, fail-open open-world on not-in-bank; legacy untouched).
                _maybe_attach_objective_candidate(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # M31 governed objective release-candidate lane (default off; flag + env kill switch +
                # cohort; signed governed answer_key -> CONTROLLED release-truth; append-only; legacy
                # construction_grading_result untouched; LLM cannot decide correctness; fail-closed on
                # tamper, fall-through to candidate/open-world on governed miss).
                _maybe_attach_m31_governed_objective(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # Verbatim 2026-textbook knowledge context for the turn's node_code (default off;
                # flag + env kill switch + cohort; append-only; teaching/source context, not a score).
                _maybe_attach_textbook_knowledge(
                    context=context,
                    graded_context=graded_context,
                    result_payload=result_payload,
                )
                # gap_1 / M28: feed the SAME compiled context into the Learning-Brain
                # consumer from the LIVE grading runtime (preview only; env kill switch;
                # append-only; never raises mastery / writes canonical truth / mutates legacy).
                _maybe_attach_learning_evidence_preview(
                    graded_context=graded_context,
                    result_payload=result_payload,
                    turn_id=turn_id,
                    session_id=str(context.session_id or ""),
                )

            # plan §Phase 5 / Batch E.2 Gap 5 — progressive disclosure payload.
            # 从 grader_trace 拿到 parsed sections，结合 grading_result 与 is_correct 输出
            # verdict / one_line_diagnosis / primary_next_action / secondary_actions / sections。
            try:
                from deeptutor.agents.question.agents.submission_grader_schema import (
                    ExplanationSections,
                )
                from deeptutor.services.construction_grading.progressive_disclosure import (
                    build_progressive_disclosure,
                    classify_difficulty_pacing,
                )

                sections_dict = grader_trace.get("explanation_sections") if isinstance(grader_trace, dict) else {}
                if not isinstance(sections_dict, dict):
                    sections_dict = {}
                question_type_value = str(graded_context.get("question_type") or "choice").strip().lower()
                is_correct_value = graded_context.get("is_correct")
                parsed = ExplanationSections(
                    sections=dict(sections_dict),
                    question_type=question_type_value,
                    is_correct=is_correct_value if isinstance(is_correct_value, bool) else None,
                )
                # Difficulty pacing: 读最近 grading outcomes（present in context.metadata if available）。
                recent_outcomes = []
                recent_meta = context.metadata.get("recent_grading_outcomes") if isinstance(context.metadata, dict) else None
                if isinstance(recent_meta, list):
                    for item in recent_meta:
                        if isinstance(item, bool):
                            recent_outcomes.append(item)
                # 把当前 outcome 加到最前面（最新）
                if isinstance(is_correct_value, bool):
                    recent_outcomes.insert(0, is_correct_value)
                pacing = classify_difficulty_pacing(recent_outcomes)
                grading_source = ""
                signal = (
                    grading_result.get("next_training_signal") if isinstance(grading_result, dict) else None
                )
                if isinstance(signal, dict):
                    grading_source = str(signal.get("grading_source") or "").strip()
                disclosure = build_progressive_disclosure(
                    explanation=parsed,
                    is_correct=is_correct_value if isinstance(is_correct_value, bool) else None,
                    grading_source=grading_source,
                    pacing=pacing,
                ).to_dict()
                result_payload["progressive_disclosure"] = disclosure
            except Exception as exc:
                # 失败不阻断主链；仅记录 trace。
                if isinstance(context.metadata, dict):
                    trace_meta = context.metadata.setdefault("trace_metadata", {})
                    if isinstance(trace_meta, dict):
                        trace_meta["progressive_disclosure_error"] = str(exc)[:200]

            # plan §Phase 0 Step 0.3 (B3) — flush schema/grader trace fields.
            if isinstance(context.metadata, dict):
                trace_meta = context.metadata.setdefault("trace_metadata", {})
                if isinstance(trace_meta, dict):
                    miss = grader_trace.get("explanation_section_miss") if isinstance(grader_trace, dict) else None
                    if miss is not None:
                        trace_meta["explanation_section_miss"] = list(miss)
                    if isinstance(grading_result, dict):
                        signal = grading_result.get("next_training_signal")
                        if isinstance(signal, dict):
                            trace_meta["construction_grading_result.grading_source"] = str(
                                signal.get("grading_source") or ""
                            )

            citation_sources: list[dict[str, Any]] = [
                item for item in grounding_sources[:5] if isinstance(item, dict)
            ]
            grading_refs = grading_result.get("evidence_refs") if isinstance(grading_result, dict) else None
            if isinstance(grading_refs, list):
                citation_sources.extend(item for item in grading_refs if isinstance(item, dict))
            original_response = str(result_payload.get("response") or "")
            citation_metadata: dict[str, Any] = {}
            result_payload["response"] = apply_answer_citation_metadata(
                citation_metadata,
                response=original_response,
                sources=citation_sources,
                policy=CitationPolicy(surface="student"),
                enabled=citation_enabled,
            )
            result_payload.update(citation_metadata)
            if citation_enabled:
                await stream.content(
                    str(result_payload["response"] or ""),
                    source=self.name,
                    stage="generation",
                )

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
        raw_user_message: str,
        force_default_decision: bool = False,
    ) -> None:
        async with stream.stage("generation", source=self.name):
            if should_block_unanswered_reference_reveal(
                raw_user_message,
                followup_question_context,
            ):
                answer = "练习阶段不公开答案；你先作答，或明确说“我放弃这题/跳过这题”后，我再展示答案和解析。"
            elif _should_render_deterministic_reference_feedback(
                raw_user_message,
                followup_question_context,
            ):
                answer = _render_deterministic_reference_feedback(
                    followup_question_context,
                    user_message=raw_user_message,
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
                    user_message=raw_user_message,
                    question_context=followup_question_context,
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )
            if answer and not answer_citations_enabled():
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
                user_message=raw_user_message,
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
            # M27 open-world diagnostic live integration (§0.26.9). This wrapper only ROUTES + APPENDS;
            # the compiled-context assembly and open-world labelling live in the fat skills. Followup
            # is the 4th compiled-context surface. When the question is NOT resolvable to canonical
            # grading authority, the already-generated LLM answer is STRUCTURED as a labeled
            # open-world diagnostic (no official score, no answer-key / source fabrication).
            _attach_open_world_diagnostic(
                followup_payload,
                followup_question_context=followup_question_context,
                user_message=raw_user_message,
                answer=str(answer or ""),
            )
            cost_meta = self._collect_cost_summary("question")
            if cost_meta:
                followup_payload["metadata"] = {"cost_summary": cost_meta}
            await self._emit_result_with_citations(
                stream,
                followup_payload,
                stage="generation",
                sources=_citation_sources_from_question_context(followup_question_context),
                emit_content_when_enabled=bool(answer),
            )

    @staticmethod
    def _is_unresolved_switch_followup(turn_semantic_decision: dict[str, Any] | None) -> bool:
        """True for the failed-switch signature (P1-Y).

        The learner asked to switch/return to a DIFFERENT question, but the runtime
        could not resolve a concrete target, so the decision degraded to a followup
        on the current active object. ``switch_to_new_object`` never legitimately
        co-occurs with ``route_to_followup_explainer`` (a real switch resolves a new
        active object and routes to generation/grading; a real followup carries
        ``ask_about_active_object`` / ``answer_active_object``). So this exact combo
        is the unambiguous "wanted a different question, fell back to the stale one"
        case — answer it as a clarification, not a stale-object followup.
        """

        decision = turn_semantic_decision if isinstance(turn_semantic_decision, dict) else {}
        return (
            str(decision.get("relation_to_active_object") or "").strip() == "switch_to_new_object"
            and str(decision.get("next_action") or "").strip() == "route_to_followup_explainer"
        )

    async def _emit_unresolved_switch_clarification(
        self,
        *,
        stream: StreamBus,
        turn_id: str,
        active_object: dict[str, Any] | None,
        suspended_object_stack: list[dict[str, Any]] | None,
        turn_semantic_decision: dict[str, Any] | None,
    ) -> None:
        """Fail-closed clarification when a switch/return target cannot be resolved.

        Keeps the current active object untouched (state is not lost) and refuses to
        present the current question's answer as if it were the referenced one.
        """

        async with stream.stage("generation", source=self.name):
            answer = (
                "你想回到/切换到的那道题，这一轮我没能定位到——当前正在进行的不是它。\n\n"
                "请把那道题的题干和选项重新发我，或告诉我题号，我再按那道题讲解。"
                "我不会拿当前这道题的答案，冒充你问的那道题。"
            )
            if not answer_citations_enabled():
                await stream.content(answer, source=self.name, stage="generation")
            payload: dict[str, Any] = {
                "response": answer,
                "mode": "clarification",
                "question_authority_source": "unresolved_switch_clarification",
                "execution_path": "deep_question_unresolved_switch_clarification",
                "clarification_reason": "unresolved_switch_target",
                "question_followup_context": {},
                "active_object": normalize_active_object(active_object) or {},
                "suspended_object_stack": suspended_object_stack or [],
                "turn_semantic_decision": turn_semantic_decision or {},
                "reveal_answers": False,
                "reveal_explanations": False,
                "metadata": {
                    "needs_clarification": True,
                    "clarification_reason": "unresolved_switch_target",
                    "turn_id": turn_id,
                },
            }
            await self._emit_result_with_citations(
                stream,
                payload,
                stage="generation",
                emit_content_when_enabled=True,
            )

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
            return f"正在生成{qid} ({current}/{total})"

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
            return f"{qid}已生成 ({ordinal}{qt}/{diff}, success={success})"

        return update.get("message", update_type)

    @staticmethod
    def _humanize_question_id(question_id: Any) -> str:
        raw = str(question_id or "").strip()
        match = re.fullmatch(r"q_(\d+)", raw.lower())
        if match:
            return f"第 {match.group(1)} 题"
        return raw or "题目"

    def _render_summary_markdown(
        self,
        summary: dict[str, Any],
        *,
        reveal_answers: bool = False,
        reveal_explanations: bool = False,
        review_mode: bool = False,
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

            lines.append(f"### 第 {idx} 题\n")
            lines.append(question)

            options = qa_pair.get("options", {})
            if isinstance(options, dict) and options:
                for key, value in options.items():
                    lines.append(f"- {key}. {value}")

            answer = qa_pair.get("correct_answer", "")
            if review_mode:
                grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else {}
                metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
                if metadata.get("question_review_variant_mode") is True:
                    notice = str(
                        metadata.get("variant_notice")
                        or "基于题库/知识库相似来源生成的变式题，不是原题复刻。"
                    ).strip()
                    if notice:
                        lines.append(f"\n> {notice}")
                display_answer = str(answer or grading_key.get("correct_answer") or "").strip()
                if display_answer:
                    lines.append(f"\n**正确答案：** {display_answer}")
                explanation = str(
                    qa_pair.get("explanation")
                    or grading_key.get("minimal_rationale")
                    or metadata.get("knowledge_context")
                    or ""
                ).strip()
                if explanation:
                    lines.append(f"\n**解析要点：** {explanation}")
                scoring_points = self._string_list(
                    qa_pair.get("scoring_points"),
                    metadata.get("scoring_points"),
                    grading_key.get("scoring_points"),
                )
                if not scoring_points:
                    scoring_points = self._default_review_scoring_points(
                        question=question,
                        answer=display_answer,
                    )
                if scoring_points:
                    lines.append("\n**采分点：**")
                    lines.extend(f"- {item}" for item in scoring_points)
                option_analysis = metadata.get("option_analysis") or qa_pair.get("option_analysis")
                option_rows = option_analysis if isinstance(option_analysis, list) else []
                if option_rows:
                    lines.append("\n**逐项分析：**")
                    for row in option_rows:
                        if not isinstance(row, dict):
                            continue
                        key = str(row.get("key") or "").strip()
                        verdict = str(row.get("verdict") or "").strip()
                        analysis = str(row.get("analysis") or "").strip()
                        if key and (verdict or analysis):
                            lines.append(f"- {key}：{verdict}。{analysis}".rstrip("。") + "。")
                pitfalls = self._string_list(
                    qa_pair.get("pitfalls"),
                    qa_pair.get("common_mistakes"),
                    metadata.get("pitfalls"),
                    metadata.get("common_mistakes"),
                    grading_key.get("common_traps"),
                )
                if not pitfalls:
                    pitfalls = self._default_review_pitfalls(
                        question=question,
                        answer=display_answer,
                    )
                if pitfalls:
                    lines.append("\n**易错点：**")
                    lines.extend(f"- {item}" for item in pitfalls)
                mnemonic = str(
                    qa_pair.get("mnemonic")
                    or qa_pair.get("memory_tip")
                    or metadata.get("mnemonic")
                    or metadata.get("memory_tip")
                    or ""
                ).strip()
                if not mnemonic and display_answer:
                    mnemonic = f"先圈题干对象，再锁定答案 {display_answer}。"
                if mnemonic:
                    lines.append(f"\n**记忆口诀：** {mnemonic}")
                lines.append("")
                continue

            if reveal_answers and answer:
                lines.append(f"\n**答案：** {answer}")

            explanation = qa_pair.get("explanation", "")
            if reveal_explanations and explanation:
                lines.append(f"\n**解析：** {explanation}")

            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _string_list(*values: Any) -> list[str]:
        for value in values:
            if not isinstance(value, list):
                continue
            items = [str(item or "").strip() for item in value]
            items = [item for item in items if item]
            if items:
                return items
        return []

    @staticmethod
    def _default_review_scoring_points(*, question: Any, answer: str) -> list[str]:
        stem = str(question or "").strip()
        points = ["先圈出题干限定对象和关键词。"]
        if answer:
            points.append(f"把标准答案 {answer} 与题干限定条件对应起来。")
        points.append("逐项排除与题干对象、数值或规范条件不一致的干扰项。")
        if "保护层" in stem:
            points[0] = "先圈出构件类型、环境条件和保护层厚度要求。"
        return points

    @staticmethod
    def _default_review_pitfalls(*, question: Any, answer: str) -> list[str]:
        stem = str(question or "").strip()
        if "保护层" in stem:
            return [
                "只记住保护层厚度考点，但没有先判断题干限定的构件和环境。",
                "把相近数值当成规范值，忽略“不应小于”等关键词。",
            ]
        pitfall = "只看选项熟悉度，没有回到题干限定条件。"
        if answer:
            return [pitfall, f"知道答案是 {answer} 后，要反推它对应的规范抓手。"]
        return [pitfall]

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
