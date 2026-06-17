from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _source_gap_report() -> dict:
    return {
        "schema": "luban_rich_leaf_source_gap_candidates.v1",
        "source_gap_candidates": [
            {
                "leaf_id": "L1",
                "artifact_id": "A1",
                "name_path": "工程价款支付与结算 > 工程预付款与起扣点",
                "missing_lane": "textbook",
                "status": "weak_candidate_sources_found",
                "top_score": 1.4,
                "strong_candidate_threshold": 2.0,
                "terms": ["工程预付款", "起扣点"],
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "canonical_unified_knowledge:nodes.X.sources.textbook[0]",
                        "record_id": "TB1",
                        "matched_terms": ["工程预付款"],
                        "score": 1.4,
                        "snippet": "工程预付款支付比例。",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
            {
                "leaf_id": "L1",
                "artifact_id": "A1",
                "name_path": "工程价款支付与结算 > 工程预付款与起扣点",
                "missing_lane": "standard",
                "status": "no_candidate_sources_found",
                "top_score": 0.0,
                "strong_candidate_threshold": 2.0,
                "terms": ["工程预付款", "起扣点"],
                "candidates": [],
            },
            {
                "leaf_id": "L2",
                "artifact_id": "A2",
                "name_path": "建筑防水材料",
                "missing_lane": "textbook",
                "status": "strong_candidate_sources_found",
                "top_score": 3.0,
                "strong_candidate_threshold": 2.0,
                "terms": ["SBS", "APP"],
                "candidates": [{"score": 3.0}],
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_build_weak_source_refinement_orders_groups_only_leaves_without_strong() -> None:
    from scripts.run_luban_rich_leaf_weak_source_refinement import build_weak_source_refinement_report

    report = build_weak_source_refinement_report(source_gap_report=_source_gap_report())

    assert report["schema"] == "luban_rich_leaf_weak_source_refinement.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "work_orders_apply_allowed": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {
        "leaf_work_order_count": 1,
        "lane_work_order_count": 2,
        "weak_lane_count": 1,
        "no_candidate_lane_count": 1,
        "leaves_with_existing_strong_skipped": 1,
    }
    assert all(value in (False, 0) for value in report["safety"].values())

    order = report["leaf_work_orders"][0]
    assert order["leaf_id"] == "L1"
    assert order["status"] == "source_authority_gap"
    assert order["promotion_allowed"] is False
    assert order["lane_work_orders"][0]["reason_codes"] == ["below_strong_threshold", "low_term_overlap"]
    assert order["lane_work_orders"][0]["next_action"] == "find_better_authority_source_for_lane"
    assert order["lane_work_orders"][1]["reason_codes"] == ["no_candidate_source"]
    assert order["lane_work_orders"][1]["next_action"] == "expand_authority_corpus_for_lane"
    assert order["lane_work_orders"][0]["candidate_snapshot"][0]["install_allowed"] is False


def test_cli_writes_weak_source_refinement_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_weak_source_refinement import main

    source_gap_path = tmp_path / "source_gap_candidates.json"
    output_dir = tmp_path / "out"
    _write_json(source_gap_path, _source_gap_report())

    exit_code = main(["--source-gap-candidates", str(source_gap_path), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "weak_source_refinement_work_orders.json").read_text("utf-8"))
    assert report["summary"]["leaf_work_order_count"] == 1
    assert report["leaf_work_orders"][0]["leaf_id"] == "L1"
