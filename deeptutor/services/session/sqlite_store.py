"""
SQLite-backed unified chat session store.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeptutor.services.path_service import get_path_service
from deeptutor.services.question_followup import normalize_question_followup_context
from deeptutor.services.render_presentation import build_canonical_presentation

_STALE_TURN_TIMEOUT_SECONDS = 180.0
_SQLITE_TIMEOUT_SECONDS = 5.0
_SQLITE_BUSY_TIMEOUT_MS = 5000
_INTERACTION_HINT_SYSTEM_PREFIXES = (
    "你正在一个学习型产品场景中工作。",
    "You are operating in a learning-product scenario.",
)
_SESSION_TITLE_PLACEHOLDERS = {"new conversation", "新对话"}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


_QUESTION_ACTIVE_OBJECT_TYPES = {"single_question", "question_set"}
_QUESTION_ACTIVE_OBJECT_TYPE_ALIASES = {
    "question": "single_question",
    "single_question": "single_question",
    "question_set": "question_set",
}
_LEARNING_ACTIVE_OBJECT_TYPES = {"guide_page", "study_plan"}
_SESSION_ACTIVE_OBJECT_TYPES = {"open_chat_topic"}
_PLAN_ACTIVE_OBJECT_TYPES = {"guide_page", "study_plan"}


def _coerce_positive_int(value: Any) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _coerce_timestamp(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _normalize_runtime_state(runtime_state: Any) -> dict[str, Any]:
    return dict(runtime_state) if isinstance(runtime_state, dict) else {}


def _normalize_question_active_object_type(
    value: Any,
    *,
    has_items: bool,
) -> str:
    normalized = _QUESTION_ACTIVE_OBJECT_TYPE_ALIASES.get(str(value or "").strip().lower())
    if normalized:
        return normalized
    return "question_set" if has_items else "single_question"


def _build_question_active_object_scope(question_context: dict[str, Any]) -> dict[str, Any]:
    items = question_context.get("items") if isinstance(question_context.get("items"), list) else []
    question_ids = [
        str(item.get("question_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    ]
    primary_question_id = str(question_context.get("question_id") or "").strip()
    if primary_question_id and primary_question_id not in question_ids:
        question_ids.insert(0, primary_question_id)
    return {
        "domain": "question",
        "question_ids": question_ids,
        "item_count": len(items) if items else 1,
    }


def _derive_question_active_object_id(question_context: dict[str, Any]) -> str:
    items = question_context.get("items") if isinstance(question_context.get("items"), list) else []
    item_ids = [
        str(item.get("question_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    ]
    if len(item_ids) > 1:
        parent_quiz_session_id = str(question_context.get("parent_quiz_session_id") or "").strip()
        if parent_quiz_session_id:
            return parent_quiz_session_id
        return "question_set:" + "|".join(item_ids[:8])

    question_id = str(question_context.get("question_id") or "").strip()
    if question_id:
        return question_id

    if item_ids:
        return item_ids[0]

    parent_quiz_session_id = str(question_context.get("parent_quiz_session_id") or "").strip()
    if parent_quiz_session_id:
        return parent_quiz_session_id

    question_text = str(question_context.get("question") or "").strip().lower()
    if not question_text:
        return "question"
    token = "".join(char if char.isalnum() else "_" for char in question_text).strip("_")
    return f"question:{token[:48] or 'anonymous'}"


def _resolve_learning_plan_current_page(
    plan_view: dict[str, Any],
) -> tuple[dict[str, Any] | None, int]:
    pages = [page for page in list(plan_view.get("pages") or []) if isinstance(page, dict)]
    if not pages:
        return None, -1
    current_index = int(plan_view.get("current_index") or -1)
    current_page = next(
        (
            page
            for page in pages
            if int(page.get("page_index", -1) or -1) == current_index
        ),
        None,
    )
    if current_page is None:
        current_page = pages[0]
        current_index = int(current_page.get("page_index", 0) or 0)
    return current_page, current_index


def _build_learning_plan_active_object_scope(
    plan_view: dict[str, Any],
    *,
    object_type: str,
    page_index: int,
) -> dict[str, Any]:
    return {
        "domain": "guided_plan",
        "plan_id": str(plan_view.get("session_id") or "").strip(),
        "page_index": page_index if object_type == "guide_page" else -1,
        "notebook_id": str(plan_view.get("notebook_id") or "").strip(),
    }


def _build_learning_plan_state_snapshot(
    plan_view: dict[str, Any],
    *,
    current_page: dict[str, Any] | None,
    current_index: int,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "plan_id": str(plan_view.get("session_id") or "").strip(),
        "user_id": str(plan_view.get("user_id") or "").strip(),
        "status": str(plan_view.get("status") or "").strip(),
        "summary": str(plan_view.get("summary") or "").strip(),
        "progress": plan_view.get("progress"),
        "current_index": current_index,
        "page_count": int(plan_view.get("page_count") or 0),
        "ready_count": int(plan_view.get("ready_count") or 0),
        "notebook_id": str(plan_view.get("notebook_id") or "").strip(),
        "notebook_name": str(plan_view.get("notebook_name") or "").strip(),
    }
    if isinstance(current_page, dict):
        snapshot["current_page"] = {
            "page_index": current_index,
            "knowledge_title": str(current_page.get("knowledge_title") or "").strip(),
            "knowledge_summary": str(current_page.get("knowledge_summary") or "").strip(),
            "page_status": str(current_page.get("page_status") or "").strip(),
        }
    return snapshot


def build_active_object_from_learning_plan_view(
    plan_view: dict[str, Any] | None,
    *,
    previous_active_object: dict[str, Any] | None = None,
    object_type: Any = None,
    object_id: Any = None,
    scope: Any = None,
    version: Any = None,
    entered_at: Any = None,
    last_touched_at: Any = None,
    source_turn_id: Any = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    if not isinstance(plan_view, dict):
        return None
    plan_id = str(plan_view.get("session_id") or "").strip()
    if not plan_id:
        return None

    current_page, current_index = _resolve_learning_plan_current_page(plan_view)
    resolved_object_type = str(object_type or "").strip().lower()
    if resolved_object_type not in _LEARNING_ACTIVE_OBJECT_TYPES:
        resolved_object_type = "guide_page" if current_page is not None else "study_plan"
    resolved_object_id = str(object_id or "").strip()
    if not resolved_object_id:
        resolved_object_id = (
            f"{plan_id}:page:{current_index}"
            if resolved_object_type == "guide_page"
            else plan_id
        )

    resolved_now = float(now if now is not None else time.time())
    previous = previous_active_object if isinstance(previous_active_object, dict) else {}
    previous_object_type = str(previous.get("object_type") or "").strip()
    previous_object_id = str(previous.get("object_id") or "").strip()
    same_identity = (
        previous_object_type in _LEARNING_ACTIVE_OBJECT_TYPES
        and previous_object_type == resolved_object_type
        and previous_object_id == resolved_object_id
    )

    resolved_scope = scope if isinstance(scope, dict) else _build_learning_plan_active_object_scope(
        plan_view,
        object_type=resolved_object_type,
        page_index=current_index,
    )
    resolved_version = _coerce_positive_int(version)
    if resolved_version is None:
        previous_version = _coerce_positive_int(previous.get("version")) or 0
        resolved_version = previous_version + 1 if same_identity else 1

    resolved_entered_at = _coerce_timestamp(entered_at)
    if resolved_entered_at is None:
        resolved_entered_at = (
            _coerce_timestamp(previous.get("entered_at")) if same_identity else resolved_now
        )
    resolved_last_touched_at = _coerce_timestamp(last_touched_at) or resolved_now
    resolved_source_turn_id = str(source_turn_id or "").strip() or (
        str(previous.get("source_turn_id") or "").strip() if same_identity else ""
    )

    return {
        "object_type": resolved_object_type,
        "object_id": resolved_object_id,
        "scope": dict(resolved_scope),
        "state_snapshot": _build_learning_plan_state_snapshot(
            plan_view,
            current_page=current_page,
            current_index=current_index,
        ),
        "version": resolved_version,
        "entered_at": resolved_entered_at,
        "last_touched_at": resolved_last_touched_at,
        "source_turn_id": resolved_source_turn_id,
    }


def build_active_object_from_session(
    session_view: dict[str, Any] | None,
    *,
    previous_active_object: dict[str, Any] | None = None,
    object_type: Any = None,
    object_id: Any = None,
    scope: Any = None,
    version: Any = None,
    entered_at: Any = None,
    last_touched_at: Any = None,
    source_turn_id: Any = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    if not isinstance(session_view, dict):
        return None
    session_id = str(session_view.get("session_id") or session_view.get("id") or "").strip()
    if not session_id:
        return None

    resolved_now = float(now if now is not None else time.time())
    previous = previous_active_object if isinstance(previous_active_object, dict) else {}
    resolved_object_type = str(object_type or "").strip().lower()
    if resolved_object_type not in _SESSION_ACTIVE_OBJECT_TYPES:
        resolved_object_type = "open_chat_topic"
    resolved_object_id = str(object_id or "").strip() or session_id
    previous_object_type = str(previous.get("object_type") or "").strip()
    previous_object_id = str(previous.get("object_id") or "").strip()
    same_identity = (
        previous_object_type in _SESSION_ACTIVE_OBJECT_TYPES
        and previous_object_type == resolved_object_type
        and previous_object_id == resolved_object_id
    )

    resolved_scope = scope if isinstance(scope, dict) else {
        "domain": "session",
        "session_id": session_id,
        "source": str(session_view.get("source") or "").strip(),
    }
    resolved_version = _coerce_positive_int(version)
    if resolved_version is None:
        previous_version = _coerce_positive_int(previous.get("version")) or 0
        resolved_version = previous_version + 1 if same_identity else 1

    resolved_entered_at = _coerce_timestamp(entered_at)
    if resolved_entered_at is None:
        resolved_entered_at = (
            _coerce_timestamp(previous.get("entered_at")) if same_identity else resolved_now
        )
    resolved_last_touched_at = _coerce_timestamp(last_touched_at) or resolved_now
    resolved_source_turn_id = str(source_turn_id or "").strip() or (
        str(previous.get("source_turn_id") or "").strip() if same_identity else ""
    )
    state_snapshot = {
        "session_id": session_id,
        "title": str(session_view.get("title") or "").strip(),
        "compressed_summary": str(session_view.get("compressed_summary") or "").strip(),
        "source": str(session_view.get("source") or "").strip(),
        "status": str(session_view.get("status") or "").strip(),
    }

    return {
        "object_type": resolved_object_type,
        "object_id": resolved_object_id,
        "scope": dict(resolved_scope),
        "state_snapshot": state_snapshot,
        "version": resolved_version,
        "entered_at": resolved_entered_at,
        "last_touched_at": resolved_last_touched_at,
        "source_turn_id": resolved_source_turn_id,
    }


def build_active_object_from_question_context(
    question_context: dict[str, Any] | None,
    *,
    previous_active_object: dict[str, Any] | None = None,
    object_type: Any = None,
    object_id: Any = None,
    scope: Any = None,
    version: Any = None,
    entered_at: Any = None,
    last_touched_at: Any = None,
    source_turn_id: Any = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    normalized_question = normalize_question_followup_context(question_context)
    if normalized_question is None:
        return None

    resolved_now = float(now if now is not None else time.time())
    previous = previous_active_object if isinstance(previous_active_object, dict) else {}
    has_items = bool(normalized_question.get("items"))
    resolved_object_type = _normalize_question_active_object_type(object_type, has_items=has_items)
    resolved_object_id = str(object_id or "").strip() or _derive_question_active_object_id(
        normalized_question
    )
    previous_object_type = str(previous.get("object_type") or "").strip()
    previous_object_id = str(previous.get("object_id") or "").strip()
    same_identity = (
        previous_object_type in _QUESTION_ACTIVE_OBJECT_TYPES
        and previous_object_type == resolved_object_type
        and previous_object_id == resolved_object_id
    )

    resolved_scope = scope if isinstance(scope, dict) else _build_question_active_object_scope(
        normalized_question
    )
    resolved_version = _coerce_positive_int(version)
    if resolved_version is None:
        previous_version = _coerce_positive_int(previous.get("version")) or 0
        resolved_version = previous_version + 1 if same_identity else 1

    resolved_entered_at = _coerce_timestamp(entered_at)
    if resolved_entered_at is None:
        resolved_entered_at = (
            _coerce_timestamp(previous.get("entered_at")) if same_identity else resolved_now
        )
    resolved_last_touched_at = _coerce_timestamp(last_touched_at) or resolved_now
    resolved_source_turn_id = str(source_turn_id or "").strip() or (
        str(previous.get("source_turn_id") or "").strip() if same_identity else ""
    )

    return {
        "object_type": resolved_object_type,
        "object_id": resolved_object_id,
        "scope": dict(resolved_scope),
        "state_snapshot": dict(normalized_question),
        "version": resolved_version,
        "entered_at": resolved_entered_at,
        "last_touched_at": resolved_last_touched_at,
        "source_turn_id": resolved_source_turn_id,
    }


def extract_question_context_from_active_object(
    active_object: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(active_object, dict):
        return None
    snapshot = (
        active_object.get("state_snapshot")
        if isinstance(active_object.get("state_snapshot"), dict)
        else active_object.get("question_followup_context")
        if isinstance(active_object.get("question_followup_context"), dict)
        else None
    )
    if not isinstance(snapshot, dict):
        return None
    return normalize_question_followup_context(snapshot)


def normalize_active_object(
    raw: dict[str, Any] | None,
    *,
    previous_active_object: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    question_snapshot = (
        raw.get("state_snapshot")
        if isinstance(raw.get("state_snapshot"), dict)
        else raw
        if ("question" in raw or "items" in raw)
        else None
    )
    if isinstance(question_snapshot, dict) and normalize_question_followup_context(question_snapshot):
        return build_active_object_from_question_context(
            question_snapshot,
            previous_active_object=previous_active_object,
            object_type=raw.get("object_type"),
            object_id=raw.get("object_id"),
            scope=raw.get("scope"),
            version=raw.get("version"),
            entered_at=raw.get("entered_at"),
            last_touched_at=raw.get("last_touched_at"),
            source_turn_id=raw.get("source_turn_id"),
            now=now,
        )

    object_type = str(raw.get("object_type") or "").strip()
    object_id = str(raw.get("object_id") or "").strip()
    state_snapshot = raw.get("state_snapshot") if isinstance(raw.get("state_snapshot"), dict) else {}
    if not object_type or not object_id:
        return None

    resolved_now = float(now if now is not None else time.time())
    resolved_version = _coerce_positive_int(raw.get("version")) or 1
    resolved_entered_at = _coerce_timestamp(raw.get("entered_at")) or resolved_now
    resolved_last_touched_at = _coerce_timestamp(raw.get("last_touched_at")) or resolved_now
    resolved_scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
    return {
        "object_type": object_type,
        "object_id": object_id,
        "scope": dict(resolved_scope),
        "state_snapshot": dict(state_snapshot),
        "version": resolved_version,
        "entered_at": resolved_entered_at,
        "last_touched_at": resolved_last_touched_at,
        "source_turn_id": str(raw.get("source_turn_id") or "").strip(),
    }


def normalize_suspended_object_stack(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized_stack: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_active_object(item)
        if normalized is not None:
            normalized_stack.append(normalized)
    return normalized_stack


def build_user_owner_key(user_id: str | None) -> str:
    resolved = str(user_id or "").strip()
    return f"user:{resolved}" if resolved else ""


def _normalize_session_source(value: Any) -> str:
    return str(value or "").strip().lower()


def _derive_owner_key_from_preferences(preferences: dict[str, Any] | None) -> str:
    if not isinstance(preferences, dict):
        return ""
    explicit = str(preferences.get("owner_key") or "").strip()
    if explicit:
        return explicit
    return build_user_owner_key(preferences.get("user_id"))


def _derive_session_source(
    preferences: dict[str, Any] | None,
    current_source: str | None = "",
) -> str:
    if isinstance(preferences, dict) and "source" in preferences:
        return _normalize_session_source(preferences.get("source"))
    return _normalize_session_source(current_source)


def _derive_session_archived(
    preferences: dict[str, Any] | None,
    current_archived: Any = 0,
) -> int:
    if isinstance(preferences, dict) and "archived" in preferences:
        return 1 if bool(preferences.get("archived")) else 0
    return 1 if bool(current_archived) else 0


def _resolve_effective_owner_key(row_owner_key: str | None, session_owner_key: str | None) -> str:
    resolved = str(row_owner_key or "").strip()
    if resolved:
        return resolved
    return str(session_owner_key or "").strip()


def _materialize_session_preferences(
    preferences_json: str | None,
    source: str | None,
    archived: Any,
) -> dict[str, Any]:
    preferences = _json_loads(preferences_json, {})
    if not isinstance(preferences, dict):
        preferences = {}
    preferences.pop("runtime_state", None)
    normalized_source = _normalize_session_source(source)
    if normalized_source:
        preferences["source"] = normalized_source
    preferences["archived"] = bool(archived)
    return preferences


def _derive_session_conversation_id(
    preferences: dict[str, Any] | None,
    session_id: str | None,
) -> str:
    if isinstance(preferences, dict):
        explicit = str(preferences.get("conversation_id") or "").strip()
        if explicit:
            return explicit
    return str(session_id or "").strip()


def _is_interaction_hint_system_message(content: str | None) -> bool:
    text = str(content or "")
    return any(text.startswith(prefix) for prefix in _INTERACTION_HINT_SYSTEM_PREFIXES)


def _normalize_message_events_for_presentation(
    content: str | None,
    events: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], bool]:
    normalized_events: list[dict[str, Any]] = []
    changed = False
    rendered_content = str(content or "")

    for raw_event in events or []:
        if not isinstance(raw_event, dict):
            normalized_events.append(raw_event)
            continue
        event = dict(raw_event)
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else None
        if str(event.get("type") or "").strip() == "result" and metadata is not None:
            normalized_metadata = dict(metadata)
            presentation = normalized_metadata.get("presentation")
            # Legacy "summary" here is old result metadata for one message, not sessions.compressed_summary.
            legacy_result_summary = normalized_metadata.get("summary")
            if isinstance(presentation, dict):
                if "summary" in normalized_metadata:
                    normalized_metadata.pop("summary", None)
                    changed = True
            elif isinstance(legacy_result_summary, dict):
                presentation = build_canonical_presentation(
                    content=rendered_content,
                    result_summary=legacy_result_summary,
                )
                if presentation:
                    normalized_metadata["presentation"] = presentation
                normalized_metadata.pop("summary", None)
                changed = True
            if normalized_metadata != metadata:
                event["metadata"] = normalized_metadata
        normalized_events.append(event)
    return normalized_events, changed


def _empty_cost_summary(*, session_id: str = "", scope_id: str = "") -> dict[str, Any]:
    resolved_session_id = str(session_id or "").strip()
    return {
        "scope_id": str(scope_id or f"session:{resolved_session_id}" if resolved_session_id else "session").strip(),
        "session_id": resolved_session_id,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_calls": 0,
        "measured_calls": 0,
        "estimated_calls": 0,
        "usage_accuracy": "unknown",
        "usage_sources": {},
        "models": {},
        "total_cost_usd": 0.0,
    }


def _normalize_cost_summary(summary: dict[str, Any] | None, *, session_id: str = "") -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None

    normalized = _empty_cost_summary(
        session_id=session_id or str(summary.get("session_id") or "").strip(),
        scope_id=str(summary.get("scope_id") or "").strip(),
    )
    normalized["total_input_tokens"] = int(round(float(summary.get("total_input_tokens") or 0)))
    normalized["total_output_tokens"] = int(round(float(summary.get("total_output_tokens") or 0)))
    normalized["total_tokens"] = int(
        round(
            float(
                summary.get("total_tokens")
                or (normalized["total_input_tokens"] + normalized["total_output_tokens"])
            )
        )
    )
    normalized["total_calls"] = int(round(float(summary.get("total_calls") or 0)))
    normalized["measured_calls"] = int(round(float(summary.get("measured_calls") or 0)))
    normalized["estimated_calls"] = int(round(float(summary.get("estimated_calls") or 0)))
    normalized["total_cost_usd"] = round(float(summary.get("total_cost_usd") or 0.0), 8)

    raw_sources = summary.get("usage_sources") if isinstance(summary.get("usage_sources"), dict) else {}
    normalized["usage_sources"] = {
        str(key): int(round(float(value or 0)))
        for key, value in raw_sources.items()
        if int(round(float(value or 0))) > 0
    }
    raw_models = summary.get("models") if isinstance(summary.get("models"), dict) else {}
    normalized["models"] = {
        str(key): int(round(float(value or 0)))
        for key, value in raw_models.items()
        if int(round(float(value or 0))) > 0
    }
    return normalized


def _merge_cost_summary(target: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_cost_summary(incoming, session_id=str(target.get("session_id") or "").strip())
    if normalized is None:
        return target

    target["total_input_tokens"] = int(target.get("total_input_tokens") or 0) + int(
        normalized["total_input_tokens"]
    )
    target["total_output_tokens"] = int(target.get("total_output_tokens") or 0) + int(
        normalized["total_output_tokens"]
    )
    target["total_tokens"] = int(target.get("total_tokens") or 0) + int(normalized["total_tokens"])
    target["total_calls"] = int(target.get("total_calls") or 0) + int(normalized["total_calls"])
    target["measured_calls"] = int(target.get("measured_calls") or 0) + int(
        normalized["measured_calls"]
    )
    target["estimated_calls"] = int(target.get("estimated_calls") or 0) + int(
        normalized["estimated_calls"]
    )
    target["total_cost_usd"] = round(
        float(target.get("total_cost_usd") or 0.0) + float(normalized["total_cost_usd"] or 0.0),
        8,
    )

    sources = target.setdefault("usage_sources", {})
    for key, value in normalized.get("usage_sources", {}).items():
        sources[key] = int(sources.get(key) or 0) + int(value or 0)

    models = target.setdefault("models", {})
    for key, value in normalized.get("models", {}).items():
        models[key] = int(models.get(key) or 0) + int(value or 0)

    return target


def _finalize_cost_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not summary:
        return None

    total_tokens = int(summary.get("total_tokens") or 0)
    total_calls = int(summary.get("total_calls") or 0)
    if total_tokens <= 0 and total_calls <= 0:
        return None

    measured_calls = int(summary.get("measured_calls") or 0)
    estimated_calls = int(summary.get("estimated_calls") or 0)
    accuracy = (
        "measured"
        if estimated_calls == 0 and measured_calls > 0
        else "estimated"
        if measured_calls == 0 and estimated_calls > 0
        else "mixed"
        if measured_calls > 0 and estimated_calls > 0
        else "unknown"
    )

    return {
        "scope_id": str(summary.get("scope_id") or "").strip(),
        "session_id": str(summary.get("session_id") or "").strip(),
        "total_input_tokens": int(summary.get("total_input_tokens") or 0),
        "total_output_tokens": int(summary.get("total_output_tokens") or 0),
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "measured_calls": measured_calls,
        "estimated_calls": estimated_calls,
        "usage_accuracy": accuracy,
        "usage_sources": {
            key: value
            for key, value in sorted((summary.get("usage_sources") or {}).items(), key=lambda item: item[0])
            if int(value or 0) > 0
        },
        "models": {
            key: value
            for key, value in sorted((summary.get("models") or {}).items(), key=lambda item: item[0])
            if int(value or 0) > 0
        },
        "total_cost_usd": round(float(summary.get("total_cost_usd") or 0.0), 8),
    }


@dataclass
class TurnRecord:
    id: str
    session_id: str
    capability: str
    status: str
    error: str
    created_at: float
    updated_at: float
    finished_at: float | None
    last_seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "turn_id": self.id,
            "session_id": self.session_id,
            "capability": self.capability,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "last_seq": self.last_seq,
        }


class SQLiteSessionStore:
    """Persist unified chat sessions and messages in a SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        path_service = get_path_service()
        self.db_path = db_path or path_service.get_chat_history_db()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_db(path_service)
        self._lock = asyncio.Lock()
        self._initialize()

    def _migrate_legacy_db(self, path_service) -> None:
        """Move the legacy ``data/chat_history.db`` into ``data/user/`` once."""
        legacy_path = path_service.project_root / "data" / "chat_history.db"
        if self.db_path.exists() or not legacy_path.exists() or legacy_path == self.db_path:
            return
        try:
            os.replace(legacy_path, self.db_path)
        except OSError:
            # Keep reading and writing the legacy DB instead of silently
            # booting against a fresh empty database.
            self.db_path = legacy_path

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path, timeout=_SQLITE_TIMEOUT_SECONDS) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New conversation',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    compressed_summary TEXT DEFAULT '',
                    summary_up_to_msg_id INTEGER DEFAULT 0,
                    preferences_json TEXT DEFAULT '{}',
                    source TEXT DEFAULT '',
                    archived INTEGER DEFAULT 0,
                    owner_key TEXT DEFAULT '',
                    conversation_id TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    capability TEXT DEFAULT '',
                    events_json TEXT DEFAULT '',
                    attachments_json TEXT DEFAULT '',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON messages(session_id, created_at, id);

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                    ON sessions(updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at_id
                    ON sessions(updated_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    capability TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'running',
                    error TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    finished_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_turns_session_updated
                    ON turns(session_id, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_turns_session_updated_id
                    ON turns(session_id, updated_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_turns_session_status
                    ON turns(session_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS turn_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    stage TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '',
                    timestamp REAL NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(turn_id, seq)
                );

                CREATE INDEX IF NOT EXISTS idx_turn_events_turn_seq
                    ON turn_events(turn_id, seq);

                CREATE TABLE IF NOT EXISTS notebook_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    owner_key TEXT DEFAULT '',
                    question_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_type TEXT DEFAULT '',
                    options_json TEXT DEFAULT '{}',
                    correct_answer TEXT DEFAULT '',
                    explanation TEXT DEFAULT '',
                    difficulty TEXT DEFAULT '',
                    user_answer TEXT DEFAULT '',
                    is_correct INTEGER DEFAULT 0,
                    bookmarked INTEGER DEFAULT 0,
                    followup_session_id TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(session_id, question_id)
                );

                CREATE INDEX IF NOT EXISTS idx_notebook_entries_session
                    ON notebook_entries(session_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_notebook_entries_created_id
                    ON notebook_entries(created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_notebook_entries_bookmarked
                    ON notebook_entries(bookmarked, created_at DESC);

                CREATE TABLE IF NOT EXISTS notebook_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_key TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(owner_key, name)
                );

                CREATE TABLE IF NOT EXISTS notebook_entry_categories (
                    entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
                    category_id INTEGER NOT NULL REFERENCES notebook_categories(id) ON DELETE CASCADE,
                    PRIMARY KEY (entry_id, category_id)
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
            if "preferences_json" not in columns:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN preferences_json TEXT DEFAULT '{}'"
                )
            if "source" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN source TEXT DEFAULT ''")
            if "archived" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN archived INTEGER DEFAULT 0")
            if "owner_key" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN owner_key TEXT DEFAULT ''")
            if "conversation_id" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN conversation_id TEXT DEFAULT ''")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_updated_at
                    ON sessions(owner_key, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_updated_at_id
                    ON sessions(owner_key, updated_at DESC, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_source_archived_updated
                    ON sessions(owner_key, source, archived, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_source_archived_updated_id
                    ON sessions(owner_key, source, archived, updated_at DESC, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_source_conversation_updated
                    ON sessions(owner_key, source, conversation_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_owner_source_conversation_updated_id
                    ON sessions(owner_key, source, conversation_id, updated_at DESC, id DESC)
                """
            )
            rows = conn.execute(
                """
                SELECT id, owner_key, source, archived, preferences_json, conversation_id
                FROM sessions
                """
            ).fetchall()
            for row in rows:
                preferences = _json_loads(row["preferences_json"], {})
                derived_owner_key = str(row["owner_key"] or "").strip() or _derive_owner_key_from_preferences(
                    preferences
                )
                derived_source = _derive_session_source(preferences, row["source"])
                derived_archived = _derive_session_archived(preferences, row["archived"])
                derived_conversation_id = (
                    str(row["conversation_id"] or "").strip()
                    or _derive_session_conversation_id(preferences, row["id"])
                )
                conn.execute(
                    """
                    UPDATE sessions
                    SET owner_key = ?, source = ?, archived = ?, conversation_id = ?
                    WHERE id = ?
                    """,
                    (
                        derived_owner_key,
                        derived_source,
                        derived_archived,
                        derived_conversation_id,
                        row["id"],
                    ),
                )

            notebook_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)").fetchall()
            }
            if "owner_key" not in notebook_columns:
                conn.execute("ALTER TABLE notebook_entries ADD COLUMN owner_key TEXT DEFAULT ''")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notebook_entries_owner
                    ON notebook_entries(owner_key, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notebook_entries_owner_created_id
                    ON notebook_entries(owner_key, created_at DESC, id DESC)
                """
            )
            notebook_rows = conn.execute(
                """
                SELECT n.id, n.owner_key, s.owner_key AS session_owner_key
                FROM notebook_entries n
                LEFT JOIN sessions s ON s.id = n.session_id
                WHERE COALESCE(n.owner_key, '') = ''
                """
            ).fetchall()
            for row in notebook_rows:
                derived_owner_key = _resolve_effective_owner_key(
                    row["owner_key"],
                    row["session_owner_key"],
                )
                if not derived_owner_key:
                    continue
                conn.execute(
                    "UPDATE notebook_entries SET owner_key = ? WHERE id = ?",
                    (derived_owner_key, row["id"]),
                )

            category_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(notebook_categories)").fetchall()
            }
            if "owner_key" not in category_columns:
                conn.execute("ALTER TABLE notebook_categories ADD COLUMN owner_key TEXT DEFAULT ''")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notebook_categories_owner_name
                    ON notebook_categories(owner_key, name)
                """
            )
            category_rows = conn.execute(
                """
                SELECT c.id
                FROM notebook_categories c
                WHERE COALESCE(c.owner_key, '') = ''
                """
            ).fetchall()
            for row in category_rows:
                derived_owner_key_row = conn.execute(
                    """
                    SELECT COALESCE(NULLIF(n.owner_key, ''), s.owner_key, '') AS owner_key
                    FROM notebook_entry_categories ec
                    INNER JOIN notebook_entries n ON n.id = ec.entry_id
                    LEFT JOIN sessions s ON s.id = n.session_id
                    WHERE ec.category_id = ?
                      AND COALESCE(NULLIF(n.owner_key, ''), s.owner_key, '') != ''
                    ORDER BY ec.entry_id ASC
                    LIMIT 1
                    """,
                    (row["id"],),
                ).fetchone()
                derived_owner_key = (
                    str(derived_owner_key_row["owner_key"] or "").strip()
                    if derived_owner_key_row is not None
                    else ""
                )
                if not derived_owner_key:
                    continue
                conn.execute(
                    "UPDATE notebook_categories SET owner_key = ? WHERE id = ?",
                    (derived_owner_key, row["id"]),
                )
            if self._notebook_categories_require_owner_scope_migration(conn):
                self._migrate_notebook_categories_owner_scope(conn)
            self._prune_notebook_entry_category_owner_mismatches(conn)
            conn.commit()

    async def _run(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    @staticmethod
    def _notebook_categories_require_owner_scope_migration(conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'notebook_categories'
            """
        ).fetchone()
        table_sql = str(row["sql"] or "").lower() if row is not None else ""
        if "unique(owner_key, name)" in table_sql:
            return False

        indexes = conn.execute("PRAGMA index_list(notebook_categories)").fetchall()
        has_owner_scoped_unique = False
        has_name_only_unique = False
        for index_row in indexes:
            if not int(index_row["unique"]):
                continue
            columns = [
                str(info_row["name"] or "")
                for info_row in conn.execute(
                    f"PRAGMA index_info({index_row['name']})"
                ).fetchall()
            ]
            if columns == ["owner_key", "name"]:
                has_owner_scoped_unique = True
            elif columns == ["name"]:
                has_name_only_unique = True

        return not has_owner_scoped_unique and has_name_only_unique

    @staticmethod
    def _migrate_notebook_categories_owner_scope(conn: sqlite3.Connection) -> None:
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                """
                CREATE TABLE notebook_categories_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_key TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(owner_key, name)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO notebook_categories_new (id, name, owner_key, created_at)
                SELECT id, name, COALESCE(owner_key, ''), created_at
                FROM notebook_categories
                """
            )
            conn.execute("DROP TABLE notebook_categories")
            conn.execute("ALTER TABLE notebook_categories_new RENAME TO notebook_categories")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notebook_categories_owner_name
                    ON notebook_categories(owner_key, name)
                """
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _prune_notebook_entry_category_owner_mismatches(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM notebook_entry_categories
            WHERE (entry_id, category_id) IN (
                SELECT
                    ec.entry_id,
                    ec.category_id
                FROM notebook_entry_categories ec
                INNER JOIN notebook_categories c ON c.id = ec.category_id
                INNER JOIN notebook_entries n ON n.id = ec.entry_id
                LEFT JOIN sessions s ON s.id = n.session_id
                WHERE COALESCE(NULLIF(n.owner_key, ''), s.owner_key, '') != COALESCE(c.owner_key, '')
            )
            """
        )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=_SQLITE_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
        return conn

    @staticmethod
    def _extract_cost_summary_from_event_metadata(metadata_json: str | None) -> dict[str, Any] | None:
        metadata = _json_loads(metadata_json, {})
        if not isinstance(metadata, dict):
            return None

        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict) and isinstance(nested_metadata.get("cost_summary"), dict):
            return nested_metadata.get("cost_summary")
        if isinstance(metadata.get("cost_summary"), dict):
            return metadata.get("cost_summary")
        return None

    def _get_usage_summaries_for_sessions_sync(
        self,
        session_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        resolved_session_ids = [str(session_id or "").strip() for session_id in session_ids if str(session_id or "").strip()]
        if not resolved_session_ids:
            return {}

        placeholders = ",".join("?" for _ in resolved_session_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    t.session_id,
                    te.turn_id,
                    te.seq,
                    te.metadata_json
                FROM turn_events te
                INNER JOIN turns t ON t.id = te.turn_id
                WHERE t.session_id IN ({placeholders})
                  AND te.type = 'result'
                ORDER BY t.session_id ASC, te.turn_id ASC, te.seq DESC
                """,
                tuple(resolved_session_ids),
            ).fetchall()

        summaries: dict[str, dict[str, Any]] = {
            session_id: _empty_cost_summary(session_id=session_id)
            for session_id in resolved_session_ids
        }
        seen_turn_ids: set[tuple[str, str]] = set()
        for row in rows:
            session_id = str(row["session_id"] or "").strip()
            turn_id = str(row["turn_id"] or "").strip()
            if not session_id or not turn_id:
                continue
            key = (session_id, turn_id)
            if key in seen_turn_ids:
                continue
            seen_turn_ids.add(key)
            cost_summary = self._extract_cost_summary_from_event_metadata(row["metadata_json"])
            if cost_summary:
                _merge_cost_summary(summaries[session_id], cost_summary)

        return {
            session_id: finalized
            for session_id, summary in summaries.items()
            if (finalized := _finalize_cost_summary(summary)) is not None
        }

    def _get_usage_summary_for_session_sync(self, session_id: str) -> dict[str, Any] | None:
        return self._get_usage_summaries_for_sessions_sync([session_id]).get(session_id)

    def _create_session_sync(
        self,
        title: str | None = None,
        session_id: str | None = None,
        owner_key: str | None = None,
        source: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        resolved_id = session_id or f"unified_{int(now * 1000)}_{uuid.uuid4().hex[:8]}"
        resolved_title = (title or "New conversation").strip() or "New conversation"
        resolved_owner_key = str(owner_key or "").strip()
        resolved_source = _normalize_session_source(source)
        resolved_archived = 1 if bool(archived) else 0
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    created_at,
                    updated_at,
                    compressed_summary,
                    summary_up_to_msg_id,
                    source,
                    archived,
                    owner_key,
                    conversation_id
                )
                VALUES (?, ?, ?, ?, '', 0, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    resolved_title[:100],
                    now,
                    now,
                    resolved_source,
                    resolved_archived,
                    resolved_owner_key,
                    resolved_id,
                ),
            )
            conn.commit()
        return {
            "id": resolved_id,
            "session_id": resolved_id,
            "title": resolved_title[:100],
            "created_at": now,
            "updated_at": now,
            "compressed_summary": "",
            "summary_up_to_msg_id": 0,
            "source": resolved_source,
            "archived": bool(resolved_archived),
            "owner_key": resolved_owner_key,
        }

    async def create_session(
        self,
        title: str | None = None,
        session_id: str | None = None,
        owner_key: str | None = None,
        source: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        return await self._run(self._create_session_sync, title, session_id, owner_key, source, archived)

    def _get_session_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.compressed_summary,
                    s.summary_up_to_msg_id,
                    s.preferences_json,
                    s.source,
                    s.archived,
                    s.owner_key,
                    COALESCE(
                        (
                            SELECT t.status
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        'idle'
                    ) AS status,
                    COALESCE(
                        (
                            SELECT t.id
                            FROM turns t
                            WHERE t.session_id = s.id AND t.status = 'running'
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS active_turn_id,
                    COALESCE(
                        (
                            SELECT t.capability
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS capability
                FROM sessions
                s
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["session_id"] = payload["id"]
        payload["preferences"] = _materialize_session_preferences(
            payload.pop("preferences_json", ""),
            payload.pop("source", ""),
            payload.pop("archived", 0),
        )
        payload.pop("owner_key", None)
        payload["cost_summary"] = self._get_usage_summary_for_session_sync(payload["id"])
        return payload

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_session_sync, session_id)

    async def ensure_session(
        self,
        session_id: str | None = None,
        owner_key: str | None = None,
        source: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        if session_id:
            session = await self.get_session(session_id)
            if session is not None:
                return session
        return await self.create_session(
            session_id=session_id,
            owner_key=owner_key,
            source=source,
            archived=archived,
        )

    @staticmethod
    def _serialize_turn(row: sqlite3.Row) -> dict[str, Any]:
        return TurnRecord(
            id=row["id"],
            session_id=row["session_id"],
            capability=row["capability"] or "",
            status=row["status"] or "running",
            error=row["error"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
            last_seq=row["last_seq"] if "last_seq" in row.keys() else 0,
        ).to_dict()

    def _create_turn_sync(self, session_id: str, capability: str = "") -> dict[str, Any]:
        now = time.time()
        turn_id = f"turn_{int(now * 1000)}_{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            session = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            stale_cutoff = now - _STALE_TURN_TIMEOUT_SECONDS
            conn.execute(
                """
                UPDATE turns
                SET status = 'failed',
                    error = CASE
                        WHEN error = '' THEN 'Recovered stale running turn'
                        ELSE error
                    END,
                    updated_at = ?,
                    finished_at = ?
                WHERE session_id = ?
                  AND status = 'running'
                  AND updated_at < ?
                """,
                (now, now, session_id, stale_cutoff),
            )
            active = conn.execute(
                """
                SELECT id
                FROM turns
                WHERE session_id = ? AND status = 'running'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if active is not None:
                raise RuntimeError(f"Session already has an active turn: {active['id']}")
            conn.execute(
                """
                INSERT INTO turns (id, session_id, capability, status, error, created_at, updated_at, finished_at)
                VALUES (?, ?, ?, 'running', '', ?, ?, NULL)
                """,
                (turn_id, session_id, capability or "", now, now),
            )
            conn.commit()
        return {
            "id": turn_id,
            "turn_id": turn_id,
            "session_id": session_id,
            "capability": capability or "",
            "status": "running",
            "error": "",
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "last_seq": 0,
        }

    async def create_turn(self, session_id: str, capability: str = "") -> dict[str, Any]:
        return await self._run(self._create_turn_sync, session_id, capability)

    def _get_turn_sync(self, turn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    t.*,
                    COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
                FROM turns t
                WHERE t.id = ?
                """,
                (turn_id,),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_turn(row)

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_turn_sync, turn_id)

    def _get_active_turn_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    t.*,
                    COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
                FROM turns t
                WHERE t.session_id = ? AND t.status = 'running'
                ORDER BY t.updated_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_turn(row)

    async def get_active_turn(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_active_turn_sync, session_id)

    def _list_active_turns_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.*,
                    COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
                FROM turns t
                WHERE t.session_id = ? AND t.status = 'running'
                ORDER BY t.updated_at DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._serialize_turn(row) for row in rows]

    async def list_active_turns(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._list_active_turns_sync, session_id)

    def _update_turn_status_sync(self, turn_id: str, status: str, error: str = "") -> bool:
        now = time.time()
        finished_at = now if status in {"completed", "failed", "cancelled"} else None
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE turns
                SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, error or "", now, finished_at, turn_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_turn_status(self, turn_id: str, status: str, error: str = "") -> bool:
        return await self._run(self._update_turn_status_sync, turn_id, status, error)

    def _append_turn_event_sync(self, turn_id: str, event: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            turn = conn.execute("SELECT id, session_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
            if turn is None:
                raise ValueError(f"Turn not found: {turn_id}")
            provided_seq = int(event.get("seq") or 0)
            if provided_seq > 0:
                seq = provided_seq
            else:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS last_seq FROM turn_events WHERE turn_id = ?",
                    (turn_id,),
                ).fetchone()
                seq = int(row["last_seq"]) + 1 if row else 1
            payload = dict(event)
            payload["seq"] = seq
            payload["turn_id"] = payload.get("turn_id") or turn_id
            payload["session_id"] = payload.get("session_id") or turn["session_id"]
            conn.execute(
                """
                INSERT OR REPLACE INTO turn_events (
                    turn_id, seq, type, source, stage, content, metadata_json, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    seq,
                    payload.get("type", ""),
                    payload.get("source", ""),
                    payload.get("stage", ""),
                    payload.get("content", "") or "",
                    _json_dumps(payload.get("metadata", {})),
                    float(payload.get("timestamp") or now),
                    now,
                ),
            )
            conn.execute(
                "UPDATE turns SET updated_at = ? WHERE id = ?",
                (now, turn_id),
            )
            conn.commit()
        return payload

    async def append_turn_event(self, turn_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return await self._run(self._append_turn_event_sync, turn_id, event)

    def _get_turn_events_sync(self, turn_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT turn_id, seq, type, source, stage, content, metadata_json, timestamp
                FROM turn_events
                WHERE turn_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (turn_id, max(0, int(after_seq))),
            ).fetchall()
            turn = conn.execute("SELECT session_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        session_id = turn["session_id"] if turn else ""
        return [
            {
                "type": row["type"],
                "source": row["source"] or "",
                "stage": row["stage"] or "",
                "content": row["content"] or "",
                "metadata": _json_loads(row["metadata_json"], {}),
                "session_id": session_id,
                "turn_id": row["turn_id"],
                "seq": row["seq"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    async def get_turn_events(self, turn_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return await self._run(self._get_turn_events_sync, turn_id, after_seq)

    def _update_session_title_sync(self, session_id: str, title: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                ((title.strip() or "New conversation")[:100], time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_session_title(self, session_id: str, title: str) -> bool:
        return await self._run(self._update_session_title_sync, session_id, title)

    def _delete_session_sync(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return cur.rowcount > 0

    async def delete_session(self, session_id: str) -> bool:
        return await self._run(self._delete_session_sync, session_id)

    def _add_message_sync(
        self,
        session_id: str,
        role: str,
        content: str,
        capability: str = "",
        events: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> int:
        now = time.time()
        with self._connect() as conn:
            session = conn.execute("SELECT id, title FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                raise ValueError(f"Session not found: {session_id}")

            cur = conn.execute(
                """
                INSERT INTO messages (
                    session_id, role, content, capability, events_json, attachments_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content or "",
                    capability or "",
                    _json_dumps(events or []),
                    _json_dumps(attachments or []),
                    now,
                ),
            )

            title = None
            session_title = str(session["title"] or "").strip().lower()
            if session_title in _SESSION_TITLE_PLACEHOLDERS and role == "user":
                trimmed = (content or "").strip()
                if trimmed:
                    title = trimmed[:50] + ("..." if len(trimmed) > 50 else "")

            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            if title:
                conn.execute(
                    "UPDATE sessions SET title = ? WHERE id = ?",
                    (title, session_id),
                )
            conn.commit()
            return int(cur.lastrowid)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        capability: str = "",
        events: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> int:
        return await self._run(
            self._add_message_sync,
            session_id,
            role,
            content,
            capability,
            events,
            attachments,
        )

    def _serialize_message(self, row: sqlite3.Row) -> dict[str, Any]:
        events = _json_loads(row["events_json"], [])
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "capability": row["capability"] or "",
            "events": events,
            "attachments": _json_loads(row["attachments_json"], []),
            "created_at": row["created_at"],
        }

    def _get_messages_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, capability, events_json, attachments_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._serialize_message(row) for row in rows]

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._get_messages_sync, session_id)

    def _backfill_message_presentations_sync(
        self,
        session_id: str | None = None,
    ) -> dict[str, int]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT id, content, events_json
                    FROM messages
                    WHERE session_id = ? AND role = 'assistant'
                    ORDER BY id ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, content, events_json
                    FROM messages
                    WHERE role = 'assistant'
                    ORDER BY id ASC
                    """
                ).fetchall()

            scanned = 0
            updated = 0
            for row in rows:
                scanned += 1
                events = _json_loads(row["events_json"], [])
                if not isinstance(events, list):
                    continue
                normalized_events, changed = _normalize_message_events_for_presentation(
                    row["content"],
                    events,
                )
                if not changed:
                    continue
                conn.execute(
                    "UPDATE messages SET events_json = ? WHERE id = ?",
                    (_json_dumps(normalized_events), row["id"]),
                )
                updated += 1
            if updated:
                conn.commit()
        return {"scanned": scanned, "updated": updated}

    async def backfill_message_presentations(
        self,
        session_id: str | None = None,
    ) -> dict[str, int]:
        return await self._run(self._backfill_message_presentations_sync, session_id)

    def _get_messages_for_context_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE session_id = ?
                  AND role IN ('user', 'assistant', 'system')
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            role = row["role"]
            content = row["content"] or ""
            if role == "system" and _is_interaction_hint_system_message(content):
                continue
            messages.append({"id": row["id"], "role": role, "content": content})
        return messages

    async def get_messages_for_context(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._get_messages_for_context_sync, session_id)

    def _serialize_session_rows(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        sessions = []
        usage_summaries = self._get_usage_summaries_for_sessions_sync([str(row["id"]) for row in rows])
        for row in rows:
            payload = dict(row)
            payload["session_id"] = payload["id"]
            payload["preferences"] = _materialize_session_preferences(
                payload.pop("preferences_json", ""),
                payload.pop("source", ""),
                payload.pop("archived", 0),
            )
            payload.pop("owner_key", None)
            payload["cost_summary"] = usage_summaries.get(payload["id"])
            sessions.append(payload)
        return sessions

    def _query_session_page_sync(
        self,
        *,
        conditions: list[str] | None = None,
        params: list[Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query_conditions = list(conditions or [])
        query_params = list(params or [])
        effective_limit = max(int(limit), 1)
        effective_offset = max(int(offset), 0)
        if before_updated_at is not None:
            cursor_session_id = str(before_session_id or "").strip() or "\uffff"
            query_conditions.append("(s.updated_at < ? OR (s.updated_at = ? AND s.id < ?))")
            query_params.extend([float(before_updated_at), float(before_updated_at), cursor_session_id])
            effective_offset = 0
        where_clause = f"WHERE {' AND '.join(query_conditions)}" if query_conditions else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                WITH filtered_sessions AS (
                    SELECT
                        s.id,
                        s.title,
                        s.created_at,
                        s.updated_at,
                        s.compressed_summary,
                        s.summary_up_to_msg_id,
                        s.preferences_json,
                        s.source,
                        s.archived,
                        s.owner_key
                    FROM sessions s
                    {where_clause}
                    ORDER BY s.updated_at DESC, s.id DESC
                    LIMIT ? OFFSET ?
                ),
                message_counts AS (
                    SELECT
                        m.session_id,
                        COUNT(*) AS message_count
                    FROM messages m
                    WHERE m.session_id IN (SELECT id FROM filtered_sessions)
                    GROUP BY m.session_id
                ),
                latest_turn AS (
                    SELECT session_id, status, capability
                    FROM (
                        SELECT
                            t.session_id,
                            t.status,
                            t.capability,
                            ROW_NUMBER() OVER (
                                PARTITION BY t.session_id
                                ORDER BY t.updated_at DESC, t.id DESC
                            ) AS rn
                        FROM turns t
                        WHERE t.session_id IN (SELECT id FROM filtered_sessions)
                    )
                    WHERE rn = 1
                ),
                running_turn AS (
                    SELECT session_id, id
                    FROM (
                        SELECT
                            t.session_id,
                            t.id,
                            ROW_NUMBER() OVER (
                                PARTITION BY t.session_id
                                ORDER BY t.updated_at DESC, t.id DESC
                            ) AS rn
                        FROM turns t
                        WHERE t.session_id IN (SELECT id FROM filtered_sessions)
                          AND t.status = 'running'
                    )
                    WHERE rn = 1
                ),
                last_message AS (
                    SELECT session_id, content
                    FROM (
                        SELECT
                            m2.session_id,
                            m2.content,
                            ROW_NUMBER() OVER (
                                PARTITION BY m2.session_id
                                ORDER BY m2.id DESC
                            ) AS rn
                        FROM messages m2
                        WHERE m2.session_id IN (SELECT id FROM filtered_sessions)
                          AND TRIM(COALESCE(m2.content, '')) != ''
                    )
                    WHERE rn = 1
                )
                SELECT
                    fs.id,
                    fs.title,
                    fs.created_at,
                    fs.updated_at,
                    fs.compressed_summary,
                    fs.summary_up_to_msg_id,
                    fs.preferences_json,
                    fs.source,
                    fs.archived,
                    fs.owner_key,
                    COALESCE(mc.message_count, 0) AS message_count,
                    COALESCE(lt.status, 'idle') AS status,
                    COALESCE(rt.id, '') AS active_turn_id,
                    COALESCE(lt.capability, '') AS capability,
                    COALESCE(lm.content, '') AS last_message
                FROM filtered_sessions fs
                LEFT JOIN message_counts mc ON mc.session_id = fs.id
                LEFT JOIN latest_turn lt ON lt.session_id = fs.id
                LEFT JOIN running_turn rt ON rt.session_id = fs.id
                LEFT JOIN last_message lm ON lm.session_id = fs.id
                ORDER BY fs.updated_at DESC, fs.id DESC
                """,
                tuple(query_params) + (effective_limit, effective_offset),
            ).fetchall()
        return self._serialize_session_rows(rows)

    def _list_sessions_sync(
        self,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._query_session_page_sync(
            limit=limit,
            offset=offset,
            before_updated_at=before_updated_at,
            before_session_id=before_session_id,
        )

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._run(
            self._list_sessions_sync,
            limit,
            offset,
            before_updated_at,
            before_session_id,
        )

    def _list_sessions_by_owner_sync(
        self,
        owner_key: str,
        source: str | None = None,
        archived: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["s.owner_key = ?"]
        params: list[Any] = [owner_key]
        if source is not None:
            conditions.append("s.source = ?")
            params.append(_normalize_session_source(source))
        if archived is not None:
            conditions.append("s.archived = ?")
            params.append(1 if bool(archived) else 0)
        return self._query_session_page_sync(
            conditions=conditions,
            params=params,
            limit=limit,
            offset=offset,
            before_updated_at=before_updated_at,
            before_session_id=before_session_id,
        )

    async def list_sessions_by_owner(
        self,
        owner_key: str,
        source: str | None = None,
        archived: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._run(
            self._list_sessions_by_owner_sync,
            owner_key,
            source,
            archived,
            limit,
            offset,
            before_updated_at,
            before_session_id,
        )

    def _list_sessions_by_owner_and_conversation_sync(
        self,
        owner_key: str,
        conversation_id: str,
        source: str | None = None,
        archived: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_conversation_id = str(conversation_id or "").strip()
        if not normalized_conversation_id:
            return []
        conditions = ["s.owner_key = ?", "s.conversation_id = ?"]
        params: list[Any] = [owner_key, normalized_conversation_id]
        if source is not None:
            conditions.append("s.source = ?")
            params.append(_normalize_session_source(source))
        if archived is not None:
            conditions.append("s.archived = ?")
            params.append(1 if bool(archived) else 0)
        return self._query_session_page_sync(
            conditions=conditions,
            params=params,
            limit=limit,
            offset=0,
        )

    async def list_sessions_by_owner_and_conversation(
        self,
        owner_key: str,
        conversation_id: str,
        source: str | None = None,
        archived: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._run(
            self._list_sessions_by_owner_and_conversation_sync,
            owner_key,
            conversation_id,
            source,
            archived,
            limit,
        )

    def _get_session_owner_key_sync(self, session_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_key, preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return ""
        owner_key = str(row["owner_key"] or "").strip()
        if owner_key:
            return owner_key
        return _derive_owner_key_from_preferences(_json_loads(row["preferences_json"], {}))

    async def get_session_owner_key(self, session_id: str) -> str:
        return await self._run(self._get_session_owner_key_sync, session_id)

    def _update_summary_sync(self, session_id: str, summary: str, up_to_msg_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET compressed_summary = ?, summary_up_to_msg_id = ?, updated_at = updated_at
                WHERE id = ?
                """,
                (summary, max(0, int(up_to_msg_id)), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_summary(self, session_id: str, summary: str, up_to_msg_id: int) -> bool:
        return await self._run(self._update_summary_sync, session_id, summary, up_to_msg_id)

    def _update_session_preferences_sync(self, session_id: str, preferences: dict[str, Any]) -> bool:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT preferences_json, owner_key, source, archived FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                return False
            merged = {
                **_json_loads(current["preferences_json"], {}),
                **(preferences or {}),
            }
            owner_key = _derive_owner_key_from_preferences(merged) or str(current["owner_key"] or "").strip()
            source = _derive_session_source(merged, current["source"])
            archived = _derive_session_archived(merged, current["archived"])
            conversation_id = _derive_session_conversation_id(merged, session_id)
            cur = conn.execute(
                """
                UPDATE sessions
                SET preferences_json = ?, source = ?, archived = ?, owner_key = ?, conversation_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json_dumps(merged), source, archived, owner_key, conversation_id, time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_session_preferences(self, session_id: str, preferences: dict[str, Any]) -> bool:
        return await self._run(self._update_session_preferences_sync, session_id, preferences)

    def _get_active_object_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        preferences = _json_loads(row["preferences_json"], {})
        runtime_state = _normalize_runtime_state(preferences.get("runtime_state"))
        active_object = normalize_active_object(runtime_state.get("active_object"))
        if active_object is not None:
            return active_object
        return normalize_active_object(runtime_state.get("active_question_context"))

    async def get_active_object(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_active_object_sync, session_id)

    def _set_active_object_sync(
        self,
        session_id: str,
        active_object: dict[str, Any] | None,
    ) -> bool:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                return False
            preferences = _json_loads(current["preferences_json"], {})
            runtime_state = _normalize_runtime_state(preferences.get("runtime_state"))
            previous_active_object = normalize_active_object(runtime_state.get("active_object"))
            normalized = normalize_active_object(
                active_object,
                previous_active_object=previous_active_object,
            )
            if normalized is None:
                runtime_state.pop("active_object", None)
                runtime_state.pop("active_question_context", None)
            else:
                runtime_state["active_object"] = normalized
                question_context = extract_question_context_from_active_object(normalized)
                if question_context is None:
                    runtime_state.pop("active_question_context", None)
                else:
                    runtime_state["active_question_context"] = question_context
            merged = {**preferences, "runtime_state": runtime_state}
            cur = conn.execute(
                """
                UPDATE sessions
                SET preferences_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json_dumps(merged), time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def set_active_object(
        self,
        session_id: str,
        active_object: dict[str, Any] | None,
    ) -> bool:
        return await self._run(
            self._set_active_object_sync,
            session_id,
            active_object,
        )

    def _get_suspended_object_stack_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return []
        preferences = _json_loads(row["preferences_json"], {})
        runtime_state = _normalize_runtime_state(preferences.get("runtime_state"))
        return normalize_suspended_object_stack(runtime_state.get("suspended_object_stack"))

    async def get_suspended_object_stack(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._get_suspended_object_stack_sync, session_id)

    def _set_suspended_object_stack_sync(
        self,
        session_id: str,
        suspended_object_stack: list[dict[str, Any]] | None,
    ) -> bool:
        normalized_stack = normalize_suspended_object_stack(suspended_object_stack)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                return False
            preferences = _json_loads(current["preferences_json"], {})
            runtime_state = _normalize_runtime_state(preferences.get("runtime_state"))
            if normalized_stack:
                runtime_state["suspended_object_stack"] = normalized_stack
            else:
                runtime_state.pop("suspended_object_stack", None)
            merged = {**preferences, "runtime_state": runtime_state}
            cur = conn.execute(
                """
                UPDATE sessions
                SET preferences_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json_dumps(merged), time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def set_suspended_object_stack(
        self,
        session_id: str,
        suspended_object_stack: list[dict[str, Any]] | None,
    ) -> bool:
        return await self._run(
            self._set_suspended_object_stack_sync,
            session_id,
            suspended_object_stack,
        )

    def _get_active_question_context_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        preferences = _json_loads(row["preferences_json"], {})
        runtime_state = _normalize_runtime_state(preferences.get("runtime_state"))
        active_object = normalize_active_object(runtime_state.get("active_object"))
        if active_object is not None:
            return extract_question_context_from_active_object(active_object)
        return normalize_question_followup_context(runtime_state.get("active_question_context"))

    async def get_active_question_context(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_active_question_context_sync, session_id)

    def _set_active_question_context_sync(
        self,
        session_id: str,
        question_context: dict[str, Any] | None,
    ) -> bool:
        return self._set_active_object_sync(session_id, question_context)

    async def set_active_question_context(
        self,
        session_id: str,
        question_context: dict[str, Any] | None,
    ) -> bool:
        return await self._run(
            self._set_active_question_context_sync,
            session_id,
            question_context,
        )

    async def get_session_with_messages(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get_session(session_id)
        if session is None:
            return None
        session["messages"] = await self.get_messages(session_id)
        session["active_turns"] = await self.list_active_turns(session_id)
        return session

    # ── Notebook entries ──────────────────────────────────────────────

    def _upsert_notebook_entries_sync(
        self, session_id: str, items: list[dict[str, Any]]
    ) -> int:
        if not items:
            return 0
        now = time.time()
        with self._connect() as conn:
            session_row = conn.execute(
                "SELECT id, owner_key, preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                raise ValueError(f"Session not found: {session_id}")
            session_owner_key = _resolve_effective_owner_key(
                session_row["owner_key"],
                _derive_owner_key_from_preferences(_json_loads(session_row["preferences_json"], {})),
            )
            upserted = 0
            for item in items:
                question = (item.get("question") or "").strip()
                question_id = (item.get("question_id") or "").strip()
                if not question or not question_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO notebook_entries (
                        session_id, owner_key, question_id, question, question_type,
                        options_json, correct_answer, explanation, difficulty,
                        user_answer, is_correct, bookmarked, followup_session_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
                    ON CONFLICT(session_id, question_id) DO UPDATE SET
                        user_answer = excluded.user_answer,
                        is_correct = excluded.is_correct,
                        owner_key = excluded.owner_key,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        session_owner_key,
                        question_id,
                        question,
                        item.get("question_type") or "",
                        _json_dumps(item.get("options") or {}),
                        item.get("correct_answer") or "",
                        item.get("explanation") or "",
                        item.get("difficulty") or "",
                        item.get("user_answer") or "",
                        1 if item.get("is_correct") else 0,
                        now,
                        now,
                    ),
                )
                upserted += 1
            conn.commit()
        return upserted

    async def upsert_notebook_entries(
        self, session_id: str, items: list[dict[str, Any]]
    ) -> int:
        return await self._run(self._upsert_notebook_entries_sync, session_id, items)

    @staticmethod
    def _serialize_notebook_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "session_id": row["session_id"],
            "session_title": row["session_title"] or "" if "session_title" in row.keys() else "",
            "question_id": row["question_id"] or "",
            "question": row["question"],
            "question_type": row["question_type"] or "",
            "options": _json_loads(row["options_json"], {}),
            "correct_answer": row["correct_answer"] or "",
            "explanation": row["explanation"] or "",
            "difficulty": row["difficulty"] or "",
            "user_answer": row["user_answer"] or "",
            "is_correct": bool(row["is_correct"]),
            "bookmarked": bool(row["bookmarked"]),
            "followup_session_id": row["followup_session_id"] or "",
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def _list_notebook_entries_sync(
        self,
        category_id: int | None,
        bookmarked: bool | None,
        is_correct: bool | None,
        limit: int,
        offset: int,
        owner_key: str | None = None,
        before_created_at: float | None = None,
        before_entry_id: int | None = None,
    ) -> dict[str, Any]:
        base = """
            SELECT
                n.id, n.session_id, COALESCE(s.title, '') AS session_title,
                n.question_id, n.question, n.question_type, n.options_json,
                n.correct_answer, n.explanation, n.difficulty,
                n.user_answer, n.is_correct, n.bookmarked,
                n.followup_session_id, n.created_at, n.updated_at
            FROM notebook_entries n
            LEFT JOIN sessions s ON s.id = n.session_id
        """
        count_base = """
            SELECT COUNT(*) AS cnt
            FROM notebook_entries n
            LEFT JOIN sessions s ON s.id = n.session_id
        """
        conditions: list[str] = []
        params: list[Any] = []
        if category_id is not None:
            join = " INNER JOIN notebook_entry_categories ec ON ec.entry_id = n.id"
            base += join
            count_base += join
            if owner_key is not None:
                base += " INNER JOIN notebook_categories c ON c.id = ec.category_id"
                count_base += " INNER JOIN notebook_categories c ON c.id = ec.category_id"
            conditions.append("ec.category_id = ?")
            params.append(category_id)
            if owner_key is not None:
                conditions.append("c.owner_key = ?")
                params.append(owner_key)
        if owner_key is not None:
            conditions.append("COALESCE(NULLIF(n.owner_key, ''), s.owner_key) = ?")
            params.append(owner_key)
        if bookmarked is not None:
            conditions.append("n.bookmarked = ?")
            params.append(1 if bookmarked else 0)
        if is_correct is not None:
            conditions.append("n.is_correct = ?")
            params.append(1 if is_correct else 0)
        effective_offset = max(int(offset), 0)
        effective_limit = max(int(limit), 1)
        if before_created_at is not None:
            cursor_entry_id = int(before_entry_id or 2**63 - 1)
            conditions.append("(n.created_at < ? OR (n.created_at = ? AND n.id < ?))")
            params.extend([float(before_created_at), float(before_created_at), cursor_entry_id])
            effective_offset = 0
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._connect() as conn:
            total_row = conn.execute(count_base + where, tuple(params)).fetchone()
            total = int(total_row["cnt"]) if total_row else 0
            rows = conn.execute(
                base + where + " ORDER BY n.created_at DESC, n.id DESC LIMIT ? OFFSET ?",
                tuple(params) + (effective_limit, effective_offset),
            ).fetchall()
        items = [self._serialize_notebook_entry(r) for r in rows]
        return {"items": items, "total": total}

    async def list_notebook_entries(
        self,
        category_id: int | None = None,
        bookmarked: bool | None = None,
        is_correct: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        owner_key: str | None = None,
        before_created_at: float | None = None,
        before_entry_id: int | None = None,
    ) -> dict[str, Any]:
        return await self._run(
            self._list_notebook_entries_sync,
            category_id,
            bookmarked,
            is_correct,
            limit,
            offset,
            owner_key,
            before_created_at,
            before_entry_id,
        )

    def _get_notebook_entry_sync(
        self,
        entry_id: int,
        owner_key: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            query = """
                SELECT
                    n.*, COALESCE(s.title, '') AS session_title
                FROM notebook_entries n
                LEFT JOIN sessions s ON s.id = n.session_id
                WHERE n.id = ?
            """
            params: list[Any] = [entry_id]
            if owner_key is not None:
                query += " AND COALESCE(NULLIF(n.owner_key, ''), s.owner_key) = ?"
                params.append(owner_key)
            row = conn.execute(query, tuple(params)).fetchone()
            if row is None:
                return None
            entry = self._serialize_notebook_entry(row)
            cats = conn.execute(
                """
                SELECT c.id, c.name
                FROM notebook_categories c
                INNER JOIN notebook_entry_categories ec ON ec.category_id = c.id
                WHERE ec.entry_id = ?
                  AND (? IS NULL OR c.owner_key = ?)
                ORDER BY c.name
                """,
                (entry_id, owner_key, owner_key),
            ).fetchall()
            entry["categories"] = [{"id": c["id"], "name": c["name"]} for c in cats]
        return entry

    async def get_notebook_entry(
        self,
        entry_id: int,
        owner_key: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._run(self._get_notebook_entry_sync, entry_id, owner_key)

    def _find_notebook_entry_sync(
        self,
        session_id: str,
        question_id: str,
        owner_key: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            query = """
                SELECT n.*, COALESCE(s.title, '') AS session_title
                FROM notebook_entries n
                LEFT JOIN sessions s ON s.id = n.session_id
                WHERE n.session_id = ? AND n.question_id = ?
            """
            params: list[Any] = [session_id, question_id]
            if owner_key is not None:
                query += " AND COALESCE(NULLIF(n.owner_key, ''), s.owner_key) = ?"
                params.append(owner_key)
            row = conn.execute(query, tuple(params)).fetchone()
        if row is None:
            return None
        return self._serialize_notebook_entry(row)

    async def find_notebook_entry(
        self,
        session_id: str,
        question_id: str,
        owner_key: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._run(self._find_notebook_entry_sync, session_id, question_id, owner_key)

    def _update_notebook_entry_sync(
        self,
        entry_id: int,
        updates: dict[str, Any],
        owner_key: str | None = None,
    ) -> bool:
        allowed = {"bookmarked", "followup_session_id", "user_answer", "is_correct"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return False
        fields["updated_at"] = time.time()
        if "bookmarked" in fields:
            fields["bookmarked"] = 1 if fields["bookmarked"] else 0
        if "is_correct" in fields:
            fields["is_correct"] = 1 if fields["is_correct"] else 0
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [entry_id]
        with self._connect() as conn:
            if owner_key is not None:
                row = conn.execute(
                    """
                    SELECT n.id
                    FROM notebook_entries n
                    LEFT JOIN sessions s ON s.id = n.session_id
                    WHERE n.id = ?
                      AND COALESCE(NULLIF(n.owner_key, ''), s.owner_key) = ?
                    """,
                    (entry_id, owner_key),
                ).fetchone()
                if row is None:
                    return False
            cur = conn.execute(
                f"UPDATE notebook_entries SET {set_clause} WHERE id = ?",
                tuple(values),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_notebook_entry(
        self,
        entry_id: int,
        updates: dict[str, Any],
        owner_key: str | None = None,
    ) -> bool:
        return await self._run(self._update_notebook_entry_sync, entry_id, updates, owner_key)

    def _delete_notebook_entry_sync(self, entry_id: int, owner_key: str | None = None) -> bool:
        with self._connect() as conn:
            if owner_key is not None:
                row = conn.execute(
                    """
                    SELECT n.id
                    FROM notebook_entries n
                    LEFT JOIN sessions s ON s.id = n.session_id
                    WHERE n.id = ?
                      AND COALESCE(NULLIF(n.owner_key, ''), s.owner_key) = ?
                    """,
                    (entry_id, owner_key),
                ).fetchone()
                if row is None:
                    return False
            cur = conn.execute("DELETE FROM notebook_entries WHERE id = ?", (entry_id,))
            conn.commit()
        return cur.rowcount > 0

    async def delete_notebook_entry(self, entry_id: int, owner_key: str | None = None) -> bool:
        return await self._run(self._delete_notebook_entry_sync, entry_id, owner_key)

    # ── Notebook categories ────────────────────────────────────────

    def _create_category_sync(self, name: str, owner_key: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notebook_categories (name, owner_key, created_at) VALUES (?, ?, ?)",
                (name.strip(), str(owner_key or "").strip(), now),
            )
            conn.commit()
        return {
            "id": int(cur.lastrowid),
            "name": name.strip(),
            "owner_key": str(owner_key or "").strip(),
            "created_at": now,
        }

    async def create_category(self, name: str, owner_key: str | None = None) -> dict[str, Any]:
        return await self._run(self._create_category_sync, name, owner_key)

    def _list_categories_sync(self, owner_key: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if owner_key is None:
                rows = conn.execute(
                    """
                    SELECT c.id, c.name, c.created_at,
                           COUNT(ec.entry_id) AS entry_count
                    FROM notebook_categories c
                    LEFT JOIN notebook_entry_categories ec ON ec.category_id = c.id
                    GROUP BY c.id
                    ORDER BY c.name
                    """,
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT c.id, c.name, c.created_at,
                           COUNT(ec.entry_id) AS entry_count
                    FROM notebook_categories c
                    LEFT JOIN notebook_entry_categories ec ON ec.category_id = c.id
                    LEFT JOIN notebook_entries n ON n.id = ec.entry_id
                    LEFT JOIN sessions s ON s.id = n.session_id
                    WHERE c.owner_key = ?
                    GROUP BY c.id
                    ORDER BY c.name
                    """,
                    (owner_key,),
                ).fetchall()
        return [
            {"id": r["id"], "name": r["name"], "created_at": float(r["created_at"]),
             "entry_count": int(r["entry_count"])}
            for r in rows
        ]

    async def list_categories(self, owner_key: str | None = None) -> list[dict[str, Any]]:
        return await self._run(self._list_categories_sync, owner_key)

    def _rename_category_sync(
        self,
        category_id: int,
        name: str,
        owner_key: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            if owner_key is not None:
                row = conn.execute(
                    "SELECT id FROM notebook_categories WHERE id = ? AND owner_key = ?",
                    (category_id, owner_key),
                ).fetchone()
                if row is None:
                    return False
            cur = conn.execute(
                "UPDATE notebook_categories SET name = ? WHERE id = ?",
                (name.strip(), category_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def rename_category(
        self,
        category_id: int,
        name: str,
        owner_key: str | None = None,
    ) -> bool:
        return await self._run(self._rename_category_sync, category_id, name, owner_key)

    def _delete_category_sync(self, category_id: int, owner_key: str | None = None) -> bool:
        with self._connect() as conn:
            if owner_key is not None:
                row = conn.execute(
                    "SELECT id FROM notebook_categories WHERE id = ? AND owner_key = ?",
                    (category_id, owner_key),
                ).fetchone()
                if row is None:
                    return False
            cur = conn.execute("DELETE FROM notebook_categories WHERE id = ?", (category_id,))
            conn.commit()
        return cur.rowcount > 0

    async def delete_category(self, category_id: int, owner_key: str | None = None) -> bool:
        return await self._run(self._delete_category_sync, category_id, owner_key)

    def _add_entry_to_category_sync(
        self,
        entry_id: int,
        category_id: int,
        owner_key: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            try:
                if owner_key is not None:
                    row = conn.execute(
                        """
                        SELECT
                            COALESCE(NULLIF(n.owner_key, ''), s.owner_key, '') AS entry_owner_key,
                            COALESCE(NULLIF(c.owner_key, ''), '') AS category_owner_key
                        FROM notebook_entries n
                        LEFT JOIN sessions s ON s.id = n.session_id
                        INNER JOIN notebook_categories c ON c.id = ?
                        WHERE n.id = ?
                        """,
                        (category_id, entry_id),
                    ).fetchone()
                    if row is None:
                        return False
                    if row["entry_owner_key"] != owner_key or row["category_owner_key"] != owner_key:
                        return False
                conn.execute(
                    "INSERT OR IGNORE INTO notebook_entry_categories (entry_id, category_id) VALUES (?, ?)",
                    (entry_id, category_id),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return False
        return True

    async def add_entry_to_category(
        self,
        entry_id: int,
        category_id: int,
        owner_key: str | None = None,
    ) -> bool:
        return await self._run(self._add_entry_to_category_sync, entry_id, category_id, owner_key)

    def _remove_entry_from_category_sync(
        self,
        entry_id: int,
        category_id: int,
        owner_key: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            if owner_key is not None:
                row = conn.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(n.owner_key, ''), s.owner_key, '') AS entry_owner_key,
                        COALESCE(NULLIF(c.owner_key, ''), '') AS category_owner_key
                    FROM notebook_entries n
                    LEFT JOIN sessions s ON s.id = n.session_id
                    INNER JOIN notebook_categories c ON c.id = ?
                    WHERE n.id = ?
                    """,
                    (category_id, entry_id),
                ).fetchone()
                if row is None:
                    return False
                if row["entry_owner_key"] != owner_key or row["category_owner_key"] != owner_key:
                    return False
            cur = conn.execute(
                "DELETE FROM notebook_entry_categories WHERE entry_id = ? AND category_id = ?",
                (entry_id, category_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def remove_entry_from_category(
        self,
        entry_id: int,
        category_id: int,
        owner_key: str | None = None,
    ) -> bool:
        return await self._run(self._remove_entry_from_category_sync, entry_id, category_id, owner_key)

    def _get_entry_categories_sync(
        self,
        entry_id: int,
        owner_key: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            query = """
                SELECT c.id, c.name FROM notebook_categories c
                INNER JOIN notebook_entry_categories ec ON ec.category_id = c.id
                WHERE ec.entry_id = ?
            """
            params: list[Any] = [entry_id]
            if owner_key is not None:
                query += " AND c.owner_key = ?"
                params.append(owner_key)
            rows = conn.execute(query + " ORDER BY c.name", tuple(params)).fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    async def get_entry_categories(
        self,
        entry_id: int,
        owner_key: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._run(self._get_entry_categories_sync, entry_id, owner_key)


_instance: SQLiteSessionStore | None = None


def get_sqlite_session_store() -> SQLiteSessionStore:
    global _instance
    if _instance is None:
        _instance = SQLiteSessionStore()
    return _instance


__all__ = ["SQLiteSessionStore", "get_sqlite_session_store"]
