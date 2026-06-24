from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_pdf_source_ledger.py"
PDF_ROOT = REPO_ROOT / "docs" / "原始数据" / "PDF"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_pdf_source_ledger", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _collect_bytes(path: Path):
    return {
        child.relative_to(path).as_posix(): child.read_bytes()
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def test_pdf_source_ledger_profiles_all_pdfs_with_derivative_status(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "pdf_source_ledger_v1"

    result = builder.build_pdf_source_ledger(
        pdf_root=PDF_ROOT,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_pdf_source_ledger_manifest.v1"
    assert manifest["authority_status"] == "raw_pdf_evidence_ledger"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["pdf_sources"] == 95
    assert (
        manifest["counts"]["candidate_structured_derivative_refs_available"]
        + manifest["counts"]["needs_compilation_or_mapping"]
        == 95
    )
    assert manifest["counts"]["by_category"]["standard_pdf"] == 21
    assert manifest["counts"]["by_category"]["textbook_pdf"] == 11
    assert manifest["counts"]["by_category"]["formula_pdf"] == 2

    records = _read_jsonl(output_root / "pdf_sources.jsonl")
    assert len(records) == 95
    assert all(len(record["file"]["sha256"]) == 64 for record in records)
    assert all(record["authority_status"] == "raw_pdf_evidence" for record in records)
    assert all(record["runtime_guard"]["canonical_write_allowed"] is False for record in records)

    gb50352 = next(record for record in records if "GB50352-2019" in record["source_path"])
    assert gb50352["compilation_status"] == "candidate_structured_derivative_refs_available"
    assert gb50352["candidate_structured_derivative_refs"]

    gb50016 = next(record for record in records if "GB50016-2014" in record["source_path"])
    assert gb50016["compilation_status"] == "raw_indexed_needs_standard_json_backfill"

    hq2022 = next(record for record in records if "2022环球网校" in record["source_path"])
    assert [ref["match"] for ref in hq2022["candidate_structured_derivative_refs"]] == ["2022"]

    textbook_6_8 = next(record for record in records if "2026一建《建筑》电子版教材_6-8.pdf" in record["source_path"])
    assert textbook_6_8["category"] == "textbook_pdf"
    assert textbook_6_8["compilation_status"] == "raw_indexed_needs_textbook_chunking_or_mapping"
    assert textbook_6_8["candidate_structured_derivative_refs"] == []

    textbook_compare = next(record for record in records if "教材对比明细" in record["source_path"])
    assert textbook_compare["category"] == "supplement_pdf"
    assert textbook_compare["candidate_structured_derivative_refs"] == []

    lecture_formula = next(record for record in records if "讲义/《建筑工程管理与实务》公式汇总_副本.pdf" in record["source_path"])
    assert lecture_formula["category"] == "formula_pdf"

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "PDF Source Ledger v1" in summary
    assert "Candidate structured derivative refs" in summary
    assert "not official score authority" in summary


def test_pdf_source_ledger_rejects_dangerous_output_root_before_reset(monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_pdf_source_ledger(
            pdf_root=PDF_ROOT,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_pdf_source_ledger_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "pdf_source_ledger_v1"
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_pdf_source_ledger(
            pdf_root=PDF_ROOT,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_pdf_source_ledger_rejects_invalid_generated_sentinel_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "pdf_source_ledger_v1"
    output_root.mkdir(parents=True)
    (output_root / ".pdf_source_ledger_generated.json").write_text(
        json.dumps({"generated_by": "someone_else", "kind": "pdf_source_ledger"}),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid sentinel: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid generated sentinel"):
        builder.build_pdf_source_ledger(
            pdf_root=PDF_ROOT,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_pdf_source_ledger_rejects_valid_sentinel_with_extra_file_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "pdf_source_ledger_v1"
    output_root.mkdir(parents=True)
    builder.write_sentinel(output_root, generated_at="2026-06-19T00:00:00+08:00")
    extra = output_root / "human_note.md"
    extra.write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for mixed generated tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe generated output tree"):
        builder.build_pdf_source_ledger(
            pdf_root=PDF_ROOT,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )
    assert extra.read_text(encoding="utf-8") == "do not delete\n"


def test_pdf_source_ledger_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "pdf_source_ledger_v1"
    kwargs = {
        "pdf_root": PDF_ROOT,
        "output_root": output_root,
        "generated_at": "2026-06-19T00:00:00+08:00",
    }
    builder.build_pdf_source_ledger(**kwargs)
    first = _collect_bytes(output_root)
    builder.build_pdf_source_ledger(**kwargs)
    second = _collect_bytes(output_root)

    assert second == first
