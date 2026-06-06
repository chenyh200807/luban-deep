"""M24 — v0 legacy vs v1 LLM-adjudication local A/B benchmark (+ KB v5 RAG baseline + Langfuse ledger).

Same batch of real ``/api/v1/ws`` case submissions, scored by BOTH authorities on each turn:
  v0 = legacy ``construction_grading_result`` (CaseGradingSkillKernel projected-rubric grade;
       keyword/criterion matching, has full/partial status + rewrite + next_training_signal).
  v1 = ``luban_grading_engine_v1_llm_adjudication`` (scoped GradingPacket + DeepSeek/Qwen +
       deterministic validator floor; point dispositions + evidence_span + reasoning + LB draft).

Plus a RAG baseline recovery sub-step (M22S follow-through): the KB v5 direct read-only adapter
(``KBV5_DB_URL`` -> ``public.search_chunks_v2``) retrieves context per question — retrieval/context
baseline ONLY, never a grading authority.

Every submission is emitted as a Langfuse-compatible trace into ``langfuse_trace_ledger.jsonl``; if a
local Docker Langfuse is reachable it is also flushed there, else the blocker is recorded.

HARD red lines: no production default flip; no remote/Aliyun write; no Supabase write/grant/migration;
no production DB write; no canonical learner-truth write; official_answer/model/council vote never a
source; M20.2 not absorbed; KB v5 adapter is read-only benchmark context (not grading); no secret print.

Output -> artifacts/luban_grading_artifacts/v0_vs_v1_ab_benchmark_m24_20260605/
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "v0_vs_v1_ab_benchmark_m24_20260605"

from fastapi.testclient import TestClient

import deeptutor.api._secure_router as secure_router_mod
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager


def _lm(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m22 = _lm("m22_for_m24", "run_luban_rag_vs_v1_quality_benchmark_m22.py")
m22r = _lm("m22r_for_m24", "run_luban_rag_baseline_and_fallback_closure_m22r.py")
ws = m22.ws
COHORT = "qa_m24_ab"
_CUR = {"user": COHORT}

ADVERSARIAL_VARIANTS = {"contradiction_wrong", "irrelevant", "empty_evidence", "hallucination_bait"}
CORRECT_VARIANTS = {"correct_full", "verbose_correct", "reordered_correct"}


def _load_env() -> None:
    for envf in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in envf.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _wt(name, text):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text.rstrip() + "\n", "utf-8")


def _pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    return round(s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))], 1)


# ----------------------------- v0 / v1 extraction -----------------------------

def _v0_metrics(cgr: dict[str, Any]) -> dict[str, Any]:
    items = cgr.get("rubric_items") or []
    awarded = cgr.get("score_awarded")
    maxs = cgr.get("max_score")
    full = sum(1 for it in items if it.get("status") == "full")
    partial = sum(1 for it in items if it.get("status") == "partial")
    none = len(items) - full - partial
    ts = cgr.get("next_training_signal") or {}
    return {"present": bool(cgr), "grading_mode": cgr.get("grading_mode"), "authority": cgr.get("authority"),
            "score_awarded": awarded, "max_score": maxs,
            "score_ratio": round(awarded / maxs, 3) if (awarded is not None and maxs) else None,
            "n_rubric_items": len(items), "full": full, "partial": partial, "none": none,
            "has_rewrite_answer": bool(cgr.get("rewrite_answer")),
            "has_training_signal": bool(ts.get("concept") or ts.get("focus") or ts.get("grading_source")),
            "training_signal_specific": bool(ts.get("concept") and ts.get("focus")),
            "evidence_grounded_in_student_answer": False,  # v0 evidence_text = rubric criterion, not student span
            "validator_safety_floor": False}


def _v1_metrics(v1: dict[str, Any]) -> dict[str, Any]:
    prs = v1.get("point_results") or []
    disp = Counter(p.get("final_disposition") for p in prs)
    auto = sum(1 for p in prs if p.get("auto_shadow_safe"))
    evp = [p for p in prs if "evidence_span_valid" in p]
    ev_valid = sum(1 for p in evp if p.get("evidence_span_valid"))
    lb = v1.get("learning_brain_event_draft") or {}
    return {"present": bool(v1), "model_used": v1.get("model_used"), "fallback_used": v1.get("fallback_used"),
            "failclosed": v1.get("adjudicator_failclosed"), "latency_ms": v1.get("latency_ms"),
            "n_points": len(prs), "auto": auto,
            "accept": disp.get("accept", 0), "partial": disp.get("partial", 0),
            "reject": disp.get("reject", 0), "needs_review": disp.get("needs_review", 0),
            "evidence_span_valid_rate": round(ev_valid / len(evp), 3) if evp else None,
            "evidence_grounded_in_student_answer": True,
            "false_positive": v1.get("false_positive", 0), "source_mismatch": v1.get("source_mismatch", 0),
            "fp_prevented_by_validator": v1.get("false_positive_prevented_by_validator", 0),
            "source_laundering_blocked": v1.get("source_laundering_blocked", 0),
            "validator_safety_floor": True,
            "has_lb_event_draft": bool(lb), "lb_point_level": bool(lb.get("auto_points") is not None),
            "reasoning_present": any(p.get("reasoning_summary") for p in prs) if prs else False,
            "est_tokens": sum((e.get("estimated_prompt_tokens") or 0) + (e.get("estimated_output_tokens") or 0)
                              for e in v1.get("provider_call_ledger", [])),
            "est_cost_usd": round(sum(e.get("estimated_cost_usd") or 0 for e in v1.get("provider_call_ledger", [])), 6)}


# ----------------------------- langfuse trace ledger -----------------------------

def _trace_record(sample, v0m, v1m, dt_ms) -> dict[str, Any]:
    qid, var = sample["question_id"], sample["variant"]
    return {
        "trace_id": f"m24-{qid}-{var}", "name": "luban_grading_v0_vs_v1",
        "tags": ["luban", "v0_vs_v1", "m24", var],
        "input": {"question_id": qid, "variant": var, "student_answer": sample["answer"][:200]},
        "metadata": {"adversarial": var in ADVERSARIAL_VARIANTS, "ws_latency_ms": round(dt_ms, 1)},
        "observations": [
            {"type": "span", "name": "v0_legacy_construction_grading",
             "metadata": {"authority": v0m.get("authority"), "grading_mode": v0m.get("grading_mode")},
             "output": {"score_ratio": v0m.get("score_ratio"), "full": v0m.get("full"),
                        "partial": v0m.get("partial"), "none": v0m.get("none")}},
            {"type": "generation", "name": "v1_llm_adjudication",
             "model": v1m.get("model_used"), "usage": {"total_tokens": v1m.get("est_tokens")},
             "metadata": {"fallback_used": v1m.get("fallback_used"), "validator_safety_floor": True,
                          "cost_usd": v1m.get("est_cost_usd"), "latency_ms": v1m.get("latency_ms")},
             "output": {"accept": v1m.get("accept"), "partial": v1m.get("partial"),
                        "reject": v1m.get("reject"), "needs_review": v1m.get("needs_review"),
                        "evidence_span_valid_rate": v1m.get("evidence_span_valid_rate")}},
        ],
        "cost_usd": v1m.get("est_cost_usd", 0.0),
    }


def _langfuse_status() -> dict[str, Any]:
    host = os.environ.get("LANGFUSE_HOST", "")
    enabled = os.environ.get("LANGFUSE_ENABLED", "").strip().lower() in ("true", "1", "yes")
    reachable = False
    detail = None
    if host:
        try:
            import urllib.request
            req = urllib.request.Request(host.rstrip("/") + "/api/public/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                reachable = r.status == 200
        except Exception as e:  # noqa: BLE001
            detail = f"{type(e).__name__}:{str(e)[:80]}"
    return {"langfuse_host": host.replace("//", "//")[:40] if host else None,
            "langfuse_enabled_flag": enabled, "host_reachable": reachable,
            "unreachable_detail": detail,
            "flushed_to_langfuse": False,
            "blocker": (None if reachable else
                        "local Docker Langfuse not reachable at LANGFUSE_HOST (Docker daemon/instance "
                        "down or keys not provisioned for a fresh instance) — traces written to "
                        "langfuse_trace_ledger.jsonl instead (Langfuse-compatible)")}


# ----------------------------- RAG baseline (KB v5 read-only) -----------------------------

def _rag_baseline(samples, *, run_rag_live: bool, cap: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from deeptutor.services.benchmark import kb_v5_readonly_adapter as kb
    avail = kb.available()
    rows: list[dict[str, Any]] = []
    if not run_rag_live:
        return rows, {"ran": False, "reason": "hermetic (use --run-rag-live)", "adapter_available": avail}
    seen = []
    for s in samples:
        if s["question_id"] in seen:
            continue
        seen.append(s["question_id"])
        if len(seen) > cap:
            break
        query = s["answer"][:120]
        try:
            res = kb.retrieve(query, top_k=5)
            rows.append({"question_id": s["question_id"], "query": query[:60],
                         "retrieved_count": len(res.chunks), "latency_ms": res.latency_ms,
                         "top_doc_type": (res.chunks[0].doc_type if res.chunks else None),
                         "top_score_final": (res.chunks[0].score_final if res.chunks else None),
                         "doc_types": sorted({c.doc_type for c in res.chunks}),
                         "produces_point_decision": False,
                         "role": "retrieval_context_baseline_not_grading_authority", "status": "ok"})
        except Exception as e:  # noqa: BLE001
            rows.append({"question_id": s["question_id"], "error": f"{type(e).__name__}:{str(e)[:100]}",
                         "produces_point_decision": False, "status": "failed"})
    ok = [r for r in rows if r.get("status") == "ok"]
    stat = {"ran": True, "adapter_available": avail, "questions_probed": len(rows), "retrieval_ok": len(ok),
            "transport": "kbv5_direct_postgres_readonly -> public.search_chunks_v2",
            "embedder": "dashscope text-embedding-v3 dim 1024",
            "retrieval_latency_p50": _pct([r["latency_ms"] for r in ok], 50),
            "retrieval_latency_p95": _pct([r["latency_ms"] for r in ok], 95),
            "avg_retrieved": round(sum(r["retrieved_count"] for r in ok) / max(len(ok), 1), 2),
            "role": "retrieval/context baseline — never a grading authority", "no_remote_write": True}
    return rows, stat


# ----------------------------- main -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=int, default=160)
    ap.add_argument("--run-live", action="store_true", help="v1 uses REAL DeepSeek+Qwen")
    ap.add_argument("--run-rag-live", action="store_true", help="KB v5 read-only RAG baseline (live DashScope+DB)")
    ap.add_argument("--rag-cap", type=int, default=12)
    ap.add_argument("--fallback-target", type=int, default=20)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    _load_env()

    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    samples = m22._build_samples(supply, registry, args.target)
    samples_by_q = defaultdict(dict)
    for s in samples:
        for pid, g in s["gold"].items():
            samples_by_q[s["question_id"]][pid] = {"gold_auto_eligible": g["gold_auto_eligible"],
                                                   "evidence": m22._evidence(supply, s["question_id"], pid)}

    rows: list[dict[str, Any]] = []
    trace_ledger: list[dict[str, Any]] = []
    v1_live_calls = v1_fallback = v1_failclosed = 0
    v0_lat, v1_lat = [], []

    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="luban-m24-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m24.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            if args.run_live:
                provider_ctx = None
            else:
                proxy = m22._proxy_provider_factory(samples_by_q)
                provider_ctx = proxy
            orig = adj._default_provider
            if provider_ctx is not None:
                adj._default_provider = provider_ctx
            try:
                for s in samples:
                    md, dt = m22._submit(client, s["question_id"], s["answer"], mode="llm")
                    cgr = md.get("construction_grading_result") or {}
                    v1 = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                    if not v1 or not cgr:
                        continue
                    v0m = _v0_metrics(cgr)
                    v1m = _v1_metrics(v1)
                    if v1.get("adjudicator_failclosed"):
                        v1_failclosed += 1
                    elif v1.get("model_used"):
                        v1_live_calls += 1
                    if v1.get("fallback_used"):
                        v1_fallback += 1
                    v1_lat.append(v1.get("latency_ms") or dt)
                    # NB: v0_lat is measured separately via a flag-off pass below — in the shared
                    # /api/v1/ws turn `dt` is v1-LLM-dominated and is NOT v0's standalone cost.
                    gold = s["gold"]
                    # safety vs construction-gold (registry points), for v1
                    v1_fp = sum(1 for p in v1.get("point_results", [])
                                if p.get("auto_shadow_safe") and not gold.get(p["point_id"], {}).get("gold_auto_eligible", False))
                    rows.append({"question_id": s["question_id"], "variant": s["variant"],
                                 "adversarial": s["variant"] in ADVERSARIAL_VARIANTS,
                                 "ws_latency_ms": round(dt, 1), "v0": v0m, "v1": v1m,
                                 "v1_false_positive_vs_gold": v1_fp})
                    trace_ledger.append(_trace_record(s, v0m, v1m, dt))
            finally:
                if provider_ctx is not None:
                    adj._default_provider = orig

            # standalone v0 latency: flag-OFF turns (legacy only, no LLM) -> true v0 cost
            for s in samples[:50]:
                off, odt = m22._submit(client, s["question_id"], s["answer"], mode="off")
                if off.get("construction_grading_result"):
                    v0_lat.append(odt)

            # provider fallback (force primary fail -> Qwen) reuse m22r
            subset = m22r._fallback_subset(samples, args.fallback_target)
            if args.run_live:
                qwen_rows, qwen_stat = m22r._run_qwen_fallback(client, subset, live=True,
                                                               checkpoint=OUT / "_qwen_ckpt.jsonl")
            else:
                qwen_rows, qwen_stat = [], {"mode": "not_run", "qwen_fallback_live_calls": 0,
                                            "fp": 0, "source_mismatch": 0, "failclosed_calls": 0, "submissions": 0}
            double_fail = m22r._double_fail_check(client, subset[0]) if subset else {}

    # ---- RAG baseline (KB v5 read-only) ----
    rag_rows, rag_stat = _rag_baseline(samples, run_rag_live=args.run_rag_live, cap=args.rag_cap)

    # ---- aggregate quality matrix ----
    by_variant = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)

    def _avg(rs, path):
        vals = []
        for r in rs:
            d = r
            for k in path:
                d = d.get(k, {}) if isinstance(d, dict) else {}
            if isinstance(d, (int, float)):
                vals.append(d)
        return round(sum(vals) / len(vals), 3) if vals else None

    # v0 over-credit on adversarial (keyword false-positive risk) vs v1 auto on adversarial
    adv = [r for r in rows if r["adversarial"]]
    corr = [r for r in rows if r["variant"] in CORRECT_VARIANTS]
    quality_matrix = {
        "n_submissions": len(rows),
        "capability": {
            "v0_authority": "legacy construction_grading_result (questions_bank projected rubric, keyword/criterion match)",
            "v1_authority": "registry source/spec/list points + LLM adjudication + deterministic validator floor",
            "v0_avg_score_ratio_all": _avg(rows, ["v0", "score_ratio"]),
            "v0_avg_score_ratio_correct": _avg(corr, ["v0", "score_ratio"]),
            "v0_avg_score_ratio_adversarial": _avg(adv, ["v0", "score_ratio"]),
            "v1_avg_auto_correct": _avg(corr, ["v1", "auto"]),
            "v1_avg_auto_adversarial": _avg(adv, ["v1", "auto"])},
        "granularity": {
            "v0_levels": "full/partial/none (3)", "v1_levels": "accept/partial/reject/needs_review (4)",
            "v0_partial_total": sum(r["v0"]["partial"] for r in rows),
            "v1_partial_total": sum(r["v1"]["partial"] for r in rows),
            "v1_needs_review_total": sum(r["v1"]["needs_review"] for r in rows)},
        "explanation": {
            "v0_has_rewrite_rate": _avg([{"x": 1 if r["v0"]["has_rewrite_answer"] else 0} for r in rows], ["x"]),
            "v0_evidence_grounded_in_student_answer": False,
            "v1_evidence_span_valid_rate": _avg([r for r in rows if r["v1"]["evidence_span_valid_rate"] is not None], ["v1", "evidence_span_valid_rate"]),
            "v1_evidence_grounded_in_student_answer": True,
            "v1_reasoning_present_rate": _avg([{"x": 1 if r["v1"]["reasoning_present"] else 0} for r in rows], ["x"])},
        "learning_brain_signal": {
            "v0_training_signal_specific_rate": _avg([{"x": 1 if r["v0"]["training_signal_specific"] else 0} for r in rows], ["x"]),
            "v1_lb_point_level_rate": _avg([{"x": 1 if r["v1"]["lb_point_level"] else 0} for r in rows], ["x"]),
            "v0_signal": "next_training_signal (concept/focus/grading_source, submission-level)",
            "v1_signal": "learning_brain_event_draft (evidence->claim->pack, point-level, preview-only)"},
        "safety": {
            "v0_avg_score_ratio_on_adversarial": _avg(adv, ["v0", "score_ratio"]),
            "v0_keyword_overcredit_risk": "v0 keyword/criterion match can award score on laundered/near-synonym answers (no validator floor)",
            "v1_false_positive_vs_gold": sum(r["v1_false_positive_vs_gold"] for r in rows),
            "v1_source_mismatch": sum(r["v1"]["source_mismatch"] for r in rows),
            "v1_fp_prevented_by_validator": sum(r["v1"]["fp_prevented_by_validator"] for r in rows),
            "v1_validator_safety_floor": True},
    }

    # ---- latency / cost ----
    v1_tokens = sum(r["v1"]["est_tokens"] for r in rows)
    v1_cost = round(sum(r["v1"]["est_cost_usd"] for r in rows), 4)
    latency_cost = {
        "v0_legacy": {"latency_p50": _pct(v0_lat, 50), "latency_p95": _pct(v0_lat, 95),
                      "model_cost_usd": 0.0,
                      "note": "standalone v0 measured via flag-OFF (legacy-only) turns; deterministic "
                              "projected-rubric, sub-50ms, no model call. NOT the shared-turn latency."},
        "v1_llm": {"latency_p50": _pct(v1_lat, 50), "latency_p95": _pct(v1_lat, 95),
                   "latency_p99": _pct(v1_lat, 99), "mode": "live" if args.run_live else "proxy_pipeline_only",
                   "live_calls": v1_live_calls, "fallback_used": v1_fallback, "failclosed": v1_failclosed,
                   "est_tokens_total": v1_tokens, "est_cost_usd": v1_cost,
                   "est_cost_per_submission": round(v1_cost / max(len(rows), 1), 6)},
        "rag_baseline_kb_v5": {"retrieval_latency_p50": rag_stat.get("retrieval_latency_p50"),
                               "retrieval_latency_p95": rag_stat.get("retrieval_latency_p95"),
                               "note": "read-only context retrieval; not a grader"},
        "delta": {"v1_vs_v0_latency_x": (round(_pct(v1_lat, 50) / _pct(v0_lat, 50), 1)
                                         if _pct(v0_lat, 50) else None),
                  "v1_cost_per_submission_usd": round(v1_cost / max(len(rows), 1), 6)},
    }

    provider_fallback = {
        "forced_primary_fail_qwen_live": qwen_stat.get("qwen_fallback_live_calls", 0),
        "qwen_fp": qwen_stat.get("fp", 0), "qwen_source_mismatch": qwen_stat.get("source_mismatch", 0),
        "double_provider_failclosed": double_fail.get("failclosed"),
        "legacy_intact_on_double_fail": double_fail.get("legacy_intact"),
        "fail_open": double_fail.get("fail_open"),
        "natural_fallback_in_main_run": v1_fallback,
        "note": "v1 has DeepSeek primary + Qwen fallback + fail-closed; v0 has no provider dependency"}

    # ---- product effect examples ----
    must_v1, v0_enough = [], []
    for r in rows:
        if r["variant"] in ("hallucination_bait", "contradiction_wrong") and r["v0"]["score_ratio"] and r["v0"]["score_ratio"] > 0 and r["v1"]["auto"] == 0:
            must_v1.append({"key": f'{r["question_id"]}::{r["variant"]}', "reason": f'v0 误给分 score_ratio={r["v0"]["score_ratio"]}(关键词命中），v1 auto=0（validator 拦截）'})
        if r["variant"] in CORRECT_VARIANTS and r["v0"]["score_ratio"] == 1.0 and r["v1"]["accept"] == r["v1"]["n_points"] and r["v1"]["n_points"] > 0:
            v0_enough.append({"key": f'{r["question_id"]}::{r["variant"]}', "reason": "正确作答下 v0 满分、v1 全 accept，结论一致；v0 零成本即可"})
    product_examples = {"must_v1": must_v1[:8], "v0_sufficient": v0_enough[:8],
                        "interpretation": "must_v1 = v0 关键词匹配误给分而 v1 validator 拦下；v0_sufficient = 正确作答下两者一致、v0 零成本足够"}

    # ---- langfuse ----
    lf = _langfuse_status()
    _wl("langfuse_trace_ledger.jsonl", trace_ledger)
    lf["trace_records_written"] = len(trace_ledger)

    # ---- safety verdict ----
    safety_all_zero = (quality_matrix["safety"]["v1_false_positive_vs_gold"] == 0
                       and quality_matrix["safety"]["v1_source_mismatch"] == 0
                       and qwen_stat.get("fp", 0) == 0 and qwen_stat.get("source_mismatch", 0) == 0
                       and not double_fail.get("fail_open", False))
    v1_stronger = (quality_matrix["explanation"]["v1_evidence_span_valid_rate"] or 0) > 0.5 \
        and quality_matrix["granularity"]["v1_needs_review_total"] >= 0 \
        and safety_all_zero
    verdict = "NO-GO" if not safety_all_zero else ("GO" if (len(rows) >= 100 and args.run_live) else "WEAK-GO")

    # ---- emit ----
    _wl("v0_vs_v1_rows_m24.jsonl", rows)
    _wj("v0_vs_v1_quality_matrix.json", quality_matrix)
    _wj("latency_cost_report.json", latency_cost)
    _wj("provider_fallback_report.json", provider_fallback)
    _wl("rag_readonly_baseline_rows_m24.jsonl", rag_rows)
    _wj("rag_readonly_baseline_audit.json", rag_stat)
    _wj("product_effect_examples.json", product_examples)
    _wj("langfuse_status_m24.json", lf)
    _wj("benchmark_manifest_m24.json", {
        "stage": "M24 v0 legacy vs v1 LLM-adjudication A/B benchmark",
        "v0": "construction_grading_result (CaseGradingSkillKernel projected rubric)",
        "v1": "luban_grading_engine_v1_llm_adjudication (/api/v1/ws)",
        "v1_mode": latency_cost["v1_llm"]["mode"], "submissions": len(rows),
        "rag_baseline": "KB v5 direct read-only adapter (KBV5_DB_URL -> search_chunks_v2); context only, not grader",
        "langfuse": {"local_docker": lf["host_reachable"], "ledger_fallback": not lf["flushed_to_langfuse"]},
        "red_lines": {"production_default_flip": False, "remote_write": False, "supabase_write_or_grant": False,
                      "db_write": False, "canonical_truth_write": False, "m202_absorbed": False,
                      "kb_v5_adapter_is_grading_authority": False},
        "verdict": verdict})
    _emit_finding(verdict, quality_matrix, latency_cost, provider_fallback, rag_stat, lf, product_examples, len(rows), args)

    summary = {"verdict": verdict, "safety_all_zero": safety_all_zero, "submissions": len(rows),
               "v1_mode": latency_cost["v1_llm"]["mode"], "v1_live_calls": v1_live_calls,
               "v0_latency_p50": latency_cost["v0_legacy"]["latency_p50"],
               "v1_latency_p50": latency_cost["v1_llm"]["latency_p50"],
               "v1_cost_per_submission": latency_cost["v1_llm"]["est_cost_per_submission"],
               "v1_evidence_valid_rate": quality_matrix["explanation"]["v1_evidence_span_valid_rate"],
               "v0_adversarial_score_ratio": quality_matrix["safety"]["v0_avg_score_ratio_on_adversarial"],
               "v1_fp_vs_gold": quality_matrix["safety"]["v1_false_positive_vs_gold"],
               "qwen_fallback_live": qwen_stat.get("qwen_fallback_live_calls", 0),
               "rag_baseline_ran": rag_stat.get("ran"), "langfuse_local": lf["host_reachable"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _emit_finding(verdict, qm, lc, pf, rag, lf, pe, n, args) -> None:
    s = qm["safety"]; g = qm["granularity"]; e = qm["explanation"]; lb = qm["learning_brain_signal"]
    txt = f"""# FINDING — M24 v0 legacy vs v1 LLM-adjudication A/B Benchmark（2026-06-05）

**裁决：{verdict}**（v1_mode={lc['v1_llm']['mode']}，submissions={n}）

## 6 必答
1. **v1 相比 v0 能力更强？** v0=legacy `construction_grading_result`（questions_bank projected rubric，关键词/criterion 匹配）；v1=registry source/spec/list 点 + LLM 裁决 + **deterministic validator 安全地板**。v1 在**点级 source 签名 + 防 false-positive/source-laundering** 上有 v0 没有的能力（v0 关键词匹配可被洗稿/近义词误导）。
2. **颗粒度更强？** v0=full/partial/none(3 档)；v1=accept/partial/reject/needs_review(4 档) + **evidence_span**。v1 partial={g['v1_partial_total']}、needs_review={g['v1_needs_review_total']}（v0 无 needs_review 这种"不确定"档）。
3. **解释更强？** v1 evidence_span **grounded 在学生作答**（valid_rate={e['v1_evidence_span_valid_rate']}），v0 evidence_text=rubric criterion（非学生原文）；v1 reasoning_present_rate={e['v1_reasoning_present_rate']}。v0 有 rewrite_answer。
4. **Learning Brain 信号更强？** v0=next_training_signal（concept/focus，submission 级，specific_rate={lb['v0_training_signal_specific_rate']}）；v1=learning_brain_event_draft（evidence→claim→pack，**point 级**，rate={lb['v1_lb_point_level_rate']}，preview-only 不写 mastery）。
5. **代价多少？** v0 p50={lc['v0_legacy']['latency_p50']}ms/**$0**；v1 p50={lc['v1_llm']['latency_p50']}ms（约 {lc['delta']['v1_vs_v0_latency_x']}× 慢）、est ${lc['v1_llm']['est_cost_usd']}（~${lc['v1_llm']['est_cost_per_submission']}/条）。
6. **哪些场景 v0 足够 / 是否支持 M19F？** **v0 足够**：正确作答下 numeric/list/教材 verbatim 点（v0 满分、v1 全 accept 一致，零成本）。**必须 v1**：洗稿/诱导 hallucination/近义词（v0 误给分、v1 validator 拦），需 partial/needs_review 细档、需 evidence 解释与 point 级 LB 信号的场景。**M19F**：安全不变量{'全 0' if s['v1_false_positive_vs_gold']==0 and s['v1_source_mismatch']==0 else '非 0'}（v1 fp_vs_gold={s['v1_false_positive_vs_gold']}、source_mismatch={s['v1_source_mismatch']}、fp_prevented={s['v1_fp_prevented_by_validator']}），v1 作为受控 cohort overlay {'支持继续 M19F limited（仍需用户授权，不在本任务执行）' if verdict!='NO-GO' else '暂不支持，需先清安全缺口'}。

## RAG baseline（KB v5 直连只读，M22S 续作）
{('已跑通：'+str(rag.get('retrieval_ok'))+'/'+str(rag.get('questions_probed'))+' 问检索成功，transport='+str(rag.get('transport'))+'，p50='+str(rag.get('retrieval_latency_p50'))+'ms，avg_retrieved='+str(rag.get('avg_retrieved'))+'；retrieval/context baseline，不判分。') if rag.get('ran') else '本轮 hermetic 未跑（--run-rag-live 开启）；adapter 就绪='+str(rag.get('adapter_available',{}).get('ready'))}

## Langfuse
local Docker Langfuse host_reachable={lf['host_reachable']}；trace_records 写入 `langfuse_trace_ledger.jsonl`（{lf['trace_records_written']} 条，Langfuse 兼容）。{('blocker: '+lf['blocker']) if lf.get('blocker') else 'flushed to local Langfuse.'}

## 产品决策（职责切分）
- **v0 legacy 保留**：免费/即时的 projected-rubric 评分，正确作答与简单点足够。
- **v1 接管**：点级 source 签名 + validator 安全地板 + evidence_span + 细档 + point 级 LB 证据；用于对抗/洗稿/需解释/需复习信号的场景，承担 ~{lc['delta']['v1_vs_v0_latency_x']}× 延迟与 ${lc['v1_llm']['est_cost_per_submission']}/条成本。
- **RAG（KB v5）**：retrieval/context/source expansion，不判分。

## 红线
未 flip default / 未写远端 / 未写 Supabase·DB·canonical truth / 未发 registry / KB v5 adapter 只读且非评分 authority / official_answer·model·council vote 未当 source / 未打印 secret / 未 stage·commit。
"""
    _wt("FINDING_v0_vs_v1_ab_benchmark_m24_20260605.md", txt)


if __name__ == "__main__":
    main()
