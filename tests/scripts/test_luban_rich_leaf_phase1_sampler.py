from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _taxonomy() -> dict:
    return {
        "manifest": {"content_hash": "tax-hash"},
        "leaves": [
            {"code": "L_textbook", "name_path": "A > textbook", "keywords": ["textbook"]},
            {"code": "L_standard", "name_path": "A > standard", "keywords": ["standard"]},
            {"code": "L_lecture", "name_path": "A > lecture", "keywords": ["lecture"]},
            {"code": "L_question", "name_path": "A > question", "keywords": ["question"]},
            {"code": "L_weak", "name_path": "A > weak", "keywords": ["weak"]},
            {"code": "L_overlap", "name_path": "A > overlap", "keywords": ["overlap"]},
        ],
    }


def _unified() -> dict:
    return {
        "manifest": {
            "content_hash": "unified-hash",
            "coverage": {"leaves_question_no_knowledge": ["L_weak"]},
        },
        "nodes": {
            "L_textbook": {"counts": {"textbook": 3, "standard": 0, "lecture": 0, "question": 0}},
            "L_standard": {"counts": {"textbook": 0, "standard": 2, "lecture": 0, "question": 0}},
            "L_lecture": {"counts": {"textbook": 0, "standard": 0, "lecture": 4, "question": 0}},
            "L_question": {"counts": {"textbook": 0, "standard": 0, "lecture": 0, "question": 5}},
            "L_weak": {"counts": {"textbook": 0, "standard": 0, "lecture": 0, "question": 2}},
            "L_overlap": {"counts": {"textbook": 2, "standard": 3, "lecture": 0, "question": 7}},
        },
    }


def _repairs() -> dict:
    return {
        "manifest": {"content_hash": "repairs-hash"},
        "negative_hits": [
            {"leaf_id": "L_weak", "reason": "source_pollution"},
            {"leaf_id": "L_overlap", "reason": "wrong_path"},
        ],
    }


def test_build_sample_manifest_is_deterministic_and_dedupes_to_highest_risk_bucket() -> None:
    from scripts.run_luban_rich_leaf_phase1_sampler import build_sample_manifest

    a = build_sample_manifest(
        taxonomy_index=_taxonomy(),
        unified_bundle=_unified(),
        source_alignment_repairs=_repairs(),
        seed="rich_leaf_phase1_20260611",
        per_bucket=2,
        candidate_pool_size=10,
    )
    b = build_sample_manifest(
        taxonomy_index=_taxonomy(),
        unified_bundle=_unified(),
        source_alignment_repairs=_repairs(),
        seed="rich_leaf_phase1_20260611",
        per_bucket=2,
        candidate_pool_size=10,
    )

    assert a == b
    assert a["schema"] == "luban_rich_leaf_phase1_sample_manifest.v1"
    assert a["input_hashes"] == {
        "canonical_taxonomy_index": "tax-hash",
        "canonical_unified_knowledge": "unified-hash",
        "source_alignment_repairs": "repairs-hash",
    }
    selected = a["selected_leaves"]
    assert {row["leaf_id"] for row in selected} == {
        "L_textbook",
        "L_standard",
        "L_lecture",
        "L_question",
        "L_weak",
        "L_overlap",
    }
    overlap = [row for row in selected if row["leaf_id"] == "L_overlap"][0]
    assert overlap["bucket"] == "weak/polluted/sparse"
    assert a["summary"]["selected_count"] == len(selected)
    assert a["classification"]["candidate_only"] is True
    assert a["safety"]["canonical_truth_written"] is False
    assert a["safety"]["official_score_allowed"] is False
    assert all(value in (False, 0) for value in a["safety"].values())


def test_cli_writes_sample_manifest(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_phase1_sampler import main

    taxonomy_path = tmp_path / "taxonomy.json"
    unified_path = tmp_path / "unified.json"
    repairs_path = tmp_path / "repairs.json"
    output_dir = tmp_path / "out"
    _write_json(taxonomy_path, _taxonomy())
    _write_json(unified_path, _unified())
    _write_json(repairs_path, _repairs())

    exit_code = main(
        [
            "--taxonomy-index",
            str(taxonomy_path),
            "--unified-bundle",
            str(unified_path),
            "--source-alignment-repairs",
            str(repairs_path),
            "--output-dir",
            str(output_dir),
            "--per-bucket",
            "1",
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "sample_manifest.json").read_text("utf-8"))
    assert manifest["seed"] == "rich_leaf_phase1_20260611"
    assert manifest["summary"]["bucket_count"] == 5
    assert manifest["classification"]["candidate_only"] is True
    assert manifest["safety"]["installed_runtime_supply"] is False
    assert all(value in (False, 0) for value in manifest["safety"].values())
