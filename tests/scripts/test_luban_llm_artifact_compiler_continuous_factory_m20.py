"""Hermetic guards for M20 LLM-assisted continuous artifact compiler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_llm_artifact_compiler_continuous_factory_m20 as m20

pytestmark = pytest.mark.skipif(
    not (m20.M17B_M18 / "artifact_feedback_candidates.jsonl").exists()
    or not (m20.M13D / "review_queue_consolidated_m13d.jsonl").exists(),
    reason="M20 input artifacts absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def m20_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m20")
    result = m20.run_m20(out)
    return out, result


def test_required_outputs_exist(m20_run):
    out, result = m20_run
    assert result["continuous_artifact_compiler"] == "GO"
    assert result["release_candidate_delta"] in {"GO", "WEAK-GO", "NO-GO"}
    for name in m20.REQUIRED_OUTPUTS:
        assert (out / name).exists(), name


def test_inventory_consumes_runtime_review_and_learning_brain_inputs(m20_run):
    out, _ = m20_run
    inv = _j(out / "compiler_input_inventory_m20.json")
    assert inv["counts"]["m17b_m18_runtime_scaleout_logs"] >= 1
    assert inv["counts"]["m17b_m18_validator_downgrade_records"] >= 1
    assert inv["counts"]["m17b_m18_artifact_feedback_candidates"] >= 1
    assert inv["counts"]["m13d_review_queue"] >= 1
    assert inv["counts"]["m18d_real_retest_proofs"] >= 1
    assert inv["live_llm_calls_executed"] == 0
    assert inv["live_ws_calls_executed"] == 0


def test_workflow_patterns_and_classification_are_present(m20_run):
    out, _ = m20_run
    cls = _j(out / "runtime_feedback_classification_m20.json")
    for pattern in (
        "classify_and_act",
        "fanout_and_synthesize",
        "generate_and_filter",
        "adversarial_verification",
        "tournament",
        "loop_until_done",
    ):
        assert pattern in cls["workflow_patterns"]
    assert cls["bucket_counts"]["unsupported_positive"] >= 1
    assert cls["bucket_counts"]["review_queue_source_gap"] >= 1
    assert cls["all_feedback_actions_terminal"] is True


def test_candidates_are_terminal_and_cover_required_delta_kinds(m20_run):
    out, _ = m20_run
    rows = _jsonl(out / "candidate_delta_registry_m20.jsonl")
    assert rows
    assert all(row["final_action"] in m20.FINAL_ACTIONS for row in rows)
    assert all(row["delta_kind"] in m20.DELTA_KINDS for row in rows)
    assert all(row["source_truth_signed"] is False for row in rows)
    kinds = {row["delta_kind"] for row in rows}
    assert {
        "source_candidate_delta",
        "rubric_normalization_delta",
        "machine_spec_delta",
        "list_rule_coverage_delta",
        "grading_packet_compression_delta",
        "learning_brain_claim_mapping_delta",
    } <= kinds


def test_council_votes_are_non_source_non_human_replay(m20_run):
    out, _ = m20_run
    votes = _jsonl(out / "ai_council_artifact_repair_votes_m20.jsonl")
    assert votes
    for row in votes:
        assert row["reviewer_type"] == "ai_expert_council_replay"
        assert row["live_model_calls_executed"] == 0
        assert row["human_reviewed"] is False
        assert row["council_replaced_source"] is False
        assert row["model_vote_as_source"] is False
        assert {"deepseek_v4", "qwen37_plus", "gpt55_codex", "opus48"} == set(row["model_votes"])


def test_rejected_variants_cover_core_laundering_and_fp_attacks(m20_run):
    out, _ = m20_run
    rejected = _jsonl(out / "rejected_delta_candidates_m20.jsonl")
    names = {row["point_id"] for row in rejected}
    assert "official_answer_textbook_source_upgrade" in names
    assert "model_vote_source_upgrade" in names
    assert "council_vote_source_upgrade" in names
    assert "partial_list_auto_without_denominator" in names
    assert "calculation_without_formula_unit_value" in names
    assert "unsupported_positive_auto_certify" in names
    assert all(row["final_action"] == "reject" for row in rejected)


def test_deterministic_signer_and_attack_suite_pass_without_runtime_overreach(m20_run):
    out, _ = m20_run
    signer = _j(out / "deterministic_signer_report_m20.json")
    attacks = _j(out / "adversarial_artifact_attack_results_m20.json")
    assert signer["schema_validation_pass"] is True
    assert signer["source_boundary_validation_pass"] is True
    assert signer["release_candidate_delta_signed"] is True
    assert signer["signed_artifact_kind"] == "release_candidate_delta_not_formal_registry"
    assert signer["official_answer_upgraded_to_textbook"] == 0
    assert signer["model_vote_as_source"] == 0
    assert signer["council_vote_as_source"] == 0
    assert signer["production_runtime_connected"] is False
    assert signer["production_write_count"] == 0
    assert signer["canonical_learner_truth_written"] is False
    assert attacks["all_attacks_pass"] is True
    assert attacks["false_positive"] == 0
    assert attacks["source_mismatch"] == 0
    assert attacks["legacy_overwrite"] == 0
    assert attacks["production_write_count"] == 0
    assert attacks["canonical_truth_written"] is False


def test_ws_shadow_replay_is_logged_real_ws_projection_not_default_flip(m20_run):
    out, _ = m20_run
    replay = _j(out / "ws_shadow_replay_delta_eval_m20.json")
    assert replay["replay_mode"] == "logged_real_api_v1_ws_shadow_replay_no_new_live_calls"
    assert replay["live_ws_calls_executed"] == 0
    assert replay["runtime_default_changed"] is False
    assert replay["baseline"]["runtime_submissions"] >= 1
    assert replay["delta_projection"]["packet_token_budget"] <= replay["baseline"]["token_budget_per_packet"]
    assert replay["safety"]["false_positive"] == 0
    assert replay["safety"]["source_mismatch"] == 0
    assert replay["safety"]["legacy_overwrite"] == 0
    assert replay["safety"]["production_write_count"] == 0
    assert replay["safety"]["canonical_learner_truth_written"] is False


def test_release_candidate_delta_is_not_formal_registry(m20_run):
    out, result = m20_run
    release = _j(out / "release_candidate_delta_m20.json")
    assert release["artifact_kind"] == "release_candidate_delta"
    assert release["formal_registry_emitted"] is False
    assert release["production_default_changed"] is False
    assert release["production_runtime_connected"] is False
    assert release["source_truth_signed"] is False
    assert release["official_answer_upgraded_to_textbook"] == 0
    assert release["model_vote_as_source"] == 0
    assert release["council_vote_as_source"] == 0
    assert release["human_reviewed"] is False
    assert release["teacher_reviewed"] is False
    assert release["po_reviewed"] is False
    assert release["accepted_delta_count"] == result["accepted_delta_count"]
    assert release["verdict"] == "WEAK-GO"


def test_finding_answers_m20_verdicts(m20_run):
    out, _ = m20_run
    finding = (out / "FINDING_llm_artifact_compiler_continuous_factory_m20_20260604.md").read_text("utf-8")
    assert "continuous artifact compiler" in finding
    assert "release-candidate delta" in finding
    assert "production default impact" in finding
    assert "official_answer/model_vote/council_vote" in finding
    assert "NO" in finding
