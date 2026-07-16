from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_data_asset_brief.py"
EXTRACTIONS_ROOT = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions"
RAW_PROFILE = EXTRACTIONS_ROOT / "raw-data-current-profile.json"
JSON_LEDGER = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "manifest.json"
OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
PDF_LEDGER = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "manifest.json"
COMPILED_LEDGER = EXTRACTIONS_ROOT / "compiled_asset_ledger_v1" / "manifest.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_data_asset_brief", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_bytes(path: Path):
    return {
        child.relative_to(path).as_posix(): child.read_bytes()
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def test_build_data_asset_brief_creates_ai_first_asset_map(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"

    result = builder.build_data_asset_brief(
        raw_profile_path=RAW_PROFILE,
        json_ledger_path=JSON_LEDGER,
        pdf_ledger_path=PDF_LEDGER,
        compiled_ledger_path=COMPILED_LEDGER,
        okf_scope_path=OKF_SCOPE,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    compiled_counts = _read_json(COMPILED_LEDGER)["counts"]
    assert manifest["schema"] == "luban_data_asset_brief_manifest.v1"
    assert manifest["authority_status"] == "asset_inventory_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["totals"]["raw_asset_files"] >= 1000
    assert manifest["totals"]["cleaned_json_sources"] == 383
    assert manifest["totals"]["pdf_files"] == 95
    assert manifest["totals"]["compiled_asset_files"] == compiled_counts["files"]
    assert manifest["totals"]["compiled_manifest_refs_copied"] == compiled_counts["manifest_refs_copied"]
    assert manifest["totals"]["exam_case_questions"] == 218
    assert manifest["totals"]["candidate_scoring_points"] == 431
    pdf_status = manifest["pdf_compilation_status"]
    assert pdf_status["status"] == "partially_structured_not_fully_pdf_compiled"
    assert pdf_status["raw_pdf_files"] == 95
    assert pdf_status["runtime_guard"]["runtime_consumable"] is False
    assert pdf_status["pdf_source_ledger"]["authority_status"] == "raw_pdf_evidence_ledger"
    assert pdf_status["pdf_source_ledger"]["counts"]["pdf_sources"] == 95
    assert pdf_status["pdf_source_ledger"]["counts"]["candidate_structured_derivative_refs_available"] == 39
    assert pdf_status["pdf_source_ledger"]["counts"]["needs_compilation_or_mapping"] == 56
    assert any("full_text/chunk manifest" in item for item in pdf_status["what_is_not_done"])

    asset_buckets = _read_json(output_root / "asset_buckets.json")["asset_buckets"]
    ids = {row["id"] for row in asset_buckets}
    assert {
        "cleaned_json_sources",
        "exam_cleaned_json",
        "textbook_2026",
        "standards_json",
        "pdf_library",
        "compiled_assets_ledger",
        "case_rubric_candidate_scope",
    }.issubset(ids)
    assert all(row["authority_status"] for row in asset_buckets)

    brief = (output_root / "ai_brief.md").read_text(encoding="utf-8")
    assert "AI Data Asset Brief v1" in brief
    assert "Cleaned JSON sources" in brief
    assert "PDF Compilation Status" in brief
    assert "Per-PDF ledger" in brief
    assert "Compiled/artifact files indexed" in brief
    assert "not runtime supply" in brief


def test_data_asset_brief_rejects_dangerous_output_root_before_reset(monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_missing_pdf_ledger_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called when PDF ledger is missing: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="required input not found"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=tmp_path / "missing_pdf_ledger.json",
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_invalid_pdf_ledger_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    bad_ledger = tmp_path / "bad_pdf_ledger.json"
    bad_ledger.write_text(
        json.dumps(
            {
                "schema": "luban_pdf_source_ledger_manifest.v1",
                "authority_status": "mirror_pdf_summary",
                "runtime_guard": {"runtime_consumable": False, "official_score_allowed": False},
                "counts": {"pdf_sources": 95},
            }
        ),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid PDF ledger: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid PDF source ledger authority"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=bad_ledger,
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_missing_compiled_ledger_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called when compiled ledger is missing: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="required input not found"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=tmp_path / "missing_compiled_ledger.json",
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_invalid_compiled_ledger_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    bad_ledger = tmp_path / "bad_compiled_ledger.json"
    bad_ledger.write_text(
        json.dumps(
            {
                "schema": "luban_compiled_asset_ledger_manifest.v1",
                "authority_status": "runtime_truth",
                "runtime_guard": {"runtime_consumable": False, "official_score_allowed": False},
                "counts": {"files": 1},
            }
        ),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid compiled ledger: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid compiled asset ledger authority"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=bad_ledger,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_invalid_generated_sentinel_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    output_root.mkdir(parents=True)
    (output_root / ".data_asset_brief_generated.json").write_text(
        json.dumps({"generated_by": "someone_else", "kind": "data_asset_brief"}),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid sentinel: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid generated sentinel"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_data_asset_brief_rejects_valid_sentinel_with_extra_file_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    output_root.mkdir(parents=True)
    builder.write_sentinel(output_root, generated_at="2026-06-19T00:00:00+08:00")
    extra = output_root / "human_note.md"
    extra.write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for mixed generated tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe generated output tree"):
        builder.build_data_asset_brief(
            raw_profile_path=RAW_PROFILE,
            json_ledger_path=JSON_LEDGER,
            pdf_ledger_path=PDF_LEDGER,
            compiled_ledger_path=COMPILED_LEDGER,
            okf_scope_path=OKF_SCOPE,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )
    assert extra.read_text(encoding="utf-8") == "do not delete\n"


def test_data_asset_brief_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "data_asset_brief_v1"
    kwargs = {
        "raw_profile_path": RAW_PROFILE,
        "json_ledger_path": JSON_LEDGER,
        "pdf_ledger_path": PDF_LEDGER,
        "compiled_ledger_path": COMPILED_LEDGER,
        "okf_scope_path": OKF_SCOPE,
        "output_root": output_root,
        "generated_at": "2026-06-19T00:00:00+08:00",
    }
    builder.build_data_asset_brief(**kwargs)
    first = _collect_bytes(output_root)
    builder.build_data_asset_brief(**kwargs)
    second = _collect_bytes(output_root)

    assert second == first
