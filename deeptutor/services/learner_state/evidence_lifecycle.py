from __future__ import annotations

import math
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


def canonical_retest_item_events(
    events: Iterable[Any],
    *,
    terminal: Any,
) -> tuple[Any, ...] | None:
    """Validate and return the exact item set sealed by one retest terminal.

    A completion id is only a correlation key.  The commit certificate is the
    canonical terminal plus its ordered ``item_event_refs`` closure: every
    referenced item must belong to the same request, completion, mode and pack,
    and the item totals must reproduce the terminal score.
    """
    if not is_canonical_luban_retest_terminal(terminal):
        return None
    terminal_payload = _safe_dict(getattr(terminal, "payload_json", {}))
    completion_id = _clean(terminal_payload.get("retest_completion_id"))
    request_hash = _clean(terminal_payload.get("request_hash"))
    pack_id = _clean(terminal_payload.get("pack_id")).upper()
    mode = _clean(terminal_payload.get("practice_mode")).lower()
    request_hash_version = _whole_number(terminal_payload.get("request_hash_version"))
    probe_id = _clean(terminal_payload.get("probe_id"))
    cycle_anchor = _clean(terminal_payload.get("cycle_anchor"))
    item_refs = [_clean(item) for item in list(terminal_payload.get("item_event_refs") or [])]
    question_count = _whole_number(terminal_payload.get("max_score"))
    score_awarded = _number(terminal_payload.get("score_awarded"))
    if (
        not completion_id
        or not request_hash
        or question_count is None
        or question_count <= 0
        or score_awarded is None
        or len(item_refs) != question_count
        or any(not item for item in item_refs)
        or len(set(item_refs)) != question_count
    ):
        return None

    by_event_id: dict[str, Any] = {}
    duplicate_event_ids: set[str] = set()
    for event in events:
        event_id = _clean(getattr(event, "event_id", ""))
        if not event_id:
            continue
        if event_id in by_event_id:
            duplicate_event_ids.add(event_id)
        by_event_id[event_id] = event
    if duplicate_event_ids.intersection(item_refs):
        return None

    item_events = tuple(by_event_id.get(event_id) for event_id in item_refs)
    if any(event is None for event in item_events):
        return None
    for event in item_events:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if not (
            _clean(getattr(event, "source_feature", "")) == "assessment_testset"
            and _clean(getattr(event, "memory_kind", "")) == "learning_evidence"
            and _clean(payload.get("event_type")) == "learning_evidence"
            and payload.get("completion_terminal") is not True
            and _clean(payload.get("retest_completion_id")) == completion_id
            and _clean(payload.get("request_hash")) == request_hash
            and _clean(payload.get("pack_id")).upper() == pack_id
            and _clean(payload.get("target_pack_id")).upper() == pack_id
            and _clean(payload.get("practice_mode")).lower() == mode
            and (
                request_hash_version != 3
                or (
                    _whole_number(payload.get("request_hash_version")) == 3
                    and _clean(payload.get("probe_id")) == probe_id
                    and _clean(payload.get("cycle_anchor")) == cycle_anchor
                )
            )
        ):
            return None

    item_scores = [
        _number(
            _safe_dict(getattr(event, "payload_json", {})).get("score_awarded")
        )
        for event in item_events
    ]
    item_max_scores = [
        _number(_safe_dict(getattr(event, "payload_json", {})).get("max_score"))
        for event in item_events
    ]
    item_correctness = [
        _safe_dict(getattr(event, "payload_json", {})).get("is_correct")
        for event in item_events
    ]
    if (
        any(value not in {0.0, 1.0} for value in item_scores)
        or any(value != 1.0 for value in item_max_scores)
        or any(not isinstance(value, bool) for value in item_correctness)
        or any(
            item_correctness[index] is not (item_scores[index] == 1.0)
            for index in range(len(item_events))
        )
    ):
        return None
    item_score = sum(value for value in item_scores if value is not None)
    item_max_score = sum(value for value in item_max_scores if value is not None)
    correct_count = sum(value is True for value in item_correctness)
    if (
        item_score != score_awarded
        or item_max_score != float(question_count)
        or float(correct_count) != score_awarded
    ):
        return None
    return item_events


def committed_retest_closure(events: Iterable[Any]) -> dict[str, tuple[str, ...]]:
    """Return completion -> ordered item ids for fully closed retests only."""
    event_list = list(events)
    closure: dict[str, tuple[str, ...]] = {}
    invalid_completions: set[str] = set()
    for terminal in event_list:
        if not is_canonical_luban_retest_terminal(terminal):
            continue
        payload = _safe_dict(getattr(terminal, "payload_json", {}))
        completion_id = _clean(payload.get("retest_completion_id"))
        item_events = canonical_retest_item_events(event_list, terminal=terminal)
        if not completion_id or item_events is None or completion_id in closure:
            invalid_completions.add(completion_id)
            closure.pop(completion_id, None)
            continue
        closure[completion_id] = tuple(
            _clean(getattr(event, "event_id", "")) for event in item_events
        )
    for completion_id in invalid_completions:
        closure.pop(completion_id, None)
    return closure


def committed_retest_item_event_ids(events: Iterable[Any]) -> set[str]:
    return {
        event_id
        for item_refs in committed_retest_closure(events).values()
        for event_id in item_refs
    }


def committed_retest_completion_ids(events: Iterable[Any]) -> set[str]:
    """Return completion ids backed by a fully validated terminal closure."""
    return set(committed_retest_closure(events))


def is_retest_completion_terminal(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return bool(
        payload.get("completion_terminal") is True
        and _clean(payload.get("retest_completion_id"))
    )


def is_canonical_luban_retest_terminal(event: Any) -> bool:
    """Recognize a canonical terminal emitted by Luban retest writeback.

    The generic terminal marker is insufficient for pack cadence: a foreign
    learning-evidence row must not move a pack clock by copying a boolean.
    Compiled HTML is accepted only for forward L0 practice; review remains
    signed-variant L2 evidence.
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
    allowed_authorities = {
        "forward": {"signed_variant_server_rescore", "compiled_html_server_rescore"},
        "review": {"signed_variant_server_rescore", "compiled_html_server_rescore"},
    }
    request_hash = _clean(payload.get("request_hash"))
    request_hash_version = _whole_number(payload.get("request_hash_version"))
    v3_identity_valid = bool(
        request_hash_version != 3
        or (
            len(request_hash) == 64
            and all(character in "0123456789abcdef" for character in request_hash)
            and (
                mode == "forward"
                or (
                    _clean(payload.get("probe_id"))
                    and _clean(payload.get("cycle_anchor"))
                )
            )
        )
    )
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
        and _clean(quality.get("authority")) in allowed_authorities.get(mode, set())
        and quality.get("writeback_eligible") is True
        and _clean(quality.get("measurement_confidence")).lower() == expected_confidence
        and _clean(quality.get("evidence_level")) == expected_evidence_level
        and _clean(result.get("status")) in expected_statuses
        and payload.get("claim_promotion_allowed") is (mode == "review")
        and v3_identity_valid
    )


def event_promotion_allowed(
    event: Any,
    *,
    committed_retest_item_ids: set[str] | None = None,
) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if not promotion_allowed(payload):
        return False
    completion_id = _clean(payload.get("retest_completion_id"))
    if completion_id and payload.get("completion_terminal") is not True:
        return _clean(getattr(event, "event_id", "")) in set(
            committed_retest_item_ids or set()
        )
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


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _whole_number(value: Any) -> int | None:
    number = _number(value)
    if number is None or number != int(number):
        return None
    return int(number)


__all__ = [
    "LEARNING_EVIDENCE_SOURCE_FEATURES",
    "PRACTICE_EVIDENCE_SOURCE_FEATURES",
    "canonical_retest_item_events",
    "committed_retest_closure",
    "distinct_attempt_count",
    "committed_retest_completion_ids",
    "committed_retest_item_event_ids",
    "evidence_attempt_id",
    "event_promotion_allowed",
    "is_learning_evidence_event",
    "is_retest_completion_terminal",
    "is_canonical_luban_retest_terminal",
    "is_real_retest",
    "promotion_allowed",
]
