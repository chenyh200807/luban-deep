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
    assert "assets/governance-map.md" in files
    assert "assets/knowledge-compiler-workbench.md" in files
    assert "assets/luban-grading-artifacts-map.md" in files
    assert "topics/index.md" in files
    assert "topics/roof-waterproofing.md" in files
    assert "topics/flow-construction.md" in files
    assert "topics/network-planning.md" in files
    assert "topics/claims.md" in files
    assert "topics/quality-acceptance.md" in files
    assert "content_cards/index.md" in files
    assert "content_cards/exams/year-2021.md" in files
    assert "content_cards/rubrics/case-2021-1.md" in files
    assert "content_cards/textbooks/textbook-2026.md" in files
    assert files == sorted(files)
    assert all(path.endswith(".md") for path in files)
    assert len(files) == 82

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
    assert "[L1 content cards](content_cards/index.md)" in index
    assert "[Topic OKF cards](topics/index.md)" in index
    assert "[DeepTutor governance map](assets/governance-map.md)" in index
    assert "[Knowledge compiler workbench](assets/knowledge-compiler-workbench.md)" in index
    assert "[Luban grading artifacts map](assets/luban-grading-artifacts-map.md)" in index
    assert "they do not mirror full source payloads" in index
    assert "DeepTutor governance layers, not OKF format requirements" in index

    topic_index = (output_root / "topics" / "index.md").read_text(encoding="utf-8")
    assert "Topic OKF v0" in topic_index
    assert "[屋面防水](roof-waterproofing.md)" in topic_index
    assert "AI-only source navigation" in topic_index

    roof_topic = (output_root / "topics" / "roof-waterproofing.md").read_text(encoding="utf-8")
    assert "屋面防水做法" in roof_topic
    assert "Candidate scoring points:" in roof_topic
    assert "sp_2021_1_q05_04" in roof_topic
    assert "Treat candidate scoring-point counts as candidate evidence" in roof_topic

    candidate = (output_root / "okf" / "candidate-scope.md").read_text(encoding="utf-8")
    assert "Cases: 25" in candidate
    assert "Rubrics: 117" in candidate
    assert "Scoring points: 431" in candidate
    assert "not official scoring authority" in candidate

    compiler_card = (output_root / "assets" / "knowledge-compiler-workbench.md").read_text(encoding="utf-8")
    assert "Knowledge Compiler Workbench" in compiler_card
    assert "## Stage Split" in compiler_card
    assert "`candidate`" in compiler_card
    assert "`fixture`" in compiler_card
    assert "does not sign runtime supply" in compiler_card

    grading_card = (output_root / "assets" / "luban-grading-artifacts-map.md").read_text(encoding="utf-8")
    assert "Luban Grading Artifacts Map" in grading_card
    assert "AI project understanding" in grading_card
    assert "## Area Split" in grading_card
    assert "## Risk Split" in grading_card
    assert "does not participate in production" in grading_card

    governance_card = (output_root / "assets" / "governance-map.md").read_text(encoding="utf-8")
    assert "DeepTutor Governance Map" in governance_card
    assert "Mandatory Entry Points" in governance_card
    assert "docs/plan/INDEX.md" in governance_card
    assert "contracts/index.yaml" in governance_card
    assert "does not replace contracts, runbooks, plans, or skills" in governance_card

    content_index = (output_root / "content_cards" / "index.md").read_text(encoding="utf-8")
    assert "L1 curated content cards" in content_index
    assert "[2021 建筑实务真题](exams/year-2021.md)" in content_index
    assert "[case_2021_1](rubrics/case-2021-1.md)" in content_index
    assert "do not copy full source payloads" in content_index

    exam_card = (output_root / "content_cards" / "exams" / "year-2021.md").read_text(encoding="utf-8")
    assert "Case study:" in exam_card
    assert "FINAL_CLEANED_EXAM_V2021.json" in exam_card

    case_card = (output_root / "content_cards" / "rubrics" / "case-2021-1.md").read_text(encoding="utf-8")
    assert "sp_2021_1_q01_01" in case_card
    assert "分包单位与建筑工人应签订劳动合同" in case_card
    assert "not official score authority" in case_card

    textbook_card = (output_root / "content_cards" / "textbooks" / "textbook-2026.md").read_text(encoding="utf-8")
    assert "650" in textbook_card
    assert "not a full textbook mirror" in textbook_card


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
