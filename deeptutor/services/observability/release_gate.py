from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot
from deeptutor.services.observability.runtime_authority import release_identity_matches
from deeptutor.services.runtime_env import env_flag

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_SKIP = "SKIP"
_INCOMPLETE_RELEASE_VALUES = {"", "unknown", "unset", "none"}
_RELEASE_SPINE_KEYS = (
    "release_id",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
)
MINIMUM_RELEASE_BENCHMARK_SUITES = (
    "pr_gate_core",
    "regression_watch",
    "real_exam_quality_spine",
)


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


def _gate_relevant_case(item: dict[str, Any]) -> bool:
    tier = str(item.get("case_tier") or "").strip()
    return bool(item.get("gate_eligible")) or tier in {"gate_stable", "regression_tier"}


def _is_long_dialog_case(item: dict[str, Any]) -> bool:
    return any(
        str(item.get(field) or "").startswith("long-dialog")
        for field in ("suite", "source_suite")
    )


def _long_dialog_live_ws_ready(
    *,
    case_results: list[dict[str, Any]],
    execution_context: dict[str, Any],
) -> bool:
    long_dialog_suites = {
        str(item.get(field) or "").strip()
        for item in case_results
        for field in ("suite", "source_suite")
        if str(item.get(field) or "").strip().startswith("long-dialog")
    }
    if not long_dialog_suites:
        return True
    api_base_url = str(execution_context.get("api_base_url") or "").strip()
    suite_modes = execution_context.get("suite_execution_modes") or {}
    if not api_base_url:
        return False
    return all(suite_modes.get(suite) == "live_ws" for suite in long_dialog_suites)


def _required_readiness_checks(
    *,
    change_impact_payload: dict[str, Any] | None,
    readiness_rows: list[dict[str, Any]],
) -> list[str]:
    explicit = [
        str(item or "").strip()
        for item in ((change_impact_payload or {}).get("required_readiness_checks") or [])
        if str(item or "").strip()
    ]
    if explicit:
        return sorted(dict.fromkeys(explicit))
    derived = [
        str(row.get("check_id") or "").strip()
        for row in readiness_rows
        if bool(row.get("required", True)) and str(row.get("check_id") or "").strip()
    ]
    return sorted(dict.fromkeys(derived))


def _has_release_value(release: dict[str, Any], key: str) -> bool:
    value = str(release.get(key) or "").strip().lower()
    if value in _INCOMPLETE_RELEASE_VALUES:
        return False
    if key in {"release_id", "git_sha"} and "unknown" in value:
        return False
    return True


def _is_complete_release_lineage(release: dict[str, Any]) -> bool:
    return all(
        _has_release_value(release, key)
        for key in (
            "release_id",
            "git_sha",
            "deployment_environment",
            "prompt_version",
            "ff_snapshot_hash",
            "git_dirty",
            "deploy_manifest_hash",
        )
    )


def _select_release_lineage(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    candidates = [
        release
        for payload in payloads
        for release in [(payload or {}).get("release")]
        if isinstance(release, dict) and release
    ]
    fallback = get_release_lineage_snapshot()
    if isinstance(fallback, dict) and fallback:
        candidates.append(fallback)
    for release in candidates:
        if _is_complete_release_lineage(release):
            return release
    return candidates[0] if candidates else get_release_lineage_snapshot()


def _is_prerelease_plan_placeholder(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    warnings = {str(item) for item in payload.get("warnings") or []}
    return (
        str(payload.get("scope_mode") or "") == "prerelease_unscoped"
        and "plan_completion_audit_not_configured_for_prerelease" in warnings
    )


def _payload_release(payload: dict[str, Any] | None) -> dict[str, Any]:
    release = (payload or {}).get("release")
    if isinstance(release, dict) and release:
        return release
    release_spine = (payload or {}).get("release_spine")
    return release_spine if isinstance(release_spine, dict) else {}


def _same_release_spine(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return release_identity_matches(expected, actual)


def _release_spine_label(release: dict[str, Any]) -> str:
    values = [
        str(release.get(key) or "").strip()
        for key in ("release_id", "git_sha", "deploy_manifest_hash", "ff_snapshot_hash")
        if str(release.get(key) or "").strip()
    ]
    return "|".join(values) or "unknown"


def _payload_git_sha(payload: dict[str, Any] | None) -> str:
    release = _payload_release(payload) or ((payload or {}).get("release_spine") or {})
    return str(release.get("git_sha") or "").strip()


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _stale_input_names(
    *,
    current_release: dict[str, Any],
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    benchmark_payload: dict[str, Any] | None,
    incident_payload: dict[str, Any] | None,
    aae_payload: dict[str, Any] | None,
    oa_payload: dict[str, Any] | None,
    change_impact_payload: dict[str, Any] | None,
    plan_completion_payload: dict[str, Any] | None,
) -> list[str]:
    current_git_sha = str((current_release or {}).get("git_sha") or "").strip()
    if not current_git_sha or "unknown" in current_git_sha.lower():
        return []
    stale: list[str] = []
    for name, payload in (
        ("om", om_payload),
        ("arr", arr_payload),
        ("benchmark", benchmark_payload),
        ("incident", incident_payload),
        ("aae", aae_payload),
        ("oa", oa_payload),
        ("change_impact", change_impact_payload),
        ("plan_completion", plan_completion_payload),
    ):
        if payload and not release_identity_matches(current_release, _payload_release(payload)):
            stale.append(name)
    return stale


def build_release_gate_report(
    *,
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    benchmark_payload: dict[str, Any] | None = None,
    incident_payload: dict[str, Any] | None = None,
    aae_payload: dict[str, Any] | None,
    oa_payload: dict[str, Any] | None,
    change_impact_payload: dict[str, Any] | None = None,
    plan_completion_payload: dict[str, Any] | None = None,
    readiness_payload: dict[str, Any] | None = None,
    release: dict[str, Any] | None = None,
    quality_evidence_required: bool = False,
) -> dict[str, Any]:
    if _is_prerelease_plan_placeholder(plan_completion_payload):
        plan_completion_payload = None
    resolved_release = dict(release or {}) or _select_release_lineage(arr_payload, om_payload, aae_payload, oa_payload)
    gate_results: list[dict[str, Any]] = []

    om_health = (om_payload or {}).get("health_summary") or {}
    release_complete = _is_complete_release_lineage(resolved_release)
    git_dirty_value = str(resolved_release.get("git_dirty") or "").strip().lower()
    release_dirty = git_dirty_value in {"1", "true", "yes", "on"}
    unified_ws_smoke_ok = om_health.get("unified_ws_smoke_ok")
    ws_main_path_healthy = unified_ws_smoke_ok is True
    orphaned_turns = int(om_health.get("orphaned_turns") or 0)
    readiness_rows = (readiness_payload or {}).get("rows") or []
    readiness_rows_by_check = {
        str(item.get("check_id") or "").strip(): item
        for item in readiness_rows
        if str(item.get("check_id") or "").strip()
    }
    required_readiness = _required_readiness_checks(
        change_impact_payload=change_impact_payload,
        readiness_rows=readiness_rows,
    )
    readiness_missing_checks = [
        check_id for check_id in required_readiness if check_id not in readiness_rows_by_check
    ] if readiness_payload is not None else []
    readiness_non_pass_rows = [
        row
        for check_id, row in readiness_rows_by_check.items()
        if check_id in required_readiness
        and bool(row.get("required", True))
        and str(row.get("status") or "").upper() != _PASS
    ] if readiness_payload is not None else []
    readiness_blockers = _unique_strings(
        [
            *[
                blocker
                for row in readiness_non_pass_rows
                for blocker in (row.get("blockers") or [f"{row.get('check_id')}_not_pass"])
            ],
            *[f"{check_id}_missing" for check_id in readiness_missing_checks],
        ]
    )
    p0_blockers = [
        *([] if om_health.get("ready") is True and release_complete else ["runtime_or_release_lineage_incomplete"]),
        *(["runtime_release_dirty"] if release_dirty else []),
        *(
            []
            if ws_main_path_healthy
            else ["ws_main_path_unhealthy" if unified_ws_smoke_ok is False else "ws_main_path_unverified"]
        ),
        *(["turn_in_flight_without_ws_subscriber"] if orphaned_turns > 0 else []),
        *readiness_blockers,
    ]
    p0_ready = not p0_blockers
    if p0_ready:
        p0_summary = "readyz、release lineage 与 ws 主链路可用"
    elif {"ws_main_path_unhealthy", "ws_main_path_unverified"}.intersection(p0_blockers):
        p0_summary = "runtime readiness、release lineage、release readiness 或 ws 主链路异常"
    else:
        p0_summary = "runtime readiness、release lineage、dirty state 或 release readiness 不完整"
    gate_results.append(
        _gate_entry(
            gate="P0 Runtime",
            status=_PASS if p0_ready else _FAIL,
            summary=p0_summary,
            evidence=[
                f"ready={om_health.get('ready')}",
                f"release_complete={release_complete}",
                f"git_dirty={resolved_release.get('git_dirty')}",
                f"unified_ws_smoke_ok={unified_ws_smoke_ok}",
                f"orphaned_turns={orphaned_turns}",
                f"required_readiness_checks={required_readiness}",
                f"readiness_required_failures={len(readiness_non_pass_rows) + len(readiness_missing_checks)}",
                f"readiness_missing_checks={','.join(readiness_missing_checks) if readiness_missing_checks else 'none'}",
                f"readiness_blockers={','.join(readiness_blockers) if readiness_blockers else 'none'}",
            ],
            blockers=[] if p0_ready else p0_blockers,
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
                f"prompt_version={resolved_release.get('prompt_version')}",
                f"ff_snapshot_hash={resolved_release.get('ff_snapshot_hash')}",
            ],
        )
    )

    canonical_benchmark_manifest = (benchmark_payload or {}).get("run_manifest") or {}
    embedded_benchmark_manifest = (arr_payload or {}).get("benchmark_run_manifest") or {}
    benchmark_manifest = canonical_benchmark_manifest or embedded_benchmark_manifest
    benchmark_case_results = (benchmark_payload or {}).get("case_results") or (arr_payload or {}).get("benchmark_case_results") or []
    benchmark_blind_spots = (benchmark_payload or {}).get("blind_spots") or (arr_payload or {}).get("blind_spots") or []
    runtime_incidents = (incident_payload or {}).get("runtime_incidents") or []
    blocking_runtime_incidents = [item for item in runtime_incidents if bool(item.get("release_blocking"))]
    arr_summary = (arr_payload or {}).get("summary") or {}
    benchmark_summary = (benchmark_payload or {}).get("summary") or {}
    arr_diff = (benchmark_payload or {}).get("baseline_diff") or (arr_payload or {}).get("baseline_diff") or {}
    execution_context = (
        (benchmark_payload or {}).get("execution_context")
        or ((benchmark_payload or {}).get("legacy") or {}).get("execution_context")
        or (arr_payload or {}).get("execution_context")
        or {}
    )
    requested_suites = [
        str(item)
        for item in (benchmark_manifest.get("requested_suites") or [])
        if str(item).strip()
    ]
    missing_required_suites = [
        suite
        for suite in MINIMUM_RELEASE_BENCHMARK_SUITES
        if suite not in set(requested_suites)
    ]
    benchmark_pass_rate = _benchmark_pass_rate(benchmark_case_results) if benchmark_case_results else arr_summary.get("pass_rate")
    if benchmark_pass_rate is None:
        benchmark_pass_rate = benchmark_summary.get("pass_rate")
    new_critical_regressions = len(arr_diff.get("regressions") or []) + len(arr_diff.get("new_failures") or [])
    gate_failures = [
        item for item in benchmark_case_results
        if str(item.get("status") or "").upper() == _FAIL and _gate_relevant_case(item)
    ]
    gate_skips = [
        item for item in benchmark_case_results
        if str(item.get("status") or "").upper() == _SKIP and _gate_relevant_case(item)
    ]
    live_ws_ready = _long_dialog_live_ws_ready(
        case_results=benchmark_case_results,
        execution_context=execution_context,
    )
    p2_status = _FAIL
    p2_summary = "未提供 benchmark / ARR run"
    p2_blockers: list[str] = ["missing_benchmark_arr"]
    if arr_payload or benchmark_payload:
        pass_rate = benchmark_pass_rate
        has_new_critical = new_critical_regressions > 0
        p2_blockers = []
        if not canonical_benchmark_manifest.get("run_id"):
            p2_status = _FAIL
            p2_summary = "canonical benchmark row missing"
            p2_blockers.append("canonical_benchmark_missing")
        else:
            p2_status = _PASS
            p2_summary = "benchmark 当前无新增 regression"
        if p2_status != _FAIL and gate_failures:
            p2_status = _FAIL
            p2_summary = "benchmark gate/regression tier 存在失败"
            p2_blockers.append("benchmark_gate_failure")
        if p2_status != _FAIL and gate_skips:
            p2_status = _FAIL
            p2_summary = "benchmark gate/regression tier 存在 SKIP"
            p2_blockers.append("benchmark_gate_skip")
        if p2_status != _FAIL and not live_ws_ready:
            p2_status = _FAIL
            p2_summary = "long-dialog 未通过真实 /api/v1/ws 执行"
            p2_blockers.append("long_dialog_not_live_ws")
        if p2_status != _FAIL and quality_evidence_required and missing_required_suites:
            p2_status = _FAIL
            p2_summary = "benchmark 未覆盖最小 release 质量套件"
            p2_blockers.append("benchmark_minimum_suite_missing")
        if p2_status != _FAIL and has_new_critical:
            p2_status = _FAIL
            p2_summary = "benchmark 出现新增 regression 或 new failure"
            p2_blockers.append("new_benchmark_regression")
        elif p2_status != _FAIL and blocking_runtime_incidents:
            p2_status = _FAIL
            p2_summary = "incident replay 捕获到 blocking runtime incident"
            p2_blockers.append("incident_replay_runtime_regression")
        elif p2_status != _FAIL and isinstance(pass_rate, (int, float)) and float(pass_rate) < 0.9:
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
                f"required_suites={list(MINIMUM_RELEASE_BENCHMARK_SUITES)}",
                f"missing_required_suites={missing_required_suites}",
                f"quality_evidence_required={quality_evidence_required}",
                f"pass_rate={benchmark_pass_rate}",
                f"regressions={new_critical_regressions}",
                f"new_failures={len(arr_diff.get('new_failures') or [])}",
                f"gate_failures={len(gate_failures)}",
                f"gate_skips={len(gate_skips)}",
                f"long_dialog_live_ws={live_ws_ready}",
                f"incident_run_id={((incident_payload or {}).get('run_manifest') or {}).get('run_id')}",
                f"blocking_runtime_incidents={len(blocking_runtime_incidents)}",
            ],
            blockers=p2_blockers,
        )
    )

    aae_scorecard = (aae_payload or {}).get("scorecard") or {}
    aae_composite = (aae_payload or {}).get("composite") or {}
    aae_coverage = (aae_payload or {}).get("coverage_summary") or {}
    p3_status = _FAIL if quality_evidence_required else _SKIP
    p3_summary = "未提供 AAE run；当前质量 gate 要求 current-release AAE" if quality_evidence_required else "未提供 AAE run"
    p3_blockers = ["missing_aae_run"] if quality_evidence_required else []
    if aae_payload:
        satisfaction_score = aae_scorecard.get("paid_student_satisfaction_score") or {}
        proxy_heavy = bool(satisfaction_score.get("is_proxy"))
        satisfaction_available = "paid_student_satisfaction_score" in aae_scorecard
        feedback_total = int(aae_coverage.get("feedback_total") or 0)
        feedback_status = str(aae_coverage.get("feedback_storage_status") or "").strip()
        composite_value = aae_composite.get("value")
        p3_status = _PASS
        p3_summary = "AAE 关键分数可用"
        p3_blockers = []
        if satisfaction_available and not proxy_heavy:
            p3_summary = "AAE 已接入真实满意度反馈"
        elif feedback_status and feedback_status != "ok":
            p3_status = _WARN
            p3_summary = "AAE 真实满意度反馈通道不可用"
        elif feedback_status == "ok" and feedback_total <= 0:
            p3_status = _WARN
            p3_summary = "AAE 已接入真实满意度反馈通道，但当前窗口无样本"
        elif proxy_heavy:
            p3_summary = "AAE pre-launch proxy 已覆盖；真实满意度作为上线后观测项"
        if isinstance(composite_value, (int, float)) and composite_value < 0.75:
            p3_status = _FAIL
            p3_summary = "AAE composite 低于最低门槛"
            p3_blockers = ["aae_composite_below_floor"]
    gate_results.append(
        _gate_entry(
            gate="P3 AAE",
            status=p3_status,
            summary=p3_summary,
            evidence=[
                f"composite={aae_composite.get('value')}",
                f"coverage_ratio={aae_composite.get('coverage_ratio')}",
                f"proxy_paid_satisfaction={((aae_scorecard.get('paid_student_satisfaction_score') or {}).get('is_proxy'))}",
                f"feedback_storage_status={aae_coverage.get('feedback_storage_status')}",
                f"feedback_total={aae_coverage.get('feedback_total')}",
                f"quality_evidence_required={quality_evidence_required}",
            ],
            blockers=p3_blockers,
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

    p6_status = _FAIL
    p6_summary = "未提供 PlanCompletionAudit"
    p6_blockers: list[str] = ["plan_completion_audit_missing"]
    plan_summary = (plan_completion_payload or {}).get("summary") or {}
    if plan_completion_payload:
        plan_release = _payload_release(plan_completion_payload)
        p6_blockers = []
        audit_status = str(plan_completion_payload.get("status") or "").strip().upper()
        if not _same_release_spine(resolved_release, plan_release):
            p6_status = _FAIL
            p6_summary = "PlanCompletionAudit 不属于当前 release spine"
            p6_blockers = ["plan_completion_audit_stale_release"]
        elif audit_status == _FAIL:
            p6_status = _FAIL
            p6_summary = "plan items 存在未完成项"
            p6_blockers = list(plan_completion_payload.get("blockers") or ["plan_item_not_done"])
        elif audit_status in {_WARN, "PARTIAL", "UNVERIFIABLE"}:
            p6_status = _WARN
            p6_summary = "plan items 存在部分完成或无法本地核验证据"
        elif audit_status != _PASS:
            p6_status = _WARN
            p6_summary = "PlanCompletionAudit 状态未知，需要人工复核"
        else:
            p6_status = _PASS
            p6_summary = "plan items 已对照 diff / evidence"
    gate_results.append(
        _gate_entry(
            gate="P6 Plan Completion",
            status=p6_status,
            summary=p6_summary,
            evidence=[
                f"plan_completion_run_id={(plan_completion_payload or {}).get('run_id')}",
                f"scope_mode={(plan_completion_payload or {}).get('scope_mode')}",
                f"plans={plan_summary.get('plan_count')}",
                f"total={plan_summary.get('total')}",
                f"scoped={plan_summary.get('scoped')}",
                f"done={plan_summary.get('done')}",
                f"partial={plan_summary.get('partial')}",
                f"not_done={plan_summary.get('not_done')}",
                f"unverifiable={plan_summary.get('unverifiable')}",
                f"out_of_scope={plan_summary.get('out_of_scope')}",
                f"warnings={(plan_completion_payload or {}).get('warnings')}",
                f"expected_release={_release_spine_label(resolved_release)}",
                f"plan_release={_release_spine_label(_payload_release(plan_completion_payload))}",
            ],
            blockers=p6_blockers,
        )
    )

    blockers = [blocker for gate in gate_results for blocker in gate.get("blockers") or []]
    final_status = _FAIL if any(item["status"] == _FAIL for item in gate_results) else _WARN if any(item["status"] == _WARN for item in gate_results) else _PASS
    recommendation = "hold"
    if final_status == _PASS:
        recommendation = "canary"
    elif final_status == _WARN:
        recommendation = "hold_with_conditions"
    stale_inputs = _stale_input_names(
        current_release=dict(release or {}) or get_release_lineage_snapshot(),
        om_payload=om_payload,
        arr_payload=arr_payload,
        benchmark_payload=benchmark_payload,
        incident_payload=incident_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
        change_impact_payload=change_impact_payload,
        plan_completion_payload=plan_completion_payload,
    )
    verdict = "STALE" if stale_inputs else "TRUSTED"
    if stale_inputs:
        blockers.append("artifact_release_stale_vs_head")
        if final_status == _PASS:
            final_status = _WARN
        recommendation = "hold"

    return {
        "run_id": f"release-gate-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": resolved_release,
        "verdict": verdict,
        "stale_inputs": stale_inputs,
        "final_status": final_status,
        "recommendation": recommendation,
        "gate_results": gate_results,
        "blockers": blockers,
        "blind_spots": blind_spots,
        "latest_runs": {
            "benchmark_run_id": canonical_benchmark_manifest.get("run_id"),
            "om_run_id": (om_payload or {}).get("run_id"),
            "arr_run_id": (arr_payload or {}).get("run_id"),
            "aae_run_id": (aae_payload or {}).get("run_id"),
            "oa_run_id": (oa_payload or {}).get("run_id"),
            "change_impact_run_id": (change_impact_payload or {}).get("run_id"),
            "plan_completion_run_id": (plan_completion_payload or {}).get("run_id"),
            "readiness_run_id": (readiness_payload or {}).get("run_id"),
            "incident_run_id": ((incident_payload or {}).get("run_manifest") or {}).get("run_id"),
        },
        "readiness_summary": {
            "required_checks": list(required_readiness),
            "missing_checks": readiness_missing_checks,
            "non_pass_checks": [str(row.get("check_id") or "") for row in readiness_non_pass_rows],
            "blockers": readiness_blockers,
        },
    }


# --- G3: canonical registry publish flow (master plan §0.26 / M33-ACT) ---
# Default OFF. Publishing the canonical registry (release_candidate -> published) is the production
# answer-authority flip; it requires a deliberate, instantly-revocable authorization, never an
# inferred one.
PUBLISH_ENABLED_FLAG = "LUBAN_REGISTRY_PUBLISH_ENABLED"


def publish_canonical_registry(
    manifest: dict[str, Any],
    supply_root: "str | Path",
    *,
    release_gate_report: dict[str, Any],
    authorized: bool,
    published_at: str,
    superseded_version: str | None = None,
) -> dict[str, Any]:
    """Promote a SIGNED ``release_candidate`` canonical manifest to ``status=published`` (M33-ACT G3).

    Triple fail-closed gate — ALL must hold or NOTHING is signed (manifest stays release_candidate):
      1. env flag ``LUBAN_REGISTRY_PUBLISH_ENABLED`` is on (default OFF -> instantly revocable)
      2. explicit ``authorized=True`` from the caller (per-gate owner sign-off)
      3. ``release_gate_report`` is a PASS *and* TRUSTED (not stale vs HEAD)
    then ``verify_manifest`` (recompute manifest hash/signature + re-check every shard's bytes on disk)
    before any promotion. On any failure returns a refusal ``{published: False, reason, manifest}``;
    only full authorization returns ``{published: True, manifest: <published>, rollback_pointer, ...}``.
    Authority is granted ONLY here by the explicit gates — never inferred from the bundle/manifest.
    """
    from pathlib import Path

    from deeptutor.services.construction_grading import canonical_knowledge_manifest as ckm

    def _refusal(reason: str) -> dict[str, Any]:
        return {"published": False, "reason": reason, "manifest": dict(manifest)}

    if supply_root is None:  # structured refusal instead of an uncaught Path(None) TypeError
        return _refusal("supply_root_missing")
    if not (manifest.get("shards") or []):  # an empty manifest is not a publishable authority
        return _refusal("manifest_has_no_shards")
    if not env_flag(PUBLISH_ENABLED_FLAG, default=False):
        return _refusal("publish_disabled")
    if authorized is not True:  # strict: only literal True authorizes (truthy values must not pass)
        return _refusal("not_authorized")
    report = release_gate_report or {}
    if str(report.get("final_status") or "").upper() != _PASS:
        return _refusal("release_gate_not_pass")
    if str(report.get("verdict") or "").upper() != "TRUSTED":
        return _refusal("release_gate_stale")
    ok, vreason = ckm.verify_manifest(manifest, Path(supply_root))
    if not ok:
        return _refusal(f"manifest_verify_failed:{vreason}")
    # Defense-in-depth: verify_manifest only checks each shard's manifest-pinned self-reported hash. For
    # a production publish, additionally re-verify each records-based shard's CONTENT (recompute records
    # hash + signature) via the lane signer's own verifier, so a records-tampered shard whose
    # self-reported hash still matches the pin cannot be published. Non-records lanes (concept_registry /
    # taxonomy index) carry their own structure and stay covered by the manifest pin + the runtime
    # resolver's fail-closed verification at consumption.
    import json as _json

    from deeptutor.services.construction_grading.full_knowledge_compiler import verify_lane_bundle

    for s in manifest.get("shards") or []:
        sp = Path(supply_root) / str(s.get("path") or "")
        try:
            sdoc = _json.loads(sp.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return _refusal(f"shard_unreadable:{s.get('lane')}")
        if isinstance(sdoc.get("records"), list) and not verify_lane_bundle(
            sdoc, str(s.get("namespace") or "")
        ):
            return _refusal(f"shard_content_tamper:{s.get('lane')}")
    try:
        published = ckm.promote_to_published(
            manifest, superseded_version=superseded_version, published_at=published_at
        )
    except ValueError as exc:
        return _refusal(f"promote_rejected:{exc}")
    return {
        "published": True,
        "reason": "ok",
        "manifest": published,
        "rollback_pointer": published.get("rollback_pointer"),
        "superseded_version": superseded_version,
        "published_at": published_at,
    }
