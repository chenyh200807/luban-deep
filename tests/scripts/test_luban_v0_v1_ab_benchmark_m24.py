"""M24 v0 vs v1 A/B benchmark — hermetic guards.

Default = hermetic: deterministic in-process adjudication provider, NO live LLM, NO Langfuse,
NO Supabase. Proves the A/B harness runs over the REAL /api/v1/ws, the deterministic validator
floor keeps false_positive=0, v1 adds per-point granularity over v0, and nothing writes
production / canonical truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_v0_v1_ab_benchmark_m24 as m24

pytestmark = pytest.mark.skipif(
    not (m24.REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py").exists(),
    reason="ws harness absent",
)


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m24")
    result = m24.run_m24(out_dir=out, mode="smoke", run_live=False, run_langfuse=False, run_rag_live=False)
    return out, result


def test_all_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "workflow_manifest_m24.json", "local_langfuse_boot_report_m24.json", "sample_inventory_m24.jsonl",
        "ws_submission_ledger_m24.jsonl", "v0_vs_v1_quality_matrix_m24.json", "latency_cost_report_m24.json",
        "provider_fallback_report_m24.json", "langfuse_trace_map_m24.jsonl", "rag_readonly_baseline_audit_m24.json",
        "adversarial_safety_report_m24.json", "product_effect_examples_m24.md", "go_no_go_m24.json",
        "FINDING_v0_v1_ab_benchmark_m24_20260605.md",
    ):
        assert (out / name).exists(), name


def test_smoke_has_at_least_20_submissions_via_real_ws(run):
    out, result = run
    assert result["samples"] >= 20
    ledger = _jsonl(out / "ws_submission_ledger_m24.jsonl")
    # each sample produces a v0 and a v1 submission
    v0 = [r for r in ledger if r["engine_version"] == "v0_legacy"]
    v1 = [r for r in ledger if r["engine_version"] == "v1_llm_adjudication"]
    assert len(v0) >= 20 and len(v1) >= 20
    manifest = _j(out / "workflow_manifest_m24.json")
    assert manifest["entry"] == "/api/v1/ws TestClient (real)"
    assert manifest["live_llm_executed"] is False


def test_default_is_hermetic_no_live_no_langfuse(run):
    out, result = run
    assert result["live"] is False
    lf = _j(out / "local_langfuse_boot_report_m24.json")
    assert lf["langfuse_started"] is False  # opt-in via --run-langfuse
    rag = _j(out / "rag_readonly_baseline_audit_m24.json")
    assert rag["status"] == "not_run"        # opt-in via --run-rag-live


def test_validator_floor_keeps_false_positive_zero(run):
    out, _ = run
    q = _j(out / "v0_vs_v1_quality_matrix_m24.json")["v1_point_level"]
    # v1 auto is a subset of the deterministic matcher gold -> precision 1.0, fp 0
    assert q["false_positive"] == 0
    assert q["precision"] == 1.0
    assert q["evidence_span_valid_rate"] == 1.0


def test_safety_invariants_all_zero(run):
    out, _ = run
    s = _j(out / "adversarial_safety_report_m24.json")
    assert s["false_positive"] == 0
    assert s["source_mismatch"] == 0
    assert s["unsupported_positive"] == 0
    assert s["bad_certified"] == 0
    assert s["evidence_span_laundering"] == 0
    assert s["legacy_overwrite_count"] == 0
    assert s["non_cohort_leak"] == 0
    assert s["provider_fail_open"] == 0
    assert s["production_write_count"] == 0
    assert s["canonical_truth_written"] is False
    assert s["all_zero"] is True


def test_v1_adds_granularity_over_v0(run):
    out, _ = run
    q = _j(out / "v0_vs_v1_quality_matrix_m24.json")
    assert q["v1_point_level"]["disposition_distribution"]  # v1 has per-point dispositions
    assert q["v0_point_level"]["has_point_level_dispositions"] is False  # legacy = score only
    gg = q["granularity_gain"]
    assert gg["v1_granular_points"] > 0
    assert "evidence_span_valid" in gg["v1_adds"]
    assert "Learning Brain event draft" in gg["v1_adds"]


def test_forced_fallback_drill_proves_real_fallback_control_flow(run):
    out, _ = run
    p = _j(out / "provider_fallback_report_m24.json")
    assert p["forced_fallback_drills"] >= 20
    assert p["fallback_used_count"] >= 20          # primary forced down -> real Qwen fallback path
    assert p["failclosed_drill"]["failclosed"] is True
    assert p["primary_model"] == "deepseek_v4_flash"
    assert p["fallback_model"] == "qwen3.7_plus"


def test_no_broad_default_no_production_write(run):
    out, _ = run
    go = _j(out / "go_no_go_m24.json")
    assert go["broad_default_flip"] is False
    assert go["production_write_count"] == 0
    assert go["canonical_truth_written"] is False
    assert go["m24_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    # hermetic default has safety all zero but no langfuse/live -> WEAK-GO
    assert go["safety_all_zero"] is True


def test_finding_answers_fifteen_questions(run):
    out, _ = run
    finding = (out / "FINDING_v0_v1_ab_benchmark_m24_20260605.md").read_text("utf-8")
    for idx in range(1, 16):
        assert f"{idx}." in finding
    assert "/api/v1/ws" in finding
    assert "verdict" in finding.lower()
