"""R8 解药库投影域测试——signed+sha 双 fail-closed 是本模块唯一的存在理由。

镜像 test_concept_cards.py 的闸测试口径：
candidate 拒 / sha 漂移拒 / signed+sha 过 / 非绿灯拒 / 缺 bank 拒。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_antidote,
    build_antidote_library,
)

_A01 = {
    "pack_id": "A01", "title": "检验批验收程序", "content_sha256": "abc123",
    "published": True, "jury_clean": True, "explicitly_barred_default_entry": False,
}
_ANTIDOTES = {
    "E07": [{
        "r8_id": "A01:R8-4",
        "mental_model": "监理单位组织、施工单位实施、监理见证全过程。",
        "textbook_ref": "kc:1A434020_085_0136:1",
    }],
    "E02": [{
        "r8_id": "A01:R8-3",
        "mental_model": "固定四件套：混凝土强度/钢筋保护层/尺寸偏差/合同约定。",
        "textbook_ref": "kc:1A434020_085_0136:0",
    }],
}


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def _write_bank(tmp_path: Path, *, status="signed", sha="abc123", antidotes=None) -> None:
    (tmp_path / "_A01_r8_antidote_bank.v0.json").write_text(
        json.dumps({
            "schema_version": "luban-antidote-bank",
            "pack_id": "A01",
            "status": status,
            "source_pack_sha256": sha,
            "antidotes": _ANTIDOTES if antidotes is None else antidotes,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_signed_sha_match_projects_antidote(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path)
    got = build_antidote("a01", "E07", manifest_path=mp)
    assert got["mental_model"] == _ANTIDOTES["E07"][0]["mental_model"]
    assert got["textbook_ref"] == "kc:1A434020_085_0136:1"
    lib = build_antidote_library(manifest_path=mp)
    assert lib["total"] == 2  # E07 + E02 各一条
    assert lib["packs"] == [
        {"pack_id": "A01", "title": "检验批验收程序",
         "error_codes": ["E02", "E07"], "antidote_count": 2}
    ]


def test_unknown_error_code_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path)
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E99", manifest_path=mp)


def test_candidate_bank_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path, status="candidate")
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E07", manifest_path=mp)
    assert build_antidote_library(manifest_path=mp) == {"total": 0, "packs": []}


def test_sha_drift_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    _write_bank(tmp_path, sha="stale000")
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E07", manifest_path=mp)
    assert build_antidote_library(manifest_path=mp)["total"] == 0


def test_non_green_pack_fail_closed_even_if_signed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], [])
    _write_bank(tmp_path)
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E07", manifest_path=mp)
    assert build_antidote_library(manifest_path=mp)["total"] == 0


def test_missing_bank_or_empty_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_A01], ["A01"])
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E07", manifest_path=mp)  # bank 缺失
    _write_bank(tmp_path, antidotes={})
    with pytest.raises(LessonNotAvailable):
        build_antidote("A01", "E07", manifest_path=mp)  # 空池同形
