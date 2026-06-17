from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_candidate_patch_splits_strong_and_weak() -> None:
    from scripts.run_luban_p0_reanchor_candidate_patch import build_candidate_patch_report

    candidates_report = {
        "schema": "luban_p0_leaf_source_reanchor_candidates.v1",
        "source_bundle_content_hash": "bundle-hash",
        "reanchor_candidates": [
            {
                "work_order_id": "P0:question_without_knowledge:L1",
                "leaf_id": "L1",
                "leaf_path": "章 > 建筑设计程序",
                "status": "strong_candidate_sources_found",
                "top_score": 3.0,
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "book.json",
                        "record_id": "B1",
                        "score": 3.0,
                        "matched_terms": ["建筑设计程序", "方案设计"],
                        "snippet": "建筑设计程序包括方案设计、初步设计、施工图设计。",
                        "candidate_only": True,
                    }
                ],
            },
            {
                "work_order_id": "P0:question_without_knowledge:L2",
                "leaf_id": "L2",
                "leaf_path": "章 > 脚手架验收与检查制度",
                "status": "weak_candidate_sources_found",
                "top_score": 1.2,
                "terms": ["主体结构工程施工", "脚手架验收与检查制度"],
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "book.json",
                        "record_id": "B2",
                        "score": 1.2,
                        "matched_terms": ["主体结构工程施工"],
                        "snippet": "主体结构工程施工同步搭设。",
                        "candidate_only": True,
                    }
                ],
            },
        ],
        "safety": {"candidate_only": True},
    }

    report = build_candidate_patch_report(candidates_report=candidates_report)

    assert report["schema"] == "luban_p0_reanchor_candidate_patch.v1"
    assert report["summary"]["candidate_patch_count"] == 1
    assert report["summary"]["weak_pollution_refinement_count"] == 1
    assert report["safety"]["canonical_truth_written"] is False
    patch = report["candidate_patches"][0]
    assert patch["leaf_id"] == "L1"
    assert patch["patch_status"] == "review_required_not_installed"
    assert patch["target"] == "canonical_unified_knowledge.nodes[L1].sources"
    weak = report["weak_pollution_refinements"][0]
    assert weak["leaf_id"] == "L2"
    assert weak["pollution_risk"] == "generic_path_term_only"
    assert "脚手架验收与检查制度" in weak["required_specific_terms"]


def test_cli_writes_patch_report_and_markdown_catalog(tmp_path: Path) -> None:
    from scripts.run_luban_p0_reanchor_candidate_patch import main

    candidates_path = tmp_path / "reanchor_candidates.json"
    output_dir = tmp_path / "out"
    _write_json(
        candidates_path,
        {
            "schema": "luban_p0_leaf_source_reanchor_candidates.v1",
            "source_bundle_content_hash": "bundle-hash",
            "summary": {"leaves_with_strong_candidates": 1, "leaves_with_weak_candidates_only": 0},
            "reanchor_candidates": [
                {
                    "work_order_id": "P0:question_without_knowledge:L1",
                    "leaf_id": "L1",
                    "leaf_path": "章 > 建筑设计程序",
                    "status": "strong_candidate_sources_found",
                    "top_score": 3.0,
                    "terms": ["建筑设计程序", "方案设计"],
                    "candidates": [
                        {
                            "source_lane": "textbook",
                            "source_path": "book.json",
                            "record_id": "B1",
                            "score": 3.0,
                            "matched_terms": ["建筑设计程序", "方案设计"],
                            "snippet": "建筑设计程序包括方案设计、初步设计、施工图设计。",
                            "candidate_only": True,
                        }
                    ],
                }
            ],
            "safety": {"candidate_only": True},
        },
    )

    exit_code = main(["--candidates", str(candidates_path), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "candidate_patch_report.json").read_text("utf-8"))
    assert report["summary"]["candidate_patch_count"] == 1
    assert (output_dir / "COMPILED_DATA_MAP.md").read_text("utf-8").startswith("# Luban Nexus Compiled Data Map")
