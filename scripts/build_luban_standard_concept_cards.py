#!/usr/bin/env python3
"""标准考点卡编译器（二梯队量产 spike · 2026-07-12 owner拍板三件事之①）。

供给链: RichLeaf v3.2 采分点富化层(quote_verified 教材溯源) × 11年真题考频
(FINAL_CLEANED_EXAM node_code 实证计数, 方向性口径) → Top-N 叶标准卡。

与精品卡(考点原料 pack 手工打样+人闸)的关系——**双梯队,明示分层不冒充**:
- 精品卡: 17 站 pack 签发, promote 人闸, tier 缺省;
- 标准卡: 本编译器全自动产出, status=candidate, tier="standard";
  后端只在 LUBAN_STD_CONCEPT_CARDS_ENABLED 且非生产时投影(owner 过目
  打样后再谈签发口径)——签发纪律不为量产让步。

四闸(fail-closed, 与精品同源):
① 只收 provenance.quote_verified=True 且 source_authority=textbook 的采分点;
② quote 复核: chunk 在教材权威库时, 归一后必须逐字 ⊂ chunk 全文(不信任传递);
③ 禁审视词(共享 FORBIDDEN_WORDS 口径);
④ front 去重 + 每叶 ≤2 组给分词。
"""
from __future__ import annotations

import argparse
import functools
import glob
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

V32_PACK = (
    REPO / "artifacts" / "luban_grading_artifacts"
    / "rich_leaf_v32_scoring_point_compile_20260613"
    / "runtime_token_pack_v32_scoring_points.json"
)
EXAM_GLOB = str(REPO / "docs" / "原始数据" / "2026_副本" / "题库" / "*真题*" / "FINAL_CLEANED_EXAM_V2*.json")
TAXONOMY_PATH = REPO / "deeptutor" / "services" / "taxonomy" / "compiled" / "construction_2026_taxonomy.compiled.json"
TEXTBOOK_DIR = REPO / "docs" / "原始数据" / "2026_副本" / "2026教材" / "第二次加强"
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_STD_concept_card_bank.v0.json"

SCHEMA_NAME = "luban-standard-concept-card-bank"
# 与精品卡同口径的禁审视词(文案铁律)
FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")

_NORM_STRIP_RE = re.compile(r"[\s　]+")


def _norm(text: str) -> str:
    return _NORM_STRIP_RE.sub("", str(text or ""))


@functools.lru_cache(maxsize=1)
def _textbook_index() -> dict[str, dict[str, Any]]:
    """chunk_id → {md, page}（教材权威库; 缺席=空索引, quote 复核降级跳过并记账）。"""
    index: dict[str, dict[str, Any]] = {}
    if not TEXTBOOK_DIR.exists():
        return index
    for path in sorted(TEXTBOOK_DIR.glob("FINAL_CLEANED_BOOK2026*fixed.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("content_blocks") or []:
            cid = str(chunk.get("chunk_id") or "")
            if cid and cid not in index:
                meta = chunk.get("source_meta") or chunk.get("metadata") or {}
                index[cid] = {
                    "md": str(chunk.get("content_markdown") or ""),
                    "page": meta.get("page_num") or meta.get("page") or chunk.get("page_num"),
                }
    return index


@functools.lru_cache(maxsize=1)
def _chapter_names() -> dict[str, str]:
    """章 code(前5位+000) → 名称（taxonomy 编译版二级节点权威）。"""
    if not TAXONOMY_PATH.exists():
        return {}
    data = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    nodes = data.get("nodes") if isinstance(data, dict) else data
    out: dict[str, str] = {}
    for node in nodes or []:
        code = str(node.get("code") or "")
        if node.get("level") == 2 and code:
            out[code] = str(node.get("name") or code)
    return out


def _chapter_of(leaf_code: str) -> str:
    names = _chapter_names()
    code = leaf_code[:5] + "000" if len(leaf_code) >= 5 else leaf_code
    return names.get(code, "综合高频")


def _exam_frequency() -> dict[str, int]:
    """node_code 前缀 → 加权题数(案例×2+选择×1)。方向性口径(数据盘点 2026-06-16)。"""
    freq: dict[str, int] = {}
    for path in sorted(glob.glob(EXAM_GLOB)):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for chunk in data.get("chunks") or []:
            code = str((chunk.get("taxonomy") or {}).get("node_code") or "").rstrip("0")
            if not code:
                continue
            for ex in chunk.get("exercises") or []:
                weight = 2 if str(ex.get("type") or "") == "case_study" else 1
                freq[code] = freq.get(code, 0) + weight
    return freq


def _leaf_score(leaf_code: str, freq: dict[str, int]) -> int:
    """叶考频 = 所有是其前缀的 node_code 计数之和。"""
    total = 0
    for code, n in freq.items():
        if leaf_code.startswith(code):
            total += n
    return total


def _dedupe_term_sets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """跨点给分词去重: 第二组剔除与第一组重复的词, 剔空则整组弃(呈现层不重复喊)。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        terms = [t for t in r["terms"] if t not in seen]
        if not terms:
            continue
        seen.update(terms)
        out.append(
            {
                "statement": str(r["point"].get("statement") or ""),
                "required_terms": terms,
                "point_id": str(r["point"].get("point_id") or ""),
            }
        )
    return out


def build_payload(top_n: int) -> dict[str, Any]:
    t0 = time.perf_counter()
    if not V32_PACK.exists():
        raise SystemExit(f"v32 pack 缺席: {V32_PACK}（本编译器只在有编译资产的机器上跑）")
    v32_bytes = V32_PACK.read_bytes()
    v32 = json.loads(v32_bytes)
    units = v32.get("runtime_token_pack_units") or []
    freq = _exam_frequency()
    textbook = _textbook_index()

    ranked: list[tuple[int, dict[str, Any]]] = []
    for unit in units:
        leaf_code = str(unit.get("leaf_id") or "").split("-")[0]
        verified = []
        for point in (unit.get("compiled_context") or {}).get("scoring_points") or []:
            prov = point.get("provenance") or {}
            if prov.get("quote_verified") is not True:
                continue
            if str(prov.get("source_authority") or "") != "textbook":
                continue
            terms = [str(t) for t in (point.get("required_terms") or []) if str(t).strip()]
            quote = str(prov.get("quote") or "").strip()
            if not terms or not quote:
                continue
            verified.append({"point": point, "terms": terms, "quote": quote})
        if not verified or not leaf_code:
            continue
        ranked.append((_leaf_score(leaf_code, freq), unit | {"_verified": verified}))
    ranked.sort(key=lambda x: (-x[0], str(x[1].get("leaf_id"))))

    cards: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen_front: set[str] = set()
    quote_recheck_skipped = 0
    for score, unit in ranked:
        if len(cards) >= top_n:
            break
        path_parts = [p.strip() for p in str(unit.get("leaf_name_path") or "").split(">")]
        front = path_parts[-1] if path_parts else ""
        leaf_code = str(unit.get("leaf_id") or "").split("-")[0]
        chapter = _chapter_of(leaf_code)
        if not front or front in seen_front:
            dropped.append({"leaf": str(unit.get("leaf_id")), "reason": "front_dup_or_empty"})
            continue
        if any(w in front for w in FORBIDDEN_WORDS):
            dropped.append({"leaf": str(unit.get("leaf_id")), "reason": "forbidden_word"})
            continue
        verified = unit["_verified"]
        # 主 quote = 最长的 verified quote(信息量启发, 确定性)
        best = max(verified, key=lambda r: len(r["quote"]))
        chunk_id = str((unit.get("source_ref") or {}).get("chunk_id") or "")
        chunk = textbook.get(chunk_id)
        if chunk is not None:
            # 闸②: 不信任传递——quote 归一后必须逐字 ⊂ 教材 chunk
            if _norm(best["quote"]) not in _norm(chunk["md"]):
                dropped.append({"leaf": str(unit.get("leaf_id")), "reason": "quote_recheck_fail"})
                continue
        else:
            quote_recheck_skipped += 1
        page = (chunk or {}).get("page") or (unit.get("source_ref") or {}).get("page_num")
        seen_front.add(front)
        cards.append(
            {
                "card_id": f"STD:{unit.get('leaf_id')}",
                "front": front,
                "key_gist": "",
                "quote": best["quote"],
                "point_id": str(best["point"].get("point_id") or ""),
                "source_ref": {
                    "chunk_id": chunk_id,
                    "page_num": page,
                    "source_lane": "rich_leaf_v32_verified",
                    "repair_mode": "std_compiled",
                },
                "leaf_name_path": str(unit.get("leaf_name_path") or ""),
                "chapter": chapter,
                "exam_weight": score,
                "scoring_terms": _dedupe_term_sets(verified[:2]),
            }
        )

    chapters: dict[str, int] = {}
    for card in cards:
        chapters[card["chapter"]] = chapters.get(card["chapter"], 0) + 1
    return {
        "schema_version": SCHEMA_NAME,
        "tier": "standard",
        "status": "candidate",  # 签发口径待 owner 过目打样后定, 不冒充 signed
        "source_v32_sha256": hashlib.sha256(v32_bytes).hexdigest(),
        "generation_ms": round((time.perf_counter() - t0) * 1000, 2),
        "ranking": "exam_frequency_directional(case*2+choice*1, 11年FINAL_CLEANED)",
        "card_count": len(cards),
        "chapters": chapters,
        "quote_recheck_skipped": quote_recheck_skipped,
        "dropped_rows": dropped,
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="标准考点卡编译器(考频Top-N, v32派生)")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--check", action="store_true", help="只算不写")
    args = parser.parse_args()
    payload = build_payload(args.top)
    print(
        f"standard-cards: {payload['card_count']} 卡 | 章分布 {payload['chapters']} | "
        f"quote复核跳过 {payload['quote_recheck_skipped']} | dropped {len(payload['dropped_rows'])}"
    )
    if args.check:
        return 0
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
