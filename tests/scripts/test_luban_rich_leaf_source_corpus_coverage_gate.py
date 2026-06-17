from __future__ import annotations

import json
from pathlib import Path


def _inventory() -> dict:
    return {
        "schema": "luban_rich_leaf_source_corpus_inventory.v1",
        "source_root": "/tmp/docs2026",
        "verdict": "PASS_SOURCE_CORPUS_INVENTORY",
        "summary": {
            "included_file_count": 3,
            "production_write_count": 0,
        },
        "files": [
            {
                "relative_path": "2026教材/a.md",
                "source_lane": "source_truth",
                "sha256": "a" * 64,
                "byte_count": 10,
            },
            {
                "relative_path": "讲义/b.md",
                "source_lane": "teaching_evidence",
                "sha256": "b" * 64,
                "byte_count": 20,
            },
            {
                "relative_path": "题库/c.md",
                "source_lane": "assessment_evidence",
                "sha256": "c" * 64,
                "byte_count": 30,
            },
        ],
        "classification": {
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
    }


def _candidate_bundle() -> dict:
    return {
        "schema": "candidate_bundle.v1",
        "summary": {"candidate_count": 2},
        "items": [
            {
                "source_refs": [
                    {"source_path": "2026教材/a.md", "span": "教材"},
                    {"path": "nodes.leaf.sources.textbook[0]", "span": "internal"},
                ]
            },
            {
                "field_patch": {
                    "source_ref": {
                        "source_path": "/tmp/docs2026/题库/c.md",
                        "span": "题库",
                    }
                }
            },
        ],
        "classification": {
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
    }


def test_source_corpus_coverage_gate_finds_missing_files_without_promotion() -> None:
    from scripts.run_luban_rich_leaf_source_corpus_coverage_gate import (
        run_source_corpus_coverage_gate,
    )

    report = run_source_corpus_coverage_gate(source_corpus_inventory=_inventory(), candidate_bundles=[_candidate_bundle()])

    assert report["schema"] == "luban_rich_leaf_source_corpus_coverage_gate.v1"
    assert report["verdict"] == "GAP_WORK_ORDERS_READY"
    assert report["summary"]["included_file_count"] == 3
    assert report["summary"]["covered_file_count"] == 2
    assert report["summary"]["missing_file_count"] == 1
    assert report["summary"]["coverage_rate"] == 0.666667
    assert report["by_lane"]["teaching_evidence"]["missing_file_count"] == 1
    assert report["coverage_records"]["2026教材/a.md"]["covered"] is True
    assert report["coverage_records"]["题库/c.md"]["covered"] is True
    assert report["coverage_records"]["讲义/b.md"]["covered"] is False
    assert report["gap_work_orders"][0]["relative_path"] == "讲义/b.md"
    assert report["gap_work_orders"][0]["runtime_install_allowed"] is False
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_source_corpus_coverage_gate_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_corpus_coverage_gate import main

    inventory = tmp_path / "inventory.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "coverage.json"
    inventory.write_text(json.dumps(_inventory(), ensure_ascii=False), encoding="utf-8")
    candidate.write_text(json.dumps(_candidate_bundle(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--inventory", str(inventory), "--candidate-bundle", str(candidate), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["covered_file_count"] == 2
    assert payload["summary"]["missing_file_count"] == 1
