from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot


def _numeric_score(
    *,
    value: float | None,
    source: str,
    is_proxy: bool = False,
    coverage: str = "direct",
    note: str | None = None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    entry: dict[str, Any] = {
        "value": round(float(value), 4),
        "source": source,
        "is_proxy": bool(is_proxy),
        "coverage": coverage,
    }
    if note:
        entry["note"] = note
    return entry


def _categorical_score(
    *,
    value: str | None,
    source: str,
    coverage: str = "direct",
    note: str | None = None,
) -> dict[str, Any] | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    entry: dict[str, Any] = {
        "value": normalized,
        "source": source,
        "coverage": coverage,
        "is_proxy": False,
    }
    if note:
        entry["note"] = note
    return entry


def _suite_pass_rate(payload: dict[str, Any], suite_prefix: str) -> float | None:
    for suite in payload.get("suite_summaries") or []:
        suite_name = str(suite.get("suite") or "")
        if suite_name.startswith(suite_prefix):
            pass_rate = suite.get("pass_rate")
            if isinstance(pass_rate, (int, float)):
                return float(pass_rate)
    return None


def _has_failure(payload: dict[str, Any], failure_type: str) -> bool:
    for case in payload.get("case_results") or []:
        if str(case.get("failure_type") or "").strip() == failure_type:
            return True
    return False


def _surface_score_from_om(om_payload: dict[str, Any] | None) -> tuple[float | None, str | None]:
    if not isinstance(om_payload, dict):
        return None, "缺少 OM snapshot。"
    metrics_snapshot = om_payload.get("metrics_snapshot") or {}
    coverages = (metrics_snapshot.get("surface_events") or {}).get("coverage") or []
    ratios: list[float] = []
    for item in coverages:
        first_ratio = item.get("first_render_coverage_ratio")
        if isinstance(first_ratio, (int, float)):
            ratios.append(float(first_ratio))
    if not ratios:
        return None, "当前没有 surface ack coverage。"
    return sum(ratios) / len(ratios), None


def _latency_class_from_om(om_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(om_payload, dict):
        return None
    turn_runtime = (om_payload.get("metrics_snapshot") or {}).get("turn_runtime") or {}
    avg_latency_ms = turn_runtime.get("turn_avg_latency_ms")
    if not isinstance(avg_latency_ms, (int, float)):
        return None
    if float(avg_latency_ms) <= 6000:
        return "fast"
    if float(avg_latency_ms) <= 18000:
        return "acceptable"
    return "slow"


def build_aae_composite_run(
    *,
    arr_payload: dict[str, Any],
    om_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arr_summary = arr_payload.get("summary") or {}
    release = arr_payload.get("release") or get_release_lineage_snapshot()
    notes: list[str] = []
    scores: dict[str, Any] = {}

    overall_pass_rate = arr_summary.get("pass_rate")
    if isinstance(overall_pass_rate, (int, float)):
        scores["correctness_score"] = _numeric_score(
            value=float(overall_pass_rate),
            source="arr_pass_rate",
            is_proxy=True,
            coverage="partial",
            note="correctness_score 当前以 ARR pass rate 作为系统级 proxy。",
        )
        notes.append("correctness_score 当前基于 ARR pass rate proxy。")

    groundedness_fail = _has_failure(arr_payload, "FAIL_GROUNDEDNESS")
    rag_suite_rate = _suite_pass_rate(arr_payload, "rag-grounding")
    groundedness_value = rag_suite_rate
    groundedness_note = None
    groundedness_proxy = False
    if groundedness_value is None:
        groundedness_value = 0.0 if groundedness_fail else 1.0
        groundedness_note = "当前未接入独立 rag-grounding suite，先按 FAIL_GROUNDEDNESS 是否出现做 proxy。"
        groundedness_proxy = True
    scores["groundedness_score"] = _numeric_score(
        value=groundedness_value,
        source="arr_failure_taxonomy" if groundedness_proxy else "arr_rag_suite",
        is_proxy=groundedness_proxy,
        coverage="partial",
        note=groundedness_note,
    )
    if groundedness_proxy:
        notes.append("groundedness_score 当前仍缺独立 rag-grounding 覆盖。")

    continuity_inputs = [
        rate
        for rate in (
            _suite_pass_rate(arr_payload, "context-orchestration"),
            _suite_pass_rate(arr_payload, "long-dialog"),
        )
        if isinstance(rate, (int, float))
    ]
    if continuity_inputs:
        scores["continuity_score"] = _numeric_score(
            value=sum(continuity_inputs) / len(continuity_inputs),
            source="arr_context_long_dialog",
            is_proxy=True,
            coverage="partial",
            note="continuity_score 当前基于 context-orchestration 与 long-dialog suite。",
        )
        notes.append("continuity_score 当前为 ARR suite proxy。")

    surface_value, surface_note = _surface_score_from_om(om_payload)
    if surface_value is not None:
        scores["surface_render_score"] = _numeric_score(
            value=surface_value,
            source="om_surface_ack",
            coverage="partial",
            note=surface_note,
        )
    elif surface_note:
        notes.append(surface_note)

    latency_class = _latency_class_from_om(om_payload)
    if latency_class:
        scores["latency_class"] = _categorical_score(
            value=latency_class,
            source="om_turn_avg_latency",
        )

    numeric_inputs = [
        float(item["value"])
        for item in scores.values()
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    ]
    if numeric_inputs:
        scores["paid_student_satisfaction_score"] = _numeric_score(
            value=sum(numeric_inputs) / len(numeric_inputs),
            source="proxy_composite",
            is_proxy=True,
            coverage="partial",
            note="paid_student_satisfaction_score 当前为 correctness/groundedness/continuity/surface proxy。",
        )
        notes.append("paid_student_satisfaction_score 当前仍是 proxy。")

    om_slo_compliance = (om_payload or {}).get("slo_summary", {}).get("compliance_ratio")
    if isinstance(om_slo_compliance, (int, float)):
        scores["om_slo_compliance_score"] = _numeric_score(
            value=float(om_slo_compliance),
            source="om_slo_summary",
            coverage="partial",
        )

    composite_inputs = [
        float(item["value"])
        for item in scores.values()
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    ]
    composite = None
    if composite_inputs:
        composite = {
            "value": round(sum(composite_inputs) / len(composite_inputs), 4),
            "coverage_ratio": round(len(composite_inputs) / 6.0, 4),
            "input_count": len(composite_inputs),
            "is_proxy": True,
        }

    run_id = f"aae-{int(time.time())}"
    return {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "source_arr_run_id": arr_payload.get("run_id"),
        "source_om_run_id": (om_payload or {}).get("run_id"),
        "scorecard": scores,
        "composite": composite,
        "coverage_summary": {
            "arr_case_count": int(arr_summary.get("total_cases") or 0),
            "surface_coverage_available": "surface_render_score" in scores,
            "om_slo_available": "om_slo_compliance_score" in scores,
        },
        "review_note": " ".join(notes).strip(),
    }
