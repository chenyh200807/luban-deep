from __future__ import annotations

from typing import Any, Iterable

PRACTICE_EVIDENCE_SOURCE_FEATURES = frozenset(
    {"construction_grading", "assessment_testset"}
)
LEARNING_EVIDENCE_SOURCE_FEATURES = PRACTICE_EVIDENCE_SOURCE_FEATURES | frozenset(
    {"conversation_synthesis", "first_run_diagnostic"}
)


def is_learning_evidence_event(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    source = _clean(getattr(event, "source_feature", ""))
    if _clean(getattr(event, "memory_kind", "")) != "learning_evidence":
        return False
    if source not in LEARNING_EVIDENCE_SOURCE_FEATURES:
        return False
    return source == "construction_grading" or _clean(payload.get("event_type")) == "learning_evidence"


def evidence_attempt_id(event: Any, payload: dict[str, Any] | None = None) -> str:
    body = _safe_dict(payload if payload is not None else getattr(event, "payload_json", {}))
    for key in (
        "retest_completion_id",
        "completion_id",
        "attempt_id",
        "quiz_id",
        "form_id",
        "turn_id",
    ):
        value = _clean(body.get(key))
        if value:
            return value
    return _clean(getattr(event, "source_id", "")) or _clean(getattr(event, "event_id", ""))


def promotion_allowed(payload: dict[str, Any]) -> bool:
    quality = _safe_dict(payload.get("quality"))
    if payload.get("claim_promotion_allowed") is False:
        return False
    if payload.get("qa_simulated") is True or payload.get("preview_only") is True:
        return False
    if _is_low_confidence(payload.get("measurement_confidence")):
        return False
    if _is_low_confidence(quality.get("measurement_confidence")):
        return False
    if _clean(payload.get("practice_mode")).lower() == "forward":
        return False
    return True


def committed_retest_completion_ids(events: Iterable[Any]) -> set[str]:
    return {
        _clean(_safe_dict(getattr(event, "payload_json", {})).get("retest_completion_id"))
        for event in events
        if _safe_dict(getattr(event, "payload_json", {})).get("completion_terminal") is True
        and _clean(_safe_dict(getattr(event, "payload_json", {})).get("retest_completion_id"))
    }


def is_retest_completion_terminal(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return bool(
        payload.get("completion_terminal") is True
        and _clean(payload.get("retest_completion_id"))
    )


def event_promotion_allowed(
    event: Any,
    *,
    committed_retest_ids: set[str] | None = None,
) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if not promotion_allowed(payload):
        return False
    completion_id = _clean(payload.get("retest_completion_id"))
    if completion_id and payload.get("completion_terminal") is not True:
        return completion_id in set(committed_retest_ids or set())
    return True


def distinct_attempt_count(rows: Iterable[dict[str, Any]]) -> int:
    return len({_clean(row.get("attempt_id")) for row in rows if _clean(row.get("attempt_id"))})


def is_real_retest(payload: dict[str, Any]) -> bool:
    quality = _safe_dict(payload.get("quality"))
    return (
        _clean(payload.get("practice_mode")).lower() in {"review", "verification"}
        and _clean(quality.get("evidence_level")) == "L2_real_retest"
        and promotion_allowed(payload)
    )


def _is_low_confidence(value: Any) -> bool:
    if isinstance(value, dict):
        return _clean(value.get("level")).lower() == "low"
    return _clean(value).lower() == "low"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "LEARNING_EVIDENCE_SOURCE_FEATURES",
    "PRACTICE_EVIDENCE_SOURCE_FEATURES",
    "distinct_attempt_count",
    "committed_retest_completion_ids",
    "evidence_attempt_id",
    "event_promotion_allowed",
    "is_learning_evidence_event",
    "is_retest_completion_terminal",
    "is_real_retest",
    "promotion_allowed",
]
