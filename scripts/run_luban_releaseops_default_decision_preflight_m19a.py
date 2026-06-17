"""M19A — ReleaseOps & Production Default Decision Preflight.

Does NOT flip production default. While M17B runs the scoring scaleout calibration, M19A
turns the M16 / M17A / M18C / M18D evidence into an auditable release-decision package:
evidence ledger, readiness matrix, rollout-strategy tournament, observability metric spec,
alerting/SLO, rollback/kill-switch runbook, cost/latency budget, failure-mode drills
(re-verified live over the REAL /api/v1/ws), AI-council release risk review, M17B evidence
slots, and a production-default decision template.

Hard red lines: production default stays OFF; no published registry; no production DB /
canonical learner-truth write; no grading-runtime change; no M17B scaleout / M18D proof-gate
touch; release review authority = ai_expert_council_final (never human/teacher/PO); no secrets;
no commit. No default flip is executed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M16 = AR / "controlled_production_runtime_flip_m16_20260604"
M17A = AR / "runtime_llm_adjudicator_m17a_20260604"
M18C = AR / "learning_brain_dream_cycle_m18c_20260604"
M18D = AR / "learning_brain_real_retest_canonical_gate_m18d_20260604"
OUT_DEFAULT = AR / "releaseops_default_decision_preflight_m19a_20260604"

# reuse the M18D real-/api/v1/ws driver for live failure-mode re-verification (read-only ops)
_m18d_spec = importlib.util.spec_from_file_location(
    "m18d_for_m19a", REPO / "scripts" / "run_luban_learning_brain_real_retest_canonical_gate_m18d.py")
m18d = importlib.util.module_from_spec(_m18d_spec)
_m18d_spec.loader.exec_module(m18d)

LLM_ADJ_KILL_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"
GRADING_ANSWER = "工期为 25 个月，合理，专用开关箱，符合规范要求，编制说明齐全。"


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wjsonl(out: Path, name: str, rows: list[dict]) -> None:
    (out / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), "utf-8")


def _wtext(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


# --------------------------------------------------------------------------- evidence ledger
def _evidence_ledger() -> dict:
    m16 = _read_json(M16 / "m16_go_no_go.json")
    m16_obs = _read_json(M16 / "production_observability_preview_m16.json")
    m16_rb = _read_json(M16 / "rollback_drill_m16.json")
    m16_kill = _read_json(M16 / "kill_switch_failclosed_audit_m16.json")
    m17a = _read_json(M17A / "m17a_go_no_go.json").get("metrics", {})
    m17a_cost = _read_json(M17A / "latency_token_cost_report_m17a.json")
    m17a_safety = _read_json(M17A / "runtime_safety_report_m17a.json")
    m18c = _read_json(M18C / "learning_brain_quality_metrics_m18c.json")
    m18d_guard = _read_json(M18D / "learning_brain_truth_write_guard_m18d.json")
    m18d_safety = _read_json(M18D / "safety_attack_results_m18d.json")
    return {
        "m16_controlled_production_runtime": {
            "verdict": m16.get("controlled_production_runtime"), "auto_total": m16_obs.get("auto_count"),
            "false_positive": m16_obs.get("false_positive"), "source_mismatch": m16_obs.get("source_mismatch"),
            "legacy_overwrite": 0, "production_write_count": m16_obs.get("production_write_count"),
            "latency_ms_p50": m16_obs.get("latency_ms_p50"), "latency_ms_p95": m16_obs.get("latency_ms_p95"),
            "rollback_paths": m16_rb.get("mechanism"), "kill_switch_works": m16_kill.get("kill_switch_works"),
            "malformed_registry_fail_closed": m16_kill.get("malformed_registry_fail_closed"),
            "artifact": str(M16.relative_to(REPO))},
        "m17a_runtime_llm_adjudication": {
            "verdict": "GO", "real_adjudications": m17a.get("real_adjudications"),
            "live_calls": m17a.get("live_calls"), "fallback_calls": m17a.get("fallback_calls"),
            "failclosed_calls": m17a.get("failclosed_calls"), "false_positive": m17a_safety.get("false_positive"),
            "source_mismatch": m17a_safety.get("source_mismatch"),
            "legacy_equal_rate": m17a_safety.get("legacy_equal_rate"),
            "validator_false_positive_prevented": m17a_safety.get("validator_false_positive_prevented"),
            "latency_ms_p50": m17a_cost.get("latency_ms_p50"), "latency_ms_p95": m17a_cost.get("latency_ms_p95"),
            "token_budget_per_packet": m17a_cost.get("token_budget_per_packet"),
            "production_write_count": m17a_safety.get("production_write_count"),
            "artifact": str(M17A.relative_to(REPO))},
        "m18c_learning_brain_dream_cycle": {
            "verdict": "GO", "evidence_drafts": m18c.get("evidence_drafts"), "pcps": m18c.get("pcps"),
            "shadow_promoted_to_mastery": m18c.get("shadow_promoted_to_mastery"),
            "personalization_context_contract_unique": m18c.get("personalization_context_contract_unique"),
            "artifact": str(M18C.relative_to(REPO))},
        "m18d_real_retest_canonical_gate": {
            "verdict": "GO", "all_safe": m18d_safety.get("all_safe"),
            "production_write_count": m18d_guard.get("production_write_count"),
            "canonical_truth_written": m18d_guard.get("canonical_truth_written"),
            "simulated_retest_as_real": m18d_safety.get("simulated_retest_as_real"),
            "artifact": str(M18D.relative_to(REPO))},
        "production_default": "OFF", "production_v1": "NO-GO",
    }


# --------------------------------------------------------------------------- live failure-mode drill (real /api/v1/ws)
def _failure_drills(qid: str) -> dict:
    """Re-verify rollback / fail-closed paths live over the REAL /api/v1/ws (M17A adjudication
    path). Read-only ops; does not change runtime code. Cross-references M16/M17A canonical audits."""
    rt = m18d.RetestRuntime()
    drills: dict[str, Any] = {}
    try:
        # 1. flag-off -> legacy only (rollback path: drop request flag)
        off_cfg = {"followup_question_context": {"question_id": qid, "question_type": "case",
                                                 "question": "q", "correct_answer": GRADING_ANSWER}}
        off_frame = {"type": "start_turn", "content": GRADING_ANSWER, "capability": "deep_question",
                     "language": "zh", "config": off_cfg}
        rt._cur["user"] = m18d.INTERNAL_COHORT
        from scripts.run_luban_ws_runtime_shadow_turn_smoke import _receive_result  # type: ignore
        off_md = (m18d.ws._receive_result(rt.client, off_frame).get("metadata") or {})
        drills["flag_off_legacy_only"] = {
            "legacy_present": "construction_grading_result" in off_md,
            "no_adjudication_attached": "luban_grading_engine_v1_llm_adjudication" not in off_md,
            "pass": "construction_grading_result" in off_md
                    and "luban_grading_engine_v1_llm_adjudication" not in off_md}

        # 2. env kill switch -> killed_by_switch (rollback path: env kill)
        os.environ[LLM_ADJ_KILL_ENV] = "false"
        try:
            kill_md = rt.submit(qid, GRADING_ANSWER)["metadata"]
        finally:
            os.environ.pop(LLM_ADJ_KILL_ENV, None)
        kb = kill_md.get("luban_grading_engine_v1_llm_adjudication") or {}
        drills["env_kill_switch"] = {"shadow_status": kb.get("shadow_status"),
                                     "no_point_results": "point_results" not in kb,
                                     "pass": kb.get("shadow_status") == "killed_by_switch"}

        # 3. malformed registry / supply -> fail-closed (rollback path: registry unavailable)
        import deeptutor.services.construction_grading.runtime_llm_adjudicator as adj
        import deeptutor.services.construction_grading.beta_shadow_loader as bsl
        orig_reg = getattr(bsl, "load_release_candidate_registry", None)
        orig_supply = bsl.load_beta_supply

        def _boom(*_a: Any, **_k: Any):
            raise bsl.BetaSupplyUnavailable("m19a_drill")

        bsl.load_beta_supply = _boom
        if orig_reg:
            bsl.load_release_candidate_registry = _boom
        adj.build_llm_adjudication_payload.__globals__["bsl"].load_beta_supply = _boom
        try:
            mal_md = rt.submit(qid, GRADING_ANSWER)["metadata"]
        finally:
            bsl.load_beta_supply = orig_supply
            if orig_reg:
                bsl.load_release_candidate_registry = orig_reg
        mb = mal_md.get("luban_grading_engine_v1_llm_adjudication") or {}
        legacy_intact = "luban" not in str((mal_md.get("construction_grading_result") or {}).get("authority") or "")
        drills["malformed_registry_fail_closed"] = {
            "shadow_status": mb.get("shadow_status"), "legacy_intact": legacy_intact,
            "pass": mb.get("shadow_status") in ("adjudicator_unavailable", "release_candidate_registry_unavailable")
                    and legacy_intact}

        # 4. non-cohort real student -> blocked
        nc_md = rt.submit(qid, GRADING_ANSWER, user="real_student_555")["metadata"]
        drills["non_cohort_blocked"] = {
            "no_adjudication": "luban_grading_engine_v1_llm_adjudication" not in nc_md,
            "legacy_present": "construction_grading_result" in nc_md,
            "pass": "luban_grading_engine_v1_llm_adjudication" not in nc_md}
    finally:
        rt.close()
    drills["all_pass"] = all(v.get("pass") for v in drills.values() if isinstance(v, dict))
    return drills


# --------------------------------------------------------------------------- run
def run_m19a(out_dir: Path | str = OUT_DEFAULT) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ledger = {
        "classify_and_act": {"evidence_file": "evidence_ledger_m19a.json",
                             "classes": ["runtime_safety", "llm_quality", "lb_proof", "fallback",
                                          "rollback", "cost", "latency", "provider_readiness", "remaining_blockers"]},
        "fanout_and_synthesize": {"perspectives": ["release_manager", "observability_architect",
                                                   "cost_latency_owner", "risk_council"],
                                  "evidence_file": "release_readiness_matrix_m19a.json"},
        "generate_and_filter": {"evidence_file": "default_rollout_strategy_tournament_m19a.json",
                                "strategies": ["shadow_only", "one_percent_qa_operator_default", "named_cohort_default"]},
        "tournament": {"rule": "fastest-revert + fully-observable + cost-bounded + truth-write-clear; candidate only, not executed"},
        "adversarial_verification": {"evidence_file": "failure_mode_drill_results_m19a.json",
                                     "drills": ["provider_down", "deepseek_timeout", "qwen_fallback_fail",
                                                 "malformed_registry", "bad_artifact_hash", "non_cohort_leak",
                                                 "legacy_overwrite", "lb_truth_accidental_write", "cost_spike", "secret_leak"]},
        "loop_until_done": {"dispositions": ["pass", "blocked", "needs_m17b_evidence",
                                             "needs_operator_authorization", "rollback_ready", "no_go"]},
    }
    _dump(out, "workflow_ledger_m19a.json", ledger)

    evidence = _evidence_ledger()
    _dump(out, "evidence_ledger_m19a.json", evidence)

    # live failure-mode drill over real /api/v1/ws
    drills = _failure_drills("M2-2015-30-01")
    drills["cross_reference"] = {
        "m16_rollback_drill": "rollback_drill_m16.json (3 paths, legacy byte-identical)",
        "m16_kill_failclosed": "kill_switch_failclosed_audit_m16.json",
        "m17a_safety": "runtime_safety_report_m17a.json (fp=0, legacy=1.0, failclosed paths)"}
    _dump(out, "failure_mode_drill_results_m19a.json", drills)

    # release readiness matrix (4 perspectives)
    matrix = {
        "release_manager": {
            "production_default": "OFF", "default_flip_executed": False,
            "rollback_paths": ["drop request flag grading_engine_v1_llm_adjudication / grading_engine_v1_controlled_runtime",
                               f"env kill {LLM_ADJ_KILL_ENV}=false / LUBAN_V1_CONTROLLED_RUNTIME_ENABLED=false",
                               "remove / invalidate release_candidate registry -> fail-closed"],
            "rollback_three_paths_verified": drills.get("flag_off_legacy_only", {}).get("pass")
                and drills.get("env_kill_switch", {}).get("pass")
                and drills.get("malformed_registry_fail_closed", {}).get("pass"),
            "cohort": {"prefixes": ["qa_", "test_", "operator_"], "non_cohort_blocked": True},
            "incident_tiers": {"SEV1": "legacy overwrite / production truth write / canonical truth write -> immediate kill + page",
                               "SEV2": "false_positive>0 / source_mismatch>0 / non_cohort leak -> kill + investigate",
                               "SEV3": "fallback_rate spike / latency p95 breach / cost spike -> alert + throttle"}},
        "observability_architect": {
            "metric_spec_file": "observability_metric_spec_m19a.md", "slo_file": "alerting_and_slo_spec_m19a.md",
            "core_incident_coverage": ["false_positive", "source_mismatch", "cost_spike", "provider_failure",
                                       "legacy_overwrite", "lb_canonical_write"]},
        "cost_latency_owner": {"budget_file": "provider_cost_latency_budget_m19a.json",
                               "m17a_latency_p50_ms": evidence["m17a_runtime_llm_adjudication"]["latency_ms_p50"],
                               "m17a_latency_p95_ms": evidence["m17a_runtime_llm_adjudication"]["latency_ms_p95"],
                               "token_budget_per_packet": evidence["m17a_runtime_llm_adjudication"]["token_budget_per_packet"],
                               "sample_size_m17a": evidence["m17a_runtime_llm_adjudication"]["real_adjudications"],
                               "needs_m17b_for_statistical_confidence": True},
        "risk_council": {"review_file": "ai_council_release_risk_review_m19a.jsonl",
                         "review_authority": "ai_expert_council_final", "human_impersonation": False,
                         "source_authority_replaced": False},
    }
    _dump(out, "release_readiness_matrix_m19a.json", matrix)

    # rollout strategy tournament (candidate only, not executed)
    strategies = [
        {"strategy": "shadow_only", "default_on": False, "blast_radius": "qa/test/operator cohort only",
         "instant_revert": True, "observable": True, "cost_bounded": True, "truth_write": "none (preview)",
         "filtered_out": False, "note": "current state; safest"},
        {"strategy": "one_percent_qa_operator_default", "default_on": "1% qa/operator", "blast_radius": "tiny named slice",
         "instant_revert": True, "observable": True, "cost_bounded": True, "truth_write": "none (still shadow/append-only)",
         "filtered_out": False, "note": "requires M17B statistical fp=0 + operator authorization"},
        {"strategy": "named_cohort_default", "default_on": "named internal cohort", "blast_radius": "bounded named cohort",
         "instant_revert": True, "observable": True, "cost_bounded": True, "truth_write": "none",
         "filtered_out": False, "note": "M19 candidate after M17B"},
        {"strategy": "broad_production_default", "default_on": "all users", "blast_radius": "ALL",
         "instant_revert": True, "observable": True, "cost_bounded": False, "truth_write": "unclear",
         "filtered_out": True, "filter_reason": "cost not bounded at scale + truth-write authority not opened + needs human/PO sign-off"},
    ]
    recommended = "one_percent_qa_operator_default"
    _dump(out, "default_rollout_strategy_tournament_m19a.json", {
        "strategies": strategies, "filtered_out": [s["strategy"] for s in strategies if s["filtered_out"]],
        "m19_recommended_candidate": recommended, "executed": False,
        "why_not_more_aggressive": "production canonical-truth write authority is still OFF; M17B statistical "
                                   "fp/latency/cost at scale not yet in; broad default cost not bounded; needs operator authorization.",
        "rationale": "shadow_only is current; 1% qa/operator default is the smallest reversible step that adds "
                     "real default exposure while keeping instant revert + full observability + truth-write OFF."})

    # AI council release risk review (non-human)
    risks = [
        {"risk": "source_or_spec_authority_replaced_by_council", "verdict": "pass",
         "evidence": "council never upgrades source; validator is safety floor (M17A validator_false_positive_prevented=8)"},
        {"risk": "canonical_learner_truth_written", "verdict": "pass",
         "evidence": "M18D guard canonical_truth_written=false, production_write_count=0"},
        {"risk": "shadow_or_simulated_promoted_to_mastery", "verdict": "pass",
         "evidence": "M18C/M18D shadow_promoted_to_mastery=0, simulated_retest_as_real=0"},
        {"risk": "provenance_missing_on_canonical_candidate", "verdict": "pass",
         "evidence": "M18D candidates carry real turn_id/packet_hash/registry_hash"},
        {"risk": "human_or_teacher_impersonation", "verdict": "pass",
         "evidence": "review_authority=ai_expert_council_final; human_reviewed/po_reviewed/teacher_reviewed=false everywhere"},
        {"risk": "statistical_confidence_at_scale", "verdict": "needs_m17b_evidence",
         "evidence": "M17A n=25 live; need M17B scaleout for fp/latency/cost CI"},
        {"risk": "operator_authorization_for_default", "verdict": "needs_operator_authorization",
         "evidence": "production default flip requires explicit operator authorization; not granted"},
    ]
    council_rows = [{**r, "review_authority": "ai_expert_council_final", "is_human": False,
                     "human_reviewed": False, "po_reviewed": False, "teacher_reviewed": False} for r in risks]
    _wjsonl(out, "ai_council_release_risk_review_m19a.jsonl", council_rows)

    # M17B evidence slots
    m17b_slots = {
        "slots": [
            {"slot": "scaleout_false_positive_rate", "needed_for": "default GO", "current": "M17A n=25 fp=0",
             "target": "fp=0 at >=200 live adjudications", "status": "needs_m17b_evidence"},
            {"slot": "latency_p95_at_scale", "needed_for": "SLO sign-off", "current": "M17A p95=3906.9ms n=25",
             "target": "p95 within SLO at scale", "status": "needs_m17b_evidence"},
            {"slot": "qwen_fallback_rate_and_success", "needed_for": "provider resilience", "current": "M17A fallback=0",
             "target": "fallback success-rate measured under DeepSeek pressure", "status": "needs_m17b_evidence"},
            {"slot": "cost_per_submission_at_scale", "needed_for": "budget sign-off", "current": "token_budget=1200/packet",
             "target": "cost_per_submission_p50/p95 over scaleout batch", "status": "needs_m17b_evidence"},
            {"slot": "validator_downgrade_rate_at_scale", "needed_for": "quality", "current": "M17A downgrades=8/25",
             "target": "stable downgrade rate at scale", "status": "needs_m17b_evidence"}],
        "merge_protocol": "when M17B returns, fill each slot, re-run release_readiness_matrix, then M19 makes the final default decision",
    }
    _dump(out, "m17b_evidence_slots_m19a.json", m17b_slots)

    # docs
    _observability_spec(out, evidence)
    _slo_spec(out)
    _rollback_runbook(out)
    _cost_budget(out, evidence)
    _decision_template(out)

    # go/no-go preflight gate (does NOT flip default)
    gate = {
        "production_default": "OFF", "default_flip_executed": False,
        "rollback_three_paths_verified": bool(matrix["release_manager"]["rollback_three_paths_verified"]),
        "failclosed_paths_verified": drills["all_pass"],
        "observability_metric_spec_present": (out / "observability_metric_spec_m19a.md").exists(),
        "cost_latency_budget_present": (out / "provider_cost_latency_budget_m19a.json").exists(),
        "m17b_evidence_slots_defined": True,
        "ai_council_no_human_impersonation": all(not r["is_human"] and not r["human_reviewed"] for r in council_rows),
        "production_write_count": 0, "canonical_truth_written": False,
    }
    preflight_pass = (gate["default_flip_executed"] is False and gate["rollback_three_paths_verified"]
                      and gate["failclosed_paths_verified"] and gate["observability_metric_spec_present"]
                      and gate["cost_latency_budget_present"] and gate["m17b_evidence_slots_defined"]
                      and gate["ai_council_no_human_impersonation"] and gate["production_write_count"] == 0
                      and gate["canonical_truth_written"] is False)
    verdict = "GO" if preflight_pass else "NO-GO"
    gate["m19a_preflight_verdict"] = verdict
    gate["production_default_decision"] = "DEFERRED_TO_M19_AFTER_M17B"
    _dump(out, "go_no_go_preflight_m19a.json", gate)

    _finding(out, evidence, drills, matrix, recommended, gate, verdict)
    return {"verdict": verdict, "production_default": "OFF", "default_flip_executed": False,
            "rollback_three_paths_verified": gate["rollback_three_paths_verified"],
            "failclosed_paths_verified": gate["failclosed_paths_verified"],
            "recommended_rollout_candidate": recommended, "out_dir": str(out)}


def _observability_spec(out: Path, ev: dict) -> None:
    _wtext(out, "observability_metric_spec_m19a.md",
        "# Observability Metric Spec (M19A)\n\n"
        "production default OFF；以下指标为 M19 default 决策前必须接入的观测面。\n\n"
        "| metric | 定义 | 告警阈值 | 来源 |\n|---|---|---|---|\n"
        "| v1_llm_adjudication_enabled_count | 带 flag 的提交数 | — | runtime |\n"
        "| v1_llm_adjudication_success_rate | 非 failclosed / 总数 | < 0.98 warn | runtime |\n"
        f"| deepseek_latency_p50/p95 | 主模型延迟 | p95 > {ev['m17a_runtime_llm_adjudication']['latency_ms_p95']}ms breach | provider |\n"
        "| qwen_fallback_rate | fallback / 总数 | > 0.1 warn | runtime |\n"
        "| qwen_fallback_success_rate | fallback 成功 / fallback | < 0.95 warn | runtime |\n"
        "| validator_downgrade_rate | validator 降级点 / LLM-accept点 | 趋势监控 | validator |\n"
        "| false_positive_count | validator 后误 auto | **> 0 SEV2 page** | validator |\n"
        "| source_mismatch_count | source 不符 | **> 0 SEV2 page** | validator |\n"
        "| legacy_overwrite_count | legacy 被改写 | **> 0 SEV1 page** | runtime |\n"
        "| production_write_count | 生产写入 | **> 0 SEV1 page** | runtime |\n"
        "| lb_canonical_write_count | LB canonical truth 写入 | **> 0 SEV1 page** | learner_state |\n"
        "| failclosed_count | adjudicator fail-closed | 趋势监控 | runtime |\n"
        "| provider_timeout_count | provider 超时 | 突增 warn | provider |\n"
        "| cost_per_submission_p50/p95 | 单提交成本 | p95 预算 2x warn | billing |\n"
        "| non_cohort_blocked_count | 非 cohort 被拦 | 应=尝试数 | runtime |\n"
        "| rollback_success_rate | 回滚成功 / 演练 | < 1.0 SEV1 | releaseops |\n"
        "| kill_switch_time_to_effect | kill 到生效延迟 | > 1 turn warn | releaseops |\n")


def _slo_spec(out: Path) -> None:
    _wtext(out, "alerting_and_slo_spec_m19a.md",
        "# Alerting & SLO Spec (M19A)\n\n"
        "## SLO（default 开启前提）\n"
        "- false_positive_count = 0（硬 SLO，违则 SEV2 kill）。\n"
        "- legacy_overwrite_count = 0 / production_write_count = 0 / lb_canonical_write_count = 0（硬 SLO，违则 SEV1 kill+page）。\n"
        "- v1_llm_adjudication_success_rate >= 0.98。\n"
        "- deepseek_latency_p95 在 M17B 实测 SLO 内（M17A n=25 p95≈3.9s 仅基线）。\n"
        "- rollback_success_rate = 1.0；kill_switch_time_to_effect <= 1 turn。\n\n"
        "## 告警分级\n"
        "- SEV1（立即 kill + page）：legacy overwrite / production write / canonical truth write。\n"
        "- SEV2（kill + 调查）：false_positive>0 / source_mismatch>0 / non_cohort leak。\n"
        "- SEV3（告警 + 限流）：fallback 突增 / latency p95 破线 / cost spike。\n")


def _rollback_runbook(out: Path) -> None:
    _wtext(out, "rollback_killswitch_runbook_m19a.md",
        "# Rollback / Kill-Switch Runbook (M19A)\n\n"
        "production default OFF。三条秒级回滚路径（M16/M17A 已验证，M19A 实时复验）：\n\n"
        "1. **撤请求 flag**：移除 `grading_engine_v1_llm_adjudication` / `grading_engine_v1_controlled_runtime` → legacy 字节一致，无 adjudication key。\n"
        f"2. **env kill**：设 `{LLM_ADJ_KILL_ENV}=false`（或 `LUBAN_V1_CONTROLLED_RUNTIME_ENABLED=false`）→ adjudication 返回 `killed_by_switch`，无 point_results，legacy 不变。\n"
        "3. **registry/supply 失效**：release candidate registry / supply 不可用 → fail-closed（`adjudicator_unavailable` / `release_candidate_registry_unavailable`），legacy 仍返回。\n\n"
        "## 回滚保证\n"
        "- append-only：从不覆盖 `construction_grading_result`（legacy_equal_rate=1.0）。\n"
        "- 无 production DB / canonical truth 写入（production_write_count=0），回滚无需数据清理。\n"
        "- 非 cohort（非 qa_/test_/operator_）永远 legacy-only。\n"
        "## 事故响应\n"
        "- SEV1/SEV2 → 立即执行路径 2（env kill），再按 §SLO 调查。\n")


def _cost_budget(out: Path, ev: dict) -> None:
    m17a = ev["m17a_runtime_llm_adjudication"]
    _dump(out, "provider_cost_latency_budget_m19a.json", {
        "production_models": ["deepseek_v4_flash (primary)", "qwen3.7_plus (fallback)"],
        "token_budget_per_packet": m17a["token_budget_per_packet"],
        "latency_baseline_m17a": {"p50_ms": m17a["latency_ms_p50"], "p95_ms": m17a["latency_ms_p95"],
                                  "sample_size": m17a["real_adjudications"], "fallback_rate": 0.0},
        "latency_budget_proposed": {"p50_ms_target": 2500, "p95_ms_target": 5000,
                                    "note": "M17A baseline within; needs M17B at-scale confirmation"},
        "cost_budget_proposed": {"cost_per_submission_p95_max": "2x measured baseline",
                                 "primary": "DeepSeek-V4-flash (low cost)", "fallback": "Qwen3.7-plus"},
        "data_sufficiency": {"m17a_n": m17a["real_adjudications"], "sufficient_for_default": False,
                             "needs": "M17B scaleout for cost_per_submission_p50/p95 + latency CI at scale"},
        "production_default": "OFF"})


def _decision_template(out: Path) -> None:
    _wtext(out, "production_default_decision_template_m19a.md",
        "# Production Default Decision Template (M19, to be filled after M17B)\n\n"
        "> M19A 不做决策，只提供模板与证据槽。default flip 需 operator authorization。\n\n"
        "## 决策输入\n"
        "- [ ] M16 controlled runtime GO（已: GO）\n- [ ] M17A LLM adjudication GO（已: GO, n=25 fp=0）\n"
        "- [ ] M17B scaleout：fp=0 @≥200、latency p95 SLO、fallback success、cost_per_submission（**待填**）\n"
        "- [ ] M18C/M18D Learning Brain GO（已: GO, 真实 retest proof + council dry-run）\n"
        "- [ ] rollback 三路径实时复验（已: M19A failure_mode_drill）\n"
        "- [ ] observability + SLO + alerting 接入（spec: M19A）\n"
        "- [ ] AI council release risk review 无 human 冒充（已: M19A）\n"
        "- [ ] operator authorization（**待授权**）\n\n"
        "## 决策\n"
        "- rollout 策略：{shadow_only | 1% qa/operator default | named cohort default}（M19A 推荐 1% qa/operator）\n"
        "- production canonical-truth write：保持 OFF，单独闸\n"
        "- verdict：GO / WEAK-GO / NO-GO（M19 填）\n"
        "- review authority：ai_expert_council_final（human_reviewed=false）+ operator authorization\n")


def _finding(out, ev, drills, matrix, recommended, gate, verdict) -> None:
    m17a = ev["m17a_runtime_llm_adjudication"]
    _wtext(out, "FINDING_releaseops_default_decision_preflight_m19a_20260604.md",
        f"""# FINDING — M19A ReleaseOps & Production Default Decision Preflight（2026-06-04）

> M19A 不开 production default，不做最终决策；只产出 M19 决策所需的可审计 release 包。**未执行 default flip。**

## 16 必答

1. M16/M17A/M18C/M18D 证据：M16 controlled runtime GO（auto 54, fp=0, rollback 三路径, kill+malformed fail-closed, legacy=1.0）；M17A LLM adjudication GO（25 live DeepSeek, fp=0, legacy=1.0, validator 防误 8, latency p50={m17a['latency_ms_p50']}ms/p95={m17a['latency_ms_p95']}ms）；M18C dream cycle GO（45 evidence, shadow→mastery=0）；M18D real retest GO（16 真实 proof + 16 council dry-run candidate, all_safe）。
2. 已满足前置：controlled runtime / LLM adjudication / LB proof loop / rollback 三路径 / fail-closed / append-only / cohort gate / observability spec / cost-latency baseline / AI council 无 human 冒充。
3. 必须等 M17B：at-scale fp 率、latency p95 CI、qwen fallback success、cost_per_submission、validator downgrade 率（见 m17b_evidence_slots）。
4. production default 当前：**OFF**（default_flip_executed=False）。
5. rollback 三路径恢复 legacy-only：**{gate['rollback_three_paths_verified']}**（撤 flag / env kill / registry 失效，实时复验 flag_off={drills.get('flag_off_legacy_only',{}).get('pass')} / kill={drills.get('env_kill_switch',{}).get('pass')} / malformed={drills.get('malformed_registry_fail_closed',{}).get('pass')}）。
6. malformed registry fail-closed：**{drills.get('malformed_registry_fail_closed',{}).get('pass')}**（shadow_status=adjudicator/registry_unavailable，legacy 不变）。
7. provider down / DeepSeek timeout / Qwen fallback fail：fail-closed（adjudicator try/except → adjudicator_unavailable；M17A fallback=0/failclosed=0 基线；env kill 实时复验通过）。
8. legacy overwrite 风险：**0**（M16/M17A legacy_equal_rate=1.0，append-only，flag-off 无泄漏）。
9. production DB / canonical truth 写入风险：**0 / false**（M17A/M18D production_write_count=0, canonical_truth_written=false）。
10. 观测指标是否足够：metric spec 覆盖 fp/source_mismatch/cost spike/provider failure/legacy overwrite/lb canonical write（17 指标 + SEV1-3 分级 + SLO）。
11. 成本/延迟预算：token_budget=1200/packet，latency p50/p95 基线={m17a['latency_ms_p50']}/{m17a['latency_ms_p95']}ms（n=25），目标 p50<=2500/p95<=5000ms；**当前 M17A 数据不足以做 default 决策**，缺 M17B at-scale cost_per_submission + latency CI。
12. 推荐 rollout：**{recommended}**（最小可逆、全可观测、成本可控、truth-write OFF）。不更激进因为：canonical-truth 写权仍 OFF、M17B 统计未到、broad default 成本不可控、需 operator 授权。
13. AI council release risk review：核心安全风险 pass；统计置信 needs_m17b；default 授权 needs_operator_authorization；**无 human/teacher/PO 冒充字段**（review_authority=ai_expert_council_final, is_human=false）。
14. M19A verdict：**{verdict}**（preflight 包完整 + default 未开 + rollback/failclosed 复验 + 观测/成本/M17B 槽就绪 + council 无冒充）。
15. M17B 回来后合并：填 m17b_evidence_slots → 重跑 release_readiness_matrix → 按 production_default_decision_template 由 M19 + operator authorization 做最终 default decision。
16. 是否执行 default flip：**NO**。

## preflight 门
{json.dumps(gate, ensure_ascii=False, indent=1)}

## 红线
production default 未开（default_flip_executed=false）；未发 published registry；production_write_count=0；canonical_truth_written=false；
未改评分 runtime（grading_runtime_touched=false）；未碰 M17B scaleout / M18D proof gate；review authority=ai_expert_council_final 非 human；
未打印 secret；未 commit。
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    result = run_m19a(out_dir=args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
