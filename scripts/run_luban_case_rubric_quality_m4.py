"""M4 — Registry v1 quality audit of M3 published candidates (no formal registry emitted).

Audits the M3 `published` audit packets (a.k.a. published_candidate_not_final): re-verifies
every textbook source_ref against the 2026 textbook content_markdown (downgrade-on-miss),
audits policy completeness + missing-point risk, simulates which questions could enter a
registry v1 draft/published candidate flow, and emits LLM-jury review packets (no fabricated
votes). It NEVER writes a formal registry.

Red lines: no DB table, no formal registry, no runtime, no kernel/RAG change, exam explanation
is never a textbook source, no fabricated source_ref/textbook_quote/LLM vote.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from scripts.run_luban_case_rubric_structuring_m3 import _load_textbook, _norm  # reuse verbatim KB index
from scripts.luban_case_rubric_schema import verify_textbook_anchor, validate_audit_packet

REPO = Path(__file__).resolve().parents[1]
M3_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
DEFAULT_OUT = REPO / "artifacts/luban_grading_artifacts/case_rubric_quality_m4_20260604"
HIGH_MISSING_RATIO = 0.6


def _published_packets() -> list[dict[str, Any]]:
    out = []
    for f in sorted(glob.glob(str(M3_DIR / "audit_packets_structured" / "*.json"))):
        d = json.loads(Path(f).read_text("utf-8"))
        if d.get("artifact_status") == "published":
            out.append(d)
    return out


def _tb_index(tb: list[tuple[str, str, str]]) -> dict[str, str]:
    return {cid: md for cid, _node, md in tb if cid}


def _recheck_source_ref(sr: dict[str, Any], tb_by_chunk: dict[str, str]) -> tuple[bool, str]:
    """A textbook source_ref survives only if chunk_id is a real 2026-textbook chunk AND
    the normalized quote appears verbatim in that chunk's content_markdown."""
    if str(sr.get("source_type")) != "textbook":
        return False, "not_textbook_source_type"
    cid = str(sr.get("chunk_id") or "")
    quote = sr.get("textbook_quote") or sr.get("quote") or ""
    if not cid or not quote:
        return False, "missing_chunk_or_quote"
    md = tb_by_chunk.get(cid)
    if md is None:
        return False, "chunk_id_not_in_2026_textbook"
    if _norm(quote) not in md:
        return False, "quote_not_verbatim_in_content_markdown"
    return True, "verbatim_ok"


def _policy_ok(point: dict[str, Any]) -> tuple[bool, str]:
    pt = str(point.get("policy_type") or "")
    if pt == "exact_required":
        return (bool(point.get("required_terms")), "missing_required_terms")
    if pt == "list_rule":
        spec = point.get("list_spec") or point.get("list_rule") or {}
        ok = bool(isinstance(spec, dict) and (spec.get("denominator") or spec.get("item_set") or spec.get("terms") or spec.get("items")))
        return (ok, "missing_denominator_or_item_set")
    if pt == "calculation":
        return (point.get("calculation_spec") is not None, "missing_calculation_spec")
    if pt == "penalty_rule":
        return (point.get("penalty_rule") is not None or point.get("penalty_spec") is not None, "missing_penalty_rule")
    if pt == "figure_label":
        return (False, "figure_authority_unresolved")  # never auto without figure authority
    if pt in ("semantic_allowed", "high_risk_review"):
        return (True, "")  # executable but not auto-certifiable
    return (False, "unknown_policy_type")


def build_m4(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "jury_review_packets").mkdir(parents=True, exist_ok=True)
    tb = _load_textbook()
    tb_by_chunk = _tb_index(tb)
    packets = _published_packets()

    worklist, quality, recheck_rows = [], [], []
    gap = {"exact_required_missing_terms": 0, "list_rule_missing_denominator": 0,
           "calculation_missing_spec": 0, "semantic_allowed_points": 0,
           "penalty_rule_missing_trigger": 0, "figure_label_missing_authority": 0}
    downgraded_points = 0
    draft_candidates = published_candidates = excluded = 0

    for pk in packets:
        qid = pk.get("question_id")
        points = pk.get("scoring_points") or []
        policy_types = sorted({str(p.get("policy_type")) for p in points})
        verified_ids, auto_ids, risk_flags = [], [], []
        weak_n = sum(1 for p in points if str(p.get("source_status")) in ("weak", "missing_or_weak"))
        missing_n = sum(1 for p in points if str(p.get("source_status")) in ("missing", "missing_or_blocked"))

        # recheck each auto_certifiable point's verified textbook anchor
        policy_pass = True
        for p in points:
            pid = p.get("point_id")
            ok_pol, _ = _policy_ok(p)
            pt = str(p.get("policy_type") or "")
            if pt == "exact_required" and not p.get("required_terms"):
                gap["exact_required_missing_terms"] += 1
            if pt == "list_rule":
                spec = p.get("list_spec") or p.get("list_rule") or {}
                if not (isinstance(spec, dict) and (spec.get("denominator") or spec.get("item_set") or spec.get("terms") or spec.get("items"))):
                    gap["list_rule_missing_denominator"] += 1
            if pt == "calculation" and p.get("calculation_spec") is None:
                gap["calculation_missing_spec"] += 1
            if pt == "semantic_allowed":
                gap["semantic_allowed_points"] += 1
            if pt == "penalty_rule" and not (p.get("penalty_rule") or p.get("penalty_spec")):
                gap["penalty_rule_missing_trigger"] += 1
            if pt == "figure_label":
                gap["figure_label_missing_authority"] += 1
            if p.get("auto_certifiable"):
                # recheck its source_refs
                kept = False
                for sr in p.get("source_refs") or []:
                    ok, reason = _recheck_source_ref(sr, tb_by_chunk)
                    recheck_rows.append({"question_id": qid, "point_id": pid, "result": "pass" if ok else "downgraded",
                                         "reason": reason, "chunk_id": sr.get("chunk_id")})
                    if ok and verify_textbook_anchor(sr):
                        kept = True
                if kept:
                    verified_ids.append(pid); auto_ids.append(pid)
                else:
                    downgraded_points += 1
                    risk_flags.append(f"{pid}:verified_downgraded_on_recheck")
            if not ok_pol and pt not in ("semantic_allowed", "high_risk_review"):
                policy_pass = False

        total_pts = len(points)
        missing_ratio = (missing_n / total_pts) if total_pts else 1.0
        missing_risk = "high" if (missing_ratio >= HIGH_MISSING_RATIO or not verified_ids) else ("medium" if missing_ratio >= 0.3 else "low")

        has_calc_no_spec = any(str(p.get("policy_type")) == "calculation" and p.get("calculation_spec") is None for p in points)
        has_list_no_denom = any(str(p.get("policy_type")) == "list_rule" and not (
            isinstance(p.get("list_spec") or p.get("list_rule") or {}, dict)
            and ((p.get("list_spec") or p.get("list_rule") or {}).get("denominator")
                 or (p.get("list_spec") or p.get("list_rule") or {}).get("item_set")
                 or (p.get("list_spec") or p.get("list_rule") or {}).get("terms")
                 or (p.get("list_spec") or p.get("list_rule") or {}).get("items"))) for p in points)

        # "sufficient source_ref" for published: verified anchors must cover >= half the
        # scoring points (a 1-verified / 7-weak question is draft_candidate, not published).
        verified_ratio = (len(verified_ids) / total_pts) if total_pts else 0.0
        sufficient_coverage = verified_ratio >= 0.5
        src_integrity = "pass" if verified_ids else "fail"
        can_draft = bool(verified_ids) and src_integrity == "pass"
        can_published = bool(can_draft and policy_pass and missing_risk != "high"
                             and sufficient_coverage and not has_calc_no_spec and not has_list_no_denom)
        blockers = []
        if not verified_ids:
            blockers.append("no_surviving_verified_textbook_anchor")
        if verified_ids and not sufficient_coverage:
            blockers.append(f"insufficient_verified_source_coverage({len(verified_ids)}/{total_pts})")
        if missing_risk == "high":
            blockers.append("high_missing_point_risk")
        if has_calc_no_spec:
            blockers.append("calculation_without_spec")
        if has_list_no_denom:
            blockers.append("list_rule_without_denominator")
        if not policy_pass:
            blockers.append("policy_incomplete")

        worklist.append({"question_id": qid, "verified_point_count": len(verified_ids),
                         "weak_point_count": weak_n, "missing_point_count": missing_n,
                         "policy_types": policy_types, "auto_certifiable_point_ids": auto_ids,
                         "risk_flags": risk_flags, "current_status": "published_candidate_not_final"})
        quality.append({"question_id": qid,
                        "source_ref_integrity": src_integrity,
                        "policy_completeness": "pass" if policy_pass else "partial",
                        "list_rule_completeness": "fail" if has_list_no_denom else ("na" if "list_rule" not in policy_types else "pass"),
                        "calculation_spec_completeness": "fail" if has_calc_no_spec else ("na" if "calculation" not in policy_types else "pass"),
                        "missing_point_risk": missing_risk,
                        "can_enter_registry_draft": can_draft,
                        "can_enter_registry_published": can_published,
                        "needs_jury_review": True, "needs_po_review": True,
                        "blockers": blockers})
        if can_published:
            published_candidates += 1
        elif can_draft:
            draft_candidates += 1
        else:
            excluded += 1

        # jury review packet (no fabricated votes)
        (out_dir / "jury_review_packets" / f"{qid}.json").write_text(json.dumps({
            "question_id": qid, "question_text": pk.get("question_text"),
            "official_answer": pk.get("official_answer"),
            "scoring_point_candidates": [{"point_id": p.get("point_id"), "label": p.get("label"),
                                          "policy_type": p.get("policy_type"), "max_score": p.get("max_score"),
                                          "source_status": p.get("source_status"),
                                          "auto_certifiable": p.get("auto_certifiable")} for p in points],
            "policy_gaps": [b for b in blockers],
            "recommended_review_questions": [
                "采分点是否覆盖 official_answer 的全部得分要点？",
                "verified 教材锚是否真的支撑该点（chunk+quote 命中）？",
                "calculation/list_rule policy spec 是否可执行？",
                "缺失点(missing)是否影响整题可发布？"],
            "votes": [], "votes_fabricated": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    sim = {"registry_emitted": False, "input_published_candidate_questions": len(packets),
           "draft_candidate_questions": draft_candidates, "published_candidate_questions": published_candidates,
           "excluded_questions": excluded,
           "total_points": sum(len(p.get("scoring_points") or []) for p in packets),
           "auto_certifiable_points_after_recheck": sum(len(w["auto_certifiable_point_ids"]) for w in worklist),
           "verified_points_downgraded_on_recheck": downgraded_points,
           "needs_jury_review_questions": len(packets), "needs_po_review_questions": len(packets),
           "top_blockers": _top_blockers(quality)}

    _dump(out_dir, "published_candidate_worklist.json", worklist)
    _dump(out_dir, "published_candidate_quality_audit.json", quality)
    _dump(out_dir, "verified_source_recheck.json", {"rechecked": len(recheck_rows),
          "passed": sum(1 for r in recheck_rows if r["result"] == "pass"),
          "downgraded": sum(1 for r in recheck_rows if r["result"] == "downgraded"), "rows": recheck_rows})
    _dump(out_dir, "policy_gap_audit.json", gap)
    _dump(out_dir, "registry_v1_draft_simulation.json", sim)
    (out_dir / "FINDING_case_rubric_quality_m4_20260604.md").write_text(_finding(worklist, quality, recheck_rows, gap, sim), encoding="utf-8")
    return {"worklist": worklist, "quality": quality, "recheck": recheck_rows, "gap": gap, "sim": sim}


def _top_blockers(quality: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from collections import Counter
    c = Counter(b for q in quality for b in q["blockers"])
    return [{"blocker": k, "count": v} for k, v in c.most_common(5)]


def _dump(out_dir: Path, name: str, obj: Any) -> None:
    (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _finding(worklist, quality, recheck, gap, sim) -> str:
    passed = sum(1 for r in recheck if r["result"] == "pass")
    down = sum(1 for r in recheck if r["result"] == "downgraded")
    return "\n".join([
        "# FINDING — Registry v1 M4 published-candidate 质量审计（2026-06-04）",
        "",
        "## 必答",
        f"1. published_candidate_not_final 输入多少题？ **{sim['input_published_candidate_questions']}**。",
        f"2. verified source recheck 通过多少点？ **{passed}**（重新对 2026 教材 content_markdown verbatim 命中）。",
        f"3. 降级多少点？ **{down}**（chunk 不在 2026 教材 / quote 非逐字 → 降 weak）。",
        f"4. 可进入 registry draft_candidate 多少题？ **{sim['draft_candidate_questions']}**。",
        f"5. 可进入 registry published_candidate 多少题？ **{sim['published_candidate_questions']}**。",
        f"6. 不可进入多少题？ **{sim['excluded_questions']}**。",
        f"7. policy gap Top 5：{sim['top_blockers']}。",
        f"8. calculation/list_rule 缺口：calculation_missing_spec={gap['calculation_missing_spec']}、list_rule_missing_denominator={gap['list_rule_missing_denominator']}。",
        f"9. missing_point_risk high 多少题？ **{sum(1 for q in quality if q['missing_point_risk']=='high')}**。",
        "10. 是否生成正式 registry？ **NO**（仅 draft simulation）。",
        "11. 是否伪造 source_ref / LLM vote？ **NO**（recheck 对 2026 教材逐字命中，jury packet `votes_fabricated=false` 空票）。",
        "12. Registry v1 下一步：先**接 LLM Jury review**（jury_review_packets 已备）对采分点 + verified 锚做复核，并**继续锚点补强**（node 收敛 + 术语对齐降 missing），再进 **PO review**；structural 通过的题才升 published_candidate，未复核不进 final。",
        "",
        f"## 概要",
        f"- 输入 published packets：{sim['input_published_candidate_questions']}；recheck 通过点 {passed} / 降级 {down}；",
        f"- draft_candidate {sim['draft_candidate_questions']} / published_candidate {sim['published_candidate_questions']} / excluded {sim['excluded_questions']}；",
        f"- recheck 后 auto_certifiable 点 {sim['auto_certifiable_points_after_recheck']}；registry_emitted=False。",
        "",
        "## 红线",
        "不新增表、不生成正式 registry v1、不接 runtime、不改 kernel、RAG 不进评分、题库 explanation 不当 textbook、不伪造 source_ref/quote/LLM vote、未 commit。",
        "",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    r = build_m4(Path(args.out_dir))
    s = r["sim"]
    print(f"M4 -> {args.out_dir}")
    print(f"  input={s['input_published_candidate_questions']} draft_candidate={s['draft_candidate_questions']} "
          f"published_candidate={s['published_candidate_questions']} excluded={s['excluded_questions']} "
          f"recheck_downgraded_points={s['verified_points_downgraded_on_recheck']} registry_emitted={s['registry_emitted']}")


if __name__ == "__main__":
    main()
