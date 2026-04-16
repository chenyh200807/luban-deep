from __future__ import annotations

from typing import Any

from .context_pack import ContextPack


def resolve_target_escalation_level(*, route_label: str = "") -> int:
    normalized = str(route_label or "").strip()
    if not normalized:
        return 0
    if normalized == "cross_session_recall":
        return 3
    if normalized in {
        "guided_plan_continuation",
        "notebook_followup",
        "personal_recall",
        "tool_or_grounding_needed",
    }:
        return 2
    return 1


def resolve_escalation_level(
    *,
    loaded_sources: list[str] | tuple[str, ...],
    route_label: str = "",
    fallback_path: str = "",
) -> int:
    if str(fallback_path or "").strip():
        return 0
    source_set = {str(item or "").strip() for item in loaded_sources if str(item or "").strip()}
    if "history" in source_set:
        return 3
    if source_set & {"active_plan", "notebook", "memory"}:
        return 2
    if source_set & {"current_question", "session_history", "learner_card"}:
        return 1
    if str(route_label or "").strip():
        return 1
    return 0


def build_context_trace_summary(
    pack: ContextPack,
    *,
    fallback_path: str = "",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(pack.trace_metadata or {})
    if overrides:
        base.update(dict(overrides))
    base["fallback_path"] = str(fallback_path or base.get("fallback_path") or "").strip()

    loaded_sources = list(base.get("loaded_sources", []) or [])
    base["escalation_level"] = resolve_escalation_level(
        loaded_sources=loaded_sources,
        route_label=str(base.get("context_route", "") or ""),
        fallback_path=base["fallback_path"],
    )
    base["target_escalation_level"] = resolve_target_escalation_level(
        route_label=str(base.get("context_route", "") or ""),
    )
    base["blocks"] = {
        block.block.value: {
            "token_budget": int(block.token_budget or 0),
            "used_tokens": int(block.used_tokens or 0),
            "remaining_tokens": int(block.remaining_tokens or 0),
            "selected_candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "source_bucket": candidate.source_bucket,
                    "source_type": candidate.source_type,
                    "source_id": candidate.source_id,
                    "token_cost": int(candidate.token_cost or 0),
                    "metadata": dict(candidate.metadata or {}),
                }
                for candidate in block.selected_candidates
            ],
            "rejected_candidates": [dict(item) for item in block.rejected_candidates],
        }
        for block in pack.blocks()
    }
    return base


__all__ = [
    "build_context_trace_summary",
    "resolve_escalation_level",
    "resolve_target_escalation_level",
]
