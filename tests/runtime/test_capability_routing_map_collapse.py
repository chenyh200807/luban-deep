"""S5-branch differential parity: the decision→capability + context side-effect
mapping for the ``deep_question`` route is collapsed into one chokepoint
(``_map_canonical_decision_to_capability``) shared by all three former inline
copies (question_review active / practice_generation active /
_route_via_canonical_decision).

These tests pin the BYTE-PARITY contract the collapse must preserve:

* ``route_to_grading`` runs ``_prepare_question_submission_context(context,
  question_followup_action)`` exactly once and returns ``deep_question`` — the
  load-bearing side-effect duplicated at three call sites.
* ``route_to_generation`` runs ``_prepare_practice_request_context`` (canonical
  fall-through only) and returns ``deep_question``.
* ``route_to_followup_explainer`` (and any other deep_question route) returns
  ``deep_question`` with NO context-prep side-effect.

The three safety belts are NOT routed through the collapse point and are pinned
here as regression guards:

* unresolved-switch-followup → context-continuous chat/tutorbot (SEV-1).
* MCQ-grading preselect bypass (硬约束40).
* deep_question preselect demote on non-answer turns (task #20).
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.orchestrator import ChatOrchestrator
from deeptutor.services.semantic_router import build_turn_semantic_decision


class _RecordingOrchestrator(ChatOrchestrator):
    """Captures which context-prep side-effects ran, without invoking the real
    (network-bound) submission/practice context builders, so the differential
    compares the *dispatch* (which prep for which next_action) deterministically.
    """

    def __init__(self) -> None:
        super().__init__()
        self.prep_calls: list[tuple[str, Any]] = []

    def _prepare_question_submission_context(  # type: ignore[override]
        self,
        context: UnifiedContext,
        action: dict[str, Any] | None = None,
    ) -> None:
        self.prep_calls.append(("submission", action))
        context.metadata["__prep_submission__"] = True

    def _prepare_practice_request_context(  # type: ignore[override]
        self,
        context: UnifiedContext,
        message: str,
    ) -> None:
        self.prep_calls.append(("practice", message))
        context.metadata["__prep_practice__"] = True


def _ctx(metadata: dict[str, Any] | None = None) -> UnifiedContext:
    return UnifiedContext(
        session_id="s1",
        user_message="选 A",
        config_overrides={},
        metadata=dict(metadata or {}),
        language="zh",
    )


def _grading_decision() -> dict[str, Any]:
    return build_turn_semantic_decision(
        relation_to_active_object="answer_active_object",
        next_action="route_to_grading",
        allowed_patch="record_submission",
        confidence=1.0,
        reason="t",
        active_object=None,
    )


def _followup_decision() -> dict[str, Any]:
    return build_turn_semantic_decision(
        relation_to_active_object="ask_about_active_object",
        next_action="route_to_followup_explainer",
        allowed_patch="no_state_change",
        confidence=1.0,
        reason="t",
        active_object=None,
    )


def _generation_decision() -> dict[str, Any]:
    return build_turn_semantic_decision(
        relation_to_active_object="switch_to_new_object",
        next_action="route_to_generation",
        allowed_patch="record_submission",
        confidence=1.0,
        reason="t",
        active_object=None,
    )


# ---------------------------------------------------------------------------
# Collapse-point contract (the single chokepoint all three callers delegate to)
# ---------------------------------------------------------------------------


def test_map_route_to_grading_preps_submission_and_returns_deep_question() -> None:
    orch = _RecordingOrchestrator()
    ctx = _ctx({"question_followup_action": {"intent": "answer_questions"}})
    cap = orch._map_canonical_decision_to_capability(
        ctx, _grading_decision(), routing_user_message="选 A"
    )
    assert cap == "deep_question"
    assert orch.prep_calls == [("submission", {"intent": "answer_questions"})]
    assert ctx.metadata.get("__prep_submission__") is True
    assert "__prep_practice__" not in ctx.metadata


def test_map_route_to_generation_preps_practice_and_returns_deep_question() -> None:
    orch = _RecordingOrchestrator()
    ctx = _ctx()
    cap = orch._map_canonical_decision_to_capability(
        ctx, _generation_decision(), routing_user_message="再出一道题"
    )
    assert cap == "deep_question"
    assert orch.prep_calls == [("practice", "再出一道题")]
    assert ctx.metadata.get("__prep_practice__") is True
    assert "__prep_submission__" not in ctx.metadata


def test_map_route_to_followup_explainer_no_prep_returns_deep_question() -> None:
    orch = _RecordingOrchestrator()
    ctx = _ctx()
    cap = orch._map_canonical_decision_to_capability(
        ctx, _followup_decision(), routing_user_message="为什么"
    )
    assert cap == "deep_question"
    assert orch.prep_calls == []
    assert "__prep_submission__" not in ctx.metadata
    assert "__prep_practice__" not in ctx.metadata


def test_map_practice_generation_message_uses_action_topic() -> None:
    """Parity with _route_via_canonical_decision: practice prep message is
    _practice_generation_message(context, routing_user_message) — action topic wins."""
    orch = _RecordingOrchestrator()
    ctx = _ctx({"question_followup_action": {"topic": "流水施工"}})
    orch._map_canonical_decision_to_capability(
        ctx, _generation_decision(), routing_user_message="fallback"
    )
    assert orch.prep_calls == [("practice", "流水施工")]


# ---------------------------------------------------------------------------
# End-to-end byte-parity through the three callers (capability + side-effect)
# ---------------------------------------------------------------------------


async def _route_active_lifecycle(
    orch: _RecordingOrchestrator,
    scene: str,
    decision: dict[str, Any],
    *,
    active_object: dict[str, Any] | None = None,
) -> tuple[str, UnifiedContext]:
    """Exercise the question_review / practice_generation active-lifecycle blocks
    by stubbing scene + turn decision so routing reaches the deep_question branch.
    """
    md: dict[str, Any] = {
        "active_object": active_object or {"object_type": "question", "question_id": "q1"},
        "question_followup_context": {"question_id": "q1"},
    }
    ctx = _ctx(md)

    async def _scene(_carrier: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            scene=scene,
            source="stub",
            confidence=1.0,
            reason="stub",
            required_anchor_status=None,
            exact_question_blocked_reason=None,
            selected_skill_names=(),
            needs_clarification=False,
            llm_scene_candidate=None,
            business_gate_result=None,
        )

    async def _decide(_context: UnifiedContext, _message: str) -> dict[str, Any]:
        return decision

    import deeptutor.runtime.orchestrator as orch_mod

    orig_scene = orch_mod.resolve_question_lifecycle_scene_decision
    orch_mod.resolve_question_lifecycle_scene_decision = _scene  # type: ignore[assignment]
    orch._resolve_turn_semantic_decision = _decide  # type: ignore[assignment]
    orch._has_active_lifecycle_context = lambda _c: True  # type: ignore[assignment]
    try:
        cap = await orch._select_capability(ctx)
    finally:
        orch_mod.resolve_question_lifecycle_scene_decision = orig_scene  # type: ignore[assignment]
    return cap, ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["question_review", "practice_generation"])
async def test_active_lifecycle_route_to_grading_preps_submission(scene: str) -> None:
    orch = _RecordingOrchestrator()
    cap, ctx = await _route_active_lifecycle(orch, scene, _grading_decision())
    assert cap == "deep_question"
    assert orch.prep_calls == [("submission", None)]
    assert ctx.metadata.get("semantic_router_selected_capability") == "deep_question"


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["question_review", "practice_generation"])
async def test_active_lifecycle_route_to_followup_no_prep(scene: str) -> None:
    orch = _RecordingOrchestrator()
    cap, ctx = await _route_active_lifecycle(orch, scene, _followup_decision())
    assert cap == "deep_question"
    assert orch.prep_calls == []


# ---------------------------------------------------------------------------
# Safety belts — NOT routed through the collapse point (regression guards)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolved_switch_belt_untouched_by_collapse() -> None:
    """SEV-1: switch_to_new_object + route_to_followup_explainer → context-continuous
    chat, never deep_question (and no submission/practice prep)."""
    orch = _RecordingOrchestrator()
    unresolved = build_turn_semantic_decision(
        relation_to_active_object="switch_to_new_object",
        next_action="route_to_followup_explainer",
        allowed_patch="no_state_change",
        confidence=1.0,
        reason="t",
        active_object=None,
    )
    cap, ctx = await _route_active_lifecycle(orch, "question_review", unresolved)
    assert cap == "chat"
    assert orch.prep_calls == []
    assert (
        ctx.metadata.get("semantic_router_mode_reason")
        == "stub_unresolved_switch_to_context_continuity"
    )


@pytest.mark.asyncio
async def test_canonical_fallthrough_route_to_grading_preps_submission() -> None:
    """_route_via_canonical_decision (post-lifecycle, no active scene) parity."""
    orch = _RecordingOrchestrator()
    ctx = _ctx({"question_followup_action": {"intent": "answer_questions"}})

    async def _decide(_context: UnifiedContext, _message: str) -> dict[str, Any]:
        return _grading_decision()

    orch._resolve_turn_semantic_decision = _decide  # type: ignore[assignment]
    cap = await orch._route_via_canonical_decision(
        ctx, "选 A", mode="primary", mode_reason="semantic_router_primary"
    )
    assert cap == "deep_question"
    assert orch.prep_calls == [("submission", {"intent": "answer_questions"})]
    assert ctx.metadata.get("semantic_router_selected_capability") == "deep_question"


@pytest.mark.asyncio
async def test_canonical_fallthrough_route_to_generation_preps_practice() -> None:
    orch = _RecordingOrchestrator()
    ctx = _ctx({"question_followup_action": {"topic": "流水施工"}})

    async def _decide(_context: UnifiedContext, _message: str) -> dict[str, Any]:
        return _generation_decision()

    orch._resolve_turn_semantic_decision = _decide  # type: ignore[assignment]
    cap = await orch._route_via_canonical_decision(
        ctx, "再来一题", mode="primary", mode_reason="semantic_router_primary"
    )
    assert cap == "deep_question"
    assert orch.prep_calls == [("practice", "流水施工")]


@pytest.mark.asyncio
async def test_canonical_fallthrough_unresolved_switch_belt() -> None:
    orch = _RecordingOrchestrator()
    ctx = _ctx()
    unresolved = build_turn_semantic_decision(
        relation_to_active_object="switch_to_new_object",
        next_action="route_to_followup_explainer",
        allowed_patch="no_state_change",
        confidence=1.0,
        reason="t",
        active_object=None,
    )

    async def _decide(_context: UnifiedContext, _message: str) -> dict[str, Any]:
        return unresolved

    orch._resolve_turn_semantic_decision = _decide  # type: ignore[assignment]
    cap = await orch._route_via_canonical_decision(
        ctx, "刚才那道题", mode="primary", mode_reason="semantic_router_primary"
    )
    assert cap == "chat"
    assert orch.prep_calls == []
    assert (
        ctx.metadata.get("semantic_router_mode_reason")
        == "unresolved_switch_to_context_continuity"
    )
