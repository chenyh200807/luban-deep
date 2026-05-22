"""ARRS-style revalidation queue read projection.

This module does not create a scheduler table or a second prescription
authority. It reads existing learner-state projections and emits at most one
active verification probe for the current learner/day. The intent embedded in
each probe is still produced by ``training_intent``.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from deeptutor.services.learner_state.mastery_estimator import DECAY_PROFILES
from deeptutor.services.learner_state.training_intent import (
    build_learning_training_intent,
    prioritize_training_intents,
)

_TZ = timezone(timedelta(hours=8))
_DEFAULT_SCHEDULE = (3, 7)


def build_revalidation_queue_projection(
    *,
    user_id: str,
    candidates: Iterable[dict[str, Any]] | None = None,
    events: Iterable[Any] | None = None,
    scoring_point_map: dict[str, Any] | None = None,
    learning_state: dict[str, Any] | None = None,
    prescription_outcomes: Iterable[dict[str, Any]] | None = None,
    declined_probe_ids: Iterable[str] | None = None,
    now_iso: str = "",
) -> dict[str, Any]:
    now = _parse_iso(now_iso) or datetime.now(_TZ)
    rows = _candidate_rows(
        candidates=candidates,
        events=events,
        scoring_point_map=scoring_point_map,
        learning_state=learning_state,
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
        if not _is_due(row, now=now):
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

    prioritized = prioritize_training_intents(
        [item["intent"] for item in due_items],
        max_active=1,
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
    emitted_items = due_items[:1]
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
            "daily_capacity": 1,
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


def _is_due(row: dict[str, Any], *, now: datetime) -> bool:
    observed_at = _parse_iso(
        str(row.get("last_observed_at") or row.get("last_practiced_at") or "")
    )
    if observed_at is None:
        return True
    age_days = (now - observed_at).total_seconds() / 86400
    return age_days >= _first_interval_days(row)


def _first_interval_days(row: dict[str, Any]) -> int:
    if row.get("state") == "weak":
        return 3
    ability = str(row.get("ability_dimension") or "").strip()
    profile = DECAY_PROFILES.get(ability) or {}
    schedule = profile.get("revalidation_schedule") or _DEFAULT_SCHEDULE
    try:
        return int(list(schedule)[0])
    except (TypeError, ValueError, IndexError):
        return 3


def _probe_id(*, user_id: str, row: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(user_id or "").strip(),
            str(row.get("node_id") or row.get("knowledge_node_id") or "").strip(),
            str(row.get("ability_dimension") or "code_application").strip(),
            str(row.get("error_code") or "").strip(),
        ]
    )
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


__all__ = ["build_revalidation_queue_projection"]
