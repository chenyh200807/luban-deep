"""Phase 9 — rescue the over-flagged quarantine cohort (the 39's repairable subset).

Honest re-triage of the Stage-1 39-case quarantine (it over-flagged AGAIN, same disease as the
91-collapse and the 51-queue): reading the SOURCE data shows 25/39 have REAL answers wrongly
excluded —
  * real_answer_rescuable (10): full 【参考答案】 body + trailing 【选项分析】 boilerplate the
    normalizer strips (the over-broad `'无选项' in answer` quarantine check flagged the boilerplate).
  * jiexi_body_usable (11): 【解析】-led but the body IS the answer (normalizer preserves 【解析】).
  * score_gap_only (4): real answer, only official_total_score is null (structure compiles; score
    is a separate, non-fabricable gap flagged for the owner).
Only 14/39 are GENUINELY placeholder ("本题考查…" exam-prep meta / unpublished-year AI placeholder)
— no real answer exists, so they CANNOT be repaired without fabricating (must-not-mint forbids it).

This rescues the 25: deterministic compile (fixed normalizer/splitter) → type-conditioned multi-AI
propose (DeepSeek+Qwen) → deterministic must-not-mint guard. Extends candidate coverage 179→~204.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec_fc = importlib.util.spec_from_file_location(
    "fc", REPO / "scripts/run_luban_per_question_grading_object_full_compile.py")
FC = importlib.util.module_from_spec(spec_fc)
spec_fc.loader.exec_module(FC)
spec_run = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec_run)
spec_run.loader.exec_module(RUN)
from deeptutor.services.construction_grading.per_question_grading_object import (  # noqa: E402
    compile_per_question_grading_object)

FACDIR = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory"
OUT = FACDIR / "quarantine_rescue"
PROPOSERS = [("deepseek", "提议员A"), ("dashscope", "提议员B")]

# reuse the factory's type-conditioned prompt verbatim (one authority for the prompt)
FACTORY_SYS = (
    "你是一级建造师建筑实务案例题评分知识编译员。给你一道案例题的题干、官方参考答案(可能是散文/顿号列表)、"
    "官方解析。你要一次性产出该题的【类型条件化评分知识】。\n"
    "第一步判类型 point_type: list/flaw_correction/process/calculation/mixed/single。\n"
    "第二步按类型切原子采分点 segments(粒度由类型决定):list每并列项各成点;flaw_correction不妥+正确做法各一点"
    "正确做法完整论述不碎切;process保留完整工序句。\n"
    "铁律 must-not-mint:每个 segment.text 必须是官方答案里的【逐字连续片段】,不得改写/增删字。\n"
    "第三步授权规则:list_rule.applies + total_items;penalty_rule(题干'多答不得分'类);每段 exact_term_required。\n"
    "只输出 JSON:{\"point_type\":\"<...>\",\"segments\":[{\"text\":\"逐字\",\"is_list_item\":true|false,"
    "\"exact_term_required\":true|false}],\"list_rule\":{\"applies\":true|false,\"total_items\":<int或null>},"
    "\"penalty_rule\":{\"exists\":true|false,\"scope\":\"\",\"text\":\"\"}}"
)


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def _full_oa(obj: dict) -> str:
    return "\n".join(sq.get("official_sub_answer_verbatim") or "" for sq in obj.get("sub_questions") or [])


def _propose(call, stem, oa, analysis) -> dict:
    payload = {"题干": (stem or "")[:1000], "官方参考答案": oa, "官方解析": (analysis or "")[:600]}
    try:
        o = json.loads(call("rescue", [{"role": "system", "content": FACTORY_SYS},
                                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])["content"])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:140]}
    segs = o.get("segments") or []
    oa_h = _hanzi(oa)
    minted = [s.get("text", "")[:24] for s in segs if _hanzi(s.get("text", "")) and _hanzi(s.get("text", "")) not in oa_h]
    return {"point_type": o.get("point_type"), "n_segments": len(segs), "segments": segs,
            "list_rule": o.get("list_rule") or {}, "penalty_rule": o.get("penalty_rule") or {},
            "must_not_mint_ok": not minted}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    retri = json.loads((FACDIR / "quarantine_retriage.json").read_text("utf-8"))
    rescuable = retri["real_answer_rescuable"] + retri["score_gap_only"] + retri["jiexi_body_usable"]
    qs = FC._enumerate_case_questions(FC.DEFAULT_EXAM_ROOT)
    idx = {str(q["qid"]): q for q in qs}
    chunks = FC._load_textbook_chunks(FC.DEFAULT_BOOK_DIR)
    calls = {}
    for prov, _ in PROPOSERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=120, max_tokens=2000)
        if c is None:
            raise SystemExit(f"{prov} key missing")
        calls[prov] = c

    def work(qid):
        q = idx.get(qid)
        obj = compile_per_question_grading_object(
            question_id=qid, stem=q.get("stem") or "", correct_answer=q.get("correct_answer") or "",
            official_total_score=q.get("score"), textbook_chunks=chunks, chunk_id=q.get("chunk_id") or "",
            official_analysis=q.get("analysis"), source_path=q.get("source_path") or "")
        oa = _full_oa(obj)
        det_pts = sum(len(sq.get("scoring_points") or []) for sq in obj.get("sub_questions") or [])
        rec = {"qid": qid, "official_answer": oa, "deterministic_points": det_pts,
               "score_is_null": q.get("score") is None, "by_model": {}}
        for prov, _ in PROPOSERS:
            rec["by_model"][prov] = _propose(calls[prov], q.get("stem"), oa, q.get("analysis"))
        ds, qw = rec["by_model"]["deepseek"], rec["by_model"]["dashscope"]
        rec["mnm_clean"] = bool(ds.get("must_not_mint_ok") and qw.get("must_not_mint_ok"))
        rec["needs_arbiter"] = (ds.get("point_type") != qw.get("point_type")
                                or abs((ds.get("n_segments") or 0) - (qw.get("n_segments") or 0)) > 1
                                or not rec["mnm_clean"])
        return rec

    results = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(work, rescuable):
            results.append(r)

    n = len(results)
    mnm = sum(1 for r in results if r["mnm_clean"])
    arb = sum(1 for r in results if r["needs_arbiter"])
    score_gap = sum(1 for r in results if r["score_is_null"])
    ds_pts = sum(r["by_model"]["deepseek"].get("n_segments", 0) for r in results)
    summary = {
        "schema": "luban_quarantine_rescue.v1", "generated_at_date": "2026-06-14",
        "re_triage": {k: len(v) for k, v in retri.items()},
        "rescued_n": n, "genuinely_placeholder_unrecoverable": len(retri["genuinely_placeholder"]),
        "both_models_mnm_clean": f"{mnm}/{n}", "needs_opus_arbiter": f"{arb}/{n}",
        "score_gap_flagged_for_owner": score_gap,
        "mean_points_deepseek": round(ds_pts / n, 2) if n else 0,
        "coverage_lift": f"179 → {179 + mnm} (rescued {mnm} of 39 quarantine)",
        "honest_note": "14/39 genuinely placeholder (no real answer in source) — NOT fabricated; "
                       "score_gap cases compile structurally but official_total_score must come from owner.",
    }
    (OUT / "rescue_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    (OUT / "rescued_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
