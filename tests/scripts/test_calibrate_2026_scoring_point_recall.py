from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_calibrate_scoring_point_recall_script_writes_outputs(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    assets_by_node = {
        "1A436000": [
            {
                "point_id": "sp1",
                "node_code": "1A436000",
                "chunk_id": "c1",
                "point_type": "text_term",
                "anchor_source": "textbook",
                "required_terms": ["操作平台"],
                "provenance": {"quote": "操作平台"},
            }
        ]
    }
    (asset_dir / "scoring_point_assets_by_node.json").write_text(json.dumps(assets_by_node, ensure_ascii=False), encoding="utf-8")
    (asset_dir / "quality_report.json").write_text(
        json.dumps({"seed_total": 1, "seed_hit": 1, "seed_miss": 0}, ensure_ascii=False),
        encoding="utf-8",
    )

    golden = {
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A436000",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出'操作平台'",
                        "official_basis": "应设置操作平台。",
                        "point_type": "text_term",
                    },
                    {
                        "point_id": "P2",
                        "label": "必须写出'连续的安全绳'",
                        "official_basis": "应设置连续的安全绳。",
                        "point_type": "text_term",
                    }
                ],
            }
        ]
    }
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(golden, ensure_ascii=False), encoding="utf-8")
    source_root = tmp_path / "2026"
    book_dir = source_root / "2026教材" / "第二次加强"
    book_dir.mkdir(parents=True)
    (book_dir / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "c1",
                        "content_markdown": "水平通道两侧应设置防护栏杆；当利用钢梁作为水平通道时，应在钢梁一侧设置连续的安全绳。",
                        "taxonomy": {"node_code": "1A436000", "parent_code": "1A430000"},
                        "source_meta": {"page_num": 8},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/calibrate_2026_scoring_point_recall.py",
            "--asset-dir",
            str(asset_dir),
            "--golden",
            str(golden_path),
            "--source-root",
            str(source_root),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "term_recall=0.5000" in result.stdout
    assert (output_dir / "term_coverage_rows.jsonl").exists()
    assert (output_dir / "miss_classification.json").exists()
    assert (output_dir / "scoring_point_assets_backfill.jsonl").exists()
    assert (output_dir / "backfill_verify_audit.json").exists()
    assert (output_dir / "with_backfill_summary.json").exists()
    assert (output_dir / "with_backfill_expanded_scope_summary.json").exists()
    assert (output_dir / "recall_oriented_backfill_candidates.json").exists()
    assert (output_dir / "truth_metric_comparison.md").exists()
    assert (output_dir / "expanded_scope_summary.json").exists()
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))["term_recall"] == 0.5
    assert json.loads((output_dir / "with_backfill_summary.json").read_text(encoding="utf-8"))["term_recall"] == 1.0
    assert json.loads((output_dir / "backfill_verify_audit.json").read_text(encoding="utf-8"))["bare_gold_term_only_count"] == 0
