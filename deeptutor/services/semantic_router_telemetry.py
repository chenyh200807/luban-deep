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
    "allowed_patch",
)


_BLOCKED_GATE_PREFIX = "blocked_"


def _classify_scene_divergence(
    *,
    llm_candidate: dict[str, Any] | None,
    final_scene: Any,
    decision_source: str,
    business_gate_result: str,
) -> str:
    """Observe-only shadow probe: LLM scene proposal vs deterministic verdict.

    Pure string/dict comparison over metadata the orchestrator already wrote
    (orchestrator._record_lifecycle_decision). Never read back by routing.
    """
    has_candidate = isinstance(llm_candidate, dict)
    candidate_scene = str((llm_candidate or {}).get("scene") or "") if has_candidate else ""
    # PR3-R4(F6):`scene` 已被 0.72 阈值置空的候选,原始判定活在 `raw_scene`
    # (question_lifecycle_skills._propose_scene_with_llm 置空前留档)。判 gate 否决
    # **优先用 raw_scene** ——否则"LLM 本来判了 scene、被闸否决"整类恒被误分到 T2。
    raw_candidate_scene = str((llm_candidate or {}).get("raw_scene") or "") if has_candidate else ""
    gate_vetoed_candidate_scene = raw_candidate_scene or candidate_scene
    gate_blocked = business_gate_result.startswith(_BLOCKED_GATE_PREFIX)
    final = str(final_scene or "")
    if gate_vetoed_candidate_scene and gate_blocked:
        return "llm_verdict_gate_vetoed"          # T1(F2 形态)
    if candidate_scene:
        return "agreement" if candidate_scene == final else "llm_scene_conflicts_final"
    if has_candidate:
        return "llm_none_or_threshold_drop"       # T2
    if gate_blocked or business_gate_result == "llm_unavailable":
        return "gate_blocked_llm_unavailable"     # T4
    if final and decision_source in {"deterministic", "metadata"}:
        return "deterministic_preempt_no_llm"     # T3
    if final:
        return "scene_without_source"             # 防御桶,预期恒 0
    return "no_llm_no_scene"                      # 开放聊天等无 scene 轮


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


def _reason_prefix(reason: str, *, max_chars: int = 80) -> str:
    normalized = " ".join(str(reason or "").strip().split())
    return normalized[:max_chars]


def _decision_schema_valid(decision: dict[str, Any]) -> bool:
    required = {
        "next_action",
        "confidence",
        "reason",
        "relation_to_active_object",
        "allowed_patch",
    }
    return all(key in decision for key in required)


def _normalize_writer_chain(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    writers: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized and normalized not in writers:
            writers.append(normalized)
    return writers


def _inferred_decision_writer_chain(
    *,
    decision: dict[str, Any],
    mode: str,
    final_executed_capability: str,
) -> list[str]:
    if not decision:
        return []

    reason = str(decision.get("reason") or "").strip()
    if reason == "question_domain_adapter":
        return ["turn_runtime_question_domain_adapter"]
    if mode == "primary":
        return ["semantic_router"]
    if mode == "question_lifecycle":
        return ["question_lifecycle"]
    if mode == "preselected":
        return ["preselected_capability"]
    if mode in {"disabled", "shadow"}:
        return ["legacy_selector"]
    if final_executed_capability == "deep_question":
        return ["deep_question_compat_fallback"]
    return ["unknown"]


def _decision_writer_chain_with_source(
    *,
    context_metadata: dict[str, Any],
    decision: dict[str, Any],
    mode: str,
    final_executed_capability: str,
) -> tuple[list[str], str]:
    for key in ("turn_semantic_decision_writer_chain", "decision_writer_chain"):
        writers = _normalize_writer_chain(context_metadata.get(key))
        if writers:
            return writers, "recorded"
    inferred = _inferred_decision_writer_chain(
        decision=decision,
        mode=mode,
        final_executed_capability=final_executed_capability,
    )
    return inferred, "inferred" if inferred else "none"


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
    raw_candidate = context_metadata.get("llm_scene_candidate")
    llm_candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else None
    final_scene = context_metadata.get("question_lifecycle_scene")
    business_gate_result = str(context_metadata.get("business_gate_result") or "").strip()
    lifecycle_source = str(
        context_metadata.get("question_lifecycle_scene_source") or ""
    ).strip()

    semantic_decision = {
        field: decision[field] for field in _SEMANTIC_DECISION_FIELDS if field in decision
    }
    next_action = str(decision.get("next_action") or "")
    reason = str(decision.get("reason") or "")
    final_capability = str(final_executed_capability or "").strip()
    writer_chain, writer_chain_source = _decision_writer_chain_with_source(
        context_metadata=context_metadata,
        decision=decision,
        mode=mode,
        final_executed_capability=final_capability,
    )
    decision_schema_valid = _decision_schema_valid(decision)
    fallback_reason_prefix = (
        _reason_prefix(reason)
        if reason and _is_default_template(next_action, reason)
        else ""
    )

    telemetry = {
        "captured_raw_input": captured_raw_input,
        "semantic_decision": semantic_decision,
        "final_executed_capability": final_capability,
        # A semantic decision only drives the route in `primary` mode; every
        # other mode (question_lifecycle / preselected / shadow / disabled) means
        # the route was decided elsewhere and this decision was bookkeeping.
        "drove_route": mode == "primary",
        "is_default_template": _is_default_template(next_action, reason),
        "mode": mode,
        "authority_probe_schema_version": 2,
        # 路由收权 shadow 度量(2026-08-11 owner 拍板,observe-only):确定性管线
        # 最终判定 vs 已付费 LLM 语义判定的分歧形态。原料全部来自
        # orchestrator._record_lifecycle_decision 已写入的 metadata,纯只读。
        "lifecycle_final": {
            "scene": final_scene,
            "source": lifecycle_source,
            "business_gate_result": business_gate_result,
            "mode_reason": str(
                context_metadata.get("semantic_router_mode_reason") or ""
            ).strip(),
        },
        "llm_scene_candidate": llm_candidate,
        "scene_divergence": _classify_scene_divergence(
            llm_candidate=llm_candidate,
            final_scene=final_scene,
            decision_source=lifecycle_source,
            business_gate_result=business_gate_result,
        ),
        "decision_writer_chain": writer_chain,
        "decision_writer_chain_source": writer_chain_source,
        "final_decision_writer": writer_chain[-1] if writer_chain else "",
        "decision_authority_count": len(writer_chain),
        "decision_schema_valid": decision_schema_valid,
        "decision_overwrite_count": max(len(writer_chain) - 1, 0),
        "legacy_selector_used": mode in {"disabled", "shadow"},
        "preselected_bypass_used": mode == "preselected",
        "deep_question_canonical_decision_missing": (
            final_capability == "deep_question" and not decision_schema_valid
        ),
    }
    if fallback_reason_prefix:
        telemetry["fallback_decision_reason_prefix"] = fallback_reason_prefix
    return telemetry


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
