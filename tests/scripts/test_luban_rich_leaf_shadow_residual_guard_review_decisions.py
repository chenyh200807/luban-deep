from __future__ import annotations

import json
from pathlib import Path


def _guard_review_packets_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_guard_patch_plan.v1",
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
            "guard_plan_item_count": 1,
            "guard_review_packet_count": 1,
            "decision_count": 0,
            "blocker_count": 0,
        },
        "guard_review_packets": [
            {
                "guard_review_packet_id": "shadow_residual_guard_review_packet:GP1",
                "guard_plan_item_id": "GP1",
                "audit_record_id": "AR1",
                "packet_id": "P1",
                "work_order_id": "WO1",
                "leaf_id": "L1",
                "review_scope": "runtime_guard_candidate_review",
                "planned_guard_action": "block_positive_context_until_source_ref_reviewed",
                "allowed_decisions": [
                    "confirm_guard_patch_candidate",
                    "request_guard_scope_narrowing",
                    "request_source_ref_reaudit",
                    "reject_guard_not_needed",
                ],
                "review_questions": ["question"],
                "evidence_trace": {
                    "record_ids": ["R1"],
                    "source_lanes": ["textbook"],
                    "reason_codes": ["negative_evidence_conflict"],
                    "field_ids": ["F1"],
                    "artifact_ids": ["A1"],
                    "residual_case_ids": ["case-1"],
                    "tasks": ["rag_answer"],
                    "guard_evidence_count": 2,
                },
                "decision_recorded": False,
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
            "human_reviewer_decision",
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


def test_guard_review_decisions_materializes_shadow_only_decisions() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decisions import (
        build_shadow_residual_guard_review_decisions,
    )

    report = build_shadow_residual_guard_review_decisions(guard_review_packets=_guard_review_packets_payload())

    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
    assert report["input_schema"] == "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["ai_council_shadow_only"] is True
    assert report["classification"]["decisions_recorded"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_guard_enforcement_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["guard_review_packet_count"] == 1
    assert report["summary"]["decision_count"] == 1
    decision = report["decisions"][0]
    assert decision["guard_review_packet_id"] == "shadow_residual_guard_review_packet:GP1"
    assert decision["decision"] == "confirm_guard_patch_candidate"
    assert decision["decision_recorded"] is True
    assert decision["shadow_only"] is True
    assert decision["human_reviewer_signoff"] is False
    assert decision["governance_signoff"] is False
    assert decision["runtime_guard_enforcement_allowed"] is False
    assert decision["patch_generation_allowed"] is False


def test_guard_review_decisions_fails_on_packet_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decisions import (
        build_shadow_residual_guard_review_decisions,
    )

    packets = _guard_review_packets_payload()
    packets["classification"]["runtime_guard_enforcement_allowed"] = True

    report = build_shadow_residual_guard_review_decisions(guard_review_packets=packets)

    assert report["verdict"] == "FAIL"
    assert report["summary"]["decision_count"] == 0
    assert "guard_review_packets_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]


def test_guard_review_decisions_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decisions import main

    packets_path = tmp_path / "shadow_residual_guard_review_packets.json"
    output = tmp_path / "shadow_residual_guard_review_decisions.json"
    packets_path.write_text(json.dumps(_guard_review_packets_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--guard-review-packets", str(packets_path), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
    assert payload["summary"]["decision_count"] == 1
