from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_knowledge_compiler_okf.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_knowledge_compiler_okf", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts" / "knowledge_compiler" / "2026"
    candidate = root / "lecture_compile_20260608"
    candidate.mkdir(parents=True)
    (candidate / "lecture_teaching_cards.jsonl").write_text(
        '{"id":"card_1"}\n{"id":"card_2"}\n',
        encoding="utf-8",
    )
    (candidate / "quality_report.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    fixture = root / "pytest-core-a"
    fixture.mkdir()
    (fixture / "question_capsules.jsonl").write_text('{"id":"q1"}\n', encoding="utf-8")
    (fixture / "__pycache__").mkdir()
    (fixture / "__pycache__" / "ignored.pyc").write_bytes(b"ignore")

    release = root / "signed-release-20260609"
    release.mkdir()
    (release / "canonical_pointer.json").write_text(json.dumps({"published": True}), encoding="utf-8")
    return root


def test_knowledge_compiler_okf_indexes_runs_by_stage(tmp_path):
    builder = _load_builder()
    compiler_root = _fixture_root(tmp_path)
    output_root = tmp_path / "extractions" / "knowledge_compiler_okf_v1"

    result = builder.build_knowledge_compiler_okf(
        compiler_root=compiler_root,
        output_root=output_root,
        generated_at="2026-06-20T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_knowledge_compiler_okf_manifest.v1"
    assert manifest["authority_status"] == "knowledge_compiler_workbench_inventory_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["copy_policy"]["payloads_copied"] is False
    assert manifest["counts"]["runs"] == 3
    assert manifest["counts"]["files"] == 4
    assert manifest["counts"]["by_stage"] == {"candidate": 1, "fixture": 1, "release": 1}

    runs = _read_jsonl(output_root / "compiler_runs.jsonl")
    stages = {row["run_id"]: row["compiler_stage"] for row in runs}
    assert stages["lecture_compile_20260608"] == "candidate"
    assert stages["pytest-core-a"] == "fixture"
    assert stages["signed-release-20260609"] == "release"
    assert any(row["jsonl_row_counts"].get("lecture_teaching_cards.jsonl") == 2 for row in runs)

    files = _read_jsonl(output_root / "file_index.jsonl")
    assert all(len(row["sha256"]) == 64 for row in files)
    assert all(row["runtime_guard"]["canonical_write_allowed"] is False for row in files)
    assert not any("__pycache__" in row["source_path"] for row in files)

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "Knowledge Compiler OKF v1" in summary
    assert "`fixture` means test/workbench data" in summary

    saved_manifest = _read_json(output_root / "manifest.json")
    assert saved_manifest == manifest


def test_knowledge_compiler_okf_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    compiler_root = _fixture_root(tmp_path)

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_knowledge_compiler_okf(
            compiler_root=compiler_root,
            output_root=REPO_ROOT,
            generated_at="2026-06-20T00:00:00+08:00",
        )


def test_knowledge_compiler_okf_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    compiler_root = _fixture_root(tmp_path)
    output_root = tmp_path / "extractions" / "knowledge_compiler_okf_v1"
    output_root.mkdir(parents=True)
    (output_root / "human_note.md").write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_knowledge_compiler_okf(
            compiler_root=compiler_root,
            output_root=output_root,
            generated_at="2026-06-20T00:00:00+08:00",
        )
