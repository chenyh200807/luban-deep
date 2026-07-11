"""F16 看穿(seethrough)5 天内容只读投影(深母题 schema v2 的 runtime 消费者)。

Thin 投影层,与 ``concept_cards.py`` / ``read_model.py`` 同一纪律:
- 看穿真值 = 编译期签发的 ``_{pack_id}_seethrough_bank.v0.json``
  (``scripts/build_luban_seethrough_bank.py`` 确定性派生自逐字转录的剧本 spike
  源 ``_F16_seethrough_source.json`` + gate;本模块零生成、零改写、零新造);
- 签发闸复用 ``read_model._load_signed_bank``(signed + source_pack_sha256 双
  fail-closed,单一 loader authority)——candidate 未签发 / pack 修订后 sha 漂移 /
  文件缺失,一律与 bank 缺失同形不可见;
- 只投影 manifest 绿灯包(与 lesson 同一门);
- **零写入**:5 天推进 / 答题证据由 program-progress 机制 + learner_signal /
  判分链路承担,掌握态唯一权威仍是判分链路 + revalidation_queue,本模块不碰。

诚实边界(随 bank item 投影,不在此新造):Day4 半写为已签发 Q18 P10/P11 采分点
文本的自我核对投影(training_org 估分口径·非官方阅卷),``honesty_label`` 随题下发;
Day2/Day5 迎水面为诚实延伸(``evidence.syllabus_chunks[].is_extension=true`` +
``true_source_pack``),学员端呈现"从屋面延伸到地下室,同一控水原则"。
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

_SEETHROUGH_BANK_TEMPLATE = "_{pack_id}_seethrough_bank.v0.json"


def _signed_items(
    pack: dict[str, Any], manifest_dir: Path
) -> list[dict[str, Any]] | None:
    bank = _load_signed_bank(
        str(pack.get("pack_id") or ""),
        manifest_dir,
        str(pack.get("content_sha256") or ""),
        filename_template=_SEETHROUGH_BANK_TEMPLATE,
    )
    if bank is None:
        return None
    items = [i for i in bank.get("items") or [] if isinstance(i, dict)]
    return items or None


def build_seethrough_library(*, manifest_path: Path | None = None) -> dict[str, Any]:
    """看穿库总览投影(哪些绿灯包有签发看穿 5 天内容 + 天数真值)。

    只数 manifest 绿灯 ∧ signed+sha 双闸通过的 bank;一个都没有 →
    ``total=0, packs=[]``(前端据此保持诚实占位)。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    packs: list[dict[str, Any]] = []
    total = 0
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        items = _signed_items(pack, manifest_dir)
        if items is None:
            continue
        packs.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "day_count": len(items),
            }
        )
        total += len(items)
    return {"total": total, "packs": sorted(packs, key=lambda p: p["pack_id"])}


def build_seethrough(pack_id: str, *, manifest_path: Path | None = None) -> dict[str, Any]:
    """单站看穿 5 天内容投影(program 消费:今日一刀→表皮试探→透视揭底→暖纠正→明日约定)。

    不过任一道闸一律 ``LessonNotAvailable``(fail-closed,不泄漏未签发存在性)。
    items 已是签发形状(表皮试探 4 选 1 + 透视揭底 4 段 + 暖纠正 + 定位证据带延伸标注),
    本模块只投影、不改写。
    """
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
    items = _signed_items(pack, manifest_dir)
    if items is None:
        raise LessonNotAvailable(pack_id)
    return {
        "pack_id": pack_id,
        "title": str(pack.get("title") or ""),
        "day_count": len(items),
        "days": sorted(items, key=lambda i: int(i.get("day") or 0)),
    }


__all__ = ["build_seethrough_library", "build_seethrough"]
