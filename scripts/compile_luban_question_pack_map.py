"""§6-5 题→pack 映射编译（确定性，可重跑零漂移）。

从 37 份 ``docs/原始数据/考点原料/_<ID>_exam_evidence.json`` 编译
「真题 chunk_id → pack」确定性映射：evidence 的（年份, 题号）经归一后
join 题库 ``FINAL_CLEANED_EXAM_V<year>.json`` 的
``(exam_year, original_anchor) → chunk_id`` 索引。

匹配不上的条目**如实落「未归位」清单，禁止硬塞**（计划 §2.4 兜底③）。

用法::

    python scripts/compile_luban_question_pack_map.py \
        [--bank-root /path/to/2026_副本/题库]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "docs/原始数据/考点原料"
OUTPUT_JSON = REPO_ROOT / "docs/原始数据/考点原料/成品/_question_pack_map.v0.json"
UNMATCHED_MD = REPO_ROOT / "docs/原始数据/考点原料/待归位-题到pack映射未匹配清单.md"
# 题库快照收进 repo（11 个年卷共 3.3MB，与已 tracked 的 37 份 exam_evidence
# 同级体量）：确定性重跑测试在任何 full checkout / CI 上都能真跑，
# 不再依赖盘外数据（原盘外路径仍可用 --bank-root 覆盖）。
DEFAULT_BANK_ROOT = REPO_ROOT / "docs/原始数据/考点原料/题库快照"

_CN_DIGITS = {
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
    "十一": "11", "十二": "12", "十三": "13", "十四": "14", "十五": "15",
    "十六": "16", "十七": "17", "十八": "18", "十九": "19", "二十": "20",
}


def normalize_anchor(raw: str) -> str:
    """题号归一：全角→半角、中文数字案例号→阿拉伯、去空白。"""
    text = str(raw or "").strip()
    text = text.translate(str.maketrans("０１２３４５６７８９（）", "0123456789()"))
    text = re.sub(r"\s+", "", text)
    case_match = re.match(r"^案例[（(]?([一二三四五六七八九十0-9]+)[）)]?$", text)
    if case_match:
        num = case_match.group(1)
        num = _CN_DIGITS.get(num, num)
        return f"案例{num}"
    question_match = re.match(r"^第?([0-9]+)题?$", text)
    if question_match:
        return f"第{question_match.group(1)}题"
    return text


def _bank_files(bank_root: Path) -> list[Path]:
    """题库年卷文件（扁平快照目录 + 兼容旧的按年子目录结构）。"""
    return sorted(
        {
            *bank_root.glob("FINAL_CLEANED_EXAM_V*.json"),
            *bank_root.glob("*/FINAL_CLEANED_EXAM_V*.json"),
        }
    )


def build_sources_section(bank_root: Path) -> list[dict[str, Any]]:
    """产物溯源段：每个源年卷的 relpath + sha256 + chunk 数。

    hash 的核验路径与写入路径解耦：CI/独立核验者直接对快照文件重算
    sha256 对照本段（非自证）——见 tests/scripts/test_luban_question_pack_map.py。"""
    sources: list[dict[str, Any]] = []
    for path in _bank_files(bank_root):
        raw = path.read_bytes()
        try:
            chunk_count = len(json.loads(raw).get("chunks") or [])
        except Exception:
            chunk_count = 0
        try:
            relpath = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relpath = path.as_posix()
        sources.append(
            {
                "relpath": relpath,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "chunk_count": chunk_count,
            }
        )
    return sources


def load_bank_index(bank_root: Path) -> dict[tuple[str, str], list[str]]:
    """(year, normalized_anchor) -> ["year:chunk_id", ...]。

    题库 chunk_id 跨年**不唯一**（2022/2023/2024 均有
    EXAM_1A411001_P0001_01），所以映射条目一律用 ``year:chunk_id``
    复合键。同一案例可按分问拆成多个 chunk（2017 案例一 = P0009_01 +
    P0010_04），因此 (year, anchor) 合法一对多。"""
    index: dict[tuple[str, str], list[str]] = {}
    for path in _bank_files(bank_root):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for chunk in payload.get("chunks") or []:
            meta = chunk.get("source_meta") or {}
            year = str(meta.get("exam_year") or "").strip()
            anchor = normalize_anchor(meta.get("original_anchor") or "")
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            if not (year and anchor and chunk_id):
                continue
            bucket = index.setdefault((year, anchor), [])
            qualified = f"{year}:{chunk_id}"
            if qualified not in bucket:
                bucket.append(qualified)
    return index


def compile_map(bank_root: Path) -> dict:
    bank_index = load_bank_index(bank_root)
    packs: dict[str, dict] = {}
    for path in sorted(EVIDENCE_DIR.glob("_*_exam_evidence.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        pack_id = str(payload.get("考点") or path.name.split("_")[1]).strip()
        if pack_id in packs:
            raise SystemExit(f"duplicate pack_id {pack_id!r} across exam_evidence files")
        linked: set[str] = set()
        ambiguous: list[dict] = []
        unmatched: list[dict] = []
        for item in payload.get("evidence") or []:
            year = str(item.get("year") or "").strip()
            anchor_raw = str(item.get("题号") or "").strip()
            anchor = normalize_anchor(anchor_raw)
            hits = bank_index.get((year, anchor)) or []
            if not hits:
                unmatched.append({"year": year, "题号": anchor_raw, "normalized": anchor})
            elif len(hits) == 1 or re.match(r"^案例\d+$", anchor):
                # 唯一命中，或案例按分问合法拆成多 chunk（如 2017 案例一）。
                linked.update(hits)
            else:
                # '问题1' 等弱锚同年命中多个不同案例 chunk = 真歧义，
                # 如实落 ambiguous 待教研裁决，禁止硬塞进 linked。
                ambiguous.append(
                    {"year": year, "题号": anchor_raw, "normalized": anchor, "candidates": sorted(hits)}
                )
        packs[pack_id] = {
            "evidence_file": path.name,
            "linked_question_ids": sorted(linked),
            "ambiguous": ambiguous,
            "unmatched": unmatched,
        }
    reverse: dict[str, list[str]] = {}
    for pack_id, entry in packs.items():
        for chunk_id in entry["linked_question_ids"]:
            reverse.setdefault(chunk_id, []).append(pack_id)
    reverse = {key: sorted(value) for key, value in sorted(reverse.items())}
    return {
        "schema": "luban_question_pack_map.v0",
        "authority_note": (
            "题→pack 确定性映射，编译自 exam_evidence（年份+题号）join 题库 chunk 索引；"
            "只作学情 join/生命周期投影用，不充判分 authority。未匹配项如实在 unmatched，禁止硬塞。"
        ),
        "question_key_format": "year:chunk_id（题库 chunk_id 跨年不唯一，必须带年份限定）",
        "sources": build_sources_section(bank_root),
        "packs": packs,
        "reverse_index": reverse,
    }


def _write_unmatched_md(compiled: dict) -> tuple[int, int]:
    unmatched_lines: list[str] = []
    ambiguous_lines: list[str] = []
    for pack_id, entry in sorted(compiled["packs"].items()):
        for item in entry["unmatched"]:
            unmatched_lines.append(
                f"| {pack_id} | {item['year']} | {item['题号']} | `{item['normalized']}` |"
            )
        for item in entry["ambiguous"]:
            candidates = "、".join(f"`{c}`" for c in item["candidates"])
            ambiguous_lines.append(
                f"| {pack_id} | {item['year']} | {item['题号']} | {candidates} |"
            )
    body = "\n".join(
        [
            "# 待归位 — 题→pack 映射未匹配/歧义清单（如实报告，禁硬塞）",
            "",
            "> 来源：`scripts/compile_luban_question_pack_map.py`。",
            "> 处置归教研：确认真实对应题后在 exam_evidence 修题号（写明案例号），再重跑编译。",
            "",
            "## 1. 未匹配（题库无对应 anchor）",
            "",
            "| Pack | 年份 | 原题号 | 归一后 |",
            "|---|---|---|---|",
            *(unmatched_lines or ["| （无未匹配项） | | | |"]),
            "",
            "## 2. 歧义（'问题N'/'答案' 等弱锚同年命中多个不同 chunk，未收进 linked）",
            "",
            "| Pack | 年份 | 原题号 | 候选 chunk |",
            "|---|---|---|---|",
            *(ambiguous_lines or ["| （无歧义项） | | | |"]),
            "",
        ]
    )
    UNMATCHED_MD.write_text(body, encoding="utf-8")
    return len(unmatched_lines), len(ambiguous_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-root", type=Path, default=DEFAULT_BANK_ROOT)
    args = parser.parse_args()
    if not args.bank_root.exists():
        raise SystemExit(f"question bank root not found: {args.bank_root}")
    compiled = compile_map(args.bank_root)
    OUTPUT_JSON.write_text(
        json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unmatched_total, ambiguous_total = _write_unmatched_md(compiled)
    matched_total = sum(len(entry["linked_question_ids"]) for entry in compiled["packs"].values())
    print(
        f"compiled {len(compiled['packs'])} packs: {matched_total} linked question chunks, "
        f"{unmatched_total} unmatched, {ambiguous_total} ambiguous -> {UNMATCHED_MD.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
