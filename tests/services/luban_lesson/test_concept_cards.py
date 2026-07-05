"""考点卡库投影域测试——signed+sha 双 fail-closed 是本模块唯一的存在理由。

镜像 test_read_model.py 的变体池闸测试口径：
candidate 拒 / sha 漂移拒 / signed+sha 过 / 非绿灯拒 / 旗标关空投影。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_concept_card_library,
    build_concept_cards,
)

_S05 = {
    "pack_id": "S05", "title": "临时用电三级配电", "content_sha256": "abc123",
    "published": True, "jury_clean": True, "explicitly_barred_default_entry": False,
}
_CARD = {
    "card_id": "S05:kc:1A431011_015_0016:1",
    "front": "送电/停电顺序",
    "key_gist": "送电：总→分→开；停电：开→分→总",
    "quote": "送电顺序：总配电箱 → 分配电箱 → 开关箱；停电顺序：开关箱 → 分配电箱 → 总配电箱。",
    "point_id": "kc:1A431011_015_0016:1",
    "source_ref": {"chunk_id": "1A431011_015_0016", "page_num": 15, "source_lane": "textbook"},
}


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def _write_bank(tmp_path: Path, *, status="signed", sha="abc123", cards=None) -> None:
    (tmp_path / "_S05_concept_card_bank.v0.json").write_text(
        json.dumps({
            "schema_version": "luban-concept-card-bank",
            "pack_id": "S05",
            "status": status,
            "source_pack_sha256": sha,
            "cards": [_CARD] if cards is None else cards,
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_signed_sha_match_projects_cards(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path)
    deck = build_concept_cards("s05", manifest_path=mp)
    assert deck["pack_id"] == "S05"
    assert deck["card_count"] == 1
    card = deck["cards"][0]
    assert card["quote"] == _CARD["quote"]  # 教材原文逐字透传
    assert card["point_id"] == _CARD["point_id"]  # 溯源角注
    library = build_concept_card_library(manifest_path=mp)
    assert library["total"] == 1
    assert library["packs"] == [
        {"pack_id": "S05", "title": "临时用电三级配电", "card_count": 1}
    ]


def test_candidate_bank_fail_closed(tmp_path):
    """candidate 未签发 = 与 bank 缺失同形不可见（签发留 owner 人闸）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, status="candidate")
    with pytest.raises(LessonNotAvailable):
        build_concept_cards("S05", manifest_path=mp)
    assert build_concept_card_library(manifest_path=mp) == {"total": 0, "packs": []}


def test_sha_drift_fail_closed(tmp_path):
    """pack 正文修订后旧卡池失效（source_pack_sha256 ≠ manifest content_sha256）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, sha="stale000")
    with pytest.raises(LessonNotAvailable):
        build_concept_cards("S05", manifest_path=mp)
    assert build_concept_card_library(manifest_path=mp)["total"] == 0


def test_non_green_pack_fail_closed_even_if_signed(tmp_path):
    """manifest 绿灯是前置门：bank 签了但 pack 不在绿灯集 → 同样不可见。"""
    mp = _write_manifest(tmp_path, [_S05], [])
    _write_bank(tmp_path)
    with pytest.raises(LessonNotAvailable):
        build_concept_cards("S05", manifest_path=mp)
    assert build_concept_card_library(manifest_path=mp)["total"] == 0


def test_missing_bank_or_empty_cards_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    with pytest.raises(LessonNotAvailable):
        build_concept_cards("S05", manifest_path=mp)  # bank 文件缺失
    _write_bank(tmp_path, cards=[])
    with pytest.raises(LessonNotAvailable):
        build_concept_cards("S05", manifest_path=mp)  # 空卡池同形


@pytest.mark.asyncio
async def test_router_flag_off_empty_projection(monkeypatch):
    """旗标关：库 = 空投影（路由形状稳定），单站 = 404 同形。"""
    from fastapi import HTTPException

    from deeptutor.api.routers.luban_lesson import (
        concept_card_deck,
        concept_card_library,
    )

    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    assert await concept_card_library(None) == {"total": 0, "packs": [], "enabled": False}
    with pytest.raises(HTTPException) as exc:
        await concept_card_deck("S05", None)
    assert exc.value.status_code == 404
