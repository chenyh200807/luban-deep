from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_compiled_asset_authority_map.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_compiled_asset_authority_map", SCRIPT_PATH)
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


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture_inputs(tmp_path: Path):
    ledger_root = tmp_path / "extractions" / "compiled_asset_ledger_v1"
    runtime_root = tmp_path / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
    output_root = tmp_path / "extractions" / "compiled_asset_authority_map_v1"
    artifact_manifest = tmp_path / "artifacts" / "shadow_runtime_supply" / "runtime_supply" / "manifest.json"
    published_pointer = runtime_root / "v_published" / "canonical_pointer.json"
    candidate_pointer = runtime_root / "v_candidate" / "canonical_pointer.json"
    manifest_no_publish = runtime_root / "v_manifest" / "runtime_supply_manifest.json"

    _write_json(
        ledger_root / "manifest.json",
        {
            "schema": "luban_compiled_asset_ledger_manifest.v1",
            "authority_status": "compiled_asset_inventory_only",
            "runtime_guard": {"runtime_consumable": False, "official_score_allowed": False},
            "counts": {"files": 4, "asset_groups": 2},
        },
    )
    _write_json(
        ledger_root / "asset_groups.json",
        {
            "schema": "luban_compiled_asset_groups.v1",
            "asset_groups": [
                {
                    "asset_group": "artifacts/knowledge_compiler",
                    "group_kind": "knowledge_compiler_workbench",
                    "authority_status": "artifact_workbench_or_candidate_inventory",
                    "files": 2,
                    "bytes": 20,
                    "manifest_like_files": 1,
                },
                {
                    "asset_group": "runtime_supply",
                    "group_kind": "runtime_supply_mixed_published_and_candidate",
                    "authority_status": "runtime_supply_inventory_mixed_publication_status",
                    "files": 2,
                    "bytes": 30,
                    "manifest_like_files": 2,
                },
            ],
        },
    )
    _write_json(
        artifact_manifest,
        {
            "namespace": "artifact_shadow",
            "status": "release_candidate",
            "published": True,
            "content_hash": "abc",
        },
    )
    _write_json(
        published_pointer,
        {
            "namespace": "published_bundle",
            "status": "release_candidate",
            "published": True,
            "content_hash": "a" * 64,
            "bundle_file": "published.json",
        },
    )
    _write_json(
        candidate_pointer,
        {
            "namespace": "candidate_bundle",
            "status": "release_candidate",
            "published": False,
            "expected_content_hash": "b" * 64,
            "bundle_path": "candidate.json",
        },
    )
    _write_json(
        manifest_no_publish,
        {
            "schema_version": "bundle_manifest.v1",
            "status": "limited_default_candidate",
            "content_hash": "c" * 64,
        },
    )
    records = [
        {
            "source_path": str(artifact_manifest),
            "asset_group": "artifacts/knowledge_compiler",
            "extension": ".json",
            "bytes": artifact_manifest.stat().st_size,
        },
        {
            "source_path": str(published_pointer),
            "asset_group": "runtime_supply",
            "extension": ".json",
            "bytes": published_pointer.stat().st_size,
        },
        {
            "source_path": str(candidate_pointer),
            "asset_group": "runtime_supply",
            "extension": ".json",
            "bytes": candidate_pointer.stat().st_size,
        },
        {
            "source_path": str(manifest_no_publish),
            "asset_group": "runtime_supply",
            "extension": ".json",
            "bytes": manifest_no_publish.stat().st_size,
        },
    ]
    with (ledger_root / "files.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ledger_root, runtime_root, output_root


def test_compiled_asset_authority_map_classifies_groups_and_runtime_pointers(tmp_path):
    builder = _load_builder()
    ledger_root, runtime_root, output_root = _fixture_inputs(tmp_path)

    result = builder.build_compiled_asset_authority_map(
        compiled_ledger_manifest_path=ledger_root / "manifest.json",
        asset_groups_path=ledger_root / "asset_groups.json",
        files_path=ledger_root / "files.jsonl",
        runtime_supply_root=runtime_root,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_compiled_asset_authority_map_manifest.v1"
    assert manifest["authority_status"] == "compiled_asset_authority_map_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["asset_groups"] == 2
    assert manifest["counts"]["runtime_pointer_records"] == 3
    assert manifest["counts"]["published_runtime_pointers"] == 1
    assert manifest["counts"]["blocked_or_candidate_runtime_pointers"] == 2
    assert manifest["counts"]["direct_artifact_runtime_reads_allowed"] == 0

    groups = _read_json(output_root / "group_authority.json")["groups"]
    by_group = {row["asset_group"]: row for row in groups}
    assert by_group["artifacts/knowledge_compiler"]["authority_class"] == "candidate_compiler_workbench_read_only"
    assert by_group["artifacts/knowledge_compiler"]["direct_runtime_read_allowed"] is False
    assert by_group["runtime_supply"]["authority_class"] == "runtime_supply_pointer_gated"

    pointers = _read_jsonl(output_root / "runtime_pointers.jsonl")
    by_namespace = {row["namespace"]: row for row in pointers}
    assert "artifact_shadow" not in by_namespace
    assert by_namespace["published_bundle"]["runtime_read_allowed"] is True
    assert by_namespace["published_bundle"]["consumer_status"] == "published_runtime_supply_hash_gated"
    assert by_namespace["candidate_bundle"]["runtime_read_allowed"] is False
    assert by_namespace["candidate_bundle"]["consumer_status"] == "release_candidate_not_runtime_default"
    assert any(row["consumer_status"] == "candidate_manifest_no_publish_flag" for row in pointers)
    assert all(row["official_score_allowed"] is False for row in pointers)

    policy = _read_json(output_root / "consumer_policy.json")
    assert "deterministic gates sign releases" in policy["principle"]
    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "Compiled Asset Authority Map v1" in summary
    assert "artifacts/*" in summary


def test_compiled_asset_authority_map_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()
    ledger_root, runtime_root, _output_root = _fixture_inputs(tmp_path)

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_compiled_asset_authority_map(
            compiled_ledger_manifest_path=ledger_root / "manifest.json",
            asset_groups_path=ledger_root / "asset_groups.json",
            files_path=ledger_root / "files.jsonl",
            runtime_supply_root=runtime_root,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_authority_map_rejects_invalid_ledger_before_output(tmp_path, monkeypatch):
    builder = _load_builder()
    ledger_root, runtime_root, output_root = _fixture_inputs(tmp_path)
    manifest_path = ledger_root / "manifest.json"
    payload = _read_json(manifest_path)
    payload["authority_status"] = "runtime_truth"
    _write_json(manifest_path, payload)

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for invalid input: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="invalid compiled asset ledger authority"):
        builder.build_compiled_asset_authority_map(
            compiled_ledger_manifest_path=manifest_path,
            asset_groups_path=ledger_root / "asset_groups.json",
            files_path=ledger_root / "files.jsonl",
            runtime_supply_root=runtime_root,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_authority_map_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    ledger_root, runtime_root, output_root = _fixture_inputs(tmp_path)
    output_root.mkdir(parents=True)
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_compiled_asset_authority_map(
            compiled_ledger_manifest_path=ledger_root / "manifest.json",
            asset_groups_path=ledger_root / "asset_groups.json",
            files_path=ledger_root / "files.jsonl",
            runtime_supply_root=runtime_root,
            output_root=output_root,
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_compiled_asset_authority_map_repeated_generation_is_byte_identical_with_fixed_timestamp(tmp_path):
    builder = _load_builder()
    ledger_root, runtime_root, output_root = _fixture_inputs(tmp_path)
    kwargs = {
        "compiled_ledger_manifest_path": ledger_root / "manifest.json",
        "asset_groups_path": ledger_root / "asset_groups.json",
        "files_path": ledger_root / "files.jsonl",
        "runtime_supply_root": runtime_root,
        "output_root": output_root,
        "generated_at": "2026-06-19T00:00:00+08:00",
    }
    builder.build_compiled_asset_authority_map(**kwargs)
    first = _collect_bytes(output_root)
    builder.build_compiled_asset_authority_map(**kwargs)
    second = _collect_bytes(output_root)

    assert second == first
