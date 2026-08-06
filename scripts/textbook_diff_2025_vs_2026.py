#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2025 教材 PDF × 2026 教材结构化块 粗 diff（只读、幂等）。

用途
----
以 2026 教材的 650 个 content block 为主轴，把每块的文本在 2025 教材 PDF 全文里做
模糊匹配，产出三档粗分类：

  - ``likely_new``      2025 全文里找不到近似内容 → 疑似 2026 新增
  - ``likely_modified`` 部分命中 → 疑似 2026 修订
  - ``unchanged``       高相似 → 2025 已有

**这是粗清单，含噪声，教研终审后方可作为出题依据。**
本脚本不写任何 runtime supply / registry / LearnerState，不做出题决策。

设计
----
1. 抽取：``pdftotext -layout`` 逐页抽 2025 PDF；抽不出文本的页如实计数（``pages_empty``）。
   抽取结果缓存到 ``--cache-dir``（默认 scratchpad，不入库，避免把教材全文提交进 repo）。
2. 归一化：去 markdown 记号、去全部空白、去标点、全角转半角，只保留 CJK / 数字 / 拉丁字母。
3. 匹配：字符 8-gram 集合。
   - ``shingle_containment`` = |block∩2025| / |block|
   - ``sentence_hit_ratio``  = 命中句数 / 总句数（单句 8-gram containment ≥ SENT_HIT 视为命中）
   - ``score`` = max(两者)
4. 分档：阈值写死在本文件顶部常量，可复跑。

用法
----
    python3 scripts/textbook_diff_2025_vs_2026.py            # 抽取（带缓存）+ diff + 出报告
    python3 scripts/textbook_diff_2025_vs_2026.py --force-extract
    python3 scripts/textbook_diff_2025_vs_2026.py --stage extract
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date

# --------------------------------------------------------------------------
# 写死的阈值与参数（可复跑）
# --------------------------------------------------------------------------
SHINGLE_K = 8          # 字符 n-gram 长度
SENT_MIN_LEN = 12      # 参与句级匹配的最短归一化句长
SENT_HIT = 0.60        # 单句判定"命中 2025"的 containment 阈值
TH_UNCHANGED = 0.72    # score >= 此值 → unchanged
TH_MODIFIED = 0.28     # TH_MODIFIED <= score < TH_UNCHANGED → likely_modified；更低 → likely_new
MIN_BLOCK_CHARS = 40   # 归一化后短于此值的块标记 too_short，单独归档不参与三档主结论

# --------------------------------------------------------------------------
# 路径（绝对路径；PDF 与 2026 块都在主仓库工作区，非本 worktree）
# --------------------------------------------------------------------------
REPO_MAIN = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"

PDF_2025 = os.path.join(
    REPO_MAIN,
    "docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）",
    "2025一建《建筑实务》电子教材（可搜索）.pdf",
)
PDF_OFFICIAL_DIFF = os.path.join(
    REPO_MAIN,
    "docs/原始数据/PDF/建筑实务11.20_副本",
    "2026一级建造师《建筑工程管理与实务》教材对比明细.pdf",
)
BLOCKS_DIR = os.path.join(REPO_MAIN, "docs/原始数据/2026_副本/2026教材/第二次加强")
BLOCK_FILES = [
    "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
INVENTORY_JSON_CANDIDATES = [
    os.path.join(
        REPO_MAIN,
        ".claude/worktrees/agent-a2ca4e09152c376ec",
        "docs/原始数据/数据盘点/2026-08-06-表单v2题源盘点.json",
    ),
]

DEFAULT_CACHE = (
    "/private/tmp/claude-501/-Users-yehongchen-orca-workspaces-deeptutor-gar/"
    "ee9233f2-6c53-4d2e-b999-9d34b995d3f5/scratchpad/textbook_diff_cache"
)

# 盘点点名的 6 个"五星 + 客观题零供给"节点
SIX_STAR_ZERO_NODES = {
    "1A422000": "相关标准",
    "1A431011": "施工平面布置",
    "1A432001": "工程招标方式与程序",
    "1A432002": "工程合同管理",
    "1A437000": "绿色建造",
    "1A438000": "季节性施工技术",
}

# --------------------------------------------------------------------------
# 归一化
# --------------------------------------------------------------------------
_MD_PAT = re.compile(r"(\*\*|__|~~|`{1,3}|^#{1,6}\s*|^\s*[-*+]\s+|^\s*>\s*|\|)", re.M)
_KEEP = re.compile(r"[一-鿿㐀-䶿0-9A-Za-z]")


def normalize(text: str) -> str:
    """去 markdown / 空白 / 标点，全角转半角，只留 CJK+数字+字母。"""
    if not text:
        return ""
    text = _MD_PAT.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if _KEEP.match(ch))


_SENT_SPLIT = re.compile(r"[。；;！!？?\n]+")


def split_sentences(md: str) -> list[str]:
    raw = _MD_PAT.sub("", md)
    parts = _SENT_SPLIT.split(raw)
    out = []
    for p in parts:
        n = normalize(p)
        if len(n) >= SENT_MIN_LEN:
            out.append(n)
    return out


def shingles(norm: str, k: int = SHINGLE_K) -> set[str]:
    if len(norm) < k:
        return {norm} if norm else set()
    return {norm[i : i + k] for i in range(len(norm) - k + 1)}


# --------------------------------------------------------------------------
# 阶段一：抽取 2025 PDF
# --------------------------------------------------------------------------
def extract_pdf_pages(pdf_path: str, cache_path: str, force: bool = False) -> dict:
    if os.path.exists(cache_path) and not force:
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh)
    if not os.path.exists(pdf_path):
        raise SystemExit("PDF 未找到: %s" % pdf_path)

    info = subprocess.run(
        ["pdfinfo", pdf_path], capture_output=True, text=True, check=True
    ).stdout
    n_pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))

    pages, empty, failed = [], [], []
    for p in range(1, n_pages + 1):
        try:
            res = subprocess.run(
                ["pdftotext", "-layout", "-f", str(p), "-l", str(p), pdf_path, "-"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            txt = res.stdout if res.returncode == 0 else ""
            if res.returncode != 0:
                failed.append(p)
        except Exception:
            txt, = ("",)
            failed.append(p)
        norm = normalize(txt)
        if len(norm) < 20:
            empty.append(p)
        pages.append({"page": p, "chars_raw": len(txt), "chars_norm": len(norm), "text": txt})
        if p % 50 == 0:
            print("  ...抽到第 %d/%d 页" % (p, n_pages), file=sys.stderr)

    payload = {
        "pdf_path": pdf_path,
        "pages_total": n_pages,
        "pages_empty": empty,
        "pages_failed": failed,
        "pages": pages,
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return payload


# --------------------------------------------------------------------------
# 阶段二：加载 2026 块
# --------------------------------------------------------------------------
def load_blocks() -> list[dict]:
    blocks = []
    for name in BLOCK_FILES:
        path = os.path.join(BLOCKS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for b in data["content_blocks"]:
            tax = b.get("taxonomy") or {}
            meta = b.get("metadata") or {}
            src = b.get("source_meta") or {}
            md = b.get("content_markdown") or ""
            title = ""
            for line in md.splitlines():
                if line.strip().startswith("#"):
                    title = line.lstrip("#").strip()
                    break
            if not title:
                title = (src.get("original_anchor") or tax.get("topic") or "").strip()
            key_terms = []
            for card in b.get("knowledge_cards") or []:
                key_terms.extend(card.get("keywords") or [])
                key_terms.extend(card.get("key_numbers") or [])
                if card.get("card_title"):
                    key_terms.append(card["card_title"])
            blocks.append(
                {
                    "chunk_id": b.get("chunk_id"),
                    "source_file": name,
                    "page_num": src.get("page_num"),
                    "source_name": src.get("source_name"),
                    "original_anchor": src.get("original_anchor"),
                    "node_code": tax.get("node_code"),
                    "node_name": tax.get("node_name"),
                    "taxonomy_path": tax.get("taxonomy_path"),
                    "topic": tax.get("topic"),
                    "exam_weight": meta.get("exam_weight"),
                    "exam_form": meta.get("exam_form"),
                    "content_type": b.get("content_type"),
                    "title": title,
                    "content_markdown": md,
                    "key_terms": sorted(set(t for t in key_terms if t))[:20],
                }
            )
    return blocks


# --------------------------------------------------------------------------
# 阶段三：匹配 + 分档
# --------------------------------------------------------------------------
def build_index(pages: list[dict]) -> tuple[set, dict]:
    """返回 (全量 shingle 集合, shingle -> 首个出现页)。"""
    all_sh: set[str] = set()
    first_page: dict[str, int] = {}
    for pg in pages:
        norm = normalize(pg["text"])
        for s in shingles(norm):
            if s not in first_page:
                first_page[s] = pg["page"]
        all_sh.update(shingles(norm))
    return all_sh, first_page


def classify(block: dict, all_sh: set, first_page: dict) -> dict:
    norm = normalize(block["content_markdown"])
    bsh = shingles(norm)
    hit = bsh & all_sh
    shingle_containment = (len(hit) / len(bsh)) if bsh else 0.0

    sents = split_sentences(block["content_markdown"])
    sent_hits = 0
    for s in sents:
        ssh = shingles(s)
        if not ssh:
            continue
        if len(ssh & all_sh) / len(ssh) >= SENT_HIT:
            sent_hits += 1
    sentence_hit_ratio = (sent_hits / len(sents)) if sents else 0.0

    score = max(shingle_containment, sentence_hit_ratio)

    # 关键术语命中（用于人工复核参考）
    term_hits = []
    for t in block["key_terms"]:
        tn = normalize(t)
        if len(tn) >= 3 and shingles(tn) & all_sh:
            term_hits.append(t)

    # 2025 定位：命中 shingle 的众数页
    pages_hit = collections.Counter(first_page[s] for s in hit if s in first_page)
    top_pages = [p for p, _ in pages_hit.most_common(3)]

    too_short = len(norm) < MIN_BLOCK_CHARS
    if score >= TH_UNCHANGED:
        verdict = "unchanged"
    elif score >= TH_MODIFIED:
        verdict = "likely_modified"
    else:
        verdict = "likely_new"

    return {
        "verdict": verdict,
        "too_short": too_short,
        "score": round(score, 4),
        "shingle_containment": round(shingle_containment, 4),
        "sentence_hit_ratio": round(sentence_hit_ratio, 4),
        "sentences_total": len(sents),
        "sentences_hit": sent_hits,
        "norm_chars": len(norm),
        "key_terms_hit": term_hits,
        "key_terms_missing": [t for t in block["key_terms"] if t not in term_hits],
        "candidate_2025_pages": top_pages,
    }


def summarize_text(block: dict, limit: int = 180) -> str:
    """标题 + 首两句 作为摘要。"""
    sents = _SENT_SPLIT.split(_MD_PAT.sub("", block["content_markdown"]))
    body = []
    for s in sents:
        s = " ".join(s.split())
        if len(s) >= 8:
            body.append(s)
        if len(body) == 2:
            break
    txt = "；".join(body)
    if len(txt) > limit:
        txt = txt[:limit] + "…"
    return txt


# --------------------------------------------------------------------------
# 题量对齐
# --------------------------------------------------------------------------
def load_inventory() -> dict:
    for p in INVENTORY_JSON_CANDIDATES:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            cov = {c["node_code"]: c for c in d["textbook_2026_blocks"]["coverage"]}
            return {"path": p, "coverage": cov}
    return {"path": None, "coverage": {}}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE)
    ap.add_argument("--out-dir", default=None, help="报告输出目录（默认 repo 内数据盘点目录）")
    ap.add_argument("--force-extract", action="store_true")
    ap.add_argument("--stage", choices=["extract", "diff", "all"], default="all")
    args = ap.parse_args()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out_dir or os.path.join(here, "docs/原始数据/数据盘点")

    print("[1/4] 抽取 2025 教材 PDF 文本 …", file=sys.stderr)
    cache_2025 = os.path.join(args.cache_dir, "pdf2025_pages.json")
    pdf25 = extract_pdf_pages(PDF_2025, cache_2025, force=args.force_extract)
    print(
        "      页数=%d 空文本页=%d 抽取失败页=%d"
        % (pdf25["pages_total"], len(pdf25["pages_empty"]), len(pdf25["pages_failed"])),
        file=sys.stderr,
    )

    official = None
    if os.path.exists(PDF_OFFICIAL_DIFF):
        cache_off = os.path.join(args.cache_dir, "pdf_official_diff_pages.json")
        official = extract_pdf_pages(PDF_OFFICIAL_DIFF, cache_off, force=args.force_extract)
        print(
            "      [旁证] 官方教材对比明细 页数=%d 空文本页=%d"
            % (official["pages_total"], len(official["pages_empty"])),
            file=sys.stderr,
        )

    if args.stage == "extract":
        return 0

    print("[2/4] 建立 2025 全文 shingle 索引 …", file=sys.stderr)
    all_sh, first_page = build_index(pdf25["pages"])
    print("      2025 shingle 数=%d" % len(all_sh), file=sys.stderr)

    print("[3/4] 加载 2026 块并逐块判定 …", file=sys.stderr)
    blocks = load_blocks()
    inv = load_inventory()

    rows = []
    for b in blocks:
        r = classify(b, all_sh, first_page)
        cov = inv["coverage"].get(b["node_code"] or "", {})
        rows.append(
            {
                **{k: b[k] for k in
                   ("chunk_id", "source_file", "page_num", "source_name",
                    "original_anchor", "node_code", "node_name", "taxonomy_path",
                    "topic", "exam_weight", "exam_form", "content_type", "title")},
                **r,
                "summary": summarize_text(b),
                "node_q_total": cov.get("q_total"),
                "node_q_single_choice": cov.get("q_single_choice"),
                "node_q_multi_choice": cov.get("q_multi_choice"),
                "node_q_case_study": cov.get("q_case_study"),
                "node_exam_weight": cov.get("exam_weight"),
                "node_block_count": cov.get("block_count"),
            }
        )

    counts = collections.Counter(r["verdict"] for r in rows)
    by_node = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        by_node[r["node_code"]][r["verdict"]] += 1

    print("[4/4] 写产物 …", file=sys.stderr)
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "schema": "luban_textbook_diff_2025_2026.v0",
        "generated_on": date.today().isoformat(),
        "disclaimer": "粗清单，含噪声，教研终审后方可作为出题依据；本产物不是 runtime supply，不做出题决策。",
        "params": {
            "shingle_k": SHINGLE_K,
            "sent_min_len": SENT_MIN_LEN,
            "sent_hit": SENT_HIT,
            "th_unchanged": TH_UNCHANGED,
            "th_modified": TH_MODIFIED,
            "min_block_chars": MIN_BLOCK_CHARS,
        },
        "sources": {
            "pdf_2025": PDF_2025,
            "pdf_2025_pages_total": pdf25["pages_total"],
            "pdf_2025_pages_empty": pdf25["pages_empty"],
            "pdf_2025_pages_failed": pdf25["pages_failed"],
            "blocks_dir": BLOCKS_DIR,
            "block_files": BLOCK_FILES,
            "block_count": len(blocks),
            "inventory_json": inv["path"],
            "official_diff_pdf": PDF_OFFICIAL_DIFF if official else None,
            "official_diff_pages_total": official["pages_total"] if official else None,
            "official_diff_pages_empty": official["pages_empty"] if official else None,
        },
        "counts": dict(counts),
        "counts_by_node": {k: dict(v) for k, v in sorted(by_node.items(), key=lambda kv: kv[0] or "")},
        "six_star_zero_supply_nodes": {
            code: {
                "node_name": name,
                "verdicts": dict(by_node.get(code, {})),
                "q_total": inv["coverage"].get(code, {}).get("q_total"),
                "q_single_choice": inv["coverage"].get(code, {}).get("q_single_choice"),
                "q_multi_choice": inv["coverage"].get(code, {}).get("q_multi_choice"),
                "q_case_study": inv["coverage"].get(code, {}).get("q_case_study"),
                "block_count": inv["coverage"].get(code, {}).get("block_count"),
            }
            for code, name in SIX_STAR_ZERO_NODES.items()
        },
        "blocks": rows,
    }
    json_path = os.path.join(out_dir, "2026-08-06-教材2026新增点粗清单.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("      -> %s" % json_path, file=sys.stderr)
    print(json.dumps(dict(counts), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
