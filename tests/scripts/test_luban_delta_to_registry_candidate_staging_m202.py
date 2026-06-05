"""Hermetic guards for M20.2 delta-to-registry candidate staging.

M20.2 must compile the M20/M20.1 GO accepted delta into a new staging namespace
only. It must not publish a registry, flip runtime/default, write production DB,
or write canonical learner truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_delta_to_registry_candidate_staging_m202 as m202


pytestmark = pytest.mark.skipif(
    not (m202.M20 / "release_candidate_delta_m20.json").exists()
    or not (m202.M201 / "release_candidate_delta_go_no_go_m201.json").exists(),
    reason="M20/M20.1 input artifacts absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def m202_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m202")
    result = m202.run_m202(out_dir=out)
    return out, result


def test_required_outputs_exist(m202_run):
    out, result = m202_run
    assert result["m202_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    for name in m202.REQUIRED_OUTPUTS:
        assert (out / name).exists(), name


def test_input_audit_hash_and_all_accepted_delta_read(m202_run):
    out, _ = m202_run
    audit = _j(out / "input_delta_audit_m202.json")
    assert audit["m20_delta_hash"] == m202.EXPECTED_DELTA_HASH
    assert audit["m201_delta_hash"] == m202.EXPECTED_DELTA_HASH
    assert audit["delta_hash_consistent"] is True
    assert audit["accepted_delta_count"] == 69
    assert audit["accepted_delta_all_read"] is True
    assert audit["m201_live_delta_replay"] == "GO"
    assert audit["m201_can_affect_current_default"] is False


def test_delta_classification_matches_m20_distribution(m202_run):
    out, _ = m202_run
    cls = _j(out / "delta_classification_m202.json")
    assert cls["classification_counts"] == {
        "list_delta": 7,
        "rubric_delta": 4,
        "machine_spec_delta": 8,
        "packet_compression_delta": 34,
        "learning_brain_claim_mapping_delta": 16,
    }
    assert cls["m20_delta_kind_counts_match"] is True
    assert cls["classified_delta_count"] == 69


def test_staged_registry_candidate_is_signed_non_published_independent_namespace(m202_run):
    out, _ = m202_run
    candidate = _j(out / "staged_registry_candidate_m202.json")
    signature = _j(out / "staged_registry_signature_m202.json")
    assert candidate["namespace"] == m202.STAGING_NAMESPACE
    assert candidate["runtime_registry_namespace"] == "m19c_limited_default_runtime_read_only"
    assert candidate["release_candidate_namespace"] == "m202_signed_immutable_candidate"
    assert candidate["status"] == "staged_release_candidate"
    assert candidate["published"] is False
    assert candidate["production_default_connected"] is False
    assert candidate["current_m19c_default_decision_changed"] is False
    assert candidate["accepted_delta_count"] == 69
    assert signature["signed"] is True
    assert signature["candidate_hash"] == candidate["candidate_hash"]
    assert signature["signed_status"] == "staged_release_candidate"
    assert signature["published"] is False


def test_deterministic_validation_blocks_laundering_partial_auto_and_unsupported_positive(m202_run):
    out, _ = m202_run
    validation = _j(out / "deterministic_validation_m202.json")
    assert validation["schema_valid"] is True
    assert validation["provenance_valid"] is True
    assert validation["no_official_answer_as_textbook"] is True
    assert validation["no_model_vote_as_source"] is True
    assert validation["no_council_vote_as_source"] is True
    assert validation["source_laundering"] == 0
    assert validation["list_partial_auto"] == 0
    assert validation["unsupported_positive"] == 0
    assert validation["all_pass"] is True


def test_regression_projection_preserves_m201_improvements_and_fallback(m202_run):
    out, _ = m202_run
    projection = _j(out / "regression_projection_m202.json")
    assert projection["comparison"] == "current_m19c_registry_vs_m202_staged_candidate"
    assert projection["token"]["current_m19c_or_m201_base"] == 1200
    assert projection["token"]["m202_staged_candidate"] == 1064
    assert projection["token"]["improvement_percent"] == 11.33
    assert projection["coverage"]["current"] == 235
    assert projection["coverage"]["m202_staged_candidate"] == 235
    assert projection["validator_downgrade_rate"]["current"] == 0.0638
    assert projection["validator_downgrade_rate"]["m202_staged_candidate"] == 0.0383
    assert projection["fallback"]["qwen_fallback_success"] == 10
    assert projection["preserves_m201_improvements"] is True


def test_lb_claim_mapping_and_release_decision_input_are_dry_run_only(m202_run):
    out, _ = m202_run
    lb = _j(out / "lb_claim_mapping_delta_m202.json")
    release_input = _j(out / "release_decision_input_m202.json")
    assert lb["learning_brain_claim_mapping_delta_count"] == 16
    assert lb["canonical_truth_written"] is False
    assert lb["mastery_written"] is False
    assert release_input["artifact_kind"] == "release_decision_input"
    assert release_input["execute_release_decision"] is False
    assert release_input["recommended_next_step"] == "run_independent_release_decision"
    assert release_input["candidate_status"] == "staged_release_candidate"


def test_no_runtime_impact_audit_keeps_m19c_default_unchanged(m202_run):
    out, _ = m202_run
    audit = _j(out / "no_runtime_impact_audit_m202.json")
    assert audit["runtime_registry"] == "read_only"
    assert audit["m202_staging_registry"] == "new_namespace_only"
    assert audit["published_registry_emitted"] is False
    assert audit["production_default_changed"] is False
    assert audit["production_runtime_connected"] is False
    assert audit["production_db_write_count"] == 0
    assert audit["canonical_learner_truth_written"] is False
    assert audit["v0_registry_overwritten"] is False
    assert audit["current_v1_registry_overwritten"] is False


def test_finding_answers_twelve_questions(m202_run):
    out, result = m202_run
    finding = (out / "FINDING_delta_to_registry_candidate_staging_m202_20260605.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "M20/M20.1 delta hash" in finding
    assert "staged_release_candidate" in finding
    assert "runtime/default" in finding
    assert result["m202_verdict"] == "GO"
