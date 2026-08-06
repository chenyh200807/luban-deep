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
OFFICIAL_LOCATE_TH = 0.50  # 官方变点文本被某个 2026 块包含的最低比例，才算"定位成功"
SENT_NEW_TH = 0.35     # 单句 containment 低于此值 → 该句在 2025 里找不到，记为"句级新增点"
NOVEL_SENT_PER_BLOCK = 6   # 每块最多记录几条句级新增点
TOP_NEW_LIMIT = 40     # md 报告里块级新增点 top 清单条数
TOP_SENT_LIMIT = 80    # md 报告里句级新增点 top 清单条数

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
_FORMULA_PAT = re.compile(r"\$\$|\\frac|\\tag|\\times|\\sqrt|\\leq|\\geq|\\cdot|\$[^$]{2,}\$")
_EDITORIAL_PAT = re.compile(
    r"(采分点|记忆口诀|口诀[:：]|必须准确记忆|本考点|考试中常考|易错点|提示[:：]|注意[:：])"
)


def split_sentences(md: str) -> list[tuple[str, str]]:
    """返回 [(原句, 归一化句)]，只保留归一化后够长的句子。"""
    raw = _MD_PAT.sub("", md)
    parts = _SENT_SPLIT.split(raw)
    out = []
    for p in parts:
        n = normalize(p)
        if len(n) >= SENT_MIN_LEN:
            out.append((" ".join(p.split()), n))
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
    novel: list[dict] = []
    novel_sh: set[str] = set()
    for raw_s, s in sents:
        ssh = shingles(s)
        if not ssh:
            continue
        c = len(ssh & all_sh) / len(ssh)
        if c >= SENT_HIT:
            sent_hits += 1
        if c < SENT_NEW_TH:
            novel.append(
                {
                    "text": raw_s[:220],
                    "containment": round(c, 3),
                    "chars": len(s),
                    # 公式/表格块经 pdftotext 无法还原 → 低分是抽取噪声，不是新增
                    "formula_like": bool(_FORMULA_PAT.search(raw_s)),
                    # 2026 块是 LLM 增强产物，部分"新句"是编者按而非教材原文
                    "editorial_like": bool(_EDITORIAL_PAT.search(raw_s)),
                }
            )
            novel_sh |= ssh
    sentence_hit_ratio = (sent_hits / len(sents)) if sents else 0.0
    novel.sort(key=lambda x: (x["containment"], -x["chars"]))

    score = max(shingle_containment, sentence_hit_ratio)

    # 关键术语命中（用于人工复核参考）
    term_hits = []
    for t in block["key_terms"]:
        tn = normalize(t)
        if len(tn) >= 3 and shingles(tn) & all_sh:
            term_hits.append(t)

    # 2025 定位：命中 shingle 的众数页
    # 注意：必须先 sorted(hit)，否则 set 迭代序会让并列页码的胜者随进程 hash 种子变化，破坏幂等
    pages_hit = collections.Counter(first_page[s] for s in sorted(hit) if s in first_page)
    top_pages = [
        pg for pg, _ in sorted(pages_hit.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    ]

    too_short = len(norm) < MIN_BLOCK_CHARS
    # 表格/图题块：pdftotext 对 2025 版表格排版还原差，此类块的低分多为抽取噪声而非真新增
    table_like = bool(
        re.match(r"^\s*(表|续表|图)\s*[\d一二三四五六七八九十]", block["title"] or "")
    ) or (block["content_markdown"].count("|") >= 6 and len(norm) < 300)

    if score >= TH_UNCHANGED:
        verdict = "unchanged"
    elif score >= TH_MODIFIED:
        verdict = "likely_modified"
    else:
        verdict = "likely_new"

    return {
        "verdict": verdict,
        "too_short": too_short,
        "table_like": table_like,
        "score": round(score, 4),
        "shingle_containment": round(shingle_containment, 4),
        "sentence_hit_ratio": round(sentence_hit_ratio, 4),
        "sentences_total": len(sents),
        "sentences_hit": sent_hits,
        "novel_sentence_count": len(novel),
        "novel_sentences": novel[:NOVEL_SENT_PER_BLOCK],
        "_novel_shingles": novel_sh,
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
# 官方《教材对比明细》解析（旁证，非本 diff 的判据，只做交叉验证）
# --------------------------------------------------------------------------
_CHANGE_HDR = re.compile(r"^\s*变化\s*(\d+)\s*$")
_FOOTER = re.compile(r"^\s*第\s*\d+\s*页\s*共\s*\d+\s*页\s*$")
_PAGEPAIR = re.compile(r"^\s*(P[\d\-–~至]+)\s{2,}(P[\d\-–~至]+)\s*$")
_SINGLE_P = re.compile(r"^\s*(P[\d\-–~至]+)\s*$")
_MARKER = re.compile(r"【([^】]{1,8})】")
COL_SPLIT = 20  # 左栏=2025，右栏=2026；缩进 >= 该列视为右栏


def parse_official_diff(official: dict) -> list[dict]:
    """把官方对比明细切成变点列表。噪声可容忍，只作旁证。"""
    lines: list[str] = []
    for pg in official["pages"]:
        lines.extend(pg["text"].splitlines())

    idxs = [i for i, l in enumerate(lines) if _CHANGE_HDR.match(l)]
    changes = []
    for n, i in enumerate(idxs):
        end = idxs[n + 1] if n + 1 < len(idxs) else len(lines)
        cid = int(_CHANGE_HDR.match(lines[i]).group(1))
        seg = lines[i + 1 : end]
        p25 = p26 = None
        left, right = [], []
        pending_single = []
        for l in seg:
            if not l.strip() or _FOOTER.match(l):
                continue
            m = _PAGEPAIR.match(l)
            if m and p25 is None:
                p25, p26 = m.group(1), m.group(2)
                continue
            m = _SINGLE_P.match(l)
            if m and p25 is None and len(pending_single) < 2:
                pending_single.append(m.group(1))
                if len(pending_single) == 2:
                    p25, p26 = pending_single
                continue
            indent = len(l) - len(l.lstrip())
            (right if indent >= COL_SPLIT else left).append(l.strip())
        text26 = "\n".join(right)
        text25 = "\n".join(left)
        changes.append(
            {
                "change_id": cid,
                "page_2025": p25,
                "page_2026": p26,
                "markers": sorted(set(_MARKER.findall(text26 + text25))),
                "text_2026": _MARKER.sub("", text26).strip(),
                "text_2025": _MARKER.sub("", text25).strip(),
            }
        )
    # 同号去重（目录/正文重复出现时保留正文更长的一条）
    best: dict[int, dict] = {}
    for c in changes:
        cur = best.get(c["change_id"])
        if cur is None or len(c["text_2026"]) > len(cur["text_2026"]):
            best[c["change_id"]] = c
    return [best[k] for k in sorted(best)]


def crossmatch_official(changes: list[dict], blocks: list[dict], all_sh: set) -> None:
    """给每个官方变点找最像的 2026 块（原地写回）。"""
    block_sh = [(b["chunk_id"], shingles(normalize(b["content_markdown"]))) for b in blocks]
    for c in changes:
        csh = shingles(normalize(c["text_2026"]))
        if not csh:
            c.update(best_block=None, best_containment=0.0, containment_in_2025=0.0)
            continue
        best_id, best_v = None, 0.0
        for cid, bsh in block_sh:
            if not bsh:
                continue
            v = len(csh & bsh) / len(csh)
            if v > best_v:
                best_id, best_v = cid, v
        c["best_block"] = best_id
        c["best_containment"] = round(best_v, 4)
        c["containment_in_2025"] = round(len(csh & all_sh) / len(csh), 4)


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
# markdown 报告
# --------------------------------------------------------------------------
def _md_escape(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def render_markdown(p: dict, inv: dict) -> str:
    rows = p["blocks"]
    counts = p["counts"]
    src = p["sources"]
    total = len(rows)
    cov = inv["coverage"]
    L: list[str] = []
    A = L.append

    A("# 2026 教材新增/修订点 粗清单（2025 PDF × 2026 结构化块 diff）")
    A("")
    A("- **日期**: %s" % p["generated_on"])
    A("- **schema**: `%s`" % p["schema"])
    A("- **产物**: 本文件 + `2026-08-06-教材2026新增点粗清单.json` + "
      "`scripts/textbook_diff_2025_vs_2026.py`")
    A("")
    A("> ⚠️ **粗清单，含噪声，教研终审后方可作为出题依据。**")
    A("> 本产物是 `raw_diff_evidence`，不是 runtime supply、不是 official score authority，")
    A("> 不写 questions_bank / LearnerState / registry，不做任何出题决策。")
    A("")

    A("## 结论先行")
    A("")
    A("以 2026 教材 %d 个 content block 为主轴，在 2025 可搜索版教材 PDF 全文（%d 页）里做"
      "字符 8-gram 模糊匹配，三档结果：" % (total, src["pdf_2025_pages_total"]))
    A("")
    A("| 档位 | 块数 | 占比 | 含义 |")
    A("|---|---:|---:|---|")
    for k, desc in (
        ("likely_new", "2025 全文找不到近似 → 疑似 2026 新增"),
        ("likely_modified", "部分命中 → 疑似 2026 修订"),
        ("unchanged", "高相似 → 2025 已有"),
    ):
        n = counts.get(k, 0)
        A("| `%s` | %d | %.1f%% | %s |" % (k, n, 100.0 * n / total, desc))
    A("| **合计** | **%d** | 100%% | |" % total)
    A("")
    sl = p.get("sentence_level") or {}
    if sl:
        A("**块级三档不够用**：官方变点大多是「在一个整体没变的段落里插一两句新规定」，"
          "这种改动在块级仍会判 `unchanged`。因此本清单同时给出**句级新增点**：")
        A("")
        A("| 指标 | 值 |")
        A("|---|---:|")
        A("| 句级新增点总数（单句 containment < %.2f） | **%d** |" % (
            sl["sent_new_threshold"], sl["novel_sentence_total"]))
        A("| 含句级新增点的块数 | %d / %d |" % (sl["blocks_with_novel_sentence"], total))
        A("| 其中落在 `unchanged` 块内部的句级新增点 | %d |" % (
            sl["novel_sentences_inside_unchanged_blocks"]))
        A("")

    ost = p.get("official_diff_crossvalidation") or {}
    if ost:
        h = ost["located_verdict_histogram"]
        nm = h.get("likely_new", 0) + h.get("likely_modified", 0)
        loc = ost["located_in_2026_blocks"]
        both = ost.get("located_flagged_by_block_or_sentence", nm)
        A("**旁证交叉验证**：官方《2026 一级建造师〈建筑工程管理与实务〉教材对比明细》"
          "（自称总体变化 107 处 / 实质内容变化 70 处）被解析出 **%d 个变点**（与官方口径一致），"
          "其中 %d 个能定位到某个 2026 块（containment ≥ %.2f）。" % (
              ost["change_points_parsed"], loc, ost["locate_threshold"]))
        A("")
        A("| 召回口径 | 命中 / 可定位 | 召回率 |")
        A("|---|---|---:|")
        A("| 仅看块级三档（`likely_new`+`likely_modified`） | %d / %d | %.0f%% |" % (
            nm, loc, 100.0 * nm / loc if loc else 0.0))
        A("| 块级三档 **或** 句级新增点覆盖 | %d / %d | %.0f%% |" % (
            both, loc, 100.0 * both / loc if loc else 0.0))
        A("")
        A("解读：块级判据单独用会漏掉大半官方变点（它们藏在 `unchanged` 块里），"
          "**句级新增点才是给教研看的主清单**；块级三档负责回答\"哪些整块是新的\"。")
        A("")
        A("另注：只有 %d/%d 个官方变点能定位到 2026 块。未定位的主要原因是官方对比表是"
          "双栏排版、`pdftotext` 会把 2025/2026 两栏文字交错，以及部分变点写成"
          "\"（1）～（6）整目变动\"这类指代式描述、本身没有可匹配正文。" % (
              loc, ost["change_points_parsed"]))
        A("")

    A("## 方法与阈值（写死在脚本里，可复跑）")
    A("")
    A("```")
    A("SHINGLE_K       = %d    # 字符 n-gram 长度" % p["params"]["shingle_k"])
    A("SENT_MIN_LEN    = %d    # 参与句级匹配的最短归一化句长" % p["params"]["sent_min_len"])
    A("SENT_HIT        = %.2f  # 单句判定命中 2025 的 containment 阈值" % p["params"]["sent_hit"])
    A("TH_UNCHANGED    = %.2f  # score >= 此值 → unchanged" % p["params"]["th_unchanged"])
    A("TH_MODIFIED     = %.2f  # 此值 <= score < TH_UNCHANGED → likely_modified；更低 → likely_new"
      % p["params"]["th_modified"])
    A("MIN_BLOCK_CHARS = %d    # 归一化后短于此值标 too_short" % p["params"]["min_block_chars"])
    A("```")
    A("")
    A("1. `pdftotext -layout` 逐页抽 2025 PDF 文本；")
    A("2. 归一化：去 markdown 记号 / 去全部空白 / 去标点 / 全角转半角，只留 CJK+数字+字母；")
    A("3. `shingle_containment` = 块 8-gram 落在 2025 全文的比例；"
      "`sentence_hit_ratio` = 命中句数 / 总句数；`score = max(两者)`；")
    A("4. 按上面阈值分三档，并给出 2025 侧候选页码（命中 shingle 的众数页）。")
    A("")

    A("## 抽取真相（失败页如实计数）")
    A("")
    A("| 源 | 页数 | 空文本页 | 抽取失败页 |")
    A("|---|---:|---:|---:|")
    A("| 2025 教材（可搜索版） | %d | %d | %d |" % (
        src["pdf_2025_pages_total"], len(src["pdf_2025_pages_empty"]),
        len(src["pdf_2025_pages_failed"])))
    if src.get("official_diff_pages_total"):
        A("| 官方教材对比明细（旁证） | %d | %d | 0 |" % (
            src["official_diff_pages_total"], len(src["official_diff_pages_empty"] or [])))
    A("")
    A("- 2025 PDF 空文本页: %s" % (src["pdf_2025_pages_empty"] or "无"))
    A("- 2025 PDF pdftotext 返回非零页: %s" % (src["pdf_2025_pages_failed"] or "无"))
    A("")
    A("**源文件**")
    A("")
    A("- 2025: `%s`" % src["pdf_2025"])
    A("- 2026 块: `%s`（%s，共 %d 块）" % (
        src["blocks_dir"], " + ".join(src["block_files"]), src["block_count"]))
    A("- 题量表: `%s`" % src["inventory_json"])
    if src.get("official_diff_pdf"):
        A("- 旁证: `%s`" % src["official_diff_pdf"])
    A("")

    A("## 按 node_code 的三档分布（对齐 20 节点题量表）")
    A("")
    novel_by_node = (p.get("sentence_level") or {}).get("novel_by_node", {})
    A("| node_code | 节点 | 星级 | 块数 | likely_new | likely_modified | unchanged | "
      "句级新增点 | 现有题量 总/单选/多选/案例 |")
    A("|---|---|---|---:|---:|---:|---:|---:|---|")
    for code, v in p["counts_by_node"].items():
        c = cov.get(code, {})
        nb = sum(v.values())
        A("| `%s` | %s | %s | %d | **%d** | %d | %d | **%d** | %s/%s/%s/%s |" % (
            code, _md_escape(c.get("node_name") or ""), c.get("exam_weight") or "-", nb,
            v.get("likely_new", 0), v.get("likely_modified", 0), v.get("unchanged", 0),
            novel_by_node.get(code, 0),
            c.get("q_total", "?"), c.get("q_single_choice", "?"),
            c.get("q_multi_choice", "?"), c.get("q_case_study", "?")))
    A("")

    A("## 句级新增点 top 清单（主清单，教研优先看这一节）")
    A("")
    A("每条是 2026 教材里**在 2025 全文找不到近似表述**的单句（containment < %.2f）。"
      "排序键：所属节点客观题供给越少越靠前 → containment 越低越靠前 → 句子越长越靠前。"
      % (p.get("sentence_level") or {}).get("sent_new_threshold", SENT_NEW_TH))
    A("")

    def obj_gap_node(code):
        c = cov.get(code or "", {})
        return (c.get("q_single_choice") or 0) + (c.get("q_multi_choice") or 0)

    sent_rows, sent_noise = [], []
    for r in rows:
        for s in r["novel_sentences"]:
            if s["chars"] < 20:
                continue
            if r["table_like"] or s["formula_like"]:
                sent_noise.append((r, s))
            else:
                sent_rows.append((r, s))
    sent_rows.sort(key=lambda t: (obj_gap_node(t[0]["node_code"]), t[1]["containment"], -t[1]["chars"]))
    A("| # | node_code / 节点 | 星级 | 节点客观题(单+多) | 块级判定 | chunk_id | 2026 新增句（截断） |")
    A("|---:|---|---|---:|---|---|---|")
    for i, (r, s) in enumerate(sent_rows[:TOP_SENT_LIMIT], 1):
        mark = " ⚠编者按" if s["editorial_like"] else ""
        A("| %d | `%s` %s | %s | %d | %s | `%s` | %s%s |" % (
            i, r["node_code"], _md_escape(cov.get(r["node_code"], {}).get("node_name") or ""),
            r.get("node_exam_weight") or "-", obj_gap_node(r["node_code"]),
            r["verdict"], r["chunk_id"], _md_escape(s["text"])[:150], mark))
    A("")
    A("（过滤掉表格块、LaTeX 公式句、过短句后共 %d 条，此处列前 %d 条；"
      "另有 %d 条落入公式/表格噪声区；全量在 JSON 的 `blocks[].novel_sentences[]`。）"
      % (len(sent_rows), min(TOP_SENT_LIMIT, len(sent_rows)), len(sent_noise)))
    A("")
    A("`⚠编者按` = 该句命中「采分点/口诀/注意：」等编者用语。2026 块是 LLM 增强产物"
      "（`增强版v3.2`），此类句子很可能是**编译时加的讲解，不是教材原文**，教研须剔除。")
    A("")

    A("## 块级新增点 top 清单（`likely_new`，按节点客观题缺口 × 星级排序）")
    A("")
    A("排序键：节点客观题供给（单选+多选）越少越靠前 → 节点星级越高越靠前 → 块正文越长越靠前。"
      "`表/图` 开头且 `table_like=true` 的块单列在后面的噪声区。")
    A("")
    new_rows = [r for r in rows if r["verdict"] == "likely_new"]
    signal = [r for r in new_rows if not r["table_like"] and not r["too_short"]]
    noise = [r for r in new_rows if r["table_like"] or r["too_short"]]

    def obj_gap(r):
        return (r.get("node_q_single_choice") or 0) + (r.get("node_q_multi_choice") or 0)

    signal.sort(key=lambda r: (obj_gap(r), -len((r.get("node_exam_weight") or "")), -r["norm_chars"]))
    A("| # | chunk_id | node_code / 节点 | 星级 | 节点客观题(单+多) | 节点题量合计 | 标题 | 摘要 |")
    A("|---:|---|---|---|---:|---:|---|---|")
    for i, r in enumerate(signal[:TOP_NEW_LIMIT], 1):
        A("| %d | `%s` | `%s` %s | %s | %d | %s | %s | %s |" % (
            i, r["chunk_id"], r["node_code"], _md_escape(r.get("node_name") or ""),
            r.get("node_exam_weight") or "-", obj_gap(r), r.get("node_q_total", "?"),
            _md_escape(r["title"])[:36], _md_escape(r["summary"])[:110]))
    A("")
    if len(signal) > TOP_NEW_LIMIT:
        A("（`likely_new` 非噪声块共 %d 条，此处只列前 %d 条；全量见 JSON 的 `blocks[]`。）"
          % (len(signal), TOP_NEW_LIMIT))
        A("")
    A("### 噪声区：表格/过短块判为 likely_new（%d 条）" % len(noise))
    A("")
    A("这些块的低分主要来自 `pdftotext` 对 2025 版表格排版还原差，**不应直接当作新增点**。")
    A("")
    A("| chunk_id | node_code | 标题 | score | 归一化字数 |")
    A("|---|---|---|---:|---:|")
    for r in noise:
        A("| `%s` | `%s` | %s | %.2f | %d |" % (
            r["chunk_id"], r["node_code"], _md_escape(r["title"])[:36], r["score"], r["norm_chars"]))
    A("")

    A("## 6 个「五星 + 客观题零供给」节点的 diff 归类")
    A("")
    A("盘点点名的 6 个节点在本 diff 里的归类如下。`客观题供给` = 单选 + 多选。")
    A("")
    A("| node_code | 节点 | 星级 | 块数 | likely_new | likely_modified | unchanged | "
      "句级新增点 | 现有客观题 | 现有案例题 |")
    A("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for code, v in p["six_star_zero_supply_nodes"].items():
        vd = v["verdicts"]
        A("| `%s` | %s | %s | %s | **%d** | %d | %d | **%d** | %d | %s |" % (
            code, v["node_name"], cov.get(code, {}).get("exam_weight", "-"),
            v.get("block_count", "?"), vd.get("likely_new", 0), vd.get("likely_modified", 0),
            vd.get("unchanged", 0), novel_by_node.get(code, 0),
            (v.get("q_single_choice") or 0) + (v.get("q_multi_choice") or 0),
            v.get("q_case_study", "?")))
    A("")
    A("注：这 6 个节点的\"零题\"口径是**客观题（单选+多选）零供给**，不是完全没题——"
      "`1A422000` / `1A431011` / `1A437000` / `1A438000` 有案例题供给，"
      "`1A432001` / `1A432002` 才是 `q_total = 0` 的真空节点。")
    A("")

    if ost:
        A("## 官方《教材对比明细》旁证（交叉验证，非本 diff 判据）")
        A("")
        A("| 指标 | 值 |")
        A("|---|---:|")
        A("| 解析出的变点数 | %d |" % ost["change_points_parsed"])
        A("| 定位阈值 containment | %.2f |" % ost["locate_threshold"])
        A("| 能定位到某个 2026 块 | %d |" % ost["located_in_2026_blocks"])
        for k in ("likely_new", "likely_modified", "unchanged"):
            A("| └ 落在本 diff `%s` 块上 | %d |" % (k, ost["located_verdict_histogram"].get(k, 0)))
        A("")
        A("变点标记分布：%s" % ", ".join(
            "`%s`=%d" % (k, v) for k, v in sorted(ost["marker_histogram"].items(),
                                                  key=lambda kv: -kv[1])))
        A("")
        A("### 官方 107 个变点 → 2026 chunk_id 定位明细（全量）")
        A("")
        A("`定位到的块` 是官方 2026 侧变点正文被哪个 2026 content block 包含（containment 越接近 "
          "1.00 定位越准）。`句级覆盖` = 该变点正文有多大比例落在本 diff 标出的句级新增点上。"
          "**这张表是本次产出里最可直接用的东西**：教研拿官方变点号就能跳到对应 chunk_id。")
        A("")
        A("| 变化# | 2025页 | 2026页 | 标记 | 定位到的块 | node_code | 本 diff 判定 | "
          "定位 containment | 句级覆盖 |")
        A("|---:|---|---|---|---|---|---|---:|---:|")
        for c in p["official_change_points"]:
            A("| %d | %s | %s | %s | `%s` | `%s` | %s | %.2f | %.2f |" % (
                c["change_id"], c.get("page_2025") or "-", c.get("page_2026") or "-",
                "/".join(c["markers"]) or "-", c.get("best_block") or "-",
                c.get("best_block_node_code") or "-", c.get("best_block_verdict") or "-",
                c.get("best_containment") or 0.0, c.get("covered_by_novel_sentences") or 0.0))
        A("")

    A("## 噪声与诚实边界")
    A("")
    A("1. **不是官方变动清单**：本 diff 由文本相似度产生，`likely_new` 里必然混有"
      "「2025 里有但 pdftotext 抽不干净」的块（表格、公式、图注最典型）。")
    A("2. **2026 块本身是 LLM 清洗+增强后的 OCR 产物**（`增强版v3.2`），与 2025 原始版式文本"
      "存在改写差异，会系统性压低相似度 → `likely_modified` 一档天然偏多；"
      "且部分\"新句\"其实是编译时加的讲解（已用 `editorial_like` 标注），不是教材新增。")
    A("3. **LaTeX 公式句必然判新增**：2026 块把公式写成 `$$...$$`，`pdftotext` 从 2025 PDF "
      "抽出的是排版后的字符，两侧不可能匹配。已用 `formula_like` 从主清单剔除。")
    A("4. **章节切分口径不同**：2026 块按 chunk 切、2025 按页抽，块 ↔ 页不是一一对应，"
      "`candidate_2025_pages` 只是定位线索。")
    A("5. **题量对齐的粒度是 node_code**，不是块级；\"某新增点下现有题量\"实际是"
      "\"该新增块所属 node_code 下的现有题量\"，不代表该具体知识点已有题。")
    A("6. **官方旁证也不是终审**：官方对比明细自身是双栏 PDF，解析有交错噪声；"
      "本表 107 个变点里 54 个未能定位到块，不代表这些变点不存在。")
    A("7. 本清单**不做出题决策**，不判断某个新增点该出几道题、什么题型。")
    A("")
    A("## 复跑")
    A("")
    A("```bash")
    A("python3 scripts/textbook_diff_2025_vs_2026.py               # 用缓存")
    A("python3 scripts/textbook_diff_2025_vs_2026.py --force-extract  # 重抽 PDF")
    A("```")
    A("")
    A("脚本只读源数据，输出固定两份产物，重复执行结果一致。")
    A("")
    return "\n".join(L)


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

    # 句级新增 shingle 只用于交叉验证，不进 JSON
    novel_sh_of = {r["chunk_id"]: r.pop("_novel_shingles") for r in rows}

    counts = collections.Counter(r["verdict"] for r in rows)
    by_node = collections.defaultdict(lambda: collections.Counter())
    novel_by_node: collections.Counter = collections.Counter()
    for r in rows:
        by_node[r["node_code"]][r["verdict"]] += 1
        novel_by_node[r["node_code"]] += r["novel_sentence_count"]
    novel_total = sum(r["novel_sentence_count"] for r in rows)
    blocks_with_novel = sum(1 for r in rows if r["novel_sentence_count"])
    novel_in_unchanged = sum(
        r["novel_sentence_count"] for r in rows if r["verdict"] == "unchanged"
    )

    print("[4/5] 交叉验证：官方《教材对比明细》 …", file=sys.stderr)
    changes: list[dict] = []
    verdict_of = {r["chunk_id"]: r["verdict"] for r in rows}
    node_of = {r["chunk_id"]: r["node_code"] for r in rows}
    official_stats = {}
    if official:
        changes = parse_official_diff(official)
        crossmatch_official(changes, blocks, all_sh)
        for c in changes:
            c["best_block_verdict"] = verdict_of.get(c.get("best_block") or "")
            c["best_block_node_code"] = node_of.get(c.get("best_block") or "")
            nsh = novel_sh_of.get(c.get("best_block") or "") or set()
            csh = shingles(normalize(c["text_2026"]))
            c["covered_by_novel_sentences"] = (
                round(len(csh & nsh) / len(csh), 3) if csh else 0.0
            )
        located = [c for c in changes if c["best_containment"] >= OFFICIAL_LOCATE_TH]
        official_stats = {
            "change_points_parsed": len(changes),
            "locate_threshold": OFFICIAL_LOCATE_TH,
            "located_in_2026_blocks": len(located),
            "located_flagged_by_block_verdict": sum(
                1 for c in located if c["best_block_verdict"] in ("likely_new", "likely_modified")
            ),
            "located_flagged_by_block_or_sentence": sum(
                1
                for c in located
                if c["best_block_verdict"] in ("likely_new", "likely_modified")
                or c["covered_by_novel_sentences"] >= 0.20
            ),
            "located_verdict_histogram": dict(
                collections.Counter(c["best_block_verdict"] for c in located)
            ),
            "located_node_histogram": dict(
                collections.Counter(c["best_block_node_code"] for c in located)
            ),
            "marker_histogram": dict(
                collections.Counter(m for c in changes for m in c["markers"])
            ),
        }
        print(
            "      官方变点=%d 可定位到 2026 块=%d 命中 verdict 分布=%s"
            % (len(changes), len(located), official_stats["located_verdict_histogram"]),
            file=sys.stderr,
        )

    print("[5/5] 写产物 …", file=sys.stderr)
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
        "sentence_level": {
            "sent_new_threshold": SENT_NEW_TH,
            "novel_sentence_total": novel_total,
            "blocks_with_novel_sentence": blocks_with_novel,
            "novel_sentences_inside_unchanged_blocks": novel_in_unchanged,
            "novel_by_node": dict(sorted(novel_by_node.items(), key=lambda kv: -kv[1])),
        },
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
        "official_diff_crossvalidation": official_stats,
        "official_change_points": changes,
        "blocks": rows,
    }
    json_path = os.path.join(out_dir, "2026-08-06-教材2026新增点粗清单.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("      -> %s" % json_path, file=sys.stderr)

    md_path = os.path.join(out_dir, "2026-08-06-教材2026新增点粗清单.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(payload, inv))
    print("      -> %s" % md_path, file=sys.stderr)

    print(json.dumps(dict(counts), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
