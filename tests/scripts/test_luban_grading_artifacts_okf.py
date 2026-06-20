from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_luban_grading_artifacts_okf.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_luban_grading_artifacts_okf", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts" / "luban_grading_artifacts"
    runtime = root / "controlled_production_runtime_flip_m16_20260604"
    runtime.mkdir(parents=True)
    (runtime / "canonical_pointer.json").write_text(json.dumps({"published": False}), encoding="utf-8")
    (runtime / "trace.jsonl").write_text('{"event":"read"}\n', encoding="utf-8")

    gold = root / "teacher_review_gold_panel_20260604"
    gold.mkdir()
    (gold / "summary.md").write_text("# summary\n", encoding="utf-8")

    source = root / "case_rubric_anchor_backfill_20260604"
    source.mkdir()
    (source / "alignment_report.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignore")
    return root


def test_luban_grading_artifacts_okf_is_ai_context_only(tmp_path):
    builder = _load_builder()
    artifact_root = _fixture_root(tmp_path)
    output_root = tmp_path / "extractions" / "luban_grading_artifacts_okf_v1"

    result = builder.build_luban_grading_artifacts_okf(
        artifact_root=artifact_root,
        output_root=output_root,
        generated_at="2026-06-20T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_grading_artifacts_okf_manifest.v1"
    assert manifest["authority_status"] == "ai_project_context_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["runtime_guard"]["production_registry_write_allowed"] is False
    assert manifest["counts"]["runs"] == 3
    assert manifest["counts"]["files"] == 4
    assert manifest["counts"]["by_risk_level"]["high"] == 1

    runs = _read_jsonl(output_root / "artifact_runs.jsonl")
    by_id = {row["run_id"]: row for row in runs}
    assert by_id["controlled_production_runtime_flip_m16_20260604"]["area"] == "runtime_shadow"
    assert by_id["controlled_production_runtime_flip_m16_20260604"]["risk_level"] == "high"
    assert by_id["teacher_review_gold_panel_20260604"]["area"] == "gold_review"
    assert by_id["case_rubric_anchor_backfill_20260604"]["area"] == "source_alignment"

    files = _read_jsonl(output_root / "file_index.jsonl")
    assert all(len(row["sha256"]) == 64 for row in files)
    assert all(row["runtime_guard"]["canonical_write_allowed"] is False for row in files)
    assert not any("__pycache__" in row["source_path"] for row in files)

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "AI project understanding only" in summary
    assert "not runtime supply" in summary

    saved_manifest = _read_json(output_root / "manifest.json")
    assert saved_manifest == manifest


def test_luban_grading_artifacts_okf_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    artifact_root = _fixture_root(tmp_path)

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_luban_grading_artifacts_okf(
            artifact_root=artifact_root,
            output_root=REPO_ROOT,
            generated_at="2026-06-20T00:00:00+08:00",
        )


def test_luban_grading_artifacts_okf_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    artifact_root = _fixture_root(tmp_path)
    output_root = tmp_path / "extractions" / "luban_grading_artifacts_okf_v1"
    output_root.mkdir(parents=True)
    (output_root / "human_note.md").write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_luban_grading_artifacts_okf(
            artifact_root=artifact_root,
            output_root=output_root,
            generated_at="2026-06-20T00:00:00+08:00",
        )
