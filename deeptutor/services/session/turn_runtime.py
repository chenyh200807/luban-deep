"""
Turn-level runtime manager for unified chat streaming.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Sequence
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import math
import os
import re
import sqlite3
import time
from types import SimpleNamespace
from typing import Any

from deeptutor.api.runtime_metrics import (
    get_turn_runtime_metrics,
    normalize_latency_stage_timings,
)
from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.contracts.bot_runtime_defaults import (
    resolve_bot_runtime_defaults as resolve_bot_binding_defaults,
)
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.logging.context import bind_log_context, reset_log_context
from deeptutor.services.exam_track import (
    exam_track_label,
    has_multiple_exam_track_mentions,
    infer_denied_exam_tracks_from_text,
    infer_exam_track_from_text,
    normalize_exam_track,
)
from deeptutor.services.internal_qa import (
    internal_qa_billing_bypass_allowed,
    internal_qa_billing_bypass_enabled,
)
from deeptutor.services.observability import (
    get_langfuse_observability,
    get_release_lineage_metadata,
    get_surface_event_store,
    get_turn_event_log,
)
from deeptutor.services.observability.aae_scores import build_turn_aae_metadata
from deeptutor.services.observability.turn_event_log import build_turn_observation_event
from deeptutor.services.path_service import get_path_service
from deeptutor.services.question_followup import (
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_result_summary,
    followup_action_route,
    interpret_question_followup_action,
    looks_like_question_followup,
    normalize_question_followup_context,
    reset_question_submission_state,
    resolve_submission_attempt,
)
from deeptutor.services.question_lifecycle_skills import (
    looks_like_free_text_mcq_grading_request,
    looks_like_free_text_mcq_question_surface,
)
from deeptutor.services.semantic_router import (
    build_turn_semantic_decision as build_semantic_turn_decision,
)
from deeptutor.services.semantic_router import (
    has_explicit_practice_generation_intent,
)
from deeptutor.services.session.sqlite_store import (
    SQLiteSessionStore,
    build_active_object_from_learning_plan_view,
    build_active_object_from_question_context,
    build_active_object_from_session,
    build_user_owner_key,
    extract_question_context_from_active_object,
    get_sqlite_session_store,
    normalize_active_object,
    normalize_suspended_object_stack,
)
from deeptutor.services.user_visible_output import (
    coerce_user_visible_answer,
    looks_like_unsafe_visible_output,
)
from deeptutor.tutorbot.markdown_style import normalize_markdown_for_tutorbot
from deeptutor.tutorbot.response_mode import (
    normalize_requested_response_mode,
    resolve_requested_response_mode,
    select_response_mode,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

logger = logging.getLogger(__name__)
observability = get_langfuse_observability()
_MINI_PROGRAM_CAPTURE_COST = 20
_MINI_PROGRAM_CAPTURE_COST_POINT_SCALE = 1000
_CAPTURED_ASSISTANT_CALL_KINDS = {"llm_final_response", "exact_authority_response"}
_PUBLIC_VISIBILITY = "public"
_INTERNAL_VISIBILITY = "internal"
_PLAN_ACTIVE_OBJECT_TYPES = {"guide_page", "study_plan"}
_PUBLIC_CANCELLED_MESSAGE = "本轮生成已取消，请重新发送或换个题目继续。"
_PUBLIC_FAILED_MESSAGE = "本轮生成失败，后台已记录问题。请稍后重试。"
_REQUEST_SNAPSHOT_REDACTED = "[redacted]"
_REQUEST_SNAPSHOT_MAX_TEXT = 4000
_REQUEST_SNAPSHOT_MAX_TOTAL_BYTES = 24000
_REQUEST_SNAPSHOT_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "base64",
    "bearer",
    "data",
    "password",
    "secret",
    "token",
)


class _ContextOrchestrationStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        super().__init__(f"{stage}: {cause}")
        self.stage = stage
        self.cause_type = type(cause).__name__


def _event_visibility(event: StreamEvent | dict[str, Any]) -> str:
    raw = (
        getattr(event, "visibility", None)
        if not isinstance(event, dict)
        else event.get("visibility")
    )
    return _INTERNAL_VISIBILITY if str(raw or "").strip().lower() == _INTERNAL_VISIBILITY else _PUBLIC_VISIBILITY


def _should_capture_assistant_content(event: StreamEvent) -> bool:
    if _event_visibility(event) != _PUBLIC_VISIBILITY:
        return False
    if event.type != StreamEventType.CONTENT:
        return False
    metadata = event.metadata or {}
    call_id = metadata.get("call_id")
    if not call_id:
        return True
    return str(metadata.get("call_kind") or "").strip() in _CAPTURED_ASSISTANT_CALL_KINDS


def _learning_prompt_intent_trace_metadata(intent: Any) -> dict[str, Any]:
    if not isinstance(intent, dict):
        return {}
    training_intent_id = str(intent.get("training_intent_id") or "").strip()
    if not training_intent_id:
        return {}
    evidence_refs = intent.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = intent.get("supporting_event_ids")
    attempt_refs = intent.get("attempt_refs")
    if not isinstance(attempt_refs, list):
        attempt_refs = intent.get("attempt_ids")
    metadata: dict[str, Any] = {
        "gbrain_training_intent_id": training_intent_id,
        "gbrain_evidence_ref_count": len(evidence_refs) if isinstance(evidence_refs, list) else 0,
        "gbrain_attempt_ref_count": len(attempt_refs) if isinstance(attempt_refs, list) else 0,
        "gbrain_prescription_authority": "training_intent",
    }
    for source_key, metadata_key in (
        ("concept_id", "gbrain_concept_id"),
        ("error_code", "gbrain_error_code"),
        ("learning_signal_type", "gbrain_learning_signal_type"),
        ("training_outcome", "gbrain_training_outcome"),
        ("outcome", "gbrain_training_outcome"),
        ("source", "gbrain_prompt_source"),
    ):
        value = str(intent.get(source_key) or "").strip()
        if value and metadata_key not in metadata:
            metadata[metadata_key] = value
    return metadata


def _extract_authoritative_assistant_content(event: StreamEvent) -> str:
    if _event_visibility(event) != _PUBLIC_VISIBILITY:
        return ""
    if event.type == StreamEventType.RESULT:
        metadata = event.metadata or {}
        response = metadata.get("response")
        if response is None and isinstance(metadata.get("metadata"), dict):
            response = metadata["metadata"].get("response")
        return str(response or "").strip()
    if event.type == StreamEventType.CONTENT:
        metadata = event.metadata or {}
        if str(metadata.get("call_kind") or "").strip() in _CAPTURED_ASSISTANT_CALL_KINDS:
            return str(event.content or "").strip()
    return ""


def _clip_text(value: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _is_sensitive_snapshot_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return any(part in normalized for part in _REQUEST_SNAPSHOT_SENSITIVE_KEY_PARTS)


def _sanitize_request_snapshot_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return _REQUEST_SNAPSHOT_REDACTED
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _clip_text(value, _REQUEST_SNAPSHOT_MAX_TEXT)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_snapshot_key(key_text):
                sanitized[key_text] = _REQUEST_SNAPSHOT_REDACTED
                continue
            sanitized[key_text] = _sanitize_request_snapshot_value(item, depth=depth + 1)
        return sanitized
    if isinstance(value, list | tuple):
        return [
            _sanitize_request_snapshot_value(item, depth=depth + 1)
            for item in value[:100]
        ]
    return _clip_text(str(value), _REQUEST_SNAPSHOT_MAX_TEXT)


def _clean_request_snapshot_attachments(
    attachments: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        record = {
            key: item.get(key)
            for key in ("type", "url", "filename", "mime_type", "extracted_text", "extracted_chars")
            if item.get(key) not in (None, "")
        }
        if record:
            cleaned.append(record)
    return cleaned


def _request_snapshot_metadata(
    *,
    payload: dict[str, Any],
    content: str,
    capability: str,
    config: dict[str, Any],
    attachments: Sequence[dict[str, Any]],
    notebook_references: Sequence[Any],
    history_references: Sequence[Any],
    question_notebook_references: Sequence[Any],
    book_references: Sequence[Any],
    requested_skills: Sequence[str],
    memory_references: Sequence[str],
    llm_selection: dict[str, Any] | None,
    turn_id: str = "",
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "content": content,
        "capability": capability,
        "enabledTools": _string_list(payload.get("tools")),
        "knowledgeBases": _string_list(payload.get("knowledge_bases")),
        "language": str(payload.get("language", "en") or "en"),
    }
    cleaned_attachments = _clean_request_snapshot_attachments(attachments)
    if cleaned_attachments:
        snapshot["attachments"] = _sanitize_request_snapshot_value(cleaned_attachments)
    if config:
        snapshot["config"] = _sanitize_request_snapshot_value(dict(config))
    if notebook_references:
        snapshot["notebookReferences"] = _sanitize_request_snapshot_value(list(notebook_references))
    if history_references:
        snapshot["historyReferences"] = _sanitize_request_snapshot_value(list(history_references))
    if question_notebook_references:
        snapshot["questionNotebookReferences"] = _sanitize_request_snapshot_value(
            list(question_notebook_references)
        )
    if book_references:
        snapshot["bookReferences"] = _sanitize_request_snapshot_value(list(book_references))
    if requested_skills:
        snapshot["skills"] = list(requested_skills)
    if memory_references:
        snapshot["memoryReferences"] = list(memory_references)
    if llm_selection:
        sanitized_llm_selection = _sanitize_request_snapshot_value(dict(llm_selection))
        snapshot["llmSelection"] = sanitized_llm_selection
        snapshot["llm_selection"] = sanitized_llm_selection
    try:
        encoded = json.dumps(snapshot, ensure_ascii=False)
    except TypeError:
        snapshot = _sanitize_request_snapshot_value(snapshot)
        encoded = json.dumps(snapshot, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > _REQUEST_SNAPSHOT_MAX_TOTAL_BYTES:
        snapshot["content"] = _clip_text(str(snapshot.get("content") or ""), 1000)
        snapshot.pop("config", None)
        snapshot["_truncated"] = True
    metadata: dict[str, Any] = {"request_snapshot": snapshot}
    normalized_turn_id = str(turn_id or "").strip()
    if normalized_turn_id:
        metadata["turn_id"] = normalized_turn_id
    client_turn_id = str(config.get("client_turn_id") or payload.get("client_turn_id") or "").strip()
    if client_turn_id:
        metadata["client_turn_id"] = client_turn_id
    return metadata


def _assistant_message_metadata(
    *,
    turn_id: str,
    config: dict[str, Any],
    terminal_status: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    normalized_turn_id = str(turn_id or "").strip()
    if normalized_turn_id:
        metadata["turn_id"] = normalized_turn_id
        metadata["engine_turn_id"] = normalized_turn_id
    client_turn_id = str((config or {}).get("client_turn_id") or "").strip()
    if client_turn_id:
        metadata["client_turn_id"] = client_turn_id
    normalized_status = str(terminal_status or "").strip()
    if normalized_status:
        metadata["terminal_status"] = normalized_status
    return metadata


def _tutorbot_mirror_session_ids(
    *,
    bot_id: str,
    session_id: str,
    user_id: str,
) -> list[str]:
    normalized_bot_id = str(bot_id or "").strip()
    normalized_session_id = str(session_id or "").strip()
    normalized_user_id = str(user_id or "").strip()
    if not normalized_bot_id or not normalized_session_id:
        return []

    candidates: list[str] = []
    if normalized_user_id:
        candidates.append(
            "tutorbot:"
            f"bot:{normalized_bot_id}:user:{normalized_user_id}:chat:{normalized_session_id}"
        )
    candidates.append(f"tutorbot:bot:{normalized_bot_id}:chat:{normalized_session_id}")
    return candidates


def _safe_terminal_assistant_content(
    assistant_content: str | None,
    *,
    status: str,
) -> str:
    fallback = _PUBLIC_CANCELLED_MESSAGE if status == "cancelled" else _PUBLIC_FAILED_MESSAGE
    source = str(assistant_content or "").strip()
    if not source:
        return fallback
    return normalize_markdown_for_tutorbot(
        coerce_user_visible_answer(source, fallback=fallback)
    ) or fallback


def _looks_like_learning_plan_request(text: str | None) -> bool:
    source = re.sub(r"\s+", "", str(text or "").strip().lower())
    if not source:
        return False
    if any(marker in source for marker in ("学习计划", "继续学习", "按计划", "学习进度")):
        return True
    return "计划" in source and any(marker in source for marker in ("我的", "学习", "继续", "查看", "看看"))


def _resolve_latest_user_learning_plan_id(user_id: str) -> str:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return ""
    try:
        from deeptutor.services.learning_plan import get_learning_plan_service

        plans = get_learning_plan_service().list_plans()
    except Exception:
        logger.debug("Failed to list learning plans for active plan recovery", exc_info=True)
        return ""
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        plan_user_id = str(plan.get("user_id") or "").strip()
        if plan_user_id != normalized_user_id:
            continue
        status = str(plan.get("status") or "").strip().lower()
        if status in {"deleted", "archived"}:
            continue
        plan_id = str(plan.get("session_id") or "").strip()
        if plan_id:
            return plan_id
    return ""


def _sanitize_public_terminal_event(event: StreamEvent, metadata: dict[str, Any]) -> dict[str, Any]:
    if _event_visibility(event) != _PUBLIC_VISIBILITY:
        return metadata
    if event.type == StreamEventType.CONTENT and _should_capture_assistant_content(event):
        raw = event.content if isinstance(event.content, str) else ""
        # Token-level deltas must keep whitespace verbatim; coerce/normalize are
        # paragraph-level transforms that strip per-delta whitespace and drop
        # pure-newline deltas ("\n\n") to "", which breaks ATX heading and list
        # parsing in the frontend markdown renderer.
        if raw and looks_like_unsafe_visible_output(raw):
            event.content = coerce_user_visible_answer(raw)
        else:
            event.content = raw
        return metadata
    if event.type == StreamEventType.ERROR:
        event.content = normalize_markdown_for_tutorbot(
            coerce_user_visible_answer(event.content, fallback=_PUBLIC_FAILED_MESSAGE)
        )
        return metadata
    if event.type != StreamEventType.RESULT:
        return metadata

    response = metadata.get("response")
    if isinstance(response, str):
        metadata["response"] = normalize_markdown_for_tutorbot(
            coerce_user_visible_answer(response)
        )

    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        nested_metadata = dict(nested)
        nested_response = nested_metadata.get("response")
        if isinstance(nested_response, str):
            nested_metadata["response"] = normalize_markdown_for_tutorbot(
                coerce_user_visible_answer(nested_response)
            )
        metadata["metadata"] = nested_metadata
    return metadata


def _exact_question_followup_context(trace_metadata: dict[str, Any]) -> dict[str, Any] | None:
    exact_question = trace_metadata.get("exact_question")
    if not isinstance(exact_question, dict):
        return None
    summary = build_choice_result_summary_from_exact_question(exact_question)
    if not summary:
        return None
    return build_question_followup_context_from_result_summary(
        summary,
        "",
        reveal_answers=bool(trace_metadata.get("reveal_answers", False)),
        reveal_explanations=bool(trace_metadata.get("reveal_explanations", False)),
    )


def _merge_missing_question_authority(
    target_context: dict[str, Any] | None,
    authority_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    target = normalize_question_followup_context(target_context)
    authority = normalize_question_followup_context(authority_context)
    if not target or not authority:
        return target

    merged = dict(target)
    for key in (
        "correct_answer",
        "explanation",
        "grading_key",
        "evidence_refs",
        "knowledge_context",
        "difficulty",
        "concentration",
    ):
        if not merged.get(key) and authority.get(key):
            merged[key] = authority[key]
    if not merged.get("options") and authority.get("options"):
        merged["options"] = authority["options"]

    target_items = target.get("items") if isinstance(target.get("items"), list) else []
    authority_items = authority.get("items") if isinstance(authority.get("items"), list) else []
    if target_items and authority_items:
        authority_by_id = {
            str(item.get("question_id") or "").strip(): item
            for item in authority_items
            if isinstance(item, dict)
        }
        merged_items: list[dict[str, Any]] = []
        for index, item in enumerate(target_items):
            if not isinstance(item, dict):
                continue
            source = authority_by_id.get(str(item.get("question_id") or "").strip())
            if source is None and index < len(authority_items):
                source = authority_items[index] if isinstance(authority_items[index], dict) else None
            merged_item = dict(item)
            if source:
                for key in (
                    "correct_answer",
                    "explanation",
                    "grading_key",
                    "evidence_refs",
                    "knowledge_context",
                    "difficulty",
                    "concentration",
                ):
                    if not merged_item.get(key) and source.get(key):
                        merged_item[key] = source[key]
                if not merged_item.get("options") and source.get("options"):
                    merged_item["options"] = source["options"]
            merged_items.append(merged_item)
        if merged_items:
            merged["items"] = merged_items
            if len(merged_items) == 1:
                for key, value in merged_items[0].items():
                    if key != "items":
                        merged[key] = value

    return normalize_question_followup_context(merged) or merged


def _enrich_result_question_authority_from_trace(
    metadata: dict[str, Any],
    trace_metadata: dict[str, Any],
) -> dict[str, Any]:
    authority_context = _exact_question_followup_context(trace_metadata)
    if not authority_context:
        return metadata

    current_context = metadata.get("question_followup_context")
    active_object = metadata.get("active_object") if isinstance(metadata.get("active_object"), dict) else None
    active_context = (
        extract_question_context_from_active_object(active_object)
        if active_object is not None
        else None
    )
    base_context = (
        current_context
        if isinstance(current_context, dict) and current_context
        else active_context
    )
    enriched_context = _merge_missing_question_authority(base_context, authority_context)
    if not enriched_context:
        return metadata

    enriched = dict(metadata)
    enriched["question_followup_context"] = enriched_context
    if active_object is not None:
        enriched_active_object = dict(active_object)
        enriched_active_object["state_snapshot"] = enriched_context
        enriched["active_object"] = enriched_active_object
    return enriched


class _TurnLatencyStages:
    def __init__(self) -> None:
        self._stages_ms: dict[str, float] = {}

    def record_since(self, stage: str, started_at: float) -> None:
        self._stages_ms[stage] = (time.perf_counter() - started_at) * 1000.0

    def add_duration(self, stage: str, duration_ms: float) -> None:
        try:
            value = float(duration_ms)
        except (TypeError, ValueError):
            return
        if value < 0:
            return
        self._stages_ms[stage] = self._stages_ms.get(stage, 0.0) + value

    def has_stage(self, stage: str) -> bool:
        return stage in self._stages_ms

    @contextlib.contextmanager
    def measure(self, stage: str):
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.record_since(stage, started_at)

    def snapshot(self) -> dict[str, float]:
        return normalize_latency_stage_timings(self._stages_ms)


def _normalize_non_negative_event_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, item in value.items():
        label = str(key or "").strip()
        if not label:
            continue
        try:
            count = int(item)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        normalized[label] = count
    return dict(sorted(normalized.items()))


def _build_terminal_turn_observation_event(
    *,
    session_id: str,
    turn_id: str,
    status: str,
    capability_name: str,
    duration_ms: float,
    trace_metadata: dict[str, Any],
    usage_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    usage = usage_summary if isinstance(usage_summary, dict) else {}
    metadata = {
        "source": "turn_runtime_terminal",
        "execution_engine": str(trace_metadata.get("execution_engine") or "").strip(),
        "bot_id": str(trace_metadata.get("bot_id") or "").strip(),
        "context_route": str(trace_metadata.get("context_route") or "").strip(),
        "task_anchor_type": str(trace_metadata.get("task_anchor_type") or "").strip(),
        "assistant_content_source": str(trace_metadata.get("assistant_content_source") or "").strip(),
        "total_input_tokens": int(usage.get("total_input_tokens") or 0),
        "total_output_tokens": int(usage.get("total_output_tokens") or 0),
        "total_calls": int(usage.get("total_calls") or 0),
    }
    latency_stages_ms = normalize_latency_stage_timings(trace_metadata.get("latency_stages_ms"))
    if latency_stages_ms:
        metadata["latency_stages_ms"] = latency_stages_ms
    context_build_stage_timings_ms = normalize_latency_stage_timings(
        trace_metadata.get("context_build_stage_timings_ms")
    )
    if context_build_stage_timings_ms:
        metadata["context_build_stage_timings_ms"] = context_build_stage_timings_ms
    start_turn_setup_stage_timings_ms = normalize_latency_stage_timings(
        trace_metadata.get("start_turn_setup_stage_timings_ms")
    )
    if start_turn_setup_stage_timings_ms:
        metadata["start_turn_setup_stage_timings_ms"] = start_turn_setup_stage_timings_ms
    capability_stream_stage_timings_ms = normalize_latency_stage_timings(
        trace_metadata.get("capability_stream_stage_timings_ms")
    )
    if capability_stream_stage_timings_ms:
        metadata["capability_stream_stage_timings_ms"] = capability_stream_stage_timings_ms
    capability_stream_event_counts = _normalize_non_negative_event_counts(
        trace_metadata.get("capability_stream_event_counts")
    )
    if capability_stream_event_counts:
        metadata["capability_stream_event_counts"] = capability_stream_event_counts
    for metadata_key in (
        "authority_applied",
        "exact_fast_path_hit",
        "execution_path",
        "question_lifecycle_scene",
        "rag_retrieval_degraded",
        "rag_retrieval_status",
        "rag_retrieval_error_type",
        "degraded_exact_answer_guard_applied",
        "degraded_mcq_grading_guard_applied",
    ):
        if metadata_key in trace_metadata:
            metadata[metadata_key] = trace_metadata[metadata_key]
    exact_question_summary = _summarize_exact_question_for_observer(trace_metadata.get("exact_question"))
    if exact_question_summary:
        metadata["exact_question"] = exact_question_summary
    lifecycle_decision = trace_metadata.get("question_lifecycle_decision")
    if isinstance(lifecycle_decision, dict):
        metadata["question_lifecycle_decision"] = dict(lifecycle_decision)
    return build_turn_observation_event(
        session_id=session_id,
        turn_id=turn_id,
        status=status,
        capability=capability_name or "chat",
        route=metadata["context_route"] or metadata["execution_engine"],
        trace_id=str(trace_metadata.get("trace_id") or "").strip(),
        surface=str(trace_metadata.get("source") or "").strip(),
        user_id=str(trace_metadata.get("user_id") or "").strip(),
        latency_ms=duration_ms,
        token_total=int(usage.get("total_tokens") or 0),
        error_type=status if status not in {"completed", "unknown"} else "",
        metadata=metadata,
    )


def _usage_summary_float(summary: dict[str, Any], key: str) -> float:
    value = summary.get(key)
    if not isinstance(value, (int, float)):
        return 0.0
    return max(float(value), 0.0)


def _billing_capture_amount_from_usage_summary(
    usage_summary: dict[str, Any] | None,
) -> tuple[int, dict[str, Any]]:
    if not isinstance(usage_summary, dict):
        return _MINI_PROGRAM_CAPTURE_COST, {
            "billing_amount_source": "fallback_minimum",
            "billing_cost_source": "missing_usage_summary",
            "billing_cost_point_scale": _MINI_PROGRAM_CAPTURE_COST_POINT_SCALE,
            "billing_minimum_points": _MINI_PROGRAM_CAPTURE_COST,
        }

    measured_cost = _usage_summary_float(usage_summary, "total_cost_usd")
    estimated_cost = _usage_summary_float(usage_summary, "estimated_total_cost_usd")
    billable_cost = measured_cost + estimated_cost
    cost_points = (
        int(math.ceil(billable_cost * _MINI_PROGRAM_CAPTURE_COST_POINT_SCALE))
        if billable_cost > 0
        else 0
    )
    amount_points = max(_MINI_PROGRAM_CAPTURE_COST, cost_points)

    if measured_cost > 0 and estimated_cost > 0:
        cost_source = "mixed_cost"
    elif measured_cost > 0:
        cost_source = "measured_cost"
    elif estimated_cost > 0:
        cost_source = "estimated_cost"
    else:
        cost_source = "missing_cost"

    metadata: dict[str, Any] = {
        "billing_amount_source": (
            cost_source if cost_points >= _MINI_PROGRAM_CAPTURE_COST else "fallback_minimum"
        ),
        "billing_cost_source": cost_source,
        "billing_cost_point_scale": _MINI_PROGRAM_CAPTURE_COST_POINT_SCALE,
        "billing_minimum_points": _MINI_PROGRAM_CAPTURE_COST,
        "billing_measured_cost": round(measured_cost, 8),
        "billing_estimated_cost": round(estimated_cost, 8),
        "billing_billable_cost": round(billable_cost, 8),
        "billing_cost_points": int(cost_points),
        "usage_accuracy": str(usage_summary.get("usage_accuracy") or "").strip(),
        "usage_total_input_tokens": int(usage_summary.get("total_input_tokens") or 0),
        "usage_total_output_tokens": int(usage_summary.get("total_output_tokens") or 0),
        "usage_total_tokens": int(usage_summary.get("total_tokens") or 0),
        "usage_estimated_input_tokens": int(usage_summary.get("estimated_input_tokens") or 0),
        "usage_estimated_output_tokens": int(usage_summary.get("estimated_output_tokens") or 0),
        "usage_estimated_total_tokens": int(usage_summary.get("estimated_total_tokens") or 0),
    }
    usage_sources = usage_summary.get("usage_sources")
    if isinstance(usage_sources, dict) and usage_sources:
        metadata["usage_sources"] = dict(usage_sources)
    models = usage_summary.get("models")
    if isinstance(models, dict) and models:
        metadata["usage_models"] = dict(models)
    return amount_points, metadata


def _append_trace_link_event(
    assistant_events: list[dict[str, Any]],
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
) -> None:
    normalized_trace_id = str(trace_id or "").strip()
    if not normalized_trace_id:
        return
    assistant_events.append(
        {
            "type": "trace_link",
            "source": "turn_runtime",
            "stage": "observability",
            "content": "",
            "metadata": {
                "session_id": session_id,
                "turn_id": turn_id,
                "trace_id": normalized_trace_id,
            },
            "session_id": session_id,
            "turn_id": turn_id,
            "trace_id": normalized_trace_id,
            "visibility": _INTERNAL_VISIBILITY,
        }
    )


def _public_turn_status_text(*, phase: str, language: str) -> str:
    normalized_language = str(language or "").strip().lower()
    zh = normalized_language.startswith("zh")
    if phase == "understanding":
        return "已收到，正在理解问题。" if zh else "Received. Understanding your question."
    if phase == "writing":
        return "正在组织回答。" if zh else "Preparing the answer."
    return "正在处理。" if zh else "Working on it."


def _env_flag(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _normalize_question_followup_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    intent = str(raw.get("intent") or "").strip()
    if not intent:
        return None
    return {
        "intent": intent,
        "confidence": raw.get("confidence"),
        "preserve_other_answers": bool(raw.get("preserve_other_answers", False)),
        "answers": raw.get("answers") if isinstance(raw.get("answers"), list) else [],
        "reason": str(raw.get("reason") or "").strip(),
    }


def _active_object_ref(active_object: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(active_object, dict):
        return {}
    return {
        "object_type": str(active_object.get("object_type") or "").strip(),
        "object_id": str(active_object.get("object_id") or "").strip(),
    }


def _active_object_plan_id(active_object: dict[str, Any] | None) -> str:
    normalized = normalize_active_object(active_object)
    if not isinstance(normalized, dict):
        return ""
    object_type = str(normalized.get("object_type") or "").strip()
    if object_type not in _PLAN_ACTIVE_OBJECT_TYPES:
        return ""
    scope = normalized.get("scope") if isinstance(normalized.get("scope"), dict) else {}
    state_snapshot = (
        normalized.get("state_snapshot")
        if isinstance(normalized.get("state_snapshot"), dict)
        else {}
    )
    for source in (scope, state_snapshot):
        value = str(source.get("plan_id") or source.get("session_id") or "").strip()
        if value:
            return value
    return ""


def _active_object_requires_deep_mode(active_object: dict[str, Any] | None) -> bool:
    normalized = normalize_active_object(active_object)
    if not isinstance(normalized, dict):
        return False
    if extract_question_context_from_active_object(normalized) is not None:
        return True
    object_type = str(normalized.get("object_type") or "").strip()
    return object_type not in {"", "open_chat_topic"}


def _same_active_object_identity(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    normalized_left = normalize_active_object(left)
    normalized_right = normalize_active_object(right)
    if not isinstance(normalized_left, dict) or not isinstance(normalized_right, dict):
        return False
    return (
        str(normalized_left.get("object_type") or "").strip()
        == str(normalized_right.get("object_type") or "").strip()
        and str(normalized_left.get("object_id") or "").strip()
        == str(normalized_right.get("object_id") or "").strip()
    )


def _suspended_stack_plan_id(suspended_object_stack: list[dict[str, Any]] | None) -> str:
    for item in normalize_suspended_object_stack(suspended_object_stack):
        plan_id = _active_object_plan_id(item)
        if plan_id:
            return plan_id
    return ""


def _prepend_suspended_object(
    suspended_object_stack: list[dict[str, Any]] | None,
    active_object: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized_object = normalize_active_object(active_object)
    if normalized_object is None:
        return normalize_suspended_object_stack(suspended_object_stack)

    deduped = [
        item
        for item in normalize_suspended_object_stack(suspended_object_stack)
        if not _same_active_object_identity(item, normalized_object)
    ]
    return [normalized_object, *deduped]


def _build_turn_semantic_decision(
    *,
    active_object: dict[str, Any] | None,
    followup_question_action: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(active_object, dict):
        return {}

    route = followup_action_route(followup_question_action)
    intent = str((followup_question_action or {}).get("intent") or "").strip()
    confidence = (followup_question_action or {}).get("confidence")
    try:
        normalized_confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        normalized_confidence = None

    relation = "uncertain"
    next_action = "hold_and_wait"
    allowed_patch = "no_state_change"
    if route == "submission":
        relation = "revise_answer_on_active_object" if intent == "revise_answers" else "answer_active_object"
        next_action = "route_to_grading"
        allowed_patch = "update_answer_slot"
    elif route == "followup":
        relation = "ask_about_active_object"
        next_action = "route_to_followup_explainer"
    elif route == "practice_generation":
        relation = "continue_same_learning_flow"
        next_action = "route_to_generation"
        allowed_patch = "set_active_object"
    return build_semantic_turn_decision(
        relation_to_active_object=relation,
        next_action=next_action,
        allowed_patch=allowed_patch,
        confidence=normalized_confidence if normalized_confidence is not None else 0.0,
        reason=str((followup_question_action or {}).get("reason") or "").strip()
        or "question_domain_adapter",
        target_object_ref=_active_object_ref(active_object),
        active_object=active_object,
    )


def _context_has_reference_answer(context: dict[str, Any] | None) -> bool:
    def _item_has_reference_answer(item: dict[str, Any] | None) -> bool:
        if not isinstance(item, dict):
            return False
        if str(item.get("correct_answer") or "").strip():
            return True
        grading_key = item.get("grading_key")
        return isinstance(grading_key, dict) and bool(
            str(grading_key.get("correct_answer") or "").strip()
        )

    normalized = normalize_question_followup_context(context)
    if normalized is None:
        return False
    if _item_has_reference_answer(normalized):
        return True
    return any(_item_has_reference_answer(item) for item in normalized.get("items") or [])


def _merge_public_submission_with_authoritative_context(
    explicit_context: dict[str, Any] | None,
    candidate_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    explicit = normalize_question_followup_context(explicit_context)
    candidate = normalize_question_followup_context(candidate_context)
    if explicit is None or candidate is None:
        return None
    if _context_has_reference_answer(explicit) or not _context_has_reference_answer(candidate):
        return None

    explicit_items = explicit.get("items") or []
    candidate_items = candidate.get("items") or []
    if explicit_items and candidate_items:
        merged_items = [dict(item) for item in candidate_items]
        candidate_by_id = {
            str(item.get("question_id") or "").strip(): index
            for index, item in enumerate(candidate_items)
            if str(item.get("question_id") or "").strip()
        }
        for index, item in enumerate(explicit_items):
            target_index = candidate_by_id.get(str(item.get("question_id") or "").strip(), index)
            if target_index < 0 or target_index >= len(merged_items):
                continue
            user_answer = str(item.get("user_answer") or "").strip()
            if user_answer:
                merged_items[target_index]["user_answer"] = user_answer
        merged = dict(candidate)
        merged["items"] = merged_items
        merged_user_answer = str(explicit.get("user_answer") or "").strip()
        if merged_user_answer:
            merged["user_answer"] = merged_user_answer
        return normalize_question_followup_context(merged)

    if candidate_items:
        explicit_question_id = str(explicit.get("question_id") or "").strip()
        target_index: int | None = None
        if explicit_question_id:
            for index, item in enumerate(candidate_items):
                if str(item.get("question_id") or "").strip() == explicit_question_id:
                    target_index = index
                    break
        elif len(candidate_items) == 1:
            target_index = 0
        if target_index is not None and 0 <= target_index < len(candidate_items):
            merged = dict(candidate_items[target_index])
            user_answer = str(explicit.get("user_answer") or "").strip()
            if user_answer:
                merged["user_answer"] = user_answer
            return normalize_question_followup_context(merged)

    explicit_question_id = str(explicit.get("question_id") or "").strip()
    candidate_question_id = str(candidate.get("question_id") or "").strip()
    if explicit_question_id and candidate_question_id and explicit_question_id != candidate_question_id:
        return None
    merged = dict(candidate)
    user_answer = str(explicit.get("user_answer") or "").strip()
    if user_answer:
        merged["user_answer"] = user_answer
    return normalize_question_followup_context(merged)


def _practice_generation_action_for_explicit_request(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not looks_like_practice_generation_request(user_message):
        return None
    if not has_explicit_practice_generation_intent(user_message):
        return None
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if submission is not None:
        return None
    return {
        "intent": "generate_more_questions",
        "confidence": 0.86,
        "answers": [],
        "reason": "用户明确要求出题/选择题，应生成新题而不是批改当前题目。",
    }


def _looks_like_batch_correction_reference(user_message: str) -> bool:
    return bool(
        re.search(r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]?", user_message)
        and ("不动" in user_message or "不变" in user_message or "不改" in user_message)
    )


def _normalize_question_identity_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s　，,。.!！?？；;：:、/／+\-—_（）()【】\[\]<>《》\"'“”‘’]+", "", text)


def _identity_ngrams(text: str, *, size: int = 2) -> set[str]:
    normalized = _normalize_question_identity_text(text)
    if len(normalized) < size:
        return set()
    return {normalized[index : index + size] for index in range(0, len(normalized) - size + 1)}


def _question_context_matches_free_text_surface(
    user_message: str,
    question_context: dict[str, Any],
) -> bool:
    message_identity = _normalize_question_identity_text(user_message)
    if not message_identity:
        return False

    question_identity = _normalize_question_identity_text(question_context.get("question"))
    if question_identity:
        if len(question_identity) >= 10 and question_identity in message_identity:
            return True
        question_grams = _identity_ngrams(question_identity)
        if question_grams:
            message_grams = _identity_ngrams(message_identity)
            overlap_ratio = len(question_grams & message_grams) / max(len(question_grams), 1)
            if overlap_ratio >= 0.55:
                return True
        return False

    options = question_context.get("options") if isinstance(question_context, dict) else None
    if not isinstance(options, dict) or not options:
        return False
    option_hits = 0
    for value in options.values():
        option_identity = _normalize_question_identity_text(value)
        if len(option_identity) >= 2 and option_identity in message_identity:
            option_hits += 1
    return option_hits >= min(2, len(options))


def _should_ignore_explicit_context_for_free_text_mcq(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return False
    if not (
        looks_like_free_text_mcq_grading_request(user_message)
        and looks_like_free_text_mcq_question_surface(user_message)
    ):
        return False
    return not _question_context_matches_free_text_surface(user_message, normalized_context)


def _submission_action_for_user_message(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None, None
    items = normalized_context.get("items") or []
    if not items and _looks_like_batch_correction_reference(user_message):
        return normalized_context, None
    target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if (
        items
        and _looks_like_batch_correction_reference(user_message)
        and isinstance(submission, dict)
        and submission.get("kind") != "batch"
    ):
        return normalized_context, None
    if not target_context or not submission:
        return normalized_context, None
    if submission.get("kind") == "ambiguous":
        return target_context, None
    if submission.get("kind") == "batch":
        return target_context, {
            "intent": "answer_questions",
            "confidence": 0.92,
            "answers": submission.get("answers") or [],
            "reason": "用户消息包含当前题组的可解析答案，优先进入批改。",
        }
    return target_context, {
        "intent": "answer_questions",
        "confidence": 0.92,
        "answers": [
            {
                "question_id": submission.get("question_id", ""),
                "answer": str(submission.get("answer") or "").strip(),
            }
        ],
        "reason": "用户消息包含当前题目的可解析答案，优先进入批改。",
    }


def _deterministic_followup_action_for_user_message(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if isinstance(submission, dict) and submission.get("kind") != "ambiguous":
        return None
    if not looks_like_question_followup(user_message, normalized_context):
        return None
    return {
        "intent": "ask_followup",
        "confidence": 0.88,
        "answers": [],
        "reason": "用户消息是围绕当前题目的稳定格式追问，不应被解释成改答或提交答案。",
    }


def _has_ambiguous_submission_attempt(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return False
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    return isinstance(submission, dict) and submission.get("kind") == "ambiguous"


async def _resolve_question_followup_context_and_action(
    *,
    user_message: str,
    explicit_context: dict[str, Any] | None,
    explicit_action: dict[str, Any] | None,
    candidate_contexts: list[dict[str, Any] | None] | tuple[dict[str, Any] | None, ...] = (),
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_explicit = normalize_question_followup_context(explicit_context)
    normalized_action = _normalize_question_followup_action(explicit_action)
    free_text_mcq_grading_request = (
        looks_like_free_text_mcq_grading_request(user_message)
        and looks_like_free_text_mcq_question_surface(user_message)
    )
    if _should_ignore_explicit_context_for_free_text_mcq(user_message, normalized_explicit):
        normalized_explicit = None
        normalized_action = None
    if (
        normalized_explicit is not None
        and not (normalized_explicit.get("items") or [])
        and _looks_like_batch_correction_reference(user_message)
    ):
        normalized_explicit = None
        normalized_action = None

    if normalized_explicit is not None:
        for candidate in candidate_contexts:
            merged = _merge_public_submission_with_authoritative_context(
                normalized_explicit,
                candidate,
            )
            if merged is not None:
                normalized_explicit = merged
                break
        submission_context, submission_action = _submission_action_for_user_message(
            user_message,
            normalized_explicit,
        )
        if submission_action is not None:
            return submission_context or normalized_explicit, submission_action
        if _has_ambiguous_submission_attempt(user_message, normalized_explicit):
            return normalized_explicit, None
        if (
            followup_action_route(normalized_action) == "practice_generation"
            and not looks_like_practice_generation_request(user_message)
        ):
            normalized_action = None
        if normalized_action is None:
            practice_action = _practice_generation_action_for_explicit_request(
                user_message,
                normalized_explicit,
            )
            if practice_action is not None:
                normalized_explicit = (
                    reset_question_submission_state(normalized_explicit)
                    or normalized_explicit
                )
                normalized_action = practice_action
            else:
                deterministic_followup_action = _deterministic_followup_action_for_user_message(
                    user_message,
                    normalized_explicit,
                )
                if deterministic_followup_action is not None:
                    return normalized_explicit, deterministic_followup_action
                normalized_action = await interpret_question_followup_action(
                    user_message,
                    normalized_explicit,
                )
                if (
                    followup_action_route(normalized_action) == "practice_generation"
                    and not looks_like_practice_generation_request(user_message)
                ):
                    normalized_action = None
        deterministic_followup = looks_like_question_followup(user_message, normalized_explicit)
        if (
            deterministic_followup
            and followup_action_route(normalized_action) == "practice_generation"
            and not looks_like_practice_generation_request(user_message)
        ):
            normalized_action = None
        return normalized_explicit, normalized_action

    for candidate in candidate_contexts:
        normalized_candidate = normalize_question_followup_context(candidate)
        if normalized_candidate is None:
            continue
        if (
            free_text_mcq_grading_request
            and not _question_context_matches_free_text_surface(user_message, normalized_candidate)
        ):
            continue
        if (
            not (normalized_candidate.get("items") or [])
            and _looks_like_batch_correction_reference(user_message)
        ):
            continue
        submission_context, submission_action = _submission_action_for_user_message(
            user_message,
            normalized_candidate,
        )
        if submission_action is not None:
            return submission_context or normalized_candidate, submission_action
        if _has_ambiguous_submission_attempt(user_message, normalized_candidate):
            return normalized_candidate, None
        practice_action = _practice_generation_action_for_explicit_request(
            user_message,
            normalized_candidate,
        )
        if practice_action is not None:
            return (
                reset_question_submission_state(normalized_candidate) or normalized_candidate,
                practice_action,
            )
        deterministic_followup_action = _deterministic_followup_action_for_user_message(
            user_message,
            normalized_candidate,
        )
        if deterministic_followup_action is not None:
            return normalized_candidate, deterministic_followup_action
        deterministic_followup = looks_like_question_followup(user_message, normalized_candidate)
        candidate_action = await interpret_question_followup_action(
            user_message,
            normalized_candidate,
        )
        candidate_route = followup_action_route(candidate_action)
        if candidate_route == "submission":
            return normalized_candidate, candidate_action
        if candidate_route == "practice_generation" and looks_like_practice_generation_request(
            user_message
        ):
            return normalized_candidate, candidate_action
        if candidate_route == "followup" and deterministic_followup:
            return normalized_candidate, candidate_action
        if deterministic_followup:
            return normalized_candidate, None

    return None, None


def _result_question_followup_context(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized_metadata = dict(metadata or {})
    explicit = normalize_question_followup_context(
        normalized_metadata.get("question_followup_context")
    )
    if explicit is not None:
        return explicit

    nested_metadata = (
        normalized_metadata.get("metadata")
        if isinstance(normalized_metadata.get("metadata"), dict)
        else {}
    )
    explicit_nested = normalize_question_followup_context(
        nested_metadata.get("question_followup_context")
    )
    if explicit_nested is not None:
        return explicit_nested

    return None


def _result_active_object(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized_metadata = dict(metadata or {})
    explicit = normalize_active_object(normalized_metadata.get("active_object"))
    if explicit is not None:
        return explicit

    nested_metadata = (
        normalized_metadata.get("metadata")
        if isinstance(normalized_metadata.get("metadata"), dict)
        else {}
    )
    explicit_nested = normalize_active_object(nested_metadata.get("active_object"))
    if explicit_nested is not None:
        return explicit_nested

    question_followup_context = _result_question_followup_context(normalized_metadata)
    if question_followup_context is None:
        return None
    return build_active_object_from_question_context(
        question_followup_context,
        source_turn_id=str(
            normalized_metadata.get("turn_id")
            or nested_metadata.get("turn_id")
            or ""
        ).strip(),
    )


def _result_suspended_object_stack(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized_metadata = dict(metadata or {})
    explicit = normalize_suspended_object_stack(normalized_metadata.get("suspended_object_stack"))
    if explicit:
        return explicit

    nested_metadata = (
        normalized_metadata.get("metadata")
        if isinstance(normalized_metadata.get("metadata"), dict)
        else {}
    )
    explicit_nested = normalize_suspended_object_stack(nested_metadata.get("suspended_object_stack"))
    return explicit_nested


def _coerce_context_flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_reference_tokens(values: list[Any] | tuple[Any, ...] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in values or []:
        if isinstance(item, dict):
            for key in ("kind", "id", "title", "notebook_id", "session_id", "content"):
                value = str(item.get(key, "") or "").strip()
                if value:
                    normalized.append(value)
                    break
            continue
        value = str(item or "").strip()
        if value:
            normalized.append(value)
    return tuple(normalized)


def _candidate_content_lines(candidates: tuple[Any, ...] | list[Any]) -> list[str]:
    lines: list[str] = []
    for candidate in candidates:
        content = str(getattr(candidate, "content", "") or "").strip()
        if not content:
            continue
        title = str(getattr(candidate, "source_id", "") or "").strip()
        source_type = str(getattr(candidate, "source_type", "") or "").strip()
        metadata = getattr(candidate, "metadata", {}) if isinstance(getattr(candidate, "metadata", {}), dict) else {}
        label = (
            str(metadata.get("title") or "").strip()
            or str(metadata.get("source_tag") or "").strip()
            or title
            or source_type
        )
        if label:
            lines.append(f"### {label}\n{content}")
        else:
            lines.append(content)
    return lines


def _render_memory_context_from_candidates(
    candidates: tuple[Any, ...] | list[Any],
    *,
    language: str,
) -> str:
    lines = _candidate_content_lines(candidates)
    if not lines:
        return ""
    title = "## 学员级长期状态" if str(language).lower().startswith("zh") else "## Learner State"
    intro = (
        "以下内容属于当前学员的长期状态真相，按需使用，不要外溢到其他学员。"
        if str(language).lower().startswith("zh")
        else "This is the authoritative long-term learner state for the current learner only."
    )
    return f"{title}\n{intro}\n\n" + "\n\n".join(lines)


def _render_evidence_block(
    candidates: tuple[Any, ...] | list[Any],
    *,
    language: str,
) -> str:
    sections: list[str] = []
    for candidate in candidates:
        content = str(getattr(candidate, "content", "") or "").strip()
        if not content:
            continue
        source_type = str(getattr(candidate, "source_type", "") or "").strip()
        metadata = getattr(candidate, "metadata", {}) if isinstance(getattr(candidate, "metadata", {}), dict) else {}
        label = (
            str(metadata.get("title") or "").strip()
            or str(metadata.get("source_tag") or "").strip()
            or source_type
            or "evidence"
        )
        sections.append(f"### {label}\n{content}")
    if not sections:
        return ""
    header = "## 参考证据" if str(language).lower().startswith("zh") else "## Supporting Evidence"
    note = (
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。"
        if str(language).lower().startswith("zh")
        else "The following content is supporting evidence only and must not override the current user question or session anchor."
    )
    return f"{header}\n{note}\n\n" + "\n\n".join(sections)


def _summarize_assistant_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    authority_applied = False
    selected_mode = ""
    execution_path = ""
    exact_fast_path_hit = False
    exact_question_summary: dict[str, Any] = {}
    retrieval_metadata: dict[str, Any] = {}
    actual_tool_rounds: int | None = None
    question_lifecycle_scene = ""
    skill_stack: list[str] = []
    skill_trace: list[dict[str, Any]] = []
    loader_source: dict[str, Any] = {}
    skill_source_status: dict[str, Any] = {}
    lifecycle_metadata: dict[str, Any] = {}
    lifecycle_metadata_keys = (
        "question_lifecycle_decision",
        "decision_source",
        "scene_confidence",
        "required_anchor_status",
        "exact_question_blocked_reason",
        "selected_skill_names",
        "llm_scene_candidate",
        "business_gate_result",
    )

    for item in events:
        if not isinstance(item, dict):
            continue
        event_type = str(item.get("type") or "").strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata_candidates = [metadata]
        if isinstance(metadata.get("metadata"), dict):
            metadata_candidates.append(metadata["metadata"])
        if event_type == "tool_call":
            tool_calls.append(
                {
                    "name": str(item.get("content") or "").strip() or str(metadata.get("tool_name") or "").strip(),
                    "args": dict(metadata.get("args") or {}) if isinstance(metadata.get("args"), dict) else {},
                }
            )
        elif event_type == "sources":
            raw_sources = metadata.get("sources")
            if isinstance(raw_sources, list):
                for source in raw_sources:
                    if isinstance(source, dict):
                        sources.append(source)
        if metadata.get("authority_applied") is True:
            authority_applied = True
        if metadata.get("authoritative_answer") or metadata.get("corrected_from"):
            authority_applied = True
        selected_mode = str(metadata.get("selected_mode") or selected_mode).strip()
        execution_path = str(metadata.get("execution_path") or execution_path).strip()
        if "exact_fast_path_hit" in metadata:
            exact_fast_path_hit = bool(metadata.get("exact_fast_path_hit"))
        raw_tool_rounds = metadata.get("actual_tool_rounds")
        if isinstance(raw_tool_rounds, int):
            actual_tool_rounds = raw_tool_rounds
        for candidate in metadata_candidates:
            raw_scene = str(candidate.get("question_lifecycle_scene") or "").strip()
            if raw_scene:
                question_lifecycle_scene = raw_scene
            for metadata_key in lifecycle_metadata_keys:
                if metadata_key in candidate and metadata_key not in lifecycle_metadata:
                    lifecycle_metadata[metadata_key] = candidate[metadata_key]
            raw_skill_stack = candidate.get("skill_stack")
            if isinstance(raw_skill_stack, list):
                for skill_name in raw_skill_stack:
                    normalized = str(skill_name or "").strip()
                    if normalized and normalized not in skill_stack:
                        skill_stack.append(normalized)
            raw_skill_trace = candidate.get("skill_trace")
            if isinstance(raw_skill_trace, list):
                trace_seen = {
                    (
                        str(trace_item.get("name") or ""),
                        str(trace_item.get("kind") or ""),
                        str(trace_item.get("status") or ""),
                    )
                    for trace_item in skill_trace
                    if isinstance(trace_item, dict)
                }
                for trace_item in raw_skill_trace:
                    if not isinstance(trace_item, dict):
                        continue
                    trace_key = (
                        str(trace_item.get("name") or ""),
                        str(trace_item.get("kind") or ""),
                        str(trace_item.get("status") or ""),
                    )
                    if not trace_key[0] or trace_key in trace_seen:
                        continue
                    trace_seen.add(trace_key)
                    skill_trace.append(dict(trace_item))
            if isinstance(candidate.get("loader_source"), dict):
                loader_source.update(dict(candidate.get("loader_source") or {}))
            if isinstance(candidate.get("skill_source_status"), dict):
                skill_source_status = dict(candidate.get("skill_source_status") or {})
            if not exact_question_summary and isinstance(candidate.get("exact_question"), dict):
                exact_question_summary = _summarize_exact_question_for_observer(
                    candidate.get("exact_question")
                )
            for metadata_key in (
                "rag_retrieval_degraded",
                "rag_retrieval_status",
                "rag_retrieval_error_type",
                "degraded_exact_answer_guard_applied",
                "degraded_mcq_grading_guard_applied",
            ):
                if metadata_key in candidate and metadata_key not in retrieval_metadata:
                    retrieval_metadata[metadata_key] = candidate[metadata_key]

    summary = {
        "tool_calls": tool_calls[:8],
        "actual_tool_rounds": actual_tool_rounds if actual_tool_rounds is not None else len(tool_calls),
        "sources": sources[:8],
        "authority_applied": authority_applied,
        "selected_mode": selected_mode,
        "execution_path": execution_path,
        "exact_fast_path_hit": exact_fast_path_hit,
    }
    if question_lifecycle_scene:
        summary["question_lifecycle_scene"] = question_lifecycle_scene
    if lifecycle_metadata:
        summary.update(lifecycle_metadata)
    if exact_question_summary:
        summary["exact_question"] = exact_question_summary
    if retrieval_metadata:
        summary.update(retrieval_metadata)
    if skill_stack:
        summary["skill_stack"] = skill_stack
    if skill_trace:
        summary["skill_trace"] = skill_trace
    if loader_source:
        summary["loader_source"] = loader_source
    if skill_source_status:
        summary["skill_source_status"] = skill_source_status
    return summary


def _summarize_exact_question_for_observer(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    summary = {
        "id": str(value.get("id") or value.get("chunk_id") or "").strip(),
        "answer_kind": str(value.get("answer_kind") or "").strip(),
        "question_type": str(value.get("question_type") or "").strip(),
        "source_group": str(value.get("source_group") or metadata.get("source_group") or "").strip(),
        "correct_answer": str(value.get("correct_answer") or "").strip(),
        "source_file": str(metadata.get("source_file") or "").strip(),
        "content_hash": str(metadata.get("content_hash") or "").strip(),
    }
    return {key: item for key, item in summary.items() if item}


def _result_selected_mode(
    metadata: dict[str, Any] | None,
    execution: "_TurnExecution",
) -> str:
    normalized_metadata = dict(metadata or {})
    nested_metadata = (
        normalized_metadata.get("metadata")
        if isinstance(normalized_metadata.get("metadata"), dict)
        else {}
    )

    for candidate in (
        normalized_metadata.get("selected_mode"),
        normalized_metadata.get("effective_response_mode"),
        nested_metadata.get("selected_mode"),
        nested_metadata.get("effective_response_mode"),
    ):
        normalized = normalize_requested_response_mode(candidate)
        if normalized in {"fast", "deep"}:
            return normalized

    payload = execution.payload if isinstance(execution.payload, dict) else {}
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    hints = (
        config.get("interaction_hints")
        if isinstance(config.get("interaction_hints"), dict)
        else {}
    )
    for candidate in (
        config.get("chat_mode"),
        hints.get("selected_mode"),
        hints.get("effective_response_mode"),
        hints.get("requested_response_mode"),
    ):
        normalized = normalize_requested_response_mode(candidate)
        if normalized in {"fast", "deep"}:
            return normalized
    return ""


def _result_execution_path(
    metadata: dict[str, Any] | None,
    execution: "_TurnExecution",
    *,
    event_source: str = "",
    selected_mode: str,
) -> str:
    normalized_metadata = dict(metadata or {})
    nested_metadata = (
        normalized_metadata.get("metadata")
        if isinstance(normalized_metadata.get("metadata"), dict)
        else {}
    )

    explicit = str(
        normalized_metadata.get("execution_path")
        or nested_metadata.get("execution_path")
        or ""
    ).strip()
    if explicit:
        return explicit

    capability = str(
        event_source
        or execution.capability
        or (
            execution.payload.get("capability")
            if isinstance(execution.payload, dict)
            else ""
        )
        or ""
    ).strip().lower()
    mode = str(
        normalized_metadata.get("mode")
        or nested_metadata.get("mode")
        or ""
    ).strip().lower()

    if capability == "tutorbot":
        if selected_mode == "fast":
            return "tutorbot_kb_first_fast_policy"
        if selected_mode == "deep":
            return "tutorbot_kb_first_full_agent_policy"
        return "tutorbot_runtime"

    if capability == "deep_question":
        normalized_mode = {
            "custom": "generation",
            "question": "generation",
            "grading": "grading",
            "followup": "followup",
        }.get(mode, mode or "capability")
        return f"deep_question_{normalized_mode}"

    if capability:
        return f"{capability}_capability"
    return ""


def _extract_followup_question_context(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("followup_question_context", None)
    normalized = normalize_question_followup_context(raw)
    if not normalized:
        return None
    normalized["knowledge_context"] = _clip_text(
        str(normalized.get("knowledge_context", "") or "").strip()
    )
    return normalized


def _extract_interaction_hints(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("interaction_hints", None)
    if not isinstance(raw, dict):
        return None

    profile = _normalize_interaction_profile_name(raw.get("profile"))
    priorities = raw.get("priorities")
    if not isinstance(priorities, list):
        priorities = []
    normalized_priorities = [
        str(item or "").strip().lower()
        for item in priorities
        if str(item or "").strip()
    ]

    preferred_question_type = str(raw.get("preferred_question_type", "") or "").strip().lower()
    if preferred_question_type not in {"choice", "written", "coding"}:
        preferred_question_type = ""
    grounding_reasons = [
        str(item or "").strip()
        for item in (raw.get("grounding_reasons") if isinstance(raw.get("grounding_reasons"), list) else [])
        if str(item or "").strip()
    ]
    requested_response_mode = normalize_requested_response_mode(
        raw.get("requested_response_mode")
    )
    raw_effective_response_mode = raw.get("effective_response_mode") or raw.get("selected_mode")
    effective_response_mode = (
        normalize_requested_response_mode(raw_effective_response_mode)
        if raw_effective_response_mode is not None and str(raw_effective_response_mode).strip()
        else ""
    )
    selected_mode = (
        effective_response_mode
        if effective_response_mode in {"fast", "deep"}
        else ""
    )
    exam_track = normalize_exam_track(raw.get("exam_track"))

    hints = {
        "profile": profile,
        "scene": str(raw.get("scene", "") or "").strip().lower(),
        "product_surface": str(raw.get("product_surface", "") or "").strip().lower(),
        "entry_role": str(raw.get("entry_role", "") or "").strip().lower(),
        "subject_domain": str(raw.get("subject_domain", "") or "").strip().lower(),
        "requested_response_mode": requested_response_mode,
        "effective_response_mode": effective_response_mode,
        "selected_mode": selected_mode,
        "response_mode_selection_reason": str(
            raw.get("response_mode_selection_reason") or ""
        ).strip(),
        "preferred_question_type": preferred_question_type,
        "allow_general_chat_fallback": raw.get("allow_general_chat_fallback", True) is not False,
        "priorities": normalized_priorities,
    }
    if raw.get("current_info_required") is True:
        hints["current_info_required"] = True
    if raw.get("textbook_delta_query") is True:
        hints["textbook_delta_query"] = True
    if grounding_reasons:
        hints["grounding_reasons"] = grounding_reasons
    if exam_track:
        hints["exam_track"] = exam_track
    if "suppress_answer_reveal_on_generate" in raw:
        hints["suppress_answer_reveal_on_generate"] = bool(
            raw.get("suppress_answer_reveal_on_generate")
        )
    if "prefer_question_context_grading" in raw:
        hints["prefer_question_context_grading"] = bool(
            raw.get("prefer_question_context_grading")
        )
    if "prefer_concept_teaching_slots" in raw:
        hints["prefer_concept_teaching_slots"] = bool(
            raw.get("prefer_concept_teaching_slots")
        )

    meaningful = any(
        [
            hints["profile"],
            hints["scene"],
            hints["product_surface"],
            hints["entry_role"],
            hints["subject_domain"],
            hints["requested_response_mode"],
            hints["preferred_question_type"],
            hints["priorities"],
            hints.get("effective_response_mode"),
            hints.get("selected_mode"),
            hints.get("response_mode_selection_reason"),
            hints.get("current_info_required"),
            hints.get("textbook_delta_query"),
            hints.get("grounding_reasons"),
            hints.get("suppress_answer_reveal_on_generate"),
            hints.get("prefer_question_context_grading"),
            hints.get("prefer_concept_teaching_slots"),
            hints.get("exam_track"),
            hints["allow_general_chat_fallback"] is False,
        ]
    )
    return hints if meaningful else None


def _should_select_tutorbot_mode(
    *,
    capability: str,
    bot_id: str,
    interaction_profile: str,
    interaction_hints: dict[str, Any] | None,
    explicit_chat_mode: bool,
) -> bool:
    if capability not in {"chat", "tutorbot"}:
        return False
    if explicit_chat_mode:
        return True
    if bot_id:
        return True
    if interaction_profile == "tutorbot":
        return True
    hints = interaction_hints if isinstance(interaction_hints, dict) else {}
    return str(hints.get("profile") or "").strip().lower() == "tutorbot" or (
        "requested_response_mode" in hints
    )


def _extract_persist_user_message(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return True
    raw = config.pop("_persist_user_message", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"false", "0", "no"}
    return bool(raw)


def _normalize_billing_context(raw: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    source = str(raw.get("source", "") or "").strip().lower()
    user_id = str(raw.get("user_id", "") or "").strip()
    if not source or not user_id:
        return None
    normalized = {
        "source": source,
        "user_id": user_id,
    }
    wallet_user_id = str(raw.get("wallet_user_id", "") or "").strip()
    learning_user_id = str(raw.get("learning_user_id", "") or "").strip()
    if wallet_user_id:
        normalized["wallet_user_id"] = wallet_user_id
    if learning_user_id:
        normalized["learning_user_id"] = learning_user_id
    return normalized


def _internal_qa_billing_context_identity_candidates(
    billing_context: dict[str, str],
) -> list[str]:
    candidates: list[str] = []

    def _append(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for key in ("user_id", "wallet_user_id", "learning_user_id"):
        _append(billing_context.get(key))

    if not internal_qa_billing_bypass_enabled():
        return candidates

    try:
        from deeptutor.services.member_console import get_member_console_service

        member_service = get_member_console_service()
        for user_id in list(candidates):
            try:
                profile = member_service.get_profile(user_id)
            except Exception:
                continue
            if not isinstance(profile, dict):
                continue
            for key in ("user_id", "username", "auth_username", "external_auth_user_id"):
                _append(profile.get(key))
    except Exception:
        pass
    return candidates


def _extract_billing_context(config: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(config, dict):
        return None
    return _normalize_billing_context(config.pop("billing_context", None))


def _normalize_name_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
    return normalized


def _normalize_interaction_profile_name(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "mini_tutor": "tutorbot",
        "construction_exam_tutor": "tutorbot",
    }.get(normalized, normalized)


def _resolve_bot_runtime_defaults(
    *,
    bot_id: str,
    tools: list[str] | None,
    knowledge_bases: list[str] | None,
) -> dict[str, Any]:
    resolved_tools = _normalize_name_list(tools)
    resolved_knowledge_bases = _normalize_name_list(knowledge_bases)
    defaults = resolve_bot_binding_defaults(bot_id=bot_id)
    if defaults is None:
        return {
            "execution_engine": "capability",
            "tools": resolved_tools,
            "knowledge_bases": resolved_knowledge_bases,
            "defaults_source": "",
        }

    injected = False
    if not resolved_knowledge_bases:
        resolved_knowledge_bases = _normalize_name_list(defaults.default_knowledge_bases)
        injected = bool(resolved_knowledge_bases)
    if resolved_knowledge_bases:
        existing_tools = {item.lower() for item in resolved_tools}
        for tool_name in _normalize_name_list(defaults.default_tools):
            lowered = tool_name.lower()
            if lowered in existing_tools:
                continue
            resolved_tools.append(tool_name)
            existing_tools.add(lowered)
            injected = True
    return {
        "execution_engine": str(defaults.execution_engine or "capability"),
        "tools": resolved_tools,
        "knowledge_bases": resolved_knowledge_bases,
        "defaults_source": "bot_runtime_defaults" if injected else "explicit",
    }


def _format_followup_question_context(context: dict[str, Any], language: str = "en") -> str:
    options = context.get("options") or {}
    option_lines = []
    if isinstance(options, dict) and options:
        for key, value in options.items():
            if value:
                option_lines.append(f"{key}. {value}")
    correctness = context.get("is_correct")
    correctness_text = (
        "correct"
        if correctness is True
        else "incorrect"
        if correctness is False
        else "unknown"
    )

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在处理一道测验题的后续追问。",
            "下面是本题上下文，请在后续回答中优先围绕这道题进行解释、纠错、延展和追问。",
            "如果用户提出超出本题的内容，也可以正常回答，但要保持和本题的连续性。",
            "",
            "[Question Follow-up Context]",
            f"Question ID: {context.get('question_id') or '(none)'}",
            f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
            f"Question type: {context.get('question_type') or '(none)'}",
            f"Difficulty: {context.get('difficulty') or '(none)'}",
            f"Concentration: {context.get('concentration') or '(none)'}",
            "",
            "Question:",
            context.get("question") or "(none)",
        ]
        if option_lines:
            lines.extend(["", "Options:", *option_lines])
        lines.extend(
            [
                "",
                f"User answer: {context.get('user_answer') or '(not provided)'}",
                f"User result: {correctness_text}",
                f"Reference answer: {context.get('correct_answer') or '(none)'}",
                "",
                "Explanation:",
                context.get("explanation") or "(none)",
            ]
        )
        if context.get("knowledge_context"):
            lines.extend(
                [
                    "",
                    "Knowledge context:",
                    context["knowledge_context"],
                ]
            )
        return "\n".join(lines).strip()

    lines = [
        "You are handling follow-up questions about a single quiz item.",
        "Use the question context below as the primary grounding for future turns in this session.",
        "If the user asks something broader, you may answer normally, but maintain continuity with this quiz item.",
        "",
        "[Question Follow-up Context]",
        f"Question ID: {context.get('question_id') or '(none)'}",
        f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
        f"Question type: {context.get('question_type') or '(none)'}",
        f"Difficulty: {context.get('difficulty') or '(none)'}",
        f"Concentration: {context.get('concentration') or '(none)'}",
        "",
        "Question:",
        context.get("question") or "(none)",
    ]
    if option_lines:
        lines.extend(["", "Options:", *option_lines])
    lines.extend(
        [
            "",
            f"User answer: {context.get('user_answer') or '(not provided)'}",
            f"User result: {correctness_text}",
            f"Reference answer: {context.get('correct_answer') or '(none)'}",
            "",
            "Explanation:",
            context.get("explanation") or "(none)",
        ]
    )
    if context.get("knowledge_context"):
        lines.extend(
            [
                "",
                "Knowledge context:",
                context["knowledge_context"],
            ]
        )
    return "\n".join(lines).strip()


def _format_interaction_hints(hints: dict[str, Any], language: str = "en") -> str:
    profile = str(hints.get("profile", "") or "").strip()
    preferred_question_type = str(hints.get("preferred_question_type", "") or "").strip()

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在一个学习型产品场景中工作。下面是交互策略提示，把它当作类似技能说明的软约束，不要机械套模板：",
        ]
        if hints.get("product_surface"):
            lines.append(f"- 当前产品表面：`{hints['product_surface']}`。")
        if profile == "tutorbot" or hints.get("entry_role") == "tutorbot":
            lines.append("- 当前入口身份是 TutorBot。")
        if hints.get("priorities"):
            lines.append(
                f"- 优先关注这些交互目标：{', '.join(str(item) for item in hints['priorities'])}。"
            )
        if preferred_question_type:
            lines.append(f"- 用户要求出题但未指定题型时，优先出 `{preferred_question_type}`。")
        if hints.get("suppress_answer_reveal_on_generate"):
            lines.append("- 出题时本回合优先只出题，不主动泄露答案或解析。")
        if hints.get("prefer_question_context_grading"):
            lines.append("- 若已有题目上下文，短答案如 A/B/C/D、我选B，应优先结合题目上下文理解为作答提交。")
        if hints.get("prefer_concept_teaching_slots"):
            lines.append("- 遇到知识讲解且本轮用了知识召回时，优先覆盖核心结论、采分点、易错点；记忆口诀和心得仅在确有帮助时补充。")
        lines.append("- 回答排版优先使用少量稳定标题和单层列表；避免多级缩进列表，以及“加粗标签 + 冒号 + 长正文 + 子列表”混搭。")
        if hints.get("allow_general_chat_fallback"):
            lines.append("- 如果用户明显转入闲聊、产品问答或开放问题，正常切回通用智能助理模式。")
        else:
            lines.append("- 优先保持学习辅导语境，除非用户明确要求切换话题。")
        return "\n".join(lines).strip()

    lines = [
        "You are operating in a learning-product scenario. Treat the notes below like skill guidance rather than a rigid workflow:",
    ]
    if hints.get("product_surface"):
        lines.append(f"- Current product surface: `{hints['product_surface']}`.")
    if profile == "tutorbot" or hints.get("entry_role") == "tutorbot":
        lines.append("- The current entry identity is TutorBot.")
    if hints.get("priorities"):
        lines.append(f"- Prioritize these interaction goals: {', '.join(str(item) for item in hints['priorities'])}.")
    if preferred_question_type:
        lines.append(f"- If the learner asks for practice without specifying type, prefer `{preferred_question_type}` questions.")
    if hints.get("suppress_answer_reveal_on_generate"):
        lines.append("- When generating practice, prefer giving only the question first without revealing the answer or explanation.")
    if hints.get("prefer_question_context_grading"):
        lines.append("- If quiz context exists, short replies like A/B/C/D or 'I choose B' should be interpreted as answer submissions when plausible.")
    if hints.get("prefer_concept_teaching_slots"):
        lines.append("- For concept teaching, try to cover conclusion, scoring points, pitfalls, memory hooks, and exam strategy.")
    if hints.get("allow_general_chat_fallback"):
        lines.append("- If the user clearly switches to open-ended chat, product questions, or general conversation, fall back naturally to general assistant behavior.")
    else:
        lines.append("- Stay in tutoring mode unless the user explicitly asks to switch topics.")
    return "\n".join(lines).strip()


# F7: bound each live WS subscriber's in-memory event queue. The queue carries
# replayed catchup events, live events, and a terminal ``None`` sentinel; on overflow
# we drop the OLDEST buffered event (never the incoming one) so memory is capped for a
# slow/stuck consumer, the close sentinel is always delivered (a slow consumer must not
# hang on end-of-stream), and any gap is recoverable by the client via SQLite replay
# (subscribe/resume with after_seq). SQLite remains the source of truth, so no data is lost.
_MAX_LIVE_SUBSCRIBER_QUEUE_SIZE = 2048


def _offer_to_subscriber(
    queue: "asyncio.Queue[dict[str, Any] | None]",
    item: dict[str, Any] | None,
) -> None:
    """Enqueue ``item`` into a bounded subscriber queue, dropping the oldest on overflow.

    Every put (catchup replay, live events, terminal ``None``) goes through here so the
    queue can never grow without bound and the ``None`` sentinel is never silently lost.
    """
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return


@dataclass
class _LiveSubscriber:
    queue: asyncio.Queue[dict[str, Any]]


@dataclass
class _TurnExecution:
    turn_id: str
    session_id: str
    capability: str
    payload: dict[str, Any]
    turn_view: dict[str, Any] | None = None
    start_turn_setup_stage_timings_ms: dict[str, float] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    subscribers: list[_LiveSubscriber] = field(default_factory=list)
    first_subscriber_attached: asyncio.Event = field(default_factory=asyncio.Event)
    deadline_exceeded: bool = False
    persistence_degraded: bool = False
    terminal_commit_started: bool = False


class TurnRuntimeManager:
    """Run one turn in the background and multiplex persisted/live events."""

    _DEFAULT_FIRST_SUBSCRIBER_GRACE_SECONDS = 0.2
    _DEFAULT_FAST_TURN_TIMEOUT_SECONDS = 75.0
    _DEFAULT_TURN_TIMEOUT_SECONDS = 180.0
    _DEFAULT_DEEP_TURN_TIMEOUT_SECONDS = 300.0

    def __init__(self, store: SQLiteSessionStore | None = None) -> None:
        self.store = store or get_sqlite_session_store()
        self._lock = asyncio.Lock()
        self._executions: dict[str, _TurnExecution] = {}
        self._volatile_question_contexts: dict[str, dict[str, Any]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    @staticmethod
    def _is_persistence_error(exc: Exception) -> bool:
        return isinstance(exc, (sqlite3.Error, OSError))

    def _mark_persistence_degraded(
        self,
        execution: _TurnExecution | None,
        operation: str,
        exc: Exception,
    ) -> None:
        if execution is not None:
            already_degraded = execution.persistence_degraded
            execution.persistence_degraded = True
            log_method = logger.debug if already_degraded else logger.warning
            log_method(
                "Persistence degraded for turn %s during %s: %s",
                execution.turn_id,
                operation,
                exc,
                exc_info=not already_degraded,
            )
            return
        logger.warning("Persistence degraded during %s: %s", operation, exc, exc_info=True)

    async def _canonicalize_execution_capability(
        self,
        execution: _TurnExecution,
        capability: str,
    ) -> str:
        normalized = str(capability or "").strip() or "chat"
        execution.capability = normalized
        execution.payload["capability"] = normalized
        if isinstance(execution.turn_view, dict):
            execution.turn_view["capability"] = normalized
        await self._safe_store_call(
            execution,
            "update_turn_capability",
            self.store.update_turn_capability,
            execution.turn_id,
            normalized,
            default=False,
        )
        await self._safe_store_call(
            execution,
            "update_session_capability_preference",
            self.store.update_session_preferences,
            execution.session_id,
            {"capability": normalized},
            default=False,
        )
        return normalized

    async def _safe_store_call(
        self,
        execution: _TurnExecution | None,
        operation: str,
        fn,
        *args,
        default: Any = None,
        swallow_value_error: bool = False,
        **kwargs,
    ) -> Any:
        try:
            return await fn(*args, **kwargs)
        except ValueError as exc:
            if not swallow_value_error:
                raise
            logger.warning("Store call skipped during %s: %s", operation, exc)
            return default
        except Exception as exc:
            if not self._is_persistence_error(exc):
                raise
            self._mark_persistence_degraded(execution, operation, exc)
            return default

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)

        def _discard(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            exc: BaseException | None = None
            with contextlib.suppress(asyncio.CancelledError):
                exc = done_task.exception()
            if exc is not None:
                logger.debug("Background turn task failed: %s", exc, exc_info=True)

        task.add_done_callback(_discard)

    @classmethod
    def _first_subscriber_grace_seconds(cls) -> float:
        raw = str(os.getenv("TURN_RUNTIME_FIRST_SUBSCRIBER_GRACE_SECONDS", "") or "").strip()
        if not raw:
            return cls._DEFAULT_FIRST_SUBSCRIBER_GRACE_SECONDS
        try:
            value = float(raw)
        except ValueError:
            return cls._DEFAULT_FIRST_SUBSCRIBER_GRACE_SECONDS
        return max(0.0, min(10.0, value))

    async def _wait_for_first_subscriber(self, execution: _TurnExecution) -> None:
        grace_seconds = self._first_subscriber_grace_seconds()
        if grace_seconds <= 0 or execution.first_subscriber_attached.is_set():
            return
        try:
            await asyncio.wait_for(execution.first_subscriber_attached.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            logger.debug(
                "Turn %s started without live subscriber after %.2fs grace window",
                execution.turn_id,
                grace_seconds,
            )

    @classmethod
    def _turn_timeout_seconds(cls, payload: dict[str, Any]) -> float:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        hints = config.get("interaction_hints") if isinstance(config.get("interaction_hints"), dict) else {}
        mode = str(
            config.get("chat_mode")
            or hints.get("selected_mode")
            or hints.get("effective_response_mode")
            or hints.get("requested_response_mode")
            or ""
        ).strip().lower()
        env_key = (
            "TURN_RUNTIME_FAST_TURN_TIMEOUT_SECONDS"
            if mode == "fast"
            else "TURN_RUNTIME_DEEP_TURN_TIMEOUT_SECONDS"
            if mode == "deep"
            else "TURN_RUNTIME_TURN_TIMEOUT_SECONDS"
        )
        default = (
            cls._DEFAULT_FAST_TURN_TIMEOUT_SECONDS
            if mode == "fast"
            else cls._DEFAULT_DEEP_TURN_TIMEOUT_SECONDS
            if mode == "deep"
            else cls._DEFAULT_TURN_TIMEOUT_SECONDS
        )
        raw = str(os.getenv(env_key) or os.getenv("TURN_RUNTIME_TURN_TIMEOUT_SECONDS") or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            return default
        return max(0.0, min(3600.0, value))

    def _schedule_turn_deadline(self, execution: _TurnExecution) -> asyncio.Task[None] | None:
        timeout_seconds = self._turn_timeout_seconds(execution.payload)
        if timeout_seconds <= 0:
            return None

        async def _watchdog() -> None:
            await asyncio.sleep(timeout_seconds)
            task = execution.task
            if task is None or task.done():
                return
            execution.deadline_exceeded = True
            logger.warning(
                "Turn %s exceeded %.1fs runtime deadline; cancelling for terminal recovery",
                execution.turn_id,
                timeout_seconds,
            )
            task.cancel()

        return asyncio.create_task(_watchdog())

    def _schedule_post_turn_refresh(
        self,
        *,
        turn_id: str,
        user_id: str,
        raw_user_content: str,
        assistant_content: str,
        session_id: str,
        capability_name: str,
        language: str,
        source_bot_id: str,
        context_route: str,
        task_anchor_type: str,
        learner_state_service: Any,
        memory_service: Any,
        learning_prompt_intent: dict[str, Any] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
    ) -> None:
        async def _run() -> None:
            try:
                refresh_trace_name = "learner_state.refresh" if user_id else "memory.consolidation"
                with contextlib.ExitStack() as stack:
                    with contextlib.suppress(Exception):
                        stack.enter_context(
                            observability.usage_scope(
                                scope_id=f"{turn_id}:post_turn_refresh",
                                session_id=session_id,
                                turn_id=turn_id,
                                capability=capability_name or "chat",
                            )
                        )
                    with contextlib.suppress(Exception):
                        stack.enter_context(
                            observability.start_observation(
                                name=refresh_trace_name,
                                as_type="chain",
                                input_payload={"content": raw_user_content},
                                metadata={
                                    "session_id": session_id,
                                    "turn_id": turn_id,
                                    "capability": capability_name or "chat",
                                    "bot_id": source_bot_id,
                                    "background_task": "post_turn_refresh",
                                },
                            )
                        )
                    if user_id:
                        await learner_state_service.refresh_from_turn(
                            user_id=user_id,
                            user_message=raw_user_content,
                            assistant_message=assistant_content,
                            session_id=session_id,
                            capability=capability_name or "chat",
                            language=language,
                            source_bot_id=source_bot_id or None,
                        )
                        if assistant_content.strip():
                            try:
                                from deeptutor.services.learner_state.conversation_learning_evidence import (
                                    write_conversation_learning_evidence_event,
                                )

                                write_conversation_learning_evidence_event(
                                    learner_state_service=learner_state_service,
                                    user_id=user_id,
                                    turn_ref=turn_id,
                                    user_question=raw_user_content,
                                    assistant_answer={"summary": assistant_content},
                                    prompt_intent=learning_prompt_intent,
                                    source_refs=source_refs,
                                )
                            except Exception:
                                logger.debug("Failed to write conversation learning evidence", exc_info=True)
                        if source_bot_id and assistant_content.strip():
                            try:
                                from deeptutor.services.learner_state import (
                                    get_bot_learner_overlay_service,
                                )

                                operations: list[dict[str, Any]] = [
                                    {
                                        "op": "set",
                                        "field": "working_memory_projection",
                                        "value": assistant_content.strip()[:500],
                                    },
                                    {
                                        "op": "merge",
                                        "field": "engagement_state",
                                        "value": {
                                            "last_interaction_at": datetime.now().astimezone().isoformat(),
                                            "last_context_route": str(context_route or "").strip(),
                                            "last_capability": str(capability_name or "chat").strip(),
                                        },
                                    },
                                ]
                                if task_anchor_type and task_anchor_type != "none":
                                    operations.append(
                                        {
                                            "op": "merge",
                                            "field": "local_focus",
                                            "value": {
                                                "task_anchor_type": task_anchor_type,
                                                "last_user_question": raw_user_content.strip()[:160],
                                            },
                                        }
                                    )
                                get_bot_learner_overlay_service().patch_overlay(
                                    source_bot_id,
                                    user_id,
                                    {"operations": operations},
                                    source_feature="turn",
                                    source_id=session_id,
                                )
                                overlay_service = get_bot_learner_overlay_service()
                                if hasattr(overlay_service, "apply_promotions"):
                                    overlay_service.apply_promotions(
                                        source_bot_id,
                                        user_id,
                                        learner_state_service=learner_state_service,
                                    )
                            except Exception:
                                logger.debug("Failed to patch bot learner overlay from turn runtime", exc_info=True)
                        return

                    await memory_service.refresh_from_turn(
                        user_message=raw_user_content,
                        assistant_message=assistant_content,
                        session_id=session_id,
                        capability=capability_name or "chat",
                        language=language,
                    )
            except Exception:
                logger.debug("Failed to refresh post-turn memory or learner state", exc_info=True)

        self._track_background_task(asyncio.create_task(_run()))

    @staticmethod
    def _initial_turn_trace_name(
        *,
        capability_name: str,
    ) -> str:
        if capability_name:
            return f"turn.{capability_name}"
        return "turn.runtime"

    async def _resolve_billing_context(
        self,
        session_id: str,
        request_config: dict[str, Any] | None,
    ) -> dict[str, str] | None:
        billing_context = _extract_billing_context(request_config)
        if billing_context is not None:
            return billing_context
        session = await self._safe_store_call(
            None,
            "get_session_for_billing_context",
            self.store.get_session,
            session_id,
            default=None,
        )
        if session is None:
            return None
        preferences = session.get("preferences") or {}
        return _normalize_billing_context(preferences if isinstance(preferences, dict) else None)

    async def _resolve_interaction_hints(
        self,
        session_id: str,
        request_config: dict[str, Any] | None,
        *,
        execution: _TurnExecution | None = None,
    ) -> dict[str, Any] | None:
        interaction_hints = _extract_interaction_hints(request_config)
        if interaction_hints is not None:
            return interaction_hints
        session = await self._safe_store_call(
            execution,
            "get_session_for_interaction_hints",
            self.store.get_session,
            session_id,
            default=None,
        )
        if not isinstance(session, dict):
            return None
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        return _extract_interaction_hints({"interaction_hints": preferences.get("interaction_hints")})

    async def _recover_orphaned_running_turns(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> None:
        active_turns = await self._safe_store_call(
            None,
            "list_active_turns",
            self.store.list_active_turns,
            session_id,
            default=[],
        )
        for turn in active_turns or []:
            turn_id = str(turn.get("id") or turn.get("turn_id") or "").strip()
            if not turn_id:
                continue
            async with self._lock:
                execution = self._executions.get(turn_id)
            if execution is not None and execution.task is not None and not execution.task.done():
                continue
            await self._safe_store_call(
                None,
                "recover_orphaned_turn",
                self.store.update_turn_status,
                turn_id,
                "failed",
                reason,
                default=False,
            )

    async def _cancel_active_turn_for_new_request(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> bool:
        active_turn = await self._safe_store_call(
            None,
            "get_active_turn_for_new_request",
            self.store.get_active_turn,
            session_id,
            default=None,
        )
        if not isinstance(active_turn, dict):
            return False
        turn_id = str(active_turn.get("id") or active_turn.get("turn_id") or "").strip()
        if not turn_id:
            return False

        async with self._lock:
            execution = self._executions.get(turn_id)

        if execution is None or execution.task is None or execution.task.done():
            updated = await self._safe_store_call(
                None,
                "cancel_superseded_turn_without_execution",
                self.store.update_turn_status,
                turn_id,
                "cancelled",
                reason,
                default=False,
            )
            return bool(updated)

        if execution.terminal_commit_started:
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(execution.task), timeout=2.0)
            refreshed_turn = await self._safe_store_call(
                None,
                "get_terminal_committed_turn_for_new_request",
                self.store.get_turn,
                turn_id,
                default=None,
            )
            return bool(refreshed_turn) and refreshed_turn.get("status") != "running"

        execution.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(execution.task, timeout=2.0)

        refreshed_turn = await self._safe_store_call(
            None,
            "get_cancelled_turn_for_new_request",
            self.store.get_turn,
            turn_id,
            default=None,
        )
        return bool(refreshed_turn) and refreshed_turn.get("status") != "running"

    def _capture_mobile_points(
        self,
        billing_context: dict[str, str] | None,
        assistant_content: str,
        *,
        session_id: str = "",
        turn_id: str = "",
        usage_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not billing_context:
            return None
        if billing_context.get("source") != "wx_miniprogram":
            return None
        user_id = str(billing_context.get("wallet_user_id") or "").strip()
        if not user_id or not str(assistant_content or "").strip():
            return None
        idempotency_key = (
            f"mini_program_capture:{turn_id}"
            if str(turn_id or "").strip()
            else f"mini_program_capture:{session_id}"
        )
        if internal_qa_billing_bypass_allowed(
            *_internal_qa_billing_context_identity_candidates(billing_context)
        ):
            return {
                "status": "bypassed",
                "reason": "internal_qa_billing_bypass",
                "wallet_user_id": user_id,
                "idempotency_key": idempotency_key,
            }
        amount_points, billing_metadata = _billing_capture_amount_from_usage_summary(usage_summary)
        capture_metadata = {
            "source": "wx_miniprogram",
            "turn_id": str(turn_id or "").strip(),
            "session_id": str(session_id or "").strip(),
            **billing_metadata,
        }
        try:
            from deeptutor.services.wallet import is_billing_enforcement_enabled

            billing_enforcement_enabled = is_billing_enforcement_enabled()
        except Exception:
            billing_enforcement_enabled = False
        if not billing_enforcement_enabled:
            try:
                from deeptutor.services.member_usage_meter import get_member_usage_meter

                meter_key = (
                    f"mini_program_meter:{turn_id}"
                    if str(turn_id or "").strip()
                    else f"mini_program_meter:{session_id}"
                )
                get_member_usage_meter().record_usage_event(
                    wallet_user_id=user_id,
                    learning_user_id=str(
                        billing_context.get("learning_user_id")
                        or billing_context.get("user_id")
                        or ""
                    ).strip(),
                    source="wx_miniprogram",
                    session_id=str(session_id or "").strip(),
                    turn_id=str(turn_id or "").strip(),
                    amount_points=amount_points,
                    dedupe_key=meter_key,
                    status="metered_not_charged",
                    metadata=capture_metadata,
                )
                return {
                    "status": "metered_not_charged",
                    "reason": "billing_enforcement_disabled",
                    "wallet_user_id": user_id,
                    "idempotency_key": idempotency_key,
                    "amount_points": amount_points,
                    "billing_amount_source": billing_metadata.get("billing_amount_source"),
                    "billing_cost_source": billing_metadata.get("billing_cost_source"),
                    "captured_micros": 0,
                    "requested_micros": int(amount_points) * 1_000_000,
                    "balance_after_micros": 0,
                }
            except Exception as exc:
                logger.warning("Failed to meter usage for user %s: %s", user_id, exc, exc_info=True)
                return {
                    "status": "failed",
                    "reason": "usage_meter_error",
                    "wallet_user_id": user_id,
                    "idempotency_key": idempotency_key,
                }
        try:
            from deeptutor.services.wallet import WalletInsufficientBalanceError, get_wallet_service

            wallet_service = get_wallet_service()
            result = wallet_service.record_usage_points(
                user_id=user_id,
                amount_points=amount_points,
                idempotency_key=idempotency_key,
                reference_id=str(turn_id or session_id or "").strip(),
                reason="capture",
                metadata=capture_metadata,
            )
            return {
                "status": "captured",
                "wallet_user_id": user_id,
                "idempotency_key": idempotency_key,
                "amount_points": amount_points,
                "billing_amount_source": billing_metadata.get("billing_amount_source"),
                "billing_cost_source": billing_metadata.get("billing_cost_source"),
                "captured_micros": int(getattr(result, "captured_micros", 0) or 0),
                "requested_micros": int(getattr(result, "requested_micros", 0) or 0),
                "balance_after_micros": int(getattr(result, "balance_after_micros", 0) or 0),
            }
        except WalletInsufficientBalanceError as exc:
            logger.warning("Insufficient wallet balance for user %s: %s", user_id, exc)
            return {
                "status": "failed",
                "reason": "insufficient_balance",
                "wallet_user_id": user_id,
                "idempotency_key": idempotency_key,
            }
        except Exception as exc:
            logger.warning("Failed to capture points for user %s: %s", user_id, exc, exc_info=True)
            return {
                "status": "failed",
                "reason": "capture_error",
                "wallet_user_id": user_id,
                "idempotency_key": idempotency_key,
            }

    def _record_mobile_learning(
        self,
        billing_context: dict[str, str] | None,
        raw_user_content: str,
        assistant_content: str,
    ) -> None:
        if not billing_context:
            return
        if billing_context.get("source") != "wx_miniprogram":
            return
        user_id = str(
            billing_context.get("learning_user_id")
            or billing_context.get("user_id", "")
            or ""
        ).strip()
        if not user_id or not str(assistant_content or "").strip():
            return
        try:
            from deeptutor.services.member_console import get_member_console_service

            member_service = get_member_console_service()
            member_service.record_chat_learning(
                user_id=user_id,
                query=raw_user_content,
                assistant_content=assistant_content,
            )
        except Exception:
            logger.warning("Failed to record learning activity for user %s", user_id, exc_info=True)

    def _context_orchestration_enabled(self, request_config: dict[str, Any]) -> bool:
        explicit = _coerce_context_flag(request_config.get("context_orchestration_enabled"))
        if explicit is not None:
            return explicit
        return _env_flag("DEEPTUTOR_CONTEXT_ORCHESTRATION_ENABLED", default=True)

    def _context_source_enabled(self, request_config: dict[str, Any], source_name: str) -> bool:
        source_flags = request_config.get("context_sources")
        if isinstance(source_flags, dict):
            explicit = _coerce_context_flag(source_flags.get(source_name))
            if explicit is not None:
                return explicit
        env_name = f"DEEPTUTOR_CONTEXT_{source_name.upper()}_ENABLED"
        return _env_flag(env_name, default=True)

    @staticmethod
    def _resolve_active_plan_id(
        request_config: dict[str, Any],
        notebook_references: list[dict[str, Any]],
    ) -> str:
        for key in ("active_plan_id", "plan_id", "guide_session_id", "learning_plan_id"):
            value = str(request_config.get(key, "") or "").strip()
            if value:
                return value
        for ref in notebook_references:
            if not isinstance(ref, dict):
                continue
            for key in ("plan_id", "session_id"):
                value = str(ref.get(key, "") or "").strip()
                if value and str(ref.get("kind", "") or "").strip() in {"plan_page", "guided_learning", "learning_plan"}:
                    return value
        return ""

    @staticmethod
    def _build_context_budget(
        *,
        context_window_tokens: int,
        output_reserve_tokens: int,
        tools_enabled: bool,
        route_label: str,
    ) -> dict[str, Any]:
        tool_reserve_tokens = 768 if tools_enabled else 384
        safety_margin_tokens = max(256, int(context_window_tokens * 0.05))
        effective_input_budget = max(
            1024,
            int(context_window_tokens) - int(output_reserve_tokens) - tool_reserve_tokens - safety_margin_tokens,
        )
        if route_label == "low_signal_social":
            ratios = {"anchor": 0.12, "session": 0.42, "learner": 0.16, "evidence": 0.0}
        elif route_label in {"cross_session_recall", "personal_recall"}:
            ratios = {"anchor": 0.12, "session": 0.30, "learner": 0.14, "evidence": 0.24}
        elif route_label in {"guided_plan_continuation", "notebook_followup"}:
            ratios = {"anchor": 0.16, "session": 0.28, "learner": 0.12, "evidence": 0.24}
        else:
            ratios = {"anchor": 0.14, "session": 0.34, "learner": 0.14, "evidence": 0.18}
        anchor_budget = max(128, int(effective_input_budget * ratios["anchor"]))
        session_budget = max(256, int(effective_input_budget * ratios["session"]))
        learner_budget = max(192, int(effective_input_budget * ratios["learner"]))
        evidence_budget = max(0, effective_input_budget - anchor_budget - session_budget - learner_budget)
        return {
            "effective_input_budget": effective_input_budget,
            "output_reserve_tokens": int(output_reserve_tokens),
            "tool_reserve_tokens": tool_reserve_tokens,
            "safety_margin_tokens": safety_margin_tokens,
            "anchor_budget": anchor_budget,
            "session_budget": session_budget,
            "learner_budget": learner_budget,
            "evidence_budget": evidence_budget,
        }

    async def _build_orchestrated_context_payload(
        self,
        *,
        execution: _TurnExecution,
        raw_user_content: str,
        payload: dict[str, Any],
        request_config: dict[str, Any],
        llm_config: Any,
        builder: Any,
        learner_state_service: Any,
        memory_service: Any,
        notebook_manager: Any,
        user_id: str,
        language: str,
        source_bot_id: str,
        active_plan_id: str,
        active_object: dict[str, Any] | None,
        followup_question_context: dict[str, Any] | None,
        interaction_hints: dict[str, Any] | None,
        notebook_references: list[dict[str, Any]],
        history_references: list[str],
    ) -> dict[str, Any]:
        from deeptutor.services.session.context_budget import ContextBudget, pack_context_candidates
        from deeptutor.services.session.context_builder import count_tokens
        from deeptutor.services.session.context_pack import ContextBlockType, ContextCandidate
        from deeptutor.services.session.context_router import (
            ContextRouteInput,
            decide_context_route,
        )
        from deeptutor.services.session.context_sources import ContextSourceLoader
        from deeptutor.services.session.context_trace import (
            build_context_trace_summary,
            resolve_target_escalation_level,
        )

        build_stage_timings_ms: dict[str, float] = {}

        @contextlib.contextmanager
        def measure_build_stage(stage: str):
            started_at = time.perf_counter()
            try:
                yield
            finally:
                build_stage_timings_ms[stage] = (time.perf_counter() - started_at) * 1000.0

        active_plan_id = str(active_plan_id or "").strip() or _active_object_plan_id(active_object)
        try:
            with measure_build_stage("route_resolver"):
                route_decision = decide_context_route(
                    ContextRouteInput(
                        user_message=raw_user_content,
                        has_active_question=bool(followup_question_context),
                        has_active_plan=bool(active_plan_id),
                        notebook_references=_normalize_reference_tokens(notebook_references),
                        history_references=_normalize_reference_tokens(history_references),
                        memory_references=(),
                        explicit_grounding=False,
                        session_followup_hint=False,
                        personal_recall_hint=False,
                    )
                )
        except Exception as exc:
            raise _ContextOrchestrationStageError("route_resolver", exc) from exc
        with measure_build_stage("context_budget"):
            context_window_tokens = (
                int(builder.context_window_tokens(llm_config))
                if hasattr(builder, "context_window_tokens")
                else max(
                    8192,
                    int(getattr(llm_config, "context_window_tokens", 0) or 0)
                    or int(getattr(llm_config, "max_tokens", 4096) or 4096),
                )
            )
            budget_parts = self._build_context_budget(
                context_window_tokens=context_window_tokens,
                output_reserve_tokens=int(getattr(llm_config, "max_tokens", 1024) or 1024),
                tools_enabled=bool(payload.get("tools") or payload.get("knowledge_bases")),
                route_label=route_decision.route_label,
            )
        try:
            with measure_build_stage("session_history"):
                history_result = await builder.build(
                    session_id=execution.session_id,
                    llm_config=llm_config,
                    language=language,
                    budget_override=budget_parts["session_budget"],
                    on_event=lambda event: self._persist_and_publish(execution, event),
                )
        except Exception as exc:
            raise _ContextOrchestrationStageError("session_history", exc) from exc

        learner_candidates_payload: dict[str, Any] | None = None
        overlay_payload: dict[str, Any] | None = None
        compiled_learning_truth: dict[str, Any] = {}
        personalization_context: dict[str, Any] = {}
        compact_memory_context = ""
        try:
            with measure_build_stage("learner_state"):
                if user_id and hasattr(learner_state_service, "build_context_candidates"):
                    learner_candidates_payload = learner_state_service.build_context_candidates(
                        user_id=user_id,
                        query=raw_user_content,
                        route=route_decision.route_label,
                        language=language,
                    )
                    projection = learner_candidates_payload.get("compiled_learning_truth")
                    if isinstance(projection, dict):
                        compiled_learning_truth = dict(projection)
                    # Grading-to-Brain loop: carry the PersonalizationContextPack (a projection of the same
                    # compiled truth) so it can be injected into the live turn alongside compiled_learning_truth.
                    pcp = learner_candidates_payload.get("personalization_context")
                    if isinstance(pcp, dict):
                        personalization_context = dict(pcp)
                elif user_id:
                    compact_memory_context = learner_state_service.build_context(
                        user_id=user_id,
                        language=language,
                    )
                else:
                    compact_memory_context = memory_service.build_memory_context()
        except Exception as exc:
            raise _ContextOrchestrationStageError("learner_state", exc) from exc

        if not user_id and not compact_memory_context:
            compact_memory_context = memory_service.build_memory_context()

        source_flags_snapshot = {
            "memory": self._context_source_enabled(request_config, "memory"),
            "notebook": self._context_source_enabled(request_config, "notebook"),
            "history": self._context_source_enabled(request_config, "history"),
            "overlay": self._context_source_enabled(request_config, "overlay"),
        }
        if (
            user_id
            and source_bot_id
            and source_flags_snapshot["overlay"]
        ):
            try:
                with measure_build_stage("overlay_read"):
                    from deeptutor.services.learner_state import get_bot_learner_overlay_service

                    overlay_payload = get_bot_learner_overlay_service().read_overlay(source_bot_id, user_id)
            except Exception:
                logger.debug(
                    "Failed to load bot learner overlay for user %s bot %s",
                    user_id,
                    source_bot_id,
                    exc_info=True,
                )
                overlay_payload = None

        notebook_loading_allowed = route_decision.route_label in {
            "guided_plan_continuation",
            "notebook_followup",
            "tool_or_grounding_needed",
        }
        history_loading_allowed = route_decision.route_label == "cross_session_recall"
        target_escalation_level = resolve_target_escalation_level(route_label=route_decision.route_label)
        loader = ContextSourceLoader(
            notebook_manager=notebook_manager,
            session_store=self.store,
        )
        notebook_source_candidates: list[Any] = []
        plan_source_candidates: list[Any] = []
        history_source_candidates: list[Any] = []
        if target_escalation_level >= 2:
            try:
                with measure_build_stage("source_loader_notebook_plan"):
                    if notebook_loading_allowed and source_flags_snapshot["notebook"]:
                        notebook_source_candidates = loader.load_notebook_candidates(
                            user_question=raw_user_content,
                            notebook_references=notebook_references,
                            max_candidates=3,
                            max_excerpt_chars=360,
                        )
                        plan_source_candidates = loader.load_active_plan_page_candidates(
                            user_question=raw_user_content,
                            user_id=user_id,
                            plan_id=active_plan_id,
                            max_candidates=3,
                            max_excerpt_chars=360,
                        )
            except Exception as exc:
                raise _ContextOrchestrationStageError("source_loader:notebook_plan", exc) from exc
        if target_escalation_level >= 3 and history_loading_allowed and source_flags_snapshot["history"]:
            try:
                with measure_build_stage("source_loader_history"):
                    history_source_candidates = await loader.load_history_candidates(
                        user_question=raw_user_content,
                        user_id=user_id,
                        current_session_id=execution.session_id,
                        history_references=history_references,
                        max_candidates=2,
                        max_excerpt_chars=600,
                    )
            except Exception as exc:
                raise _ContextOrchestrationStageError("source_loader:history", exc) from exc

        with measure_build_stage("candidate_build"):
            source_priority = {
                "current_question": 0,
                "active_plan": 1,
                "session_history": 2,
                "learner_card": 3,
                "overlay": 4,
                "notebook": 4,
                "memory": 5,
                "history": 6,
            }
            source_budgets = {
                "current_question": budget_parts["anchor_budget"],
                "active_plan": max(0, min(budget_parts["anchor_budget"], int(budget_parts["evidence_budget"] * 0.7)) or budget_parts["anchor_budget"]),
                "session_history": budget_parts["session_budget"],
                "learner_card": budget_parts["learner_budget"],
                "overlay": max(0, int(budget_parts["evidence_budget"] * 0.45)),
                "notebook": max(0, int(budget_parts["evidence_budget"] * 0.7)),
                "memory": max(0, int(budget_parts["evidence_budget"] * 0.55)),
                "history": max(0, int(budget_parts["evidence_budget"] * (0.8 if route_decision.route_label == "cross_session_recall" else 0.45))),
            }
            budget = ContextBudget(
                total_tokens=budget_parts["effective_input_budget"],
                block_budgets={
                    ContextBlockType.ANCHOR: budget_parts["anchor_budget"],
                    ContextBlockType.SESSION: budget_parts["session_budget"],
                    ContextBlockType.LEARNER: budget_parts["learner_budget"],
                    ContextBlockType.EVIDENCE: budget_parts["evidence_budget"],
                },
                source_budgets=source_budgets,
                source_priority=source_priority,
                trace_metadata={
                    "route_confidence": route_decision.confidence,
                    "anchor_confidence": 1.0 if route_decision.task_anchor_type.value != "none" else 0.0,
                    "compression_applied": bool(history_result.conversation_summary),
                    "history_search_applied": False,
                    "cache_hits": [],
                    "fallback_path": "",
                    "target_escalation_level": target_escalation_level,
                    "source_flags": dict(source_flags_snapshot),
                    "token_budget_reserved_output": budget_parts["output_reserve_tokens"],
                    "token_budget_tool_reserve": budget_parts["tool_reserve_tokens"],
                    "token_budget_safety_margin": budget_parts["safety_margin_tokens"],
                },
            )

        base_candidates: list[Any] = []
        level2_candidates: list[Any] = []
        level3_candidates: list[Any] = []
        if followup_question_context:
            anchor_text = _clip_text(_format_followup_question_context(followup_question_context, language=language), limit=max(300, budget_parts["anchor_budget"] * 4))
            base_candidates.append(
                ContextCandidate(
                    candidate_id="active-question",
                    block=ContextBlockType.ANCHOR,
                    source_bucket="current_question",
                    source_type="active_question_context",
                    source_id=str(followup_question_context.get("question_id", "") or "active-question"),
                    content=anchor_text,
                    token_cost=max(1, count_tokens(anchor_text)),
                    authority=10,
                    relevance=10,
                    recency=10,
                    anchor_alignment=10,
                    metadata={"title": "Active Question" if not language.startswith("zh") else "当前题目"},
                )
            )
        if history_result.context_text.strip():
            base_candidates.append(
                ContextCandidate(
                    candidate_id="session-history",
                    block=ContextBlockType.SESSION,
                    source_bucket="session_history",
                    source_type="session_history",
                    source_id=execution.session_id,
                    content=history_result.context_text,
                    token_cost=max(1, int(history_result.token_count or count_tokens(history_result.context_text))),
                    authority=9,
                    relevance=8,
                    recency=9,
                    anchor_alignment=8,
                    metadata={"title": "Conversation Summary" if not language.startswith("zh") else "会话连续性"},
                )
            )
        if learner_candidates_payload is not None:
            for index, segment in enumerate(list(learner_candidates_payload.get("learner_candidates") or [])):
                content = str(segment.get("content", "") or "").strip()
                if not content:
                    continue
                source_tag = str(segment.get("source_tag", "") or "learner_card").strip()
                base_candidates.append(
                    ContextCandidate(
                        candidate_id=f"learner-{source_tag}-{index}",
                        block=ContextBlockType.LEARNER,
                        source_bucket="learner_card",
                        source_type=source_tag,
                        source_id=user_id or "global-memory",
                        content=content,
                        token_cost=max(1, count_tokens(content)),
                        authority=7 if source_tag != "learner_summary" else 6,
                        relevance=6,
                        recency=7,
                        anchor_alignment=3,
                        metadata={"source_tag": source_tag, "title": str(segment.get("title", "") or source_tag)},
                    )
                )
            if source_flags_snapshot["memory"]:
                for index, segment in enumerate(list(learner_candidates_payload.get("memory_candidates") or [])):
                    content = str(segment.get("content", "") or "").strip()
                    if not content:
                        continue
                    metadata = dict(segment.get("metadata") or {})
                    level2_candidates.append(
                        ContextCandidate(
                            candidate_id=f"memory-{metadata.get('event_id') or index}",
                            block=ContextBlockType.EVIDENCE,
                            source_bucket="memory",
                            source_type="memory_hit",
                            source_id=str(metadata.get("event_id", "") or index),
                            content=content,
                            token_cost=max(1, count_tokens(content)),
                            authority=4,
                            relevance=max(1, int(round(float(segment.get("score", 1.0)) * 2))),
                            recency=6,
                            anchor_alignment=3,
                            conflict_risk=1,
                            metadata={"source_tag": "memory_hit", "title": metadata.get("memory_kind") or "memory_hit", **metadata},
                        )
                    )
        if overlay_payload is not None:
            effective_overlay = dict(overlay_payload.get("effective_overlay") or {})
            overlay_candidates_added = 0
            overlay_candidate_target = (
                base_candidates
                if route_decision.route_label == "session_followup"
                else level2_candidates
            )

            def _append_overlay_candidate(
                *,
                suffix: str,
                block: Any,
                content: str,
                title: str,
                authority: int,
                relevance: int,
                recency: int,
                anchor_alignment: int,
                conflict_risk: int = 1,
            ) -> None:
                nonlocal overlay_candidates_added
                normalized = str(content or "").strip()
                if not normalized:
                    return
                overlay_candidates_added += 1
                overlay_candidate_target.append(
                    ContextCandidate(
                        candidate_id=f"overlay-{suffix}-{overlay_candidates_added}",
                        block=block,
                        source_bucket="overlay",
                        source_type=f"overlay_{suffix}",
                        source_id=source_bot_id,
                        content=normalized,
                        token_cost=max(1, count_tokens(normalized)),
                        authority=authority,
                        relevance=relevance,
                        recency=recency,
                        anchor_alignment=anchor_alignment,
                        conflict_risk=conflict_risk,
                        metadata={
                            "title": title,
                            "source_tag": f"overlay_{suffix}",
                            "bot_id": source_bot_id,
                            "user_id": user_id,
                        },
                    )
                )

            local_focus = dict(effective_overlay.get("local_focus") or {})
            if local_focus:
                _append_overlay_candidate(
                    suffix="local_focus",
                    block=ContextBlockType.LEARNER,
                    content=json.dumps(local_focus, ensure_ascii=False, indent=2),
                    title="Bot Local Focus" if not language.startswith("zh") else "Bot 局部 Focus",
                    authority=5,
                    relevance=5,
                    recency=6,
                    anchor_alignment=4,
                )

            teaching_policy_override = dict(effective_overlay.get("teaching_policy_override") or {})
            if teaching_policy_override:
                _append_overlay_candidate(
                    suffix="teaching_policy",
                    block=ContextBlockType.LEARNER,
                    content=json.dumps(teaching_policy_override, ensure_ascii=False, indent=2),
                    title="Teaching Policy Override" if not language.startswith("zh") else "教学策略局部覆盖",
                    authority=4,
                    relevance=4,
                    recency=5,
                    anchor_alignment=3,
                )

            engagement_state = dict(effective_overlay.get("engagement_state") or {})
            if engagement_state:
                _append_overlay_candidate(
                    suffix="engagement_state",
                    block=ContextBlockType.LEARNER,
                    content=json.dumps(engagement_state, ensure_ascii=False, indent=2),
                    title="Engagement State" if not language.startswith("zh") else "局部互动状态",
                    authority=3,
                    relevance=3,
                    recency=6,
                    anchor_alignment=2,
                )

            working_memory_projection = str(effective_overlay.get("working_memory_projection", "") or "").strip()
            if working_memory_projection:
                _append_overlay_candidate(
                    suffix="working_memory",
                    block=ContextBlockType.EVIDENCE,
                    content=working_memory_projection,
                    title="Working Memory Projection" if not language.startswith("zh") else "局部工作记忆投影",
                    authority=4,
                    relevance=5,
                    recency=7,
                    anchor_alignment=4,
                )

            active_plan_binding = dict(effective_overlay.get("active_plan_binding") or {})
            if active_plan_binding:
                _append_overlay_candidate(
                    suffix="active_plan_binding",
                    block=ContextBlockType.EVIDENCE,
                    content=json.dumps(active_plan_binding, ensure_ascii=False, indent=2),
                    title="Active Plan Binding" if not language.startswith("zh") else "局部学习计划绑定",
                    authority=4,
                    relevance=5,
                    recency=6,
                    anchor_alignment=4,
                )

            local_notebook_scope_refs = list(effective_overlay.get("local_notebook_scope_refs") or [])
            if local_notebook_scope_refs:
                _append_overlay_candidate(
                    suffix="notebook_scope",
                    block=ContextBlockType.EVIDENCE,
                    content=json.dumps(local_notebook_scope_refs, ensure_ascii=False, indent=2),
                    title="Notebook Scope Override" if not language.startswith("zh") else "局部 Notebook 范围",
                    authority=3,
                    relevance=4,
                    recency=5,
                    anchor_alignment=3,
                )

            if overlay_candidates_added:
                budget.trace_metadata["overlay_candidate_count"] = overlay_candidates_added
                budget.trace_metadata["overlay_fields"] = sorted(
                    key for key, value in effective_overlay.items() if value not in ({}, [], "")
                )
        for index, item in enumerate([*plan_source_candidates, *notebook_source_candidates]):
            source_bucket = "active_plan" if item.source_kind == "active_plan" else item.source_kind
            authority_map = {"anchor": 9, "primary": 8, "supporting": 6, "fallback": 4}
            block = ContextBlockType.EVIDENCE
            if item.source_kind == "active_plan" and route_decision.route_label == "guided_plan_continuation":
                block = ContextBlockType.ANCHOR if item.authority in {"anchor", "primary"} else ContextBlockType.EVIDENCE
            level2_candidates.append(
                ContextCandidate(
                    candidate_id=f"{item.source_kind}-{item.fragment_id}-{index}",
                    block=block,
                    source_bucket=source_bucket,
                    source_type=item.source_kind,
                    source_id=item.source_id,
                    content=item.content,
                    token_cost=max(1, int(item.cost_tokens or count_tokens(item.content))),
                    authority=authority_map.get(item.authority, 4),
                    relevance=max(1, int(round(float(item.score or 0.0) + 3))),
                    recency=7 if item.source_kind == "active_plan" else 5,
                    anchor_alignment=8 if item.source_kind == "active_plan" else 4,
                    conflict_risk=1 if item.source_kind == "history" else 0,
                    metadata={"title": item.title, "fragment_kind": item.fragment_kind, **dict(item.metadata or {})},
                )
            )
        for index, item in enumerate(history_source_candidates):
            level3_candidates.append(
                ContextCandidate(
                    candidate_id=f"{item.source_kind}-{item.fragment_id}-{index}",
                    block=ContextBlockType.EVIDENCE,
                    source_bucket="history",
                    source_type=item.source_kind,
                    source_id=item.source_id,
                    content=item.content,
                    token_cost=max(1, int(item.cost_tokens or count_tokens(item.content))),
                    authority={"anchor": 9, "primary": 8, "supporting": 6, "fallback": 4}.get(item.authority, 4),
                    relevance=max(1, int(round(float(item.score or 0.0) + 3))),
                    recency=5,
                    anchor_alignment=4,
                    conflict_risk=1,
                    metadata={"title": item.title, "fragment_kind": item.fragment_kind, **dict(item.metadata or {})},
                )
            )

        try:
            with measure_build_stage("context_pack"):
                escalation_attempts: list[int] = [1]
                pack = pack_context_candidates(base_candidates, budget, route=route_decision)
                escalation_stop_reason = "target_level_reached" if target_escalation_level <= 1 else ""
                if target_escalation_level >= 2:
                    escalation_attempts.append(2)
                    if level2_candidates:
                        pack = pack_context_candidates([*base_candidates, *level2_candidates], budget, route=route_decision)
                    elif route_decision.route_label in {"guided_plan_continuation", "notebook_followup", "personal_recall", "tool_or_grounding_needed"}:
                        escalation_stop_reason = "no_level2_candidates"
                    else:
                        escalation_stop_reason = "level2_not_required"
                if target_escalation_level >= 3:
                    escalation_attempts.append(3)
                    if level3_candidates:
                        pack = pack_context_candidates(
                            [*base_candidates, *level2_candidates, *level3_candidates],
                            budget,
                            route=route_decision,
                        )
                        escalation_stop_reason = "target_level_reached"
                    elif not source_flags_snapshot["history"]:
                        escalation_stop_reason = "source_flag_disabled:history"
                    else:
                        escalation_stop_reason = "no_level3_candidates"
                if not escalation_stop_reason:
                    escalation_stop_reason = "target_level_reached"
                pack.trace_metadata["escalation_attempts"] = escalation_attempts
                pack.trace_metadata["escalation_stop_reason"] = escalation_stop_reason
        except Exception as exc:
            raise _ContextOrchestrationStageError("context_pack", exc) from exc
        with measure_build_stage("pack_render"):
            anchor_text = _render_evidence_block(pack.anchor_block.selected_candidates, language=language)
            evidence_text = _render_evidence_block(pack.evidence_block.selected_candidates, language=language)
            memory_context = compact_memory_context or _render_memory_context_from_candidates(
                pack.learner_block.selected_candidates,
                language=language,
            )
            user_sections: list[str] = []
            if anchor_text:
                user_sections.append(anchor_text)
            if evidence_text:
                user_sections.append(evidence_text)
            if user_sections:
                user_sections.append(
                    ("## 当前用户问题" if language.startswith("zh") else "## Current User Question")
                    + f"\n{raw_user_content}"
                )
                effective_user_message = "\n\n".join(user_sections)
            else:
                effective_user_message = raw_user_content

            notebook_context = _render_evidence_block(
                [
                    candidate
                    for candidate in pack.evidence_block.selected_candidates
                    if str(getattr(candidate, "source_bucket", "")) in {"notebook", "active_plan"}
                ],
                language=language,
            )
            history_context = _render_evidence_block(
                [
                    candidate
                    for candidate in pack.evidence_block.selected_candidates
                    if str(getattr(candidate, "source_bucket", "")) == "history"
                ],
                language=language,
            )
        history_search_applied = bool(history_context.strip())
        budget.trace_metadata["history_search_applied"] = history_search_applied
        pack.trace_metadata["history_search_applied"] = history_search_applied
        context_trace = build_context_trace_summary(pack, fallback_path="")
        context_trace["build_stage_timings_ms"] = normalize_latency_stage_timings(build_stage_timings_ms)
        return {
            "route_decision": route_decision,
            "budget": budget,
            "pack": pack,
            "context_trace": context_trace,
            "history_result": history_result,
            "effective_user_message": effective_user_message,
            "memory_context": memory_context,
            "notebook_context": notebook_context,
            "history_context": history_context,
            "compiled_learning_truth": compiled_learning_truth,
            "personalization_context": personalization_context,
        }

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        setup_stages = _TurnLatencyStages()
        payload_normalize_started_at = time.perf_counter()
        requested_capability = str(payload.get("capability") or "").strip() or None
        capability = requested_capability or ""
        config_capability = requested_capability or "chat"
        session_id = str(payload.get("session_id") or "").strip()
        raw_user_content = str(payload.get("content") or "").strip()
        raw_config = dict(payload.get("config", {}) or {})
        explicit_chat_mode = "chat_mode" in raw_config
        effective_chat_mode_explicit = explicit_chat_mode
        runtime_only_keys = (
            "_persist_user_message",
            "client_turn_id",
            "followup_question_context",
            "_question_followup_action",
            "semantic_router_enabled",
            "semantic_router_shadow_mode",
            "semantic_router_scope",
            "interaction_hints",
            "billing_context",
            "grading_engine_runtime_shadow",
            "grading_engine_runtime_shadow_engine",
            "grading_engine_runtime_shadow_mode",
            "grading_engine_runtime_shadow_cache_student_id",
            "grading_engine_v1_beta_shadow",
            "enable_luban_v1_beta_shadow",
            "grading_engine_v1_controlled_runtime",
            "grading_engine_v1_llm_adjudication",
            "grading_engine_objective_candidate",
            "grading_engine_m31_governed_objective",
            "grading_engine_textbook_knowledge",
            "general_knowledge_context",
            "interaction_profile",
            "chat_mode_explicit",
            "context_orchestration_enabled",
            "context_sources",
            "active_plan_id",
            "plan_id",
            "guide_session_id",
            "learning_plan_id",
            "exam_track",
        )
        runtime_only_config = {
            key: raw_config.pop(key)
            for key in runtime_only_keys
            if key in raw_config
        }
        runtime_interaction_hints = _extract_interaction_hints(
            {"interaction_hints": runtime_only_config.get("interaction_hints")}
        )
        if runtime_interaction_hints:
            runtime_only_config["interaction_hints"] = runtime_interaction_hints
        else:
            runtime_only_config.pop("interaction_hints", None)
        explicit_exam_track = (
            normalize_exam_track(runtime_only_config.get("exam_track"))
            or normalize_exam_track((runtime_interaction_hints or {}).get("exam_track"))
            or infer_exam_track_from_text(raw_user_content)
        )
        multiple_exam_track_mentions = has_multiple_exam_track_mentions(raw_user_content)
        denied_exam_tracks = infer_denied_exam_tracks_from_text(raw_user_content)
        clear_stored_exam_track = False
        setup_stages.record_since("payload_normalize", payload_normalize_started_at)
        if explicit_exam_track:
            runtime_only_config["exam_track"] = explicit_exam_track
            runtime_interaction_hints = {
                **dict(runtime_interaction_hints or {}),
                "exam_track": explicit_exam_track,
            }
            runtime_only_config["interaction_hints"] = runtime_interaction_hints
        runtime_followup_question_context = normalize_question_followup_context(
            runtime_only_config.get("followup_question_context")
        )
        runtime_followup_action = _normalize_question_followup_action(
            runtime_only_config.get("_question_followup_action")
        )
        stored_active_object = None
        candidate_followup_contexts: list[dict[str, Any] | None] = []
        active_object_lookup_started_at = time.perf_counter()
        if session_id:
            stored_active_object = await self._safe_store_call(
                None,
                "get_active_object_for_start_turn",
                self.store.get_active_object,
                session_id,
                default=None,
            )
            stored_followup_question_context = extract_question_context_from_active_object(
                stored_active_object
            )
            volatile_followup_question_context = self._volatile_question_contexts.get(session_id)
            candidate_followup_contexts.extend(
                [stored_followup_question_context, volatile_followup_question_context]
            )
            billing_context = (
                runtime_only_config.get("billing_context")
                if isinstance(runtime_only_config.get("billing_context"), dict)
                else {}
            )
            mirror_user_id = str(
                billing_context.get("learning_user_id")
                or billing_context.get("user_id")
                or billing_context.get("wallet_user_id")
                or ""
            ).strip()
            for mirror_session_id in _tutorbot_mirror_session_ids(
                bot_id=str(raw_config.get("bot_id") or "").strip(),
                session_id=session_id,
                user_id=mirror_user_id,
            ):
                mirror_active_object = await self._safe_store_call(
                    None,
                    "get_tutorbot_mirror_active_object_for_start_turn",
                    self.store.get_active_object,
                    mirror_session_id,
                    default=None,
                )
                mirror_followup_context = extract_question_context_from_active_object(
                    mirror_active_object
                )
                if mirror_followup_context is not None:
                    candidate_followup_contexts.append(mirror_followup_context)
        setup_stages.record_since("active_object_lookup", active_object_lookup_started_at)
        followup_resolution_started_at = time.perf_counter()
        (
            runtime_followup_question_context,
            runtime_followup_action,
        ) = await _resolve_question_followup_context_and_action(
            user_message=raw_user_content,
            explicit_context=runtime_followup_question_context,
            explicit_action=runtime_followup_action,
            candidate_contexts=candidate_followup_contexts,
        )
        setup_stages.record_since("followup_resolution", followup_resolution_started_at)
        entry_capability_hint = (
            requested_capability
            if requested_capability in {"chat", "tutorbot"}
            else None
        )
        if entry_capability_hint is None and (
            _normalize_interaction_profile_name(runtime_only_config.get("interaction_profile") or "")
            == "tutorbot"
            or str((runtime_interaction_hints or {}).get("profile") or "").strip().lower()
            == "tutorbot"
            or str((runtime_interaction_hints or {}).get("entry_role") or "").strip().lower()
            == "tutorbot"
        ):
            entry_capability_hint = "tutorbot"
        if requested_capability in {"chat", "tutorbot"} or entry_capability_hint:
            runtime_only_config["_entry_capability_hint"] = entry_capability_hint or ""
            requested_capability = None
            capability = ""
            config_capability = "chat"
        mode_selection_active_object = stored_active_object
        if (
            mode_selection_active_object is not None
            and extract_question_context_from_active_object(mode_selection_active_object) is not None
            and runtime_followup_question_context is None
            and followup_action_route(runtime_followup_action) is None
        ):
            mode_selection_active_object = None
        if runtime_followup_question_context is not None:
            runtime_only_config["followup_question_context"] = dict(
                runtime_followup_question_context
            )
        if runtime_followup_action is not None:
            runtime_only_config["_question_followup_action"] = dict(runtime_followup_action)
        public_config_validation_started_at = time.perf_counter()
        try:
            from deeptutor.capabilities.request_contracts import validate_capability_config
            from deeptutor.services.config import get_model_catalog_service
            from deeptutor.services.model_selection import (
                LLMSelection,
                apply_llm_selection_to_catalog,
            )

            validated_public_config = validate_capability_config(config_capability, raw_config)
            llm_selection = LLMSelection.from_payload(payload.get("llm_selection"))
            if llm_selection is not None:
                apply_llm_selection_to_catalog(
                    get_model_catalog_service().load(),
                    llm_selection,
                )
                payload = {**payload, "llm_selection": llm_selection.to_dict()}
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        setup_stages.record_since("public_config_validation", public_config_validation_started_at)
        bot_id = str(validated_public_config.get("bot_id") or "").strip()
        interaction_profile = _normalize_interaction_profile_name(
            runtime_only_config.get("interaction_profile")
            or (runtime_interaction_hints or {}).get("profile")
            or ""
        )
        if interaction_profile:
            runtime_only_config["interaction_profile"] = interaction_profile
        requested_response_mode = resolve_requested_response_mode(
            chat_mode=raw_config.get("chat_mode"),
            interaction_hints=runtime_interaction_hints,
        )
        if _should_select_tutorbot_mode(
            capability=config_capability,
            bot_id=bot_id,
            interaction_profile=interaction_profile,
            interaction_hints=runtime_interaction_hints,
            explicit_chat_mode=explicit_chat_mode,
        ):
            selected_chat_mode, selection_reason = select_response_mode(
                requested_response_mode,
                user_message=raw_user_content,
                interaction_hints=runtime_interaction_hints,
                has_active_object=bool(
                    runtime_followup_question_context
                    or _active_object_requires_deep_mode(mode_selection_active_object)
                ),
            )
            validated_public_config = {
                **validated_public_config,
                "chat_mode": selected_chat_mode,
            }
            runtime_interaction_hints = {
                **dict(runtime_interaction_hints or {}),
                "requested_response_mode": requested_response_mode,
                "effective_response_mode": selected_chat_mode,
                "selected_mode": selected_chat_mode,
                "response_mode_selection_reason": selection_reason,
            }
            runtime_only_config["interaction_hints"] = runtime_interaction_hints
            effective_chat_mode_explicit = True
        bot_runtime_defaults_started_at = time.perf_counter()
        knowledge_chain_defaults = _resolve_bot_runtime_defaults(
            bot_id=bot_id,
            tools=payload.get("tools"),
            knowledge_bases=payload.get("knowledge_bases"),
        )
        setup_stages.record_since("bot_runtime_defaults", bot_runtime_defaults_started_at)
        selected_capability = requested_capability
        capability = selected_capability or (
            ""
            if (
                requested_capability is None
                and knowledge_chain_defaults.get("execution_engine") == "tutorbot_runtime"
            )
            else config_capability
        )
        payload = {
            **payload,
            "capability": selected_capability,
            "_chat_mode_explicit": effective_chat_mode_explicit,
            "tools": knowledge_chain_defaults["tools"],
            "knowledge_bases": knowledge_chain_defaults["knowledge_bases"],
            "config": {
                **validated_public_config,
                **runtime_only_config,
            },
        }
        billing_context = _extract_billing_context(dict(runtime_only_config)) or {}
        ensure_session_started_at = time.perf_counter()
        session = await self.store.ensure_session(
            payload.get("session_id"),
            owner_key=build_user_owner_key(billing_context.get("user_id")),
        )
        setup_stages.record_since("ensure_session", ensure_session_started_at)
        session_preferences = session.get("preferences") if isinstance(session, dict) else {}
        if not explicit_exam_track:
            stored_exam_track = normalize_exam_track(
                session_preferences.get("exam_track") if isinstance(session_preferences, dict) else ""
            )
            if stored_exam_track and stored_exam_track in denied_exam_tracks:
                clear_stored_exam_track = True
                stored_hints = (
                    session_preferences.get("interaction_hints")
                    if isinstance(session_preferences, dict)
                    and isinstance(session_preferences.get("interaction_hints"), dict)
                    else {}
                )
                cleaned_interaction_hints = {
                    **dict(stored_hints),
                    **dict(runtime_interaction_hints or {}),
                }
                cleaned_interaction_hints.pop("exam_track", None)
                runtime_interaction_hints = _extract_interaction_hints(
                    {"interaction_hints": cleaned_interaction_hints}
                )
                runtime_only_config.pop("exam_track", None)
                if runtime_interaction_hints:
                    runtime_only_config["interaction_hints"] = runtime_interaction_hints
                else:
                    runtime_only_config.pop("interaction_hints", None)
                payload["config"] = {
                    key: value
                    for key, value in dict(payload.get("config", {}) or {}).items()
                    if key != "exam_track"
                }
                if runtime_interaction_hints:
                    payload["config"]["interaction_hints"] = runtime_interaction_hints
                else:
                    payload["config"].pop("interaction_hints", None)
            elif stored_exam_track and not multiple_exam_track_mentions:
                explicit_exam_track = stored_exam_track
                runtime_only_config["exam_track"] = explicit_exam_track
                runtime_interaction_hints = {
                    **dict(runtime_interaction_hints or {}),
                    "exam_track": explicit_exam_track,
                }
                payload["config"] = {
                    **dict(payload.get("config", {}) or {}),
                    "exam_track": explicit_exam_track,
                    "interaction_hints": runtime_interaction_hints,
                }
        preference_updates = {
            "chat_mode": (payload.get("config", {}) or {}).get(
                "chat_mode",
                validated_public_config.get("chat_mode", get_default_chat_mode()),
            ),
            "tools": list(payload.get("tools") or []),
            "knowledge_bases": list(payload.get("knowledge_bases") or []),
            "language": str(payload.get("language") or "en"),
            **(
                {"bot_id": str(validated_public_config.get("bot_id") or "").strip()}
                if str(validated_public_config.get("bot_id") or "").strip()
                else {}
            ),
            **({"capability": capability} if capability else {}),
            **({"llm_selection": payload.get("llm_selection")} if payload.get("llm_selection") else {}),
            **(billing_context or {}),
        }
        if explicit_exam_track:
            preference_updates["exam_track"] = explicit_exam_track
        elif clear_stored_exam_track:
            preference_updates["exam_track"] = ""
        if runtime_interaction_hints:
            preference_updates["interaction_hints"] = runtime_interaction_hints
        elif clear_stored_exam_track:
            preference_updates["interaction_hints"] = {}
        update_preferences_started_at = time.perf_counter()
        await self.store.update_session_preferences(
            session["id"],
            preference_updates,
        )
        setup_stages.record_since("update_session_preferences", update_preferences_started_at)
        recover_orphaned_turns_started_at = time.perf_counter()
        await self._recover_orphaned_running_turns(
            session["id"],
            reason="Recovered orphaned running turn before starting a new turn",
        )
        setup_stages.record_since("recover_orphaned_turns", recover_orphaned_turns_started_at)
        cancel_active_turn_started_at = time.perf_counter()
        await self._cancel_active_turn_for_new_request(
            session["id"],
            reason="Cancelled superseded running turn before starting a new turn",
        )
        setup_stages.record_since("cancel_active_turn", cancel_active_turn_started_at)
        create_turn_started_at = time.perf_counter()
        try:
            turn = await self.store.create_turn(session["id"], capability=capability)
        except RuntimeError as exc:
            if "active turn" not in str(exc).lower():
                raise
            cancelled = await self._cancel_active_turn_for_new_request(
                session["id"],
                reason="Cancelled superseded running turn after create_turn conflict",
            )
            if not cancelled:
                await self._recover_orphaned_running_turns(
                    session["id"],
                    reason="Recovered orphaned running turn after create_turn conflict",
                )
                await self._cancel_active_turn_for_new_request(
                    session["id"],
                    reason="Cancelled superseded running turn after orphan recovery conflict",
                )
            try:
                turn = await self.store.create_turn(session["id"], capability=capability)
            except RuntimeError as retry_exc:
                # Active turn persists after cancel/recovery — likely a concurrent start_turn.
                # Raise a clean error so the WS handler can surface an informative client event.
                raise RuntimeError(
                    f"[turn_runtime] start_turn conflict on session {session['id']}: "
                    "active turn persists after cancel/recovery. Concurrent request detected."
                ) from retry_exc
        setup_stages.record_since("create_turn", create_turn_started_at)
        execution = _TurnExecution(
            turn_id=turn["id"],
            session_id=session["id"],
            capability=capability,
            payload=dict(payload),
            turn_view=turn,
        )
        register_execution_started_at = time.perf_counter()
        async with self._lock:
            self._executions[turn["id"]] = execution
        setup_stages.record_since("register_execution", register_execution_started_at)
        get_turn_runtime_metrics().record_turn_started()
        publish_session_event_started_at = time.perf_counter()
        await self._persist_and_publish(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION,
                source="turn_runtime",
                metadata={"session_id": session["id"], "turn_id": turn["id"]},
            ),
        )
        setup_stages.record_since("publish_session_event", publish_session_event_started_at)
        execution.start_turn_setup_stage_timings_ms = setup_stages.snapshot()
        async with self._lock:
            execution.task = asyncio.create_task(self._run_turn(execution))
        return session, turn

    async def cancel_turn(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
        if execution is None or execution.task is None or execution.task.done():
            turn = await self._safe_store_call(
                None,
                "get_turn_for_cancel",
                self.store.get_turn,
                turn_id,
                default=None,
            )
            if turn is None or turn.get("status") != "running":
                return False
            updated = await self._safe_store_call(
                None,
                "cancel_turn_without_execution",
                self.store.update_turn_status,
                turn_id,
                "cancelled",
                "Turn cancelled",
                default=False,
            )
            return bool(updated)
        if execution.terminal_commit_started:
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(execution.task), timeout=2.0)
            return True
        execution.task.cancel()
        return True

    async def subscribe_turn(
        self,
        turn_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        backlog = await self._safe_store_call(
            None,
            "get_turn_backlog",
            self.store.get_turn_events,
            turn_id,
            after_seq,
            default=[],
        )
        last_seq = after_seq
        for item in backlog:
            last_seq = max(last_seq, int(item.get("seq") or 0))
            yield item

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=_MAX_LIVE_SUBSCRIBER_QUEUE_SIZE
        )
        subscriber = _LiveSubscriber(queue=queue)
        execution: _TurnExecution | None = None
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is not None:
                execution.subscribers.append(subscriber)
                execution.first_subscriber_attached.set()

        catchup = await self._safe_store_call(
            None,
            "get_turn_catchup",
            self.store.get_turn_events,
            turn_id,
            last_seq,
            default=[],
        )
        for item in catchup:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            if execution is None:
                yield item
            else:
                _offer_to_subscriber(queue, item)

        turn = await self._safe_store_call(
            None,
            "get_turn_for_subscribe",
            self.store.get_turn,
            turn_id,
            default=None,
        )
        if execution is None:
            if turn is None or turn.get("status") != "running":
                return
            await self._recover_orphaned_running_turns(
                str(turn.get("session_id") or ""),
                reason=f"Recovered orphaned running turn during subscribe: {turn_id}",
            )
            return
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                seq = int(item.get("seq") or 0)
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield item
        finally:
            async with self._lock:
                execution = self._executions.get(turn_id)
                if execution is not None:
                    execution.subscribers = [sub for sub in execution.subscribers if sub is not subscriber]

    async def subscribe_session(
        self,
        session_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        active_turn = await self._safe_store_call(
            None,
            "get_active_turn_for_session_subscribe",
            self.store.get_active_turn,
            session_id,
            default=None,
        )
        if active_turn is None:
            return
        async for item in self.subscribe_turn(active_turn["id"], after_seq=after_seq):
            yield item

    async def _run_turn(self, execution: _TurnExecution) -> None:
        await self._wait_for_first_subscriber(execution)
        payload = execution.payload
        session_id = execution.session_id
        capability_name = str(execution.capability or "").strip()
        turn_id = execution.turn_id
        attachments = []
        attachment_records = []
        document_texts: list[str] = []
        persisted_attachment_records: list[dict[str, Any]] = []
        assistant_events: list[dict[str, Any]] = []
        assistant_content = ""
        authoritative_assistant_content = ""
        assistant_content_source = "content_stream"
        turn_observation: Any | None = None
        turn_observation_cm: Any | None = None
        usage_scope_cm: Any | None = None
        usage_scope_state: Any | None = None
        post_turn_refresh_kwargs: dict[str, Any] | None = None
        terminal_status = "failed"
        llm_selection_token = None
        turn_started_at = time.perf_counter()
        latency_stages = _TurnLatencyStages()
        deadline_task = self._schedule_turn_deadline(execution)
        surface_event_store = get_surface_event_store()
        trace_metadata = {
            "session_id": session_id,
            "turn_id": turn_id,
            **get_release_lineage_metadata(),
            "capability": capability_name,
            "execution_engine": "tutorbot_runtime" if capability_name == "tutorbot" else "capability",
            "bot_id": str((payload.get("config", {}) or {}).get("bot_id", "") or "").strip(),
            "interaction_profile": str(
                (payload.get("config", {}) or {}).get("interaction_profile", "") or ""
            ).strip(),
            "start_turn_setup_stage_timings_ms": dict(
                execution.start_turn_setup_stage_timings_ms or {}
            ),
        }
        await self._persist_and_publish(
            execution,
            StreamEvent(
                type=StreamEventType.PROGRESS,
                source="turn_runtime",
                stage="understanding",
                content=_public_turn_status_text(
                    phase="understanding",
                    language=str(payload.get("language", "en") or "en"),
                ),
                metadata={
                    "status_kind": "turn_status",
                    "phase": "understanding",
                    "public_safe": True,
                },
                visibility=_PUBLIC_VISIBILITY,
            ),
        )
        log_context_tokens: dict[str, Any] | None = None

        def _build_final_observation_metadata(
            *,
            usage_summary: dict[str, Any],
            terminal_status: str,
        ) -> dict[str, Any]:
            assistant_event_summary = _summarize_assistant_events(assistant_events)
            turn_duration_ms = (time.perf_counter() - turn_started_at) * 1000.0
            surface_turn_summary = surface_event_store.get_turn_summary(turn_id)
            skill_metadata = {
                metadata_key: assistant_event_summary[metadata_key]
                for metadata_key in (
                    "question_lifecycle_scene",
                    "skill_stack",
                    "skill_trace",
                    "loader_source",
                    "skill_source_status",
                )
                if metadata_key in assistant_event_summary
            }
            for metadata_key in (
                "question_lifecycle_scene",
                "skill_stack",
                "skill_trace",
                "loader_source",
                "skill_source_status",
            ):
                if metadata_key in trace_metadata and metadata_key not in skill_metadata:
                    skill_metadata[metadata_key] = trace_metadata[metadata_key]
            return {
                **skill_metadata,
                **observability.summary_metadata(usage_summary),
                **trace_metadata,
                **assistant_event_summary,
                "assistant_event_count": len(assistant_events),
                "assistant_content_source": assistant_content_source,
                **build_turn_aae_metadata(
                    trace_metadata=trace_metadata,
                    assistant_event_summary=assistant_event_summary,
                    terminal_status=terminal_status,
                    turn_duration_ms=turn_duration_ms,
                    surface_turn_summary=surface_turn_summary,
                ),
            }

        async def _complete_security_guardrail_turn(
            *,
            security_decision: Any,
            public_source: str,
        ) -> None:
            nonlocal assistant_content, assistant_content_source, terminal_status
            assistant_content = normalize_markdown_for_tutorbot(
                coerce_user_visible_answer(security_decision.content or "")
            )
            assistant_content_source = "security_guardrail"
            security_metadata = {
                "response": assistant_content,
                "guardrail": "tutorbot_security_skill",
                "guardrail_level": security_decision.level,
                "guardrail_signals": list(security_decision.signals),
            }
            for security_event in (
                StreamEvent(
                    type=StreamEventType.STAGE_START,
                    source=public_source,
                    stage="responding",
                    metadata={
                        "stage": "responding",
                        "guardrail": "tutorbot_security_skill",
                    },
                ),
                StreamEvent(
                    type=StreamEventType.CONTENT,
                    source=public_source,
                    stage="responding",
                    content=assistant_content,
                    metadata={
                        "call_kind": "security_guardrail_response",
                        "guardrail": "tutorbot_security_skill",
                    },
                ),
                StreamEvent(
                    type=StreamEventType.RESULT,
                    source=public_source,
                    stage="responding",
                    metadata=security_metadata,
                ),
                StreamEvent(
                    type=StreamEventType.STAGE_END,
                    source=public_source,
                    stage="responding",
                    metadata={
                        "stage": "responding",
                        "guardrail": "tutorbot_security_skill",
                    },
                ),
                StreamEvent(
                    type=StreamEventType.DONE,
                    source=public_source,
                    metadata={"status": "completed"},
                ),
            ):
                payload_event = await self._persist_and_publish(execution, security_event)
                if (
                    payload_event.get("type") not in {"done", "session"}
                    and _event_visibility(payload_event) == _PUBLIC_VISIBILITY
                ):
                    assistant_events.append(payload_event)
            await self._safe_store_call(
                execution,
                "add_security_guardrail_assistant_message",
                self.store.add_message,
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                capability=public_source,
                events=assistant_events,
                metadata=_assistant_message_metadata(
                    turn_id=turn_id,
                    config=dict(payload.get("config", {}) or {}),
                    terminal_status="completed",
                ),
                default=None,
            )
            await self._safe_store_call(
                execution,
                "mark_security_guardrail_turn_completed",
                self.store.update_turn_status,
                turn_id,
                "completed",
                default=False,
            )
            terminal_status = "completed"

        try:
            from deeptutor.agents.notebook import NotebookAnalysisAgent
            from deeptutor.core.context import Attachment, UnifiedContext
            from deeptutor.runtime.orchestrator import ChatOrchestrator
            from deeptutor.services.learner_state import get_learner_state_service
            from deeptutor.services.memory import get_memory_service
            from deeptutor.services.model_selection.runtime import activate_llm_selection
            from deeptutor.services.notebook import notebook_manager
            from deeptutor.services.security.tutorbot_guardrails import classify_tutorbot_user_input
            from deeptutor.services.session.context_builder import ContextBuilder

            request_config = dict(payload.get("config", {}) or {})
            raw_user_content = str(payload.get("content", "") or "")
            entry_capability_hint = str(request_config.pop("_entry_capability_hint", "") or "").strip()
            notebook_references = payload.get("notebook_references", []) or []
            history_references = payload.get("history_references", []) or []
            question_notebook_references = payload.get("question_notebook_references", []) or []
            book_references = payload.get("book_references", []) or []
            requested_skills = _string_list(payload.get("skills"))
            memory_references = _string_list(payload.get("memory_references"))
            followup_question_context = _extract_followup_question_context(request_config)
            followup_question_action = _normalize_question_followup_action(
                request_config.pop("_question_followup_action", None)
            )
            interaction_hints = await self._resolve_interaction_hints(
                session_id,
                request_config,
                execution=execution,
            )
            persist_user_message = _extract_persist_user_message(request_config)
            billing_context = await self._resolve_billing_context(session_id, request_config)
            security_decision = classify_tutorbot_user_input(raw_user_content)
            if security_decision.blocked:
                public_source = capability_name or "chat"
                if persist_user_message:
                    await self._safe_store_call(
                        execution,
                        "add_security_guardrail_user_message",
                        self.store.add_message,
                        session_id=session_id,
                        role="user",
                        content=raw_user_content,
                        capability=public_source,
                        attachments=[],
                        metadata=_request_snapshot_metadata(
                            payload=payload,
                            content=raw_user_content,
                            capability=public_source,
                            config=request_config,
                            attachments=[],
                            notebook_references=notebook_references,
                            history_references=history_references,
                            question_notebook_references=question_notebook_references,
                            book_references=book_references,
                            requested_skills=requested_skills,
                            memory_references=memory_references,
                            llm_selection=(
                                payload.get("llm_selection")
                                if isinstance(payload.get("llm_selection"), dict)
                                else None
                            ),
                            turn_id=turn_id,
                        ),
                        default=None,
                    )
                await _complete_security_guardrail_turn(
                    security_decision=security_decision,
                    public_source=public_source,
                )
                return
            stored_active_object = None
            stored_suspended_object_stack: list[dict[str, Any]] = []
            stored_followup_question_context = None
            volatile_followup_question_context = None
            stored_object_type = ""
            original_stored_suspended_object_stack: list[dict[str, Any]] = []
            if session_id:
                stored_active_object = await self._safe_store_call(
                    execution,
                    "get_active_object",
                    self.store.get_active_object,
                    session_id,
                    default=None,
                )
                stored_suspended_object_stack = await self._safe_store_call(
                    execution,
                    "get_suspended_object_stack",
                    self.store.get_suspended_object_stack,
                    session_id,
                    default=[],
                )
                original_stored_suspended_object_stack = list(stored_suspended_object_stack)
                stored_object_type = str((stored_active_object or {}).get("object_type") or "").strip()
                stored_followup_question_context = extract_question_context_from_active_object(
                    stored_active_object
                )
            if (
                stored_active_object is not None
                and stored_followup_question_context is not None
                and followup_question_context is None
                and followup_action_route(followup_question_action) is None
            ):
                stored_suspended_object_stack = _prepend_suspended_object(
                    stored_suspended_object_stack,
                    stored_active_object,
                )
                stored_active_object = None
                stored_object_type = ""
            resolved_user_id = str((billing_context or {}).get("user_id", "") or "").strip()
            active_plan_id = (
                self._resolve_active_plan_id(request_config, notebook_references)
                or _active_object_plan_id(stored_active_object)
                or _suspended_stack_plan_id(stored_suspended_object_stack)
            )
            if not active_plan_id and _looks_like_learning_plan_request(raw_user_content):
                active_plan_id = _resolve_latest_user_learning_plan_id(resolved_user_id)
            plan_active_object = None
            if active_plan_id:
                try:
                    from deeptutor.services.learning_plan import get_learning_plan_service

                    plan_view = get_learning_plan_service().read_guided_session_view(active_plan_id)
                except Exception:
                    logger.debug("Failed to load guided plan view for %s", active_plan_id, exc_info=True)
                    plan_view = None
                if isinstance(plan_view, dict):
                    plan_user_id = str(plan_view.get("user_id") or "").strip()
                    resolved_user_id = str((billing_context or {}).get("user_id", "") or "").strip()
                    if not plan_user_id or not resolved_user_id or plan_user_id == resolved_user_id:
                        plan_previous_active_object = (
                            stored_active_object
                            if str((stored_active_object or {}).get("object_type") or "").strip()
                            in {"guide_page", "study_plan"}
                            else None
                        )
                        plan_active_object = build_active_object_from_learning_plan_view(
                            plan_view,
                            previous_active_object=plan_previous_active_object,
                            source_turn_id=turn_id,
                        )
            stored_followup_question_context = extract_question_context_from_active_object(
                stored_active_object
            ) or stored_followup_question_context
            if session_id:
                volatile_followup_question_context = self._volatile_question_contexts.get(session_id)
            session_active_object = None
            if (
                session_id
                and not followup_question_context
                and plan_active_object is None
                and stored_object_type in {"", "open_chat_topic"}
            ):
                session_view = await self._safe_store_call(
                    execution,
                    "get_session_for_open_chat_active_object",
                    self.store.get_session,
                    session_id,
                    default=None,
                )
                session_active_object = build_active_object_from_session(
                    session_view,
                    previous_active_object=(
                        stored_active_object if stored_object_type == "open_chat_topic" else None
                    ),
                    source_turn_id=turn_id,
                )
            (
                followup_question_context,
                followup_question_action,
            ) = await _resolve_question_followup_context_and_action(
                user_message=raw_user_content,
                explicit_context=followup_question_context,
                explicit_action=followup_question_action,
                candidate_contexts=[
                    stored_followup_question_context,
                    volatile_followup_question_context,
                ],
            )
            if followup_question_context:
                active_object = build_active_object_from_question_context(
                    followup_question_context,
                    previous_active_object=stored_active_object,
                )
            elif (
                isinstance(plan_active_object, dict)
                and str((stored_active_object or {}).get("object_type") or "").strip()
                in {"guide_page", "study_plan"}
            ):
                active_object = plan_active_object
            elif session_active_object is not None and stored_object_type == "open_chat_topic":
                active_object = session_active_object
            else:
                active_object = stored_active_object or plan_active_object or session_active_object
            if active_object is not None and (
                not _same_active_object_identity(stored_active_object, active_object)
                or stored_active_object != active_object
            ):
                await self._safe_store_call(
                    execution,
                    "set_active_object_for_turn_start",
                    self.store.set_active_object,
                    session_id,
                    active_object,
                    default=False,
                )
            if stored_suspended_object_stack != original_stored_suspended_object_stack:
                await self._safe_store_call(
                    execution,
                    "set_suspended_object_stack_for_turn_start",
                    self.store.set_suspended_object_stack,
                    session_id,
                    stored_suspended_object_stack,
                    default=False,
                )
            turn_semantic_decision = _build_turn_semantic_decision(
                active_object=active_object,
                followup_question_action=followup_question_action,
            )
            if followup_question_context:
                self._volatile_question_contexts[session_id] = dict(followup_question_context)
            notebook_context = ""
            history_context = ""
            context_pack: Any | None = None
            context_route: str = ""
            task_anchor_type: str = ""
            route_confidence = 0.0
            with latency_stages.measure("context_route_preview"):
                try:
                    from deeptutor.services.session.context_router import (
                        ContextRouteInput,
                        decide_context_route,
                    )

                    preview_route = decide_context_route(
                        ContextRouteInput(
                            user_message=raw_user_content,
                            has_active_question=bool(followup_question_context),
                            has_active_plan=bool(active_plan_id or _active_object_plan_id(active_object)),
                            notebook_references=_normalize_reference_tokens(notebook_references),
                            history_references=_normalize_reference_tokens(history_references),
                            explicit_grounding=False,
                            session_followup_hint=False,
                        )
                    )
                    context_route = preview_route.route_label
                    task_anchor_type = preview_route.task_anchor_type.value
                    route_confidence = float(preview_route.confidence or 0.0)
                except Exception:
                    logger.debug("Failed to preview context route", exc_info=True)
            trace_metadata["language"] = payload.get("language", "en")
            raw_interaction_hints = (
                (payload.get("config", {}) or {}).get("interaction_hints")
                if isinstance((payload.get("config", {}) or {}).get("interaction_hints"), dict)
                else {}
            )
            chat_mode = str(request_config.get("chat_mode") or "").strip()
            raw_requested_response_mode = str(
                (interaction_hints or {}).get("requested_response_mode")
                or raw_interaction_hints.get("requested_response_mode")
                or request_config.get("chat_mode")
                or ""
            ).strip()
            requested_response_mode = (
                normalize_requested_response_mode(raw_requested_response_mode)
                if raw_requested_response_mode
                else ""
            )
            effective_response_mode = str(
                request_config.get("chat_mode")
                or (interaction_hints or {}).get("selected_mode")
                or (interaction_hints or {}).get("effective_response_mode")
                or requested_response_mode
            ).strip()
            selected_mode = str(
                (interaction_hints or {}).get("selected_mode")
                or effective_response_mode
            ).strip()
            trace_metadata["chat_mode"] = chat_mode
            trace_metadata["requested_response_mode"] = requested_response_mode
            trace_metadata["effective_response_mode"] = effective_response_mode
            trace_metadata["selected_mode"] = selected_mode
            exam_track = normalize_exam_track(
                request_config.get("exam_track")
                or (interaction_hints or {}).get("exam_track")
            )
            if exam_track:
                trace_metadata["exam_track"] = exam_track
                trace_metadata["exam_track_label"] = exam_track_label(exam_track)
            trace_metadata["response_mode_degrade_reason"] = str(
                (interaction_hints or {}).get("response_mode_degrade_reason") or ""
            ).strip()
            trace_metadata["source"] = str((billing_context or {}).get("source", "") or "").strip()
            trace_metadata["active_object"] = dict(active_object) if active_object else {}
            trace_metadata["suspended_object_stack"] = list(stored_suspended_object_stack)
            trace_metadata["turn_semantic_decision"] = (
                dict(turn_semantic_decision) if turn_semantic_decision else {}
            )
            if context_route:
                trace_metadata["context_route"] = context_route
            if task_anchor_type:
                trace_metadata["task_anchor_type"] = task_anchor_type
                trace_metadata["route_confidence"] = route_confidence
            if followup_question_context:
                trace_metadata["question_followup_context"] = dict(followup_question_context)
            user_id = str((billing_context or {}).get("user_id", "") or "").strip()
            if user_id:
                trace_metadata["user_id"] = user_id
            trace_metadata.update(
                _learning_prompt_intent_trace_metadata(request_config.get("learning_prompt_intent"))
            )
            try:
                with latency_stages.measure("observability_start"):
                    usage_scope_cm = observability.usage_scope(
                        scope_id=turn_id,
                        session_id=session_id,
                        turn_id=turn_id,
                        capability=capability_name,
                    )
                    usage_scope_state = usage_scope_cm.__enter__()
                    turn_observation_cm = observability.start_observation(
                        name=self._initial_turn_trace_name(
                            capability_name=capability_name,
                        ),
                        as_type="chain",
                        input_payload={"content": raw_user_content},
                        metadata=trace_metadata,
                    )
                    turn_observation = turn_observation_cm.__enter__()
                    observation_trace_id = ""
                    trace_id_reader = getattr(observability, "observation_trace_id", None)
                    if callable(trace_id_reader):
                        observation_trace_id = str(
                            trace_id_reader(turn_observation) or ""
                        ).strip()
                    if observation_trace_id:
                        trace_metadata["trace_id"] = observation_trace_id
                        _append_trace_link_event(
                            assistant_events,
                            session_id=session_id,
                            turn_id=turn_id,
                            trace_id=observation_trace_id,
                        )
            except Exception:
                if turn_observation_cm is not None:
                    with contextlib.suppress(Exception):
                        turn_observation_cm.__exit__(None, None, None)
                    turn_observation_cm = None
                if usage_scope_cm is not None:
                    with contextlib.suppress(Exception):
                        usage_scope_cm.__exit__(None, None, None)
                    usage_scope_cm = None
                raise

            with contextlib.nullcontext():

                import uuid as _uuid

                for item in payload.get("attachments", []):
                    filename = str(item.get("filename", "") or "")
                    mime_type = str(item.get("mime_type", "") or "")
                    raw_b64 = str(item.get("base64", "") or "")
                    stored_url = str(item.get("url", "") or "")
                    attachment_id = str(
                        item.get("id")
                        or item.get("attachment_id")
                        or f"att-{len(attachment_records) + 1}"
                    )
                    raw_bytes: bytes | None = None
                    if raw_b64:
                        try:
                            b64_payload = raw_b64.split(",", 1)[1] if "," in raw_b64 else raw_b64
                            raw_bytes = base64.b64decode(b64_payload, validate=False)
                        except Exception:
                            raw_bytes = None
                    if raw_bytes:
                        try:
                            from deeptutor.services.storage import get_attachment_store

                            stored_url = await get_attachment_store().put(
                                session_id=session_id,
                                attachment_id=attachment_id,
                                filename=filename or "attachment",
                                data=raw_bytes,
                                mime_type=mime_type,
                            )
                        except Exception:
                            logger.warning("Failed to persist chat attachment", exc_info=True)

                    record = {
                        "id": str(item.get("id") or _uuid.uuid4().hex),
                        "type": item.get("type", "file"),
                        "url": stored_url,
                        "base64": raw_b64,
                        "filename": filename,
                        "mime_type": mime_type,
                    }
                    attachment_records.append(record)

                try:
                    from deeptutor.utils.document_extractor import extract_documents_from_records

                    document_texts, attachment_records = extract_documents_from_records(
                        attachment_records
                    )
                except Exception:
                    logger.warning("Document attachment extraction failed", exc_info=True)

                attachments = [
                    Attachment(
                        type=record.get("type", "file"),
                        url=record.get("url", ""),
                        base64=record.get("base64", ""),
                        filename=record.get("filename", ""),
                        mime_type=record.get("mime_type", ""),
                    )
                    for record in attachment_records
                ]
                persisted_attachment_records = [
                    {**record, "base64": ""} if record.get("url") else dict(record)
                    for record in attachment_records
                ]

                if followup_question_context:
                    existing_messages = await self._safe_store_call(
                        execution,
                        "get_messages_for_followup_bootstrap",
                        self.store.get_messages_for_context,
                        session_id,
                        default=[],
                    )
                    if not existing_messages:
                        await self._safe_store_call(
                            execution,
                            "add_followup_bootstrap_message",
                            self.store.add_message,
                            session_id=session_id,
                            role="system",
                            content=_format_followup_question_context(
                                followup_question_context,
                                language=str(payload.get("language", "en") or "en"),
                            ),
                            capability=capability_name or "chat",
                            default=None,
                        )

                llm_selection = payload.get("llm_selection")
                llm_config, llm_selection_token = activate_llm_selection(llm_selection)
                if isinstance(llm_selection, dict) and llm_selection:
                    trace_metadata["llm_selection"] = dict(llm_selection)
                trace_metadata["llm_model"] = str(getattr(llm_config, "model", "") or "")
                trace_metadata["llm_provider"] = str(
                    getattr(llm_config, "provider_name", "") or ""
                )
                builder = ContextBuilder(self.store)
                memory_service = get_memory_service()
                learner_state_service = get_learner_state_service()
                user_id = str((billing_context or {}).get("user_id", "") or "").strip()
                source_bot_id = str(request_config.get("bot_id", "") or "").strip()

                history_result = None
                memory_context = ""
                compiled_learning_truth: dict[str, Any] = {}
                personalization_context: dict[str, Any] = {}
                effective_user_message = raw_user_content
                context_build_started_at = time.perf_counter()
                context_trace: dict[str, Any] = {
                    "fallback_path": "legacy",
                    "fallback_stage": "legacy_flag",
                    "fallback_reason": "context_orchestration_disabled",
                    "escalation_level": 0,
                }
                if self._context_orchestration_enabled(request_config):
                    try:
                        orchestrated = await self._build_orchestrated_context_payload(
                            execution=execution,
                            raw_user_content=raw_user_content,
                            payload=payload,
                            request_config=request_config,
                            llm_config=llm_config,
                            builder=builder,
                            learner_state_service=learner_state_service,
                            memory_service=memory_service,
                            notebook_manager=notebook_manager,
                            user_id=user_id,
                            language=str(payload.get("language", "en") or "en"),
                            source_bot_id=source_bot_id,
                            active_plan_id=active_plan_id,
                            active_object=active_object,
                            followup_question_context=followup_question_context,
                            interaction_hints=interaction_hints,
                            notebook_references=notebook_references,
                            history_references=history_references,
                        )
                        history_result = orchestrated["history_result"]
                        context_pack = orchestrated["pack"]
                        effective_user_message = orchestrated["effective_user_message"]
                        memory_context = orchestrated["memory_context"]
                        notebook_context = orchestrated["notebook_context"]
                        history_context = orchestrated["history_context"]
                        compiled_learning_truth = dict(orchestrated.get("compiled_learning_truth") or {})
                        personalization_context = dict(orchestrated.get("personalization_context") or {})
                        context_route = orchestrated["route_decision"].route_label
                        task_anchor_type = orchestrated["route_decision"].task_anchor_type.value
                        route_confidence = float(orchestrated["route_decision"].confidence or 0.0)
                        context_trace = dict(orchestrated.get("context_trace") or {})
                    except _ContextOrchestrationStageError as exc:
                        logger.warning(
                            "Context orchestration failed at stage %s, falling back to legacy path",
                            exc.stage,
                            exc_info=True,
                        )
                        context_trace = {
                            "fallback_path": f"legacy_context_builder:{exc.stage}",
                            "fallback_stage": exc.stage,
                            "fallback_reason": exc.cause_type,
                            "escalation_level": 0,
                        }
                    except Exception:
                        logger.warning("Context orchestration failed, falling back to legacy path", exc_info=True)
                        context_trace = {
                            "fallback_path": "legacy_context_builder:unknown",
                            "fallback_stage": "unknown",
                            "fallback_reason": "UnexpectedError",
                            "escalation_level": 0,
                        }

                if history_result is None:
                    try:
                        history_result = await builder.build(
                            session_id=session_id,
                            llm_config=llm_config,
                            language=payload.get("language", "en"),
                            on_event=lambda event: self._persist_and_publish(execution, event),
                        )
                    except Exception as exc:
                        if self._is_persistence_error(exc):
                            self._mark_persistence_degraded(execution, "build_context_history", exc)
                        else:
                            logger.warning(
                                "Legacy context builder failed, continuing with empty context",
                                exc_info=True,
                            )
                        history_result = SimpleNamespace(
                            conversation_history=[],
                            conversation_summary="",
                            context_text="",
                            token_count=0,
                            budget=0,
                        )
                    if user_id:
                        try:
                            memory_context = learner_state_service.build_context(
                                user_id=user_id,
                                language=str(payload.get("language", "en") or "en"),
                            )
                            if hasattr(learner_state_service, "read_compiled_learning_truth"):
                                projection = learner_state_service.read_compiled_learning_truth(user_id)
                                if isinstance(projection, dict):
                                    compiled_learning_truth = dict(projection)
                                    try:
                                        from deeptutor.services.learner_state.personalization_context import (
                                            build_personalization_context_pack,
                                        )
                                        pcp = build_personalization_context_pack(
                                            user_id=user_id,
                                            learning_brain=compiled_learning_truth,
                                        )
                                        if isinstance(pcp, dict):
                                            personalization_context = pcp
                                    except Exception:
                                        logger.warning(
                                            "Legacy path: PCP projection failed (%s); degrading to empty",
                                            "unknown",
                                            exc_info=True,
                                        )
                        except Exception:
                            logger.warning(
                                "Failed to build learner state context for user %s",
                                user_id,
                                exc_info=True,
                            )
                            memory_context = memory_service.build_memory_context()
                    else:
                        memory_context = memory_service.build_memory_context()

                    if notebook_references and self._context_source_enabled(request_config, "notebook"):
                        referenced_records = notebook_manager.get_records_by_references(
                            notebook_references
                        )
                        if referenced_records:
                            analysis_agent = NotebookAnalysisAgent(
                                language=str(payload.get("language", "en") or "en")
                            )
                            notebook_context = await analysis_agent.analyze(
                                user_question=raw_user_content,
                                records=referenced_records,
                                emit=lambda event: self._persist_and_publish(execution, event),
                            )

                    if history_references and self._context_source_enabled(request_config, "history"):
                        history_records: list[dict[str, Any]] = []
                        for session_ref in history_references:
                            history_session_id = str(session_ref or "").strip()
                            if not history_session_id:
                                continue

                            history_session = await self._safe_store_call(
                                execution,
                                "get_history_reference_session",
                                self.store.get_session,
                                history_session_id,
                                default=None,
                            )
                            if not history_session:
                                continue

                            history_messages = await self._safe_store_call(
                                execution,
                                "get_history_reference_messages",
                                self.store.get_messages_for_context,
                                history_session_id,
                                default=[],
                            )
                            transcript_lines = [
                                f"## {str(message.get('role', '')).title()}\n{message.get('content', '')}"
                                for message in history_messages
                                if str(message.get("content", "") or "").strip()
                            ]
                            if not transcript_lines:
                                continue

                            history_summary = str(
                                history_session.get("compressed_summary", "") or ""
                            ).strip()
                            if not history_summary:
                                history_summary = _clip_text(
                                    " ".join(
                                        str(message.get("content", "") or "").strip()
                                        for message in history_messages[-4:]
                                        if str(message.get("content", "") or "").strip()
                                    ),
                                    limit=400,
                                )
                            if not history_summary:
                                history_summary = f"{len(history_messages)} messages"

                            history_records.append(
                                {
                                    "id": history_session_id,
                                    "notebook_id": "__history__",
                                    "notebook_name": "History",
                                    "title": str(
                                        history_session.get("title", "") or "Untitled session"
                                    ),
                                    "summary": history_summary,
                                    "output": "\n\n".join(transcript_lines),
                                    "metadata": {
                                        "session_id": history_session_id,
                                        "source": "history",
                                    },
                                }
                            )

                        if history_records:
                            analysis_agent = NotebookAnalysisAgent(
                                language=str(payload.get("language", "en") or "en")
                            )
                            history_context = await analysis_agent.analyze(
                                user_question=raw_user_content,
                                records=history_records,
                                emit=lambda event: self._persist_and_publish(execution, event),
                            )
                            if not history_context.strip():
                                max_fallback_chars = 8000
                                parts: list[str] = []
                                total = 0
                                for record in history_records:
                                    output = record.get("output")
                                    if not output:
                                        continue
                                    part = f"## Session: {record.get('title', 'Untitled')}\n{output}"
                                    if total + len(part) > max_fallback_chars:
                                        remaining = max_fallback_chars - total
                                        if remaining > 100:
                                            parts.append(part[:remaining] + "\n...(truncated)")
                                        break
                                    parts.append(part)
                                    total += len(part)
                                history_context = "\n\n".join(parts)

                    context_parts: list[str] = []
                    if document_texts:
                        context_parts.append("[Attached Documents]\n" + "\n\n".join(document_texts))
                    if notebook_context:
                        context_parts.append(f"[Notebook Context]\n{notebook_context}")
                    if history_context:
                        context_parts.append(f"[History Context]\n{history_context}")
                    if context_parts:
                        context_parts.append(f"[User Question]\n{raw_user_content}")
                        effective_user_message = "\n\n".join(context_parts)
                latency_stages.record_since("context_build", context_build_started_at)

                if document_texts and "[Attached Documents]" not in effective_user_message:
                    effective_user_message = (
                        "[Attached Documents]\n"
                        + "\n\n".join(document_texts)
                        + f"\n\n[User Question]\n{effective_user_message}"
                    )

                conversation_history = list(history_result.conversation_history)
                conversation_context_text = history_result.context_text
                trace_metadata.update(
                    {
                        "context_route": context_route,
                        "task_anchor_type": task_anchor_type,
                        "escalation_level": context_trace.get("escalation_level"),
                        "route_confidence": route_confidence,
                        "loaded_sources": list(context_trace.get("loaded_sources", []) or []),
                        "candidate_sources": list(context_trace.get("candidate_sources", []) or []),
                        "excluded_sources": list(context_trace.get("excluded_sources", []) or []),
                        "token_budget_total": context_trace.get("token_budget_total"),
                        "token_budget_used": context_trace.get("token_budget_used"),
                        "token_budget_by_source": dict(context_trace.get("token_budget_by_source", {}) or {}),
                        "compression_applied": context_trace.get("compression_applied"),
                        "history_search_applied": context_trace.get("history_search_applied"),
                        "context_build_stage_timings_ms": context_trace.get("build_stage_timings_ms"),
                            "fallback_path": context_trace.get("fallback_path", ""),
                        }
                )

                context = UnifiedContext(
                    session_id=session_id,
                    user_message=effective_user_message,
                    conversation_history=conversation_history,
                    enabled_tools=payload.get("tools"),
                    active_capability=payload.get("capability") or None,
                    knowledge_bases=payload.get("knowledge_bases", []),
                    attachments=attachments,
                    config_overrides=request_config,
                    language=payload.get("language", "en"),
                    notebook_context=notebook_context,
                    history_context=history_context,
                    memory_context=memory_context,
                    metadata={
                        "raw_user_message": raw_user_content,
                        "conversation_summary": history_result.conversation_summary,
                        "conversation_context_text": conversation_context_text,
                        "history_token_count": history_result.token_count,
                        "history_budget": history_result.budget,
                        "chat_mode_explicit": bool(payload.get("_chat_mode_explicit", False)),
                        "turn_id": turn_id,
                        **get_release_lineage_metadata(),
                        "bot_id": str(request_config.get("bot_id", "") or "").strip(),
                        "billing_context": billing_context or {},
                        "source": str((billing_context or {}).get("source", "") or "").strip(),
                        "interaction_profile": str(
                            payload.get("config", {}).get("interaction_profile", "") or ""
                        ).strip(),
                        "entry_capability_hint": str(
                            entry_capability_hint
                        ).strip(),
                        "requested_response_mode": str(
                            (interaction_hints or {}).get("requested_response_mode") or ""
                        ).strip(),
                        "selected_mode": str(
                            request_config.get("chat_mode")
                            or (interaction_hints or {}).get("selected_mode")
                            or ""
                        ).strip(),
                        "response_mode_selection_reason": str(
                            (interaction_hints or {}).get("response_mode_selection_reason") or ""
                        ).strip(),
                        "active_object": active_object or {},
                        "suspended_object_stack": stored_suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision or {},
                        "interaction_hints": interaction_hints or {},
                        **(
                            {"general_knowledge_context": request_config["general_knowledge_context"]}
                            if isinstance(request_config.get("general_knowledge_context"), bool)
                            else {}
                        ),
                        **(
                            {
                                "exam_track": exam_track,
                                "exam_track_label": exam_track_label(exam_track),
                            }
                            if exam_track
                            else {}
                        ),
                        "notebook_references": notebook_references,
                        "history_references": history_references,
                        "memory_context": memory_context,
                        **(
                            {
                                "llm_selection": dict(llm_selection),
                                "llm_model": str(getattr(llm_config, "model", "") or ""),
                                "llm_provider": str(
                                    getattr(llm_config, "provider_name", "") or ""
                                ),
                            }
                            if isinstance(llm_selection, dict) and llm_selection
                            else {}
                        ),
                        "context_route": context_route,
                        "task_anchor_type": task_anchor_type,
                        "escalation_level": context_trace.get("escalation_level"),
                        "route_confidence": route_confidence,
                        "context_pack_trace": context_trace,
                        "token_budget_total": context_trace.get("token_budget_total"),
                        "token_budget_used": context_trace.get("token_budget_used"),
                        "token_budget_by_source": context_trace.get("token_budget_by_source", {}),
                        "loaded_sources": context_trace.get("loaded_sources", []),
                        "candidate_sources": context_trace.get("candidate_sources", []),
                        "excluded_sources": context_trace.get("excluded_sources", []),
                        "compression_applied": context_trace.get("compression_applied"),
                        "history_search_applied": context_trace.get("history_search_applied"),
                        "fallback_path": context_trace.get("fallback_path", ""),
                        **(
                            {"compiled_learning_truth": compiled_learning_truth}
                            if compiled_learning_truth
                            else {}
                        ),
                        **(
                            {"personalization_context": personalization_context}
                            if personalization_context
                            else {}
                        ),
                        **(
                            {
                                "question_followup_context": dict(followup_question_context),
                            }
                            if followup_question_context is not None
                            else {}
                        ),
                        **(
                            {
                                "question_followup_action": followup_question_action,
                            }
                            if followup_question_action
                            else {}
                        ),
                    },
                )

                selector_orchestrator = ChatOrchestrator()
                selector = getattr(selector_orchestrator, "_select_capability", None)
                capability_selection_started_at = time.perf_counter()
                if not capability_name and callable(selector):
                    resolved_capability = await selector(context)
                    capability_name = await self._canonicalize_execution_capability(
                        execution,
                        resolved_capability,
                    )
                    trace_metadata["capability"] = capability_name
                    trace_metadata["execution_engine"] = (
                        "tutorbot_runtime" if capability_name == "tutorbot" else "capability"
                    )
                    if usage_scope_state is not None:
                        with contextlib.suppress(Exception):
                            usage_scope_state.capability = capability_name
                    context.active_capability = capability_name
                latency_stages.record_since("capability_selection", capability_selection_started_at)

                log_context_tokens = bind_log_context(
                    user_id=user_id,
                    session_id=session_id,
                    turn_id=turn_id,
                )

                if persist_user_message:
                    user_message_persist_started_at = time.perf_counter()
                    await self._safe_store_call(
                        execution,
                        "add_user_message",
                        self.store.add_message,
                        session_id=session_id,
                        role="user",
                        content=raw_user_content,
                        capability=capability_name,
                        attachments=persisted_attachment_records,
                        metadata=_request_snapshot_metadata(
                            payload=payload,
                            content=raw_user_content,
                            capability=capability_name,
                            config=request_config,
                            attachments=persisted_attachment_records,
                            notebook_references=notebook_references,
                            history_references=history_references,
                            question_notebook_references=question_notebook_references,
                            book_references=book_references,
                            requested_skills=requested_skills,
                            memory_references=memory_references,
                            llm_selection=(
                                payload.get("llm_selection")
                                if isinstance(payload.get("llm_selection"), dict)
                                else None
                            ),
                            turn_id=turn_id,
                        ),
                        default=None,
                    )
                    latency_stages.record_since("user_message_persist", user_message_persist_started_at)

                orch = selector_orchestrator
                await self._persist_and_publish(
                    execution,
                    StreamEvent(
                        type=StreamEventType.PROGRESS,
                        source="turn_runtime",
                        stage="writing",
                        content=_public_turn_status_text(
                            phase="writing",
                            language=str(payload.get("language", "en") or "en"),
                        ),
                        metadata={
                            "status_kind": "turn_status",
                            "phase": "writing",
                            "public_safe": True,
                        },
                        visibility=_PUBLIC_VISIBILITY,
                    ),
                )
                capability_stream_started_at = time.perf_counter()
                capability_stream_stage_timings = _TurnLatencyStages()
                capability_stream_event_counts: dict[str, int] = {}

                def _record_capability_stream_since_once(stage: str) -> None:
                    if capability_stream_stage_timings.has_stage(stage):
                        return
                    capability_stream_stage_timings.record_since(stage, capability_stream_started_at)

                async for event in orch.handle(context):
                    _record_capability_stream_since_once("first_event")
                    event_type_name = str(getattr(event.type, "value", event.type) or "").strip()
                    if event_type_name:
                        capability_stream_event_counts[event_type_name] = (
                            capability_stream_event_counts.get(event_type_name, 0) + 1
                        )
                    if event_type_name == "content":
                        _record_capability_stream_since_once("first_content")
                    elif event_type_name == "result":
                        _record_capability_stream_since_once("first_result")
                    elif event_type_name == "tool_call":
                        _record_capability_stream_since_once("first_tool_call")
                    elif event_type_name == "tool_result":
                        _record_capability_stream_since_once("first_tool_result")
                    if event.type == StreamEventType.SESSION:
                        continue
                    if _event_visibility(event) == _PUBLIC_VISIBILITY:
                        _record_capability_stream_since_once("first_public_event")
                    event_source = str(event.source or "").strip()
                    if (
                        event_source
                        and event_source != capability_name
                        and event_source not in {"orchestrator", "turn_runtime"}
                    ):
                        from deeptutor.runtime.registry.capability_registry import (
                            get_capability_registry,
                        )

                        if get_capability_registry().get(event_source) is not None:
                            capability_name = await self._canonicalize_execution_capability(
                                execution,
                                event_source,
                            )
                            trace_metadata["capability"] = capability_name
                            trace_metadata["execution_engine"] = (
                                "tutorbot_runtime" if capability_name == "tutorbot" else "capability"
                            )
                            if usage_scope_state is not None:
                                with contextlib.suppress(Exception):
                                    usage_scope_state.capability = capability_name
                            context.active_capability = capability_name
                    if event.type == StreamEventType.RESULT:
                        result_trace_metadata = {
                            **trace_metadata,
                            **dict(event.metadata or {}),
                        }
                        event.metadata = _enrich_result_question_authority_from_trace(
                            dict(event.metadata or {}),
                            result_trace_metadata,
                        )
                    event_persist_started_at = time.perf_counter()
                    payload_event = await self._persist_and_publish(execution, event)
                    capability_stream_stage_timings.add_duration(
                        "event_persist_total",
                        (time.perf_counter() - event_persist_started_at) * 1000.0,
                    )
                    if (
                        payload_event.get("type") not in {"done", "session"}
                        and _event_visibility(payload_event) == _PUBLIC_VISIBILITY
                    ):
                        assistant_events.append(payload_event)
                    authoritative_candidate = _extract_authoritative_assistant_content(event)
                    if authoritative_candidate:
                        authoritative_assistant_content = authoritative_candidate
                        assistant_content_source = (
                            "result.response" if event.type == StreamEventType.RESULT else "final_content"
                        )
                    elif _should_capture_assistant_content(event):
                        assistant_content += event.content
                latency_stages.record_since("capability_stream", capability_stream_started_at)
                trace_metadata["capability_stream_stage_timings_ms"] = (
                    capability_stream_stage_timings.snapshot()
                )
                trace_metadata["capability_stream_event_counts"] = _normalize_non_negative_event_counts(
                    capability_stream_event_counts
                )
                trace_metadata.update(
                    {
                        "active_object": dict(context.metadata.get("active_object", {}) or {}),
                        "suspended_object_stack": list(
                            context.metadata.get("suspended_object_stack", []) or []
                        ),
                        "turn_semantic_decision": dict(
                            context.metadata.get("turn_semantic_decision", {}) or {}
                        ),
                        "semantic_router_mode": str(
                            context.metadata.get("semantic_router_mode", "") or ""
                        ).strip(),
                        "semantic_router_mode_reason": str(
                            context.metadata.get("semantic_router_mode_reason", "") or ""
                        ).strip(),
                        "semantic_router_scope": str(
                            context.metadata.get("semantic_router_scope", "") or ""
                        ).strip(),
                        "semantic_router_scope_match": bool(
                            context.metadata.get("semantic_router_scope_match", False)
                        ),
                        "semantic_router_shadow_decision": dict(
                            context.metadata.get("semantic_router_shadow_decision", {}) or {}
                        ),
                        "semantic_router_shadow_route": str(
                            context.metadata.get("semantic_router_shadow_route", "") or ""
                        ).strip(),
                        "semantic_router_selected_capability": str(
                            context.metadata.get("semantic_router_selected_capability", "")
                            or ""
                        ).strip(),
                    }
                )
                if (
                    isinstance(context.metadata.get("question_followup_context"), dict)
                    and context.metadata.get("question_followup_context")
                ):
                    trace_metadata["question_followup_context"] = dict(
                        context.metadata.get("question_followup_context", {}) or {}
                    )
                elif "question_followup_context" in trace_metadata:
                    trace_metadata.pop("question_followup_context", None)
                assistant_content = authoritative_assistant_content or assistant_content
                assistant_content = normalize_markdown_for_tutorbot(
                    coerce_user_visible_answer(assistant_content)
                )
                execution.terminal_commit_started = True
                await self._safe_store_call(
                    execution,
                    "add_assistant_message",
                    self.store.add_message,
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    metadata=_assistant_message_metadata(
                        turn_id=turn_id,
                        config=request_config,
                        terminal_status="completed",
                    ),
                    default=None,
                )
                usage_summary = observability.get_current_usage_summary()
                billing_capture = self._capture_mobile_points(
                    billing_context,
                    assistant_content,
                    session_id=session_id,
                    turn_id=turn_id,
                    usage_summary=usage_summary,
                )
                if billing_capture and billing_capture.get("status") == "captured":
                    with contextlib.suppress(Exception):
                        observability.mark_usage_scope_billable(
                            turn_id=turn_id,
                            billing_capture=billing_capture,
                        )
                if billing_capture:
                    trace_metadata["billing_capture"] = billing_capture
                self._record_mobile_learning(
                    billing_context,
                    raw_user_content,
                    assistant_content,
                )
                await self._safe_store_call(
                    execution,
                    "mark_turn_completed",
                    self.store.update_turn_status,
                    turn_id,
                    "completed",
                    default=False,
                )
                assistant_event_summary = _summarize_assistant_events(assistant_events)
                observability.update_observation(
                    turn_observation,
                    output_payload={"assistant_content": assistant_content},
                    metadata=_build_final_observation_metadata(
                        usage_summary=usage_summary,
                        terminal_status="completed",
                    ),
                    usage_details=observability.usage_details_from_summary(usage_summary),
                    cost_details=observability.cost_details_from_summary(usage_summary),
                    usage_source="summary",
                )
                post_turn_refresh_kwargs = {
                    "turn_id": turn_id,
                    "user_id": user_id,
                    "raw_user_content": raw_user_content,
                    "assistant_content": assistant_content,
                    "session_id": session_id,
                    "capability_name": capability_name or "chat",
                    "language": str(payload.get("language", "en") or "en"),
                    "source_bot_id": source_bot_id,
                    "context_route": context_route,
                    "task_anchor_type": task_anchor_type,
                    "learner_state_service": learner_state_service,
                    "memory_service": memory_service,
                    "learning_prompt_intent": (
                        dict(request_config.get("learning_prompt_intent") or {})
                        if isinstance(request_config.get("learning_prompt_intent"), dict)
                        else None
                    ),
                    "source_refs": (
                        list(assistant_event_summary.get("sources") or [])
                        if isinstance(assistant_event_summary, dict)
                        else []
                    ),
                }
                terminal_status = "completed"
        except asyncio.CancelledError:
            timed_out = bool(execution.deadline_exceeded)
            cancelled_status = "failed" if timed_out else "cancelled"
            cancelled_message = (
                f"Turn exceeded runtime deadline after {self._turn_timeout_seconds(execution.payload):.1f}s"
                if timed_out
                else "Turn cancelled"
            )
            public_assistant_content = _safe_terminal_assistant_content(
                assistant_content,
                status=cancelled_status,
            )
            usage_summary = observability.get_current_usage_summary()
            assistant_event_summary = _summarize_assistant_events(assistant_events)
            observability.update_observation(
                turn_observation,
                output_payload={"assistant_content": public_assistant_content},
                metadata=_build_final_observation_metadata(
                    usage_summary=usage_summary,
                    terminal_status=cancelled_status,
                ),
                usage_details=observability.usage_details_from_summary(usage_summary),
                cost_details=observability.cost_details_from_summary(usage_summary),
                usage_source="summary",
                level="ERROR",
                status_message=cancelled_message,
            )
            await self._safe_store_call(
                execution,
                "add_failed_assistant_message" if timed_out else "add_cancelled_assistant_message",
                self.store.add_message,
                session_id=session_id,
                role="assistant",
                content=public_assistant_content,
                capability=capability_name,
                events=assistant_events,
                metadata=_assistant_message_metadata(
                    turn_id=turn_id,
                    config=request_config,
                    terminal_status=cancelled_status,
                ),
                default=None,
            )
            await self._safe_store_call(
                execution,
                "mark_turn_failed" if timed_out else "mark_turn_cancelled",
                self.store.update_turn_status,
                turn_id,
                cancelled_status,
                cancelled_message,
                default=False,
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.ERROR,
                    source=capability_name,
                    content=public_assistant_content,
                    metadata={"turn_terminal": True, "status": cancelled_status},
                ),
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": cancelled_status},
                ),
            )
            terminal_status = cancelled_status
            if not timed_out:
                raise
        except Exception as exc:
            public_assistant_content = _safe_terminal_assistant_content(
                assistant_content,
                status="failed",
            )
            usage_summary = observability.get_current_usage_summary()
            assistant_event_summary = _summarize_assistant_events(assistant_events)
            observability.update_observation(
                turn_observation,
                output_payload={"assistant_content": public_assistant_content},
                metadata=_build_final_observation_metadata(
                    usage_summary=usage_summary,
                    terminal_status="failed",
                ),
                usage_details=observability.usage_details_from_summary(usage_summary),
                cost_details=observability.cost_details_from_summary(usage_summary),
                usage_source="summary",
                level="ERROR",
                status_message=str(exc),
            )
            logger.error("Turn %s failed: %s", turn_id, exc, exc_info=True)
            await self._safe_store_call(
                execution,
                "add_failed_assistant_message",
                self.store.add_message,
                session_id=session_id,
                role="assistant",
                content=public_assistant_content,
                capability=capability_name,
                events=assistant_events,
                metadata=_assistant_message_metadata(
                    turn_id=turn_id,
                    config=request_config,
                    terminal_status="failed",
                ),
                default=None,
            )
            await self._safe_store_call(
                execution,
                "mark_turn_failed",
                self.store.update_turn_status,
                turn_id,
                "failed",
                str(exc),
                default=False,
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.ERROR,
                    source=capability_name,
                    content=public_assistant_content,
                    metadata={"turn_terminal": True, "status": "failed"},
                ),
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": "failed"},
                ),
            )
        finally:
            if deadline_task is not None:
                deadline_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await deadline_task
            if llm_selection_token is not None:
                with contextlib.suppress(Exception):
                    from deeptutor.services.model_selection.runtime import reset_llm_selection

                    reset_llm_selection(llm_selection_token)
            terminal_usage_summary = observability.get_current_usage_summary()
            if terminal_status == "completed" and post_turn_refresh_kwargs is not None:
                self._schedule_post_turn_refresh(**post_turn_refresh_kwargs)
            if turn_observation_cm is not None:
                with contextlib.suppress(Exception):
                    turn_observation_cm.__exit__(None, None, None)
            if usage_scope_cm is not None:
                with contextlib.suppress(Exception):
                    usage_scope_cm.__exit__(None, None, None)
            turn_duration_ms = (time.perf_counter() - turn_started_at) * 1000.0
            trace_metadata["latency_stages_ms"] = latency_stages.snapshot()
            get_turn_runtime_metrics().record_turn_finished(
                status=terminal_status,
                duration_ms=turn_duration_ms,
                stage_timings_ms=trace_metadata.get("latency_stages_ms"),
            )
            with contextlib.suppress(Exception):
                event_log = get_turn_event_log()
                terminal_trace_metadata = _build_final_observation_metadata(
                    usage_summary=terminal_usage_summary,
                    terminal_status=terminal_status,
                )
                append_ok = event_log.append(
                    _build_terminal_turn_observation_event(
                        session_id=session_id,
                        turn_id=turn_id,
                        status=terminal_status,
                        capability_name=capability_name,
                        duration_ms=turn_duration_ms,
                        trace_metadata=terminal_trace_metadata,
                        usage_summary=terminal_usage_summary,
                    )
                )
                if not append_ok:
                    logger.debug(
                        "Turn observation event append failed: %s",
                        event_log.stats().get("last_write_error"),
                    )
            if log_context_tokens:
                reset_log_context(log_context_tokens)
            async with self._lock:
                current = self._executions.get(turn_id)
                if current is not None:
                    for subscriber in current.subscribers:
                        _offer_to_subscriber(subscriber.queue, None)
                    self._executions.pop(turn_id, None)

    async def _persist_and_publish(
        self,
        execution: _TurnExecution,
        event: StreamEvent,
    ) -> dict[str, Any]:
        metadata = dict(event.metadata or {})
        metadata = _sanitize_public_terminal_event(event, metadata)
        if event.type == StreamEventType.DONE and not metadata.get("status"):
            metadata["status"] = "completed"
        if event.type == StreamEventType.RESULT:
            usage_summary = observability.get_current_usage_summary()
            if usage_summary:
                nested_metadata = (
                    dict(metadata.get("metadata", {}))
                    if isinstance(metadata.get("metadata"), dict)
                    else {}
                )
                existing_cost_summary = nested_metadata.get("cost_summary")
                if existing_cost_summary and existing_cost_summary != usage_summary:
                    nested_metadata["capability_cost_summary"] = existing_cost_summary
                    nested_metadata["cost_summary"] = usage_summary
                metadata["metadata"] = nested_metadata
            selected_mode = _result_selected_mode(metadata, execution)
            if selected_mode and not str(metadata.get("selected_mode") or "").strip():
                metadata["selected_mode"] = selected_mode
            execution_path = _result_execution_path(
                metadata,
            execution,
                event_source=str(event.source or "").strip(),
                selected_mode=str(metadata.get("selected_mode") or selected_mode).strip(),
            )
            if execution_path and not str(metadata.get("execution_path") or "").strip():
                metadata["execution_path"] = execution_path
            active_object = _result_active_object(metadata)
            suspended_object_stack = _result_suspended_object_stack(metadata)
            if active_object is not None:
                metadata["active_object"] = dict(active_object)
            metadata["suspended_object_stack"] = list(suspended_object_stack)

            question_followup_context = (
                extract_question_context_from_active_object(active_object)
                if active_object is not None
                else _result_question_followup_context(metadata)
            )
            if question_followup_context is not None and "question_followup_context" not in metadata:
                metadata["question_followup_context"] = dict(question_followup_context)
            if active_object is not None:
                self._volatile_question_contexts[execution.session_id] = dict(
                    question_followup_context or {}
                )
                await self._safe_store_call(
                    execution,
                    "set_active_object",
                    self.store.set_active_object,
                    execution.session_id,
                    active_object,
                    default=False,
                )
                await self._safe_store_call(
                    execution,
                    "set_suspended_object_stack",
                    self.store.set_suspended_object_stack,
                    execution.session_id,
                    suspended_object_stack,
                    default=False,
                )
            elif question_followup_context is not None:
                self._volatile_question_contexts[execution.session_id] = dict(question_followup_context)
                await self._safe_store_call(
                    execution,
                    "set_active_object_from_question_adapter",
                    self.store.set_active_object,
                    execution.session_id,
                    question_followup_context,
                    default=False,
                )
                await self._safe_store_call(
                    execution,
                    "set_suspended_object_stack_from_question_adapter",
                    self.store.set_suspended_object_stack,
                    execution.session_id,
                    suspended_object_stack,
                    default=False,
                )
            elif suspended_object_stack:
                await self._safe_store_call(
                    execution,
                    "set_suspended_object_stack_only",
                    self.store.set_suspended_object_stack,
                    execution.session_id,
                    suspended_object_stack,
                    default=False,
                )
        event.metadata = metadata
        event.session_id = execution.session_id
        event.turn_id = execution.turn_id
        payload = event.to_dict()
        try:
            persisted = await self.store.append_turn_event(execution.turn_id, payload)
        except ValueError as exc:
            # A turn can disappear when the session is deleted while the turn task
            # is still draining events. Avoid cascading failures in the error path.
            if "Turn not found:" not in str(exc):
                raise
            logger.warning(
                "Skip persisting event for missing turn %s (%s)",
                execution.turn_id,
                event.type.value,
            )
            persisted = payload
        except Exception as exc:
            if not self._is_persistence_error(exc):
                raise
            self._mark_persistence_degraded(execution, "append_turn_event", exc)
            persisted = payload
        async with self._lock:
            subscribers = list(self._executions.get(execution.turn_id, execution).subscribers)
        for subscriber in subscribers:
            _offer_to_subscriber(subscriber.queue, persisted)
        self._mirror_event_to_workspace(execution, persisted)
        return persisted

    @staticmethod
    def _mirror_event_to_workspace(execution: _TurnExecution, payload: dict[str, Any]) -> None:
        """Mirror turn events to task-local ``events.jsonl`` files under ``data/user/workspace``."""
        try:
            path_service = get_path_service()
            task_dir = path_service.get_task_workspace(execution.capability, execution.turn_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            event_file = task_dir / "events.jsonl"
            with open(event_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Failed to mirror turn event to workspace", exc_info=True)


_runtime_instance: TurnRuntimeManager | None = None


def get_turn_runtime_manager() -> TurnRuntimeManager:
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = TurnRuntimeManager()
    return _runtime_instance


__all__ = ["TurnRuntimeManager", "get_turn_runtime_manager"]
