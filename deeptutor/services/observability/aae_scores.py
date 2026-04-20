from __future__ import annotations

from typing import Any

_CONTINUITY_SENSITIVE_ROUTES = {
    "active_question_followup",
    "guided_plan_continuation",
    "cross_session_recall",
    "notebook_followup",
}


def _score_entry(
    *,
    value: float | bool | str | None,
    score_type: str,
    source: str,
    is_proxy: bool = False,
    coverage: str = "direct",
    note: str | None = None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    entry: dict[str, Any] = {
        "value": value,
        "type": score_type,
        "source": source,
        "is_proxy": bool(is_proxy),
        "coverage": coverage,
    }
    if note:
        entry["note"] = note
    return entry


def _extract_correctness(trace_metadata: dict[str, Any]) -> bool | None:
    followup_context = trace_metadata.get("question_followup_context")
    if isinstance(followup_context, dict) and "is_correct" in followup_context:
        value = followup_context.get("is_correct")
        if isinstance(value, bool):
            return value

    active_object = trace_metadata.get("active_object")
    if isinstance(active_object, dict):
        state_snapshot = active_object.get("state_snapshot")
        if isinstance(state_snapshot, dict):
            value = state_snapshot.get("is_correct")
            if isinstance(value, bool):
                return value
    return None


def build_turn_aae_metadata(
    *,
    trace_metadata: dict[str, Any],
    assistant_event_summary: dict[str, Any],
    terminal_status: str,
    turn_duration_ms: float,
    surface_turn_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    notes: list[str] = []

    correctness = _extract_correctness(trace_metadata)
    correctness_entry = _score_entry(
        value=1.0 if correctness is True else 0.0 if correctness is False else None,
        score_type="NUMERIC",
        source="rule_turn_context",
    )
    if correctness_entry:
        scores["correctness_score"] = correctness_entry

    sources = assistant_event_summary.get("sources") if isinstance(assistant_event_summary, dict) else None
    if isinstance(sources, list) and sources:
        groundedness_entry = _score_entry(
            value=1.0,
            score_type="NUMERIC",
            source="rule_sources_presence",
            is_proxy=True,
            coverage="partial",
            note="来源存在只能证明有 grounding signal，不等于人工核验正确 grounded。",
        )
        scores["groundedness_score"] = groundedness_entry
        notes.append("groundedness_score 当前基于来源存在性 proxy。")

    context_route = str(trace_metadata.get("context_route") or "").strip()
    if context_route in _CONTINUITY_SENSITIVE_ROUTES:
        continuity_value = 1.0 if terminal_status == "completed" else 0.0
        scores["continuity_score"] = _score_entry(
            value=continuity_value,
            score_type="NUMERIC",
            source="rule_route_completion",
            is_proxy=True,
            coverage="partial",
            note="当前 continuity_score 仅基于 continuity-sensitive route 是否顺利完成。",
        )
        notes.append("continuity_score 当前为 route completion proxy。")

    surface_summary = surface_turn_summary or {}
    surface_failed = int(surface_summary.get("surface_render_failed") or 0)
    surface_first = int(surface_summary.get("first_visible_content_rendered") or 0)
    surface_done = int(surface_summary.get("done_rendered") or 0)
    if surface_failed > 0:
        scores["surface_render_score"] = _score_entry(
            value=0.0,
            score_type="NUMERIC",
            source="surface_ack",
        )
    elif surface_first > 0 or surface_done > 0:
        scores["surface_render_score"] = _score_entry(
            value=1.0,
            score_type="NUMERIC",
            source="surface_ack",
        )
    else:
        notes.append("surface_render_score 当前无客户端 ACK，覆盖率未知。")

    latency_class = "fast" if turn_duration_ms <= 6000 else "acceptable" if turn_duration_ms <= 18000 else "slow"
    scores["latency_class"] = _score_entry(
        value=latency_class,
        score_type="CATEGORICAL",
        source="turn_runtime",
        coverage="direct",
    )

    proxy_values = [
        float(item["value"])
        for key, item in scores.items()
        if key in {"correctness_score", "groundedness_score", "continuity_score", "surface_render_score"}
        and isinstance(item, dict)
        and isinstance(item.get("value"), (int, float))
    ]
    if proxy_values:
        paid_student_proxy = round(sum(proxy_values) / len(proxy_values), 4)
        scores["paid_student_satisfaction_score"] = _score_entry(
            value=paid_student_proxy,
            score_type="NUMERIC",
            source="proxy_composite",
            is_proxy=True,
            coverage="partial",
            note="paid_student_satisfaction_score 当前为 correctness/groundedness/continuity/surface 的 proxy。",
        )
        notes.append("paid_student_satisfaction_score 当前为 proxy，不等于真实满意度。")

    composite_inputs = [
        float(item["value"])
        for item in scores.values()
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    ]
    composite = None
    if composite_inputs:
        composite = {
            "value": round(sum(composite_inputs) / len(composite_inputs), 4),
            "coverage_ratio": round(len(composite_inputs) / 5.0, 4),
            "input_count": len(composite_inputs),
            "is_proxy": True,
        }

    return {
        "aae_scores": scores,
        "aae_composite": composite,
        "aae_review_note": " ".join(notes).strip(),
    }
