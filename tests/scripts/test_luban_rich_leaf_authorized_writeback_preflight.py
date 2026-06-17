from __future__ import annotations

import json
from pathlib import Path


def _sandbox_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "artifact_only_sandbox_readback",
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 50,
            "valid_candidate_event_count": 50,
            "sandbox_event_write_count": 50,
            "sandbox_readback_event_count": 50,
            "synthesis_observed_candidate_count": 0,
            "synthesis_compiled_object_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_sandbox_readback_gate": True,
            "sandbox_write_scope": "artifact_only",
            "learner_memory_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _pcp_projection() -> dict:
    return {
        "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_candidate_projection",
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 50,
            "valid_candidate_event_count": 50,
            "top_claim_candidate_count": 50,
            "next_action_candidate_count": 3,
            "learner_memory_write_count": 0,
            "pcp_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
            "provider_call_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "pcp_nba_candidate_projection": True,
            "learner_memory_write_allowed": False,
            "personalization_context_pack_readback_allowed": False,
            "next_best_action_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def test_preflight_reports_ready_for_authorization_review_without_writing() -> None:
    from scripts.run_luban_rich_leaf_authorized_writeback_preflight import run_authorized_writeback_preflight

    report = run_authorized_writeback_preflight(
        test_learner_sandbox_readback_gate=_sandbox_gate(),
        pcp_nba_candidate_projection=_pcp_projection(),
    )

    assert report["schema"] == "luban_rich_leaf_authorized_writeback_preflight.v1"
    assert report["verdict"] == "READY_FOR_AUTHORIZATION_REVIEW"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "authorization_preflight_only"
    assert report["authorization"] == {
        "explicit_user_authorization_required": True,
        "test_learner_writeback_authorized": False,
        "allowed_write_scope": "none_without_authorization",
        "canonical_truth_authorized": False,
        "production_db_authorized": False,
    }
    assert report["summary"]["candidate_event_count"] == 50
    assert report["summary"]["sandbox_readback_event_count"] == 50
    assert report["summary"]["writeback_executed"] is False
    assert report["summary"]["learner_memory_write_count"] == 0
    assert report["summary"]["canonical_truth_write_count"] == 0
    assert "explicit_user_authorization" in report["missing_authorizations"]
    assert "learner_state_service_append_memory_event" in report["not_exercised_by_layer"]["memory_not_exercised"]
    assert report["classification"]["test_learner_writeback_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_preflight_blocks_dirty_sandbox_gate() -> None:
    from scripts.run_luban_rich_leaf_authorized_writeback_preflight import run_authorized_writeback_preflight

    sandbox = _sandbox_gate()
    sandbox["summary"]["synthesis_observed_candidate_count"] = 1

    report = run_authorized_writeback_preflight(
        test_learner_sandbox_readback_gate=sandbox,
        pcp_nba_candidate_projection=_pcp_projection(),
    )

    assert report["verdict"] == "FAIL"
    assert "sandbox_synthesis_observed_candidate_count" in report["blockers"]
    assert report["summary"]["writeback_executed"] is False


def test_preflight_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_authorized_writeback_preflight import main

    sandbox = tmp_path / "test_learner_sandbox_readback_gate.json"
    projection = tmp_path / "pcp_nba_candidate_projection.json"
    output = tmp_path / "authorized_writeback_preflight.json"
    sandbox.write_text(json.dumps(_sandbox_gate(), ensure_ascii=False), encoding="utf-8")
    projection.write_text(json.dumps(_pcp_projection(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--test-learner-sandbox-readback-gate",
            str(sandbox),
            "--pcp-nba-candidate-projection",
            str(projection),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_authorized_writeback_preflight.v1"
    assert payload["authorization"]["test_learner_writeback_authorized"] is False
