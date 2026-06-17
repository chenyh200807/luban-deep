from __future__ import annotations

import json
from pathlib import Path


def test_source_corpus_inventory_records_files_without_runtime_authority(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_corpus_inventory import run_source_corpus_inventory

    source_root = tmp_path / "docs2026"
    (source_root / "题库").mkdir(parents=True)
    (source_root / "教材").mkdir(parents=True)
    (source_root / "规范").mkdir(parents=True)
    (source_root / "题库" / "近三年案例题_按学生答卷排版.md").write_text("考生答卷", encoding="utf-8")
    (source_root / "教材" / "施工技术.md").write_text("教材原文", encoding="utf-8")
    (source_root / "规范" / "质量验收.txt").write_text("规范条文", encoding="utf-8")
    (source_root / "ignore.bin").write_bytes(b"\x00\x01")

    report = run_source_corpus_inventory(source_root=source_root)

    assert report["schema"] == "luban_rich_leaf_source_corpus_inventory.v1"
    assert report["verdict"] == "PASS_SOURCE_CORPUS_INVENTORY"
    assert report["summary"]["total_file_count"] == 4
    assert report["summary"]["included_file_count"] == 3
    assert report["summary"]["unsupported_file_count"] == 1
    assert report["summary"]["production_write_count"] == 0
    assert report["by_lane"]["assessment_evidence"]["file_count"] == 1
    assert report["by_lane"]["source_truth"]["file_count"] == 2
    assert len(report["files"]) == 3
    assert all(item["sha256"] for item in report["files"])
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_source_corpus_inventory_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_corpus_inventory import main

    source_root = tmp_path / "docs2026"
    output = tmp_path / "source_corpus_inventory.json"
    source_root.mkdir()
    (source_root / "讲义.md").write_text("讲义", encoding="utf-8")

    exit_code = main(["--source-root", str(source_root), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["included_file_count"] == 1
    assert payload["by_lane"]["teaching_evidence"]["file_count"] == 1
