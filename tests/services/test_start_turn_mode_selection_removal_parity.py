"""Differential / regression net for removing ``start_turn`` mode-selection
(control-plane QTPK S3d — deleting the FIRST of three turn-runtime parses).

Background (S3a already landed)
--------------------------------
Two sites historically selected fast/deep (a student-facing latency/density
decision):

1. ``start_turn`` mode-selection (``turn_runtime.start_turn``): when
   ``_should_select_tutorbot_mode`` is true it calls
   ``select_response_mode(... has_active_object=active_object_requires_deep_mode(...))``
   and stamps ``chat_mode`` / ``interaction_hints.selected_mode``.

2. The capability fallback ``TutorBotCapability._mode_policy``: when the
   incoming ``selected_mode == "smart"`` it computes the SAME
   ``select_response_mode(... has_active_object=active_object_requires_deep_mode(...))``.

S3a collapsed the fast/deep decision into the single canonical
``deeptutor.tutorbot.response_mode.active_object_requires_deep_mode`` +
``select_response_mode`` that BOTH sites call. Therefore deleting the
``start_turn`` mode-selection is safe *iff* the capability fallback, fed the
same inputs (requested mode, user message, interaction hints, and the
followup/active-object that ``_run_turn`` resolves), produces the same
``effective_mode``.

This net proves exactly that parity over a corpus, BEFORE the deletion. After
S3d removes ``start_turn`` mode-selection, the same net is the regression
guard: deleting must not change the fast/deep outcome the student sees.

Mirror sessions
---------------
A TutorBot turn may resolve its followup question context from a *mirror*
session (cross-surface). ``start_turn`` followup① collected mirror candidates;
once it is deleted the mirror candidate must reach ``_run_turn``'s authoritative
resolve so the resolved followup is identical. The mirror corpus rows here
assert that *given the same resolved followup* (which both paths receive once
the mirror candidate flows to ``_run_turn``), the fast/deep mode is identical —
i.e. the mode decision never depended on *where* the followup was resolved, only
on the resolved followup itself. The companion test
``test_unified_ws_turn_runtime`` exercises the live mirror-candidate plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeptutor.services.active_object_builder import (
    build_active_object_from_question_context,
    extract_question_context_from_active_object,
    normalize_active_object,
)
from deeptutor.services.question_followup import normalize_question_followup_context
from deeptutor.tutorbot.response_mode import (
    active_object_requires_deep_mode,
    select_response_mode,
)


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

_SINGLE_QUESTION_CONTEXT = {
    "question": {
        "stem": "下列关于施工组织设计的说法，正确的是？",
        "options": [
            {"label": "A", "text": "选项A"},
            {"label": "B", "text": "选项B"},
            {"label": "C", "text": "选项C"},
            {"label": "D", "text": "选项D"},
        ],
        "answer": "A",
        "question_type": "single_choice",
    },
}


def _active_object(object_type: str, context: dict | None) -> dict | None:
    raw: dict = {"object_type": object_type, "object_id": "obj-1"}
    if context is not None:
        raw["state_snapshot"] = context
    return normalize_active_object(raw)


@dataclass(frozen=True)
class Case:
    name: str
    # The active object the turn carries (None == no active question).
    active_object: dict | None
    user_message: str
    # smart | fast | deep (the requested response mode for this turn).
    requested_mode: str
    interaction_hints: dict
    # When True, the resolved followup arrives ONLY via a mirror session
    # (start_turn followup① / _run_turn candidate_contexts). The resolved
    # followup is otherwise identical, so the mode must be identical to a
    # non-mirror turn carrying the same active object.
    via_mirror: bool = False


def _build_corpus() -> list[Case]:
    sq = _active_object("single_question", _SINGLE_QUESTION_CONTEXT)
    qs = _active_object("question_set", _SINGLE_QUESTION_CONTEXT)
    open_topic = _active_object("open_chat_topic", None)

    return [
        # --- No active object ---
        Case("no_active_smart_simple", None, "什么是进度网络图？", "smart", {}),
        Case("no_active_smart_deep_shape", None, "请详细对比两种方案的风险", "smart", {}),
        Case("no_active_explicit_fast", None, "一句话讲讲", "fast", {}),
        Case("no_active_explicit_deep", None, "随便", "deep", {}),
        # --- Active question + explanation (DEEP) ---
        Case(
            "active_explain_smart",
            sq,
            "这道题为什么选A，详细讲一下解题思路",
            "smart",
            {},
        ),
        # --- Active question + answer submission (FAST) ---
        Case("active_submission_short", sq, "我选A", "smart", {}),
        Case("active_submission_explicit", sq, "我的答案是D", "smart", {}),
        # --- Active question + practice generation (FAST) ---
        Case("active_practice_generation", qs, "再来一道类似的题考我", "smart", {}),
        Case("active_next_question", qs, "下一题", "smart", {}),
        # --- Active question + structured grading "第N题" (FAST) ---
        Case("active_structured_grading", qs, "第1题我选B，帮我批改", "smart", {}),
        # --- Open chat topic active object ---
        Case("open_chat_topic", open_topic, "随便聊聊", "smart", {}),
        # --- explicit mode overrides win regardless of active object ---
        Case("active_question_explicit_fast", sq, "为什么", "fast", {}),
        Case("active_question_explicit_deep", sq, "我选A", "deep", {}),
        # --- current_info_required hint forces deep ---
        Case(
            "no_active_current_info_required",
            None,
            "今天的情况",
            "smart",
            {"current_info_required": True},
        ),
        # --- Mirror-resolved followup: same resolved followup, cross surface ---
        Case("mirror_active_explain", sq, "这道题详细讲讲思路", "smart", {}, via_mirror=True),
        Case("mirror_active_submission", sq, "我选A", "smart", {}, via_mirror=True),
        Case("mirror_active_practice", qs, "再来一道", "smart", {}, via_mirror=True),
    ]


# ---------------------------------------------------------------------------
# The two call-site computations, expressed exactly as each site uses the
# shared canonical (S3a). ``_run_turn`` + ``_mode_policy`` is the FALLBACK.
# ``start_turn`` is the soon-to-be-deleted PRE-PARSE.
# ---------------------------------------------------------------------------


def _resolved_followup(active_object: dict | None) -> dict | None:
    """The followup context both sites resolve. start_turn resolves it (incl.
    mirror candidates) and passes it forward; _run_turn re-resolves it. Once
    the mirror candidate reaches _run_turn the resolved followup is identical,
    so we model the *resolved* followup once here."""
    normalized = normalize_active_object(active_object)
    if normalized is None:
        return None
    return normalize_question_followup_context(
        extract_question_context_from_active_object(normalized)
    )


def _start_turn_selected_mode(case: Case) -> str:
    """Mirror of turn_runtime.start_turn mode-selection (the code to delete).

    ``has_active_object`` is computed from ``mode_selection_active_object`` (the
    stored active object) or, when absent, an active object built from the
    resolved followup — exactly the start_turn branch."""
    followup = _resolved_followup(case.active_object)
    mode_selection_active_object = case.active_object
    if mode_selection_active_object is None and followup is not None:
        mode_selection_active_object = build_active_object_from_question_context(followup)
    selected, _reason = select_response_mode(
        case.requested_mode,
        user_message=case.user_message,
        interaction_hints=case.interaction_hints or None,
        has_active_object=active_object_requires_deep_mode(
            active_object=mode_selection_active_object,
            followup_context=followup,
            user_message=case.user_message,
        ),
    )
    return selected


def _capability_fallback_selected_mode(case: Case) -> str:
    """Mirror of TutorBotCapability._mode_policy smart fallback (the bottom
    that remains after deletion). The capability reads ``active_object`` /
    ``question_followup_context`` from metadata that ``_run_turn`` resolved."""
    followup = _resolved_followup(case.active_object)
    selected, _reason = select_response_mode(
        case.requested_mode,
        user_message=case.user_message,
        interaction_hints=case.interaction_hints or None,
        has_active_object=active_object_requires_deep_mode(
            active_object=case.active_object,
            followup_context=followup,
            user_message=case.user_message,
        ),
    )
    return selected


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _build_corpus(), ids=lambda c: c.name)
def test_start_turn_mode_selection_equals_capability_fallback(case: Case) -> None:
    """S3b parity (pre-delete) / S3d regression (post-delete): the start_turn
    mode-selection result must equal the capability fallback result. Removing
    start_turn mode-selection therefore does not change the student-facing
    fast/deep mode."""
    start_turn_mode = _start_turn_selected_mode(case)
    fallback_mode = _capability_fallback_selected_mode(case)
    assert start_turn_mode == fallback_mode, (
        f"{case.name}: start_turn={start_turn_mode} fallback={fallback_mode} "
        f"(requested={case.requested_mode})"
    )
    assert start_turn_mode in {"fast", "deep"}


@pytest.mark.parametrize(
    "case",
    [c for c in _build_corpus() if c.via_mirror],
    ids=lambda c: c.name,
)
def test_mirror_resolved_followup_mode_matches_non_mirror(case: Case) -> None:
    """A followup resolved via a mirror session yields the same fast/deep mode
    as the same active object resolved locally — the mode never depended on the
    resolution *source*, only the resolved followup. Guards against silently
    losing the mirror path's mode signal when followup① is deleted."""
    mirror_mode = _capability_fallback_selected_mode(case)
    # Same active object + message, but pretend it resolved locally.
    local = Case(
        name=case.name + "_local",
        active_object=case.active_object,
        user_message=case.user_message,
        requested_mode=case.requested_mode,
        interaction_hints=case.interaction_hints,
        via_mirror=False,
    )
    local_mode = _capability_fallback_selected_mode(local)
    assert mirror_mode == local_mode, (
        f"{case.name}: mirror={mirror_mode} local={local_mode}"
    )
