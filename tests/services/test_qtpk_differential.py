"""QTPK differential parity net (QTPK physical extraction plan, S0).

This is the safety net that makes the S1-S5 physical moves *zero-behavior*: for
the same input, the legacy ``turn_runtime`` resolution path and the future
``resolve_turn_policy`` (QTPK) path must produce identical question-turn facts.

S0 scope — this file establishes the scaffold:

  * ``_baseline_followup`` calls the **existing** ``turn_runtime`` path
    (``_resolve_question_followup_context_and_action``) so the parity baseline is
    pinned to real production behavior (a parity-net nucleus, asserting the
    existing path is stable for the corpus inputs).
  * ``test_qtpk_matches_legacy_followup`` is the differential assertion. It is
    skipped until S1 implements ``resolve_turn_policy`` (which raises
    ``NotImplementedError`` in S0). When S1 lands, drop the skip and assert the
    candidate (QTPK) envelope equals the baseline tuple.

When S1 fills ``resolve_turn_policy``, remove the ``@pytest.mark.skip`` and wire
the candidate call (commented below). The corpus is intentionally small in S0;
S2-S5 expand it with the E8 套题 / 回指 hard-corpus cases the plan §6 SEV-1
safety belt requires.
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.question_turn_policy import (
    TurnPolicyDecision,
    resolve_turn_policy,
)
from deeptutor.services.session.turn_runtime import (
    _resolve_question_followup_context_and_action,
)

# ---------------------------------------------------------------------------
# Differential corpus: same input fed to legacy path and (future) QTPK path.
# Each case is (label, kwargs-for-the-followup-resolver).
# ---------------------------------------------------------------------------
_FOLLOWUP_CORPUS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "answer_with_stored_context",
        {
            "user_message": "我选 A",
            "explicit_context": {
                "items": [{"index": 1, "options": ["A", "B", "C", "D"]}],
                "correct_answer": "A",
                "explanation": "基层应平整、干净、含水率符合要求。",
            },
            "explicit_action": {
                "intent": "answer_questions",
                "answers": [{"index": 1, "user_answer": "A"}],
            },
            "candidate_contexts": (),
        },
    ),
    (
        "no_explicit_context_plain_message",
        {
            "user_message": "这道题怎么做",
            "explicit_context": None,
            "explicit_action": None,
            "candidate_contexts": (),
        },
    ),
)


async def _baseline_followup(
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Legacy ``turn_runtime`` followup resolution — the parity baseline."""
    return await _resolve_question_followup_context_and_action(**kwargs)


# ---------------------------------------------------------------------------
# Parity-net nucleus: the legacy path is deterministic / stable for the corpus.
# This protects the baseline itself before S1 wires the candidate.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("label,kwargs", _FOLLOWUP_CORPUS, ids=lambda v: v if isinstance(v, str) else "")
async def test_legacy_followup_path_is_stable(label: str, kwargs: dict[str, Any]) -> None:
    first = await _baseline_followup(kwargs)
    second = await _baseline_followup(kwargs)
    assert first == second, f"legacy followup path is non-deterministic for {label!r}"


# ---------------------------------------------------------------------------
# S1: resolve_turn_policy is now a partial forwarder over the physically-moved
# submission resolver — it returns a TurnPolicyDecision (no longer a stub).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_turn_policy_returns_decision_in_s1() -> None:
    decision = await resolve_turn_policy(
        user_message="这道题怎么做",
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=(),
    )
    assert isinstance(decision, TurnPolicyDecision)
    # S1 forwards ONLY the submission intent + evidence fact; the other four
    # facts stay at their empty envelope defaults until the S2+ full assembly.
    assert decision.active_object is None
    assert decision.turn_semantic_decision is None
    assert decision.lifecycle_scene is None
    assert decision.scene_decision is None


def test_turn_policy_decision_is_frozen_envelope() -> None:
    decision = TurnPolicyDecision()
    assert decision.active_object is None
    assert decision.suspended_object_stack == []
    assert decision.turn_semantic_decision is None
    assert decision.question_followup_context is None
    assert decision.question_followup_action is None
    assert decision.lifecycle_scene is None
    assert decision.scene_decision is None
    with pytest.raises(Exception):
        decision.active_object = {"changed": True}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The differential assertion — enabled in S1 now that resolve_turn_policy
# forwards the physically-moved submission resolver. The baseline path
# (``turn_runtime._resolve_question_followup_context_and_action``) is now the
# import-back of the QTPK-owned function, so this asserts the QTPK envelope
# carries the same submission intent + evidence the pre-move turn_runtime path
# produced for the corpus inputs (zero-behavior parity).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("label,kwargs", _FOLLOWUP_CORPUS, ids=lambda v: v if isinstance(v, str) else "")
async def test_qtpk_matches_legacy_followup(label: str, kwargs: dict[str, Any]) -> None:
    baseline_context, baseline_action = await _baseline_followup(kwargs)

    candidate: TurnPolicyDecision = await resolve_turn_policy(**kwargs)
    assert candidate.question_followup_context == baseline_context
    assert candidate.question_followup_action == baseline_action
