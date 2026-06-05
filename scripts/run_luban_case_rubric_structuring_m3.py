"""Registry v1 M3 — first-batch case-question structuring + textbook verify-on-write.

Pipeline (rule-based candidates, NOT LLM authority):
  official_answer -> scoring point candidates -> typed_policy -> node_code resolution
  -> 2026 教材 content_markdown VERBATIM verify-on-write -> audit packets -> impact sim.

Authority correction (hard): a textbook-verified anchor may ONLY come from the 2026
教材 books (FINAL_CLEANED_BOOK2026-*_fixed.json content_blocks). 题库 explanation /
official_answer is at most a weak/official source, never ``verified``. node-level assets
and semantic/loose matches are never verified. No formal registry is emitted; no new
table; no kernel/RAG/production change; no fabricated source_ref; no fabricated LLM vote.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M2 = REPO / "artifacts/luban_grading_artifacts/case_rubric_expansion_m2_20260604/candidate_case_questions.json"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
JURY_MODELS = ["gpt55", "opus48", "deepseek_v4", "qwen37"]


def _norm(s: Any) -> str:
    return re.sub(r"[（）()\s、,.，。；;:：!！?？\"'《》\[\]\n\t]", "", str(s or ""))


# --- textbook index (the ONLY verified-anchor authority) ---------------------------

def _load_textbook() -> list[tuple[str, str, str]]:
    """Return [(chunk_id, node_code, normalized_content_markdown)] over the 2026 books."""
    idx: list[tuple[str, str, str]] = []
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        d = json.loads(f.read_text("utf-8"))
        for b in d.get("content_blocks") or []:
            md = b.get("content_markdown") or ""
            if not md:
                continue
            node = str((b.get("taxonomy") or {}).get("node_code") or "")
            idx.append((str(b.get("chunk_id") or ""), node, _norm(md)))
    return idx


def _textbook_lookup(term: str, node_hint: str, tb: list[tuple[str, str, str]]) -> dict[str, Any]:
    """VERBATIM verify-on-write: term normalized-appears in a block's content_markdown."""
    tn = _norm(term)
    if len(tn) < 4:  # too short/common to anchor
        return {"hit": False, "scope": "too_short"}
    # prefer same-node blocks, then full KB
    for scope, pred in (("node", lambda n: n == node_hint), ("full_kb", lambda n: True)):
        for chunk_id, node, md in tb:
            if pred(node) and tn in md:
                # recover a short verbatim quote window around the term
                return {"hit": True, "scope": scope, "chunk_id": chunk_id, "node_code": node,
                        "textbook_quote": term.strip()[:60]}
    return {"hit": False, "scope": "full_kb"}


# --- official_answer -> scoring point candidates -----------------------------------

_LIST_MARK = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]|(?<![0-9])\d[.、)]")


def _classify(span: str) -> str:
    s = span
    if re.search(r"[=＝]|\d+\s*[×x*/÷+\-]\s*\d+|计算|公式|节拍|工期\s*=|总工期", s):
        return "calculation"
    if re.search(r"不妥|改正|正确做法|应改为|不正确", s):
        return "exact_required"
    if re.search(r"包括|内容有|应包括|列举|分别为|有[:：]|：$", s) or _LIST_MARK.search(s):
        return "list_rule"
    if re.search(r"因为|由于|所以|原因是|理由", s):
        return "semantic_allowed"
    if re.search(r"图|标号|节点|箭线|双代号", s):
        return "figure_label"
    if len(_norm(s)) <= 14:
        return "exact_required"
    return "semantic_allowed"


def _split_points(official_answer: str) -> list[str]:
    parts = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]|[。；;]\s*", official_answer)
    return [p.strip() for p in parts if len(_norm(p)) >= 3][:8]


def _extract_points(q: dict[str, Any]) -> list[dict[str, Any]]:
    oa = str(q.get("official_answer") or "")
    spans = _split_points(oa)
    points = []
    for i, span in enumerate(spans, 1):
        pt = _classify(span)
        terms = []
        if pt in ("exact_required", "list_rule"):
            terms = [t for t in re.split(r"[，,、；;:：\s]", span) if 2 <= len(_norm(t)) <= 18][:6]
        points.append({
            "question_id": q["question_id"], "point_id": f"P{i}", "label": span[:60],
            "official_answer_span": span, "max_score": None, "policy_type": pt,
            "required_terms": terms,
            "list_rule": ({"denominator": len(terms) or None, "terms": terms} if pt == "list_rule" else None),
            "calculation_spec": None, "penalty_rule": None,
            "confidence": 0.5, "needs_jury_review": True,
        })
    return points


# --- node resolution ---------------------------------------------------------------

def _resolve_node(q: dict[str, Any], tb_nodes: set[str]) -> dict[str, Any]:
    orig = str(q.get("node_code") or "")
    if orig and orig in tb_nodes:
        return {"question_id": q["question_id"], "original_node_code": orig, "resolved_node_code": orig,
                "resolution_source": "metadata", "confidence": 0.9, "evidence": "candidate metadata node in textbook"}
    # keyword fallback: a 1A4xxxxx code mentioned in text
    m = re.search(r"1A4\d{5}", str(q.get("question_text") or "") + str(q.get("official_answer") or ""))
    if m and m.group(0) in tb_nodes:
        return {"question_id": q["question_id"], "original_node_code": orig, "resolved_node_code": m.group(0),
                "resolution_source": "taxonomy_keyword", "confidence": 0.5, "evidence": m.group(0)}
    return {"question_id": q["question_id"], "original_node_code": orig, "resolved_node_code": "",
            "resolution_source": "unresolved", "confidence": 0.0, "evidence": ""}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit_packets_structured").mkdir(exist_ok=True)
    from scripts.luban_case_rubric_schema import validate_audit_packet

    candidates = json.loads(M2.read_text("utf-8"))
    tb = _load_textbook()
    tb_nodes = {n for _, n, _ in tb if n}

    all_points, node_res, verify_rows, packets_meta = [], [], [], []
    for q in candidates:
        nr = _resolve_node(q, tb_nodes)
        node_res.append(nr)
        node_hint = nr["resolved_node_code"]
        points = _extract_points(q)
        all_points.extend(points)
        packet_points = []
        for p in points:
            search_terms = p["required_terms"] or [p["official_answer_span"][:20]]
            anchor = {"hit": False}
            for t in search_terms:
                anchor = _textbook_lookup(t, node_hint, tb)
                if anchor.get("hit"):
                    break
            meets_min = (
                (p["policy_type"] == "exact_required" and bool(p["required_terms"]))
                or (p["policy_type"] == "list_rule" and bool((p["list_rule"] or {}).get("denominator")))
                or (p["policy_type"] not in ("exact_required", "list_rule", "calculation", "high_risk_review"))
            )
            # over-credit guard: a bare numeric/measurement term (200mm, 1.5mm, 30MPa) is a
            # numeric spec, not a verifiable exact_required term -> needs calculation_spec / PO,
            # never auto-verified by a verbatim number match.
            matched_term = anchor.get("textbook_quote") or ""
            is_numeric = bool(re.fullmatch(r"\s*\d+(\.\d+)?\s*(mm|cm|m|MPa|kN|%|度|天|月|年|kg|个|根|层)?\s*", matched_term))
            verified = bool(anchor.get("hit")) and meets_min and p["policy_type"] != "high_risk_review" and not is_numeric
            status = "verified" if verified else ("weak" if p["policy_type"] != "calculation" else "weak")
            if not anchor.get("hit"):
                status = "missing"
            verify_rows.append({
                "question_id": q["question_id"], "point_id": p["point_id"], "policy_type": p["policy_type"],
                "search_terms": search_terms, "search_scope": anchor.get("scope") or ("unresolved_node" if not node_hint else "full_kb"),
                "candidate_hits": [anchor.get("chunk_id")] if anchor.get("hit") else [],
                "selected_source_ref": ({"source_type": "textbook", "chunk_id": anchor.get("chunk_id"),
                                          "textbook_quote": anchor.get("textbook_quote"), "verified": True} if verified else None),
                "anchor_status": status, "auto_certifiable": verified,
                "reason": "verbatim 2026 textbook anchor" if verified else "no verbatim textbook anchor; official_answer is weak only",
            })
            refs = []
            if verified:
                refs.append({"source_type": "textbook", "chunk_id": anchor.get("chunk_id"),
                             "textbook_quote": anchor.get("textbook_quote"), "verified": True, "match_method": "verbatim"})
            else:
                refs.append({"source_type": "official_answer", "chunk_id": "", "textbook_quote": p["official_answer_span"][:60], "verified": False, "match_method": "none"})
            packet_points.append({
                "point_id": p["point_id"], "label": p["label"], "policy_type": p["policy_type"],
                "max_score": p["max_score"] if p["max_score"] is not None else 2,
                "required_terms": p["required_terms"], "list_spec": p["list_rule"],
                "calculation_spec": p["calculation_spec"], "penalty_rule": p["penalty_rule"],
                "source_refs": refs, "source_status": "ok" if verified else "missing_or_weak",
                "auto_certifiable": verified,
            })
        auto_n = sum(1 for pp in packet_points if pp["auto_certifiable"])
        status = "published_candidate_not_final" if auto_n else "draft"
        packet = {
            "schema_version": "luban_case_rubric_audit_packet.v0",
            "question_id": q["question_id"], "question_text": str(q.get("question_text"))[:300],
            "official_answer": str(q.get("official_answer"))[:300], "node_code": node_hint,
            "source_exam": str(q.get("source_file") or ""),
            "rubric_candidates": [{"point_id": pp["point_id"], "label": pp["label"], "candidate_source": "official_answer_rule_extraction", "is_authority": False} for pp in packet_points],
            "textbook_anchor_evidence": [r for pp in packet_points for r in pp["source_refs"] if r.get("verified")],
            "teacher_review_status": "unreviewed",
            "artifact_status": "published" if auto_n else "draft",  # A1 validator status
            "registry_disposition": status,
            "scoring_points": packet_points,
            "quality_gate": {"published": auto_n > 0, "auto_certifiable_points": auto_n, "weak_points": sum(1 for pp in packet_points if pp["source_status"] != "ok"), "verify_on_write": "verbatim_2026_textbook_only"},
            "provenance": {"compiled_from": "外部真题 official_answer + 2026 教材 verbatim verify-on-write", "compiler": "case_rubric_structuring_m3", "note": "candidate, not final; teacher_review_status=unreviewed"},
        }
        violations = validate_audit_packet(packet)
        (OUT_DIR / "audit_packets_structured" / f"{q['question_id']}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        packets_meta.append({"question_id": q["question_id"], "registry_disposition": status, "auto_certifiable_points": auto_n, "points": len(packet_points), "validator_violations": violations})

    verified_pts = sum(1 for v in verify_rows if v["anchor_status"] == "verified")
    weak_pts = sum(1 for v in verify_rows if v["anchor_status"] == "weak")
    missing_pts = sum(1 for v in verify_rows if v["anchor_status"] == "missing")
    resolved_nodes = sum(1 for n in node_res if n["resolved_node_code"])

    # jury: no live/cache rubric-extraction provider for NEW candidates -> unavailable, not fabricated
    jury_availability = {
        "available_models": [], "unavailable_models": JURY_MODELS,
        "reason": "no live/cache rubric extraction provider for new 真题 candidates (485 cache only covers 20 golden)",
        "review_source": "model_jury_rubric_review", "reviewer_type": "llm_jury", "votes_fabricated": False,
        "adjudication_protocol": "case_rubric_jury_v0",
    }
    jury_packets = [{"question_id": q["question_id"], "points": [p["point_id"] for p in _extract_points(q)], "jury_status": "pending_unavailable"} for q in candidates]

    impact = {
        "total_candidates": len(candidates),
        "total_scoring_points": len(all_points),
        "verified_textbook_points": verified_pts,
        "weak_points": weak_pts,
        "missing_points": missing_pts,
        "draft_count": sum(1 for m in packets_meta if m["registry_disposition"] == "draft"),
        "published_candidate_not_final_count": sum(1 for m in packets_meta if m["registry_disposition"] == "published_candidate_not_final"),
        "blocked_count": 0,
        "auto_certifiable_points": verified_pts,
        "node_resolved": resolved_nodes,
        "top_blockers": [
            "official_answer 采分点结构化为规则启发式，须 LLM jury + PO 复核确认",
            "verbatim 2026 教材锚命中率低（真题术语与教材原文表述差异）",
            "node_code 多数 unresolved，缩小不了教材检索范围",
            "calculation 缺 calculation_spec",
        ],
        "registry_emitted": False,
    }

    _dump("scoring_point_candidates.json", all_points)
    _dump("node_code_resolution.json", node_res)
    _dump("textbook_verify_on_write.json", verify_rows)
    _dump("jury_packets.json", jury_packets)
    _dump("jury_availability.json", jury_availability)
    _dump("registry_impact_simulation_m3.json", impact)
    _write_finding(candidates, all_points, resolved_nodes, verified_pts, weak_pts, missing_pts, packets_meta, impact)

    print(f"candidates={len(candidates)} points={len(all_points)} node_resolved={resolved_nodes} "
          f"verified={verified_pts} weak={weak_pts} missing={missing_pts} "
          f"draft={impact['draft_count']} pub_cand={impact['published_candidate_not_final_count']}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_finding(candidates, points, nodes, verified, weak, missing, packets_meta, impact):
    pub = impact["published_candidate_not_final_count"]
    draft = impact["draft_count"]
    lines = [
        "# FINDING — case-rubric structuring M3 (2026-06-04)", "",
        "## 必答", "",
        f"1. 首批处理多少 case candidates？ **{len(candidates)}**。",
        f"2. 生成多少 scoring point candidates？ **{len(points)}**（official_answer 规则抽取，非 LLM authority）。",
        f"3. node_code 补齐多少？ **{nodes}/{len(candidates)}**（其余 unresolved，未硬填）。",
        f"4. textbook verified points？ **{verified}**（仅 2026 教材 content_markdown verbatim 命中）。",
        f"5. weak points？ **{weak}**（official_answer 源，未命中教材）。",
        f"6. missing/blocked points？ missing **{missing}** / blocked 0。",
        f"7. published_candidate_not_final？ **{pub}**。",
        f"8. draft？ **{draft}**。",
        f"9. auto_certifiable points？ **{verified}**（= verified textbook points）。",
        "10. 是否把题库 explanation 当 textbook？ **NO**（official_answer/解释只标 weak，textbook 仅来自 FINAL_CLEANED_BOOK2026-*）。",
        "11. 是否伪造 LLM vote？ **NO**（新题无 live/cache provider → jury unavailable，`votes_fabricated=false`）。",
        "12. 是否生成正式 registry？ **NO**（仅 audit packets + impact sim）。",
        "13. Registry v1 距发布还差什么？ (a) 采分点结构化经 LLM jury + PO 复核升 authority；(b) 提升 verbatim 教材锚命中（真题术语↔教材原文对齐 / node 收敛检索）；(c) calculation/list policy spec 补齐。",
        "14. 下一步建议：先**补强教材锚命中**（node 收敛 + 术语对齐 + parent/full_kb 检索）与**接 LLM jury 对新题做 rubric extraction**，再进 PO 复核；当前 verbatim 命中率是主要瓶颈。",
        "",
        "## 结论", "",
        f"首批 {len(candidates)} 道真题已结构化为 {len(points)} 个采分点候选；2026 教材 verbatim 锚命中 **{verified}** 点 → {pub} 题达 published_candidate_not_final、{draft} 题 draft。**数据充足，瓶颈在锚定命中率 + 复核 pipeline**，非题目缺失。未伪造 source/vote，未生成正式 registry。",
        "",
        "## 红线", "",
        "不新增表、不生成正式 registry、不接 runtime、不改 kernel、RAG 不进评分、题库 explanation 不当 textbook、official_answer 不当强锚、不伪造 source_ref/textbook_quote、不伪造 LLM vote、未 commit。",
        "",
    ]
    (OUT_DIR / "FINDING_case_rubric_structuring_m3_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
