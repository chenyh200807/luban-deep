"""Canonical active_object builder / normalizer (single authority).

Historically two builder/normalizer pairs existed and diverged on identity口径:

* ``deeptutor/services/semantic_router.py``     produced the *next* active_object
  for the capability side (orchestrator / deep_question / tutorbot).
* ``deeptutor/services/session/sqlite_store.py`` produced the *current*
  active_object for the persistence side (turn_runtime restore / persist).

They disagreed on:

1. ``object_id`` derivation for multi-item sets — SR used ``question_set:<first
   item>`` while SS preferred ``parent_quiz_session_id`` then
   ``question_set:Q1|Q2``. Same input → different id → ``_same_active_object``
   returns False → follow-up (回指) mis-binding (SEV-1).
2. ``object_type`` set — SS lacked ``open_world_question`` and silently
   downgraded it, losing the object's identity tier.
3. ``entered_at`` / ``last_touched_at`` type — SR string化 (lossy) vs SS
   time-aware float.

This module is now the SINGLE authority for that口径. ``sqlite_store`` and
``semantic_router`` both import the builder / normalizer from here, so the
restore side (current) and the capability side (next) always agree.

Canonical口径 (absorbs the more complete sqlite_store base + SR's two missing
features):

* object_id re-derive: ``parent_quiz_session_id`` wins for multi-item sets so
  the id identifies the whole set (not a single item) and survives single-item
  grading collapse. **preserve-when-passed**: an explicit ``object_id`` (an
  already-persisted id) is kept verbatim and never re-formatted, so existing
  in-flight sessions do not see a migration break-point.
* object_type set: ``{single_question, question_set, open_world_question}`` plus
  aliases; unknown values fall back to item-count inference.
* timestamps: time-aware floats (no string化 data loss).
* version: positive-int coerce, else ``prev + 1`` when identity is unchanged,
  else 1.
"""

from __future__ import annotations

import time
from typing import Any

from deeptutor.services.question_followup import normalize_question_followup_context

QUESTION_ACTIVE_OBJECT_TYPES = {"single_question", "question_set", "open_world_question"}
QUESTION_ACTIVE_OBJECT_TYPE_ALIASES = {
    "question": "single_question",
    "single_question": "single_question",
    "question_set": "question_set",
    # open_world_question 让出题侧（如 source-backed 变式卡）显式声明开放世界 tier；
    # 缺失会被静默降级成 single_question/question_set，从而丢失对象身份（回指错绑）。
    "open_world_question": "open_world_question",
}


def coerce_positive_int(value: Any) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def coerce_timestamp(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def normalize_question_active_object_type(value: Any, *, has_multiple_items: bool) -> str:
    normalized = QUESTION_ACTIVE_OBJECT_TYPE_ALIASES.get(str(value or "").strip().lower())
    if normalized:
        return normalized
    # 口径与 derive_question_active_object_id 一致：只有 item 数 > 1 才是 question_set；
    # 单 item（如一道含 A-E 选项的 MCQ followup）是 single_question。
    return "question_set" if has_multiple_items else "single_question"


def build_question_active_object_scope(question_context: dict[str, Any]) -> dict[str, Any]:
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


def derive_question_active_object_id(question_context: dict[str, Any]) -> str:
    """Canonical id derivation for a question active_object.

    For multi-item sets the id must identify the WHOLE set (抗单题 collapse) and
    must be stable / deterministic across the restore (current) and capability
    (next) sides. Precedence for multi-item sets:

    1. ``parent_quiz_session_id`` — the explicit quiz/set identifier.
    2. a top-level ``question_id`` — when the set itself carries a set-level id
       (existing in-flight sessions were stamped this way; honoring it keeps the
       回指 chain stable across the口径 unification rollout).
    3. ``question_set:Q1|Q2|...`` — synthesized from item ids as the last resort.
    """
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
        set_level_question_id = str(question_context.get("question_id") or "").strip()
        if set_level_question_id:
            return set_level_question_id
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
    items = normalized_question.get("items") if isinstance(normalized_question.get("items"), list) else []
    has_multiple_items = len(items) > 1
    resolved_object_type = normalize_question_active_object_type(
        object_type, has_multiple_items=has_multiple_items
    )
    # preserve-when-passed: an explicit object_id (already-persisted id) is kept
    # verbatim — never re-formatted — so existing in-flight sessions keep their
    # canonical id and do not break the回指 chain on the unification rollout.
    resolved_object_id = str(object_id or "").strip() or derive_question_active_object_id(
        normalized_question
    )
    previous_object_type = str(previous.get("object_type") or "").strip()
    previous_object_id = str(previous.get("object_id") or "").strip()
    same_identity = (
        previous_object_type in QUESTION_ACTIVE_OBJECT_TYPES
        and previous_object_type == resolved_object_type
        and previous_object_id == resolved_object_id
    )

    resolved_scope = scope if isinstance(scope, dict) else build_question_active_object_scope(
        normalized_question
    )
    resolved_version = coerce_positive_int(version)
    if resolved_version is None:
        previous_version = coerce_positive_int(previous.get("version")) or 0
        resolved_version = previous_version + 1 if same_identity else 1

    resolved_entered_at = coerce_timestamp(entered_at)
    if resolved_entered_at is None:
        resolved_entered_at = (
            coerce_timestamp(previous.get("entered_at")) if same_identity else resolved_now
        )
        if resolved_entered_at is None:
            resolved_entered_at = resolved_now
    resolved_last_touched_at = coerce_timestamp(last_touched_at) or resolved_now
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
    resolved_version = coerce_positive_int(raw.get("version")) or 1
    resolved_entered_at = coerce_timestamp(raw.get("entered_at")) or resolved_now
    resolved_last_touched_at = coerce_timestamp(raw.get("last_touched_at")) or resolved_now
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


# PR3-6c 退役的镜像态对象类型。存量来源:2026-08-10 之前
# ``orchestrator._record_lifecycle_decision`` 在 blocked 轮把
# ``build_question_lifecycle_clarification_context`` 的产物写成 active_object,
# 并把真正在场的题目对象压进 suspended stack。该 writer 与其所有读端已删,
# 但**已落库的会话仍带着这个垃圾对象**(它是一次性快照,永不会被自己刷新)。
RETIRED_CLARIFICATION_OBJECT_TYPE = "question_lifecycle_clarification"


def discard_retired_clarification_active_object(
    active_object: dict[str, Any] | None,
    suspended_object_stack: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    """读时一次性迁移(PR3-R5 / F7):丢弃存量 clarification 对象并 resume 栈顶。

    F7 病灶:6c 删掉 writer 之后,存量会话恢复出来的 active_object 仍是
    ``question_lifecycle_clarification``。它的 ``object_type`` 落在
    ``active_object_family_for_type`` 的 ``""`` 桶(非题型),``question`` 家族的所有
    承接(回指/判分/re-present/anti-peek carve-out)全部读不到题——而真正的题目对象
    就压在 suspended stack 栈顶,被这个垃圾挡着永远回不来。

    返回 ``(active_object, suspended_object_stack, migrated)``。非 clarification
    对象**原样透传**(stack 也不重排),所以正常会话零影响。

    删除时机:存量会话的这层垃圾会随本函数在每次读时被清掉、并由调用方写回持久层;
    等生产上 ``migrated`` 计数长期为 0(会话时间衰减完)即可删除本函数与常量。
    """

    if not isinstance(active_object, dict):
        return active_object, list(suspended_object_stack or []), False
    object_type = str(active_object.get("object_type") or "").strip()
    if object_type != RETIRED_CLARIFICATION_OBJECT_TYPE:
        return active_object, list(suspended_object_stack or []), False
    normalized_stack = normalize_suspended_object_stack(suspended_object_stack)
    if not normalized_stack:
        return None, [], True
    # 栈顶 = index 0(_prepend_suspended_object 的 prepend 口径)。
    return dict(normalized_stack[0]), list(normalized_stack[1:]), True
