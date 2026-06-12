from __future__ import annotations

import json
from pathlib import Path

from tests.scripts.test_luban_rich_leaf_shadow_residual_review_decision_validation import (
    _review_packets_payload,
)


def _validation_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
        "input_schema": "luban_rich_leaf_shadow_residual_review_packets.v1",
        "verdict": "INCOMPLETE",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_decision_validation": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": 2,
            "decision_count": 0,
            "missing_decision_count": 2,
            "invalid_decision_count": 0,
            "duplicate_decision_count": 0,
            "stale_decision_count": 0,
            "blocker_count": 0,
        },
        "missing_packet_ids": [
            "shadow_residual_review_packet:WO_1",
            "shadow_residual_review_packet:WO_2",
        ],
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


def test_shadow_residual_review_decision_seed_suggests_only_for_missing_packets() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_seed import (
        run_shadow_residual_review_decision_seed,
    )

    report = run_shadow_residual_review_decision_seed(
        review_packets=_review_packets_payload(),
        decision_validation=_validation_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_review_decision_seed.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["suggestion_only"] is True
    assert report["classification"]["decisions_recorded"] is False
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["summary"]["seed_suggestion_count"] == 2
    by_packet = {item["packet_id"]: item for item in report["decision_seed_suggestions"]}
    assert by_packet["shadow_residual_review_packet:WO_1"]["suggested_decision"] == "confirm_guard_needed"
    assert by_packet["shadow_residual_review_packet:WO_2"]["suggested_decision"] == "request_source_ref_reaudit"
    assert by_packet["shadow_residual_review_packet:WO_1"]["reviewer_must_confirm"] is True
    assert by_packet["shadow_residual_review_packet:WO_1"]["decision_recorded"] is False


def test_shadow_residual_review_decision_seed_fails_on_validation_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_seed import (
        run_shadow_residual_review_decision_seed,
    )

    validation = _validation_payload()
    validation["classification"]["patch_generation_allowed"] = True

    report = run_shadow_residual_review_decision_seed(
        review_packets=_review_packets_payload(),
        decision_validation=validation,
    )

    assert report["verdict"] == "FAIL"
    assert "input_decision_validation_patch_generation_allowed" in report["blockers"]


def test_shadow_residual_review_decision_seed_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_seed import main

    review_packets = tmp_path / "shadow_residual_review_packets.json"
    validation = tmp_path / "shadow_residual_review_decision_validation.json"
    output = tmp_path / "shadow_residual_review_decision_seed.json"
    review_packets.write_text(json.dumps(_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    validation.write_text(json.dumps(_validation_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--review-packets",
            str(review_packets),
            "--decision-validation",
            str(validation),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_review_decision_seed.v1"
    assert payload["summary"]["seed_suggestion_count"] == 2
