"""R6 精确挖空库只读投影（复习二期实务闯关②「半写」消费，双轮 v3.2 §6.3）。

Thin 投影层，与 ``read_model.py`` / ``concept_cards.py`` 同一纪律：
- 挖空真值 = 编译期签发的 ``_{pack_id}_r6_cloze_bank.v0.json``
  （``scripts/build_luban_r6_cloze_bank.py`` 确定性派生自签发 pack §5.1 R5
  采分点表 + required_terms 字面挖空；本模块零生成、零改写）；
- 签发闸复用 ``read_model._load_signed_bank``（signed + source_pack_sha256
  双 fail-closed，单一 loader authority）——candidate 未签发 / sha 漂移 /
  文件缺失，一律与 bank 缺失同形不可见；
- 只投影 manifest 绿灯包（与 lesson 同一门）；
- **零写入**：漏点/命中只做呈现层暖反馈，错因记账真值只归判分内核 writeback。

消费接口（gauntlet vm head note 钉死的形状，供给逐字对齐）：
请求 ``{pack_id}`` → 响应
``{skeleton_sentences:[{text_before, blank_hint, text_after}], recall_prompt}``。
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

_CLOZE_BANK_TEMPLATE = "_{pack_id}_r6_cloze_bank.v0.json"


def _signed_cloze(
    pack: dict[str, Any], manifest_dir: Path
) -> dict[str, Any] | None:
    bank = _load_signed_bank(
        str(pack.get("pack_id") or ""),
        manifest_dir,
        str(pack.get("content_sha256") or ""),
        filename_template=_CLOZE_BANK_TEMPLATE,
    )
    if bank is None:
        return None
    sentences = [
        s for s in bank.get("skeleton_sentences") or [] if isinstance(s, dict)
    ]
    if not sentences:
        return None
    return {
        "skeleton_sentences": sentences,
        "recall_prompt": str(bank.get("recall_prompt") or ""),
    }


def build_cloze_library(
    *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """挖空库总览投影（实务闯关资产入口的「精确挖空覆盖」真值）。

    只数 manifest 绿灯 ∧ signed+sha 双闸通过的 bank；一个都没有 →
    ``total=0, packs=[]``（实务闯关据此保持「精确挖空准备中」诚实占位）。
    ``total`` = 各包挖空句总数。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    packs = []
    total = 0
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        cloze = _signed_cloze(pack, manifest_dir)
        if cloze is None:
            continue
        count = len(cloze["skeleton_sentences"])
        packs.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "cloze_count": count,
            }
        )
        total += count
    return {"total": total, "packs": sorted(packs, key=lambda p: p["pack_id"])}


def build_cloze(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单站挖空投影（实务闯关半写数据）；不过任一道闸一律 LessonNotAvailable。"""
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
    cloze = _signed_cloze(pack, manifest_dir)
    if cloze is None:
        raise LessonNotAvailable(pack_id)
    return {
        "pack_id": pack_id,
        "title": str(pack.get("title") or ""),
        "recall_prompt": cloze["recall_prompt"],
        "skeleton_sentences": [
            {
                "cloze_id": str(s.get("cloze_id") or ""),
                "point_id": str(s.get("point_id") or ""),
                "text_before": str(s.get("text_before") or ""),
                "blank_hint": str(s.get("blank_hint") or ""),
                "text_after": str(s.get("text_after") or ""),
            }
            for s in cloze["skeleton_sentences"]
        ],
    }
