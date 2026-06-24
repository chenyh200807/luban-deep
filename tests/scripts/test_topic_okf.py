from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_topic_okf.py"
JSON_SOURCES = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "json_source_ledger_v0" / "sources.jsonl"
OKF_POINTS = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_candidate_scope_v0" / "scoring_points.jsonl"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_topic_okf", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_topic_okf_builds_ai_only_topic_cards(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "topic_okf_v0"

    result = builder.build_topics(
        json_sources_path=JSON_SOURCES,
        okf_points_path=OKF_POINTS,
        output_root=output_root,
        generated_at="2026-06-20T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "luban_topic_okf_manifest.v0"
    assert manifest["status"] == "topic_okf_candidate_ready"
    assert manifest["authority_status"] == "ai_topic_navigation_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["counts"]["topics"] == 5
    assert manifest["counts"]["source_hits_kept"] > 0

    topics = _read_jsonl(output_root / "topics.jsonl")
    by_id = {topic["topic_id"]: topic for topic in topics}
    assert set(by_id) == {
        "claims",
        "flow-construction",
        "network-planning",
        "quality-acceptance",
        "roof-waterproofing",
    }
    assert by_id["roof-waterproofing"]["title"] == "屋面防水"
    assert by_id["roof-waterproofing"]["runtime_guard"]["runtime_consumable"] is False
    assert by_id["roof-waterproofing"]["evidence_summary"]["source_count"] > 0
    assert by_id["roof-waterproofing"]["evidence_summary"]["candidate_rubric"]["candidate_scoring_point_count"] > 0
    assert "屋面防水" in by_id["roof-waterproofing"]["aliases"]

    hits = _read_jsonl(output_root / "source_hits.jsonl")
    assert hits
    assert all(hit["runtime_guard"]["canonical_write_allowed"] is False for hit in hits)
    assert any(hit["topic_id"] == "roof-waterproofing" for hit in hits)
    assert (output_root / "summary.md").read_text(encoding="utf-8").startswith("# Topic OKF v0")


def test_topic_okf_rejects_runtime_consumable_source(tmp_path):
    builder = _load_builder()
    source_copy = tmp_path / "sources.jsonl"
    rows = _read_jsonl(JSON_SOURCES)
    rows[0]["runtime_guard"]["runtime_consumable"] = True
    source_copy.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runtime_consumable=false"):
        builder.build_topics(
            json_sources_path=source_copy,
            okf_points_path=OKF_POINTS,
            output_root=tmp_path / "extractions" / "topic_okf_v0",
            generated_at="2026-06-20T00:00:00+08:00",
        )


def test_topic_okf_rejects_dangerous_output_root(monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_topics(
            json_sources_path=JSON_SOURCES,
            okf_points_path=OKF_POINTS,
            output_root=REPO_ROOT,
            generated_at="2026-06-20T00:00:00+08:00",
        )


def test_topic_okf_rejects_foreign_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "topic_okf_v0"
    output_root.mkdir(parents=True)
    (output_root / ".topic_okf_generated.json").write_text(
        json.dumps(
            {
                "kind": "topic_okf",
                "generated_by": "build_topic_okf.py",
                "generated_at": "2026-06-20T00:00:00+08:00",
                "runtime_consumable": False,
            }
        ),
        encoding="utf-8",
    )
    (output_root / "unexpected.txt").write_text("no", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe tree: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe generated output tree"):
        builder.build_topics(
            json_sources_path=JSON_SOURCES,
            okf_points_path=OKF_POINTS,
            output_root=output_root,
            generated_at="2026-06-20T00:00:00+08:00",
        )
