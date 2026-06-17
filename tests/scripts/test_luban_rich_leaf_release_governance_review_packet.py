from __future__ import annotations

import json
from pathlib import Path


def _compiler_status() -> dict:
    return {
        "schema": "luban_rich_leaf_compiler_status_ledger.v1",
        "overall_verdict": "WEAK_GO_SHADOW_CANDIDATE",
        "quality_claim_allowed": False,
        "release_truth_claimed": False,
        "runtime_default_status": "ready_for_controlled_default_review",
        "learning_brain_write_status": "blocked_pending_signed_authorization",
        "summary": {
            "blocker_count": 2,
            "semantic_audit_item_count": 3506,
            "semantic_decision_count": 3506,
            "missing_semantic_decision_count": 0,
            "provider_call_count": 1096,
            "runtime_token_pack_unit_count": 102,
            "planned_learning_event_count": 274,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "safety_violation_count": 0,
        },
        "blockers": [
            "learning_brain_signed_authorization_missing",
            "release_governance_not_exercised",
        ],
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
        },
    }


def _controlled_default_authorization() -> dict:
    return {
        "schema": "luban_rich_leaf_controlled_default_authorization_package.v1",
        "verdict": "READY_FOR_OPERATOR_SIGNATURE",
        "authorization_decision": {
            "operator_signature_recorded": False,
            "controlled_default_authorized": False,
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "release_truth_authorized": False,
        },
        "summary": {"blocker_count": 0, "write_executed": False, "production_write_count": 0},
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _writeback_execution_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
        "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
        "summary": {
            "blocker_count": 0,
            "dry_run_planned_event_count": 274,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
        },
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
        },
    }


def test_release_governance_review_packet_blocks_release_truth_until_signoffs() -> None:
    from scripts.run_luban_rich_leaf_release_governance_review_packet import (
        run_release_governance_review_packet,
    )

    report = run_release_governance_review_packet(
        compiler_status_ledger=_compiler_status(),
        controlled_default_authorization=_controlled_default_authorization(),
        writeback_execution_gate=_writeback_execution_gate(),
    )

    assert report["schema"] == "luban_rich_leaf_release_governance_review_packet.v1"
    assert report["verdict"] == "BLOCKED_FOR_RELEASE_TRUTH"
    assert "learning_brain_signed_authorization_missing" in report["release_blockers"]
    assert "operator_signature_missing" in report["release_blockers"]
    assert report["release_decision"]["release_truth_claim_allowed"] is False
    assert report["release_decision"]["official_score_allowed"] is False
    assert report["summary"]["production_write_count"] == 0
    assert report["classification"]["release_truth_claimed"] is False


def _operator_signature_record(controlled_default_authorization: dict) -> dict:
    from scripts.run_luban_rich_leaf_operator_signature_capture import content_hash

    return {
        "schema": "luban_rich_leaf_operator_signature_record.v1",
        "verdict": "OPERATOR_SIGNATURE_CAPTURED",
        "signature": {
            "template_id": "rich_leaf_controlled_default_operator_signature_v1",
            "signature_status": "signed",
            "operator_id": "owner",
            "statement": "authorized_by_owner_20260613, scope: rich-leaf frozen v1 controlled default",
            "signed_at": "2026-06-13T00:00:00+08:00",
        },
        "authorization_binding": {
            "authorization_package_schema": "luban_rich_leaf_controlled_default_authorization_package.v1",
            "authorization_package_verdict": "READY_FOR_OPERATOR_SIGNATURE",
            "authorization_package_content_hash": content_hash(controlled_default_authorization),
        },
        "granted_scope": {
            "controlled_default_operator_signature": True,
            "runtime_default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "remote_write_allowed": False,
            "release_truth_allowed": False,
        },
        "summary": {"blocker_count": 0, "write_executed": False, "production_write_count": 0},
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_release_governance_review_packet_consumes_valid_operator_signature() -> None:
    from scripts.run_luban_rich_leaf_release_governance_review_packet import (
        run_release_governance_review_packet,
    )

    controlled = _controlled_default_authorization()
    record = _operator_signature_record(controlled)
    report = run_release_governance_review_packet(
        compiler_status_ledger=_compiler_status(),
        controlled_default_authorization=controlled,
        writeback_execution_gate=_writeback_execution_gate(),
        operator_signature_record=record,
    )

    assert "operator_signature_missing" not in report["release_blockers"]
    assert "controlled_default_authorization_missing" not in report["release_blockers"]
    # signature scope is controlled default only: release truth stays blocked
    assert "release_truth_authorization_missing" in report["release_blockers"]
    assert "learning_brain_signed_authorization_missing" in report["release_blockers"]
    assert report["verdict"] == "BLOCKED_FOR_RELEASE_TRUTH"
    assert report["operator_signature"]["recorded"] is True
    assert report["operator_signature"]["operator_id"] == "owner"
    assert report["operator_signature"]["content_hash_bound"] is True
    # release decision invariants never relax with a signature present
    assert report["release_decision"]["release_truth_claim_allowed"] is False
    assert report["release_decision"]["production_default_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_release_governance_review_packet_rejects_unbound_operator_signature() -> None:
    from scripts.run_luban_rich_leaf_release_governance_review_packet import (
        run_release_governance_review_packet,
    )

    controlled = _controlled_default_authorization()
    record = _operator_signature_record(controlled)
    record["authorization_binding"]["authorization_package_content_hash"] = "0" * 64
    report = run_release_governance_review_packet(
        compiler_status_ledger=_compiler_status(),
        controlled_default_authorization=controlled,
        writeback_execution_gate=_writeback_execution_gate(),
        operator_signature_record=record,
    )

    assert "operator_signature_record_invalid:content_hash_unbound" in report["release_blockers"]
    assert "operator_signature_missing" in report["release_blockers"]
    assert report["operator_signature"]["recorded"] is False


def test_release_governance_review_packet_fails_closed_on_safety_drift() -> None:
    from scripts.run_luban_rich_leaf_release_governance_review_packet import (
        run_release_governance_review_packet,
    )

    compiler_status = _compiler_status()
    compiler_status["safety"]["production_write_count"] = 1
    report = run_release_governance_review_packet(
        compiler_status_ledger=compiler_status,
        controlled_default_authorization=_controlled_default_authorization(),
        writeback_execution_gate=_writeback_execution_gate(),
    )

    assert report["verdict"] == "NO_GO_SAFETY_INVARIANT"
    assert "compiler_status_ledger:production_write_count_nonzero" in report["safety_violations"]


def test_release_governance_review_packet_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_release_governance_review_packet import main

    compiler_status = tmp_path / "compiler_status.json"
    controlled_default = tmp_path / "controlled_default.json"
    writeback = tmp_path / "writeback.json"
    output = tmp_path / "release_governance_review_packet.json"
    compiler_status.write_text(json.dumps(_compiler_status(), ensure_ascii=False), encoding="utf-8")
    controlled_default.write_text(json.dumps(_controlled_default_authorization(), ensure_ascii=False), encoding="utf-8")
    writeback.write_text(json.dumps(_writeback_execution_gate(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--compiler-status-ledger",
            str(compiler_status),
            "--controlled-default-authorization",
            str(controlled_default),
            "--writeback-execution-gate",
            str(writeback),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "BLOCKED_FOR_RELEASE_TRUTH"
