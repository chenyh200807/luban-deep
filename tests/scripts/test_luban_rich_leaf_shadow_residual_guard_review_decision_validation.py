from __future__ import annotations

import json
from pathlib import Path

from tests.scripts.test_luban_rich_leaf_shadow_residual_guard_review_decisions import (
    _guard_review_packets_payload,
)


def _decision(packet_id: str, decision: str = "confirm_guard_patch_candidate") -> dict:
    return {
        "decision_id": f"shadow_residual_guard_review_decision:{packet_id}",
        "guard_review_packet_id": packet_id,
        "guard_plan_item_id": "GP1",
        "audit_record_id": "AR1",
        "packet_id": "P1",
        "work_order_id": "WO1",
        "leaf_id": "L1",
        "decision": decision,
        "decision_recorded": True,
        "reviewer_role": "ai_council_shadow_guard_reviewer",
        "reviewer_id": "codex_ai_council_shadow_guard_v1",
        "rationale": "Trace supports keeping this guard candidate under review.",
        "confidence": "medium",
        "shadow_only": True,
        "human_reviewer_signoff": False,
        "governance_signoff": False,
        "evidence_trace": {
            "record_ids": ["R1"],
            "source_lanes": ["textbook"],
            "reason_codes": ["negative_evidence_conflict"],
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
    }


def test_guard_review_decision_validation_accepts_complete_decisions() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decision_validation import (
        validate_shadow_residual_guard_review_decisions,
    )

    report, merged = validate_shadow_residual_guard_review_decisions(
        guard_review_packets=_guard_review_packets_payload(),
        decision_payloads=[
            {
                "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
                "verdict": "PASS",
                "decisions": [_decision("shadow_residual_guard_review_packet:GP1")],
            }
        ],
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["review_only"] is True
    assert report["classification"]["decisions_recorded"] is True
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["runtime_guard_enforcement_allowed"] is False
    assert report["summary"]["guard_review_packet_count"] == 1
    assert report["summary"]["decision_count"] == 1
    assert report["summary"]["missing_decision_count"] == 0
    assert merged["schema"] == "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
    assert len(merged["decisions"]) == 1


def test_guard_review_decision_validation_marks_missing_as_incomplete() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decision_validation import (
        validate_shadow_residual_guard_review_decisions,
    )

    report, merged = validate_shadow_residual_guard_review_decisions(
        guard_review_packets=_guard_review_packets_payload(),
        decision_payloads=[],
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"]["missing_decision_count"] == 1
    assert report["missing_guard_review_packet_ids"] == ["shadow_residual_guard_review_packet:GP1"]
    assert merged["decisions"] == []


def test_guard_review_decision_validation_rejects_bad_authority() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decision_validation import (
        validate_shadow_residual_guard_review_decisions,
    )

    bad = _decision("shadow_residual_guard_review_packet:GP1")
    bad["runtime_guard_enforcement_allowed"] = True

    report, merged = validate_shadow_residual_guard_review_decisions(
        guard_review_packets=_guard_review_packets_payload(),
        decision_payloads=[
            {
                "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
                "verdict": "PASS",
                "decisions": [bad],
            }
        ],
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["invalid_decision_count"] == 1
    assert merged["decisions"] == []


def test_guard_review_decision_validation_ignores_stale_decisions() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decision_validation import (
        validate_shadow_residual_guard_review_decisions,
    )

    report, merged = validate_shadow_residual_guard_review_decisions(
        guard_review_packets=_guard_review_packets_payload(),
        decision_payloads=[
            {
                "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
                "verdict": "PASS",
                "decisions": [_decision("stale_packet")],
            }
        ],
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"]["stale_decision_count"] == 1
    assert report["summary"]["missing_decision_count"] == 1
    assert merged["decisions"] == []


def test_guard_review_decision_validation_cli_writes_reports(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_guard_review_decision_validation import main

    packets_path = tmp_path / "shadow_residual_guard_review_packets.json"
    decisions_dir = tmp_path / "decisions"
    output_dir = tmp_path / "out"
    decisions_dir.mkdir()
    packets_path.write_text(json.dumps(_guard_review_packets_payload(), ensure_ascii=False), encoding="utf-8")
    (decisions_dir / "shadow_residual_guard_review_decisions.json").write_text(
        json.dumps(
            {
                "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
                "verdict": "PASS",
                "decisions": [_decision("shadow_residual_guard_review_packet:GP1")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--guard-review-packets", str(packets_path), "--decisions-dir", str(decisions_dir), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "shadow_residual_guard_review_decision_validation.json").read_text("utf-8"))
    merged = json.loads((output_dir / "merged_shadow_residual_guard_review_decisions.json").read_text("utf-8"))
    assert report["verdict"] == "PASS"
    assert merged["schema"] == "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
