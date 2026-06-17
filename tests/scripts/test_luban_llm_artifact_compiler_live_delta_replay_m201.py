"""Hermetic guards for M20.1 live-delta replay harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_llm_artifact_compiler_live_delta_replay_m201 as m201
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

pytestmark = pytest.mark.skipif(
    not (m201.M20 / "release_candidate_delta_m20.json").exists(),
    reason="M20 signed delta artifacts absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def m201_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m201")
    original_builder = adj.build_grading_packet
    result = m201.run_m201(out, run_live_delta_replay=False, samples=100, fallback=10)
    assert adj.build_grading_packet is original_builder
    return out, result


def test_required_outputs_exist_and_no_live_default(m201_run):
    out, result = m201_run
    for name in m201.REQUIRED_OUTPUTS:
        assert (out / name).exists(), name
    plan = _j(out / "model_usage_plan_m201.json")
    replay = _j(out / "live_ws_delta_replay_results_m201.json")
    assert plan["live_delta_replay_requested"] is False
    assert replay["mode"] == "stubbed_shadow_replay"
    assert replay["live_llm_calls_executed"] is False
    assert replay["provider_stub_used"] is True
    assert result["live_replay_executed"] is False


def test_m20_input_hash_and_accepted_delta_count(m201_run):
    out, _ = m201_run
    audit = _j(out / "m20_delta_input_audit_m201.json")
    assert audit["m20_delta_hash"] == m201.EXPECTED_M20_DELTA_HASH
    assert audit["delta_hash_matches"] is True
    assert audit["candidate_delta_count"] == 122
    assert audit["accepted_delta_count"] == 69
    assert audit["accepted_delta_all_read"] is True
    assert audit["signer_schema_pass"] is True
    assert audit["signer_source_boundary_pass"] is True


def test_temporary_packet_builder_contract_is_explicit_and_non_authority(m201_run):
    out, _ = m201_run
    contract = (out / "temporary_packet_builder_contract_m201.md").read_text("utf-8")
    assert "--run-live-delta-replay" in contract
    assert "Source truth" in contract
    assert "Auto permission" in contract
    ledger = _jsonl(out / "delta_packet_application_ledger_m201.jsonl")
    assert ledger
    assert all(row["base_packet_hash"] != row["m20_delta_packet_hash"] for row in ledger)
    assert all(row["source_truth_signed"] is False for row in ledger)
    assert all(row["auto_permission_delta"] is False for row in ledger)
    assert all(row["production_runtime_connected"] is False for row in ledger)


def test_base_vs_delta_metrics_and_safety(m201_run):
    out, _ = m201_run
    comparison = _j(out / "base_vs_delta_comparison_m201.json")
    replay = _j(out / "live_ws_delta_replay_results_m201.json")
    assert comparison["requirements"]["same_batch_base_and_delta"] is True
    assert comparison["requirements"]["submissions_or_point_decisions_met"] is True
    assert comparison["token_budget_improved"] is True
    assert comparison["validator_downgrade_rate_improved"] is True
    assert comparison["false_positive"] == 0
    assert comparison["source_mismatch"] == 0
    assert comparison["unsupported_positive"] == 0
    assert comparison["list_partial_auto"] == 0
    assert comparison["bad_calculation"] == 0
    assert replay["base_rows"] == 100
    assert replay["delta_rows"] == 100
    assert replay["base"]["point_decisions"] >= 1
    assert replay["delta"]["point_decisions"] >= 1


def test_qwen_fallback_drill_available_under_delta_packet(m201_run):
    out, _ = m201_run
    qwen = _j(out / "qwen_fallback_delta_drill_m201.json")
    assert qwen["requested_forced_fallback"] == 10
    assert qwen["fallback_success"] >= 10
    assert qwen["delta_packet_qwen_available"] is True
    assert qwen["failclosed_rate"] == 0
    assert qwen["provider_stub_used"] is True


def test_adversarial_and_learning_brain_guards(m201_run):
    out, _ = m201_run
    attacks = _j(out / "adversarial_delta_replay_results_m201.json")
    lb = _j(out / "learning_brain_delta_quality_audit_m201.json")
    assert attacks["all_attacks_pass"] is True
    assert attacks["false_positive"] == 0
    assert attacks["source_mismatch"] == 0
    assert attacks["unsupported_positive"] == 0
    assert attacks["production_write_count"] == 0
    assert attacks["canonical_truth_written"] is False
    assert lb["learning_brain_delta_count"] == 16
    assert lb["card_specificity_improved_or_equal"] is True
    assert lb["canonical_truth_written"] is False
    assert lb["mastery_written"] is False
    assert lb["human_reviewed"] is False


def test_go_no_go_does_not_upgrade_without_live_flag(m201_run):
    out, result = m201_run
    gate = _j(out / "release_candidate_delta_go_no_go_m201.json")
    assert gate["m201_live_delta_replay"] == "WEAK-GO"
    assert gate["release_candidate_delta"] == "WEAK-GO"
    assert gate["live_replay_executed"] is False
    assert gate["provider_stub_used"] is True
    assert gate["can_feed_next_formal_registry_candidate"] is False
    assert gate["can_affect_current_m19b_default_decision"] is False
    assert gate["production_default_changed"] is False
    assert gate["production_write_count"] == 0
    assert gate["canonical_learner_truth_written"] is False
    assert result["release_candidate_delta"] == "WEAK-GO"


def test_finding_answers_required_questions(m201_run):
    out, _ = m201_run
    finding = (out / "FINDING_llm_artifact_compiler_live_delta_replay_m201_20260605.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "can affect current M19B default decision" in finding
    assert "NO" in finding
