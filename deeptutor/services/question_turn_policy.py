"""Question-Turn Policy Kernel (QTPK) — physical home of question-turn policy.

This module is the single physical place that will own the five question-turn
facts of the unified ``/api/v1/ws`` path:

  1. ``question_lifecycle_scene`` — the lifecycle scene of the turn.
  2. ``turn_semantic_decision`` — relation + next_action (suspend/resume/demote).
  3. submission **intent + evidence** — what the learner submitted, with span.
  4. **current object identity** — which active object the turn is about.
  5. **active-object patch** — the suspend/resume/demote transition applied.

QTPK does NOT reimplement any of those facts. It is a *read-only forwarder* over
the already-canonical resolvers, collapsing the policy that is currently parsed
three times (``turn_runtime.start_turn`` mode-selection, ``turn_runtime._run_turn``
authoritative restore, and ``orchestrator._resolve_semantic_routing``) into one
resolution. The canonical resolvers it forwards to (and never re-derives):

  * ``deeptutor.services.semantic_router.resolve_question_semantic_routing``
    — relation/submission semantic decision.
  * ``deeptutor.services.semantic_router.apply_active_object_transition``
    — the suspend/resume/demote canonical (active-object patch).
  * ``deeptutor.services.question_lifecycle_skills.resolve_question_lifecycle_scene_decision``
    — lifecycle scene canonical.
  * ``deeptutor.services.active_object_builder`` — active object construction.
  * ``deeptutor.services.question_followup`` — followup context/action normalize.

GOD-OBJECT RED LINE (enforced by ``scripts/check_qtpk_import_allowlist.py``):
QTPK MUST NOT import or own a sixth class of fact. It is forbidden to import any
LLM client, grading kernel, RAG / retrieval, learner-state, reveal/answer-reveal,
terminal-result/visible-output, stream/transport, orchestrator, or turn_runtime
module. QTPK owns ONLY the five facts above; reveal/response_mode/practice
strategy/terminal/score are NOT QTPK facts.

S0 status: this module is a **zero-behavior skeleton**. ``resolve_turn_policy``
is a stub that does not implement any logic yet (S1 fills it by physically
moving ``_resolve_question_followup_context_and_action`` + active-object helpers
from ``turn_runtime`` and forwarding to the canonical resolvers above). No
existing caller imports this module yet; S0 changes no behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TurnPolicyDecision:
    """Immutable envelope of the five question-turn facts QTPK owns.

    Every field mirrors an already-canonical control-plane fact; QTPK only
    forwards the canonical resolvers' output into this envelope. It introduces
    no sixth fact (no reveal / response_mode / practice strategy / terminal /
    score). All fields default to an empty value so the S0 skeleton can build an
    empty envelope without implying any decision.
    """

    # Current object identity (which active object this turn is about).
    active_object: dict[str, Any] | None = None
    # Active-object patch result: the suspended-object stack after transition.
    suspended_object_stack: list[dict[str, Any]] = field(default_factory=list)
    # Relation + next_action (suspend/resume/demote) canonical decision.
    turn_semantic_decision: dict[str, Any] | None = None
    # Submission intent + evidence: the normalized followup context.
    question_followup_context: dict[str, Any] | None = None
    # Submission next action derived alongside the followup context.
    question_followup_action: dict[str, Any] | None = None
    # Lifecycle scene of the turn (string scene name).
    lifecycle_scene: str | None = None
    # Full lifecycle scene decision envelope (scene + supporting fields).
    scene_decision: dict[str, Any] | None = None


def resolve_turn_policy(*args: Any, **kwargs: Any) -> TurnPolicyDecision:
    """Resolve the question-turn policy for a single turn (QTPK entry point).

    Owns the five question-turn facts (scene / relation+next_action / submission
    intent+evidence / current object identity / active-object patch) by
    forwarding — never reimplementing — the canonical resolvers documented in the
    module docstring: ``resolve_question_semantic_routing``,
    ``resolve_question_lifecycle_scene_decision``,
    ``apply_active_object_transition``, and ``active_object_builder``.

    S0: not implemented. The physical move of ``turn_runtime``'s
    ``_resolve_question_followup_context_and_action`` and active-object helpers
    into this forwarder happens in S1 (zero-behavior parity move), guarded by the
    differential parity net in ``tests/services/test_qtpk_differential.py``.
    """

    raise NotImplementedError(
        "resolve_turn_policy is an S0 skeleton stub; the policy resolution is "
        "physically moved here (forwarding the existing canonical resolvers) in "
        "S1. See docs/plan/题目生命周期与助教运行时/"
        "2026-06-27-qtpk-physical-extraction-turnruntime-thinning-execution-plan.md."
    )
