"""R8 解药库只读投影（复习二期错因银行「解药位」消费，双轮 v3.2 §6.2）。

Thin 投影层，与 ``read_model.py`` / ``concept_cards.py`` 同一纪律：
- 解药真值 = 编译期签发的 ``_{pack_id}_r8_antidote_bank.v0.json``
  （``scripts/build_luban_r8_antidote_bank.py`` 确定性派生自签发 pack §6
  「R8 误区 → error_code → 解药」；本模块零生成、零改写）；
- 签发闸复用 ``read_model._load_signed_bank``（signed + source_pack_sha256
  双 fail-closed，单一 loader authority）——candidate 未签发 / pack 修订后
  sha 漂移 / 文件缺失，一律与 bank 缺失同形不可见；
- 只投影 manifest 绿灯包（与 lesson 同一门）；
- **零写入**：错因记账真值只归判分内核 writeback，本模块不提供任何写路径。

诚实边界（v3 §6 护城河口径）：解药是教研 authored **🔵 讲懂用语**，忠实门只到
signed-pack 级（error_code∈registry + kc: 锚 resolve + 三色门），**不是**逐字教材
quote；本模块不声称「答案绝对正确」，只如实透传 mental_model / textbook_ref。

消费接口（errorbank vm head note 钉死的形状，供给逐字对齐）：
请求 ``{pack_id, error_code}`` → 响应 ``{mental_model, textbook_ref}``。
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

_ANTIDOTE_BANK_TEMPLATE = "_{pack_id}_r8_antidote_bank.v0.json"


def _signed_antidotes(
    pack: dict[str, Any], manifest_dir: Path
) -> dict[str, list[dict[str, Any]]] | None:
    bank = _load_signed_bank(
        str(pack.get("pack_id") or ""),
        manifest_dir,
        str(pack.get("content_sha256") or ""),
        filename_template=_ANTIDOTE_BANK_TEMPLATE,
    )
    if bank is None:
        return None
    antidotes = bank.get("antidotes")
    if not isinstance(antidotes, dict):
        return None
    cleaned = {
        str(code): [a for a in rows if isinstance(a, dict)]
        for code, rows in antidotes.items()
        if isinstance(rows, list)
    }
    cleaned = {code: rows for code, rows in cleaned.items() if rows}
    return cleaned or None


def build_antidote_library(
    *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """解药库总览投影（错因银行资产入口的「解药覆盖」真值）。

    只数 manifest 绿灯 ∧ signed+sha 双闸通过的 bank；一个都没有 →
    ``total=0, packs=[]``（错因银行据此保持「解药整理中」诚实占位）。
    ``total`` = 各包 error_code→解药条目总数。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    packs = []
    total = 0
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        antidotes = _signed_antidotes(pack, manifest_dir)
        if antidotes is None:
            continue
        count = sum(len(rows) for rows in antidotes.values())
        packs.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "error_codes": sorted(antidotes),
                "antidote_count": count,
            }
        )
        total += count
    return {"total": total, "packs": sorted(packs, key=lambda p: p["pack_id"])}


def build_antidote(
    pack_id: str, error_code: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单条解药投影（错因银行 detail 页 `{pack_id, error_code}` 消费）；
    不过任一道闸 / 该码无解药一律 LessonNotAvailable（与占位同形）。"""
    pack_id = str(pack_id or "").strip().upper()
    error_code = str(error_code or "").strip()
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
    antidotes = _signed_antidotes(pack, manifest_dir)
    if antidotes is None:
        raise LessonNotAvailable(pack_id)
    rows = antidotes.get(error_code) or []
    if not rows:
        raise LessonNotAvailable(pack_id)
    row = rows[0]
    # 签发内容全字段投影(2026-07-12: phenomenon/wrong_model 此前被丢弃=消费不足;
    # 同码多条全部返回, 首条字段保持向后兼容的顶层键)。
    def _proj(r: dict) -> dict:
        return {
            "mental_model": str(r.get("mental_model") or ""),
            "phenomenon": str(r.get("phenomenon") or ""),
            "wrong_model": str(r.get("wrong_model") or ""),
            "textbook_ref": str(r.get("textbook_ref") or ""),
        }
    return {
        "pack_id": pack_id,
        "error_code": error_code,
        "mental_model": str(row.get("mental_model") or ""),
        "textbook_ref": str(row.get("textbook_ref") or ""),
        "items": [_proj(r) for r in rows],
    }
