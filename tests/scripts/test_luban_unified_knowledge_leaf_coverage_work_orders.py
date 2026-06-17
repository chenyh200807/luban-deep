from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_leaf_coverage_work_orders_prioritizes_question_without_knowledge(tmp_path: Path) -> None:
    from scripts.run_luban_unified_knowledge_leaf_coverage_work_orders import build_work_orders

    taxonomy_index = {
        "manifest": {"content_hash": "tax-hash"},
        "leaves": [
            {"code": "L1", "name_path": "章 > 有题无知识", "keywords": ["题"]},
            {"code": "L2", "name_path": "章 > 有知识无题", "keywords": ["知"]},
            {"code": "L3", "name_path": "章 > 已完整", "keywords": ["全"]},
            {"code": "L4", "name_path": "章 > 有题缺源", "keywords": ["缺"]},
        ],
    }
    unified_bundle = {
        "manifest": {
            "schema": "luban_canonical_unified_knowledge.v1",
            "namespace": "canonical_unified_knowledge",
            "status": "release_candidate",
            "tier": "teaching_context_not_answer_key",
            "official_score_allowed": False,
            "content_hash": "unified-hash",
            "coverage": {
                "canonical_leaves_total": 3,
                "leaves_populated": 2,
                "leaves_question_no_knowledge": ["L1"],
                "leaves_knowledge_no_question": 1,
            },
        },
        "nodes": {
            "L2": {"counts": {"textbook": 1, "standard": 0, "lecture": 0, "question": 0}},
            "L3": {"counts": {"textbook": 1, "standard": 1, "lecture": 1, "question": 1}},
            "L4": {"counts": {"textbook": 0, "standard": 0, "lecture": 1, "question": 2}},
        },
    }

    report = build_work_orders(
        taxonomy_index=taxonomy_index,
        unified_bundle=unified_bundle,
        max_question_no_knowledge=10,
        max_knowledge_no_question=10,
        max_missing_source=10,
    )

    assert report["schema"] == "luban_unified_knowledge_leaf_coverage_work_orders.v1"
    assert report["safety"]["official_score_allowed"] is False
    assert report["summary"]["question_no_knowledge_count"] == 1
    assert report["summary"]["knowledge_no_question_count"] == 1
    assert report["summary"]["missing_source_work_order_count"] == 1

    first = report["work_orders"][0]
    assert first["category"] == "question_without_knowledge"
    assert first["node_code"] == "L1"
    assert first["priority"] == "P0"
    assert first["recommended_action"] == "compile_or_reanchor_source_context_for_question_leaf"


def test_cli_writes_leaf_coverage_work_order_report(tmp_path: Path) -> None:
    from scripts.run_luban_unified_knowledge_leaf_coverage_work_orders import main

    taxonomy_path = tmp_path / "taxonomy.json"
    unified_path = tmp_path / "unified.json"
    output_dir = tmp_path / "out"
    _write_json(taxonomy_path, {"manifest": {"content_hash": "tax"}, "leaves": [{"code": "L1", "name_path": "A"}]})
    _write_json(
        unified_path,
        {
            "manifest": {
                "content_hash": "unified",
                "official_score_allowed": False,
                "coverage": {"canonical_leaves_total": 1, "leaves_populated": 0, "leaves_question_no_knowledge": ["L1"]},
            },
            "nodes": {},
        },
    )

    exit_code = main(
        [
            "--taxonomy-index",
            str(taxonomy_path),
            "--unified-bundle",
            str(unified_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "leaf_coverage_work_orders.json").read_text("utf-8"))
    assert report["work_orders"][0]["node_code"] == "L1"
