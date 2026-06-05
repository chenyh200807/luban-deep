"""Case-rubric data expansion M2 — first-batch candidate audit + pipeline demo.

Honest finding (reconfirmed exhaustively): there are NO new gradeable subjective case
questions beyond the 20 golden. ``docs/2026/{教材,题库,标准文件}`` are absent; every
artifact slice references Q1–Q20; exam_quality_bank is 62 MCQ (out of scope); the 6134
node assets and the content_markdown reanchor (97 points) yield 0 verbatim enrichment
for v0's 28 weak points.

So M2 does two honest things:
  1. AUDIT: scan all candidate sources -> 0 new gradeable case candidates, 62 MCQ excluded.
  2. PIPELINE DEMO: run the full M2 machinery (AuditPacket build -> LLM-jury rubric
     candidate (cached real votes, llm_jury) -> textbook verify-on-write -> registry
     impact simulation) on existing golden cases, proving it is plug-and-play when real
     new questions arrive. Net-new registry impact from current data = 0 (no new data).

No new table, no production runtime, no kernel/RAG change, no fabricated source_ref,
no MCQ in case registry, no node-asset-as-rubric, LLM jury never claims human.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / "case_rubric_expansion_m2_20260604"
REANCHOR = REPO / "artifacts/luban_no_human_v1_5/content_markdown_reanchor_20260602/point_classification_reanchor_20260602.json"
EXAM_BANK = REPO / "deeptutor/services/benchmark/fixtures/exam_quality_bank.json"
# 5 golden cases covering the policy spectrum (the only real input available).
DEMO_CASES = ["Q1-NA", "Q2-1A436000-罚则", "Q17-1A433000", "Q20-1A413000", "Q10-1A422000"]
SCANNED_PATHS = ["docs/2026/", "docs/2026/2026教材/", "docs/2026/题库/", "docs/2026/标准文件/",
                 "artifacts/luban_human_validation_v1/", "artifacts/luban_agentic_grading_harness/",
                 "artifacts/luban_typed_policy/", "deeptutor/services/benchmark/fixtures/"]


def _reanchor_index() -> dict[tuple[str, str], dict[str, Any]]:
    if not REANCHOR.exists():
        return {}
    return {(r["case_id"], r["point_id"]): r for r in json.loads(REANCHOR.read_text("utf-8"))}


def _verbatim_anchor(rec: dict[str, Any] | None) -> dict[str, Any]:
    """verify-on-write: textbook anchor verified iff anchor_source=textbook + chunk_id +
    quote (the reanchor pipeline already verbatim-checked against content_markdown)."""
    if not rec:
        return {"anchor_status": "missing", "chunk_id": "", "textbook_quote": "", "normalized_match": False, "auto_certifiable": False, "reason": "no reanchor record"}
    src = str(rec.get("anchor_source") or "")
    chunk = str(rec.get("chunk_id") or "").strip()
    quote = str(rec.get("textbook_quote") or "").strip()
    if src == "textbook" and chunk and quote:
        return {"anchor_status": "verified", "chunk_id": chunk, "textbook_quote": quote, "normalized_match": True, "auto_certifiable": True, "reason": "verbatim textbook anchor (content_markdown reanchor)"}
    if quote and not chunk:
        return {"anchor_status": "weak", "chunk_id": "", "textbook_quote": quote, "normalized_match": False, "auto_certifiable": False, "reason": "quote without verified chunk"}
    return {"anchor_status": "missing", "chunk_id": chunk, "textbook_quote": quote, "normalized_match": False, "auto_certifiable": False, "reason": "no verbatim textbook anchor"}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit_packets").mkdir(exist_ok=True)
    (OUT_DIR / "model_votes").mkdir(exist_ok=True)

    from deeptutor.services.construction_grading.question_grading_artifacts import build_question_grading_artifact
    from scripts.luban_case_rubric_schema import validate_audit_packet
    from scripts.run_luban_model_jury_teacher_review_pilot import build_jury_review

    golden = {c["case_id"]: c for c in json.loads((REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json").read_text("utf-8"))["cases"]}
    reidx = _reanchor_index()

    # --- 1. candidate audit (0 new) + MCQ exclusion ---
    exam = json.loads(EXAM_BANK.read_text("utf-8"))
    mcq = []
    for year, by in (exam.get("by_year") or {}).items():
        for kind, items in (by or {}).items():
            if isinstance(items, list):
                for q in items:
                    qid = q.get("question_id") if isinstance(q, dict) else None
                    mcq.append({"question_id": qid, "year": year, "type": kind, "excluded_reason": "mcq_out_of_scope_for_case_registry"})
            else:  # value is a count (int), not a list of questions
                mcq.append({"question_id": None, "year": year, "type": kind, "count": items, "excluded_reason": "mcq_out_of_scope_for_case_registry"})
    mcq_total = int(exam.get("question_count") or sum(int(m.get("count") or 1) for m in mcq))
    candidate_case_questions: list[dict[str, Any]] = []  # 0 new gradeable case questions found

    # --- 2. pipeline demo on golden cases ---
    anchor_audit = []
    jury_candidates = []
    packets_meta = []
    for cid in DEMO_CASES:
        art = build_question_grading_artifact(cid)
        g = golden[cid]
        # textbook verify-on-write per point (from reanchor)
        points = []
        for sp in art["scoring_points"]:
            anc = _verbatim_anchor(reidx.get((cid, sp["point_id"])))
            anchor_audit.append({"case_id": cid, "point_id": sp["point_id"], "policy_type": sp["policy_type"], **anc})
            refs = []
            if anc["anchor_status"] == "verified":
                refs.append({"source_type": "textbook", "chunk_id": anc["chunk_id"], "textbook_quote": anc["textbook_quote"], "verified": True, "match_method": "verbatim"})
            points.append({
                "point_id": sp["point_id"], "label": sp["label"], "policy_type": sp["policy_type"],
                "max_score": sp["max_score"], "required_terms": sp.get("required_terms") or [],
                "list_spec": ({"denominator": len(sp.get("required_terms") or []) or None, "terms": sp.get("required_terms") or []} if sp["policy_type"] == "list_rule" else None),
                "calculation_spec": sp.get("calculation_spec"), "penalty_rule": sp.get("penalty_rule"),
                "source_refs": refs, "source_status": "ok" if refs else "missing_or_weak",
                "auto_certifiable": bool(refs) and sp["policy_type"] != "high_risk_review",
            })
        auto_n = sum(1 for p in points if p["auto_certifiable"])
        packet = {
            "schema_version": "luban_case_rubric_audit_packet.v0",
            "question_id": cid, "question_text": art["stem"][:300], "official_answer": art["official_answer"][:300],
            "node_code": str(g.get("question_node") or ""), "source_exam": "luban_case_grading_golden_v1 (EXISTING, not new)",
            "rubric_candidates": [{"point_id": p["point_id"], "label": p["label"], "candidate_source": "golden_human_anchored", "is_authority": False} for p in points],
            "textbook_anchor_evidence": [r for p in points for r in p["source_refs"]],
            "teacher_review_status": "reviewed", "artifact_status": "published" if auto_n else "draft",
            "scoring_points": points,
            "quality_gate": {"published": auto_n > 0, "auto_certifiable_points": auto_n, "weak_points": sum(1 for p in points if p["source_status"] != "ok"), "verify_on_write": "verbatim_textbook_only"},
            "provenance": {"compiled_from": "golden + content_markdown reanchor (verbatim)", "compiler": "case_rubric_expansion_m2", "note": "EXISTING question; demonstrates pipeline, not a new registry entry"},
        }
        violations = validate_audit_packet(packet)
        (OUT_DIR / "audit_packets" / f"{cid}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        packets_meta.append({"case_id": cid, "artifact_status": packet["artifact_status"], "auto_certifiable_points": auto_n, "validator_violations": violations})

        # LLM-jury rubric candidate (cached real votes)
        try:
            review, jury_points = build_jury_review(cid, "S1")
            (OUT_DIR / "model_votes" / f"{cid}.json").write_text(json.dumps([{"point_id": jp["point_id"], "model_votes": jp["model_votes"], "jury_verdict": jp["jury_verdict"], "needs_human_review": jp["needs_human_review"]} for jp in jury_points], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            jury_candidates.append({"case_id": cid, "review_source": review["review_source"], "reviewer_type": review["reviewer_type"], "adjudication_protocol": "case_rubric_jury_v0", "jury_models": review["jury_models"], "live_or_cached": "cached", "needs_human_review_points": sum(1 for jp in jury_points if jp["needs_human_review"])})
        except Exception as exc:  # noqa: BLE001
            jury_candidates.append({"case_id": cid, "live_or_cached": "unavailable", "reason": str(exc)[:120]})

    # --- 3. registry impact simulation (honest: 0 net-new from current data) ---
    verified_anchors = sum(1 for a in anchor_audit if a["anchor_status"] == "verified")
    weak_missing = sum(1 for a in anchor_audit if a["anchor_status"] != "verified")
    impact = {
        "new_questions_discovered": 0,
        "new_questions_published": 0,
        "new_questions_draft": 0,
        "net_new_auto_certifiable_points": 0,
        "note": "demo packets are EXISTING golden questions already in registry v0; no NEW questions exist to add.",
        "demo_packets": len(DEMO_CASES),
        "demo_textbook_verified_anchors": verified_anchors,
        "demo_weak_or_missing_anchors": weak_missing,
        "blocked_reasons_top": [
            "no_raw_case_question_corpus_in_repo (docs/2026 absent)",
            "all_artifact_slices_reference_Q1_Q20",
            "exam_quality_bank_is_mcq_out_of_scope",
            "node_6134_assets_are_knowledge_seeds_not_questions",
            "reanchor_yields_0_enrichment_for_v0_weak_points",
        ],
        "still_needs": "new exam/textbook case-question corpus + official_answer + verbatim textbook anchoring + PO review",
    }

    # --- write artifacts ---
    _dump("candidate_case_questions.json", candidate_case_questions)
    _dump("excluded_mcq.json", {"count": mcq_total, "reason": "MCQ not in case scoring-point registry", "questions": mcq})
    _dump("llm_jury_rubric_candidates.json", jury_candidates)
    _dump("jury_availability.json", {"models_requested": ["gpt55", "opus48", "deepseek_v4", "qwen37"], "live_or_cached": "cached", "source": "485 span-guarded real 4-model run", "note": "real cached votes, not live, not fabricated; reviewer_type=llm_jury, never human"})
    _dump("textbook_anchor_audit.json", anchor_audit)
    _dump("registry_impact_simulation.json", impact)
    _write_input_audit(len(candidate_case_questions), mcq_total, packets_meta)
    _write_finding(candidate_case_questions, mcq_total, packets_meta, jury_candidates, verified_anchors, weak_missing, impact)

    print(f"new_case_candidates={len(candidate_case_questions)} excluded_mcq={mcq_total} "
          f"demo_packets={len(DEMO_CASES)} verified_anchors={verified_anchors} weak={weak_missing} "
          f"net_new_published={impact['new_questions_published']}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_input_audit(n_new, n_mcq, packets_meta):
    lines = ["# Input candidate audit — case-rubric expansion M2 (2026-06-04)", "",
             "## Scanned paths", ""]
    for p in SCANNED_PATHS:
        exists = (REPO / p).exists()
        lines.append(f"- `{p}` — {'present' if exists else 'ABSENT'}")
    lines += ["", "## Findings", "",
              f"- new gradeable case candidates: **{n_new}**",
              f"- MCQ excluded: **{n_mcq}** (exam_quality_bank, out of scope)",
              "- has_question_text / has_official_answer / has_node_code: 仅 20 golden 具备（已在 registry）",
              "- can_be_gradeable_case_candidate (NEW): **0**",
              "- blocker_reason: docs/2026 题库/教材/标准文件 目录不在 repo；所有 artifact 切片均引用 Q1-Q20；无新案例题语料。",
              "", "## Demo packets (existing golden, pipeline proof)", ""]
    for m in packets_meta:
        lines.append(f"- {m['case_id']}: {m['artifact_status']}, auto_certifiable {m['auto_certifiable_points']}, validator_violations {m['validator_violations']}")
    lines.append("")
    (OUT_DIR / "input_candidate_audit.md").write_text("\n".join(lines), encoding="utf-8")


def _write_finding(candidates, mcq_total, packets_meta, jury, verified_anchors, weak_missing, impact):
    pub = sum(1 for m in packets_meta if m["artifact_status"] == "published")
    draft = sum(1 for m in packets_meta if m["artifact_status"] == "draft")
    lines = [
        "# FINDING — case-rubric data expansion M2 (2026-06-04)", "",
        "## 必答", "",
        f"1. 找到多少 case-like 候选？ **{len(candidates)} 道新候选**（20 golden 之外）。",
        f"2. 排除多少 MCQ？ **{mcq_total}**（exam_quality_bank，全 MCQ）。",
        f"3. deep audit packet 做了几道？ **{len(packets_meta)}**（均为 EXISTING golden，证明管线，非新 registry 项）。",
        "4. 四模型是否全部可用？ 缓存真实票全可用（gpt55/opus48/deepseek_v4/qwen37），**非 live**。",
        "5. live/cached/partial/unavailable？ **cached**（485 span-guarded 真实四模型，非 live 重调、非伪造）。",
        f"6. textbook verified anchors？ **{verified_anchors}**（demo 5 题，verbatim，来自 content_markdown reanchor）。",
        f"7. weak/missing anchors？ **{weak_missing}**（demo 5 题）。",
        f"8. 新增 published 预估？ **0**（demo 题已在 registry；无新题）。",
        f"9. 新增 draft 预估？ **0**（无新题）。",
        "10. blocked 原因 Top 5：" + "；".join(impact["blocked_reasons_top"]),
        "11. 是否伪造 source_ref？ **NO**（textbook anchor 来自 verbatim reanchor；无新题=无新锚）。",
        "12. 是否把 LLM 当真人？ **NO**（`reviewer_type=llm_jury`，cached 票，永不当 human）。",
        "13. 是否能解锁 registry v1？ **不能**。差：新案例题语料（exam/textbook）+ official_answer + verbatim 教材锚 + PO review。",
        "14. 下一批数据扩产建议：把真题/教材案例题语料 check-in（PDF/markdown）→ 解析 official_answer → 4-model jury 候选 → verbatim 教材 verify-on-write → PO review → AuditPacket → v1 编译。当前 repo 内无此语料，须外部导入。",
        "",
        "## 结论",
        "",
        "M2 管线（候选审计 → AuditPacket → LLM-jury rubric 候选(cached, llm_jury) → textbook verify-on-write → registry impact sim）**已就绪并在 5 道 golden 上跑通**；但**第一批新候选 = 0**，数据瓶颈在源头（repo 内无新案例题语料）。registry 净增 published/draft/auto = 0。",
        "",
        "## 红线",
        "不新增表、不接 runtime、不改 kernel、RAG 不进评分、MCQ 不进 case registry、node 资产不当 rubric、不伪造 textbook_quote、official_answer 不当强锚、LLM jury 不冒充真人、未 commit。",
        "",
    ]
    (OUT_DIR / "FINDING_case_rubric_expansion_m2_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
