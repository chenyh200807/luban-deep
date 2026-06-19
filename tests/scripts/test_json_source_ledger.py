from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_json_source_ledger.py"
SOURCE_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_json_source_ledger", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_ledger_profiles_cleaned_json_sources(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "json_source_ledger_v0"

    result = builder.build_ledger(
        source_root=SOURCE_ROOT,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["authority_status"] == "raw_evidence_ledger"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["json_sources"] >= 300
    assert manifest["counts"]["buckets"]["exam_cleaned_json"] == 11
    assert manifest["counts"]["buckets"]["standard_cleaned_json"] == 8
    assert manifest["counts"]["buckets"]["lecture_cleaned_json"] >= 300

    sources_path = output_root / "sources.jsonl"
    records = [json.loads(line) for line in sources_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == manifest["counts"]["json_sources"]
    assert all(record["authority_status"] == "raw_evidence_ledger" for record in records)
    assert all(record["source_claim_reviewed"] is False for record in records)
    assert all(record["runtime_guard"]["canonical_write_allowed"] is False for record in records)
    assert any(
        record["source_path"].endswith("FINAL_CLEANED_EXAM_V2021.json")
        and record["bucket"] == "exam_cleaned_json"
        for record in records
    )

    summary = _read_json(output_root / "summary.json")
    assert summary["json_sources"] == manifest["counts"]["json_sources"]
    assert summary["runtime_guard"]["learner_truth_write_allowed"] is False


def test_build_ledger_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_ledger(
            source_root=SOURCE_ROOT,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_build_ledger_rejects_source_output_overlap(tmp_path):
    builder = _load_builder()

    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "sample.json").write_text('{"ok": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="overlap source root"):
        builder.build_ledger(
            source_root=source_root,
            output_root=source_root / "extractions" / "json_source_ledger_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_build_ledger_rejects_unowned_generated_shaped_tree_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "json_source_ledger_v0"
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_ledger(
            source_root=SOURCE_ROOT,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_classify_source_path_keeps_authority_roles_separate():
    builder = _load_builder()

    exam_path = SOURCE_ROOT / "题库" / "2021年一级建造师《建筑实务》考试真题及答案解析" / "FINAL_CLEANED_EXAM_V2021.json"
    standard_path = SOURCE_ROOT / "标准文件" / "1、GB50352-2019民用建筑设计统一标准.json"
    textbook_path = SOURCE_ROOT / "2026教材" / "第二次加强" / "v3_production_core9-166.json"

    assert builder.classify_source(SOURCE_ROOT, exam_path) == "exam_cleaned_json"
    assert builder.classify_source(SOURCE_ROOT, standard_path) == "standard_cleaned_json"
    assert builder.classify_source(SOURCE_ROOT, textbook_path) == "textbook_core_json"
