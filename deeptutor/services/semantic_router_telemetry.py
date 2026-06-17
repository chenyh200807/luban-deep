"""Additive, behavior-preserving telemetry for semantic-router decisions.

Builds a stable, queryable telemetry tuple from metadata the orchestrator has
already populated. It NEVER changes any routing decision — it only observes.

Closes the 3 instrumentation breakpoints surfaced by the 2026-05-30 baseline
(`docs/plan/2026-05-30-semantic-router-baseline-results.md`):

  1. ``captured_raw_input`` is supplied in-place by the caller at the moment the
     decision is recorded, so analysis no longer needs the unreliable
     session+time join (35% missed / stale matches).
  2. ``final_executed_capability`` + ``drove_route`` separate "the semantic
     decision was recorded" from "the semantic decision actually drove the
     route" (18% of decisions were lifecycle overrides / bookkeeping).
  3. ``is_default_template`` explicitly flags the non-discriminative default /
     deterministic-fallback / hold decisions (~40%) so analysis can bucket or
     drop them instead of counting them as judged routes.
"""
from __future__ import annotations

from typing import Any

# The bulk conf=0.70 "no active object -> default to generation" fallback. It is
# emitted verbatim, so a prefix match reliably identifies it.
_DEFAULT_TEMPLATE_REASON_PREFIX = "当前 session 仍在开放对话"
_DETERMINISTIC_FALLBACK_MARKER = "deterministic fallback"

_SEMANTIC_DECISION_FIELDS = (
    "next_action",
    "confidence",
    "reason",
    "relation_to_active_object",
)


def _is_default_template(next_action: str, reason: str) -> bool:
    """True for non-discriminative default / fallback / hold decisions."""
    if next_action == "hold_and_wait":
        return True
    stripped = reason.strip()
    if stripped.startswith(_DEFAULT_TEMPLATE_REASON_PREFIX):
        return True
    if _DETERMINISTIC_FALLBACK_MARKER in reason:
        return True
    return False


def build_semantic_router_telemetry(
    *,
    context_metadata: dict[str, Any],
    final_executed_capability: str,
    captured_raw_input: str,
) -> dict[str, Any]:
    """Build the additive semantic-router telemetry tuple (pure, no IO)."""
    raw_decision = context_metadata.get("turn_semantic_decision")
    decision = raw_decision if isinstance(raw_decision, dict) else {}
    mode = str(context_metadata.get("semantic_router_mode") or "").strip()

    semantic_decision = {
        field: decision[field] for field in _SEMANTIC_DECISION_FIELDS if field in decision
    }
    next_action = str(decision.get("next_action") or "")
    reason = str(decision.get("reason") or "")

    return {
        "captured_raw_input": captured_raw_input,
        "semantic_decision": semantic_decision,
        "final_executed_capability": str(final_executed_capability or "").strip(),
        # A semantic decision only drives the route in `primary` mode; every
        # other mode (question_lifecycle / preselected / shadow / disabled) means
        # the route was decided elsewhere and this decision was bookkeeping.
        "drove_route": mode == "primary",
        "is_default_template": _is_default_template(next_action, reason),
        "mode": mode,
    }


def build_semantic_router_telemetry_event(
    *,
    context_metadata: dict[str, Any],
    final_executed_capability: str,
    captured_raw_input: str,
) -> dict[str, Any]:
    """Build an internal turn_event payload carrying the telemetry tuple.

    Stored to the app's own durable turn_events store (SQLite), ``internal``
    visibility, never published to the client and never forwarded to external
    trace. This is the PII-safe home for ``captured_raw_input`` (same durability
    tier as ``messages.content``).
    """
    return {
        "type": "observation",
        "source": "turn_runtime",
        "stage": "semantic_router_telemetry",
        "content": "",
        "visibility": "internal",
        "metadata": {
            "semantic_router_telemetry": build_semantic_router_telemetry(
                context_metadata=context_metadata,
                final_executed_capability=final_executed_capability,
                captured_raw_input=captured_raw_input,
            )
        },
    }


__all__ = [
    "build_semantic_router_telemetry",
    "build_semantic_router_telemetry_event",
]
