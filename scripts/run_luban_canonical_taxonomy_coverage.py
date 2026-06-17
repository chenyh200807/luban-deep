#!/usr/bin/env python3
"""Living LLM Artifact Compiler — pin textbook cards + questions to the CANONICAL taxonomy (dry-run).

READ-ONLY. The 2026 canonical taxonomy (FINAL_CLEANED_TAXONOMY2026.json) is the authoritative L1-L6
node spine (2393 L6 leaves, keyword-rich). The textbook cards and the question bank were each tagged
to DIFFERENT, inconsistent code systems, so they cannot be joined by code. This dry-run classifies
BOTH onto the canonical leaves by KEYWORD/content match (deterministic, no embedding service) and
reports:
  * classification confidence (how many cards/questions map with strong keyword evidence vs need a
    council pass),
  * coverage at canonical-leaf granularity: leaves with cards AND questions / cards-only (untested) /
    questions-only (no teaching content) / neither,
  * the biggest question-but-no-card leaves (where to direct re-tagging / compile).

Mutates NOTHING (no re-index, no re-sign, no supply write). It only measures whether keyword
classification onto the canonical tree is good enough to drive a later, safe re-index. NO remote / DB.

Usage:
  python scripts/run_luban_canonical_taxonomy_coverage.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "canonical_taxonomy_coverage_20260606"
BUNDLE = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_knowledge_full" / "textbook_knowledge_release_candidate.json"
TAX = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json")
QB_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")


def _load_leaves() -> list[dict[str, Any]]:
    """Flatten the canonical tree to its keyword-bearing classification nodes (L5 + L6), each with the
    full name path (L1>..>Ln) for human-readable reporting."""
    d = json.loads(TAX.read_text("utf-8"))
    leaves: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], trail: list[str]) -> None:
        name_trail = trail + [str(node.get("name") or "")]
        kws = node.get("keywords") or []
        if kws and node.get("level") in (5, 6):
            leaves.append({
                "code": str(node.get("code") or ""),
                "name": str(node.get("name") or ""),
                "level": node.get("level"),
                "name_path": " > ".join(t for t in name_trail if t),
                "keywords": [str(k) for k in kws],
            })
        for c in node.get("children") or []:
            walk(c, name_trail)

    for root in d.get("outline_structure", []):
        walk(root, [])
    return leaves


def _classify(text: str, leaves: list[dict[str, Any]]) -> tuple[str, int]:
    """Best canonical leaf for ``text`` by keyword hit count. Returns (leaf_code, hits). hits==0 -> the
    text matched no canonical keyword (low confidence -> a council pass would decide). Deterministic
    tie-break by leaf code; prefers the deeper (L6) leaf on a tie via code length."""
    best_code, best_hits = "", 0
    for lf in leaves:
        hits = sum(1 for k in lf["keywords"] if k and k in text)
        if hits > best_hits or (hits == best_hits and hits > 0 and len(lf["code"]) > len(best_code)):
            best_code, best_hits = lf["code"], hits
    return best_code, best_hits


def _load_textbook_cards() -> list[dict[str, Any]]:
    b = json.loads(BUNDLE.read_text("utf-8"))
    return [{"point_id": r.get("point_id"), "old_node": r.get("node_code"),
             "text": " ".join(str(r.get(k) or "") for k in ("textbook_quote", "taxonomy_path"))}
            for r in b["records"]]


def _load_questions() -> list[dict[str, Any]]:
    qs: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(QB_DIR / "**" / "*.json"), recursive=True)):
        try:
            d = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for ch in d.get("chunks", []):
            for e in ch.get("exercises") or []:
                qd = e.get("question_data") if isinstance(e.get("question_data"), dict) else {}
                stem = str(qd.get("stem") or "")
                if stem:
                    qs.append({"stem": stem})
    return qs


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    leaves = _load_leaves()
    by_code = {lf["code"]: lf for lf in leaves}
    cards = _load_textbook_cards()
    questions = _load_questions()

    card_by_leaf: dict[str, int] = {}
    card_conf = {"strong": 0, "weak": 0, "none": 0}  # >=2 hits / 1 hit / 0
    for c in cards:
        code, hits = _classify(c["text"], leaves)
        card_conf["strong" if hits >= 2 else "weak" if hits == 1 else "none"] += 1
        if hits:
            card_by_leaf[code] = card_by_leaf.get(code, 0) + 1

    q_by_leaf: dict[str, int] = {}
    q_conf = {"strong": 0, "weak": 0, "none": 0}
    for q in questions:
        code, hits = _classify(q["stem"], leaves)
        q_conf["strong" if hits >= 2 else "weak" if hits == 1 else "none"] += 1
        if hits:
            q_by_leaf[code] = q_by_leaf.get(code, 0) + 1

    card_leaves = set(card_by_leaf)
    q_leaves = set(q_by_leaf)
    both = card_leaves & q_leaves
    cards_only = card_leaves - q_leaves
    q_only = q_leaves - card_leaves

    def _name(code: str) -> str:
        return by_code.get(code, {}).get("name_path", code)

    q_only_top = sorted(
        [{"code": c, "name_path": _name(c), "questions": q_by_leaf[c]} for c in q_only],
        key=lambda x: -x["questions"])[:30]
    cards_only_top = sorted(
        [{"code": c, "name_path": _name(c), "cards": card_by_leaf[c]} for c in cards_only],
        key=lambda x: -x["cards"])[:30]

    report = {
        "canonical_leaves_total": len(leaves),
        "canonical_leaves_with_cards": len(card_leaves),
        "canonical_leaves_with_questions": len(q_leaves),
        "textbook_cards": len(cards),
        "questions": len(questions),
        "card_classification_confidence": card_conf,
        "question_classification_confidence": q_conf,
        "leaves_cards_and_questions": len(both),
        "leaves_cards_only_untested": len(cards_only),
        "leaves_questions_only_no_card": len(q_only),
        "questions_only_top": q_only_top,
        "cards_only_top": cards_only_top,
        "note": "DRY-RUN classification by canonical keywords; no re-index, no re-sign. 'none' confidence "
                "rows are the council backlog. Coverage is at canonical L5/L6 leaf granularity.",
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_canonical_coverage.md").write_text(_finding(report), "utf-8")
    return report


def _finding(r: dict[str, Any]) -> str:
    cc, qc = r["card_classification_confidence"], r["question_classification_confidence"]
    lines = [
        "# FINDING — 把教材卡+题目挂到 canonical taxonomy（dry-run，只读）",
        "",
        f"canonical 叶子(L5+L6,带keywords): **{r['canonical_leaves_total']}**。",
        f"教材卡 {r['textbook_cards']} 张 → 命中 {r['canonical_leaves_with_cards']} 个叶子；"
        f"题目 {r['questions']} 道 → 命中 {r['canonical_leaves_with_questions']} 个叶子。",
        "",
        "## 关键词分类置信度（确定性方法够不够的关键）",
        f"- 教材卡: 强({cc['strong']}) / 弱({cc['weak']}) / 无命中→council({cc['none']})",
        f"- 题目:   强({qc['strong']}) / 弱({qc['weak']}) / 无命中→council({qc['none']})",
        "",
        "## 叶子级覆盖（canonical L5/L6 粒度，精确）",
        f"- 既有卡又有题: **{r['leaves_cards_and_questions']}**",
        f"- 只有卡、无题(教材有内容没题考): **{r['leaves_cards_only_untested']}**",
        f"- 只有题、无卡(有题没教材内容): **{r['leaves_questions_only_no_card']}**",
        "",
        "## 有题但无教材卡 — 前 15（应补/重挂教材内容）",
        "| canonical 叶子 | 题数 |",
        "|---|---:|",
    ]
    for x in r["questions_only_top"][:15]:
        lines.append(f"| {x['name_path'][:60]} | {x['questions']} |")
    lines += [
        "",
        "## 有教材卡但无题 — 前 10（教材内容暂未被考）",
        "| canonical 叶子 | 卡数 |",
        "|---|---:|",
    ]
    for x in r["cards_only_top"][:10]:
        lines.append(f"| {x['name_path'][:60]} | {x['cards']} |")
    lines += ["", "## 口径", f"> {r['note']}"]
    return "\n".join(lines)


def main() -> int:
    r = run()
    print(json.dumps({
        "canonical_leaves": r["canonical_leaves_total"],
        "card_strong+weak": r["card_classification_confidence"]["strong"] + r["card_classification_confidence"]["weak"],
        "card_none": r["card_classification_confidence"]["none"],
        "q_strong+weak": r["question_classification_confidence"]["strong"] + r["question_classification_confidence"]["weak"],
        "q_none": r["question_classification_confidence"]["none"],
        "leaves_q_no_card": r["leaves_questions_only_no_card"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
