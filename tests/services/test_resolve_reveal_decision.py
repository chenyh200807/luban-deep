"""Adversarial RED-first tests for the single reveal-decision authority.

Control-plane collapse Task 5 Slice 4 (reveal 3+1 → 1). The highest
answer-leak risk in the plan: the resolver MUST never reveal answers/explanations
when either hard red line holds:

  Rule 1 (preference is False)          — user said "先别给", suppresses everything.
  Rule 2 (is_unanswered_block)          — unanswered, non-conceding practice; anti-peek.

These two MUST out-prioritise review mode, preference=True, explicit markers and
overrides. ``resolve_reveal_decision`` is a PURE function: callers construct the
boolean facets, the resolver only adjudicates. This isolates the leak-critical
priority ladder from context shape.
"""

from __future__ import annotations

import pytest

from deeptutor.services.question_followup import (
    RevealDecision,
    resolve_reveal_decision,
)


# ---------------------------------------------------------------------------
# HARD RED LINES (highest priority — must compress everything below).
# ---------------------------------------------------------------------------
def test_case1_unanswered_plus_preference_true_blocks_reveal() -> None:
    """#1 RED-LINE FIX: unanswered + preference=True → (False, False).

    Old tutorbot._reveal_reference_flags returned (True, True) the instant
    preference was True, *before* the unanswered-block check — a direct answer
    leak on an un-attempted practice question. The resolver puts the
    unanswered-block red line ABOVE preference=True, so this can never leak.
    """
    decision = resolve_reveal_decision(
        preference=True,
        is_review=False,
        is_unanswered_block=True,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


def test_case2_review_plus_preference_false_blocks_reveal() -> None:
    """#2: review + preference=False → (False, False). Rule 1 > Rule 3.

    Owner-decided: an explicit "先别给答案" must win even inside review mode.
    """
    decision = resolve_reveal_decision(
        preference=False,
        is_review=True,
        is_unanswered_block=False,
        overrides_reveal=True,
        context_reveal_flags=True,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


def test_case4_pasted_unanswered_solve_request_blocks_reveal() -> None:
    """#4: pasted unanswered question asking for the solution → (False, False)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=True,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


def test_case5_answered_plus_preference_false_blocks_reveal() -> None:
    """#5: answered + preference=False → (False, False). Rule 1 compresses."""
    decision = resolve_reveal_decision(
        preference=False,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=True,
        context_reveal_flags=True,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


# ---------------------------------------------------------------------------
# LEGITIMATE REVEALS.
# ---------------------------------------------------------------------------
def test_case6_unanswered_concession_reveals() -> None:
    """#6: unanswered + concession ("我放弃") + answer request → (True, True).

    Concession clears the unanswered-block (is_unanswered_block=False), so
    preference=True legitimately reveals.
    """
    decision = resolve_reveal_decision(
        preference=True,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_case3_answered_explicit_marker_reveals() -> None:
    """#3: answered + explicit request marker → (True, True)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_case7_multi_question_second_item_answered_reveals() -> None:
    """#7: multi-question, item-2 answered, asking about it → (True, True).

    The caller resolves the per-item attempt to is_unanswered_block=False, so a
    plain explicit request reveals.
    """
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=True,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_case8_question_bank_context_reveal_flags_reveals() -> None:
    """#8: question-bank already carries reveal flags → (True, True)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=True,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_case9_unanswered_plain_followup_no_marker_blocks() -> None:
    """#9: unanswered + plain follow-up, no marker → (False, False)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=True,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


# ---------------------------------------------------------------------------
# PRIORITY LADDER coverage (rules 3-8) beyond the 9 named cases.
# ---------------------------------------------------------------------------
def test_review_mode_reveals_both() -> None:
    """Rule 3: review mode (no red line) → (True, True)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=True,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_preference_true_reveals_when_not_blocked() -> None:
    """Rule 4: preference=True with no red line → (True, True)."""
    decision = resolve_reveal_decision(
        preference=True,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_overrides_reveal_true_honours_explanations_override() -> None:
    """Rule 7: overrides_reveal=True with explanations override=False → (True, False)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=True,
        context_reveal_flags=False,
        explicit_request=False,
        overrides_reveal_explanations=False,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=False)


def test_overrides_reveal_true_defaults_explanations_to_answers() -> None:
    """Rule 7: overrides_reveal=True, no explicit explanations override → mirrors answers."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=True,
        context_reveal_flags=False,
        explicit_request=False,
        overrides_reveal_explanations=None,
    )
    assert decision == RevealDecision(reveal_answers=True, reveal_explanations=True)


def test_default_blocks_reveal() -> None:
    """Rule 8: no signal at all → (False, False)."""
    decision = resolve_reveal_decision(
        preference=None,
        is_review=False,
        is_unanswered_block=False,
        overrides_reveal=None,
        context_reveal_flags=False,
        explicit_request=False,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


@pytest.mark.parametrize(
    "is_review,overrides_reveal,context_reveal_flags,explicit_request",
    [
        (True, True, True, True),
        (False, True, True, True),
        (True, False, False, False),
    ],
)
def test_preference_false_is_absolute_red_line(
    is_review: bool,
    overrides_reveal: bool,
    context_reveal_flags: bool,
    explicit_request: bool,
) -> None:
    """Red line 1: preference=False compresses EVERY lower-priority reveal signal."""
    decision = resolve_reveal_decision(
        preference=False,
        is_review=is_review,
        is_unanswered_block=False,
        overrides_reveal=overrides_reveal,
        context_reveal_flags=context_reveal_flags,
        explicit_request=explicit_request,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)


@pytest.mark.parametrize(
    "is_review,preference,overrides_reveal,context_reveal_flags,explicit_request",
    [
        (True, True, True, True, True),
        (False, True, True, True, True),
        (True, None, True, True, True),
    ],
)
def test_unanswered_block_is_absolute_red_line(
    is_review: bool,
    preference: bool | None,
    overrides_reveal: bool,
    context_reveal_flags: bool,
    explicit_request: bool,
) -> None:
    """Red line 2: is_unanswered_block compresses review/preference=True/overrides/explicit."""
    decision = resolve_reveal_decision(
        preference=preference,
        is_review=is_review,
        is_unanswered_block=True,
        overrides_reveal=overrides_reveal,
        context_reveal_flags=context_reveal_flags,
        explicit_request=explicit_request,
    )
    assert decision == RevealDecision(reveal_answers=False, reveal_explanations=False)
