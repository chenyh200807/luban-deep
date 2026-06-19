from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_bundle.py"
INVENTORY_ROOT = REPO_ROOT / "docs" / "原始数据" / "数据盘点"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_bundle", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, rest = text.split("---\n", 1)
    head, body = rest.split("---\n", 1)
    assert body.strip()
    fields = {}
    for line in head.splitlines():
        if not line or line.startswith("  - "):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields


def test_okf_bundle_is_markdown_yaml_only(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "数据盘点" / "okf_bundle_v0"

    result = builder.build_okf_bundle(
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    files = result["files"]
    assert "index.md" in files
    assert "log.md" in files
    assert "okf/candidate-scope.md" in files
    assert "okf/source-alignment.md" in files
    assert "gaps/asset-gap-map.md" in files
    assert "assets/case-rubric-candidate-scope.md" in files
    assert files == sorted(files)
    assert all(path.endswith(".md") for path in files)

    for rel_path in files:
        frontmatter = _frontmatter(output_root / rel_path)
        assert frontmatter["type"]
        assert frontmatter["title"]
        assert frontmatter["description"]
        assert frontmatter["resource"] is not None
        assert frontmatter["timestamp"] == "2026-06-19T00:00:00+08:00"

    index = (output_root / "index.md").read_text(encoding="utf-8")
    assert "Markdown + YAML frontmatter + links" in index
    assert "Candidate cases / rubrics / scoring points: 25 / 117 / 431" in index
    assert "DeepTutor governance layers, not OKF format requirements" in index

    candidate = (output_root / "okf" / "candidate-scope.md").read_text(encoding="utf-8")
    assert "Cases: 25" in candidate
    assert "Rubrics: 117" in candidate
    assert "Scoring points: 431" in candidate
    assert "not official scoring authority" in candidate


def test_okf_bundle_rejects_dangerous_output_root_before_reset(monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_okf_bundle(output_root=REPO_ROOT, generated_at="2026-06-19T00:00:00+08:00")


def test_okf_bundle_rejects_non_markdown_owned_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "数据盘点" / "okf_bundle_v0"
    output_root.mkdir(parents=True)
    (output_root / "log.md").write_text(
        """---
type: "Log"
title: "OKF Bundle Generation Log"
description: "Generated markdown-only OKF bundle log."
resource: "tmp"
tags:
  - "luban"
timestamp: "2026-06-19T00:00:00+08:00"
generated_by: "build_okf_bundle.py"
status: "markdown_yaml_only"
---

# Generation Log
""",
        encoding="utf-8",
    )
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for non-markdown output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="markdown-only"):
        builder.build_okf_bundle(output_root=output_root, generated_at="2026-06-19T00:00:00+08:00")


def test_real_okf_bundle_has_only_markdown_files():
    if not (INVENTORY_ROOT / "okf_bundle_v0").exists():
        pytest.skip("real OKF bundle has not been generated")

    files = [path for path in (INVENTORY_ROOT / "okf_bundle_v0").rglob("*") if path.is_file()]
    assert files
    assert all(path.suffix == ".md" for path in files)
