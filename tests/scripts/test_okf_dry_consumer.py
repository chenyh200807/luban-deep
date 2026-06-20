from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_okf_dry_consumer.py"
COMPILED_ROOT = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions" / "okf_rubric_pilot_v0"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_okf_dry_consumer", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_dry_consumer_reads_compiled_pack_without_runtime_writes(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "okf_dry_consumer_v0"

    result = builder.consume_candidate_pack(
        compiled_root=COMPILED_ROOT,
        output_root=output_root,
        generated_at="2026-06-19T00:00:00+08:00",
    )

    receipt = result["receipt"]
    assert receipt["schema"] == "luban_okf_dry_consumer_receipt.v0"
    assert receipt["status"] == "dry_consumed_non_runtime"
    assert receipt["counts"] == {"cases": 1, "rubrics": 5, "scoring_points": 15}
    assert receipt["runtime_guard"]["runtime_consumable"] is False
    assert receipt["runtime_guard"]["canonical_write_allowed"] is False
    assert receipt["runtime_guard"]["official_score_allowed"] is False
    assert receipt["sample"]["case_id"] == "case_2021_1"
    assert "sp_2021_1_q01_01" in receipt["sample"]["scoring_point_ids"]

    written = _read_json(output_root / "receipt.json")
    assert written == receipt


def test_dry_consumer_rejects_runtime_consumable_context_pack(tmp_path):
    builder = _load_builder()
    compiled_root = tmp_path / "okf_rubric_pilot_v0"
    shutil.copytree(COMPILED_ROOT, compiled_root)
    context_pack_path = compiled_root / "question_context_pack.json"
    context_pack = _read_json(context_pack_path)
    context_pack["runtime_guard"]["runtime_consumable"] = True
    context_pack_path.write_text(json.dumps(context_pack, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="runtime_consumable=false"):
        builder.consume_candidate_pack(
            compiled_root=compiled_root,
            output_root=tmp_path / "extractions" / "okf_dry_consumer_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_dry_consumer_rejects_count_mismatch(tmp_path):
    builder = _load_builder()
    compiled_root = tmp_path / "okf_rubric_pilot_v0"
    shutil.copytree(COMPILED_ROOT, compiled_root)
    point_index_path = compiled_root / "scoring_point_index.json"
    point_index = _read_json(point_index_path)
    point_index["points_by_id"].pop("sp_2021_1_q01_01")
    point_index_path.write_text(json.dumps(point_index, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="scoring point count mismatch"):
        builder.consume_candidate_pack(
            compiled_root=compiled_root,
            output_root=tmp_path / "extractions" / "okf_dry_consumer_v0",
            generated_at="2026-06-19T00:00:00+08:00",
        )


def test_dry_consumer_rejects_dangerous_output_root(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.consume_candidate_pack(
            compiled_root=COMPILED_ROOT,
            output_root=REPO_ROOT,
            generated_at="2026-06-19T00:00:00+08:00",
        )
