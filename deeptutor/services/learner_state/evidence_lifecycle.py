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


def is_signed_luban_retest_terminal(event: Any) -> bool:
    """Recognize the canonical terminal emitted by Luban retest writeback.

    The generic terminal marker is insufficient for pack cadence: a foreign
    learning-evidence row must not move a pack clock by copying a boolean and
    an authority label.
    """
    payload = _safe_dict(getattr(event, "payload_json", {}))
    quality = _safe_dict(payload.get("quality"))
    result = _safe_dict(payload.get("prescription_result"))
    completion_id = _clean(payload.get("retest_completion_id"))
    mode = _clean(payload.get("practice_mode")).lower()
    pack_id = _clean(payload.get("pack_id")).upper()
    target_pack_id = _clean(payload.get("target_pack_id")).upper()
    expected_assessment = f"luban_{mode}_completion" if mode in {"forward", "review"} else ""
    expected_statuses = {"not_verified"} if mode == "forward" else {"verified", "not_verified"}
    expected_confidence = "medium" if mode == "forward" else "high"
    expected_evidence_level = "L0_observed" if mode == "forward" else "L2_real_retest"
    return bool(
        _clean(getattr(event, "source_feature", "")) == "assessment_testset"
        and _clean(getattr(event, "memory_kind", "")) == "learning_evidence"
        and _clean(getattr(event, "source_id", "")) == f"{completion_id}:terminal"
        and _clean(payload.get("event_type")) == "learning_evidence"
        and _clean(payload.get("evidence_source")) == "assessment_testset"
        and payload.get("completion_terminal") is True
        and completion_id
        and expected_assessment
        and _clean(payload.get("assessment_type")) == expected_assessment
        and pack_id
        and pack_id == target_pack_id
        and _clean(quality.get("authority")) == "signed_variant_server_rescore"
        and quality.get("writeback_eligible") is True
        and _clean(quality.get("measurement_confidence")).lower() == expected_confidence
        and _clean(quality.get("evidence_level")) == expected_evidence_level
        and _clean(result.get("status")) in expected_statuses
        and payload.get("claim_promotion_allowed") is (mode == "review")
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
    "is_signed_luban_retest_terminal",
    "is_real_retest",
    "promotion_allowed",
]
