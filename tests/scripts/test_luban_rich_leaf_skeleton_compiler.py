from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import validate_rich_leaf_artifact


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sample_manifest() -> dict:
    return {
        "schema": "luban_rich_leaf_phase1_sample_manifest.v1",
        "seed": "rich_leaf_phase1_20260611",
        "selected_leaves": [
            {
                "leaf_id": "L1",
                "bucket": "textbook-strong",
                "name_path": "A > L1",
                "keywords": ["构成"],
                "counts": {"textbook": 1, "standard": 0, "lecture": 0, "question": 0},
                "task_pairs": [],
            },
            {
                "leaf_id": "L2",
                "bucket": "weak/polluted/sparse",
                "name_path": "A > L2",
                "keywords": ["缺源"],
                "counts": {"textbook": 0, "standard": 0, "lecture": 0, "question": 0},
                "task_pairs": [],
            },
        ],
        "input_hashes": {
            "canonical_unified_knowledge": "unified-hash",
            "canonical_taxonomy_index": "tax-hash",
            "source_alignment_repairs": "repair-hash",
        },
    }


def _unified_bundle() -> dict:
    return {
        "manifest": {"content_hash": "unified-hash"},
        "nodes": {
            "L1": {
                "name_path": "A > L1",
                "counts": {"textbook": 1, "standard": 0, "lecture": 0, "question": 0},
                "sources": {
                    "textbook": [
                        {
                            "unit_id": "TB_1",
                            "authority_tier": "textbook_verbatim",
                            "confidence": 0.9,
                            "method": "anchor+keyword",
                            "text_preview": "建筑物由结构体系、围护体系和设备体系组成。",
                            "provenance": {
                                "chunk_id": "1A411011_001",
                                "content_hash": "source-hash",
                            },
                        }
                    ]
                },
            },
            "L2": {"name_path": "A > L2", "counts": {}, "sources": {}},
        },
    }


def test_build_rich_leaf_skeletons_are_candidate_only_and_validator_safe() -> None:
    from scripts.run_luban_rich_leaf_skeleton_compiler import build_rich_leaf_skeleton_batch

    batch = build_rich_leaf_skeleton_batch(
        sample_manifest=_sample_manifest(),
        unified_bundle=_unified_bundle(),
        bundle_version="v_rich_leaf_skeleton_candidate_20260611",
        max_sources_per_lane=2,
    )

    assert batch["schema"] == "luban_rich_leaf_skeleton_batch.v1"
    assert batch["summary"]["artifact_count"] == 2
    assert batch["summary"]["with_source_refs_count"] == 1
    assert batch["safety"]["canonical_truth_written"] is False
    artifact = batch["rich_leaf_artifacts"][0]
    assert artifact["candidate_status"] == "candidate"
    assert artifact["source_refs"][0]["source_registry_id"] == "canonical_unified_knowledge"
    assert artifact["teaching_cards"][0]["claim_status"] == "candidate_only"
    assert artifact["rubric_link_index"] == []
    assert validate_rich_leaf_artifact(artifact).ok is True
    weak = batch["rich_leaf_artifacts"][1]
    assert weak["missing_source_lanes"] == ["textbook", "standard", "lecture", "question"]
    assert validate_rich_leaf_artifact(weak).ok is True


def test_skeleton_compiler_does_not_count_empty_span_sources_as_valid() -> None:
    from scripts.run_luban_rich_leaf_skeleton_compiler import build_rich_leaf_skeleton_batch

    unified = _unified_bundle()
    unified["nodes"]["L1"]["sources"]["textbook"][0].pop("text_preview")

    batch = build_rich_leaf_skeleton_batch(
        sample_manifest=_sample_manifest(),
        unified_bundle=unified,
        bundle_version="v_rich_leaf_skeleton_candidate_20260611",
        max_sources_per_lane=2,
    )

    artifact = batch["rich_leaf_artifacts"][0]
    assert artifact["source_refs"] == []
    assert "textbook" in artifact["missing_source_lanes"]
    assert batch["summary"]["with_source_refs_count"] == 0
    assert batch["summary"]["missing_source_refs_count"] == 2
    assert validate_rich_leaf_artifact(artifact).ok is True


def test_skeleton_compiler_filters_empty_sources_before_applying_lane_limit() -> None:
    from scripts.run_luban_rich_leaf_skeleton_compiler import build_rich_leaf_skeleton_batch

    unified = _unified_bundle()
    unified["nodes"]["L1"]["sources"]["textbook"] = [
        {"unit_id": "TB_empty_1", "method": "empty"},
        {"unit_id": "TB_empty_2", "text_preview": "", "method": "empty"},
        {"unit_id": "TB_valid", "text_preview": "有效教材原文段落。", "method": "anchor"},
    ]

    batch = build_rich_leaf_skeleton_batch(
        sample_manifest=_sample_manifest(),
        unified_bundle=unified,
        bundle_version="v_rich_leaf_skeleton_candidate_20260611",
        max_sources_per_lane=1,
    )

    artifact = batch["rich_leaf_artifacts"][0]
    assert len(artifact["source_refs"]) == 1
    assert artifact["source_refs"][0]["record_id"] == "TB_valid"
    assert "textbook" not in artifact["missing_source_lanes"]
    assert validate_rich_leaf_artifact(artifact).ok is True


def test_skeleton_safety_flags_are_side_effect_flags_only() -> None:
    from scripts.run_luban_rich_leaf_skeleton_compiler import build_rich_leaf_skeleton_batch

    batch = build_rich_leaf_skeleton_batch(
        sample_manifest=_sample_manifest(),
        unified_bundle=_unified_bundle(),
        bundle_version="v_rich_leaf_skeleton_candidate_20260611",
        max_sources_per_lane=2,
    )

    assert batch["classification"]["candidate_only"] is True
    assert all(value in (False, 0) for value in batch["safety"].values())


def test_cli_writes_rich_leaf_skeleton_batch(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_skeleton_compiler import main

    sample_path = tmp_path / "sample_manifest.json"
    unified_path = tmp_path / "unified.json"
    output_dir = tmp_path / "out"
    _write_json(sample_path, _sample_manifest())
    _write_json(unified_path, _unified_bundle())

    exit_code = main(
        [
            "--sample-manifest",
            str(sample_path),
            "--unified-bundle",
            str(unified_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    batch = json.loads((output_dir / "rich_leaf_skeleton_candidates.json").read_text("utf-8"))
    report = json.loads((output_dir / "skeleton_report.json").read_text("utf-8"))
    assert len(batch["rich_leaf_artifacts"]) == 2
    assert report["summary"]["artifact_count"] == 2
    assert report["safety"]["installed_runtime_supply"] is False
