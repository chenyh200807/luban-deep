"""PROGRESS 三个事实字段的唯一投影器：total_attempts / last_practiced_at / today.today_done。

**真值是 learning_evidence 账本，PROGRESS 只是它的投影。**
本模块把账本派生成这三个数字，不做累加。派生而非累加意味着同一次完成重放多少遍
都得到同一组数字——幂等由 `append_memory_event(dedupe_key=...)` 的 exactly-once
账本保证，不需要第二套去重台账。

边界（owner 明确）：只写这三个**事实**字段。
mastery / chapters[*].done / 推荐相关字段是「判断」不是「事实」，本模块一律不碰。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from deeptutor.services.learner_state.evidence_lifecycle import (
    is_learning_evidence_record,
    is_progress_countable_event,
)

_TZ = timezone(timedelta(hours=8))

PROGRESS_COUNTER_FIELDS = ("total_attempts", "last_practiced_at", "today_done")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _today_key() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _day_key_from_iso(value: str) -> str | None:
    """ISO 时间戳 → +08:00 的 YYYY-MM-DD；缺失/畸形/未来时间返回 None。

    与 learning_report_read_model._date_key_from_iso 同口径：未来时间戳不得
    被折进今天的计数。
    """
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    if parsed > datetime.now(_TZ) + timedelta(minutes=5):
        return None
    return parsed.astimezone(_TZ).strftime("%Y-%m-%d")


def _identity(event: Any) -> str:
    """同一条证据在本地/远端两副本上的稳定身份。

    dedupe_key 是 append_memory_event 的 exactly-once 键，优先用它；
    没有时退到 event_id。注意**不能**用 evidence_attempt_id——first_run 一次
    完成的 N 道题共享同一个 completion_id，那会把 N 题坍缩成 1 次。
    """
    return (
        _clean(getattr(event, "dedupe_key", ""))
        or _clean(getattr(event, "event_id", ""))
        or _clean(getattr(event, "source_id", ""))
    )


def build_progress_counters(events: list[Any] | None) -> dict[str, Any]:
    """从证据账本派生三个数字。无可计数证据时返回全零/空。"""
    seen: set[str] = set()
    total_attempts = 0
    today_done = 0
    last_practiced_at = ""
    today_key = _today_key()

    for event in list(events or []):
        if not is_learning_evidence_record(event):
            continue
        if not is_progress_countable_event(event):
            continue
        identity = _identity(event)
        if identity:
            if identity in seen:
                continue
            seen.add(identity)
        created_at = _clean(getattr(event, "created_at", ""))
        day = _day_key_from_iso(created_at)
        if day is None:
            continue
        total_attempts += 1
        if day == today_key:
            today_done += 1
        if created_at > last_practiced_at:
            last_practiced_at = created_at

    return {
        "total_attempts": total_attempts,
        "last_practiced_at": last_practiced_at,
        "today_done": today_done,
    }


def build_progress_counters_patch(
    events: list[Any] | None,
    *,
    existing_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """派生出可直接喂 merge_progress 的 patch（deep-merge 友好，单调不回退）。

    三个字段都取 max(已有, 派生)：既保证重复调用不会二次累加，也保证不会把
    别的 writer（如引导学习完成）已经写高的数字改小。派生为 0 时不下发该字段。
    """
    counters = build_progress_counters(events)
    current = dict(existing_progress or {})
    current_today = dict(current.get("today") or {})

    patch: dict[str, Any] = {}

    total_attempts = max(counters["total_attempts"], _safe_int(current.get("total_attempts")))
    if total_attempts > 0:
        patch["total_attempts"] = total_attempts

    last_practiced_at = max(counters["last_practiced_at"], _clean(current.get("last_practiced_at")))
    if last_practiced_at:
        patch["last_practiced_at"] = last_practiced_at

    today_done = max(counters["today_done"], _safe_int(current_today.get("today_done")))
    if today_done > 0:
        patch["today"] = {"today_done": today_done}

    return patch


def write_progress_counters(
    learner_state_service: Any,
    *,
    user_id: str,
) -> dict[str, Any]:
    """把账本派生的三个数字投影进 PROGRESS。返回实际下发的 patch（空 = 无事可写）。

    尽力而为：读账本或写 PROGRESS 失败都不抛——证据账本才是真值，投影落后
    不该把用户已经答完的一次摸底整个回滚掉。
    """
    normalized_user_id = _clean(user_id)
    if not normalized_user_id:
        return {}

    lister = getattr(learner_state_service, "list_memory_events", None)
    merger = getattr(learner_state_service, "merge_progress", None)
    reader = getattr(learner_state_service, "read_progress", None)
    if not callable(lister) or not callable(merger):
        return {}

    try:
        events = list(lister(normalized_user_id, limit=None) or [])
    except Exception:
        return {}

    existing_progress: dict[str, Any] = {}
    if callable(reader):
        try:
            existing_progress = dict(reader(normalized_user_id) or {})
        except Exception:
            existing_progress = {}

    patch = build_progress_counters_patch(events, existing_progress=existing_progress)
    if not patch:
        return {}
    try:
        merger(normalized_user_id, patch)
    except Exception:
        return {}
    return patch


__all__ = [
    "PROGRESS_COUNTER_FIELDS",
    "build_progress_counters",
    "build_progress_counters_patch",
    "write_progress_counters",
]
