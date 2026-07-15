"""Batch D Task 9: prescription completion read projection.

Reads the canonical ``learner_memory_events.learning_evidence`` stream and
projects whether a training intent reached verification. This module is
read-only: it does not create a prescription authority, table, endpoint or
recommendation engine.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from deeptutor.services.learner_state.evidence_lifecycle import (
    committed_retest_completion_ids,
    is_canonical_luban_retest_terminal,
)

_TZ = timezone(timedelta(hours=8))


def build_prescription_outcomes_read_projection(
    *, events: Iterable[Any]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    unlinked: list[dict[str, Any]] = []
    ordered = sorted(
        list(events or []),
        key=lambda event: (
            str(getattr(event, "created_at", "") or ""),
            str(getattr(event, "event_id", "") or ""),
        ),
    )
    for event in ordered:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if not _has_prescription_signal(payload):
            continue
        intent_id = str(payload.get("training_intent_id") or "").strip()
        if not intent_id:
            unlinked.append(_unlinked_prescription_outcome(event))
            continue
        grouped[intent_id].append(event)

    outcomes = [
        _prescription_outcome(intent_id, group)
        for intent_id, group in grouped.items()
    ]
    outcomes.extend(unlinked)
    return sorted(
        outcomes,
        key=lambda item: str(item.get("latest_event_at") or ""),
        reverse=True,
    )


def _has_prescription_signal(payload: dict[str, Any]) -> bool:
    return bool(
        str(payload.get("training_intent_id") or "").strip()
        or str(payload.get("prescription_phase") or "").strip()
        or _safe_dict(payload.get("prescription_result"))
    )


def _unlinked_prescription_outcome(event: Any) -> dict[str, Any]:
    event_id = str(getattr(event, "event_id", "") or "").strip()
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return {
        "training_intent_id": "",
        "status": "unlinked_training_evidence",
        "prescription_phase": str(payload.get("prescription_phase") or "").strip(),
        "score_ratio": None,
        "verified_at": "",
        "latest_event_at": str(getattr(event, "created_at", "") or "").strip(),
        "evidence_refs": [event_id] if event_id else [],
        "next_required_action": "link_to_training_intent",
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "degraded": True,
        },
    }


def _prescription_outcome(training_intent_id: str, events: list[Any]) -> dict[str, Any]:
    ordered = sorted(
        list(events or []),
        key=lambda event: (
            str(getattr(event, "created_at", "") or ""),
            str(getattr(event, "event_id", "") or ""),
        ),
    )
    evidence_refs = [
        str(getattr(event, "event_id", "") or "").strip()
        for event in ordered
        if str(getattr(event, "event_id", "") or "").strip()
    ]
    latest = ordered[-1] if ordered else None
    latest_payload = _safe_dict(
        getattr(latest, "payload_json", {}) if latest is not None else {}
    )
    latest_result = _safe_dict(latest_payload.get("prescription_result"))
    target_pack_id = str(latest_payload.get("target_pack_id") or "").strip().upper()
    concept_label = str(latest_payload.get("concept_label") or "").strip()
    latest_status = str(latest_result.get("status") or "").strip()
    latest_phase = str(latest_payload.get("prescription_phase") or "").strip()
    verified_at = str(latest_result.get("verified_at") or "").strip()
    score_ratio = _score_ratio_value(
        latest_result.get("score_ratio", latest_payload.get("score_ratio"))
    )

    committed_retest_ids = committed_retest_completion_ids(ordered)
    verified_probe = _latest_grading_probe(
        ordered,
        require_success=True,
        committed_retest_ids=committed_retest_ids,
    )
    failed_probe = _latest_grading_probe(
        ordered,
        require_success=False,
        committed_retest_ids=committed_retest_ids,
    )

    if verified_probe is not None and evidence_refs:
        status = "verified"
        next_required_action = "maintain"
        verified_payload = _safe_dict(getattr(verified_probe, "payload_json", {}))
        verified_result = _safe_dict(verified_payload.get("prescription_result"))
        score_ratio = _score_ratio_value(
            verified_result.get("score_ratio", verified_payload.get("score_ratio"))
        )
        verified_at = str(
            verified_result.get("verified_at")
            or getattr(verified_probe, "created_at", "")
            or ""
        ).strip()
        latest_phase = str(
            verified_payload.get("prescription_phase") or latest_phase
        ).strip()
    elif failed_probe is not None:
        status = "not_verified"
        next_required_action = "retry_verification_probe"
    elif latest_status == "verified":
        status = "not_verified"
        next_required_action = "complete_verification_probe"
    elif _assigned_needs_followup(
        ordered,
        committed_retest_ids=committed_retest_ids,
    ):
        status = "needs_followup"
        next_required_action = "resume_prescription"
    elif latest_status in {"assigned", "in_progress", "completed"}:
        status = latest_status
        next_required_action = "complete_verification_probe"
    else:
        status = "assigned"
        next_required_action = "complete_verification_probe"

    if status == "verified" and not evidence_refs:
        status = "not_verified"
        next_required_action = "complete_verification_probe"

    return {
        "training_intent_id": training_intent_id,
        "status": status,
        "prescription_phase": latest_phase,
        "score_ratio": score_ratio,
        "verified_at": verified_at if status == "verified" else "",
        "latest_event_at": str(getattr(latest, "created_at", "") or "").strip()
        if latest is not None
        else "",
        "evidence_refs": evidence_refs,
        "target_pack_id": target_pack_id,
        "concept_label": concept_label,
        "next_required_action": next_required_action,
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "degraded": False,
        },
    }


def _latest_grading_probe(
    events: list[Any],
    *,
    require_success: bool,
    committed_retest_ids: set[str],
) -> Any | None:
    for event in reversed(list(events or [])):
        if not str(getattr(event, "event_id", "") or "").strip():
            continue
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if str(payload.get("prescription_phase") or "").strip() != "verification_probe":
            continue
        source_feature = str(getattr(event, "source_feature", "") or "").strip()
        payload_source = str(payload.get("evidence_source") or "").strip()
        is_canonical_retest = is_canonical_luban_retest_terminal(event)
        completion_id = str(payload.get("retest_completion_id") or "").strip()
        if is_canonical_retest and completion_id not in committed_retest_ids:
            continue
        carries_retest_identity = bool(
            str(payload.get("retest_completion_id") or "").strip()
            or source_feature == "assessment_testset"
            or payload_source == "assessment_testset"
        )
        if carries_retest_identity and not is_canonical_retest:
            continue
        if not is_canonical_retest and (
            source_feature != "construction_grading"
            or payload_source not in {"", "construction_grading"}
        ):
            continue
        if _is_preview_or_simulated(payload):
            continue
        score_ratio = _score_ratio_value(
            _safe_dict(payload.get("prescription_result")).get(
                "score_ratio", payload.get("score_ratio")
            )
        )
        status = str(
            _safe_dict(payload.get("prescription_result")).get("status") or ""
        ).strip()
        success = status == "verified" or (
            score_ratio is not None and score_ratio >= 1.0
        )
        if success is require_success:
            return event
    return None


def _is_preview_or_simulated(payload: dict[str, Any]) -> bool:
    if payload.get("qa_simulated") is True or payload.get("preview_only") is True:
        return True
    if payload.get("claim_promotion_allowed") is False:
        return True
    return False


def _assigned_needs_followup(
    events: list[Any],
    *,
    committed_retest_ids: set[str],
) -> bool:
    assigned = [
        event
        for event in list(events or [])
        if str(
            _safe_dict(getattr(event, "payload_json", {})).get("prescription_phase")
            or ""
        ).strip()
        in {"", "assigned", "repair_root", "expression_drill", "transfer_case"}
    ]
    if not assigned:
        return False
    latest_probe = _latest_grading_probe(
        list(events or []),
        require_success=True,
        committed_retest_ids=committed_retest_ids,
    ) or _latest_grading_probe(
        list(events or []),
        require_success=False,
        committed_retest_ids=committed_retest_ids,
    )
    if latest_probe is not None:
        return False
    oldest_at = min(str(getattr(event, "created_at", "") or "") for event in assigned)
    parsed = _parse_iso(oldest_at)
    if parsed is None:
        return False
    return datetime.now(_TZ) - parsed >= timedelta(days=7)


def _score_ratio_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = ["build_prescription_outcomes_read_projection"]
