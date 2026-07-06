"""R6 精确挖空库投影域测试——signed+sha 双 fail-closed 是本模块唯一的存在理由。

镜像 test_concept_cards.py 的闸测试口径：
candidate 拒 / sha 漂移拒 / signed+sha 过 / 非绿灯拒 / 缺 bank 拒。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_cloze,
    build_cloze_library,
)

_A01 = {
    "pack_id": "A01", "title": "检验批验收程序", "content_sha256": "abc123",
    "published": True, "jury_clean": True, "explicitly_barred_default_entry": False,
}
_SENTENCE = {
    "cloze_id": "A01:C4-1",
    "point_id": "kc:1A434020_085_0136:0",
    "text_before": "实体检验四内容：",
    "blank_hint": "混凝土强度 / 钢筋保护层 / 尺寸偏差",
    "text_after": "、合同约定项目",
}
_RECALL = "想一想：每个采分点的关键词，你能默写全吗？"


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def _write_bank(tmp_path: Path, *, status="signed", sha="abc123", sentences=None) -> None:
    (tmp_path / "_A01_r6_cloze_bank.v0.json").write_text(
        json.dumps({
            "schema_version": "luban-cloze-bank",
            "pack_id": "A01",
            "status": status,
            "source_pack_sha256": sha,
            "recall_prompt": _RECALL,
            "skeleton_sentences": [_SENTENCE] if sentences is None else sentences,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_signed_sha_match_projects_cloze(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path)
    vm = build_cloze("a01", manifest_path=mp)
    assert vm["pack_id"] == "A01"
    assert vm["recall_prompt"] == _RECALL
    s = vm["skeleton_sentences"][0]
    assert s["text_before"] == "实体检验四内容："
    assert s["blank_hint"] == "混凝土强度 / 钢筋保护层 / 尺寸偏差"
    assert s["text_after"] == "、合同约定项目"
    lib = build_cloze_library(manifest_path=mp)
    assert lib["total"] == 1
    assert lib["packs"] == [
        {"pack_id": "A01", "title": "检验批验收程序", "cloze_count": 1}
    ]


def test_candidate_bank_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path, status="candidate")
    with pytest.raises(LessonNotAvailable):
        build_cloze("A01", manifest_path=mp)
    assert build_cloze_library(manifest_path=mp) == {"total": 0, "packs": []}


def test_sha_drift_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path, sha="stale000")
    with pytest.raises(LessonNotAvailable):
        build_cloze("A01", manifest_path=mp)
    assert build_cloze_library(manifest_path=mp)["total"] == 0


def test_non_green_pack_fail_closed_even_if_signed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], [])
    _write_bank(tmp_path)
    with pytest.raises(LessonNotAvailable):
        build_cloze("A01", manifest_path=mp)
    assert build_cloze_library(manifest_path=mp)["total"] == 0


def test_missing_bank_or_empty_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    with pytest.raises(LessonNotAvailable):
        build_cloze("A01", manifest_path=mp)  # bank 缺失
    _write_bank(tmp_path, sentences=[])
    with pytest.raises(LessonNotAvailable):
        build_cloze("A01", manifest_path=mp)  # 空池同形
