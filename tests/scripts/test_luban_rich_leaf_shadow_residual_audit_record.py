from __future__ import annotations

import json
from pathlib import Path

from tests.scripts.test_luban_rich_leaf_shadow_residual_review_decision_materializer import (
    _seed_payload,
)
from tests.scripts.test_luban_rich_leaf_shadow_residual_review_decision_validation import (
    _review_packets_payload,
)


def _decisions_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_review_decisions.v1",
        "input_schemas": {
            "review_packets": "luban_rich_leaf_shadow_residual_review_packets.v1",
            "decision_seed": "luban_rich_leaf_shadow_residual_review_decision_seed.v1",
        },
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": True,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": 2,
            "seed_suggestion_count": 2,
            "decision_count": 2,
            "blocker_count": 0,
        },
        "decisions": [
            {
                "packet_id": "shadow_residual_review_packet:WO_1",
                "decision": "confirm_guard_needed",
                "reviewer_role": "ai_council_shadow_reviewer",
                "reviewer_id": "codex_ai_council_shadow_v1",
                "rationale": "Guard evidence should remain under review.",
                "confidence": "medium",
                "decision_recorded": True,
                "shadow_only": True,
                "source_seed_id": "shadow_residual_review_decision_seed:shadow_residual_review_packet:WO_1",
                "work_order_id": "WO_1",
                "leaf_id": "L1",
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "packet_id": "shadow_residual_review_packet:WO_2",
                "decision": "request_source_ref_reaudit",
                "reviewer_role": "ai_council_shadow_reviewer",
                "reviewer_id": "codex_ai_council_shadow_v1",
                "rationale": "Runtime residual needs source reference review.",
                "confidence": "medium",
                "decision_recorded": True,
                "shadow_only": True,
                "source_seed_id": "shadow_residual_review_decision_seed:shadow_residual_review_packet:WO_2",
                "work_order_id": "WO_2",
                "leaf_id": "L2",
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
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


def _validation_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_review_packets.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_decision_validation": True,
            "decisions_recorded": True,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": 2,
            "decision_count": 2,
            "missing_decision_count": 0,
            "invalid_decision_count": 0,
            "duplicate_decision_count": 0,
            "stale_decision_count": 0,
            "blocker_count": 0,
        },
        "missing_packet_ids": [],
        "invalid_decisions": [],
        "duplicate_decisions": [],
        "stale_decisions_ignored": [],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_shadow_residual_audit_record_builds_review_only_records() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_audit_record import (
        build_shadow_residual_audit_record,
    )

    report = build_shadow_residual_audit_record(
        review_packets=_review_packets_payload(),
        review_decisions=_decisions_payload(),
        decision_validation=_validation_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_audit_record.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["audit_record_count"] == 2
    assert report["summary"]["guard_review_required_count"] == 1
    assert report["summary"]["source_ref_reaudit_required_count"] == 1
    records = {record["packet_id"]: record for record in report["shadow_residual_audit_records"]}
    assert records["shadow_residual_review_packet:WO_1"]["next_compiler_action"] == "guard_review_required"
    assert records["shadow_residual_review_packet:WO_2"]["next_compiler_action"] == "source_ref_reaudit_required"
    assert all(record["patch_generation_allowed"] is False for record in records.values())
    assert all(record["runtime_install_allowed"] is False for record in records.values())
    assert all(record["release_truth_claimed"] is False for record in records.values())


def test_shadow_residual_audit_record_fails_without_validation_pass() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_audit_record import (
        build_shadow_residual_audit_record,
    )

    validation = _validation_payload()
    validation["verdict"] = "INCOMPLETE"
    validation["summary"]["missing_decision_count"] = 1

    report = build_shadow_residual_audit_record(
        review_packets=_review_packets_payload(),
        review_decisions=_decisions_payload(),
        decision_validation=validation,
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["audit_record_count"] == 0
    assert "decision_validation_not_pass:INCOMPLETE" in report["blockers"]


def test_shadow_residual_audit_record_rejects_decision_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_audit_record import (
        build_shadow_residual_audit_record,
    )

    decisions = _decisions_payload()
    decisions["decisions"][0]["runtime_install_allowed"] = True

    report = build_shadow_residual_audit_record(
        review_packets=_review_packets_payload(),
        review_decisions=decisions,
        decision_validation=_validation_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["audit_record_count"] == 0
    assert any("decision_authority_allowed" in blocker for blocker in report["blockers"])


def test_shadow_residual_audit_record_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_audit_record import main

    packets_path = tmp_path / "shadow_residual_review_packets.json"
    decisions_path = tmp_path / "ai_council_shadow_review_decisions.json"
    validation_path = tmp_path / "shadow_residual_review_decision_validation.json"
    output = tmp_path / "shadow_residual_audit_record.json"
    packets_path.write_text(json.dumps(_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    decisions_path.write_text(json.dumps(_decisions_payload(), ensure_ascii=False), encoding="utf-8")
    validation_path.write_text(json.dumps(_validation_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--review-packets",
            str(packets_path),
            "--review-decisions",
            str(decisions_path),
            "--decision-validation",
            str(validation_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_audit_record.v1"
    assert payload["summary"]["audit_record_count"] == 2
