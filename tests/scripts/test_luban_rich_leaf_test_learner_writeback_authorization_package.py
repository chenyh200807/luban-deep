from __future__ import annotations

import json
from pathlib import Path


def _authorization_preflight() -> dict:
    return {
        "schema": "luban_rich_leaf_authorized_writeback_preflight.v1",
        "input_schemas": {
            "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
            "pcp_nba_candidate_projection": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        },
        "verdict": "READY_FOR_AUTHORIZATION_REVIEW",
        "quality_claim_allowed": False,
        "execution_mode": "authorization_preflight_only",
        "authorization": {
            "explicit_user_authorization_required": True,
            "test_learner_writeback_authorized": False,
            "allowed_write_scope": "none_without_authorization",
            "canonical_truth_authorized": False,
            "production_db_authorized": False,
        },
        "writeback_plan_candidate": {
            "target_memory_kind": "learning_evidence",
            "target_source_feature": "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
            "max_candidate_event_count": 50,
            "canonical_truth_after_writeback": "still_forbidden_without_separate_authorization",
        },
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 50,
            "sandbox_readback_event_count": 50,
            "top_claim_candidate_count": 50,
            "next_action_candidate_count": 3,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "missing_authorizations": [
            "explicit_user_authorization",
            "test_learner_identity_scope",
            "teacher_final_or_governance_review",
            "rollback_plan_for_test_learner_writeback",
            "separate_canonical_truth_authorization",
        ],
        "blockers": [],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "authorized_writeback_preflight": True,
            "test_learner_writeback_allowed": False,
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


def test_authorization_package_is_review_only_and_requires_user_decision() -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_authorization_package import (
        run_test_learner_writeback_authorization_package,
    )

    report = run_test_learner_writeback_authorization_package(authorized_writeback_preflight=_authorization_preflight())

    assert report["schema"] == "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
    assert report["verdict"] == "READY_FOR_USER_AUTHORIZATION_DECISION"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "authorization_package_only"
    assert report["authorization_decision"] == {
        "explicit_user_authorization_required": True,
        "user_authorization_recorded": False,
        "test_learner_writeback_authorized": False,
        "allowed_write_scope": "none_without_signed_authorization",
        "canonical_truth_authorized": False,
        "production_db_authorized": False,
    }
    assert report["candidate_scope"]["max_candidate_event_count"] == 50
    assert report["candidate_scope"]["target_memory_kind"] == "learning_evidence"
    assert report["rollback_plan"]["pre_write_snapshot_required"] is True
    assert report["rollback_plan"]["delete_by_source_feature_required"] is True
    assert report["summary"]["writeback_executed"] is False
    assert report["summary"]["learner_memory_write_count"] == 0
    assert report["classification"]["test_learner_writeback_allowed"] is False
    assert report["safety"]["canonical_learner_truth_written"] is False


def test_authorization_package_blocks_dirty_preflight() -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_authorization_package import (
        run_test_learner_writeback_authorization_package,
    )

    preflight = _authorization_preflight()
    preflight["summary"]["writeback_executed"] = True

    report = run_test_learner_writeback_authorization_package(authorized_writeback_preflight=preflight)

    assert report["verdict"] == "FAIL"
    assert "preflight_writeback_executed" in report["blockers"]
    assert report["summary"]["learner_memory_write_count"] == 0


def test_authorization_package_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_authorization_package import main

    preflight = tmp_path / "authorized_writeback_preflight.json"
    output = tmp_path / "test_learner_writeback_authorization_package.json"
    preflight.write_text(json.dumps(_authorization_preflight(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--authorized-writeback-preflight", str(preflight), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
    assert payload["authorization_decision"]["test_learner_writeback_authorized"] is False
