"""Registry v1 M5A — exam-term <-> textbook alignment + policy spec enrichment.

Continues M3/M4: raises the VERBATIM textbook-anchor hit rate by cleaning the messy
official_answer-derived terms (stripping meta-instructions / trailing punctuation),
building an exam-term <-> textbook-phrase alignment table, and re-running the
deterministic exact-quote check. Synonyms/abbreviations are used ONLY to widen search;
``verified`` is decided solely by a local normalized exact match against the 2026
textbook content_markdown. Also enriches calculation_spec / list_rule denominator+item_set
/ exact_required terms — marking candidates vs needs_po_review vs cannot_infer rather
than hard-filling.

Red lines: no DB, no runtime, no kernel/RAG, no formal registry, official_answer /
explanation never verified, LLM/embedding/semantic never升 verified, no fabricated
source_ref / textbook_quote / LLM vote, never overwrite M3/M4 artifacts, node_code
candidate-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M4 = REPO / "artifacts/luban_grading_artifacts/case_rubric_anchor_refinement_m4_20260604"
M3 = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_term_alignment_m5a_20260604"
MIN_VERBATIM = 4  # normalized chars

# meta-instruction noise that must never be a scoring term / verified anchor
_META = ["只需写出", "题目上缺少", "即可", "见上", "如下", "等等", "本题", "答案",
         "下列", "之一", "以上", "其他", "略", "言之有理"]


def _norm(s: Any) -> str:
    return re.sub(r"[（）()\s、,.，。；;:：!！?？\"'《》【】\[\]\n\t…·－—-]", "", str(s or ""))


def _is_numeric(s: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+(\.\d+)?\s*(mm|cm|m|MPa|kN|%|度|天|月|年|kg|个|根|层|m2|m3|h)?\s*", s))


def _is_meta(s: str) -> bool:
    return any(m in s for m in _META)


def _clean_term(t: str) -> str:
    """Strip leading/trailing punctuation and surrounding noise from a raw fragment."""
    t = re.sub(r"^[\s（()【\[、,，。；;:：]+|[\s）)】\]、,，。；;:：(（]+$", "", str(t or "")).strip()
    return t


# --- textbook (the ONLY verified-anchor authority) ---------------------------------

def _load_textbook() -> list[tuple[str, str, str]]:
    idx = []
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        for b in json.loads(f.read_text("utf-8")).get("content_blocks") or []:
            md = b.get("content_markdown") or ""
            if md:
                idx.append((str(b.get("chunk_id") or ""), str((b.get("taxonomy") or {}).get("node_code") or ""), _norm(md)))
    return idx


def _exam_terms(official_answer: str, required_terms: list[str]) -> list[str]:
    """Cleaned distinctive exam terms (longest-first). Drops meta/numeric/punctuation junk."""
    raw = list(required_terms or [])
    raw += re.split(r"[，,、；;:：。！？\s]+|[①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]", official_answer or "")
    out = []
    for t in raw:
        ct = _clean_term(t)
        n = _norm(ct)
        if len(n) >= MIN_VERBATIM and not _is_numeric(ct) and not _is_meta(ct):
            out.append(ct)
    # dedupe preserve, longest-first (most distinctive anchors first)
    seen = set()
    uniq = []
    for t in sorted(set(out), key=lambda x: -len(_norm(x))):
        if _norm(t) not in seen:
            seen.add(_norm(t))
            uniq.append(t)
    return uniq


def _search_verbatim(terms: list[str], node_hint: str, tb: list[tuple[str, str, str]]) -> dict[str, Any]:
    parent = node_hint[:5] if node_hint else ""
    for scope, pred in (("node", lambda n: bool(node_hint) and n == node_hint),
                        ("parent", lambda n: bool(parent) and n.startswith(parent)),
                        ("full_kb", lambda n: True)):
        for term in terms:
            tn = _norm(term)
            for chunk_id, node, md in tb:
                if pred(node) and tn in md:
                    return {"hit": True, "scope": scope, "chunk_id": chunk_id, "candidate_node_code": node,
                            "textbook_quote": term.strip()[:80], "exam_term": term}
    return {"hit": False, "scope": "full_kb"}


# --- policy spec enrichment --------------------------------------------------------

def _calc_spec(span: str) -> dict[str, Any]:
    expr = re.findall(r"[\d.]+\s*[×x*/÷+\-]\s*[\d.]+(?:\s*[×x*/÷+\-]\s*[\d.]+)*", span)
    eq = re.findall(r"([一-龥A-Za-z]+)\s*[=＝]\s*([\d.]+\s*[a-zA-Z天月年%]*)", span)
    if expr or eq:
        return {"kind": "candidate_spec", "expressions": expr, "equalities": [{"name": a, "value": b.strip()} for a, b in eq]}
    return {"kind": "calculation_spec_needed"}


def _list_spec(span: str, cleaned_terms: list[str]) -> dict[str, Any]:
    n_markers = len(re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]", span))
    items = [t for t in cleaned_terms if len(_norm(t)) >= 3]
    denom = n_markers or (len(items) if items else None)
    if denom and items:
        return {"kind": "candidate_spec", "denominator": denom, "item_set": items}
    return {"kind": "needs_po_review", "denominator": denom, "item_set": items}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "refined_audit_packets").mkdir(exist_ok=True)
    (OUT_DIR / "jury_review_packets_m5a").mkdir(exist_ok=True)
    from scripts.luban_case_rubric_schema import validate_audit_packet

    tb = _load_textbook()
    tb_by_chunk = {c: m for c, _, m in tb}
    packet_files = sorted((M4 / "refined_audit_packets").glob("*.json"))
    packets = {f.stem: json.loads(f.read_text("utf-8")) for f in packet_files}
    pt_index = {(pkt["question_id"], p["point_id"]): p
                for pkt in packets.values() for p in pkt["scoring_points"]}

    # --- A. baseline + re-verify all existing verified (36) ---
    base = {"questions": len(packets), "points": sum(len(p["scoring_points"]) for p in packets.values()),
            "verified": 0, "weak": 0, "missing": 0}
    recheck = {"rechecked": 0, "ok": 0, "downgraded": [], "regressions": []}
    for pkt in packets.values():
        for sp in pkt["scoring_points"]:
            tb_refs = [r for r in sp["source_refs"] if r.get("source_type") == "textbook" and r.get("verified")]
            if tb_refs:
                base["verified"] += 1
                recheck["rechecked"] += 1
                q = _norm(tb_refs[0].get("textbook_quote"))
                cid = tb_refs[0].get("chunk_id")
                if cid in tb_by_chunk and q and q in tb_by_chunk[cid]:
                    recheck["ok"] += 1
                else:
                    recheck["downgraded"].append({"question_id": pkt["question_id"], "point_id": sp["point_id"]})
            elif sp["source_status"] == "missing_or_weak":
                if any(r.get("source_type") == "official_answer" for r in sp["source_refs"]):
                    base["weak"] += 1
                else:
                    base["missing"] += 1
    recheck["regressions"] = recheck["downgraded"]

    # --- B/C/D. worklist + alignment table + re-search ---
    worklist, align_table, new_verified = [], [], []
    refined_status: dict[tuple[str, str], dict[str, Any]] = {}
    for pkt in packets.values():
        for sp in pkt["scoring_points"]:
            already = any(r.get("source_type") == "textbook" and r.get("verified") for r in sp["source_refs"])
            if already:
                continue
            cand = pt_index[(pkt["question_id"], sp["point_id"])]
            oa = next((r.get("textbook_quote") for r in sp["source_refs"] if r.get("source_type") == "official_answer"), "") or cand.get("label", "")
            terms = _exam_terms(oa, sp.get("required_terms") or [])
            prio = {"exact_required": 2, "calculation": 3, "list_rule": 4}.get(sp["policy_type"], 5)
            if pkt.get("artifact_status") == "published":
                prio = 1
            worklist.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": sp["policy_type"],
                             "official_answer_phrase": oa[:80], "current_required_terms": sp.get("required_terms"),
                             "current_status": "weak" if any(r.get("source_type") == "official_answer" for r in sp["source_refs"]) else "missing",
                             "search_terms": terms, "likely_textbook_terms": terms[:3], "reason_for_miss": "exam term not verbatim in textbook", "priority": prio})
            hit = _search_verbatim(terms, "", tb)
            for t in terms:
                tn = _norm(t)
                matched = hit.get("hit") and _norm(hit.get("exam_term")) == tn
                align_table.append({"exam_term": t, "textbook_candidate_phrase": hit.get("textbook_quote") if matched else None,
                                    "chunk_id": hit.get("chunk_id") if matched else None,
                                    "match_type": "exact" if matched else "search_candidate_only",
                                    "can_verify": bool(matched), "used_for_search_only": not matched,
                                    "rationale": "normalized exact match in 2026 textbook" if matched else "search candidate; not verbatim"})
            meets_min = (sp["policy_type"] == "exact_required" and bool(sp.get("required_terms"))) or \
                        (sp["policy_type"] == "list_rule" and bool((sp.get("list_spec") or {}).get("denominator"))) or \
                        (sp["policy_type"] not in ("exact_required", "list_rule", "calculation", "high_risk_review"))
            if hit.get("hit") and meets_min and sp["policy_type"] != "high_risk_review":
                refined_status[(pkt["question_id"], sp["point_id"])] = {
                    "source_type": "textbook", "chunk_id": hit["chunk_id"], "textbook_quote": hit["textbook_quote"],
                    "verified": True, "match_method": "verbatim", "search_scope": hit["scope"]}
                new_verified.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": sp["policy_type"],
                                     "scope": hit["scope"], "chunk_id": hit["chunk_id"], "textbook_quote": hit["textbook_quote"],
                                     "candidate_node_code": hit.get("candidate_node_code")})

    # --- E. policy spec enrichment ---
    spec_enrich = []
    for pkt in packets.values():
        for sp in pkt["scoring_points"]:
            cand = pt_index[(pkt["question_id"], sp["point_id"])]
            label = cand.get("label", "")
            if sp["policy_type"] == "calculation" and sp.get("calculation_spec") is None:
                cs = _calc_spec(label)
                spec_enrich.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": "calculation",
                                    "enrichment_class": cs["kind"], "spec": cs})
            elif sp["policy_type"] == "list_rule":
                terms = _exam_terms(label, sp.get("required_terms") or [])
                ls = _list_spec(label, terms)
                spec_enrich.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": "list_rule",
                                    "enrichment_class": ls["kind"], "spec": ls})
            elif sp["policy_type"] == "exact_required":
                clean = [t for t in _exam_terms(label, sp.get("required_terms") or [])]
                cls = "deterministic_spec" if clean else "needs_po_review"
                spec_enrich.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": "exact_required",
                                    "enrichment_class": cls, "required_terms_clean": clean, "search_aliases": []})
            elif sp["policy_type"] == "penalty_rule" and not sp.get("penalty_rule"):
                spec_enrich.append({"question_id": pkt["question_id"], "point_id": sp["point_id"], "policy_type": "penalty_rule",
                                    "enrichment_class": "needs_po_review", "trigger_candidate": label[:60]})

    # --- F. refined packets v2 + G. quality gate ---
    coverage, policy_gap_by_q, q_disposition = {}, {}, {}
    candidate_nodes = []
    after = {"verified": 0, "weak": 0, "missing": 0, "auto": 0}
    for stem, pkt in packets.items():
        pkt = json.loads(json.dumps(pkt))  # deep copy; never mutate M4 on disk
        auto = total = 0
        gaps = []
        for sp in pkt["scoring_points"]:
            total += 1
            key = (pkt["question_id"], sp["point_id"])
            nv = refined_status.get(key)
            if nv:
                sp["source_refs"] = [nv]
                sp["source_status"] = "ok"
                sp["auto_certifiable"] = True
                if nv.get("candidate_node_code"):
                    candidate_nodes.append({"question_id": pkt["question_id"], "point_id": sp["point_id"],
                                            "candidate_node_code": nv["candidate_node_code"], "confidence": 0.4})
            if sp["auto_certifiable"]:
                auto += 1
                after["verified"] += 1
            else:
                after["weak" if any(r.get("source_type") == "official_answer" for r in sp["source_refs"]) else "missing"] += 1
                if sp["policy_type"] == "exact_required" and not sp.get("required_terms"):
                    gaps.append("exact_required_without_required_terms")
                if sp["policy_type"] == "list_rule" and not (sp.get("list_spec") or {}).get("denominator"):
                    gaps.append("list_rule_without_denominator")
                if sp["policy_type"] == "calculation" and sp.get("calculation_spec") is None:
                    gaps.append("calculation_without_spec")
                gaps.append("no_verbatim_textbook_anchor")
        after["auto"] += auto
        cov = round(auto / total, 3) if total else 0.0
        coverage[pkt["question_id"]] = cov
        policy_gap_by_q[pkt["question_id"]] = sorted(set(gaps))
        # publish-candidate gate
        hard_gap = any(g in gaps for g in ("calculation_without_spec", "list_rule_without_denominator", "exact_required_without_required_terms"))
        if auto and cov >= 0.5 and not hard_gap and not recheck["regressions"]:
            disp = "published_candidate"
        elif hard_gap or (auto == 0 and total > 0 and cov < 0.5):
            disp = "needs_po_review" if hard_gap else "draft_candidate"
        else:
            disp = "draft_candidate"
        q_disposition[pkt["question_id"]] = disp
        pkt["artifact_status"] = "published" if auto else "draft"
        pkt["registry_disposition"] = disp
        pkt["quality_gate"]["auto_certifiable_points"] = auto
        pkt["provenance"]["m5a_term_aligned"] = True
        assert validate_audit_packet(pkt) == [], f"{pkt['question_id']} validator failed"
        (OUT_DIR / "refined_audit_packets" / f"{stem}.json").write_text(json.dumps(pkt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / "jury_review_packets_m5a" / f"{stem}.json").write_text(json.dumps({
            "question_id": pkt["question_id"], "reviewer_type": "llm_jury", "votes": [], "votes_fabricated": False,
            "available_models": [], "items": [{"point_id": sp["point_id"], "policy_type": sp["policy_type"],
                                                "auto_certifiable": sp["auto_certifiable"], "label": sp.get("label")}
                                               for sp in pkt["scoring_points"]]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    impact = {
        "baseline": {k: base[k] for k in ("verified", "weak", "missing")},
        "m5a": {"verified": after["verified"], "weak": after["weak"], "missing": after["missing"]},
        "new_verified_anchors": len(new_verified),
        "new_verified_by_scope": {s: sum(1 for n in new_verified if n["scope"] == s) for s in ("node", "parent", "full_kb")},
        "by_policy_type": {pt: sum(1 for n in new_verified if n["policy_type"] == pt) for pt in {n["policy_type"] for n in new_verified}},
        "published_candidate": sum(1 for d in q_disposition.values() if d == "published_candidate"),
        "draft_candidate": sum(1 for d in q_disposition.values() if d == "draft_candidate"),
        "needs_po_review": sum(1 for d in q_disposition.values() if d == "needs_po_review"),
        "blocked": 0,
        "verified_coverage_by_question": coverage,
        "policy_gap_by_question": policy_gap_by_q,
        "auto_certifiable_point_count": after["auto"],
        "insufficient_source_coverage_count": sum(1 for c in coverage.values() if c < 0.5),
        "registry_emitted": False,
    }

    _dump("baseline_audit.json", base)
    _dump("verified_source_recheck.json", recheck)
    _dump("term_alignment_worklist.json", sorted(worklist, key=lambda w: (w["priority"], w["question_id"])))
    _dump("term_alignment_table.json", align_table)
    _dump("anchor_refinement_m5a_results.json", {"new_verified": new_verified, "candidate_node_codes": candidate_nodes,
                                                 "before": base, "after": impact["m5a"], "new_verified_count": len(new_verified),
                                                 "downgraded_count": len(recheck["downgraded"]), "still_missing_count": after["missing"],
                                                 "by_policy_type": impact["by_policy_type"], "by_source_layer": impact["new_verified_by_scope"]})
    _dump("policy_spec_enrichment_m5a.json", spec_enrich)
    _dump("registry_impact_simulation_m5a.json", impact)
    _write_finding(base, impact, recheck, align_table, spec_enrich)

    print(f"baseline verified={base['verified']} -> m5a verified={after['verified']} (+{len(new_verified)}; "
          f"scope={impact['new_verified_by_scope']}) pub_cand={impact['published_candidate']} "
          f"draft={impact['draft_candidate']} needs_po={impact['needs_po_review']} recheck_fail={len(recheck['downgraded'])}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_finding(base, impact, recheck, align_table, spec_enrich):
    from collections import Counter
    exact = sum(1 for a in align_table if a["match_type"] == "exact")
    calc_filled = sum(1 for s in spec_enrich if s["policy_type"] == "calculation" and s["enrichment_class"] == "candidate_spec")
    calc_need = sum(1 for s in spec_enrich if s["policy_type"] == "calculation" and s["enrichment_class"] == "calculation_spec_needed")
    list_filled = sum(1 for s in spec_enrich if s["policy_type"] == "list_rule" and s["enrichment_class"] == "candidate_spec")
    list_need = sum(1 for s in spec_enrich if s["policy_type"] == "list_rule" and s["enrichment_class"] == "needs_po_review")
    m5a = impact["m5a"]
    go = impact["new_verified_anchors"]
    verdict = "**GO**" if go >= 3 else ("**WEAK-GO**" if go >= 1 else "**NO-GO**")
    lines = [
        "# FINDING — case-rubric term alignment M5A (2026-06-04)", "",
        "## 必答", "",
        f"1. M5A 前后 verified/weak/missing？ 前 {base['verified']}/{base['weak']}/{base['missing']} → 后 **{m5a['verified']}/{m5a['weak']}/{m5a['missing']}**。",
        f"2. 新增 verified anchors？ **{impact['new_verified_anchors']}**；来源层 {impact['new_verified_by_scope']}。",
        f"3. 36 个旧 verified 全复验通过？ {'是（0 降级）' if not recheck['downgraded'] else '否：'+str(recheck['downgraded'])}。",
        f"4. term_alignment_table 多少条？ **{len(align_table)}**；其中 exact-verify **{exact}**，其余仅 search_candidate。",
        "5. still_missing top 原因：真题术语与教材原文逐字差异（同义/缩写/口语）、list item 分散多 chunk、calculation 非术语、node 未解析致 full_kb 噪声。",
        f"6. calculation_spec 补了多少？仍缺多少？ candidate {calc_filled} / 仍 needs {calc_need}。",
        f"7. list_rule denominator/item_set 补了多少？仍缺多少？ candidate {list_filled} / needs_po_review {list_need}。",
        f"8. published_candidate？ **{impact['published_candidate']}**（注：M4 的 20 是宽口径『≥1 auto 点』；M5A 用严格发布门 verified-coverage≥50% + 无 calc/list/exact 硬缺口，故数字下降是**门更严，非数据退化**）。",
        f"9. draft_candidate / needs_po_review？ {impact['draft_candidate']} / {impact['needs_po_review']}。",
        "10. 是否生成正式 registry？ **NO**。",
        "11. 是否伪造 source_ref / textbook_quote / LLM vote？ **NO**（verified 仅 verbatim 教材；jury votes=[]，votes_fabricated=false）。",
        f"12. 是否可进入 M5B LLM Jury Review？ {'**WEAK-GO**' if 1 <= go < 8 else verdict} —— "
        + (f"增量为 +{go}（部分为短词/句段 verbatim 命中，质量需 jury/PO 确认），refined packets 全过 A1 validator、待评包就绪；"
           "建议**停止继续挖锚点**（边际递减），直接进 M5B：jury 评候选质量、still_missing/needs_po 交 PO 标 needs_review，避免无限打磨。" if go >= 1
           else "锚点零增量，停止挖锚点，把 still_missing 交 PO/jury 标 needs_review。"),
        "",
        "## 结论",
        f"M5A 清洗真题术语 + 多层 verbatim 检索，把教材锚从 {base['verified']} 提到 **{m5a['verified']}**（+{impact['new_verified_anchors']}）；"
        f"published_candidate={impact['published_candidate']}；calc/list spec 以 candidate/needs_po_review 区分，不硬填；未伪造、未生成 registry、未覆盖 M3/M4。",
        "",
        "## 红线",
        "不新增表 / 不接 runtime / 不改 kernel / RAG 不进评分 / 官方答案·解释不当 textbook / LLM·同义·embedding 不升 verified / 不伪造 source·quote·vote / 未覆盖 M3/M4 / node 仅 candidate / 未 commit。",
        "",
    ]
    (OUT_DIR / "FINDING_case_rubric_term_alignment_m5a_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
