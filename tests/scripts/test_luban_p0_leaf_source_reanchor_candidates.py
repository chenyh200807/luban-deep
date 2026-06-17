from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_reanchor_candidates_finds_p0_source_evidence() -> None:
    from scripts.run_luban_p0_leaf_source_reanchor_candidates import SourceRecord, build_reanchor_candidates

    work_order_report = {
        "schema": "luban_unified_knowledge_leaf_coverage_work_orders.v1",
        "source_bundle_content_hash": "hash-1",
        "work_orders": [
            {
                "work_order_id": "P0:question_without_knowledge:L1",
                "priority": "P0",
                "gap_type": "question_without_knowledge",
                "leaf_id": "L1",
                "leaf_path": "建筑工程技术 > 建筑设计 > 建筑设计程序",
                "keywords": ["方案设计", "初步设计", "施工图设计"],
            },
            {
                "work_order_id": "P1:knowledge_without_question:L2",
                "priority": "P1",
                "gap_type": "knowledge_without_question",
                "leaf_id": "L2",
                "leaf_path": "无关",
                "keywords": ["无关"],
            },
        ],
    }
    source_records = [
        SourceRecord(
            source_lane="textbook",
            source_path="2026教材/第二次加强/book.json",
            record_id="BOOK_1",
            text="建筑设计程序通常包括方案设计、初步设计、施工图设计三个阶段。",
            provenance={"source_meta": {"page": 1}},
        )
    ]

    report = build_reanchor_candidates(work_order_report=work_order_report, source_records=source_records)

    assert report["schema"] == "luban_p0_leaf_source_reanchor_candidates.v1"
    assert report["summary"]["p0_work_orders_input"] == 1
    assert report["summary"]["leaves_with_candidates"] == 1
    assert report["summary"]["leaves_with_strong_candidates"] == 1
    assert report["safety"]["canonical_truth_written"] is False
    row = report["reanchor_candidates"][0]
    assert row["leaf_id"] == "L1"
    assert row["status"] == "strong_candidate_sources_found"
    assert row["candidates"][0]["candidate_only"] is True
    assert "方案设计" in row["candidates"][0]["matched_terms"]


def test_cli_writes_candidate_only_report(tmp_path: Path) -> None:
    from scripts.run_luban_p0_leaf_source_reanchor_candidates import main

    source_root = tmp_path / "docs2026"
    work_orders = tmp_path / "work_orders.json"
    output_dir = tmp_path / "out"
    _write_json(
        source_root / "讲义" / "demo" / "page_1.json",
        [
            {
                "chunk_id": "LEC_1",
                "content_markdown": "### 氧元素对钢材性能的影响\n氧含量增加会降低钢材塑性和韧性。",
                "source_meta": {"source": "demo lecture"},
            }
        ],
    )
    _write_json(
        work_orders,
        {
            "schema": "luban_unified_knowledge_leaf_coverage_work_orders.v1",
            "source_bundle_content_hash": "hash-2",
            "work_orders": [
                {
                    "work_order_id": "P0:question_without_knowledge:1A412011-01-f",
                    "priority": "P0",
                    "gap_type": "question_without_knowledge",
                    "leaf_id": "1A412011-01-f",
                    "leaf_path": "结构工程材料 > 钢材化学成分对性能的影响 > 氧元素对钢材性能的影响",
                    "keywords": ["氧元素", "钢材性能"],
                }
            ],
        },
    )

    exit_code = main(
        [
            "--source-root",
            str(source_root),
            "--work-orders",
            str(work_orders),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "reanchor_candidates.json").read_text("utf-8"))
    assert report["summary"]["candidate_total"] == 1
    assert report["summary"]["leaves_with_weak_candidates_only"] == 0
    assert report["safety"]["official_score_allowed"] is False
    assert report["reanchor_candidates"][0]["candidates"][0]["source_lane"] == "lecture"
