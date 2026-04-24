from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_SKIP = "SKIP"
_INCOMPLETE_RELEASE_VALUES = {"", "unknown", "unset", "none"}


def _gate_entry(
    *,
    gate: str,
    status: str,
    summary: str,
    evidence: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "blockers": blockers or [],
    }


def _benchmark_pass_rate(case_results: list[dict[str, Any]]) -> float | None:
    executed = [item for item in case_results if item.get("status") != "SKIP"]
    if not executed:
        return None
    passed = len([item for item in executed if item.get("status") == "PASS"])
    return round(passed / len(executed), 4)


def _has_release_value(release: dict[str, Any], key: str) -> bool:
    value = str(release.get(key) or "").strip().lower()
    if value in _INCOMPLETE_RELEASE_VALUES:
        return False
    if key in {"release_id", "git_sha"} and "unknown" in value:
        return False
    return True


def build_release_gate_report(
    *,
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    aae_payload: dict[str, Any] | None,
    oa_payload: dict[str, Any] | None,
    change_impact_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    release = (
        (arr_payload or {}).get("release")
        or (om_payload or {}).get("release")
        or (aae_payload or {}).get("release")
        or get_release_lineage_snapshot()
    )
    gate_results: list[dict[str, Any]] = []

    om_health = (om_payload or {}).get("health_summary") or {}
    release_complete = all(
        _has_release_value(release, key)
        for key in ("release_id", "git_sha", "deployment_environment", "prompt_version", "ff_snapshot_hash")
    )
    unified_ws_smoke_ok = om_health.get("unified_ws_smoke_ok")
    ws_main_path_healthy = unified_ws_smoke_ok is not False
    p0_ready = om_health.get("ready") is True and release_complete and ws_main_path_healthy
    gate_results.append(
        _gate_entry(
            gate="P0 Runtime",
            status=_PASS if p0_ready else _FAIL,
            summary="readyz、release lineage 与 ws 主链路可用"
            if p0_ready
            else "runtime readiness、release lineage 或 ws 主链路异常",
            evidence=[
                f"ready={om_health.get('ready')}",
                f"release_complete={release_complete}",
                f"unified_ws_smoke_ok={unified_ws_smoke_ok}",
            ],
            blockers=[] if p0_ready else [
                *([] if om_health.get("ready") is True and release_complete else ["runtime_or_release_lineage_incomplete"]),
                *(["ws_main_path_unhealthy"] if ws_main_path_healthy is False else []),
            ],
        )
    )

    surface_coverages = ((om_payload or {}).get("metrics_snapshot") or {}).get("surface_events", {}).get("coverage") or []
    unknown_surface = not bool(surface_coverages)
    p1_status = _WARN if unknown_surface else _PASS
    gate_results.append(
        _gate_entry(
            gate="P1 Trace Completeness",
            status=p1_status,
            summary="已看到 surface ack 覆盖" if not unknown_surface else "surface ack coverage 仍未知",
            evidence=[
                f"surface_coverage_count={len(surface_coverages)}",
                f"prompt_version={release.get('prompt_version')}",
                f"ff_snapshot_hash={release.get('ff_snapshot_hash')}",
            ],
        )
    )

    benchmark_case_results = (arr_payload or {}).get("benchmark_case_results") or []
    benchmark_manifest = (arr_payload or {}).get("benchmark_run_manifest") or {}
    benchmark_blind_spots = (arr_payload or {}).get("blind_spots") or []
    arr_summary = (arr_payload or {}).get("summary") or {}
    arr_diff = (arr_payload or {}).get("baseline_diff") or {}
    benchmark_pass_rate = _benchmark_pass_rate(benchmark_case_results) if benchmark_case_results else arr_summary.get("pass_rate")
    new_critical_regressions = len(arr_diff.get("regressions") or []) + len(arr_diff.get("new_failures") or [])
    p2_status = _SKIP
    p2_summary = "未提供 benchmark / ARR run"
    p2_blockers: list[str] = []
    if arr_payload:
        pass_rate = benchmark_pass_rate
        has_new_critical = new_critical_regressions > 0
        p2_status = _PASS
        p2_summary = "benchmark 当前无新增 regression"
        if has_new_critical:
            p2_status = _FAIL
            p2_summary = "benchmark 出现新增 regression 或 new failure"
            p2_blockers.append("new_benchmark_regression")
        elif isinstance(pass_rate, (int, float)) and float(pass_rate) < 0.9:
            p2_status = _WARN
            p2_summary = "benchmark pass rate 偏低，但当前没有新增 regression"
    gate_results.append(
        _gate_entry(
            gate="P2 Benchmark Regression",
            status=p2_status,
            summary=p2_summary,
            evidence=[
                f"benchmark_run_id={benchmark_manifest.get('run_id')}",
                f"requested_suites={benchmark_manifest.get('requested_suites')}",
                f"pass_rate={benchmark_pass_rate}",
                f"regressions={new_critical_regressions}",
                f"new_failures={len(arr_diff.get('new_failures') or [])}",
            ],
            blockers=p2_blockers,
        )
    )

    aae_scorecard = (aae_payload or {}).get("scorecard") or {}
    aae_composite = (aae_payload or {}).get("composite") or {}
    p3_status = _SKIP
    p3_summary = "未提供 AAE run"
    if aae_payload:
        proxy_heavy = bool(((aae_scorecard.get("paid_student_satisfaction_score") or {}).get("is_proxy")))
        composite_value = aae_composite.get("value")
        p3_status = _WARN if proxy_heavy else _PASS
        p3_summary = "AAE 已生成，但关键分数仍以 proxy 为主" if proxy_heavy else "AAE 关键分数可用"
        if isinstance(composite_value, (int, float)) and composite_value < 0.75:
            p3_status = _FAIL
            p3_summary = "AAE composite 低于最低门槛"
    gate_results.append(
        _gate_entry(
            gate="P3 AAE",
            status=p3_status,
            summary=p3_summary,
            evidence=[
                f"composite={aae_composite.get('value')}",
                f"coverage_ratio={aae_composite.get('coverage_ratio')}",
                f"proxy_paid_satisfaction={((aae_scorecard.get('paid_student_satisfaction_score') or {}).get('is_proxy'))}",
            ],
            blockers=["aae_composite_below_floor"] if p3_status == _FAIL else [],
        )
    )

    blind_spots = [*benchmark_blind_spots, *((oa_payload or {}).get("blind_spots") or [])]
    root_causes = (oa_payload or {}).get("root_causes") or []
    p4_status = _SKIP
    p4_summary = "未提供 benchmark blind spots 或 OA run"
    if benchmark_blind_spots or oa_payload:
        p4_status = _PASS
        p4_summary = "benchmark / OA 已产出 blind spots / root causes / playbook"
        if len(blind_spots) >= 3:
            p4_status = _WARN
            p4_summary = "benchmark / OA blind spots 偏多，发布判断需要保守"
    gate_results.append(
        _gate_entry(
            gate="P4 Blind Spot Budget",
            status=p4_status,
            summary=p4_summary,
            evidence=[
                f"blind_spots={len(blind_spots)}",
                f"root_causes={len(root_causes)}",
            ],
        )
    )

    p5_status = _SKIP
    p5_summary = "未提供 ChangeImpactRun"
    p5_blockers: list[str] = []
    if change_impact_payload:
        risk_level = str(change_impact_payload.get("risk_level") or "unknown")
        recommendation = str(change_impact_payload.get("blocking_recommendation") or "")
        p5_status = _PASS
        p5_summary = "change impact 风险可控"
        if risk_level == "high" or recommendation == "hold":
            p5_status = _FAIL
            p5_summary = "change impact 高风险，必须先定位第一个失败信号"
            p5_blockers.append("change_impact_high_risk")
        elif risk_level in {"medium", "unknown"}:
            p5_status = _WARN
            p5_summary = "change impact 需要条件性验证"
    gate_results.append(
        _gate_entry(
            gate="P5 Change Impact",
            status=p5_status,
            summary=p5_summary,
            evidence=[
                f"change_impact_run_id={(change_impact_payload or {}).get('run_id')}",
                f"risk_level={(change_impact_payload or {}).get('risk_level')}",
                f"first_failing_signal={((change_impact_payload or {}).get('first_failing_signal') or {}).get('type')}",
            ],
            blockers=p5_blockers,
        )
    )

    blockers = [blocker for gate in gate_results for blocker in gate.get("blockers") or []]
    final_status = _FAIL if any(item["status"] == _FAIL for item in gate_results) else _WARN if any(item["status"] == _WARN for item in gate_results) else _PASS
    recommendation = "hold"
    if final_status == _PASS:
        recommendation = "canary"
    elif final_status == _WARN:
        recommendation = "hold_with_conditions"

    return {
        "run_id": f"release-gate-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "final_status": final_status,
        "recommendation": recommendation,
        "gate_results": gate_results,
        "blockers": blockers,
        "blind_spots": blind_spots,
        "latest_runs": {
            "benchmark_run_id": benchmark_manifest.get("run_id"),
            "om_run_id": (om_payload or {}).get("run_id"),
            "arr_run_id": (arr_payload or {}).get("run_id"),
            "aae_run_id": (aae_payload or {}).get("run_id"),
            "oa_run_id": (oa_payload or {}).get("run_id"),
            "change_impact_run_id": (change_impact_payload or {}).get("run_id"),
        },
    }
