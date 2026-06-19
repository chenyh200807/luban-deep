from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_landing_gap.py"
CANONICAL_RUBRIC = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "case_rubric_canonical.json"
JSON_LEDGER_MANIFEST = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "json_source_ledger_v0" / "manifest.json"
)
OKF_MANIFEST = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_rubric_pilot_v0" / "manifest.json"
)
DRY_CONSUMER_RECEIPT = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_dry_consumer_v0" / "receipt.json"
)
SOURCE_ALIGNMENT_REPORT = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_source_alignment_v0" / "report.json"
)
CANDIDATE_SCOPE_MANIFEST = (
    REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_candidate_scope_v0" / "manifest.json"
)


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_landing_gap", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_gap_report_compares_target_to_current_source_layer(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "okf_landing_gap_v0"

    result = builder.build_gap_report(
        canonical_rubric_path=CANONICAL_RUBRIC,
        json_ledger_manifest_path=JSON_LEDGER_MANIFEST,
        okf_manifest_path=OKF_MANIFEST,
        dry_consumer_receipt_path=DRY_CONSUMER_RECEIPT,
        source_alignment_report_path=SOURCE_ALIGNMENT_REPORT,
        candidate_scope_manifest_path=CANDIDATE_SCOPE_MANIFEST,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    report = result["report"]
    assert report["schema"] == "luban_okf_landing_gap_report.v0"
    assert report["status"] == "source_layer_target_matched"
    assert report["target"]["canonical_rubric"]["cases"] == 25
    assert report["target"]["canonical_rubric"]["scoring_points"] == 431
    assert report["current"]["okf_pilot"]["cases"] == 1
    assert report["current"]["okf_pilot"]["scoring_points"] == 15
    assert report["current"]["okf_candidate_scope"]["cases"] == 25
    assert report["current"]["okf_candidate_scope"]["scoring_points"] == 431
    assert report["gap"]["remaining_cases"] == 0
    assert report["gap"]["remaining_scoring_points"] == 0
    assert report["current"]["json_source_ledger"]["json_sources"] == 383
    assert report["current"]["json_source_ledger"]["buckets"]["exam_cleaned_json"] == 11
    assert report["current"]["okf_dry_consumer"]["status"] == "dry_consumed_non_runtime"
    assert report["current"]["okf_source_alignment"]["status"] == "case_source_alignment_ready"
    assert report["runtime_guard"]["runtime_consumable"] is False
    assert report["runtime_guard"]["official_score_allowed"] is False
    assert report["next_actions"][0]["id"] == "okf_dry_consumer"
    assert report["next_actions"][0]["status"] == "completed"
    assert report["next_actions"][1]["id"] == "ledger_to_okf_source_alignment"
    assert report["next_actions"][1]["status"] == "completed"
    assert report["next_actions"][2]["id"] == "expand_okf_candidate_scope"
    assert report["next_actions"][2]["status"] == "completed"

    written = _read_json(output_root / "report.json")
    assert written == report


def test_build_gap_report_rejects_runtime_consumable_okf_manifest(tmp_path):
    builder = _load_builder()
    bad_manifest = tmp_path / "bad_okf_manifest.json"
    manifest = _read_json(OKF_MANIFEST)
    manifest["runtime_guard"]["runtime_consumable"] = True
    bad_manifest.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="runtime_consumable=false"):
        builder.build_gap_report(
            canonical_rubric_path=CANONICAL_RUBRIC,
            json_ledger_manifest_path=JSON_LEDGER_MANIFEST,
            okf_manifest_path=bad_manifest,
            dry_consumer_receipt_path=DRY_CONSUMER_RECEIPT,
            source_alignment_report_path=SOURCE_ALIGNMENT_REPORT,
            candidate_scope_manifest_path=CANDIDATE_SCOPE_MANIFEST,
            output_root=tmp_path / "extractions" / "okf_landing_gap_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_build_gap_report_rejects_dangerous_output_root(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_gap_report(
            canonical_rubric_path=CANONICAL_RUBRIC,
            json_ledger_manifest_path=JSON_LEDGER_MANIFEST,
            okf_manifest_path=OKF_MANIFEST,
            dry_consumer_receipt_path=DRY_CONSUMER_RECEIPT,
            source_alignment_report_path=SOURCE_ALIGNMENT_REPORT,
            candidate_scope_manifest_path=CANDIDATE_SCOPE_MANIFEST,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )
