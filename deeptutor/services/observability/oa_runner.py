from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot


def _append_root_cause(
    target: list[dict[str, Any]],
    *,
    hypothesis: str,
    confidence: str,
    supporting_evidence: list[str],
    affected_cohorts: list[str],
    suspected_change_window: str,
    next_verification_step: str,
    counterfactual: str,
    validation_cmds: list[str],
    suggested_fix_type: str,
    owner: str = "observability",
) -> None:
    target.append(
        {
            "hypothesis": hypothesis,
            "confidence": confidence,
            "supporting_evidence": supporting_evidence,
            "affected_cohorts": affected_cohorts,
            "suspected_change_window": suspected_change_window,
            "next_verification_step": next_verification_step,
            "counterfactual": counterfactual,
            "validation_cmds": validation_cmds,
            "suggested_fix_type": suggested_fix_type,
            "owner": owner,
        }
    )


def build_oa_run(
    *,
    mode: str,
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    aae_payload: dict[str, Any] | None,
    observer_payload: dict[str, Any] | None = None,
    change_impact_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"daily", "pre-release", "incident"}:
        raise ValueError(f"Unsupported OA mode: {mode}")

    release = (
        (observer_payload or {}).get("release")
        or (arr_payload or {}).get("release")
        or (om_payload or {}).get("release")
        or (aae_payload or {}).get("release")
        or get_release_lineage_snapshot()
    )
    blind_spots: list[dict[str, Any]] = []
    root_causes: list[dict[str, Any]] = []
    playbooks: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []

    if observer_payload:
        observer_coverage = observer_payload.get("data_coverage") or {}
        observer_turn_events = observer_payload.get("turn_events") or {}
        signals.append(
            {
                "kind": "observer_snapshot",
                "payload": {
                    "run_id": observer_payload.get("run_id"),
                    "data_coverage": observer_coverage,
                    "turn_events": observer_turn_events,
                    "source_runs": observer_payload.get("source_runs") or {},
                },
            }
        )
        for blind_spot in observer_payload.get("blind_spots") or []:
            if isinstance(blind_spot, dict):
                blind_spots.append(dict(blind_spot))
        error_ratio = observer_turn_events.get("error_ratio")
        if isinstance(error_ratio, (int, float)) and float(error_ratio) >= 0.05:
            _append_root_cause(
                root_causes,
                hypothesis="真实 turn 失败率偏高，优先从 turn event log 回放失败 turn，而不是只看聚合分数。",
                confidence="high" if float(error_ratio) >= 0.1 else "medium",
                supporting_evidence=[
                    f"observer.turn_events.error_ratio={error_ratio}",
                    f"observer.turn_events.error_count={observer_turn_events.get('error_count')}",
                    f"observer.turn_events.event_count={observer_turn_events.get('event_count')}",
                ],
                affected_cohorts=["interactive_turns"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="读取 ObserverSnapshot 的 turn_events，再按 turn_id/trace_id 回放失败样本。",
                counterfactual="若 turn event error_ratio < 0.05，则更可能是评测样本或表面覆盖问题。",
                validation_cmds=[
                    "python3.11 scripts/run_observer_snapshot.py",
                    "python3.11 scripts/run_oa.py --mode incident",
                ],
                suggested_fix_type="收权",
            )
        coverage_ratio = observer_coverage.get("coverage_ratio")
        if isinstance(coverage_ratio, (int, float)) and float(coverage_ratio) < 0.5:
            blind_spots.append(
                {
                    "type": "low_observer_snapshot_coverage",
                    "severity": "high",
                    "evidence": {"coverage_ratio": coverage_ratio},
                }
            )

    if change_impact_payload:
        first_signal = change_impact_payload.get("first_failing_signal") or {}
        signals.append(
            {
                "kind": "change_impact",
                "payload": {
                    "run_id": change_impact_payload.get("run_id"),
                    "risk_level": change_impact_payload.get("risk_level"),
                    "risk_score": change_impact_payload.get("risk_score"),
                    "changed_domains": change_impact_payload.get("changed_domains") or [],
                    "first_failing_signal": first_signal,
                    "required_gates": change_impact_payload.get("required_gates") or [],
                },
            }
        )
        if str(change_impact_payload.get("risk_level") or "") == "high":
            _append_root_cause(
                root_causes,
                hypothesis="变更影响风险偏高，优先沿 ChangeImpactRun 的 changed_domains 与 first_failing_signal 定位。",
                confidence="high",
                supporting_evidence=[
                    f"change_impact.risk_score={change_impact_payload.get('risk_score')}",
                    f"change_impact.first_failing_signal={first_signal.get('type')}",
                    f"change_impact.domains={[item.get('domain') for item in change_impact_payload.get('changed_domains') or []]}",
                ],
                affected_cohorts=[
                    str(item.get("domain") or "")
                    for item in change_impact_payload.get("changed_domains") or []
                    if isinstance(item, dict)
                ]
                or ["unknown"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="先执行 ChangeImpactRun 的 required_gates，再按第一个失败信号回放对应 case。",
                counterfactual="若 change impact risk 不高且 first_failing_signal 为 none，则本轮更可能是低风险变更或观测盲区。",
                validation_cmds=list(change_impact_payload.get("next_commands") or []),
                suggested_fix_type="收权",
            )

    if not om_payload:
        blind_spots.append({"type": "missing_om_snapshot", "severity": "high"})
    else:
        health_summary = om_payload.get("health_summary") or {}
        smoke_checks = om_payload.get("smoke_checks") or []
        signals.append({"kind": "om_health_summary", "payload": health_summary})
        if health_summary.get("ready") is not True:
            _append_root_cause(
                root_causes,
                hypothesis="运行态 readiness 未完成，当前候选版本不具备稳定接流量前提。",
                confidence="high",
                supporting_evidence=["om.health_summary.ready=false"],
                affected_cohorts=["all"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="先查 readyz checks 和关键依赖启动状态。",
                counterfactual="若 readiness 为 true，后续失败更可能落到语义或表面链路。",
                validation_cmds=[
                    "curl -fsS http://127.0.0.1:8001/readyz | jq",
                    "curl -fsS http://127.0.0.1:8001/metrics | jq '.readiness'",
                ],
                suggested_fix_type="收权",
            )
        unified_ws_smoke_ok = health_summary.get("unified_ws_smoke_ok")
        if unified_ws_smoke_ok is False:
            smoke_entry = next(
                (item for item in smoke_checks if str(item.get("name") or "").strip() == "unified_ws_smoke"),
                {},
            )
            _append_root_cause(
                root_causes,
                hypothesis="主聊天链路 `/api/v1/ws` 无法完成真实 turn，优先怀疑 LLM 凭证、主 provider 配置或 turn 主路径异常。",
                confidence="high",
                supporting_evidence=list(smoke_entry.get("evidence") or [])
                or [str(health_summary.get("unified_ws_smoke_summary") or "unified_ws_smoke_failed")],
                affected_cohorts=["all_interactive_turns"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="先复跑 unified ws smoke，并核查 OPENAI_API_KEY / provider 配置是否为真实可用值。",
                counterfactual="若 unified ws smoke 能完成 done，则 P0 更可能是局部 surface 或评测层问题。",
                validation_cmds=[
                    "python3.11 scripts/run_unified_ws_smoke.py --api-base-url http://127.0.0.1:8001 --message '请只回复ok。'",
                    "curl -fsS http://127.0.0.1:8001/readyz | jq",
                ],
                suggested_fix_type="收权",
            )

        if health_summary.get("turn_first_render_ratio") in (None,):
            blind_spots.append({"type": "missing_surface_coverage", "severity": "medium"})

    if not arr_payload:
        blind_spots.append({"type": "missing_arr_run", "severity": "high"})
    else:
        arr_summary = arr_payload.get("summary") or {}
        baseline_diff = arr_payload.get("baseline_diff") or {}
        signals.append({"kind": "arr_summary", "payload": arr_summary})
        if baseline_diff.get("regressions"):
            _append_root_cause(
                root_causes,
                hypothesis="当前版本出现新的回归 case，优先怀疑最近 release lineage 下的 runtime 或 prompt 变化。",
                confidence="high",
                supporting_evidence=[
                    f"arr.regressions={len(baseline_diff.get('regressions') or [])}",
                    f"arr.pass_rate_delta={baseline_diff.get('pass_rate_delta')}",
                ],
                affected_cohorts=["regression_tier", "gate_stable"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="逐条回放 regression cases，并比对 release lineage 与变更窗口。",
                counterfactual="若 baseline diff 无 regressions，则更可能是单点 infra 波动。",
                validation_cmds=[
                    "python3.11 scripts/run_arr_lite.py --mode lite --baseline <baseline.json>",
                ],
                suggested_fix_type="减法",
            )

        long_dialog_summary = next(
            (item for item in arr_payload.get("suite_summaries") or [] if str(item.get("suite") or "").startswith("long-dialog")),
            None,
        )
        if long_dialog_summary and int(long_dialog_summary.get("skipped") or 0) > 0:
            blind_spots.append(
                {
                    "type": "long_dialog_skipped",
                    "severity": "medium",
                    "evidence": long_dialog_summary,
                }
            )

    if not aae_payload:
        blind_spots.append({"type": "missing_aae_run", "severity": "medium"})
    else:
        scorecard = aae_payload.get("scorecard") or {}
        signals.append({"kind": "aae_scorecard", "payload": scorecard})
        continuity = ((scorecard.get("continuity_score") or {}).get("value"))
        satisfaction = ((scorecard.get("paid_student_satisfaction_score") or {}).get("value"))
        if isinstance(continuity, (int, float)) and continuity < 0.8:
            _append_root_cause(
                root_causes,
                hypothesis="多轮承接能力偏弱，active object 或 long-dialog continuity 仍有断裂。",
                confidence="medium",
                supporting_evidence=[f"aae.continuity_score={continuity}"],
                affected_cohorts=["followup", "long_dialog"],
                suspected_change_window=str(release.get("release_id") or "unknown"),
                next_verification_step="重点回放 context-orchestration 与 long-dialog failures。",
                counterfactual="若 continuity_score >= 0.8，则更可能是表面体验或 grounding 问题。",
                validation_cmds=[
                    "python3.11 scripts/run_arr_lite.py --mode lite",
                ],
                suggested_fix_type="归一化",
            )
        if isinstance(satisfaction, (int, float)) and satisfaction < 0.85:
            playbooks.append(
                {
                    "title": "paid-student-satisfaction-proxy-drop",
                    "owner": "product+runtime",
                    "steps": [
                        "核查 surface_render_score 与 latency_class，先排除表面/时延问题。",
                        "再核查 correctness 和 continuity proxy，确认是否是教学体验而非语义错误。",
                    ],
                }
            )

    if not playbooks:
        playbooks.append(
            {
                "title": "default-pre-release-check",
                "owner": "observability",
                "steps": [
                    "先看 P0-P4 哪一级阻塞。",
                    "若是 blind spot，优先补证据链，不直接做语义补丁。",
                    "若是 regressions，回放 baseline diff 中的新增失败。",
                ],
            }
        )

    run_id = f"oa-{mode}-{int(time.time())}"
    return {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "release": release,
        "health_summary": (om_payload or {}).get("health_summary") or {},
        "raw_evidence_bundle": {
            "observer_snapshot_run_id": (observer_payload or {}).get("run_id"),
            "change_impact_run_id": (change_impact_payload or {}).get("run_id"),
            "om_run_id": (om_payload or {}).get("run_id"),
            "arr_run_id": (arr_payload or {}).get("run_id"),
            "aae_run_id": (aae_payload or {}).get("run_id"),
        },
        "blind_spots": blind_spots,
        "root_causes": root_causes,
        "change_impact": change_impact_payload,
        "repair_playbooks": playbooks,
        "signals": signals,
        "run_history_entry": {
            "mode": mode,
            "root_cause_count": len(root_causes),
            "blind_spot_count": len(blind_spots),
        },
    }
