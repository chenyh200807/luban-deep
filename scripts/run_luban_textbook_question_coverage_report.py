#!/usr/bin/env python3
"""Living LLM Artifact Compiler — textbook ↔ question-bank coverage report (path_index granularity).

READ-ONLY cross-reference of the signed textbook pack against the 2026 question bank, to answer:
  * which exam topics have questions but NO textbook cards (compile gap), and
  * which textbook sub-topics (taxonomy_path) have no corresponding questions (question gap), and
  * which textbook content (blocks) produced no signed cards.

Taxonomy reality (why the join is multi-level): the textbook tags 20 leaf node_codes + 197
taxonomy_path sub-topics; the question bank tags ~116 leaf node_codes (``predicted_node``) and carries
NO taxonomy_path. The two are tagged at DIFFERENT tree depths, so the reliable exact join is at the
6-char section prefix (chapter.section). A finer per-path question estimate is provided via lexical
relevance (the same ranker the runtime uses) and is clearly labelled HEURISTIC.

NO writes outside the artifacts dir. NO remote / DB / production.

Usage:
  python scripts/run_luban_textbook_question_coverage_report.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "textbook_question_coverage_20260606"
BUNDLE = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_knowledge_full" / "textbook_knowledge_release_candidate.json"
QB_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")

from deeptutor.services.construction_grading import compiled_registry_resolver as _R  # noqa: E402

_SECTION = 6  # 6-char node_code prefix = chapter.section level (the reliable cross-taxonomy join key)


def _section(code: str) -> str:
    return str(code or "")[:_SECTION]


def _load_textbook() -> dict[str, Any]:
    b = json.loads(BUNDLE.read_text("utf-8"))
    m = b["manifest"]
    recs = b["records"]
    path_cards: dict[str, list[dict[str, Any]]] = {}
    node_of_path: dict[str, str] = {}
    for r in recs:
        p = str(r.get("taxonomy_path") or "")
        if p:
            path_cards.setdefault(p, []).append(r)
            node_of_path.setdefault(p, str(r.get("node_code") or ""))
    return {"node_index": m.get("node_index") or {}, "path_index": m.get("path_index") or {},
            "records": recs, "path_cards": path_cards, "node_of_path": node_of_path}


def _load_questions() -> dict[str, Any]:
    """Per exam exercise: its finest node_code (predicted_node, else chunk taxonomy) + stem text."""
    nodes: dict[str, int] = {}
    names: dict[str, str] = {}
    stems_by_section: dict[str, list[str]] = {}
    total = 0
    for f in sorted(glob.glob(str(QB_DIR / "**" / "*.json"), recursive=True)):
        try:
            d = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for ch in d.get("chunks", []):
            tax = ch.get("taxonomy") or {}
            ch_code = str(tax.get("node_code") or "")
            if ch_code and tax.get("node_name"):
                names.setdefault(ch_code, str(tax.get("node_name")))
            for e in ch.get("exercises") or []:
                pn = e.get("predicted_node")
                code = pn if isinstance(pn, str) else (str((pn or {}).get("node_code") or "") if isinstance(pn, dict) else "")
                code = code or ch_code
                if not code:
                    continue
                total += 1
                nodes[code] = nodes.get(code, 0) + 1
                qd = e.get("question_data") if isinstance(e.get("question_data"), dict) else {}
                stem = str(qd.get("stem") or "")
                if stem:
                    stems_by_section.setdefault(_section(code), []).append(stem)
    return {"nodes": nodes, "names": names, "total": total, "stems_by_section": stems_by_section}


def _load_block_card_production() -> dict[str, Any]:
    """650 教材 blocks: how many knowledge_cards each had vs how many got signed (by node/path)."""
    signed_pids = set()
    b = json.loads(BUNDLE.read_text("utf-8"))
    signed_pids = {str(r.get("point_id")) for r in b["records"]}
    blocks_total = blocks_with_cards = blocks_zero_signed = 0
    zero_signed_examples: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(BOOK_DIR / "FINAL_CLEANED_BOOK2026*fixed.json"))):
        try:
            doc = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for blk in doc.get("content_blocks") or []:
            if not isinstance(blk, dict) or not str(blk.get("content_markdown") or "").strip():
                continue
            blocks_total += 1
            cards = blk.get("knowledge_cards") or []
            if not cards:
                continue
            blocks_with_cards += 1
            cid = str(blk.get("chunk_id") or "")
            n_signed = sum(1 for i in range(len(cards)) if f"{cid}::C{i}" in signed_pids)
            if n_signed == 0:
                blocks_zero_signed += 1
                if len(zero_signed_examples) < 25:
                    zero_signed_examples.append({
                        "chunk_id": cid, "node_code": str((blk.get("taxonomy") or {}).get("node_code") or ""),
                        "taxonomy_path": str((blk.get("taxonomy") or {}).get("taxonomy_path") or ""),
                        "cards": len(cards)})
    return {"blocks_total": blocks_total, "blocks_with_cards": blocks_with_cards,
            "blocks_zero_signed": blocks_zero_signed, "zero_signed_examples": zero_signed_examples}


def _estimate_path_questions(tb: dict[str, Any], q: dict[str, Any]) -> dict[str, int]:
    """HEURISTIC per-path question count: assign each question stem to its single best-matching textbook
    path by lexical relevance (the runtime ranker). Questions have no taxonomy_path, so this is an
    estimate, not ground truth. Restricted to stems whose SECTION the textbook covers."""
    path_text_tokens = {p: _R._relevance_tokens(" ".join(_R._card_text(c) for c in cards))
                        for p, cards in tb["path_cards"].items()}
    tb_sections = {_section(tb["node_of_path"][p]) for p in tb["path_cards"]}
    counts: dict[str, int] = dict.fromkeys(tb["path_cards"], 0)
    for sec, stems in q["stems_by_section"].items():
        if sec not in tb_sections:
            continue
        cand = [p for p in tb["path_cards"] if _section(tb["node_of_path"][p]) == sec]
        for stem in stems:
            qt = _R._relevance_tokens(stem)
            best, best_score = "", 0
            for p in cand:
                s = len(qt & path_text_tokens[p])
                if s > best_score:
                    best_score, best = s, p
            if best:
                counts[best] += 1
    return counts


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    tb = _load_textbook()
    q = _load_questions()
    blocks = _load_block_card_production()

    tb_nodes = set(tb["node_index"].keys())
    q_nodes = set(q["nodes"].keys())
    tb_sec = {_section(c) for c in tb_nodes}
    q_sec = {_section(c) for c in q_nodes}

    q_count_by_section: dict[str, int] = {}
    for code, n in q["nodes"].items():
        q_count_by_section[_section(code)] = q_count_by_section.get(_section(code), 0) + n

    sections_q_no_textbook = sorted(q_sec - tb_sec)
    sections_textbook_no_q = sorted(tb_sec - q_sec)

    est = _estimate_path_questions(tb, q)
    path_rows = []
    for p, cards in sorted(tb["path_cards"].items(), key=lambda kv: -len(kv[1])):
        node = tb["node_of_path"][p]
        sec = _section(node)
        path_rows.append({
            "taxonomy_path": p, "node_code": node, "section": sec, "card_count": len(cards),
            "section_has_questions": sec in q_sec,
            "section_question_count": q_count_by_section.get(sec, 0),
            "relevance_estimated_questions": est.get(p, 0),
        })
    paths_no_estimated_q = [r["taxonomy_path"] for r in path_rows if r["relevance_estimated_questions"] == 0]

    report = {
        "textbook": {"leaf_nodes": len(tb_nodes), "taxonomy_paths": len(tb["path_cards"]),
                     "sections": len(tb_sec), "signed_cards": len(tb["records"])},
        "questions": {"total_exercises": q["total"], "leaf_nodes": len(q_nodes), "sections": len(q_sec)},
        "section_cross_reference": {
            "sections_both": sorted(tb_sec & q_sec),
            "sections_question_but_no_textbook_card": [
                {"section": s, "question_count": q_count_by_section.get(s, 0),
                 "example_name": q["names"].get(next((c for c in q_nodes if _section(c) == s), ""), "")}
                for s in sections_q_no_textbook],
            "sections_textbook_card_but_no_question": sections_textbook_no_q,
        },
        "block_card_production": blocks,
        "path_detail_count": len(path_rows),
        "paths_with_zero_estimated_questions": paths_no_estimated_q,
        "caveat": "questions carry only node_code (no taxonomy_path) and are tagged at a different tree "
                  "depth than the textbook; exact cross-ref is at the 6-char section level. Per-path "
                  "question counts are LEXICAL-RELEVANCE ESTIMATES, not ground truth.",
    }
    (OUT / "coverage_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    with (OUT / "path_detail.jsonl").open("w", encoding="utf-8") as fh:
        for r in path_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "FINDING_textbook_question_coverage.md").write_text(_finding(report, path_rows, q), "utf-8")
    return report


def _finding(rep: dict[str, Any], path_rows: list[dict[str, Any]], q: dict[str, Any]) -> str:
    tb, qs = rep["textbook"], rep["questions"]
    xref = rep["section_cross_reference"]
    bcp = rep["block_card_production"]
    lines = [
        "# FINDING — 教材 ↔ 题库 覆盖度报表（path_index 粒度）",
        "",
        f"教材: **{tb['signed_cards']} 张签署卡**，{tb['leaf_nodes']} 个叶子节点 / "
        f"**{tb['taxonomy_paths']} 个 taxonomy_path 子题** / {tb['sections']} 个章节。",
        f"题库: **{qs['total_exercises']} 道题**，{qs['leaf_nodes']} 个叶子节点 / {qs['sections']} 个章节。",
        "",
        "## 1. 章节级精确交叉（可靠口径）",
        f"- 教材与题库都有的章节: **{len(xref['sections_both'])}** 个。",
        f"- ⚠️ **有题但教材零卡的章节: {len(xref['sections_question_but_no_textbook_card'])} 个**（最大缺口，应补教材编译）:",
    ]
    for g in xref["sections_question_but_no_textbook_card"]:
        lines.append(f"  - `{g['section']}*`  {g['example_name']}  — 题库有 **{g['question_count']}** 道题，教材 0 卡")
    lines += [
        f"- 有教材卡但无题的章节: {len(xref['sections_textbook_card_but_no_question'])} 个"
        f"（{xref['sections_textbook_card_but_no_question'] or '无'}）。",
        "",
        "## 2. 教材出卡情况（哪些教材内容没出卡）",
        f"- 含 knowledge_cards 的 block: **{bcp['blocks_with_cards']}** / {bcp['blocks_total']}。",
        f"- 其中 **0 张签署成功的 block: {bcp['blocks_zero_signed']}**（内容在但没出卡）。",
    ]
    for ex in bcp["zero_signed_examples"][:10]:
        lines.append(f"  - `{ex['chunk_id']}` ({ex['taxonomy_path'][:50]}) {ex['cards']} 卡全未签")
    lines += [
        "",
        "## 3. 197 taxonomy_path 明细（按卡数排序，前 20）",
        "| taxonomy_path | 节点 | 卡数 | 本章节题数 | 相关性估算题数 |",
        "|---|---|---:|---:|---:|",
    ]
    for r in path_rows[:20]:
        lines.append(f"| {r['taxonomy_path'][:46]} | {r['node_code']} | {r['card_count']} | "
                     f"{r['section_question_count']} | {r['relevance_estimated_questions']} |")
    lines += [
        "",
        f"- 相关性估算下 **0 道题命中的 taxonomy_path: {len(rep['paths_with_zero_estimated_questions'])}** 个"
        "（教材有内容、题库疑似缺题；启发式，需人工确认）。",
        "",
        "## 口径说明",
        f"> {rep['caveat']}",
        "",
        "## 范围外",
        "未做：题库重打 taxonomy_path 标签（可把估算变精确）、补编译缺口章节、写任何远端/生产。",
    ]
    return "\n".join(lines)


def main() -> int:
    rep = run()
    x = rep["section_cross_reference"]
    print(json.dumps({
        "textbook_paths": rep["textbook"]["taxonomy_paths"],
        "question_exercises": rep["questions"]["total_exercises"],
        "sections_question_but_no_textbook": len(x["sections_question_but_no_textbook_card"]),
        "blocks_zero_signed": rep["block_card_production"]["blocks_zero_signed"],
        "paths_zero_estimated_questions": len(rep["paths_with_zero_estimated_questions"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
