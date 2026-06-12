from __future__ import annotations

import json
from pathlib import Path


def _audit_record_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_audit_record.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_audit_record": True,
            "ai_council_shadow_only": True,
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
            "packet_count": 2,
            "decision_count": 2,
            "audit_record_count": 2,
            "blocker_count": 0,
            "guard_review_required_count": 1,
            "source_ref_reaudit_required_count": 1,
            "leaf_retaxonomy_required_count": 0,
            "dismissed_after_shadow_review_count": 0,
        },
        "shadow_residual_audit_records": [
            {
                "audit_record_id": "shadow_residual_audit_record:packet:WO_1",
                "packet_id": "packet:WO_1",
                "work_order_id": "WO_1",
                "leaf_id": "L1",
                "review_scope": "guard_review",
                "trigger_reason": "fail_open_risk",
                "decision": "confirm_guard_needed",
                "next_compiler_action": "guard_review_required",
                "shadow_only": True,
                "work_order_trace": {
                    "artifact_ids": ["A1"],
                    "field_ids": ["F1"],
                    "record_ids": ["R1"],
                    "source_lanes": ["textbook"],
                    "reason_codes": ["negative_evidence_conflict"],
                    "guard_evidence_count": 2,
                    "residual_case_ids": ["case-1"],
                    "tasks": ["rag_answer"],
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
                "audit_record_id": "shadow_residual_audit_record:packet:WO_2",
                "packet_id": "packet:WO_2",
                "work_order_id": "WO_2",
                "leaf_id": "L2",
                "review_scope": "source_ref_review",
                "trigger_reason": "source_ref_mismatch",
                "decision": "request_source_ref_reaudit",
                "next_compiler_action": "source_ref_reaudit_required",
                "shadow_only": True,
                "work_order_trace": {
                    "artifact_ids": ["A2"],
                    "field_ids": ["F2"],
                    "record_ids": ["R2"],
                    "source_lanes": ["lecture"],
                    "reason_codes": ["span_mismatch"],
                    "guard_evidence_count": 0,
                    "residual_case_ids": ["case-2"],
                    "tasks": ["grading"],
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
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_shadow_residual_guard_patch_plan_builds_review_only_plan_items() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_patch_plan import (
        build_shadow_residual_guard_patch_plan,
    )

    report = build_shadow_residual_guard_patch_plan(audit_record=_audit_record_payload())

    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_patch_plan.v1"
    assert report["input_schema"] == "luban_rich_leaf_shadow_residual_audit_record.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_guard_enforcement_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["audit_record_count"] == 2
    assert report["summary"]["guard_plan_item_count"] == 1
    assert report["summary"]["source_ref_reaudit_required_count"] == 1
    item = report["guard_plan_items"][0]
    assert item["audit_record_id"] == "shadow_residual_audit_record:packet:WO_1"
    assert item["planned_guard_action"] == "block_positive_context_until_source_ref_reviewed"
    assert item["reason_codes"] == ["negative_evidence_conflict"]
    assert item["source_lanes"] == ["textbook"]
    assert item["record_ids"] == ["R1"]
    assert item["runtime_guard_enforcement_allowed"] is False
    assert item["patch_generation_allowed"] is False


def test_shadow_residual_guard_patch_plan_fails_on_audit_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_patch_plan import (
        build_shadow_residual_guard_patch_plan,
    )

    audit_record = _audit_record_payload()
    audit_record["classification"]["runtime_guard_enforcement_allowed"] = True

    report = build_shadow_residual_guard_patch_plan(audit_record=audit_record)

    assert report["verdict"] == "FAIL"
    assert report["summary"]["guard_plan_item_count"] == 0
    assert "audit_record_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]


def test_shadow_residual_guard_patch_plan_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_patch_plan import main

    audit_record_path = tmp_path / "shadow_residual_audit_record.json"
    output = tmp_path / "shadow_residual_guard_patch_plan.json"
    audit_record_path.write_text(json.dumps(_audit_record_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--audit-record", str(audit_record_path), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_guard_patch_plan.v1"
    assert payload["summary"]["guard_plan_item_count"] == 1
