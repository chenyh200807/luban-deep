#!/usr/bin/env python3
"""构建深母题 Pack 机器可读 manifest（luban_deep_pack_manifest.v0）。

背景（双轮设计 v3.2 §7 / Codex 对抗采信）：成品目录 41 个 Pack 的签发状态
全是散文 blockquote，无机器可读字段——投影门（signed+published+jury-clean）
无从判定。本脚本做**纯确定性提取**（零 LLM），产出唯一 manifest：

- ``published`` 默认恒 False：签发是人的裁决，脚本只登记、绝不代签
  （防"库建好没通电"与"脚本自签发"两个历史坑）。
- 人工签发 = 在 ``_pack_manifest.overrides.json`` 里对具体 pack_id 置
  ``published: true``；本脚本重跑时合并 overrides，其余字段永远以扫描为准。
  只有 owner 明确要求将已完成成品接入默认学习入口时，才可额外置
  ``allow_default_entry: true``。该动作会保留扫描到的原始 barrier，并记录为
  ``source_explicitly_barred_default_entry`` + ``default_entry_override``，不把
  人工放行伪装成源材料从未设限。
- ``jury_clean`` = jury sidecar 存在且**无未解决的高可信 issue**（双轮设计 §7
  投影门③「jury issue 已 fix 或不涉该簇」的机器可读载体）：解决状态由人工/汇编
  在 jury sidecar 行内登记 ``resolution: {status: fixed|not_applicable, fixed_in,
  verified}``，本脚本只确定性读取、不做语义裁决；无 resolution 的高可信 issue
  一律计为未解决（fail-closed）。
- 消费侧（投影门）只认本 manifest 绿灯：``published and jury_clean and
  not explicitly_barred_default_entry``。

用法::

    python3 scripts/build_luban_pack_manifest.py          # 生成/刷新
    python3 scripts/build_luban_pack_manifest.py --check  # CI 校验(漂移即非0退出)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PACK_DIR = REPO / "docs" / "原始数据" / "考点原料" / "成品"
CARD_HOST_DIR = REPO / "web" / "public" / "luban-preview"  # 讲懂卡托管目录(确定性扫描)
PRACTICE_AUTHORITY_DIR = REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
MANIFEST_PATH = PACK_DIR / "_pack_manifest.json"
OVERRIDES_PATH = PACK_DIR / "_pack_manifest.overrides.json"

SCHEMA_NAME = "luban_deep_pack_manifest.v0"
_PACK_FILE_RE = re.compile(r"^([A-Z]\d{2})_(?!.*作答层样板)(.+)\.md$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_RESOLVED_STATUSES = {"fixed", "not_applicable"}


def _is_resolved(row: dict[str, Any]) -> bool:
    resolution = row.get("resolution")
    return isinstance(resolution, dict) and resolution.get("status") in _RESOLVED_STATUSES


def _jury_stats(pack_id: str) -> dict[str, Any]:
    path = PACK_DIR / f"_{pack_id}_jury.json"
    if not path.exists():
        return {
            "jury_file": False,
            "jury_total": 0,
            "jury_high_confidence": 0,
            "jury_high_confidence_unresolved": 0,
        }
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "jury_file": True,
            "jury_total": -1,
            "jury_high_confidence": -1,
            "jury_high_confidence_unresolved": -1,
        }
    if not isinstance(rows, list):
        rows = []
    high_rows = [r for r in rows if isinstance(r, dict) and r.get("confidence") == "高可信"]
    unresolved = sum(1 for r in high_rows if not _is_resolved(r))
    return {
        "jury_file": True,
        "jury_total": len(rows),
        "jury_high_confidence": len(high_rows),
        "jury_high_confidence_unresolved": unresolved,
    }


def _companion_exists(pack_id: str, suffix: str) -> bool:
    # 配套件分布在成品目录与其上级挖矿目录两处, 只查成品会漏报(S05 实证)
    name = f"_{pack_id}_{suffix}"
    return (PACK_DIR / name).exists() or (PACK_DIR.parent / name).exists()


def _practice_capability(pack_id: str, content_sha256: str) -> dict[str, Any]:
    """Sidecar 是 finished HTML 的可验证运行时投影，此处只登记已闭合的产物。"""
    filename = f"{pack_id.lower()}.practice.authority.json"
    path = PRACTICE_AUTHORITY_DIR / filename
    try:
        authority = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unavailable"}
    surfaces = authority.get("surfaces") if isinstance(authority, dict) else None
    items = authority.get("items") if isinstance(authority, dict) else None
    public = CARD_HOST_DIR / pack_id.lower()
    if (
        authority.get("schema_version") != "luban_compiled_practice.v1"
        or authority.get("pack_id") != pack_id
        or authority.get("source_pack_sha256") != content_sha256
        or not isinstance(surfaces, list)
        or not surfaces
        or not isinstance(items, list)
        or len(items) != 5 * len(surfaces)
        or authority.get("published_lesson_sha256")
        != (_sha256(public / "lesson.html") if (public / "lesson.html").is_file() else "")
    ):
        return {"status": "unavailable"}
    for surface in surfaces:
        hosted = public / str(surface.get("surface_id") or "")
        if (
            not hosted.is_file()
            or surface.get("published_practice_sha256") != _sha256(hosted)
            or len(surface.get("variant_ids") or []) != 5
        ):
            return {"status": "unavailable"}
    return {
        "status": "compiled",
        "authority_path": filename,
        "source_pack_sha256": content_sha256,
        "source_bundle_sha256": str(authority.get("source_bundle_sha256") or ""),
        "surface_count": len(surfaces),
        "question_count": len(items),
        "writeback_contract": "luban_retest_completion.v1",
    }


def _scan_pack(path: Path, pack_id: str, title: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    jury = _jury_stats(pack_id)
    coarse = "coarse_review" in text
    needs_leaf = "needs_leaf_review" in text
    barred = bool(re.search(r"不进(学员)?默认(学习)?入口", text)) or needs_leaf
    content_sha256 = _sha256(path)
    entry: dict[str, Any] = {
        "pack_id": pack_id,
        "title": title,
        "file": path.name,
        "content_sha256": content_sha256,
        # 状态信号(确定性提取, 不做语义裁决)
        "review_level": "coarse_review" if coarse else "standard",
        "needs_leaf_review": needs_leaf,
        "explicitly_barred_default_entry": barred,
        "red_marker_count": text.count("🔴"),
        # 配套件存在性
        "has_compiled_source": _companion_exists(pack_id, "compiled_source.json"),
        "has_exam_evidence": _companion_exists(pack_id, "exam_evidence.json"),
        "has_answer_layer": any(PACK_DIR.glob(f"{pack_id}_*作答层样板.md")),
        # 讲懂卡托管存在性(确定性: web/public/luban-preview/<id小写>/lesson.html 实存)
        # read_model 只对 card_hosted 的绿灯站派生 card_url——防 22 站 web-view 404(2026-07-05 部署探针实证)
        "card_hosted": (CARD_HOST_DIR / pack_id.lower() / "lesson.html").is_file(),
        "practice": _practice_capability(pack_id, content_sha256),
        **jury,
        # 签发态: 脚本恒 False, 只能经 overrides 人工置 true
        "published": False,
    }
    entry["jury_clean"] = (
        bool(jury["jury_file"]) and jury["jury_high_confidence_unresolved"] == 0
    )
    return entry


def _apply_overrides(packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not OVERRIDES_PATH.exists():
        return packs
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    if not isinstance(overrides, dict):
        raise ValueError("overrides 必须是 {pack_id: {published: bool}} 形状")
    by_id = {p["pack_id"]: p for p in packs}
    for pack_id, patch in overrides.items():
        if pack_id not in by_id:
            raise ValueError(f"override 指向不存在的 pack: {pack_id}")
        if not isinstance(patch, dict) or set(patch) - {"published", "allow_default_entry", "note"}:
            raise ValueError(f"override 只允许 published/allow_default_entry/note 字段: {pack_id}")
        by_id[pack_id]["published"] = bool(patch.get("published", False))
        if "allow_default_entry" in patch:
            source_barred = bool(by_id[pack_id]["explicitly_barred_default_entry"])
            allow_default_entry = bool(patch["allow_default_entry"])
            by_id[pack_id]["source_explicitly_barred_default_entry"] = source_barred
            by_id[pack_id]["default_entry_override"] = allow_default_entry
            if allow_default_entry:
                by_id[pack_id]["explicitly_barred_default_entry"] = False
        if patch.get("note"):
            by_id[pack_id]["publish_note"] = str(patch["note"])
    return packs


_SUPERSEDED_RE = re.compile(r"_v\d+model$")


def build_manifest() -> dict[str, Any]:
    packs = []
    superseded: list[str] = []
    for path in sorted(PACK_DIR.iterdir()):
        m = _PACK_FILE_RE.match(path.name)
        if not m:
            continue
        if _SUPERSEDED_RE.search(m.group(2)):
            # 旧版草稿(如 Q03_*_v4model): 不进 manifest 主体, 但透明登记不静默丢
            superseded.append(path.name)
            continue
        packs.append(_scan_pack(path, m.group(1), m.group(2)))
    packs = _apply_overrides(packs)
    green = [p["pack_id"] for p in packs
             if p["published"] and p["jury_clean"] and not p["explicitly_barred_default_entry"]]
    return {
        "schema": SCHEMA_NAME,
        "pack_dir": str(PACK_DIR.relative_to(REPO)),
        "pack_count": len(packs),
        "superseded_files": superseded,
        "projection_green": green,
        "packs": packs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="校验 manifest 与磁盘一致(CI 漂移闸)")
    args = parser.parse_args()
    manifest = build_manifest()
    rendered = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.check:
        if not MANIFEST_PATH.exists() or MANIFEST_PATH.read_text(encoding="utf-8") != rendered:
            print("pack-manifest-gate: DRIFT — 运行 scripts/build_luban_pack_manifest.py 刷新", file=sys.stderr)
            return 1
        print(f"pack-manifest-gate: passed | packs={manifest['pack_count']} green={len(manifest['projection_green'])}")
        return 0
    MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    print(f"written {MANIFEST_PATH.relative_to(REPO)} | packs={manifest['pack_count']} "
          f"green={manifest['projection_green'] or '无(全部未签发,符合当前真实状态)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
