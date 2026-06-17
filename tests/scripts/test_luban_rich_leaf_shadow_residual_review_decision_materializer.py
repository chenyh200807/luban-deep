from __future__ import annotations

import json
from pathlib import Path

from tests.scripts.test_luban_rich_leaf_shadow_residual_review_decision_seed import (
    _validation_payload,
)
from tests.scripts.test_luban_rich_leaf_shadow_residual_review_decision_validation import (
    _review_packets_payload,
)


def _seed_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_review_decision_seed.v1",
        "input_schemas": {
            "review_packets": "luban_rich_leaf_shadow_residual_review_packets.v1",
            "decision_validation": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
        },
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_decision_seed": True,
            "suggestion_only": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": 2,
            "missing_packet_count": 2,
            "seed_suggestion_count": 2,
            "blocker_count": 0,
        },
        "decision_seed_suggestions": [
            {
                "seed_id": "shadow_residual_review_decision_seed:shadow_residual_review_packet:WO_1",
                "packet_id": "shadow_residual_review_packet:WO_1",
                "work_order_id": "WO_1",
                "leaf_id": "L1",
                "review_scope": "preventive_negative_evidence_guard_review",
                "suggested_decision": "confirm_guard_needed",
                "suggestion_confidence": "medium",
                "reason_codes": ["negative_evidence_guard_review"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "candidate_only": True,
                "review_only": True,
            },
            {
                "seed_id": "shadow_residual_review_decision_seed:shadow_residual_review_packet:WO_2",
                "packet_id": "shadow_residual_review_packet:WO_2",
                "work_order_id": "WO_2",
                "leaf_id": "L2",
                "review_scope": "runtime_residual_source_ref_review",
                "suggested_decision": "request_source_ref_reaudit",
                "suggestion_confidence": "medium",
                "reason_codes": ["runtime_residual"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "candidate_only": True,
                "review_only": True,
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


def test_shadow_residual_review_decision_materializer_records_shadow_only_decisions() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_materializer import (
        materialize_shadow_residual_review_decisions,
    )

    report = materialize_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_seed=_seed_payload(),
        reviewer_id="codex_ai_council_shadow_v1",
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_review_decisions.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["ai_council_shadow_only"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["summary"]["decision_count"] == 2
    assert report["summary"]["blocker_count"] == 0
    first = report["decisions"][0]
    assert first["reviewer_role"] == "ai_council_shadow_reviewer"
    assert first["reviewer_id"] == "codex_ai_council_shadow_v1"
    assert first["decision_recorded"] is True
    assert first["decision"] == "confirm_guard_needed"
    assert first["patch_generation_allowed"] is False
    assert first["runtime_install_allowed"] is False
    assert first["release_truth_claimed"] is False
    assert first["shadow_only"] is True


def test_shadow_residual_review_decision_materializer_fails_on_seed_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_materializer import (
        materialize_shadow_residual_review_decisions,
    )

    seed = _seed_payload()
    seed["classification"]["decisions_recorded"] = True

    report = materialize_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_seed=seed,
        reviewer_id="codex_ai_council_shadow_v1",
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["decision_count"] == 0
    assert "input_decision_seed_decisions_recorded" in report["blockers"]


def test_shadow_residual_review_decision_materializer_output_passes_validation() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_materializer import (
        materialize_shadow_residual_review_decisions,
    )
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_validation import (
        validate_shadow_residual_review_decisions,
    )

    decisions = materialize_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_seed=_seed_payload(),
        reviewer_id="codex_ai_council_shadow_v1",
    )
    report, merged = validate_shadow_residual_review_decisions(
        review_packets=_review_packets_payload(),
        decision_payloads=[decisions],
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["decision_count"] == 2
    assert report["summary"]["missing_decision_count"] == 0
    assert len(merged["decisions"]) == 2


def test_shadow_residual_review_decision_materializer_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_decision_materializer import main

    review_packets = tmp_path / "shadow_residual_review_packets.json"
    decision_seed = tmp_path / "shadow_residual_review_decision_seed.json"
    output = tmp_path / "ai_council_shadow_review_decisions.json"
    review_packets.write_text(json.dumps(_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    decision_seed.write_text(json.dumps(_seed_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--review-packets",
            str(review_packets),
            "--decision-seed",
            str(decision_seed),
            "--reviewer-id",
            "codex_ai_council_shadow_v1",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_review_decisions.v1"
    assert payload["summary"]["decision_count"] == 2
