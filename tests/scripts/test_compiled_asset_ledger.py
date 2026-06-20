from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_compiled_asset_ledger.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_compiled_asset_ledger", SCRIPT_PATH)
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


def _fixture_roots(tmp_path: Path):
    artifacts_root = tmp_path / "artifacts"
    runtime_root = tmp_path / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
    (artifacts_root / "knowledge_compiler" / "2026").mkdir(parents=True)
    (artifacts_root / "knowledge_compiler" / "2026" / "compile_manifest.json").write_text(
        json.dumps({"kind": "compile_manifest", "records": 2}),
        encoding="utf-8",
    )
    (artifacts_root / "knowledge_compiler" / "2026" / "payload.bin").write_bytes(b"\x00" * 10)
    (artifacts_root / "root_report.md").write_text("# root report\n", encoding="utf-8")
    (artifacts_root / "knowledge_compiler" / "2026" / "__pycache__").mkdir()
    (artifacts_root / "knowledge_compiler" / "2026" / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
    (runtime_root / "v_rich_leaf_context").mkdir(parents=True)
    (runtime_root / "v_rich_leaf_context" / "canonical_pointer.json").write_text(
        json.dumps({"namespace": "test", "published": False}),
        encoding="utf-8",
    )
    return artifacts_root, runtime_root


def test_compiled_asset_ledger_indexes_artifacts_and_copies_manifest_snapshots(tmp_path):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)
    output_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"

    result = builder.build_compiled_asset_ledger(
        artifacts_root=artifacts_root,
        runtime_supply_root=runtime_root,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_compiled_asset_ledger_manifest.v1"
    assert manifest["authority_status"] == "compiled_asset_inventory_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["files"] == 4
    assert manifest["counts"]["asset_groups"] == 3
    assert manifest["counts"]["manifest_refs_copied"] == 3
    assert manifest["copy_policy"]["payloads_copied"] is False
    assert manifest["copy_policy"]["manifest_like_snapshots_copied"] is True

    groups = _read_json(output_root / "asset_groups.json")["asset_groups"]
    group_ids = {row["asset_group"] for row in groups}
    assert {"artifacts/knowledge_compiler", "artifacts/[root_files]", "runtime_supply"}.issubset(group_ids)

    records = _read_jsonl(output_root / "files.jsonl")
    assert len(records) == 4
    assert all(len(record["sha256"]) == 64 for record in records)
    assert all(record["runtime_guard"]["canonical_write_allowed"] is False for record in records)

    refs = _read_jsonl(output_root / "manifest_refs.jsonl")
    snapshot_paths = [output_root / ref["snapshot_path"] for ref in refs]
    assert all(path.exists() for path in snapshot_paths)
    assert any("compile_manifest" in path.name for path in snapshot_paths)
    assert any("canonical_pointer" in path.name for path in snapshot_paths)
    assert any("root_report" in path.name for path in snapshot_paths)

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "Compiled Asset Ledger v1" in summary
    assert "not runtime install" in summary


def test_compiled_asset_ledger_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_compiled_asset_ledger(
            artifacts_root=artifacts_root,
            runtime_supply_root=runtime_root,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_ledger_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)
    output_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_compiled_asset_ledger(
            artifacts_root=artifacts_root,
            runtime_supply_root=runtime_root,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_ledger_rejects_invalid_generated_sentinel_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)
    output_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"
    output_root.mkdir(parents=True)
    (output_root / ".compiled_asset_ledger_generated.json").write_text(
        json.dumps({"generated_by": "someone_else", "kind": "compiled_asset_ledger"}),
        encoding="utf-8",
    )

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid sentinel: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid generated sentinel"):
        builder.build_compiled_asset_ledger(
            artifacts_root=artifacts_root,
            runtime_supply_root=runtime_root,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_ledger_rejects_valid_sentinel_with_extra_file_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)
    output_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"
    output_root.mkdir(parents=True)
    builder.write_sentinel(output_root, generated_at="2026-06-19T00:00:00+08:00")
    extra = output_root / "human_note.md"
    extra.write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for mixed generated tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe generated output tree"):
        builder.build_compiled_asset_ledger(
            artifacts_root=artifacts_root,
            runtime_supply_root=runtime_root,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )
    assert extra.read_text(encoding="utf-8") == "do not delete\n"


def test_compiled_asset_ledger_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    artifacts_root, runtime_root = _fixture_roots(tmp_path)
    output_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"
    kwargs = {
        "artifacts_root": artifacts_root,
        "runtime_supply_root": runtime_root,
        "output_root": output_root,
        "generated_at": "2026-06-19T00:00:00+08:00",
    }
    builder.build_compiled_asset_ledger(**kwargs)
    first = _collect_bytes(output_root)
    builder.build_compiled_asset_ledger(**kwargs)
    second = _collect_bytes(output_root)

    assert second == first
