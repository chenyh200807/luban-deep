from __future__ import annotations

import json
from pathlib import Path


def _guard_review_packets_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_review_packets": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        },
        "summary": {
            "guard_plan_item_count": 2,
            "guard_review_packet_count": 2,
            "decision_count": 0,
            "blocker_count": 0,
        },
        "guard_review_packets": [
            {
                "guard_review_packet_id": "P1",
                "guard_plan_item_id": "G1",
                "audit_record_id": "A1",
                "packet_id": "RP1",
                "work_order_id": "WO1",
                "leaf_id": "L1",
                "allowed_decisions": [
                    "confirm_guard_patch_candidate",
                    "request_guard_scope_narrowing",
                    "request_source_ref_reaudit",
                    "reject_guard_not_needed",
                ],
                "decision_recorded": False,
                "evidence_trace": {
                    "reason_codes": ["negative_evidence_guard_review"],
                    "source_lanes": ["textbook"],
                    "record_ids": ["R1"],
                    "field_ids": ["F1"],
                    "artifact_ids": ["ART1"],
                    "residual_case_ids": ["case-1"],
                    "tasks": ["rag_answer"],
                    "guard_evidence_count": 1,
                },
                "candidate_only": True,
                "review_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            {
                "guard_review_packet_id": "P2",
                "guard_plan_item_id": "G2",
                "audit_record_id": "A2",
                "packet_id": "RP2",
                "work_order_id": "WO2",
                "leaf_id": "L2",
                "allowed_decisions": [
                    "confirm_guard_patch_candidate",
                    "request_guard_scope_narrowing",
                    "request_source_ref_reaudit",
                    "reject_guard_not_needed",
                ],
                "decision_recorded": False,
                "evidence_trace": {
                    "reason_codes": ["source_ref_conflict"],
                    "source_lanes": ["lecture"],
                    "record_ids": ["R2"],
                    "field_ids": ["F2"],
                    "artifact_ids": ["ART2"],
                    "residual_case_ids": [],
                    "tasks": ["grading"],
                    "guard_evidence_count": 1,
                },
                "candidate_only": True,
                "review_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _guard_review_decisions_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_review_decisions": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": True,
            "human_reviewer_signoff": False,
            "governance_signoff": False,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        },
        "summary": {
            "guard_review_packet_count": 2,
            "decision_count": 2,
            "blocker_count": 0,
        },
        "decisions": [
            {
                "decision_id": "D1",
                "guard_review_packet_id": "P1",
                "guard_plan_item_id": "G1",
                "audit_record_id": "A1",
                "packet_id": "RP1",
                "work_order_id": "WO1",
                "leaf_id": "L1",
                "decision": "confirm_guard_patch_candidate",
                "decision_recorded": True,
                "shadow_only": True,
                "human_reviewer_signoff": False,
                "governance_signoff": False,
                "evidence_trace": {
                    "reason_codes": ["negative_evidence_guard_review"],
                    "source_lanes": ["textbook"],
                    "record_ids": ["R1"],
                    "field_ids": ["F1"],
                    "artifact_ids": ["ART1"],
                    "residual_case_ids": ["case-1"],
                    "tasks": ["rag_answer"],
                    "guard_evidence_count": 1,
                },
                "candidate_only": True,
                "review_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            {
                "decision_id": "D2",
                "guard_review_packet_id": "P2",
                "guard_plan_item_id": "G2",
                "audit_record_id": "A2",
                "packet_id": "RP2",
                "work_order_id": "WO2",
                "leaf_id": "L2",
                "decision": "request_source_ref_reaudit",
                "decision_recorded": True,
                "shadow_only": True,
                "human_reviewer_signoff": False,
                "governance_signoff": False,
                "evidence_trace": {
                    "reason_codes": ["source_ref_conflict"],
                    "source_lanes": ["lecture"],
                    "record_ids": ["R2"],
                    "field_ids": ["F2"],
                    "artifact_ids": ["ART2"],
                    "residual_case_ids": [],
                    "tasks": ["grading"],
                    "guard_evidence_count": 1,
                },
                "candidate_only": True,
                "review_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _validation_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_review_decision_validation": True,
            "human_reviewer_signoff": False,
            "governance_signoff": False,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        },
        "summary": {
            "guard_review_packet_count": 2,
            "decision_count": 2,
            "missing_decision_count": 0,
            "invalid_decision_count": 0,
            "duplicate_decision_count": 0,
            "stale_decision_count": 0,
            "blocker_count": 0,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_guard_audit_record_records_validated_shadow_decisions_only() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_audit_record import (
        build_shadow_residual_guard_audit_record,
    )

    report = build_shadow_residual_guard_audit_record(
        guard_review_packets=_guard_review_packets_payload(),
        guard_review_decisions=_guard_review_decisions_payload(),
        validation_report=_validation_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_audit_record.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["shadow_residual_guard_audit_record"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["source_ref_mutation_allowed"] is False
    assert report["classification"]["runtime_guard_enforcement_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["guard_review_packet_count"] == 2
    assert report["summary"]["decision_count"] == 2
    assert report["summary"]["audit_record_count"] == 2
    assert report["summary"]["confirm_guard_patch_candidate_count"] == 1
    assert report["summary"]["request_source_ref_reaudit_count"] == 1
    record = report["shadow_residual_guard_audit_records"][0]
    assert record["guard_audit_record_id"] == "shadow_residual_guard_audit_record:P1"
    assert record["guard_review_packet_id"] == "P1"
    assert record["next_compiler_action"] == "guard_patch_candidate_review_required"
    assert record["decision"] == "confirm_guard_patch_candidate"
    assert record["evidence_trace"]["record_ids"] == ["R1"]
    assert record["patch_generation_allowed"] is False
    assert record["runtime_guard_enforcement_allowed"] is False


def test_guard_audit_record_blocks_incomplete_validation() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_audit_record import (
        build_shadow_residual_guard_audit_record,
    )

    validation = _validation_payload()
    validation["verdict"] = "INCOMPLETE"
    validation["summary"]["missing_decision_count"] = 1

    report = build_shadow_residual_guard_audit_record(
        guard_review_packets=_guard_review_packets_payload(),
        guard_review_decisions=_guard_review_decisions_payload(),
        validation_report=validation,
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["audit_record_count"] == 0
    assert "validation_not_pass:INCOMPLETE" in report["blockers"]
    assert "validation_missing_decision_count:1" in report["blockers"]


def test_guard_audit_record_blocks_decision_packet_mismatch() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_audit_record import (
        build_shadow_residual_guard_audit_record,
    )

    decisions = _guard_review_decisions_payload()
    decisions["decisions"][0]["leaf_id"] = "OTHER"

    report = build_shadow_residual_guard_audit_record(
        guard_review_packets=_guard_review_packets_payload(),
        guard_review_decisions=decisions,
        validation_report=_validation_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["audit_record_count"] == 0
    assert "decision_packet_join_mismatch:D1:leaf_id" in report["blockers"]


def test_guard_audit_record_blocks_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_audit_record import (
        build_shadow_residual_guard_audit_record,
    )

    decisions = _guard_review_decisions_payload()
    decisions["decisions"][0]["runtime_guard_enforcement_allowed"] = True

    report = build_shadow_residual_guard_audit_record(
        guard_review_packets=_guard_review_packets_payload(),
        guard_review_decisions=decisions,
        validation_report=_validation_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["audit_record_count"] == 0
    assert "decision_authority_allowed:D1:runtime_guard_enforcement_allowed" in report["blockers"]


def test_guard_audit_record_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_audit_record import main

    packets_path = tmp_path / "packets.json"
    decisions_path = tmp_path / "decisions.json"
    validation_path = tmp_path / "validation.json"
    output = tmp_path / "out.json"
    packets_path.write_text(json.dumps(_guard_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    decisions_path.write_text(json.dumps(_guard_review_decisions_payload(), ensure_ascii=False), encoding="utf-8")
    validation_path.write_text(json.dumps(_validation_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--guard-review-packets",
            str(packets_path),
            "--guard-review-decisions",
            str(decisions_path),
            "--validation-report",
            str(validation_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text("utf-8"))
    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_audit_record.v1"
    assert report["summary"]["audit_record_count"] == 2
