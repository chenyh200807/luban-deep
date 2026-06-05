"""M19A — ReleaseOps & Production Default Decision Preflight guards.

M19A produces the M19 release-decision package WITHOUT flipping production default. It must
keep default OFF, prove the three rollback paths + fail-closed paths live over the REAL
/api/v1/ws, define observability/SLO/cost, and use a non-human AI-council release risk review.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_releaseops_default_decision_preflight_m19a as m19a

pytestmark = pytest.mark.skipif(
    not (m19a.M16 / "m16_go_no_go.json").exists()
    or not (m19a.M17A / "m17a_go_no_go.json").exists()
    or not (m19a.REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py").exists(),
    reason="M16/M17A evidence or ws harness absent",
)


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m19a")
    result = m19a.run_m19a(out_dir=out)
    return out, result


def test_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "workflow_ledger_m19a.json", "evidence_ledger_m19a.json", "release_readiness_matrix_m19a.json",
        "default_rollout_strategy_tournament_m19a.json", "observability_metric_spec_m19a.md",
        "alerting_and_slo_spec_m19a.md", "rollback_killswitch_runbook_m19a.md",
        "provider_cost_latency_budget_m19a.json", "failure_mode_drill_results_m19a.json",
        "ai_council_release_risk_review_m19a.jsonl", "m17b_evidence_slots_m19a.json",
        "production_default_decision_template_m19a.md", "go_no_go_preflight_m19a.json",
        "FINDING_releaseops_default_decision_preflight_m19a_20260604.md",
    ):
        assert (out / name).exists(), name


def test_default_not_flipped(run):
    out, result = run
    gate = _j(out / "go_no_go_preflight_m19a.json")
    assert result["default_flip_executed"] is False
    assert result["production_default"] == "OFF"
    assert gate["default_flip_executed"] is False
    assert gate["production_default"] == "OFF"
    assert gate["production_default_decision"] == "DEFERRED_TO_M19_AFTER_M17B"


def test_rollback_three_paths_verified_live(run):
    out, _ = run
    drills = _j(out / "failure_mode_drill_results_m19a.json")
    assert drills["flag_off_legacy_only"]["pass"] is True         # path 1: drop request flag
    assert drills["env_kill_switch"]["pass"] is True              # path 2: env kill -> killed_by_switch
    assert drills["env_kill_switch"]["shadow_status"] == "killed_by_switch"
    assert drills["malformed_registry_fail_closed"]["pass"] is True  # path 3: registry unavailable
    assert drills["malformed_registry_fail_closed"]["legacy_intact"] is True
    assert drills["non_cohort_blocked"]["pass"] is True
    assert drills["all_pass"] is True


def test_evidence_ledger_consumes_all_four_milestones(run):
    out, _ = run
    ev = _j(out / "evidence_ledger_m19a.json")
    assert ev["m16_controlled_production_runtime"]["verdict"] == "GO"
    assert ev["m17a_runtime_llm_adjudication"]["verdict"] == "GO"
    assert ev["m17a_runtime_llm_adjudication"]["false_positive"] == 0
    assert ev["m18c_learning_brain_dream_cycle"]["verdict"] == "GO"
    assert ev["m18d_real_retest_canonical_gate"]["verdict"] == "GO"
    assert ev["m18d_real_retest_canonical_gate"]["canonical_truth_written"] is False
    assert ev["production_default"] == "OFF"


def test_rollout_tournament_recommends_reversible_candidate_only(run):
    out, _ = run
    t = _j(out / "default_rollout_strategy_tournament_m19a.json")
    assert t["executed"] is False
    assert t["m19_recommended_candidate"] == "one_percent_qa_operator_default"
    assert "broad_production_default" in t["filtered_out"]
    for s in t["strategies"]:
        if not s["filtered_out"]:
            assert s["instant_revert"] is True and s["observable"] is True and s["cost_bounded"] is True


def test_ai_council_risk_review_has_no_human_impersonation(run):
    out, _ = run
    rows = _jsonl(out / "ai_council_release_risk_review_m19a.jsonl")
    assert rows
    for r in rows:
        assert r["is_human"] is False
        assert r["human_reviewed"] is False
        assert r["po_reviewed"] is False
        assert r["teacher_reviewed"] is False
        assert r["review_authority"] == "ai_expert_council_final"
    # statistical confidence + operator authorization must be deferred to M17B / operator
    verdicts = {r["risk"]: r["verdict"] for r in rows}
    assert verdicts["statistical_confidence_at_scale"] == "needs_m17b_evidence"
    assert verdicts["operator_authorization_for_default"] == "needs_operator_authorization"


def test_observability_spec_covers_core_incidents(run):
    out, _ = run
    spec = (out / "observability_metric_spec_m19a.md").read_text("utf-8")
    for metric in ("false_positive_count", "source_mismatch_count", "legacy_overwrite_count",
                   "production_write_count", "lb_canonical_write_count", "cost_per_submission",
                   "deepseek_latency", "qwen_fallback_rate", "rollback_success_rate",
                   "kill_switch_time_to_effect"):
        assert metric in spec


def test_cost_latency_budget_marks_m17a_insufficient(run):
    out, _ = run
    budget = _j(out / "provider_cost_latency_budget_m19a.json")
    assert budget["production_default"] == "OFF"
    assert budget["data_sufficiency"]["sufficient_for_default"] is False
    assert budget["latency_baseline_m17a"]["sample_size"] >= 1


def test_m17b_slots_defined(run):
    out, _ = run
    slots = _j(out / "m17b_evidence_slots_m19a.json")
    assert len(slots["slots"]) >= 4
    assert all(s["status"] == "needs_m17b_evidence" for s in slots["slots"])


def test_preflight_verdict_go(run):
    out, result = run
    gate = _j(out / "go_no_go_preflight_m19a.json")
    assert result["verdict"] == "GO"
    assert gate["m19a_preflight_verdict"] == "GO"
    assert gate["production_write_count"] == 0
    assert gate["canonical_truth_written"] is False
    finding = (out / "FINDING_releaseops_default_decision_preflight_m19a_20260604.md").read_text("utf-8")
    for idx in range(1, 17):
        assert f"{idx}." in finding
    assert "NO" in finding  # Q16 default flip executed = NO
