"""M19C limited default flip guards.

M19C may enable only the M19B-authorized reversible qa_/operator_ limited default
in local QA/test runtime drill. It must not broaden production default, write DB,
write canonical learner truth, publish a registry, or rely on hidden live calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_limited_default_flip_m19c as m19c

# REVIEW-ARTIFACT-ONLY: M19C is a milestone-audit drill that consumes the (gitignored) M19B
# review-artifact package. It is NOT a limited-default runtime test — the runtime path is covered
# by the gate / registry / adjudicator / ws / runtime-supply-bundle tests, which run clean without
# artifacts. Skip in a clean checkout where the upstream review artifacts are absent.
pytestmark = pytest.mark.skipif(
    not (m19c.M19B / "release_go_no_go_m19b.json").exists(),
    reason="M19B review-artifact package absent (milestone-audit drill; not a runtime dependency)",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m19c")
    result = m19c.run_m19c(out_dir=out, submissions=100, authorized=True)
    return out, result


def test_authorization_required(tmp_path):
    result = m19c.run_m19c(out_dir=tmp_path, submissions=10, authorized=False)
    gate = _j(tmp_path / "go_no_go_m19c.json")
    assert result["verdict"] == "NO-GO"
    assert gate["authorization_detected"] is False
    assert gate["limited_default_current_state"] == "ROLLBACK"
    assert gate["production_default_broad"] == "NO-GO"
    assert gate["canonical_learner_truth_write"] == "NO-GO"


def test_required_outputs_exist(run):
    out, _ = run
    for name in (
        "authorization_audit_m19c.json",
        "preflight_baseline_m19c.json",
        "applied_limited_default_config_m19c.json",
        "ws_limited_default_live_results_m19c.json",
        "provider_fallback_failure_ledger_m19c.json",
        "latency_token_cost_report_m19c.json",
        "safety_invariant_report_m19c.json",
        "rollback_drill_transcript_m19c.md",
        "observability_stop_conditions_m19c.md",
        "go_no_go_m19c.json",
        "FINDING_limited_default_flip_m19c_20260605.md",
    ):
        assert (out / name).exists(), name


def test_limited_default_config_is_strict_and_no_truth_write(run):
    out, _ = run
    cfg = _j(out / "applied_limited_default_config_m19c.json")
    assert cfg["source_config"] == "M19B production_default_config_dryrun_m19b.json"
    assert cfg["limited_default_enabled"] is True
    assert cfg["default_mode"] == "one_percent_qa_operator_default"
    assert cfg["default_cohort_prefixes"] == ["qa_", "operator_"]
    assert cfg["allowed_internal_cohort_prefixes"] == ["qa_", "test_", "operator_"]
    assert cfg["broad_production_default_enabled"] is False
    assert cfg["canonical_truth_write_enabled"] is False
    assert cfg["production_db_write_enabled"] is False
    assert cfg["published_registry_emitted"] is False


def test_ws_default_drill_has_100_plus_submissions_and_blocks_non_cohort(run):
    out, result = run
    ws = _j(out / "ws_limited_default_live_results_m19c.json")
    assert ws["real_entry"] == "/api/v1/ws TestClient"
    assert ws["submission_count"] >= 100
    assert result["submission_count"] >= 100
    assert set(ws["cohort_coverage"]) >= {"qa_", "test_", "operator_"}
    assert set(ws["default_on_cohort_coverage"]) == {"qa_", "operator_"}
    assert ws["non_cohort_real_student_blocked"] is True
    assert ws["legacy_equal_rate"] == 1.0
    assert ws["production_write_count"] == 0
    assert ws["canonical_truth_written"] is False


def test_provider_success_fallback_failure_and_cost_ledger(run):
    out, _ = run
    ledger = _j(out / "provider_fallback_failure_ledger_m19c.json")
    assert ledger["deepseek_success_count"] > 0
    assert ledger["qwen_fallback_count"] > 0
    assert ledger["provider_failure_failclosed_count"] > 0
    assert ledger["live_llm_calls_executed"] is False
    cost = _j(out / "latency_token_cost_report_m19c.json")
    assert cost["submission_count"] >= 100
    assert cost["fallback_rate"] > 0
    assert cost["failclosed_rate"] > 0
    assert cost["duplicated_paid_calls"] == 0


def test_safety_invariants_all_hold(run):
    out, _ = run
    safety = _j(out / "safety_invariant_report_m19c.json")
    for key in (
        "false_positive",
        "bad_certified",
        "source_mismatch",
        "official_answer_as_source",
        "model_vote_as_source",
        "council_vote_as_source",
        "list_partial_auto",
        "legacy_overwrite",
        "production_write_count",
    ):
        assert safety[key] == 0
    assert safety["canonical_truth_written"] is False
    assert safety["non_cohort_blocked"] is True
    assert safety["kill_switch_works"] is True
    assert safety["all_pass"] is True


def test_rollback_drill_then_current_state_on(run):
    out, result = run
    gate = _j(out / "go_no_go_m19c.json")
    rollback = (out / "rollback_drill_transcript_m19c.md").read_text("utf-8")
    assert "drop request flag -> legacy-only: PASS" in rollback
    assert "env kill switch -> killed/fail-closed: PASS" in rollback
    assert "registry unavailable -> legacy intact: PASS" in rollback
    assert gate["m19c_limited_default_flip"] == "GO"
    assert gate["limited_default_current_state"] == "ON"
    assert gate["production_v1_broad_default"] == "NO-GO"
    assert gate["canonical_learner_truth_write"] == "NO-GO"
    assert result["current_state"] == "ON"
