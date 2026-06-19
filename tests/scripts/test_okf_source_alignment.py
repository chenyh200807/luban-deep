from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_source_alignment.py"
CANONICAL_RUBRIC = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "case_rubric_canonical.json"
JSON_LEDGER_SOURCES = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "json_source_ledger_v0" / "sources.jsonl"
)
EXAM_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "题库"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_source_alignment", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_source_alignment_maps_all_canonical_cases_to_cleaned_exam_json(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "okf_source_alignment_v0"

    result = builder.build_source_alignment(
        canonical_rubric_path=CANONICAL_RUBRIC,
        json_ledger_sources_path=JSON_LEDGER_SOURCES,
        exam_root=EXAM_ROOT,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    report = result["report"]
    assert report["schema"] == "luban_okf_source_alignment_report.v0"
    assert report["status"] == "case_source_alignment_ready"
    assert report["counts"]["target_cases"] == 25
    assert report["counts"]["aligned_cases"] == 25
    assert report["runtime_guard"]["runtime_consumable"] is False
    assert report["next_action"]["id"] == "expand_okf_candidate_scope"
    assert report["next_action"]["status"] == "ready_for_source_layer_expansion"

    records = _read_jsonl(output_root / "case_alignment.jsonl")
    assert len(records) == 25
    assert all(record["source_in_ledger"] is True for record in records)
    assert all(record["alignment_status"] == "case_chunk_found" for record in records)

    first = next(record for record in records if record["year"] == "2021" and record["case_no"] == "1")
    assert first["case_id"] == "case_2021_1"
    assert first["question_chunk"]["chunk_id"] == "EXAM_1A431000_P0016_02"
    assert first["question_chunk"]["page"] == 16
    assert first["subquestion_alignment"]["status"] == "ordinal_match"

    written = _read_json(output_root / "report.json")
    assert written == report


def test_source_alignment_rejects_missing_exam_source_in_ledger(tmp_path):
    builder = _load_builder()
    missing_sources = tmp_path / "sources.jsonl"
    missing_sources.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="missing exam source ledger record"):
        builder.build_source_alignment(
            canonical_rubric_path=CANONICAL_RUBRIC,
            json_ledger_sources_path=missing_sources,
            exam_root=EXAM_ROOT,
            output_root=tmp_path / "extractions" / "okf_source_alignment_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_source_alignment_rejects_dangerous_output_root(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_source_alignment(
            canonical_rubric_path=CANONICAL_RUBRIC,
            json_ledger_sources_path=JSON_LEDGER_SOURCES,
            exam_root=EXAM_ROOT,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )
