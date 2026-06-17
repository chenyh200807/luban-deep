"""Hermetic guards for M8 v1 alpha grand sprint.

M8 is an alpha-shadow product slice: source hunt -> hard gate -> alpha pack ->
shadow payload -> QA metrics. It must not publish a formal registry, call live
models by default, connect production runtime, or treat official/model evidence
as textbook authority.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_v1_alpha_grand_sprint_m8 as m8

pytestmark = pytest.mark.skipif(
    not (m8.M35 / "normalized_rubric_candidates.jsonl").exists(),
    reason="M3.5 normalized supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def m8_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m8_alpha")
    result = m8.run_m8(out_dir=out, live_models=False, qa_samples=10)
    return out, result


def test_phase0_reconciles_canonical_input_counts(m8_run):
    out, _ = m8_run
    phase0 = _j(out / "phase0_input_reconciliation.json")
    assert phase0["normalized_ready"] == 47
    assert phase0["split_candidates"] == 22
    assert phase0["m7_existing_auto_preview"] == 6
    assert phase0["production_runtime_connected"] is False


def test_model_usage_plan_records_no_live_calls_by_default(m8_run):
    out, _ = m8_run
    plan = _j(out / "model_usage_plan.json")
    assert plan["live_calls_requested"] is False
    assert plan["live_calls_performed"] is False
    assert all(model["max_calls"] == 0 for model in plan["models"])
    assert all(value == 0 for value in plan["actual_calls"].values())
    assert plan["deterministic_source_gate_is_authority"] is True


def test_source_hunt_hard_gate_blocks_laundering(m8_run):
    out, _ = m8_run
    gate = _j(out / "m7r_hard_gate_results.json")
    assert gate["candidates_hunted"] == 69  # 47 ready + 22 split candidates
    assert gate["official_answer_upgraded_to_textbook"] == 0
    assert gate["model_vote_upgraded_to_textbook"] == 0
    assert gate["source_mismatch"] == 0
    assert gate["list_rule_partial_anchor_auto"] == 0

    for row in _jsonl(out / "verified_source_candidates.jsonl"):
        assert row["source_authority"] == "textbook_exact_match"
        assert row["human_reviewed"] is False
        assert row["production_runtime_connected"] is False
        assert row["source_verdict"]["hard_gate_pass"] is True


def test_alpha_registry_pack_is_shadow_only(m8_run):
    out, _ = m8_run
    pack = _j(out / "v1_alpha_registry_pack.json")
    phase2 = _j(out / "phase2_alpha_gate_decision.json")
    assert pack["status"] == m8.ALPHA_STATUS
    assert pack["formal_registry_emitted"] is False
    assert pack["production_runtime_connected"] is False
    assert pack["human_reviewed"] is False
    assert pack["alpha_auto_preview_total"] == phase2["total_auto_preview"]
    assert not (out / "registry_v1.json").exists()


def test_runtime_shadow_appends_only_when_gate_allows(m8_run):
    out, _ = m8_run
    runtime = _j(out / "alpha_runtime_shadow_smoke.json")
    diff = _j(out / "legacy_unchanged_audit.json")
    phase2 = _j(out / "phase2_alpha_gate_decision.json")
    assert diff["legacy_equal"] is True
    assert diff["legacy_key_overwritten"] is False
    if phase2["enter_runtime_shadow"]:
        shadow = runtime["client_result_payload"]["metadata"]["luban_grading_engine_v1_alpha_shadow"]
        assert shadow["authority"] == "luban_grading_engine_v1_alpha_shadow"
        assert shadow["not_production_grade"] is True
        assert shadow["writeback_performed"] is False
        assert shadow["production_runtime_connected"] is False
    else:
        assert runtime["shadow_attached"] is False


def test_qa_metrics_and_progress_preview_are_product_shaped(m8_run):
    out, _ = m8_run
    metrics = _j(out / "alpha_quality_metrics.json")
    assert metrics["bad_certified"] == 0
    assert metrics["source_mismatch"] == 0
    assert metrics["learning_brain_writeback_performed"] is False
    preview = (out / "progress_report_preview.md").read_text("utf-8")
    assert "哪里错" in preview
    assert "为什么" in preview
    assert "下一步练什么" in preview


def test_finding_answers_go_no_go_and_runtime_boundaries(m8_run):
    out, result = m8_run
    finding = (out / "FINDING_v1_alpha_grand_sprint_m8_20260604.md").read_text("utf-8")
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert "production_runtime_connected=false" in finding
    assert "legacy unchanged" in finding
    assert "official_answer" in finding
