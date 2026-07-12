#!/usr/bin/env python3
"""考点卡 bank 编译器（确定性派生，禁 LLM 现编——双轮 v3.2 §6.2 / §8）。

派生层裁决（2026-07-05，调研 S05/A01/F16/J01/N01 五包后定）：
- **§1 跨章知识点全景表 = 唯一派生层**。一行 = 一个原子知识点，自带人审短名
  （卡正面问法的确定性底料）、关键数值/做法（可背关键词颗粒=助记）、三色标注
  与 kc: point_id 锚——正好是 30 秒再认卡的形态。
- R5 采分点不做卡源：R5 是答案态语句、按采分簇组织，已归 §6.3 实务闯关的
  答案键（再认卡复用它会把两种复习单元的面撕混）；且 R5 的 🟢 标注在 A01
  等包挂在簇标题层，行级机械解析不稳。
- R2 不变量不做卡源：每包一段、cardinality=1，是闯关的判别逻辑不是再认颗粒。

**fail-closed 铁律**（每条都无豁免）：
1. 只收三色 🟢 行（🟡/🔴 直接掉，🟢+🔵 混标行按 🟢 分支收，quote 门兜底）；
2. 教材原文 = compiled_source 对应 point 的 quote **逐字**——锚解析不到
   quote 的行不成卡（真题-only 锚、`…` 省略锚、m35 锚都在此掉）；
3. 同 point_id 重复行只留首行（后续行留痕 dropped_rows，不算违规）；
4. 恒写 status="candidate"——签发（candidate→signed）唯一入口 =
   docs/原始数据/考点原料/promote_variant_bank.py --kind concept_cards（人闸）。

gate（结构 + quote 逐字命中 + 去重 + 禁审视词）必须 100% 才写文件；
--check 模式零写入：重新派生 + 重跑 gate，且若磁盘已有 bank，
逐卡比对（确定性重建一致性——builder 升版/pack 改动都会在此现形）。

用法::

    python3 scripts/build_luban_concept_card_bank.py S05          # 生成/更新 bank
    python3 scripts/build_luban_concept_card_bank.py S05 --check  # 零写入核验
"""
from __future__ import annotations

import argparse
import hashlib
import functools
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "docs" / "原始数据" / "考点原料"
PACK_DIR = RAW_DIR / "成品"

SCHEMA_NAME = "luban-concept-card-bank"  # dash 命名空间=脚本编译产物, 非 runtime schema(同变体池惯例)
BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"

_PACK_ID_RE = re.compile(r"^[A-Z]\d{2}$")
_KC_ANCHOR_RE = re.compile(r"kc:[0-9A-Za-z_]+:\d+")
# 文案铁律(评审要点摘要): 禁审视揭短词——只查模板侧字段, 教材 quote 是逐字权威不动
FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")
# 去掉知识点名尾部括注(全/半角)——A01 的括注常把答案写在正面, 会泄卡背
_TRAILING_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]\s*$")
_MD_DECOR_RE = re.compile(r"[*`]")


class BankBuildError(Exception):
    """派生/gate 失败：bank 不写。"""


# ── 教材 quote 修复层（2026-07-11 owner 验尸后加，治"断头引文/空页码"病） ──
# 病根：compiled_source 的 quote 是 ~92 字窗口切片（账本 D4 登记的切片管道病），
# 首尾断句 + markdown 噪声混入（34 卡验尸: 11 卡截断、10 卡 source_ref 空）。
# 治法：按 point 的 chunk_id 在教材权威库（FINAL_CLEANED_BOOK2026*_fixed.json，
# 事实权威阶梯: 教材 > 一切）定位原 quote，**确定性延展**到完整块/句边界，
# 剥 markdown 装饰，并从 chunk source_meta 取真页码——零 LLM、零生成，
# 修复后 quote 归一化后必须仍是 chunk 全文的逐字子串（gate 硬核验）。
# 教材库缺失 → fail-loud（禁静默产出未修复 bank，防两台机器产出漂移）。
TEXTBOOK_DIR = REPO / "docs" / "原始数据" / "2026_副本" / "2026教材" / "第二次加强"
_TEXTBOOK_GLOB = "FINAL_CLEANED_BOOK2026*fixed.json"
# 归一化剔除集：空白 + markdown 装饰(#*`>|) + 列表连字符/项目符
_NORM_STRIP = set(" \t\r\n　#*`>|—–-·•▪")
_SENTENCE_END = "。！？；"
_QUOTE_MAX_LEN = 320
_TEXTBOOK_LANE = "textbook_v3_fixed"

_textbook_cache: dict[str, dict[str, Any]] | None = None


def _load_textbook_index(textbook_dir: Path) -> dict[str, dict[str, Any]]:
    """chunk_id → {md, page}（三分片合并，模块级缓存）。缺库 = fail-loud。"""
    global _textbook_cache
    if _textbook_cache is not None:
        return _textbook_cache
    paths = sorted(textbook_dir.glob(_TEXTBOOK_GLOB))
    if not paths:
        raise BankBuildError(
            f"教材权威库缺失: {textbook_dir}/{_TEXTBOOK_GLOB}——quote 修复无法复现，"
            "拒绝产出（在有教材库的机器上编译，或先同步 2026_副本）"
        )
    index: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            book = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise BankBuildError(f"教材库解析失败: {path} ({exc})")
        for block in book.get("content_blocks") or []:
            cid = str(block.get("chunk_id") or "").strip()
            md = str(block.get("content_markdown") or "")
            if not cid or not md or cid in index:
                continue
            meta = block.get("source_meta") or {}
            page = meta.get("page_num")
            index[cid] = {"md": md, "page": page if isinstance(page, int) else None}
    _textbook_cache = index
    return index


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """归一化（剔 _NORM_STRIP 字符）并保留 归一下标→原文下标 映射。"""
    out: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(text):
        if ch in _NORM_STRIP:
            continue
        out.append(ch)
        mapping.append(i)
    return "".join(out), mapping


def _norm(text: str) -> str:
    return "".join(ch for ch in text if ch not in _NORM_STRIP)


def _clean_block_lines(lines: list[str]) -> str:
    """剥 markdown 装饰：删标题行，去列表符/加粗/代码记号；不动任何文字。"""
    kept: list[str] = []
    for line in lines:
        striped = line.strip()
        if not striped or striped.startswith("#"):
            continue  # 标题是排版件不是教材正文句
        striped = re.sub(r"^[-*·•]\s*", "", striped)
        striped = striped.replace("**", "").replace("`", "")
        kept.append(striped)
    return " ".join(kept).strip()


def _trim_to_sentences(cleaned: str, probe: str) -> str:
    """超长时收敛到覆盖 probe（原截断 quote）的完整句窗口。"""
    if len(cleaned) <= _QUOTE_MAX_LEN:
        return cleaned
    parts = re.split(f"(?<=[{_SENTENCE_END}])", cleaned)
    norm_probe = _norm(probe)[:30]
    acc = ""
    start_idx = 0
    for i, part in enumerate(parts):
        acc += part
        if norm_probe and norm_probe in _norm(acc):
            start_idx = i
            break
    window = ""
    begin = start_idx
    while begin > 0 and len(parts[begin - 1]) + len(window) < 60:
        begin -= 1
        window = parts[begin] + window
    for part in parts[start_idx:]:
        if window and len(window) + len(part) > _QUOTE_MAX_LEN:
            break
        window += part
    window = window.strip()
    return window if window else cleaned[:_QUOTE_MAX_LEN]


_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _bigrams(text: str) -> set[str]:
    n = _norm(text)
    return {n[i : i + 2] for i in range(len(n) - 1)}


_ENUM_HEAD_RE = re.compile(r"^\s*(?:[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[）)．.、])")


def _chunk_windows(chunk_md: str) -> list[dict[str, str]]:
    """chunk → 候选窗口 [{text, heading}]：逐块清洗文本，超长块按句滑窗；
    heading = 该块上方最近的标题文本（front 对齐用，不进 quote 输出）。

    枚举合并：教材"（1）…（5）/①…⑤"逐项常被空行拆成单条块——"合格五条"这类
    整表考点必须有**完整枚举窗口**候选（含前置引导句），否则选句只会命中末条
    （对抗质检实锤的选句错位残留形态）。"""
    lines = chunk_md.splitlines()
    raw_blocks: list[dict[str, Any]] = []  # {lines, heading, enum}
    heading = ""
    cur: list[str] = []

    def _flush_raw() -> None:
        nonlocal cur
        if not cur:
            return
        first = next((l.strip() for l in cur if l.strip()), "")
        raw_blocks.append(
            {"lines": cur, "heading": heading, "enum": bool(_ENUM_HEAD_RE.match(first))}
        )
        cur = []

    for line in lines + [""]:
        striped = line.strip()
        if not striped:
            _flush_raw()
            continue
        if striped.startswith("#"):
            _flush_raw()
            heading = _MD_DECOR_RE.sub("", striped.lstrip("#")).strip()
            continue
        cur.append(line)

    windows: list[dict[str, str]] = []

    def _emit(block_lines: list[str], head: str) -> None:
        block = _clean_block_lines(block_lines)
        if not block:
            return
        if len(block) <= _QUOTE_MAX_LEN:
            windows.append({"text": block, "heading": head})
            return
        parts = re.split(f"(?<=[{_SENTENCE_END}])", block)
        for i in range(len(parts)):
            window = ""
            for part in parts[i:]:
                if window and len(window) + len(part) > _QUOTE_MAX_LEN:
                    break
                window += part
            if window.strip():
                windows.append({"text": window.strip(), "heading": head})

    idx = 0
    while idx < len(raw_blocks):
        blk = raw_blocks[idx]
        _emit(blk["lines"], blk["heading"])
        # 枚举 run：连续 enum 块（同 heading）合并为整表窗口，带上前一块引导句
        if blk["enum"]:
            run = [blk]
            j = idx + 1
            while (
                j < len(raw_blocks)
                and raw_blocks[j]["enum"]
                and raw_blocks[j]["heading"] == blk["heading"]
            ):
                run.append(raw_blocks[j])
                _emit(raw_blocks[j]["lines"], raw_blocks[j]["heading"])
                j += 1
            if len(run) > 1:
                merged: list[str] = []
                if idx > 0 and not raw_blocks[idx - 1]["enum"]:
                    intro = _clean_block_lines(raw_blocks[idx - 1]["lines"])
                    if intro.endswith("：") or intro.endswith(":") or len(intro) < 40:
                        merged.extend(raw_blocks[idx - 1]["lines"])
                for member in run:
                    merged.extend(member["lines"])
                block = _clean_block_lines(merged)
                if block:
                    # 整表窗口豁免滑窗上限(枚举完整性 > 长度上限, 上限=2倍)
                    if len(block) <= _QUOTE_MAX_LEN * 2:
                        windows.append({"text": block, "heading": blk["heading"]})
            idx = j
            continue
        idx += 1
    return windows


def _select_quote(
    front: str, gist: str, legacy_quote: str, chunk_md: str
) -> dict[str, str] | None:
    """按**卡意图（front+gist）语义对齐**在 chunk 里选教材真句窗口。

    对抗质检两个批级病的治法合一：
    - 改写冒充原文（39+78 卡实锤）：不再信 legacy quote，只从 chunk 逐字窗口选；
    - 选句错位（C02 13/16 张 quote 选中提问/邻卡答案）：以 front+gist 为对齐权威
      （人写的 §1 短名/关键词 = 这张卡在问什么），legacy quote 只作低权重提示。

    硬门槛（不满足=None，调用侧剔卡——宁缺勿假）：
    - gist 含数字时，窗口须覆盖 ≥80% 的 gist 数字 token（数字是安全关键面）；
    - front 与 窗口+其标题 的双字重叠 ≥0.15（答非所问挡板）。
    """
    windows = _chunk_windows(chunk_md)
    if not windows:
        return None
    front_bg = _bigrams(front)
    gist_bg = _bigrams(gist)
    legacy_bg = _bigrams(legacy_quote)
    gist_nums = set(_NUM_RE.findall(gist))
    best: tuple[float, dict[str, str]] | None = None
    for win in windows:
        text = win["text"]
        w_bg = _bigrams(text)
        if not w_bg:
            continue
        w_head_bg = w_bg | _bigrams(win["heading"])
        w_nums = set(_NUM_RE.findall(text))
        num_cov = (len(gist_nums & w_nums) / len(gist_nums)) if gist_nums else 1.0
        front_ov = (len(front_bg & w_head_bg) / len(front_bg)) if front_bg else 0.0
        gist_ov = (len(gist_bg & w_bg) / len(gist_bg)) if gist_bg else 0.0
        legacy_ov = (len(legacy_bg & w_bg) / len(legacy_bg)) if legacy_bg else 0.0
        if gist_nums and num_cov < 0.8:
            continue
        if front_bg and front_ov < 0.15:
            continue
        score = num_cov * 2 + front_ov * 1.5 + gist_ov + legacy_ov * 0.5 - len(text) / 2000
        if best is None or score > best[0]:
            best = (score, win)
    if best is None:
        return None
    chosen = best[1]
    if _norm(chosen["text"]) not in _norm(chunk_md):
        return None
    return chosen


def _match_by_terms(raw_quote: str, chunk_md: str) -> str | None:
    """改写文本回退锚定：quote 非教材逐字（对抗质检实锤 78 卡为 LLM 改写冒充原文）
    时，按**数字 token + 字面双字重叠**在 chunk 里找真句窗口。命中门槛硬：
    quote 的数字 token ≥80% 必须出现在窗口里（数字是安全关键面）、双字重叠≥0.25。
    找不到 = 返回 None（调用侧整卡剔除——宁缺勿假，"教材原文"必须是教材原文）。
    """
    q_nums = set(_NUM_RE.findall(raw_quote))
    q_norm = _norm(raw_quote)
    q_bigrams = {q_norm[i : i + 2] for i in range(len(q_norm) - 1)}
    if not q_bigrams:
        return None
    lines = chunk_md.splitlines()
    # 候选窗口 = 逐块（空行/标题分隔）的清洗文本，块过长再按句滑窗
    blocks: list[str] = []
    cur: list[str] = []
    for line in lines + [""]:
        striped = line.strip()
        if not striped or striped.startswith("#"):
            if cur:
                blocks.append(_clean_block_lines(cur))
                cur = []
            continue
        cur.append(line)
    candidates: list[str] = []
    for block in blocks:
        if not block:
            continue
        if len(block) <= _QUOTE_MAX_LEN:
            candidates.append(block)
            continue
        parts = re.split(f"(?<=[{_SENTENCE_END}])", block)
        for i in range(len(parts)):
            window = ""
            for part in parts[i:]:
                if window and len(window) + len(part) > _QUOTE_MAX_LEN:
                    break
                window += part
            if window.strip():
                candidates.append(window.strip())
    best: tuple[float, str] | None = None
    for cand in candidates:
        c_norm = _norm(cand)
        c_bigrams = {c_norm[i : i + 2] for i in range(len(c_norm) - 1)}
        if not c_bigrams:
            continue
        c_nums = set(_NUM_RE.findall(cand))
        num_cov = (len(q_nums & c_nums) / len(q_nums)) if q_nums else 1.0
        overlap = len(q_bigrams & c_bigrams) / len(q_bigrams)
        if num_cov < 0.8 or overlap < 0.25:
            continue
        score = num_cov * 2 + overlap - len(cand) / 2000  # 同分偏短窗口
        if best is None or score > best[0]:
            best = (score, cand)
    if best is None:
        return None
    result = best[1]
    return result if _norm(result) in _norm(chunk_md) else None


def _repair_quote(raw_quote: str, chunk_md: str) -> str | None:
    """把截断 quote 修复为完整块/句边界的教材原文；定位失败返回 None（保留原样）。

    跨块窗口处理：~92 字切片常"头沾上一节尾巴、中间横着标题行"。头尾双锚定位，
    若展开范围内有内部标题（跨块实锤），取**最后一个内部标题之后**的块——点的
    真身所在（切片窗口是越过标题伸进目标节的）。
    """
    norm_chunk, mapping = _norm_with_map(chunk_md)
    norm_quote = _norm(raw_quote)
    if len(norm_quote) < 12 or not mapping:
        return None

    def _find(probe_lens: tuple[int, ...], from_tail: bool) -> tuple[int, int]:
        for plen in probe_lens:
            plen = min(plen, len(norm_quote))
            probe = norm_quote[-plen:] if from_tail else norm_quote[:plen]
            pos = norm_chunk.find(probe)
            if pos >= 0:
                return pos, pos + plen
        return -1, -1

    head_s, head_e = _find((len(norm_quote), 60, 40, 24), from_tail=False)
    tail_s, tail_e = _find((40, 24), from_tail=True)
    if head_s < 0 and tail_s < 0:
        return None
    # 双锚合法（尾在头后且跨度合理）则并成大 span；否则用能用的那个
    if head_s >= 0 and tail_e > head_s and (tail_e - head_s) <= len(norm_quote) * 2 + 40:
        span = (head_s, tail_e - 1)
    elif head_s >= 0:
        span = (head_s, head_e - 1)
    else:
        span = (tail_s, tail_e - 1)
    orig_start = mapping[min(span[0], len(mapping) - 1)]
    orig_end = mapping[min(span[1], len(mapping) - 1)]

    lines = chunk_md.splitlines(keepends=True)
    offsets: list[tuple[int, int]] = []
    acc_len = 0
    for line in lines:
        offsets.append((acc_len, acc_len + len(line)))
        acc_len += len(line)

    def line_of(offset: int) -> int:
        for i, (s, e) in enumerate(offsets):
            if s <= offset < e:
                return i
        return len(offsets) - 1

    def is_blank(i: int) -> bool:
        return not lines[i].strip()

    def is_heading(i: int) -> bool:
        return lines[i].lstrip().startswith("#")

    ls, le = line_of(orig_start), line_of(min(orig_end, acc_len - 1))
    # 展开到空行边界（标题不当边界，先容进来再裁跨块）
    while ls > 0 and not is_blank(ls - 1):
        ls -= 1
    while le + 1 < len(lines) and not is_blank(le + 1):
        le += 1
    # 跨块裁决：范围内(不含首行)有标题 → 取最后一个内部标题之后的块
    interior_headings = [i for i in range(ls + 1, le + 1) if is_heading(i)]
    if interior_headings:
        cut = interior_headings[-1] + 1
        if cut <= le:
            ls = cut
    cleaned = _clean_block_lines(lines[ls : le + 1])
    if not cleaned:
        return None
    # trim 的 probe 用 quote 尾段（跨块时头段属于被裁掉的上一节）
    cleaned = _trim_to_sentences(cleaned, raw_quote[-40:])
    # 硬校验：修复产物归一后必须仍是 chunk 的逐字子串（清洗只删装饰字符）
    if _norm(cleaned) not in norm_chunk:
        return None
    return cleaned


def _load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise BankBuildError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — 统一转 BankBuildError
        raise BankBuildError(f"{what} 解析失败: {path} ({exc})")


def _point_index(pack_id: str) -> dict[str, dict[str, Any]]:
    """compiled_source 的 point_id → {quote, source_ref} 索引（quote 为空的点不进索引）。"""
    cs = _load_json(RAW_DIR / f"_{pack_id}_compiled_source.json", "compiled_source")
    index: dict[str, dict[str, Any]] = {}
    for unit in cs.get("units") or []:
        ref = unit.get("source_ref") or {}
        textbook = _load_textbook_index(TEXTBOOK_DIR)
        for sp in unit.get("scoring_points") or []:
            pid = str(sp.get("point_id") or "")
            quote = str(sp.get("quote") or "").strip()
            if not pid or not quote or pid in index:
                continue
            # 教材修复层：按 point 自带 chunk_id 在教材权威库定位并延展 quote
            chunk_id = str(sp.get("chunk") or ref.get("chunk_id") or "").strip()
            source_ref = {
                "chunk_id": chunk_id,
                "page_num": ref.get("page_num"),
                "source_lane": str(ref.get("source_lane") or ""),
            }
            # 注意：此处不再做 quote 修复/选择——选句权在 derive_cards 的
            # _select_quote（需要 front+gist 卡意图做对齐权威, 见对抗质检 S2）。
            index[pid] = {
                "quote": quote,
                "chunk_id": chunk_id,
                "source_ref": source_ref,
                "leaf_name_path": str(unit.get("leaf_name_path") or ""),
            }
    return index


def _section1_table_rows(pack_md: str) -> list[list[str]]:
    """抽 §1（`## 1.` / `## 1 ·`）里的 markdown 表行（含表头，不含分隔行）。"""
    rows: list[list[str]] = []
    in_sec = False
    for line in pack_md.splitlines():
        if line.startswith("## "):
            in_sec = bool(re.match(r"^## 1[.\s·]", line))
            continue
        if not in_sec:
            continue
        striped = line.strip()
        if not striped.startswith("|"):
            continue
        cells = [c.strip() for c in striped.strip("|").split("|")]
        if cells and set("".join(cells)) <= set("-—: "):
            continue  # 分隔行
        rows.append(cells)
    return rows


def _column_map(header: list[str]) -> dict[str, int]:
    """按表头语义定位列（S05 七列版 / A01 五列版共用）。"""
    cols: dict[str, int] = {}
    for idx, cell in enumerate(header):
        if "知识点" in cell and "name" not in cols:
            cols["name"] = idx
        elif "关键" in cell and "gist" not in cols:
            cols["gist"] = idx
        elif ("三色" in cell or "🚦" in cell) and "color" not in cols:
            cols["color"] = idx  # C02 用 🚦 做三色列头(同义)
    missing = {"name", "gist", "color"} - set(cols)
    if missing:
        raise BankBuildError(f"§1 表头缺语义列 {sorted(missing)}: {header}")
    return cols


def _clean_name(raw: str) -> str:
    name = _MD_DECOR_RE.sub("", raw).strip()
    return _TRAILING_PAREN_RE.sub("", name).strip()


_BLOCKLIST_PATH = RAW_DIR / "_concept_card_blocklist.json"
_blocklist_cache: set[str] | None = None


def _blocklist() -> set[str]:
    """对抗质检面板剔卡清单（card_id 集合；人审 editorial 记录，缺文件=空集）。"""
    global _blocklist_cache
    if _blocklist_cache is None:
        try:
            data = json.loads(_BLOCKLIST_PATH.read_text(encoding="utf-8"))
            _blocklist_cache = {
                str(item.get("card_id") or "") for item in data.get("cards") or []
            }
        except FileNotFoundError:
            _blocklist_cache = set()
    return _blocklist_cache


def derive_cards(pack_id: str) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    """确定性派生：返回 (cards, dropped_rows, source_pack_sha256)。纯函数式重建。"""
    manifest = _load_json(PACK_DIR / "_pack_manifest.json", "pack manifest")
    entry = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id), None
    )
    if entry is None or not entry.get("file"):
        raise BankBuildError(f"manifest 中无 pack {pack_id}")
    pack_path = PACK_DIR / str(entry["file"])
    pack_bytes = pack_path.read_bytes()
    pack_sha = hashlib.sha256(pack_bytes).hexdigest()
    if pack_sha != str(entry.get("content_sha256") or ""):
        raise BankBuildError(
            f"manifest content_sha256 落后于 pack 正文，先重跑 scripts/build_luban_pack_manifest.py"
        )
    points = _point_index(pack_id)
    rows = _section1_table_rows(pack_bytes.decode("utf-8"))
    if len(rows) < 2:
        raise BankBuildError(f"{pack_id} §1 未找到知识点全景表")
    cols = _column_map(rows[0])

    cards: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen_points: set[str] = set()
    for row in rows[1:]:
        if len(row) <= max(cols.values()):
            continue
        name = _clean_name(row[cols["name"]])
        color_cell = row[cols["color"]]
        row_text = " | ".join(row)
        if not name:
            continue
        if "🟢" not in color_cell or "🟡" in color_cell or "🔴" in color_cell:
            dropped.append({"row": name, "reason": "not_green"})
            continue
        resolved = next(
            (a for a in _KC_ANCHOR_RE.findall(row_text) if a in points), None
        )
        if resolved is None:
            dropped.append({"row": name, "reason": "no_verbatim_quote"})
            continue
        if resolved in seen_points:
            dropped.append({"row": name, "reason": "duplicate_point_id"})
            continue
        if f"{pack_id}:{resolved}" in _blocklist():
            # 对抗质检面板人审剔卡(内容错误/答非所问)——人审记录在
            # _concept_card_blocklist.json, builder 确定性消费(--check 可复现)
            dropped.append({"row": name, "reason": "panel_reject"})
            continue
        seen_points.add(resolved)
        point = points[resolved]
        gist = _MD_DECOR_RE.sub("", row[cols["gist"]]).strip()
        # ── 选句（对抗质检 S1+S2 治法合一）：chunk 在教材权威库时, quote 一律由
        # front+gist 意图对齐重选真句窗口; 选不出(答非所问/数字无出处)=剔卡。
        # chunk 不在库(讲义 lane 等少数)保留 compiled_source 原 quote。
        quote = point["quote"]
        source_ref = point["source_ref"]
        textbook = _load_textbook_index(TEXTBOOK_DIR)
        chunk = textbook.get(str(point.get("chunk_id") or ""))
        if chunk:
            chosen = _select_quote(name, gist, point["quote"], chunk["md"])
            if chosen is None:
                dropped.append({"row": name, "reason": "quote_unalignable"})
                seen_points.discard(resolved)
                continue
            quote = chosen["text"]
            source_ref = {
                "chunk_id": str(point.get("chunk_id") or ""),
                "page_num": chunk["page"],
                "source_lane": _TEXTBOOK_LANE,
                "repair_mode": "intent_aligned",
            }
        cards.append(
            {
                "card_id": f"{pack_id}:{resolved}",
                "front": name,
                "key_gist": gist,
                "quote": quote,
                "point_id": resolved,
                "source_ref": source_ref,
                "leaf_name_path": point["leaf_name_path"],
            }
        )
    return cards, dropped, pack_sha


def run_gate(pack_id: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """结构 + quote 逐字命中 compiled_source + 去重 + 禁审视词。100% 才算产出。"""
    points = _point_index(pack_id)
    quote_mismatches: list[str] = []
    duplicate_cards: list[str] = []
    forbidden_words: list[str] = []
    passed = 0
    seen_front: set[str] = set()
    textbook = _load_textbook_index(TEXTBOOK_DIR)
    intent_misses: list[str] = []
    gist_num_orphans: list[str] = []
    for card in cards:
        ok = True
        source = points.get(str(card.get("point_id") or ""))
        ref = card.get("source_ref") or {}
        lane = str(ref.get("source_lane") or "")
        quote = str(card.get("quote") or "")
        chunk = textbook.get(str(ref.get("chunk_id") or ""))
        if lane == _TEXTBOOK_LANE:
            # 教材 lane 硬闸①：quote 归一后必须逐字 ⊂ 教材 chunk 全文
            if chunk is None or _norm(quote) not in _norm(chunk["md"]):
                quote_mismatches.append(card["card_id"])
                ok = False
        else:
            # 非教材 lane（讲义等少数）：保持与 compiled_source 逐字一致
            if source is None or quote != source["quote"]:
                quote_mismatches.append(card["card_id"])
                ok = False
        # 硬闸②（对抗质检 S3-①）：front ↔ quote+所在块标题 对齐（答非所问挡板）。
        # 只对教材 lane 执行——讲义 lane 无 chunk 标题上下文, 该检查假阴性率高
        # (实测 N01 面板人工验真的卡会被误杀), 其正确性由逐字一致闸+人审面板兜。
        front_bg = _bigrams(str(card.get("front") or ""))
        if front_bg and lane == _TEXTBOOK_LANE:
            ctx_bg = _bigrams(quote)
            if chunk is not None:
                for win in _chunk_windows(chunk["md"]):
                    if _norm(win["text"]).startswith(_norm(quote)[:24]) or _norm(quote)[:24] in _norm(win["text"]):
                        ctx_bg |= _bigrams(win["heading"])
                        break
            if len(front_bg & ctx_bg) / len(front_bg) < 0.15:
                intent_misses.append(card["card_id"])
                ok = False
        # 硬闸③（对抗质检 S3-②）：gist 里的数字必须 ∈ quote ∪ chunk（防编数）
        gist_nums = set(_NUM_RE.findall(str(card.get("key_gist") or "")))
        if gist_nums:
            allowed = set(_NUM_RE.findall(quote))
            if chunk is not None:
                allowed |= set(_NUM_RE.findall(chunk["md"]))
            if not gist_nums <= allowed:
                gist_num_orphans.append(card["card_id"])
                ok = False
        if card["front"] in seen_front:
            duplicate_cards.append(card["card_id"])
            ok = False
        seen_front.add(card["front"])
        template_text = f'{card.get("front", "")}|{card.get("key_gist", "")}'
        if any(w in template_text for w in FORBIDDEN_WORDS):
            forbidden_words.append(card["card_id"])
            ok = False
        if not card.get("front") or not card.get("quote"):
            if card["card_id"] not in quote_mismatches:
                quote_mismatches.append(card["card_id"])
            ok = False
        if ok:
            passed += 1
    total = len(cards)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "quote_mismatches": quote_mismatches,
        "duplicate_cards": duplicate_cards,
        "forbidden_words": forbidden_words,
        # 对抗质检 S3 补闸(2026-07-11): 答非所问挡板 + gist 数字出处闸
        "intent_misses": intent_misses,
        "gist_num_orphans": gist_num_orphans,
    }


# ── v32 采分点富化(2026-07-12): 编译期 join RichLeaf v3.2 采分点富化层 ──
# owner 指令"利用编译资产"。四闸 fail-closed:
# ① provenance.quote_verified=True 且 source_authority=textbook 才收;
# ② required_terms 1..8 个;
# ③ 每个 term 都逐字 ∈ 本卡 quote(卡引的是 chunk 的意图切片, 词不在切片=不是
#    这张卡的给分词, 宁缺勿挂);
# ④ 按 terms 元组去重, 每卡至多 2 组。
# v32 包缺席(其他机器) → 空富化, 卡照常产出(enrichment 是加法, 不是门)。
_V32_PACK_PATH = (
    REPO / "artifacts" / "luban_grading_artifacts"
    / "rich_leaf_v32_scoring_point_compile_20260613"
    / "runtime_token_pack_v32_scoring_points.json"
)


@functools.lru_cache(maxsize=1)
def _v32_chunk_index() -> dict[str, list[dict[str, Any]]]:
    if not _V32_PACK_PATH.exists():
        return {}
    data = json.loads(_V32_PACK_PATH.read_text(encoding="utf-8"))
    index: dict[str, list[dict[str, Any]]] = {}
    for unit in data.get("runtime_token_pack_units") or []:
        chunk_id = str((unit.get("source_ref") or {}).get("chunk_id") or "")
        if not chunk_id:
            continue
        points = (unit.get("compiled_context") or {}).get("scoring_points") or []
        index.setdefault(chunk_id, []).extend(points)
    return index


def _attach_scoring_terms(cards: list[dict[str, Any]]) -> int:
    index = _v32_chunk_index()
    attached = 0
    for card in cards:
        chunk_id = str((card.get("source_ref") or {}).get("chunk_id") or "")
        quote = str(card.get("quote") or "")
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for point in index.get(chunk_id, []):
            prov = point.get("provenance") or {}
            if prov.get("quote_verified") is not True:
                continue
            if str(prov.get("source_authority") or "") != "textbook":
                continue
            terms = [str(t) for t in (point.get("required_terms") or []) if str(t).strip()]
            if not 1 <= len(terms) <= 8:
                continue
            if not all(term in quote for term in terms):
                continue
            key = tuple(terms)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "statement": str(point.get("statement") or ""),
                    "required_terms": terms,
                    "point_id": str(point.get("point_id") or ""),
                }
            )
            if len(rows) >= 2:
                break
        if rows:
            card["scoring_terms"] = rows
            attached += 1
    return attached


def build_payload(pack_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    cards, dropped, pack_sha = derive_cards(pack_id)
    if not cards:
        raise BankBuildError(f"{pack_id} 派生 0 卡（fail-closed，无 quote 不成卡）")
    terms_attached = _attach_scoring_terms(cards)
    gate = run_gate(pack_id, cards)
    return {
        "scoring_terms_enrichment": {
            "source": "rich_leaf_v32_scoring_point_compile_20260613",
            "cards_with_terms": terms_attached,
        },
        "schema_version": SCHEMA_NAME,
        "pack_id": pack_id,
        "status": "candidate",  # 签发唯一入口 = promote_variant_bank.py --kind concept_cards
        "source_pack_sha256": pack_sha,
        "generation_ms": round((time.perf_counter() - t0) * 1000, 2),
        "gate": gate,
        "card_count": len(cards),
        "dropped_rows": dropped,
        "cards": cards,
    }


def _stable_view(payload: dict[str, Any]) -> dict[str, Any]:
    """确定性比对视图：剔除非确定字段（generation_ms）与签发面（status/signoff，
    promote 人闸独占的翻牌字段——签发后的 bank 重跑 --check 仍应一致）。"""
    return {
        k: v
        for k, v in payload.items()
        if k not in ("generation_ms", "signoff", "status")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="考点卡 bank 编译器（确定性派生 + gate）")
    parser.add_argument("pack_id", help="pack id，如 S05")
    parser.add_argument(
        "--check", action="store_true",
        help="零写入：重派生 + 重跑 gate + 与磁盘 bank 逐卡比对",
    )
    args = parser.parse_args()
    pack_id = args.pack_id.strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        print(f"build-concept-card-bank: 非法 pack_id {args.pack_id!r}", file=sys.stderr)
        return 1
    try:
        payload = build_payload(pack_id)
    except BankBuildError as exc:
        print(f"build-concept-card-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    gate = payload["gate"]
    clean = not (
        gate["quote_mismatches"]
        or gate["duplicate_cards"]
        or gate["forbidden_words"]
        or gate["intent_misses"]
        or gate["gist_num_orphans"]
    )
    print(
        f"cards={gate['total']} gate_pass={gate['passed']} rate={gate['pass_rate']:.2%} "
        f"dropped={len(payload['dropped_rows'])} -> {'PASS' if clean else 'FAIL'}"
    )
    if not clean or gate["passed"] != gate["total"]:
        print(json.dumps(
            {k: gate[k] for k in (
                "quote_mismatches", "duplicate_cards", "forbidden_words",
                "intent_misses", "gist_num_orphans",
            )},
            ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = PACK_DIR / BANK_TEMPLATE.format(pack_id=pack_id)
    if args.check:
        if out_path.exists():
            existing = _load_json(out_path, "考点卡 bank")
            if _stable_view(existing) != _stable_view(payload):
                print(
                    "build-concept-card-bank: FAIL — 磁盘 bank 与确定性重建不一致"
                    "（pack/builder 已变更），请重跑本脚本重建后再签发",
                    file=sys.stderr,
                )
                return 1
        return 0
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"written {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
