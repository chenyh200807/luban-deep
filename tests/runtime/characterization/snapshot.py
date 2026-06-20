"""Routing-decision snapshot for the context-continuity characterization harness.

Captures the OBSERVABLE routing decision of ``ChatOrchestrator._select_capability`` —
the returned capability plus the decision keys it writes into ``context.metadata`` —
normalized to the decision-bearing fields only (confidence / free-text reason dropped so
the golden is not brittle; hidden grading authority redacted per contracts/turn.md §13).

This is the safety net for the task #12 真闭包 migration: each 收口 step that moves where a
relation/submission decision is computed must keep this snapshot byte-identical across the
whole matrix, or the golden diff shows exactly which row/key drifted.
"""

from __future__ import annotations

from typing import Any

from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.orchestrator import ChatOrchestrator

# Top-level metadata decision keys written by _record_lifecycle_decision /
# _resolve_turn_semantic_decision / the routing branches.
DECISION_KEYS = (
    "question_lifecycle_scene",
    "question_lifecycle_scene_source",
    "question_lifecycle_skill_names",
    "decision_source",
    "exact_question_blocked_reason",
    "business_gate_result",
    "required_anchor_status",
    "semantic_router_mode",
    "semantic_router_mode_reason",
    "semantic_router_selected_capability",
    "semantic_router_shadow_route",
    "semantic_router_scope_match",
)


def _norm_semantic_decision(d: Any) -> dict[str, Any] | None:
    if not isinstance(d, dict):
        return None
    # decision-bearing only; drop confidence (float) + reason (free prose) → anti-brittle
    return {
        "relation_to_active_object": d.get("relation_to_active_object"),
        "next_action": d.get("next_action"),
        "allowed_patch": sorted(d.get("allowed_patch") or []),
    }


def _norm_active_object(ao: Any) -> dict[str, Any] | None:
    if not isinstance(ao, dict):
        return None
    # identity only — redact hidden grading authority (turn.md §13)
    return {"object_type": ao.get("object_type"), "object_id": ao.get("object_id")}


def _norm_stack(stack: Any) -> list[str]:
    if not isinstance(stack, list):
        return []
    return [str((o or {}).get("object_type") or "") for o in stack if isinstance(o, dict)]


async def capture_routing_decision(
    *,
    message: str,
    context_state: dict[str, Any],
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the live router on (message, context_state) and snapshot the decision."""

    orchestrator = ChatOrchestrator()
    context = UnifiedContext(
        session_id="characterization",
        user_message=message,
        config_overrides=dict(config_overrides or {}),
        metadata=dict(context_state),
        language="zh",
    )
    capability = await orchestrator._select_capability(context)

    md = context.metadata
    snap: dict[str, Any] = {"_capability": capability}
    for key in DECISION_KEYS:
        if key in md:
            snap[key] = md[key]
    lifecycle = md.get("question_lifecycle_decision")
    if isinstance(lifecycle, dict):
        snap["needs_clarification"] = lifecycle.get("needs_clarification")
    snap["turn_semantic_decision"] = _norm_semantic_decision(md.get("turn_semantic_decision"))
    action = md.get("question_followup_action")
    snap["followup_action_intent"] = (
        action.get("intent") if isinstance(action, dict) else None
    )
    snap["active_object"] = _norm_active_object(md.get("active_object"))
    snap["suspended_object_stack"] = _norm_stack(md.get("suspended_object_stack"))
    return snap
