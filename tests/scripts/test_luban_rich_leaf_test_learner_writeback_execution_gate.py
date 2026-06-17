from __future__ import annotations

import json
from pathlib import Path


def _dry_run_manifest() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
        "input_schemas": {
            "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
            "test_learner_writeback_authorization_package": "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
        },
        "verdict": "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_manifest_only",
        "target_scope": {
            "target_user_id": "not_bound_without_authorization",
            "target_memory_kind": "learning_evidence",
            "target_source_feature": "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
        },
        "write_batch_candidate": {
            "batch_id": "rich_leaf_writeback_dry_run_batch_1",
            "event_count": 2,
            "idempotency_key_count": 2,
            "write_allowed": False,
        },
        "rollback_selector": {
            "target_user_id": "not_bound_without_authorization",
            "source_feature": "rich_leaf_authorized_test_writeback",
            "batch_id": "rich_leaf_writeback_dry_run_batch_1",
            "rollback_allowed": False,
        },
        "event_write_candidates": [
            {
                "planned_event_id": "rich_leaf_writeback_dry_run_event_1",
                "source_event_id": "rich_leaf_le_candidate_1",
                "target_user_id": "not_bound_without_authorization",
                "source_feature": "rich_leaf_authorized_test_writeback",
                "memory_kind": "learning_evidence",
                "idempotency_key": "rich_leaf_writeback_dry_run_idempotency_1",
                "write_allowed": False,
                "payload_json": {
                    "candidate_event_id": "rich_leaf_le_candidate_1",
                    "candidate_only": True,
                    "quality": {
                        "writeback_eligible": False,
                        "progress_countable": False,
                        "truth_eligible": False,
                        "stable_truth_eligible": False,
                    },
                },
            },
            {
                "planned_event_id": "rich_leaf_writeback_dry_run_event_2",
                "source_event_id": "rich_leaf_le_candidate_2",
                "target_user_id": "not_bound_without_authorization",
                "source_feature": "rich_leaf_authorized_test_writeback",
                "memory_kind": "learning_evidence",
                "idempotency_key": "rich_leaf_writeback_dry_run_idempotency_2",
                "write_allowed": False,
                "payload_json": {
                    "candidate_event_id": "rich_leaf_le_candidate_2",
                    "candidate_only": True,
                    "quality": {
                        "writeback_eligible": False,
                        "progress_countable": False,
                        "truth_eligible": False,
                        "stable_truth_eligible": False,
                    },
                },
            },
        ],
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "planned_event_count": 2,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "blockers": [],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_writeback_dry_run_manifest": True,
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


def test_execution_gate_blocks_without_signed_authorization_or_bound_test_learner() -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_execution_gate import (
        run_test_learner_writeback_execution_gate,
    )

    report = run_test_learner_writeback_execution_gate(test_learner_writeback_dry_run_manifest=_dry_run_manifest())

    assert report["schema"] == "luban_rich_leaf_test_learner_writeback_execution_gate.v1"
    assert report["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "execution_gate_only"
    assert report["execution_decision"] == {
        "writeback_allowed": False,
        "writeback_executed": False,
        "target_user_id_bound": False,
        "signed_authorization_recorded": False,
        "rollback_plan_approved": False,
    }
    assert report["summary"]["dry_run_planned_event_count"] == 2
    assert report["summary"]["learner_memory_write_count"] == 0
    assert "signed_user_authorization_missing" in report["blocking_reasons"]
    assert "target_user_unbound" in report["blocking_reasons"]
    assert "rollback_plan_not_approved" in report["blocking_reasons"]
    assert report["classification"]["learner_memory_write_allowed"] is False
    assert report["safety"]["canonical_learner_truth_written"] is False


def test_execution_gate_blocks_dirty_dry_run_manifest() -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_execution_gate import (
        run_test_learner_writeback_execution_gate,
    )

    manifest = _dry_run_manifest()
    manifest["write_batch_candidate"]["write_allowed"] = True

    report = run_test_learner_writeback_execution_gate(test_learner_writeback_dry_run_manifest=manifest)

    assert report["verdict"] == "FAIL"
    assert "dry_run_write_allowed" in report["blockers"]
    assert report["summary"]["writeback_executed"] is False


def test_execution_gate_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_execution_gate import main

    dry_run = tmp_path / "test_learner_writeback_dry_run_manifest.json"
    output = tmp_path / "test_learner_writeback_execution_gate.json"
    dry_run.write_text(json.dumps(_dry_run_manifest(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--test-learner-writeback-dry-run-manifest", str(dry_run), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_test_learner_writeback_execution_gate.v1"
    assert payload["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
