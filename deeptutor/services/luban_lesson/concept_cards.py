"""考点卡库只读投影（复习模块 §6.2 的 30 秒再认卡，纸墨风翻卡页消费）。

Thin 投影层，与 ``read_model.py`` 同一纪律：
- 卡真值 = 编译期签发的 ``_{pack_id}_concept_card_bank.v0.json``
  （``scripts/build_luban_concept_card_bank.py`` 确定性派生自签发 pack §1 +
  compiled_source 逐字 quote；本模块零生成、零改写）；
- 签发闸复用 ``read_model._load_signed_bank``（signed + source_pack_sha256
  双 fail-closed，单一 loader authority）——candidate 未签发 / pack 修订后
  sha 漂移 / 文件缺失，一律与 bank 缺失同形不可见；
- 只投影 manifest 绿灯包（与 lesson 同一门）；
- **零写入**：翻卡页的「记住了/再看一眼」是纯本地呈现态，本模块不提供
  任何写路径，掌握态唯一权威仍是判分链路 + revalidation_queue。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from deeptutor.services.luban_lesson.read_model import (
    _MANIFEST_PATH,
    LessonNotAvailable,
    _load_manifest,
    _load_signed_bank,
)

_CONCEPT_CARD_BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"


def _signed_cards(
    pack: dict[str, Any], manifest_dir: Path
) -> list[dict[str, Any]] | None:
    bank = _load_signed_bank(
        str(pack.get("pack_id") or ""),
        manifest_dir,
        str(pack.get("content_sha256") or ""),
        filename_template=_CONCEPT_CARD_BANK_TEMPLATE,
    )
    if bank is None:
        return None
    cards = [c for c in bank.get("cards") or [] if isinstance(c, dict)]
    return cards or None


def build_concept_card_library(
    *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """考点卡库总览投影（复习页资产入口的「张数」真值）。

    只数 manifest 绿灯 ∧ signed+sha 双闸通过的 bank；一个都没有 →
    ``total=0, packs=[]``（复习页据此保持「即将开通」诚实占位）。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    packs = []
    total = 0
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        cards = _signed_cards(pack, manifest_dir)
        if cards is None:
            continue
        packs.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "card_count": len(cards),
            }
        )
        total += len(cards)
    return {"total": total, "packs": sorted(packs, key=lambda p: p["pack_id"])}


def build_concept_cards(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单站考点卡投影（翻卡页数据）；不过任一道闸一律 LessonNotAvailable。"""
    pack_id = str(pack_id or "").strip().upper()
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    if pack_id not in green:
        raise LessonNotAvailable(pack_id)
    pack = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id),
        None,
    )
    if pack is None:
        raise LessonNotAvailable(pack_id)
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    cards = _signed_cards(pack, manifest_dir)
    if cards is None:
        raise LessonNotAvailable(pack_id)
    return {
        "pack_id": pack_id,
        "title": str(pack.get("title") or ""),
        "card_count": len(cards),
        "cards": [
            {
                "card_id": str(c.get("card_id") or ""),
                "front": str(c.get("front") or ""),
                "key_gist": str(c.get("key_gist") or ""),
                "quote": str(c.get("quote") or ""),
                "point_id": str(c.get("point_id") or ""),
                "source_ref": c.get("source_ref") or {},
            }
            for c in cards
        ],
    }
