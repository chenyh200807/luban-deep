"""Registry v1 M4 — textbook anchor refinement + policy gap audit (no jury, no registry).

Goal: turn as many of M3's 105 missing / 5 weak scoring points into VERIFIED textbook
anchors, using a STRONGER search (official_answer split into phrases, multi-layer
node/parent/full_kb) — but the ``verified`` judgement stays strictly VERBATIM against the
2026 textbook content_markdown. Synonyms are used only for search, never to verify.
official_answer / 题库 explanation / LLM rationale can NEVER be a textbook quote.

No new table, no runtime, no kernel/RAG change, no formal registry, no fabricated
source_ref, no fabricated LLM vote. node_code is candidate-only (never hard-filled).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M3 = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_anchor_refinement_m4_20260604"
MIN_VERBATIM = 5  # normalized chars; below this a match is too common to anchor


def _norm(s: Any) -> str:
    return re.sub(r"[（）()\s、,.，。；;:：!！?？\"'《》\[\]\n\t]", "", str(s or ""))


def _is_numeric(s: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+(\.\d+)?\s*(mm|cm|m|MPa|kN|%|度|天|月|年|kg|个|根|层)?\s*", s))


def _load_textbook() -> list[tuple[str, str, str]]:
    """[(chunk_id, node_code, normalized_content_markdown)]."""
    idx = []
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        for b in json.loads(f.read_text("utf-8")).get("content_blocks") or []:
            md = b.get("content_markdown") or ""
            if md:
                idx.append((str(b.get("chunk_id") or ""), str((b.get("taxonomy") or {}).get("node_code") or ""), _norm(md)))
    return idx


def _phrases(span: str) -> list[str]:
    """Distinctive candidate phrases from an official_answer span (longest first)."""
    frags = re.split(r"[，,、；;:：。！？\s]+|[①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]", span)
    out = []
    for fr in frags:
        n = _norm(fr)
        if len(n) >= MIN_VERBATIM and not _is_numeric(fr):
            out.append(fr.strip())
    # longest-first so the most distinctive phrase anchors
    return sorted(set(out), key=lambda x: -len(_norm(x)))


def _search(span: str, node_hint: str, tb: list[tuple[str, str, str]]) -> dict[str, Any]:
    """Verbatim multi-layer search. Returns a hit with the textbook chunk + the exact
    phrase (which, being verbatim, IS the textbook quote) or {hit:False}."""
    phrases = _phrases(span)
    parent = node_hint[:5] if node_hint else ""
    for scope, pred in (("node", lambda n: bool(node_hint) and n == node_hint),
                        ("parent", lambda n: bool(parent) and n.startswith(parent)),
                        ("full_kb", lambda n: True)):
        for ph in phrases:
            pn = _norm(ph)
            for chunk_id, node, md in tb:
                if pred(node) and pn in md:
                    return {"hit": True, "scope": scope, "chunk_id": chunk_id, "candidate_node_code": node,
                            "textbook_quote": ph.strip()[:80], "matched_norm_len": len(pn)}
    return {"hit": False, "scope": "full_kb"}


def _meets_min(policy_type: str, required_terms: list[str], list_spec: Any, calc_spec: Any) -> bool:
    if policy_type == "exact_required":
        return bool(required_terms)
    if policy_type == "list_rule":
        return bool((list_spec or {}).get("denominator"))
    if policy_type == "calculation":
        return calc_spec is not None
    if policy_type == "high_risk_review":
        return False
    return True


def _policy_gap(sp: dict[str, Any], verified: bool) -> dict[str, Any]:
    pt = sp["policy_type"]
    gaps = []
    if pt == "exact_required" and not sp.get("required_terms"):
        gaps.append("missing_required_terms")
    if pt == "list_rule":
        ls = sp.get("list_spec") or {}
        if not ls.get("denominator"):
            gaps.append("missing_denominator")
        if not (ls.get("terms")):
            gaps.append("missing_item_set")
    if pt == "calculation" and sp.get("calculation_spec") is None:
        gaps.append("missing_calculation_spec")
    if pt == "penalty_rule" and not sp.get("penalty_rule"):
        gaps.append("missing_penalty_trigger")
    if not verified:
        gaps.append("no_verbatim_textbook_anchor")
    return {"point_id": sp["point_id"], "policy_type": pt, "gaps": gaps, "auto_certifiable": verified}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "refined_audit_packets").mkdir(exist_ok=True)
    from scripts.luban_case_rubric_schema import validate_audit_packet

    tb = _load_textbook()
    verify_rows = json.loads((M3 / "textbook_verify_on_write.json").read_text("utf-8"))
    points = json.loads((M3 / "scoring_point_candidates.json").read_text("utf-8"))
    pt_index = {(p["question_id"], p["point_id"]): p for p in points}
    packet_files = sorted((M3 / "audit_packets_structured").glob("*.json"))

    # --- A. baseline + re-verify existing 28 ---
    base = {"questions": len(packet_files), "points": len(verify_rows),
            "verified": sum(1 for r in verify_rows if r["anchor_status"] == "verified"),
            "weak": sum(1 for r in verify_rows if r["anchor_status"] == "weak"),
            "missing": sum(1 for r in verify_rows if r["anchor_status"] == "missing")}
    tb_by_chunk = {c: m for c, _, m in tb}
    reverify_fail = []
    for r in verify_rows:
        if r["anchor_status"] == "verified":
            sr = r["selected_source_ref"]
            q = _norm(sr["textbook_quote"])
            if not (sr["chunk_id"] in tb_by_chunk and q and q in tb_by_chunk[sr["chunk_id"]]):
                reverify_fail.append({"question_id": r["question_id"], "point_id": r["point_id"]})
    base["reverify_28_ok"] = base["verified"] - len(reverify_fail)
    base["reverify_failures"] = reverify_fail

    # --- B. worklist ---
    def _priority(r):
        pt = r["policy_type"]
        p = 3
        if pt in ("exact_required", "calculation", "penalty_rule"):
            p = 1
        elif pt == "list_rule":
            p = 2
        return p
    worklist = []
    for r in verify_rows:
        if r["anchor_status"] in ("missing", "weak"):
            cand = pt_index.get((r["question_id"], r["point_id"]), {})
            worklist.append({
                "question_id": r["question_id"], "point_id": r["point_id"], "policy_type": r["policy_type"],
                "expected_label": cand.get("label"), "official_answer_seed": cand.get("official_answer_span"),
                "required_terms_seed": cand.get("required_terms"), "current_source_status": r["anchor_status"],
                "search_terms": _phrases(cand.get("official_answer_span") or ""), "priority": _priority(r),
            })
    worklist.sort(key=lambda w: (w["priority"], w["question_id"]))

    # --- C. refinement search ---
    new_verified = []
    refined_status = {}  # (qid,pid) -> (status, source_ref, candidate_node)
    for w in worklist:
        cand = pt_index.get((w["question_id"], w["point_id"]), {})
        node_hint = ""  # M3 resolved 0; rely on parent/full_kb
        hit = _search(cand.get("official_answer_span") or "", node_hint, tb)
        meets = _meets_min(w["policy_type"], cand.get("required_terms") or [], cand.get("list_rule"), cand.get("calculation_spec"))
        verified = hit.get("hit") and meets and w["policy_type"] != "high_risk_review"
        if verified:
            sr = {"source_type": "textbook", "chunk_id": hit["chunk_id"], "textbook_quote": hit["textbook_quote"],
                  "verified": True, "match_method": "verbatim", "search_scope": hit["scope"]}
            refined_status[(w["question_id"], w["point_id"])] = ("verified", sr, hit.get("candidate_node_code"))
            new_verified.append({**w, "scope": hit["scope"], "chunk_id": hit["chunk_id"], "textbook_quote": hit["textbook_quote"], "candidate_node_code": hit.get("candidate_node_code")})
        else:
            refined_status[(w["question_id"], w["point_id"])] = (w["current_source_status"] if not hit.get("hit") else "weak", None, None)

    # --- D. policy gap audit + E. refined packets ---
    policy_gaps = []
    impact = {"verified": 0, "weak": 0, "missing": 0, "auto_certifiable_points": 0}
    pub_cand = draft = 0
    candidate_nodes = []
    for pf in packet_files:
        packet = json.loads(pf.read_text("utf-8"))
        auto_n = 0
        for sp in packet["scoring_points"]:
            key = (packet["question_id"], sp["point_id"])
            ref = refined_status.get(key)
            if ref and ref[0] == "verified":
                sp["source_refs"] = [ref[1]]
                sp["source_status"] = "ok"
                sp["auto_certifiable"] = True
                if ref[2]:
                    candidate_nodes.append({"question_id": packet["question_id"], "point_id": sp["point_id"], "candidate_node_code": ref[2], "confidence": 0.4, "reason": "matched textbook chunk node (candidate, not authority)"})
            verified = bool(sp["auto_certifiable"])
            policy_gaps.append({"question_id": packet["question_id"], **_policy_gap(sp, verified)})
            if verified:
                auto_n += 1
                impact["verified"] += 1
            elif sp["source_status"] == "missing_or_weak":
                impact["weak" if any(r.get("source_type") == "official_answer" for r in sp["source_refs"]) else "missing"] += 1
        impact["auto_certifiable_points"] += auto_n
        # node_code stays as-is (candidate only, never hard-filled into the packet authority field)
        packet["artifact_status"] = "published" if auto_n else "draft"
        packet["registry_disposition"] = "published_candidate_not_final" if auto_n else "draft"
        packet["quality_gate"]["auto_certifiable_points"] = auto_n
        packet["provenance"]["m4_refined"] = True
        pub_cand += 1 if auto_n else 0
        draft += 0 if auto_n else 1
        violations = validate_audit_packet(packet)
        assert violations == [], f"{packet['question_id']} {violations}"
        (OUT_DIR / "refined_audit_packets" / pf.name).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    impact_sim = {
        "baseline": {"verified": base["verified"], "weak": base["weak"], "missing": base["missing"]},
        "m4": {"verified": impact["verified"], "weak": impact["weak"], "missing": impact["missing"]},
        "new_verified_anchors": len(new_verified),
        "new_verified_by_scope": {s: sum(1 for n in new_verified if n["scope"] == s) for s in ("node", "parent", "full_kb")},
        "published_candidate_not_final": pub_cand, "draft": draft,
        "auto_certifiable_points": impact["auto_certifiable_points"],
        "registry_emitted": False,
        "top_missing_reasons": [
            "真题术语与教材原文表述差异（同义/缩写/口语化），逐字不命中",
            "list_rule item set 在教材中分散，不在单一 chunk verbatim",
            "calculation 点需 calculation_spec，非 verbatim 术语",
            "node_code 未解析，full_kb 检索噪声大",
        ],
    }
    jury_review_packet = {
        "purpose": "offline LLM-jury + PO review material (NOT executed; no votes)",
        "reviewer_type": "llm_jury", "votes_fabricated": False, "available_models": [],
        "items": [{"question_id": p["question_id"], "point_id": p["point_id"], "policy_type": p["policy_type"],
                   "expected_label": p["expected_label"], "official_answer_seed": p["official_answer_seed"],
                   "current_status": refined_status.get((p["question_id"], p["point_id"]), ("missing",))[0]}
                  for p in worklist],
    }

    _dump("baseline_audit.json", base)
    _dump("missing_anchor_worklist.json", worklist)
    _dump("textbook_anchor_refinement_results.json", {"new_verified": new_verified, "candidate_node_codes": candidate_nodes})
    _dump("policy_gap_audit.json", policy_gaps)
    _dump("registry_impact_simulation_m4.json", impact_sim)
    _dump("jury_review_packet_m4.json", jury_review_packet)
    _write_finding(base, impact_sim, new_verified, policy_gaps)

    print(f"baseline verified={base['verified']} -> m4 verified={impact['verified']} "
          f"(+{len(new_verified)}; scope={impact_sim['new_verified_by_scope']}) "
          f"pub_cand={pub_cand} draft={draft} reverify_fail={len(reverify_fail)}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_finding(base, impact, new_verified, policy_gaps):
    from collections import Counter
    gap_counter = Counter(g for row in policy_gaps for g in row["gaps"])
    m4 = impact["m4"]
    lines = [
        "# FINDING — case-rubric anchor refinement M4 (2026-06-04)", "",
        "## 必答", "",
        f"1. M4 前后 verified/weak/missing？ 前 {base['verified']}/{base['weak']}/{base['missing']} → 后 **{m4['verified']}/{m4['weak']}/{m4['missing']}**。",
        f"2. 新增 verified anchors？ **{len(new_verified)}**；来源层 {impact['new_verified_by_scope']}（node/parent/full_kb）。",
        f"3. 28 个旧 verified 是否全部复验通过？ {'是' if not base['reverify_failures'] else '否：'+str(base['reverify_failures'])}（exact normalized match）。",
        f"4. 仍 missing 的 top 原因：" + "；".join(impact["top_missing_reasons"]),
        f"5. policy_gap 最大缺口：{dict(gap_counter.most_common(4))}。",
        f"6. published_candidate_not_final 是否增加？ {impact['published_candidate_not_final']}（M3=16）。",
        "7. 是否生成正式 registry？ **NO**（仅 refined packets + impact sim）。",
        "8. 是否伪造教材 source / LLM vote？ **NO**（verified 仅 verbatim 教材；jury 未跑、`votes_fabricated=false`）。",
        f"9. 是否可进入 LLM jury offline rubric review？ {'**GO**' if len(new_verified) > 0 else '**NO-GO**'} —— "
        + ("锚点命中已有增量、refined packets 通过 A1 validator、待评包就绪；jury 评候选质量、PO 终裁。" if len(new_verified) > 0 else "锚点零增量，先补强教材对齐再评。"),
        "10. 下一步最小任务：对仍 missing 的 exact_required/list_rule 点做**真题术语↔教材原文同义/缩写对齐表**（只扩 search，不改 verified 判定），并补 list_rule denominator/item_set 与 calculation_spec 结构化。",
        "",
        "## 结论",
        f"M4 把 verbatim 教材锚从 {base['verified']} 提到 **{m4['verified']}**（+{len(new_verified)}），refined packets 全过 A1 validator、未生成 registry、未伪造。瓶颈仍是真题术语与教材原文逐字差异 + node 未解析。",
        "",
        "## 红线",
        "不新增表、不接 runtime、不改 kernel、RAG 不进评分、官方答案/解释不当 textbook、不伪造 source/vote、不生成正式 registry、node_code 仅 candidate、未 commit。",
        "",
    ]
    (OUT_DIR / "FINDING_case_rubric_anchor_refinement_m4_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
