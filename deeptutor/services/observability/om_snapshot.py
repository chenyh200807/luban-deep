from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def build_om_run(
    *,
    metrics_snapshot: dict[str, Any],
    stack_health: list[dict[str, Any]] | None = None,
    smoke_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    release = metrics_snapshot.get("release") or get_release_lineage_snapshot()
    turn_runtime = metrics_snapshot.get("turn_runtime") or {}
    readiness = metrics_snapshot.get("readiness") or {}
    surface_snapshot = metrics_snapshot.get("surface_events") or {}
    providers = metrics_snapshot.get("providers") or {}

    turns_started = float(turn_runtime.get("turns_started_total") or 0.0)
    turns_completed = float(turn_runtime.get("turns_completed_total") or 0.0)
    turns_failed = float(turn_runtime.get("turns_failed_total") or 0.0)
    turns_cancelled = float(turn_runtime.get("turns_cancelled_total") or 0.0)
    readyz_ratio = 1.0 if readiness.get("ready") is True else 0.0
    turn_success_ratio = _ratio(turns_completed, max(turns_started, 1.0))

    first_render_ratios: list[float] = []
    for item in surface_snapshot.get("coverage") or []:
        ratio = item.get("first_render_coverage_ratio")
        if isinstance(ratio, (int, float)):
            first_render_ratios.append(float(ratio))
    turn_first_render_ratio = round(sum(first_render_ratios) / len(first_render_ratios), 4) if first_render_ratios else None

    provider_error_rates = (providers.get("error_rates") or {}) if isinstance(providers, dict) else {}
    provider_ratios: list[float] = []
    for provider in provider_error_rates.values():
        ratio = provider.get("error_rate")
        if isinstance(ratio, (int, float)):
            provider_ratios.append(float(ratio))
    provider_error_ratio = round(max(provider_ratios), 4) if provider_ratios else 0.0
    smoke_entries = list(smoke_checks or [])
    unified_ws_smoke = next(
        (item for item in smoke_entries if str(item.get("name") or "").strip() == "unified_ws_smoke"),
        None,
    )
    unified_ws_smoke_ok = bool(unified_ws_smoke.get("ok")) if isinstance(unified_ws_smoke, dict) else None
    unified_ws_smoke_summary = str(unified_ws_smoke.get("summary") or "").strip() if isinstance(unified_ws_smoke, dict) else ""

    slo_checks = [
        {
            "name": "turn_success_ratio",
            "value": turn_success_ratio,
            "target": 0.995,
            "status": "PASS" if isinstance(turn_success_ratio, (int, float)) and turn_success_ratio >= 0.995 else "WARN",
        },
        {
            "name": "turn_first_render_ratio",
            "value": turn_first_render_ratio,
            "target": 0.99,
            "status": "PASS"
            if isinstance(turn_first_render_ratio, (int, float)) and turn_first_render_ratio >= 0.99
            else "WARN",
        },
        {
            "name": "readyz_success_ratio",
            "value": readyz_ratio,
            "target": 0.999,
            "status": "PASS" if readyz_ratio >= 0.999 else "FAIL",
        },
        {
            "name": "turn_p95_latency_seconds_proxy",
            "value": round(float(turn_runtime.get("turn_avg_latency_ms") or 0.0) / 1000.0, 4),
            "target": 6.0,
            "status": "PASS"
            if float(turn_runtime.get("turn_avg_latency_ms") or 0.0) <= 6000.0
            else "WARN",
        },
        {
            "name": "provider_error_ratio",
            "value": provider_error_ratio,
            "target": 0.05,
            "status": "PASS" if provider_error_ratio <= 0.05 else "WARN",
        },
    ]
    compliance_inputs = [1.0 if item["status"] == "PASS" else 0.0 for item in slo_checks]

    health_summary = {
        "ready": bool(readiness.get("ready")),
        "turns_started_total": int(turns_started),
        "turns_completed_total": int(turns_completed),
        "turns_failed_total": int(turns_failed),
        "turns_cancelled_total": int(turns_cancelled),
        "turn_success_ratio": turn_success_ratio,
        "turn_first_render_ratio": turn_first_render_ratio,
        "provider_error_ratio": provider_error_ratio,
        "unified_ws_smoke_ok": unified_ws_smoke_ok,
        "unified_ws_smoke_summary": unified_ws_smoke_summary,
    }

    run_id = f"om-{int(time.time())}"
    return {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "metrics_snapshot": metrics_snapshot,
        "stack_health": stack_health or [],
        "smoke_checks": smoke_entries,
        "health_summary": health_summary,
        "slo_summary": {
            "checks": slo_checks,
            "compliance_ratio": round(sum(compliance_inputs) / len(compliance_inputs), 4),
        },
        "incident_candidates": [
            *[
                {
                    "title": "runtime_not_ready",
                    "severity": "critical",
                    "evidence": ["readiness.ready=false"],
                }
                for _ in [0]
                if readiness.get("ready") is not True
            ],
            *[
                {
                    "title": "unified_ws_smoke_failed",
                    "severity": "critical",
                    "evidence": list(unified_ws_smoke.get("evidence") or []) or [unified_ws_smoke_summary or "ws smoke failed"],
                }
                for _ in [0]
                if isinstance(unified_ws_smoke, dict) and unified_ws_smoke_ok is False
            ],
        ],
    }
