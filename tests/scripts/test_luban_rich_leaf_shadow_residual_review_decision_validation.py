from __future__ import annotations

import json
from pathlib import Path


def _review_packets_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_review_packets.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_work_orders.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_packets": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "input_work_order_count": 2,
            "review_packet_count": 2,
            "non_joinable_residual_count": 0,
            "blocker_count": 0,
        },
        "review_packets": [
            {
                "packet_id": "shadow_residual_review_packet:WO_1",
                "work_order_id": "WO_1",
                "leaf_id": "L1",
                "allowed_decisions": ["confirm_guard_needed", "dismiss_after_review"],
                "decision_recorded": False,
                "patch_generation_allowed": False,
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "candidate_only": True,
                "review_only": True,
            },
            {
                "packet_id": "shadow_residual_review_packet:WO_2",
                "work_order_id": "WO_2",
                "leaf_id": "L2",
                "allowed_decisions": ["request_source_ref_reaudit", "request_leaf_retaxonomy"],
                "decision_recorded": False,
                "patch_generation_allowed": False,
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "candidate_only": True,
                "review_only": True,
            },
        ],
        "non_joinable_residuals": [],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _decision(packet_id: str, decision: str) -> dict:
    return {
        "packet_id": packet_id,
        "decision": decision,
        "reviewer_role": "ai_council_reviewer",
        "reviewer_id": "reviewer_1",
        "rationale": "Trace supports the selected residual review action.",
        "confidence": "medium",
        "decision_recorded": True,
        "patch_generation_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def test_shadow_residual_review_decision_validation_accepts_complete_decisions() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_validation import (
        validate_shadow_residual_review_decisions,
    )

    report, merged = validate_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_payloads=[
            {
                "schema": "luban_rich_leaf_shadow_residual_review_decisions.v1",
                "decisions": [
                    _decision("shadow_residual_review_packet:WO_1", "confirm_guard_needed"),
                    _decision("shadow_residual_review_packet:WO_2", "request_source_ref_reaudit"),
                ],
            }
        ],
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_review_decision_validation.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["decisions_recorded"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["summary"]["packet_count"] == 2
    assert report["summary"]["decision_count"] == 2
    assert report["summary"]["missing_decision_count"] == 0
    assert merged["schema"] == "luban_rich_leaf_shadow_residual_review_decisions.v1"
    assert len(merged["decisions"]) == 2


def test_shadow_residual_review_decision_validation_marks_missing_as_incomplete() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_validation import (
        validate_shadow_residual_review_decisions,
    )

    report, merged = validate_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_payloads=[
            {
                "schema": "luban_rich_leaf_shadow_residual_review_decisions.v1",
                "decisions": [_decision("shadow_residual_review_packet:WO_1", "confirm_guard_needed")],
            }
        ],
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"]["missing_decision_count"] == 1
    assert report["missing_packet_ids"] == ["shadow_residual_review_packet:WO_2"]
    assert len(merged["decisions"]) == 1


def test_shadow_residual_review_decision_validation_rejects_bad_authority() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_validation import (
        validate_shadow_residual_review_decisions,
    )

    bad = _decision("shadow_residual_review_packet:WO_1", "confirm_guard_needed")
    bad["patch_generation_allowed"] = True

    report, merged = validate_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_payloads=[{"schema": "luban_rich_leaf_shadow_residual_review_decisions.v1", "decisions": [bad]}],
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["invalid_decision_count"] == 1
    assert merged["decisions"] == []


def test_shadow_residual_review_decision_validation_cli_writes_reports(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_validation import main

    review_packets = tmp_path / "shadow_residual_review_packets.json"
    decisions_dir = tmp_path / "decisions"
    output_dir = tmp_path / "out"
    decisions_dir.mkdir()
    review_packets.write_text(json.dumps(_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    (decisions_dir / "decisions.json").write_text(
        json.dumps(
            {
                "schema": "luban_rich_leaf_shadow_residual_review_decisions.v1",
                "decisions": [_decision("shadow_residual_review_packet:WO_1", "confirm_guard_needed")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--review-packets", str(review_packets), "--decisions-dir", str(decisions_dir), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "shadow_residual_review_decision_validation.json").read_text("utf-8"))
    merged = json.loads((output_dir / "merged_shadow_residual_review_decisions.json").read_text("utf-8"))
    assert report["verdict"] == "INCOMPLETE"
    assert merged["schema"] == "luban_rich_leaf_shadow_residual_review_decisions.v1"
