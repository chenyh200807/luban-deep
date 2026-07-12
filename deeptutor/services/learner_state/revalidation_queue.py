"""ARRS-style revalidation queue read projection.

This module does not create a scheduler table or a second prescription
authority. It reads existing learner-state projections and emits at most one
active verification probe for the current learner/day. The intent embedded in
each probe is still produced by ``training_intent``.
"""
from __future__ import annotations

# 复习到期日容量(owner 2026-07-11 拍板 5;此前 v3.2 §6.1 口径为 1)
_DAILY_MAX_ACTIVE = 5

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Iterable

from deeptutor.services.learner_state.mastery_estimator import DECAY_PROFILES
from deeptutor.services.learner_state.training_intent import (
    build_learning_training_intent,
    prioritize_training_intents,
)

_TZ = timezone(timedelta(hours=8))
_DEFAULT_SCHEDULE = DECAY_PROFILES["code_application"]["revalidation_schedule"]

# ── 复习引擎地平线参数（双轮设计 v3.2 §6.1，调度真值唯一归本模块）──
# 间隔上限：早期 cap ≤14 天（FSRS 实战教训——过长间隔让用户觉得"App 把我忘了"）。
_INTERVAL_CAP_DAYS = 14
# 考试日期地平线：考前 40 天起确定性压缩间隔（线性缩放，无 AI 无随机）。
_EXAM_COMPRESSION_WINDOW_DAYS = 40


def build_revalidation_queue_projection(
    *,
    user_id: str,
    candidates: Iterable[dict[str, Any]] | None = None,
    events: Iterable[Any] | None = None,
    scoring_point_map: dict[str, Any] | None = None,
    learning_state: dict[str, Any] | None = None,
    dispute_candidates: Iterable[dict[str, Any]] | None = None,
    prescription_outcomes: Iterable[dict[str, Any]] | None = None,
    declined_probe_ids: Iterable[str] | None = None,
    now_iso: str = "",
    exam_date_iso: str = "",
) -> dict[str, Any]:
    now = _parse_iso(now_iso) or datetime.now(_TZ)
    rows = _candidate_rows(
        candidates=candidates,
        events=events,
        scoring_point_map=scoring_point_map,
        learning_state=learning_state,
        dispute_candidates=dispute_candidates,
    )
    declined = {str(item or "").strip() for item in list(declined_probe_ids or [])}
    verified = {
        str(item.get("training_intent_id") or "").strip()
        for item in list(prescription_outcomes or [])
        if isinstance(item, dict) and item.get("status") == "verified"
    }
    blocked_reasons: set[str] = set()
    due_items: list[dict[str, Any]] = []

    for row in rows:
        probe_id = _probe_id(user_id=user_id, row=row)
        if probe_id in verified:
            blocked_reasons.add("already_verified")
            continue
        if not _is_due(row, now=now, exam_date_iso=exam_date_iso):
            blocked_reasons.add("not_due")
            continue
        item = _queue_item(
            user_id=user_id,
            row=row,
            probe_id=probe_id,
            now=now,
            declined=probe_id in declined,
        )
        due_items.append(item)

    # 日容量 owner 拍板 2026-07-11: 1→5("做1实在太少了")。
    # 复习页三层信息架构(汇总gauge/约定卡/到期清单)自此名副其实。
    prioritized = prioritize_training_intents(
        [item["intent"] for item in due_items],
        max_active=_DAILY_MAX_ACTIVE,
    )
    priority_by_id = {
        str(intent.get("training_intent_id") or ""): intent
        for intent in prioritized
    }
    due_items.sort(
        key=lambda item: (
            -float(priority_by_id.get(item["probe_id"], {}).get("priority") or 0),
            item["probe_id"],
        )
    )
    emitted_items = due_items[:_DAILY_MAX_ACTIVE]
    for item in emitted_items:
        prioritized_intent = priority_by_id.get(item["probe_id"])
        if prioritized_intent:
            item["intent"] = prioritized_intent
            if item["status"] != "deferred":
                item["status"] = prioritized_intent.get("status") or "queued"

    return {
        "items": emitted_items,
        "source_status": {
            "authority": "learner_memory_events.learning_evidence -> mastery_estimator -> training_intent",
            "model": "rule_based_arrs_v1",
            "daily_capacity": _DAILY_MAX_ACTIVE,
            "candidate_count": len(rows),
            "due_count": len(due_items),
            "suppressed_due_count": max(len(due_items) - len(emitted_items), 0),
            "blocked_reasons": sorted(blocked_reasons),
        },
    }


def _candidate_rows(
    *,
    candidates: Iterable[dict[str, Any]] | None,
    events: Iterable[Any] | None,
    scoring_point_map: dict[str, Any] | None,
    learning_state: dict[str, Any] | None,
    dispute_candidates: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    base = _base_candidate_rows(
        candidates=candidates,
        events=events,
        scoring_point_map=scoring_point_map,
        learning_state=learning_state,
    )
    # 学员订正候选【可叠加】到 base（不替换 scoring_point_map / candidates 源）。
    dispute_rows = [_safe_dict(item) for item in list(dispute_candidates or []) if isinstance(item, dict)]
    if not dispute_rows:
        return base
    seen = {_row_key(row) for row in base}
    merged = list(base)
    for row in dispute_rows:
        key = _row_key(row)
        if key not in seen:
            merged.append(row)
            seen.add(key)
    return merged


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("node_id") or row.get("knowledge_node_id") or "").strip(),
        str(row.get("ability_dimension") or "code_application").strip(),
        str(row.get("error_code") or "").strip(),
    )


def dispute_candidates_from_events(events: Iterable[Any] | None) -> list[dict[str, Any]]:
    """从 events 提取 ``learning_signal_type == "user_dispute"`` 的订正事件，
    造 ``needs_revalidation`` 立即到期候选行（``last_observed_at=""``）。

    双向：``user_says ∈ {mastered, not_mastered}`` 都触发复测；自我声明只排复测，
    绝不直接置 mastered。对 dict 与对象事件(payload_json)均鲁棒。
    """
    rows: list[dict[str, Any]] = []
    for ev in list(events or []):
        payload = ev.get("payload_json") if isinstance(ev, dict) else getattr(ev, "payload_json", None)
        if not isinstance(payload, dict):
            payload = ev if isinstance(ev, dict) else {}
        if str(payload.get("learning_signal_type") or "").strip() != "user_dispute":
            continue
        concept_id = str(payload.get("concept_id") or "").strip()
        if not concept_id:
            continue
        event_id = ev.get("event_id") if isinstance(ev, dict) else getattr(ev, "event_id", "")
        event_id = str(event_id or "").strip()
        rows.append({
            "node_id": concept_id,
            "label": str(payload.get("concept_label") or "").strip(),
            "state": "needs_revalidation",
            "ability_dimension": str(payload.get("ability_dimension") or "").strip(),
            "error_code": str(payload.get("error_code") or "").strip(),
            "evidence_refs": [event_id] if event_id else [],
            "last_observed_at": "",
        })
    return rows


def _base_candidate_rows(
    *,
    candidates: Iterable[dict[str, Any]] | None,
    events: Iterable[Any] | None,
    scoring_point_map: dict[str, Any] | None,
    learning_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if candidates is not None:
        return [_safe_dict(item) for item in list(candidates or []) if isinstance(item, dict)]
    if scoring_point_map is not None:
        return _candidates_from_scoring_map(scoring_point_map=scoring_point_map, events=events)
    state = _safe_dict(learning_state)
    rows: list[dict[str, Any]] = []
    for item in list(state.get("knowledge_state") or []):
        row = _safe_dict(item)
        if row.get("state") in {"weak", "unstable", "needs_revalidation"}:
            rows.append(row)
    return rows


def _candidates_from_scoring_map(
    *,
    scoring_point_map: dict[str, Any],
    events: Iterable[Any] | None,
) -> list[dict[str, Any]]:
    by_id = {
        str(getattr(event, "event_id", "") or "").strip(): event
        for event in list(events or [])
        if str(getattr(event, "event_id", "") or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    for item in list(_safe_dict(scoring_point_map).get("items") or []):
        row = _safe_dict(item)
        refs = [
            ref
            for ref in _refs(row.get("evidence_refs"))
            if str(ref or "").strip() in by_id
        ]
        if not refs:
            continue
        last_observed_at = max(
            str(getattr(by_id[str(ref)], "created_at", "") or "") for ref in refs
        )
        error_code = ""
        for code in list(row.get("error_codes") or []):
            error_code = str(code or "").strip()
            if error_code:
                break
        candidates.append({
            "node_id": str(row.get("knowledge_node_id") or "").strip(),
            "label": str(row.get("label") or "").strip(),
            "state": "weak" if _safe_int(row.get("miss_count")) >= 2 else "unstable",
            "ability_dimension": str(row.get("ability_dimension") or "").strip(),
            "error_code": error_code,
            "evidence_refs": refs,
            "last_observed_at": last_observed_at,
            "forgetting_risk": 0.75 if _safe_int(row.get("miss_count")) >= 2 else 0.6,
        })
    return candidates


def _queue_item(
    *,
    user_id: str,
    row: dict[str, Any],
    probe_id: str,
    now: datetime,
    declined: bool,
) -> dict[str, Any]:
    evidence_refs = _refs(row.get("evidence_refs"))
    ability_dimension = str(row.get("ability_dimension") or "code_application").strip()
    intent = build_learning_training_intent(
        user_id=user_id,
        concept_id=str(row.get("node_id") or row.get("knowledge_node_id") or "").strip(),
        concept_label=str(row.get("label") or "").strip(),
        error_code=str(row.get("error_code") or "").strip(),
        evidence_refs=evidence_refs,
        ability_dimension=ability_dimension,
        behavior_state=str(row.get("state") or "").strip(),
        source="revalidation_queue",
        reason="arrs_revalidation_probe",
    )
    intent["training_intent_id"] = probe_id
    next_available_at = (now + timedelta(days=1)).isoformat() if declined else ""
    return {
        "probe_id": probe_id,
        "kind": "revalidation_probe",
        "status": "deferred" if declined else "queued",
        "due_at": now.isoformat(),
        "next_available_at": next_available_at,
        "evidence_refs": evidence_refs,
        "intent": intent,
    }


def _is_due(row: dict[str, Any], *, now: datetime, exam_date_iso: str = "") -> bool:
    observed_at = _parse_iso(
        str(row.get("last_observed_at") or row.get("last_practiced_at") or "")
    )
    if observed_at is None:
        return True
    if row.get("state") == "fresh":
        # 新学相"明天见"按日历日(§9-D2: "天"=UTC+8 日历日, 服务端折算)——
        # 昨晚学的今早即到期; 满 24h 判定会把它拖到晚上, 违背次日承诺。
        return now.astimezone(_TZ).date() > observed_at.astimezone(_TZ).date()
    age_days = (now - observed_at).total_seconds() / 86400
    return age_days >= effective_interval_days(
        _first_interval_days(row), now=now, exam_date_iso=exam_date_iso
    )


def _first_interval_days(row: dict[str, Any]) -> int:
    # "fresh" = 新学相(双轮 §6.1 分相: 刚学的走短间隔, 首跳次日)——
    # 交接时刻"明天见"承诺的调度语义载体; 巩固后转常规 schedule 是阶段 2。
    if row.get("state") == "fresh":
        return 1
    if row.get("state") == "weak":
        return 3
    ability = str(row.get("ability_dimension") or "").strip()
    profile = DECAY_PROFILES.get(ability) or DECAY_PROFILES.get("code_application") or {}
    schedule = profile.get("revalidation_schedule") or _DEFAULT_SCHEDULE
    try:
        index = 0
        if row.get("state") == "stable":
            index = max(0, int(row.get("successful_review_streak") or 1) - 1)
        values = list(schedule)
        return int(values[min(index, len(values) - 1)])
    except (TypeError, ValueError, IndexError):
        return 3


def effective_interval_days(base_days: int, *, now: datetime, exam_date_iso: str = "") -> int:
    """§6.1 地平线折算：base 间隔 → 生效间隔（纯确定性，无 AI）。

    1. 间隔上限 cap ≤14 天（恒生效）。
    2. exam_date 已设且 0 < 距考天数 ≤40：线性压缩 ``base × 距考/40``（考前 40 天
       起确定性压缩）；再钳到不超过距考天数——**考前一周结构上不可能出现
       "21 天后复习"**（§6.1 硬边界）。
    3. 考后（距考 ≤0）不压缩（队列语义切换归后续阶段，不在此发明）。
    """
    days = max(1, _safe_int(base_days) or 1)
    days = min(days, _INTERVAL_CAP_DAYS)
    exam_date = _parse_iso(str(exam_date_iso or ""))
    if exam_date is None:
        return days
    days_to_exam = (exam_date.astimezone(_TZ).date() - now.astimezone(_TZ).date()).days
    if days_to_exam <= 0:
        return days
    if days_to_exam <= _EXAM_COMPRESSION_WINDOW_DAYS:
        days = max(1, round(days * days_to_exam / _EXAM_COMPRESSION_WINDOW_DAYS))
    return min(days, days_to_exam)


def derive_review_due_at(
    *,
    last_observed_at: str,
    state: str = "weak",
    ability_dimension: str = "",
    now_iso: str = "",
    exam_date_iso: str = "",
) -> str:
    """读侧派生「计划复习时刻」——到期/间隔真值唯一归本模块（双轮 v3 §10-①）。

    ``mistake_book`` 等 read model 只准调用此函数取 ``review_due_at``，禁自算
    间隔（防第二调度权威）。零写入：返回 ISO 字符串由调用方投影，不落库。
    ``fresh`` 走日历日次日；其余 = 观测时刻 + 生效间隔（含 §6.1 cap/考期压缩）。
    """
    observed = _parse_iso(str(last_observed_at or ""))
    if observed is None:
        return ""
    now = _parse_iso(now_iso) or datetime.now(_TZ)
    row = {"state": str(state or "").strip(), "ability_dimension": str(ability_dimension or "").strip()}
    if row["state"] == "fresh":
        next_day = observed.astimezone(_TZ).date() + timedelta(days=1)
        return datetime(next_day.year, next_day.month, next_day.day, tzinfo=_TZ).isoformat()
    days = effective_interval_days(
        _first_interval_days(row), now=now, exam_date_iso=exam_date_iso
    )
    return (observed + timedelta(days=days)).isoformat()


def _probe_id(*, user_id: str, row: dict[str, Any]) -> str:
    parts = [
        str(user_id or "").strip(),
        str(row.get("node_id") or row.get("knowledge_node_id") or "").strip(),
        str(row.get("ability_dimension") or "code_application").strip(),
        str(row.get("error_code") or "").strip(),
    ]
    cycle_anchor = str(row.get("cycle_anchor") or "").strip()
    if cycle_anchor:
        parts.append(cycle_anchor)
    raw = "|".join(parts)
    human = raw.replace("|", "_")
    if len(human) <= 80 and all(part for part in raw.split("|")):
        return "rvp_" + human
    return "rvp_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _refs(value: Any) -> list[str]:
    result: list[str] = []
    for item in list(value or []):
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    return parsed.astimezone(_TZ)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = [
    "build_revalidation_queue_projection",
    "derive_review_due_at",
    "dispute_candidates_from_events",
    "effective_interval_days",
]
