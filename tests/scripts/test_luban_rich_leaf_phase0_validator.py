from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _source_ref() -> dict:
    span = "建筑物由结构体系、围护体系和设备体系组成。"
    return {
        "source_ref_id": "src_1",
        "source_registry_id": "docs2026_registry",
        "source_dataset_id": "textbook_2026",
        "source_version": "2026.0",
        "extractor_version": "extractor.v1",
        "source_lane": "textbook",
        "path": "docs/2026/textbook.md",
        "record_id": "1A411011:block-1",
        "span": span,
        "span_hash": source_span_hash(span),
    }


def _artifact(artifact_id: str = "leaf_ok") -> dict:
    return {
        "artifact_id": artifact_id,
        "leaf_id": "1A411011-01-a",
        "bundle_version": "v_rich_leaf_candidate_20260611",
        "candidate_status": "reviewed_candidate",
        "source_refs": [_source_ref()],
        "rules": [
            {
                "field_id": "rule_1",
                "claim_status": "source_backed",
                "source_ref_ids": ["src_1"],
                "rule_type": "mandatory",
                "statement": "建筑物构成应区分结构、围护、设备体系。",
            }
        ],
        "rubric_link_index": [
            {
                "field_id": "rubric_link_1",
                "claim_status": "source_backed",
                "source_ref_ids": ["src_1"],
                "scoring_artifact_id": "case_rubric_v1",
                "rubric_version": "2026.case.v1",
                "scoring_point_ids": ["P1"],
                "link_status": "reviewed_candidate",
            }
        ],
    }


def test_build_phase0_validator_report_preserves_candidate_safety() -> None:
    from scripts.run_luban_rich_leaf_phase0_validator import build_phase0_validator_report

    ok_artifact = _artifact("leaf_ok")
    bad_artifact = _artifact("leaf_bad")
    bad_artifact["candidate_status"] = "controlled_default"
    bad_artifact["rubric_link_index"][0]["policy_type"] = "exact_required"

    report = build_phase0_validator_report(
        artifacts=[ok_artifact, bad_artifact],
        bundle_version="v_rich_leaf_candidate_20260611",
        manifest_hash="sha256:test-manifest",
        pack_tasks=["grading"],
    )

    assert report["schema"] == "luban_rich_leaf_phase0_validator_report.v1"
    assert report["summary"]["artifact_count"] == 2
    assert report["summary"]["valid_artifact_count"] == 1
    assert report["summary"]["invalid_artifact_count"] == 1
    assert report["classification"]["candidate_only"] is True
    assert report["safety"]["canonical_truth_written"] is False
    assert report["safety"]["official_score_allowed"] is False
    assert report["safety"]["installed_runtime_supply"] is False
    assert all(value in (False, 0) for value in report["safety"].values())
    invalid = [row for row in report["validation_reports"] if row["artifact_id"] == "leaf_bad"][0]
    assert "artifact_self_declared_controlled_default" in invalid["blockers"]
    assert report["pack_smoke"]["grading"]["canonical_write_allowed"] is False
    assert "rule_1" in report["pack_smoke"]["grading"]["consumption_trace"]["consumed_field_ids"]


def test_cli_writes_phase0_validator_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_phase0_validator import main

    input_path = tmp_path / "rich_leaf_candidates.json"
    output_dir = tmp_path / "out"
    _write_json(
        input_path,
        {
            "schema": "luban.rich_leaf_artifact_batch.v0",
            "bundle_version": "v_rich_leaf_candidate_20260611",
            "manifest_hash": "sha256:test-manifest",
            "rich_leaf_artifacts": [_artifact()],
        },
    )

    exit_code = main(["--input", str(input_path), "--output-dir", str(output_dir), "--pack-task", "grading"])

    assert exit_code == 0
    report = json.loads((output_dir / "rich_leaf_phase0_validator_report.json").read_text("utf-8"))
    assert report["summary"]["valid_artifact_count"] == 1
    assert report["pack_smoke"]["grading"]["task"] == "grading"
    assert report["safety"]["production_write_count"] == 0
    assert all(value in (False, 0) for value in report["safety"].values())


def test_invalid_artifacts_are_excluded_from_pack_positive_context() -> None:
    from scripts.run_luban_rich_leaf_phase0_validator import build_phase0_validator_report

    bad_artifact = _artifact("leaf_bad")
    bad_artifact["rules"][0]["source_ref_ids"] = ["missing_src"]

    report = build_phase0_validator_report(
        artifacts=[bad_artifact],
        bundle_version="v_rich_leaf_candidate_20260611",
        manifest_hash="sha256:test-manifest",
        pack_tasks=["grading"],
    )

    assert report["summary"]["valid_artifact_count"] == 0
    assert report["pack_smoke"]["grading"]["fields"] == []
    assert "source_backed_field_without_valid_source:rules:rule_1" in report["blocker_counts"]
    assert report["pack_smoke"]["grading"]["official_score_allowed"] is False
    assert report["pack_smoke"]["grading"]["canonical_write_allowed"] is False
