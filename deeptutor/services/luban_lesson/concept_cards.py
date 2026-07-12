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

# ── 标准梯队(2026-07-12 spike): v32编译资产派生的全考纲标准卡 ──
# 与精品卡明示分层: tier="standard"、status=candidate;
# 只在 LUBAN_STD_CONCEPT_CARDS_ENABLED 且非生产时投影(owner 过目打样期,
# 签发口径未定, 签发纪律不为量产让步——生产永远 fail-closed)。
_STD_BANK_NAME = "_STD_concept_card_bank.v0.json"
_STD_FLAG = "LUBAN_STD_CONCEPT_CARDS_ENABLED"
_STD_PREFIX = "STD"


def _std_enabled() -> bool:
    import os

    return str(os.getenv(_STD_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _std_status_ok(bank: dict[str, Any]) -> bool:
    """生产只认 signed(promote std车道翻牌); 非生产额外容 candidate(打样预览)。"""
    from deeptutor.services.runtime_env import is_production_environment

    status = str(bank.get("status") or "")
    if is_production_environment():
        return status == "signed"
    return status in {"signed", "candidate"}


def _std_decks(manifest_dir: Path) -> list[dict[str, Any]]:
    """标准卡按章成组: [{pack_id: STD01.., title, cards}]（旗标关/文件缺失=空）。"""
    if not _std_enabled():
        return []
    path = manifest_dir / _STD_BANK_NAME
    if not path.exists():
        return []
    import json as _json

    try:
        bank = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if str(bank.get("tier") or "") != "standard":
        return []
    if not _std_status_ok(bank):
        return []
    chapters: dict[str, list[dict[str, Any]]] = {}
    for card in bank.get("cards") or []:
        if not isinstance(card, dict):
            continue
        chapters.setdefault(str(card.get("chapter") or "综合高频"), []).append(card)
    decks = []
    for i, (title, cards) in enumerate(sorted(chapters.items()), start=1):
        decks.append(
            {
                "pack_id": f"{_STD_PREFIX}{i:02d}",
                "title": title,
                "cards": cards,
            }
        )
    return decks


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
    packs = sorted(packs, key=lambda p: p["pack_id"])
    for deck in _std_decks(manifest_dir):
        packs.append(
            {
                "pack_id": deck["pack_id"],
                "title": deck["title"],
                "card_count": len(deck["cards"]),
                "tier": "standard",
            }
        )
        total += len(deck["cards"])
    return {"total": total, "packs": packs}


def build_concept_cards(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单站考点卡投影（翻卡页数据）；不过任一道闸一律 LessonNotAvailable。"""
    pack_id = str(pack_id or "").strip().upper()
    manifest = _load_manifest(manifest_path)
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    if pack_id.startswith(_STD_PREFIX):
        deck = next(
            (d for d in _std_decks(manifest_dir) if d["pack_id"] == pack_id), None
        )
        if deck is None:
            raise LessonNotAvailable(pack_id)
        return {
            "pack_id": pack_id,
            "title": deck["title"],
            "tier": "standard",
            "card_count": len(deck["cards"]),
            "cards": [
                {
                    "card_id": str(c.get("card_id") or ""),
                    "front": str(c.get("front") or ""),
                    "key_gist": str(c.get("key_gist") or ""),
                    "quote": str(c.get("quote") or ""),
                    "point_id": str(c.get("point_id") or ""),
                    "source_ref": c.get("source_ref") or {},
                    "scoring_terms": c.get("scoring_terms") or [],
                }
                for c in deck["cards"]
            ],
        }
    green = set(manifest.get("projection_green") or [])
    if pack_id not in green:
        raise LessonNotAvailable(pack_id)
    pack = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id),
        None,
    )
    if pack is None:
        raise LessonNotAvailable(pack_id)
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
                # v32 采分点富化(2026-07-12): 阅卷认的词, 编译期签发, 此处只透传
                "scoring_terms": c.get("scoring_terms") or [],
            }
            for c in cards
        ],
    }
