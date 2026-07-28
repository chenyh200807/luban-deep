from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from deeptutor.services.learner_state.event_identity import canonical_event_id

PRACTICE_EVIDENCE_SOURCE_FEATURES = frozenset(
    {"construction_grading", "assessment_testset"}
)
LEARNING_EVIDENCE_SOURCE_FEATURES = PRACTICE_EVIDENCE_SOURCE_FEATURES | frozenset(
    {"conversation_synthesis", "first_run_diagnostic"}
)
LIFECYCLE_EVIDENCE_SOURCE_FEATURES = LEARNING_EVIDENCE_SOURCE_FEATURES | frozenset(
    {"luban_lesson"}
)


def is_learning_evidence_record(event: Any) -> bool:
    """Return whether a row belongs to the learner-evidence read stream.

    This is deliberately broader than promotion eligibility: non-promoting
    facts such as ``luban_lesson`` exposure still have to reach lifecycle read
    models, while control rows such as ``retest_completion_claim`` must not.
    """
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if _clean(getattr(event, "memory_kind", "")) != "learning_evidence":
        return False
    source = _clean(getattr(event, "source_feature", ""))
    if source not in LIFECYCLE_EVIDENCE_SOURCE_FEATURES:
        return False
    if source == "construction_grading":
        return True
    return _clean(payload.get("event_type")) == "learning_evidence"


def is_learning_evidence_event(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    source = _clean(getattr(event, "source_feature", ""))
    if not is_learning_evidence_record(event):
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
    by_event_id, duplicate_event_ids = _event_index(events)
    return _canonical_retest_item_events_from_index(
        terminal=terminal,
        by_event_id=by_event_id,
        duplicate_event_ids=duplicate_event_ids,
    )


def _canonical_retest_item_events_from_index(
    *,
    terminal: Any,
    by_event_id: dict[str, Any],
    duplicate_event_ids: set[str],
) -> tuple[Any, ...] | None:
    if not is_canonical_luban_retest_terminal(terminal):
        return None
    terminal_payload = _safe_dict(getattr(terminal, "payload_json", {}))
    completion_id = _clean(terminal_payload.get("retest_completion_id"))
    request_hash = _clean(terminal_payload.get("request_hash"))
    pack_id = _clean(terminal_payload.get("pack_id")).upper()
    mode = _clean(terminal_payload.get("practice_mode")).lower()
    request_hash_version = _whole_number(terminal_payload.get("request_hash_version"))
    probe_id = _clean(terminal_payload.get("probe_id"))
    cycle_anchor = canonical_event_id(terminal_payload.get("cycle_anchor"))
    item_refs = [
        canonical_event_id(item)
        for item in list(terminal_payload.get("item_event_refs") or [])
    ]
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
                    and canonical_event_id(payload.get("cycle_anchor")) == cycle_anchor
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
    by_event_id, duplicate_event_ids = _event_index(event_list)
    closure: dict[str, tuple[str, ...]] = {}
    invalid_completions: set[str] = set()
    for terminal in event_list:
        if not is_canonical_luban_retest_terminal(terminal):
            continue
        payload = _safe_dict(getattr(terminal, "payload_json", {}))
        completion_id = _clean(payload.get("retest_completion_id"))
        item_events = _canonical_retest_item_events_from_index(
            terminal=terminal,
            by_event_id=by_event_id,
            duplicate_event_ids=duplicate_event_ids,
        )
        if not completion_id or item_events is None or completion_id in closure:
            invalid_completions.add(completion_id)
            closure.pop(completion_id, None)
            continue
        closure[completion_id] = tuple(
            canonical_event_id(getattr(event, "event_id", "")) for event in item_events
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


def is_progress_countable_event(event: Any) -> bool:
    """Whether an evidence row counts as one learner attempt for progress numbers.

    Single authority for "does this row move today_done / total_attempts".
    Both the learning report read model and the PROGRESS counter projection
    read this one predicate — they must never drift apart.
    """
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if is_retest_completion_terminal(event):
        return False
    if _clean(payload.get("evidence_source")) == "conversation_synthesis":
        return False
    quality = _safe_dict(payload.get("quality"))
    if quality.get("progress_countable") is False:
        return False
    return True


RETEST_ROLE_FORWARD_PRACTICE = "forward_practice"
RETEST_ROLE_IMMEDIATE_CONFIRM = "immediate_confirm"
RETEST_ROLE_REVIEW = "review"
EPISODE_BINDING_EXACT = "exact"
EPISODE_BINDING_LEGACY = "legacy_compatible"
EPISODE_BINDING_LEGACY_UNBOUND = "legacy_unbound"
EPISODE_BINDING_UNBOUND = "unbound"


@dataclass(frozen=True)
class CanonicalRetestEpisodeRecord:
    """One validated closure plus its binding to a forward practice episode."""

    terminal: Any
    items: tuple[Any, ...]
    pack_id: str
    role: str
    episode_id: str
    binding: str


def canonical_retest_completion_role(
    events: Iterable[Any], *, terminal: Any
) -> str:
    """Classify one committed Luban terminal from its canonical item closure.

    ``practice_mode=forward`` is intentionally insufficient: immediate-confirm
    uses the same transport mode but must not open a new learning/review cycle.
    The signed ``cycle_anchor`` and sealed item roles jointly define the episode:
    an empty anchor restores only the known historical selector bug shape (at
    least one anchor plus known sub-step roles); homogeneous confirm remains a
    confirm and must bind to a parent later; unknown/blank roles fail closed.
    """
    if not is_canonical_luban_retest_terminal(terminal):
        return ""
    items = canonical_retest_item_events(events, terminal=terminal)
    if items is None:
        return ""
    return _canonical_retest_role_from_items(terminal=terminal, items=items)


def _canonical_retest_role_from_items(*, terminal: Any, items: Iterable[Any]) -> str:
    payload = _safe_dict(getattr(terminal, "payload_json", {}))
    mode = _clean(payload.get("practice_mode")).lower()
    if mode == "review":
        return RETEST_ROLE_REVIEW
    if mode != "forward":
        return ""
    raw_roles = [
        _clean(_safe_dict(getattr(item, "payload_json", {})).get("probe_role"))
        for item in items
    ]
    if not raw_roles:
        return ""
    cycle_anchor = canonical_event_id(payload.get("cycle_anchor"))
    if any(not role for role in raw_roles):
        return ""
    roles = set(raw_roles)
    if roles == {RETEST_ROLE_IMMEDIATE_CONFIRM}:
        return RETEST_ROLE_IMMEDIATE_CONFIRM
    recoverable_forward_roles = {
        "anchor",
        RETEST_ROLE_IMMEDIATE_CONFIRM,
        "d1_probe",
    }
    if (
        not cycle_anchor
        and "anchor" in roles
        and roles.issubset(recoverable_forward_roles)
    ):
        return RETEST_ROLE_FORWARD_PRACTICE
    return ""


def canonical_retest_episode_records(
    events: Iterable[Any],
) -> tuple[CanonicalRetestEpisodeRecord, ...]:
    """Validate closures once and bind sub-steps to one canonical episode.

    Modern review terminals must carry the exact current ``cycle_anchor``.
    Immediate-confirm terminals must contain only facts that were wrong in the
    current forward closure.  Pre-v3 review rows retain an explicit legacy
    compatibility path only inside a pre-v3 chronological episode; they can
    never attach to a modern episode.
    """
    event_list = list(events or [])
    closure = committed_retest_closure(event_list)
    by_event_id = {
        canonical_event_id(getattr(event, "event_id", "")): event
        for event in event_list
        if canonical_event_id(getattr(event, "event_id", ""))
    }
    ordered_terminals = sorted(
        (
            event
            for event in event_list
            if is_canonical_luban_retest_terminal(event)
            and _clean(
                _safe_dict(getattr(event, "payload_json", {})).get(
                    "retest_completion_id"
                )
            )
            in closure
        ),
        key=lambda event: (
            _clean(getattr(event, "created_at", "")),
            canonical_event_id(getattr(event, "event_id", "")),
        ),
    )
    state_by_pack: dict[str, dict[str, Any]] = {}
    records: list[CanonicalRetestEpisodeRecord] = []
    for terminal in ordered_terminals:
        payload = _safe_dict(getattr(terminal, "payload_json", {}))
        completion_id = _clean(payload.get("retest_completion_id"))
        items = tuple(by_event_id[item_id] for item_id in closure[completion_id])
        pack_id = _clean(payload.get("pack_id")).upper()
        role = _canonical_retest_role_from_items(terminal=terminal, items=items)
        terminal_id = canonical_event_id(getattr(terminal, "event_id", "")) or completion_id
        version = _whole_number(payload.get("request_hash_version"))
        state = state_by_pack.get(pack_id)
        episode_id = ""
        binding = EPISODE_BINDING_UNBOUND

        if role == RETEST_ROLE_FORWARD_PRACTICE:
            wrong_facts = {
                _clean(_safe_dict(getattr(item, "payload_json", {})).get("fact_id"))
                for item in items
                if _safe_dict(getattr(item, "payload_json", {})).get("is_correct")
                is False
            }
            wrong_facts.discard("")
            state = {
                "episode_id": terminal_id,
                "current_anchor": terminal_id,
                "wrong_facts": wrong_facts,
                "legacy_compatible": version != 3,
            }
            state_by_pack[pack_id] = state
            episode_id = terminal_id
            binding = EPISODE_BINDING_EXACT
        elif role == RETEST_ROLE_IMMEDIATE_CONFIRM:
            confirm_facts = {
                _clean(_safe_dict(getattr(item, "payload_json", {})).get("fact_id"))
                for item in items
            }
            confirm_facts.discard("")
            parent_anchor = canonical_event_id(payload.get("cycle_anchor"))
            if (
                state is not None
                and parent_anchor == str(state.get("episode_id") or "")
                and confirm_facts
                and confirm_facts.issubset(set(state.get("wrong_facts") or set()))
            ):
                episode_id = str(state["episode_id"])
                binding = EPISODE_BINDING_EXACT
        elif role == RETEST_ROLE_REVIEW:
            cycle_anchor = canonical_event_id(payload.get("cycle_anchor"))
            if version == 3:
                if state is not None and cycle_anchor == str(state["current_anchor"]):
                    episode_id = str(state["episode_id"])
                    binding = EPISODE_BINDING_EXACT
                    state["current_anchor"] = terminal_id
                    state["legacy_compatible"] = False
            elif state is not None and state.get("legacy_compatible") is True:
                episode_id = str(state["episode_id"])
                binding = EPISODE_BINDING_LEGACY
                state["current_anchor"] = terminal_id
            elif state is None:
                # Historical review-only evidence remains visible to cadence
                # readers, but has no authority to complete a six-step episode.
                binding = EPISODE_BINDING_LEGACY_UNBOUND

        records.append(
            CanonicalRetestEpisodeRecord(
                terminal=terminal,
                items=items,
                pack_id=pack_id,
                role=role,
                episode_id=episode_id,
                binding=binding,
            )
        )
    return tuple(records)


def validate_immediate_confirm_parent(
    events: Iterable[Any],
    *,
    pack_id: str,
    parent_terminal_id: str,
    fact_ids: Iterable[str],
) -> bool:
    """Validate an immediate-confirm request against the latest forward episode.

    The client may carry a terminal id as an opaque receipt, but only this
    canonical evidence reader may decide whether it is still the current
    parent and whether every requested fact was actually wrong in that closure.
    """
    normalized_pack = _clean(pack_id).upper()
    normalized_parent = canonical_event_id(parent_terminal_id)
    requested_facts = {_clean(fact_id) for fact_id in fact_ids}
    requested_facts.discard("")
    if not normalized_pack or not normalized_parent or not requested_facts:
        return False
    forward_records = [
        record
        for record in canonical_retest_episode_records(events)
        if record.pack_id == normalized_pack
        and record.role == RETEST_ROLE_FORWARD_PRACTICE
        and record.binding == EPISODE_BINDING_EXACT
    ]
    if not forward_records:
        return False
    parent = forward_records[-1]
    parent_id = canonical_event_id(getattr(parent.terminal, "event_id", ""))
    if parent_id != normalized_parent:
        return False
    wrong_facts = {
        _clean(_safe_dict(getattr(item, "payload_json", {})).get("fact_id"))
        for item in parent.items
        if _safe_dict(getattr(item, "payload_json", {})).get("is_correct") is False
    }
    wrong_facts.discard("")
    return requested_facts.issubset(wrong_facts)


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
                    and canonical_event_id(payload.get("cycle_anchor"))
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
        return canonical_event_id(getattr(event, "event_id", "")) in {
            canonical_event_id(item_id)
            for item_id in set(committed_retest_item_ids or set())
        }
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


def _event_index(events: Iterable[Any]) -> tuple[dict[str, Any], set[str]]:
    by_event_id: dict[str, Any] = {}
    duplicate_event_ids: set[str] = set()
    for event in events:
        event_id = canonical_event_id(getattr(event, "event_id", ""))
        if not event_id:
            continue
        if event_id in by_event_id:
            duplicate_event_ids.add(event_id)
        by_event_id[event_id] = event
    return by_event_id, duplicate_event_ids


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
    "CanonicalRetestEpisodeRecord",
    "EPISODE_BINDING_EXACT",
    "EPISODE_BINDING_LEGACY",
    "EPISODE_BINDING_LEGACY_UNBOUND",
    "EPISODE_BINDING_UNBOUND",
    "LEARNING_EVIDENCE_SOURCE_FEATURES",
    "LIFECYCLE_EVIDENCE_SOURCE_FEATURES",
    "PRACTICE_EVIDENCE_SOURCE_FEATURES",
    "RETEST_ROLE_FORWARD_PRACTICE",
    "RETEST_ROLE_IMMEDIATE_CONFIRM",
    "RETEST_ROLE_REVIEW",
    "canonical_retest_completion_role",
    "canonical_retest_episode_records",
    "canonical_retest_item_events",
    "committed_retest_closure",
    "distinct_attempt_count",
    "committed_retest_completion_ids",
    "committed_retest_item_event_ids",
    "evidence_attempt_id",
    "event_promotion_allowed",
    "is_learning_evidence_event",
    "is_learning_evidence_record",
    "is_progress_countable_event",
    "is_retest_completion_terminal",
    "is_canonical_luban_retest_terminal",
    "is_real_retest",
    "promotion_allowed",
    "validate_immediate_confirm_parent",
]
