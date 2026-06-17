from __future__ import annotations

import json
from pathlib import Path


def _bridge_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "input_schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "candidate_bridge",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "learning_evidence_candidate_bridge": True,
            "learner_memory_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "learner_memory_write_count": 0,
            "provider_call_count": 0,
        },
        "learning_evidence_event_candidates": [
            {
                "candidate_event_id": "C1",
                "event_type": "learning_evidence",
                "memory_kind": "learning_evidence",
                "source": "rich_leaf_shadow_candidate",
                "source_feature": "rich_leaf_shadow_candidate",
                "candidate_only": True,
                "preview_only": True,
                "claim_promotion_allowed": False,
                "canonical_truth_written": False,
                "quality": {
                    "candidate_only": True,
                    "authority": "rich_leaf_shadow_candidate",
                    "writeback_eligible": False,
                    "progress_countable": False,
                    "truth_eligible": False,
                    "stable_truth_eligible": False,
                    "evidence_level": "preview_needs_retest",
                },
                "rich_leaf_trace": {"leaf_id": "L1", "field_id": "F1"},
            },
            {
                "candidate_event_id": "C2",
                "event_type": "learning_evidence",
                "memory_kind": "learning_evidence",
                "source": "rich_leaf_shadow_candidate",
                "source_feature": "rich_leaf_shadow_candidate",
                "candidate_only": True,
                "preview_only": True,
                "claim_promotion_allowed": False,
                "canonical_truth_written": False,
                "quality": {
                    "candidate_only": True,
                    "authority": "rich_leaf_shadow_candidate",
                    "writeback_eligible": False,
                    "progress_countable": False,
                    "truth_eligible": False,
                    "stable_truth_eligible": False,
                    "evidence_level": "preview_needs_retest",
                },
                "rich_leaf_trace": {"leaf_id": "L2", "field_id": "F2"},
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
        },
    }


def _pcp_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "input_schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_candidate_projection",
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
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "valid_candidate_event_count": 2,
            "top_claim_candidate_count": 2,
            "next_action_candidate_count": 1,
            "learner_memory_write_count": 0,
            "pcp_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
            "provider_call_count": 0,
        },
        "personalization_context_pack_candidate": {
            "candidate_only": True,
            "readback_verified": False,
            "authority": {
                "evidence": "learning_evidence_candidate_bridge",
                "claims": "candidate_projection_not_learning_synthesis",
                "prescription": "not_exercised_training_intent",
            },
        },
        "next_action_candidates": [
            {
                "action_id": "A1",
                "candidate_only": True,
                "status": "candidate_not_prescription",
                "prescription_authority": "not_exercised_training_intent",
            }
        ],
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _sandbox_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "artifact_only_sandbox_readback",
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
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "valid_candidate_event_count": 2,
            "sandbox_event_write_count": 2,
            "sandbox_readback_event_count": 2,
            "synthesis_observed_candidate_count": 0,
            "synthesis_compiled_object_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _dry_run_manifest_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
        "verdict": "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_manifest_only",
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
        "target_scope": {"target_user_id": "not_bound_without_authorization"},
        "write_batch_candidate": {"write_allowed": False, "event_count": 2},
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
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _execution_gate_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
        "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
        "quality_claim_allowed": False,
        "execution_mode": "execution_gate_only",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_writeback_execution_gate": True,
            "test_learner_writeback_allowed": False,
            "learner_memory_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "execution_decision": {
            "writeback_allowed": False,
            "writeback_executed": False,
            "target_user_id_bound": False,
            "signed_authorization_recorded": False,
            "rollback_plan_approved": False,
        },
        "summary": {
            "blocker_count": 0,
            "dry_run_planned_event_count": 2,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def test_current_standard_compat_audit_marks_candidates_not_current_standard_payloads() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_current_standard_compat_audit import (
        run_learning_evidence_current_standard_compat_audit,
    )

    report = run_learning_evidence_current_standard_compat_audit(
        learning_evidence_candidate_bridge=_bridge_payload(),
        pcp_nba_candidate_projection=_pcp_payload(),
        test_learner_sandbox_readback_gate=_sandbox_payload(),
        test_learner_writeback_dry_run_manifest=_dry_run_manifest_payload(),
        test_learner_writeback_execution_gate=_execution_gate_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["current_standard_readback_verified"] is False
    assert report["classification"]["learner_memory_write_allowed"] is False
    assert report["summary"]["candidate_event_count"] == 2
    assert report["summary"]["not_current_standard_payload_count"] == 2
    assert report["summary"]["current_standard_readback_verified"] is False
    assert report["summary"]["standard_accepted_source_feature_count"] == 0
    assert report["summary"]["pcp_readback_count"] == 0
    assert report["summary"]["training_intent_write_count"] == 0
    assert report["summary"]["next_best_action_write_count"] == 0
    finding = report["candidate_event_compat_findings"][0]
    assert finding["candidate_event_id"] == "C1"
    assert finding["current_standard_payload"] is False
    assert finding["current_standard_readback_verified"] is False
    assert finding["writeback_eligible"] is False
    assert "source_feature_not_accepted" in finding["incompatibility_reasons"]
    assert "candidate_only" in finding["incompatibility_reasons"]
    assert "writeback_eligible_false" in finding["incompatibility_reasons"]


def test_current_standard_compat_audit_fails_if_candidate_claims_writeback() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_current_standard_compat_audit import (
        run_learning_evidence_current_standard_compat_audit,
    )

    bridge = _bridge_payload()
    bridge["learning_evidence_event_candidates"][0]["quality"]["writeback_eligible"] = True

    report = run_learning_evidence_current_standard_compat_audit(
        learning_evidence_candidate_bridge=bridge,
        pcp_nba_candidate_projection=_pcp_payload(),
        test_learner_sandbox_readback_gate=_sandbox_payload(),
        test_learner_writeback_dry_run_manifest=_dry_run_manifest_payload(),
        test_learner_writeback_execution_gate=_execution_gate_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["blocker_count"] > 0
    assert "candidate_event_writeback_eligible:C1" in report["blockers"]


def test_current_standard_compat_audit_fails_if_pcp_readback_is_claimed() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_current_standard_compat_audit import (
        run_learning_evidence_current_standard_compat_audit,
    )

    pcp = _pcp_payload()
    pcp["summary"]["pcp_readback_count"] = 1
    pcp["personalization_context_pack_candidate"]["readback_verified"] = True

    report = run_learning_evidence_current_standard_compat_audit(
        learning_evidence_candidate_bridge=_bridge_payload(),
        pcp_nba_candidate_projection=pcp,
        test_learner_sandbox_readback_gate=_sandbox_payload(),
        test_learner_writeback_dry_run_manifest=_dry_run_manifest_payload(),
        test_learner_writeback_execution_gate=_execution_gate_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert "pcp_readback_count_nonzero" in report["blockers"]
    assert "pcp_candidate_readback_verified_claimed" in report["blockers"]


def test_current_standard_compat_audit_fails_if_execution_gate_allows_writeback() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_current_standard_compat_audit import (
        run_learning_evidence_current_standard_compat_audit,
    )

    gate = _execution_gate_payload()
    gate["execution_decision"]["writeback_allowed"] = True

    report = run_learning_evidence_current_standard_compat_audit(
        learning_evidence_candidate_bridge=_bridge_payload(),
        pcp_nba_candidate_projection=_pcp_payload(),
        test_learner_sandbox_readback_gate=_sandbox_payload(),
        test_learner_writeback_dry_run_manifest=_dry_run_manifest_payload(),
        test_learner_writeback_execution_gate=gate,
    )

    assert report["verdict"] == "FAIL"
    assert "execution_gate_writeback_allowed" in report["blockers"]


def test_current_standard_compat_audit_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_current_standard_compat_audit import main

    bridge = tmp_path / "bridge.json"
    pcp = tmp_path / "pcp.json"
    sandbox = tmp_path / "sandbox.json"
    dry_run = tmp_path / "dry_run.json"
    gate = tmp_path / "gate.json"
    output = tmp_path / "audit.json"
    bridge.write_text(json.dumps(_bridge_payload(), ensure_ascii=False), encoding="utf-8")
    pcp.write_text(json.dumps(_pcp_payload(), ensure_ascii=False), encoding="utf-8")
    sandbox.write_text(json.dumps(_sandbox_payload(), ensure_ascii=False), encoding="utf-8")
    dry_run.write_text(json.dumps(_dry_run_manifest_payload(), ensure_ascii=False), encoding="utf-8")
    gate.write_text(json.dumps(_execution_gate_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--learning-evidence-candidate-bridge",
            str(bridge),
            "--pcp-nba-candidate-projection",
            str(pcp),
            "--test-learner-sandbox-readback-gate",
            str(sandbox),
            "--test-learner-writeback-dry-run-manifest",
            str(dry_run),
            "--test-learner-writeback-execution-gate",
            str(gate),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1"
    assert payload["summary"]["not_current_standard_payload_count"] == 2
