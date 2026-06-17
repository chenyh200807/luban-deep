from __future__ import annotations

import json
from pathlib import Path


def _guard_patch_plan_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_guard_patch_plan.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_audit_record.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_patch_plan": True,
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
            "audit_record_count": 1,
            "guard_plan_item_count": 1,
            "source_ref_reaudit_required_count": 0,
            "leaf_retaxonomy_required_count": 0,
            "dismissed_after_shadow_review_count": 0,
            "blocker_count": 0,
        },
        "guard_plan_items": [
            {
                "guard_plan_item_id": "shadow_residual_guard_plan:AR1",
                "audit_record_id": "AR1",
                "packet_id": "P1",
                "work_order_id": "WO1",
                "leaf_id": "L1",
                "planned_guard_action": "block_positive_context_until_source_ref_reviewed",
                "plan_status": "review_required",
                "action_source": "shadow_residual_audit_record",
                "reason_codes": ["negative_evidence_conflict"],
                "source_lanes": ["textbook"],
                "record_ids": ["R1"],
                "field_ids": ["F1"],
                "artifact_ids": ["A1"],
                "residual_case_ids": ["case-1"],
                "tasks": ["rag_answer"],
                "guard_evidence_count": 2,
                "candidate_only": True,
                "review_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            }
        ],
        "blockers": [],
        "not_exercised": [
            "human_reviewer_signoff",
            "governance_signoff",
            "candidate_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
            "runtime_install",
            "learner_memory_writeback",
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_guard_review_packets_builds_review_only_packets() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_packets import (
        build_shadow_residual_guard_review_packets,
    )

    report = build_shadow_residual_guard_review_packets(guard_patch_plan=_guard_patch_plan_payload())

    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
    assert report["input_schema"] == "luban_rich_leaf_shadow_residual_guard_patch_plan.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["decisions_recorded"] is False
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_guard_enforcement_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["guard_plan_item_count"] == 1
    assert report["summary"]["guard_review_packet_count"] == 1
    packet = report["guard_review_packets"][0]
    assert packet["guard_plan_item_id"] == "shadow_residual_guard_plan:AR1"
    assert packet["review_scope"] == "runtime_guard_candidate_review"
    assert packet["decision_recorded"] is False
    assert packet["allowed_decisions"] == [
        "confirm_guard_patch_candidate",
        "request_guard_scope_narrowing",
        "request_source_ref_reaudit",
        "reject_guard_not_needed",
    ]
    assert packet["evidence_trace"]["record_ids"] == ["R1"]
    assert packet["runtime_guard_enforcement_allowed"] is False
    assert packet["patch_generation_allowed"] is False


def test_guard_review_packets_fails_on_guard_plan_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_packets import (
        build_shadow_residual_guard_review_packets,
    )

    guard_patch_plan = _guard_patch_plan_payload()
    guard_patch_plan["classification"]["patch_generation_allowed"] = True

    report = build_shadow_residual_guard_review_packets(guard_patch_plan=guard_patch_plan)

    assert report["verdict"] == "FAIL"
    assert report["summary"]["guard_review_packet_count"] == 0
    assert "guard_patch_plan_authority_allowed:patch_generation_allowed" in report["blockers"]


def test_guard_review_packets_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_packets import main

    guard_patch_plan_path = tmp_path / "shadow_residual_guard_patch_plan.json"
    output = tmp_path / "shadow_residual_guard_review_packets.json"
    guard_patch_plan_path.write_text(json.dumps(_guard_patch_plan_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--guard-patch-plan", str(guard_patch_plan_path), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
    assert payload["summary"]["guard_review_packet_count"] == 1
