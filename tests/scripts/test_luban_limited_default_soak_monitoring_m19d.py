"""M19D limited cohort soak monitoring guards.

M19D monitors the M19C limited default ON state. It must not flip again, broaden
cohort, write remote/Aliyun config, write production DB, write canonical learner
truth, or issue uncontrolled live calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_limited_default_soak_monitoring_m19d as m19d


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m19d")
    result = m19d.run_m19d(out_dir=out, submissions=300)
    return out, result


def test_required_outputs_exist(run):
    out, _ = run
    for name in (
        "soak_manifest_m19d.json",
        "cohort_coverage_m19d.json",
        "ws_submission_results_m19d.jsonl",
        "safety_invariants_m19d.json",
        "latency_cost_rollup_m19d.json",
        "fallback_failclosed_report_m19d.json",
        "rollback_readiness_m19d.json",
        "operator_stop_conditions_m19d.json",
        "release_verdict_m19d.json",
        "FINDING_limited_default_soak_monitoring_m19d_20260605.md",
        # Backward-compatible aliases from the first M19D run.
        "m19c_input_audit_m19d.json",
        "soak_window_submission_ledger_m19d.jsonl",
        "soak_metrics_m19d.json",
        "safety_invariant_report_m19d.json",
        "provider_fallback_failclosed_report_m19d.json",
        "latency_token_cost_report_m19d.json",
        "rollback_readiness_drill_m19d.json",
        "non_cohort_leak_audit_m19d.json",
        "learning_brain_preview_only_audit_m19d.json",
        "go_no_go_m19d.json",
        "FINDING_limited_default_soak_monitoring_m19d_20260605.md",
    ):
        assert (out / name).exists(), name


def test_preflight_confirms_m19c_on_and_strict_cohort(run):
    out, _ = run
    audit = _j(out / "m19c_input_audit_m19d.json")
    manifest = _j(out / "soak_manifest_m19d.json")
    assert audit["m19c_state"] == "ON"
    assert audit["default_cohort_prefixes"] == ["qa_", "operator_"]
    assert audit["broad_production_default"] == "NO-GO"
    assert audit["canonical_learner_truth_write"] == "NO-GO"
    assert audit["remote_deployment_written"] is False
    assert audit["production_db_write_enabled"] is False
    assert manifest["m19c_state"] == "ON"
    assert manifest["real_entry"] == "/api/v1/ws TestClient"
    assert manifest["m20_1_delta_absorbed"] is False
    assert manifest["production_db_write"] is False
    assert manifest["canonical_learner_truth_write"] is False
    assert manifest["published_registry_emitted"] is False


def test_soak_ledger_has_300_plus_real_ws_submissions_and_required_fields(run):
    out, result = run
    rows = _jsonl(out / "soak_window_submission_ledger_m19d.jsonl")
    required_rows = _jsonl(out / "ws_submission_results_m19d.jsonl")
    assert len(rows) >= 300
    assert len(required_rows) == len(rows)
    assert result["submissions_total"] >= 300
    for row in rows[:20]:
        assert row["real_entry"] == "/api/v1/ws TestClient"
        assert "user_id_prefix" in row
        assert "adjudicator_status" in row
        assert "packet_hash" in row
        assert "registry_hash" in row
        assert row["production_write"] is False
        assert row["canonical_truth_written"] is False


def test_soak_metrics_cover_cohort_fallback_failclosed_and_non_cohort(run):
    out, _ = run
    metrics = _j(out / "soak_metrics_m19d.json")
    coverage = _j(out / "cohort_coverage_m19d.json")
    assert metrics["submissions_total"] >= 300
    assert metrics["cohort_hit_count"] > 0
    assert metrics["non_cohort_blocked_count"] > 0
    assert metrics["deepseek_success_count"] > 0
    assert metrics["qwen_fallback_count"] > 0
    assert metrics["failclosed_count"] > 0
    assert metrics["fallback_rate"] > 0
    assert metrics["failclosed_rate"] > 0
    assert metrics["latency_p50_ms"] >= 0
    assert metrics["latency_p95_ms"] >= metrics["latency_p50_ms"]
    assert metrics["latency_p99_ms"] >= metrics["latency_p95_ms"]
    assert metrics["token_p95"] >= metrics["token_p50"]
    assert metrics["learning_brain_preview_only_count"] > 0
    assert coverage["qa_default_on_attached"] > 0
    assert coverage["operator_default_on_attached"] > 0
    assert coverage["test_explicit_regression_attached"] > 0
    assert coverage["non_cohort_blocked"] is True
    assert coverage["non_cohort_default_leak"] == 0
    assert coverage["m20_1_delta_absorbed"] is False


def test_safety_gates_all_pass_and_no_truth_write(run):
    out, _ = run
    safety = _j(out / "safety_invariant_report_m19d.json")
    safety_required = _j(out / "safety_invariants_m19d.json")
    assert safety_required == safety
    for key in (
        "false_positive",
        "bad_certified",
        "source_mismatch",
        "unsupported_positive",
        "legacy_overwrite",
        "production_write_count",
        "non_cohort_default_leak",
        "provider_failure_fail_open",
    ):
        assert safety[key] == 0
    assert safety["canonical_truth_written"] is False
    assert safety["kill_switch_works"] is True
    assert safety["rollback_works"] is True
    assert safety["all_pass"] is True


def test_rollback_readiness_paths_are_state_correct(run):
    out, _ = run
    rb = _j(out / "rollback_readiness_drill_m19d.json")
    rb_required = _j(out / "rollback_readiness_m19d.json")
    assert rb_required == rb
    for key in ("env_kill", "registry_unavailable", "request_flag_withdraw"):
        assert rb[key]["state_correct"] is True
        assert rb[key]["legacy_intact"] is True
        assert rb[key]["switch_path_latency_ms"] >= 0
    assert rb["all_pass"] is True


def test_final_decision_keeps_on_and_allows_remote_review_not_broad_default(run):
    out, result = run
    gate = _j(out / "go_no_go_m19d.json")
    release = _j(out / "release_verdict_m19d.json")
    stop = _j(out / "operator_stop_conditions_m19d.json")
    assert release == gate
    assert gate["m19d_soak_verdict"] == "GO"
    assert gate["keep_limited_default_on"] == "YES"
    assert gate["remote_aliyun_deployment_authorization_review"] == "GO"
    assert gate["broad_default"] == "NO-GO"
    assert gate["canonical_learner_truth_write"] == "NO-GO"
    assert gate["next_step"] == "M19E remote deployment authorization package"
    assert result["verdict"] == "GO"
    assert result["keep_limited_default_on"] == "YES"
    assert stop["stop_condition_hit_count"] == 0
    assert stop["rollback_required"] is False


def test_no_leak_and_preview_only_audits(run):
    out, _ = run
    leak = _j(out / "non_cohort_leak_audit_m19d.json")
    preview = _j(out / "learning_brain_preview_only_audit_m19d.json")
    assert leak["non_cohort_default_leak"] == 0
    assert leak["non_cohort_blocked_count"] > 0
    assert preview["canonical_truth_written"] is False
    assert preview["writeback_performed_count"] == 0
    assert preview["preview_only_count"] > 0


def test_finding_answers_12_questions(run):
    out, _ = run
    finding = (out / "FINDING_limited_default_soak_monitoring_m19d_20260605.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "M20.1 delta absorbed: **NO**" in finding
