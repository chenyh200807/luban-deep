#!/usr/bin/env python3
"""Living LLM Artifact Compiler — unify all four content sources onto the canonical taxonomy (Phase 1).

Loads the canonical 2026 taxonomy and the four sources (textbook verbatim cards, GB/JGJ standards,
佑森 lecture notes, 题库 questions), classifies every unit onto a canonical L5/L6 leaf
(``canonical_taxonomy``), and aggregates per node preserving authority tiers (``knowledge_unification``).

Output (all under artifacts, READ-ONLY w.r.t. every source):
  * unified_knowledge_bundle.json — node-keyed map {textbook + standard + lecture + question per leaf}
  * coverage_report.json / FINDING — canonical-granularity coverage + per-source classification stats
  * unclassified_backlog.jsonl — the units no deterministic rule placed (the targeted LLM-pass tail)

Deterministic spine only. The LLM tail (unclassified) + adversarial QA run as a separate workflow.
NO re-sign (textbook keeps its verbatim signatures), NO remote / DB / production.

Usage:
  python scripts/run_luban_canonical_knowledge_unification.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "canonical_unified_knowledge_20260606"
BUNDLE = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_knowledge_full" / "textbook_knowledge_release_candidate.json"
DATA = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
TAX_PATH = DATA / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json"

from deeptutor.services.construction_grading import knowledge_unification as KU  # noqa: E402
from deeptutor.services.construction_grading.canonical_taxonomy import (
    CanonicalTaxonomy,  # noqa: E402
)


def _textbook_units() -> list[KU.Unit]:
    b = json.loads(BUNDLE.read_text("utf-8"))
    out = []
    for r in b.get("records", []):
        out.append(KU.Unit(
            source="textbook", unit_id=str(r.get("point_id")), native_code=str(r.get("node_code") or ""),
            authority_tier=KU.TIER_TEXTBOOK,
            text=" ".join(str(r.get(k) or "") for k in ("textbook_quote", "taxonomy_path")),
            provenance={"chunk_id": r.get("chunk_id"), "content_hash": r.get("content_hash"),
                        "signed": True}))
    return out


# Standards carry NO native node_code, so global-keyword classification mis-files them badly (adversarial
# QA: ~all wrong). Each standard FILE is a single technical domain — anchor it to the canonical 施工技术
# / 建筑设计 subtree where the textbook + questions on that topic ALSO live, so a standard clause
# aggregates with its matching textbook/question on the SAME node. Keyword then refines within the
# anchored subtree (anchor+keyword is QA-reliable).
_STANDARD_ANCHORS: dict[str, str] = {
    "GB55003": "1A413030", "GB+51004": "1A413030", "GB51004": "1A413030",  # 地基基础 -> 地基与基础工程施工
    "JGJ120": "1A413020",                                                   # 基坑支护 -> 土石方工程施工
    "GB+50207": "1A413050", "GB50207": "1A413050",                          # 屋面 -> 屋面与防水工程施工
    "GB50210": "1A413060",                                                  # 装饰装修验收 -> 装饰装修工程施工
    "GB50352": "1A411010",                                                  # 民用建筑设计 -> 建筑设计
    "GB50354": "1A413060",                                                  # 内部装修防火 -> 装饰装修工程施工
    "GBT51366": "1A437000",                                                 # 碳排放 -> 绿色建造
}


def _standard_anchor(filename: str) -> str:
    for key, code in _STANDARD_ANCHORS.items():
        if key in filename:
            return code
    return ""


def _standard_units() -> list[KU.Unit]:
    out = []
    for f in sorted(glob.glob(str(DATA / "标准文件" / "*.json"))):
        try:
            d = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        anchor = _standard_anchor(Path(f).name)
        stem = Path(f).stem
        for i, cb in enumerate(d.get("content_blocks") or []):
            sc = cb.get("source_context") or {}
            text = str(sc.get("origin_text") or "")
            if not text.strip():
                continue
            # standards content_block ``id`` is NOT unique across files (e.g. "UNKNOWN_000_0001"
            # repeats), so qualify it with the file stem + running index to make a globally unique id.
            raw_id = str(cb.get("id") or cb.get("chunk_id") or i)
            out.append(KU.Unit(
                source="standard", unit_id=f"{stem}::{raw_id}::{i}",
                native_code=anchor, authority_tier=KU.TIER_STANDARD, text=text,
                provenance={"standard_code": sc.get("standard_code"), "article_id": sc.get("article_id"),
                            "is_mandatory": sc.get("is_mandatory"), "node_type": cb.get("node_type"),
                            "anchor": anchor}))
    return out


def _lecture_units() -> list[KU.Unit]:
    out = []
    for topic_dir in sorted(glob.glob(str(DATA / "讲义" / "*"))):
        if not Path(topic_dir).is_dir():
            continue
        mains = [f for f in glob.glob(topic_dir + "/*.json") if "/page_" not in f]
        for f in mains:
            try:
                d = json.loads(Path(f).read_text("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for ch in (d if isinstance(d, list) else []):
                if not isinstance(ch, dict):
                    continue
                text = str(ch.get("content_markdown") or "")
                if not text.strip():
                    continue
                tax = ch.get("taxonomy") or {}
                out.append(KU.Unit(
                    source="lecture", unit_id=str(ch.get("chunk_id") or ""),
                    native_code=str(tax.get("node_code") or ""), authority_tier=KU.TIER_LECTURE,
                    text=text, provenance={"topic": tax.get("topic"), "lecture": Path(topic_dir).name[:30]}))
    return out


def _question_units() -> list[KU.Unit]:
    out = []
    for f in sorted(glob.glob(str(DATA / "题库" / "**" / "*.json"), recursive=True)):
        try:
            d = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        src = Path(f).parent.name
        for ch in d.get("chunks", []):
            cid = str(ch.get("chunk_id") or "")
            ch_node = str((ch.get("taxonomy") or {}).get("node_code") or "")
            for i, e in enumerate(ch.get("exercises") or []):
                qd = e.get("question_data") if isinstance(e.get("question_data"), dict) else {}
                stem = str(qd.get("stem") or "")
                if not stem.strip():
                    continue
                pn = e.get("predicted_node")
                native = pn if isinstance(pn, str) else ch_node
                out.append(KU.Unit(
                    source="question", unit_id=f"{cid}::E{i}", native_code=native,
                    authority_tier=KU.TIER_QUESTION, text=stem,
                    provenance={"source": src, "predicted_node": native}))
    return out


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    tax = CanonicalTaxonomy.load(TAX_PATH)
    units = (_textbook_units() + _standard_units() + _lecture_units() + _question_units())
    by_source: dict[str, int] = {}
    for u in units:
        by_source[u.source] = by_source.get(u.source, 0) + 1

    result = KU.unify(tax, units)
    bundle = KU.build_unified_bundle(tax, result)

    (OUT / "unified_knowledge_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), "utf-8")
    with (OUT / "unclassified_backlog.jsonl").open("w", encoding="utf-8") as fh:
        for u in result["unclassified"]:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")

    cov = result["coverage"]
    report = {
        "units_by_source": by_source,
        "units_total": len(units),
        "classification_stats": result["stats"],
        "unclassified_total": len(result["unclassified"]),
        "coverage": cov,
        "name_paths_question_no_knowledge": [tax.name_path(c) for c in cov["leaves_question_no_knowledge"][:40]],
    }
    (OUT / "coverage_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_canonical_unification.md").write_text(_finding(report, bundle, tax), "utf-8")
    return report


def _finding(rep: dict[str, Any], bundle: dict[str, Any], tax: CanonicalTaxonomy) -> str:
    cov = rep["coverage"]
    st = rep["classification_stats"]
    def _pct(s):
        tot = sum(st.get(s, {}).values()) or 1
        ok = tot - st.get(s, {}).get("unclassified", 0)
        return f"{ok}/{tot} ({ok/tot*100:.1f}%)"
    lines = [
        "# FINDING — 四类源统一挂到 canonical taxonomy（Phase 1，确定性脊柱）",
        "",
        f"canonical 叶子: **{cov['canonical_leaves_total']}** | 已落子: **{cov['leaves_populated']}**。",
        f"单元总数 **{rep['units_total']}**: " + "，".join(f"{k}={v}" for k, v in rep["units_by_source"].items()) + "。",
        "",
        "## 确定性分类命中率（每源）",
        f"- 教材: {_pct('textbook')}",
        f"- 标准: {_pct('standard')}",
        f"- 讲义: {_pct('lecture')}",
        f"- 题库: {_pct('question')}",
        f"- 未分类（LLM 尾部）合计: **{rep['unclassified_total']}**",
        "",
        "## 叶子级覆盖（canonical 精确口径）",
        f"- 有教材: {cov['leaves_with_textbook']} | 有标准: {cov['leaves_with_standard']} | "
        f"有讲义: {cov['leaves_with_lecture']} | 有题: {cov['leaves_with_question']}",
        f"- 有题且有知识(教材/标准/讲义任一): **{cov['leaves_question_with_knowledge']}**",
        f"- ⚠️ 有题但无任何知识源: **{len(cov['leaves_question_no_knowledge'])}**（真缺口，应补内容）",
        f"- 有知识但无题: {cov['leaves_knowledge_no_question']}（教材/规范有、暂未考）",
        "",
        "## 有题但无任何知识源 — 前 20（真缺口）",
    ]
    for nm in rep["name_paths_question_no_knowledge"][:20]:
        lines.append(f"- {nm}")
    lines += [
        "",
        "## 统一节点示例（一个知识点拿到四类源）",
    ]
    rich = sorted(bundle["nodes"].items(),
                  key=lambda kv: sum(1 for s in ("textbook", "standard", "lecture", "question") if kv[1]["counts"][s]),
                  reverse=True)[:3]
    for code, n in rich:
        c = n["counts"]
        lines.append(f"- `{code}` {n['name_path'][:50]} → 教材{c['textbook']}/标准{c['standard']}/讲义{c['lecture']}/题{c['question']}")
    lines += ["", "## 范围/口径",
              "> 确定性脊柱。未分类尾部 + 抽样准确率由 workflow 兜底。统一=挂载聚合，不重签；标准逐字签名为后续独立 lane。"]
    return "\n".join(lines)


def main() -> int:
    r = run()
    cov = r["coverage"]
    print(json.dumps({
        "units": r["units_total"], "by_source": r["units_by_source"],
        "leaves_populated": cov["leaves_populated"], "unclassified": r["unclassified_total"],
        "leaves_question_no_knowledge": len(cov["leaves_question_no_knowledge"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
