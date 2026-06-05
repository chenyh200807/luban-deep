"""M19B production default decision synthesis guards.

M19B is the canonical release package after M17C. It may run a real `/api/v1/ws`
release drill and produce dry-run config, but it must not flip production default,
write production DB, write canonical learner truth, publish registry, or trigger live
LLM calls during tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_production_default_decision_synthesis_m19b as m19b

pytestmark = pytest.mark.skipif(
    not (m19b.M17C / "m19_default_decision_readiness_delta_m17c.json").exists(),
    reason="M17C evidence absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m19b")
    result = m19b.run_m19b(out_dir=out, submissions=205)
    return out, result


def test_required_outputs_exist(run):
    out, _ = run
    for name in (
        "canonical_evidence_ledger_m19b.json",
        "supersession_matrix_m19b.md",
        "ws_release_drill_results_m19b.json",
        "provider_cost_latency_rollup_m19b.json",
        "rollback_and_killswitch_verification_m19b.json",
        "production_default_decision_matrix_m19b.json",
        "release_go_no_go_m19b.json",
        "production_default_config_dryrun_m19b.json",
        "FINDING_production_default_decision_synthesis_m19b_20260604.md",
    ):
        assert (out / name).exists(), name


def test_m17c_supersedes_m17b_live_gap(run):
    out, _ = run
    ledger = _j(out / "canonical_evidence_ledger_m19b.json")
    assert ledger["m17b_runtime_llm_scaleout"]["original_verdict"] == "WEAK-GO"
    assert ledger["m17c_deepseek_live_completion"]["merged_deepseek_live_calls"] == 80
    assert ledger["canonical_runtime_llm_scaleout_axis"] == "GO"
    matrix = (out / "supersession_matrix_m19b.md").read_text("utf-8")
    assert "M17B WEAK-GO" in matrix
    assert "superseded by M17C" in matrix


def test_ws_release_drill_has_200_plus_real_ws_submissions(run):
    out, result = run
    drill = _j(out / "ws_release_drill_results_m19b.json")
    assert drill["real_entry"] == "/api/v1/ws TestClient"
    assert drill["submission_count"] >= 200
    assert result["submission_count"] >= 200
    assert set(drill["cohort_coverage"]) >= {"qa_", "test_", "operator_"}
    assert drill["non_cohort_real_student_blocked"] is True
    assert drill["legacy_equal_rate"] == 1.0
    assert drill["production_write_count"] == 0
    assert drill["canonical_truth_written"] is False
    assert drill["live_llm_calls_executed"] is False


def test_failure_modes_and_rollback_all_covered(run):
    out, _ = run
    rb = _j(out / "rollback_and_killswitch_verification_m19b.json")
    assert rb["kill_switch"]["pass"] is True
    assert rb["malformed_registry"]["pass"] is True
    assert rb["provider_failure"]["pass"] is True
    assert rb["fallback"]["pass"] is True
    assert rb["rollback_flag_off"]["pass"] is True
    assert rb["all_pass"] is True


def test_decision_matrix_and_final_go_no_go(run):
    out, _ = run
    matrix = _j(out / "production_default_decision_matrix_m19b.json")
    assert matrix["shadow_only"]["verdict"] == "GO"
    assert matrix["controlled_cohort_only"]["verdict"] == "GO"
    assert matrix["one_percent_qa_operator_default"]["verdict"] == "GO"
    assert matrix["named_internal_cohort_default"]["verdict"] == "GO"
    assert matrix["broad_production_default"]["verdict"] == "NO-GO"
    gate = _j(out / "release_go_no_go_m19b.json")
    assert gate["m19b_limited_production_default_candidate"] == "GO"
    assert gate["production_v1_default_flip"] == "NO-GO"
    assert gate["canonical_learner_truth_write"] == "NO-GO"
    assert gate["default_flip_executed"] is False
    assert gate["formal_registry_emitted"] is False


def test_dryrun_config_does_not_enable_default(run):
    out, _ = run
    cfg = _j(out / "production_default_config_dryrun_m19b.json")
    assert cfg["dryrun_only"] is True
    assert cfg["execute_flip"] is False
    assert cfg["production_default_enabled"] is False
    assert cfg["canonical_truth_write_enabled"] is False
    assert cfg["rollback"]["kill_switch_env"] == "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"


def test_provider_rollup_fills_m19a_waiting_slots(run):
    out, _ = run
    rollup = _j(out / "provider_cost_latency_rollup_m19b.json")
    assert rollup["deepseek_live"]["merged_live_calls"] == 80
    assert rollup["fallback"]["qwen_fallback_drills"] >= 20
    assert rollup["cost"]["duplicated_paid_calls"] == 0
    assert rollup["validator"]["safety_all_zero"] is True
    assert rollup["council_risk"]["council_vote_as_source"] == 0
