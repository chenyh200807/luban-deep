from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_candidate_scope.py"
CANONICAL_RUBRIC = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "case_rubric_canonical.json"
ALIGNMENT_ROOT = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_source_alignment_v0"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_candidate_scope", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_candidate_scope_expands_all_aligned_canonical_rubrics(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "okf_candidate_scope_v0"

    result = builder.build_candidate_scope(
        canonical_rubric_path=CANONICAL_RUBRIC,
        source_alignment_root=ALIGNMENT_ROOT,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_okf_candidate_scope_manifest.v0"
    assert manifest["status"] == "source_layer_candidate_complete"
    assert manifest["counts"] == {"cases": 25, "rubrics": 117, "scoring_points": 431}
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False

    cases = _read_jsonl(output_root / "cases.jsonl")
    rubrics = _read_jsonl(output_root / "rubrics.jsonl")
    points = _read_jsonl(output_root / "scoring_points.jsonl")
    assert len(cases) == 25
    assert len(rubrics) == 117
    assert len(points) == 431
    assert all(case["source_alignment_status"] == "case_chunk_found" for case in cases)
    assert all(point["runtime_guard"]["canonical_write_allowed"] is False for point in points)
    assert any(point["point_id"] == "sp_2021_1_q01_01" for point in points)

    point_index = _read_json(output_root / "scoring_point_index.json")
    assert len(point_index["points_by_id"]) == 431
    assert point_index["points_by_id"]["sp_2021_1_q01_01"]["case_id"] == "case_2021_1"


def test_candidate_scope_rejects_unready_source_alignment(tmp_path):
    builder = _load_builder()
    alignment_root = tmp_path / "okf_source_alignment_v0"
    shutil.copytree(ALIGNMENT_ROOT, alignment_root)
    report_path = alignment_root / "report.json"
    report = _read_json(report_path)
    report["status"] = "case_source_alignment_gap_open"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="source alignment must be ready"):
        builder.build_candidate_scope(
            canonical_rubric_path=CANONICAL_RUBRIC,
            source_alignment_root=alignment_root,
            output_root=tmp_path / "extractions" / "okf_candidate_scope_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_candidate_scope_rejects_dangerous_output_root(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_candidate_scope(
            canonical_rubric_path=CANONICAL_RUBRIC,
            source_alignment_root=ALIGNMENT_ROOT,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )
