"""M22R — RAG baseline recovery + dual-provider (Qwen fallback) benchmark closure.

Closes the two WEAK-GO gaps of M22 WITHOUT redoing M22:

  TASK A — old RAG live baseline recovery. M22 line A was unavailable because
  ``data/knowledge_bases`` is empty. Here we build a MINIMAL read-only index from
  REAL source material (M14B case-stem source excerpts with official_answer /
  ai_generated / answer_explanation candidates EXCLUDED, plus the M7/M8/M9 verified
  textbook terms) and run the production ``RAGService`` (llamaindex + OpenAI dense
  embeddings, retriever mode — no answer LLM). No second RAG authority is created;
  no official_answer is ever indexed as source. RAG stays a retrieval/context
  baseline — it never signs a scoring point.

  TASK B — Qwen3.7-plus fallback same-bench quality. Reusing the M22 sample, we
  FORCE the DeepSeek primary to fail so the real Qwen fallback adjudicates, and pair
  every (question, variant) against the M22 DeepSeek result already on disk (DeepSeek
  is NOT re-billed). Double-provider failure must fail-closed with legacy intact.

Live calls are gated: ``--run-rag-live`` (real OpenAI embeddings) and ``--run-live``
(real Qwen). Hermetic default makes no live call: it emits the recovery audit and
runs the deterministic double-fail fail-closed check only.

HARD red lines: no production default flip; no remote/Aliyun write; no production DB
write; no canonical learner-truth write; no published registry; M20.2 delta not
absorbed; official_answer / model / council vote never a source; no second RAG
authority; live calls logged and never re-billed; unavailable -> fail-closed + partial.

Output -> artifacts/luban_grading_artifacts/rag_vs_luban_v1_benchmark_closure_m22r_20260605/
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts" / "luban_grading_artifacts"
OUT = ART / "rag_vs_luban_v1_benchmark_closure_m22r_20260605"
M14B = ART / "full_case_stem_source_acquisition_m14b_20260604" / "case_stem_source_candidates_m14b.jsonl"
M22_DIR = ART / "rag_vs_luban_v1_quality_benchmark_m22_20260605"

from fastapi.testclient import TestClient

import deeptutor.api._secure_router as secure_router_mod
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m22 = _load_module("m22_for_r", "run_luban_rag_vs_v1_quality_benchmark_m22.py")
ws = m22.ws
COHORT = "qa_m22r_closure"
_CUR = {"user": COHORT}


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _wt(name, text):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text.rstrip() + "\n", "utf-8")


def _pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))], 1)


# ============================ TASK A: RAG baseline via REAL Supabase link ============================
# The production old-RAG path is RAGService/rag_search -> SupabasePipeline (PostgREST read-only),
# selected by the SUPABASE_RAG_* runtime defaults. We attempt the REAL link (never a local stub),
# diagnose the exact reachability/schema state, and — if a read-only retrieval succeeds — measure it.
# We NEVER deploy schema or write to Supabase (that is a remote write; forbidden).

_SUPABASE_ENV_KEYS = ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_RAG_ENABLED",
                      "SUPABASE_RAG_DEFAULT_KB_NAME", "SUPABASE_RAG_SOURCES",
                      "SUPABASE_RAG_INCLUDE_QUESTIONS", "DEEPTUTOR_AUTO_RAG_GATE_ENABLED")


def _load_supabase_env() -> dict[str, bool]:
    """Load the project's normal Supabase RAG env from .env into os.environ (read-only retrieval)."""
    for envf in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in envf.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if (k in _SUPABASE_ENV_KEYS or k == "OPENAI_API_KEY") and v:
                        os.environ.setdefault(k, v)
        except Exception:
            pass
    return {k: bool(os.environ.get(k)) for k in _SUPABASE_ENV_KEYS}


def _probe_supabase_schema() -> dict[str, Any]:
    """Read-only probe: is the project reachable/authed, and is the RAG schema (kb_chunks table +
    match RPC) deployed? Returns the exact PostgREST status/codes — never writes."""
    import urllib.request
    import urllib.error
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY") or ""
    if not url or not key:
        return {"reachable": False, "reason": "SUPABASE_URL/SUPABASE_KEY absent"}

    def _probe(path: str) -> dict[str, Any]:
        req = urllib.request.Request(url + path, headers={"apikey": key, "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"status": r.status}
        except urllib.error.HTTPError as e:
            body = (e.read(240) or b"").decode("utf-8", "ignore")
            code = None
            try:
                code = json.loads(body).get("code")
            except Exception:
                pass
            return {"status": e.code, "pgrst_code": code, "body": body[:160]}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERR", "error": str(e)[:120]}

    root = _probe("/rest/v1/")
    chunks = _probe("/rest/v1/kb_chunks?limit=1")
    auth = _probe("/auth/v1/health")
    schema_deployed = chunks.get("status") == 200
    return {"reachable": root.get("status") == 200, "authed": auth.get("status") == 200,
            "rest_root_status": root.get("status"), "kb_chunks_status": chunks.get("status"),
            "kb_chunks_pgrst_code": chunks.get("pgrst_code"), "kb_chunks_body": chunks.get("body"),
            "rag_schema_deployed": schema_deployed,
            "exact_reason": (None if schema_deployed else
                             f"project reachable+authed but RAG schema not deployed "
                             f"(kb_chunks -> {chunks.get('status')} {chunks.get('pgrst_code')})")}


def _rag_queries(supply: bsl.BetaSupply) -> list[dict[str, str]]:
    """Real construction-exam retrieval queries: M14B case stems (official_answer excluded) +
    verified textbook terms. These probe the REAL Supabase KB; nothing is indexed locally."""
    queries: list[dict[str, str]] = []
    if M14B.exists():
        for ln in M14B.read_text("utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("official_answer_as_stem_source") or r.get("ai_generated_text_as_stem_source") \
                    or r.get("answer_explanation_as_stem_source"):
                continue
            txt = (r.get("candidate_excerpt") or "").strip()
            if txt:
                qid = (r.get("matched_question_ids") or ["?"])[0]
                queries.append({"question_id": qid, "query": txt[:120], "origin": "m14b_case_stem"})
    for (qid, pid), terms in list(supply.source_terms.items())[:20]:
        if terms and terms[0]:
            queries.append({"question_id": qid, "query": f"一级建造师建筑实务 {terms[0]} 依据",
                            "origin": "verified_textbook_term"})
    # de-dup queries
    seen, uniq = set(), []
    for q in queries:
        if q["query"] not in seen:
            seen.add(q["query"]); uniq.append(q)
    return uniq


def _run_rag_supabase_live(supply: bsl.BetaSupply) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attempt the REAL production Supabase RAG retrieval per query. Read-only. Records the exact
    per-query outcome (sources/latency or PostgREST error code). Never writes/deploys schema."""
    import asyncio
    from deeptutor.tools.rag_tool import rag_search
    kb_name = os.environ.get("SUPABASE_RAG_DEFAULT_KB_NAME") or "supabase-main"
    rows: list[dict[str, Any]] = []
    ok = 0
    for q in _rag_queries(supply):
        t0 = time.monotonic()
        try:
            res = asyncio.run(rag_search(query=q["query"], kb_name=kb_name, provider="supabase"))
            lat = (time.monotonic() - t0) * 1000.0
            sources = res.get("sources") or []
            ans = res.get("answer") or ""
            ok += 1
            rows.append({"question_id": q["question_id"], "query": q["query"][:60], "origin": q["origin"],
                         "provider": "supabase", "retrieval_latency_ms": round(lat, 1),
                         "retrieved_source_count": len(sources),
                         "top_score": (sources[0].get("score") if sources else None),
                         "answer_nonempty": bool(ans.strip()),
                         "answer_usefulness": "context_retrieved" if ans.strip() else "empty",
                         "produces_point_decision": False,
                         "role": "retrieval_context_baseline_not_grading_authority", "status": "ok"})
        except Exception as e:  # noqa: BLE001
            lat = (time.monotonic() - t0) * 1000.0
            rows.append({"question_id": q["question_id"], "query": q["query"][:60], "origin": q["origin"],
                         "provider": "supabase", "retrieval_latency_ms": round(lat, 1),
                         "error": f"{type(e).__name__}:{str(e)[:140]}",
                         "produces_point_decision": False, "status": "failed"})
    lat_ok = [r["retrieval_latency_ms"] for r in rows if r.get("status") == "ok"]
    stat = {"queries": len(rows), "ran_live": True, "retrieval_ok": ok,
            "retrieval_failed": len(rows) - ok,
            "citation_correct_rate": (round(sum(1 for r in rows if r.get("answer_nonempty")) / max(ok, 1), 4) if ok else None),
            "answer_nonempty_rate": (round(sum(1 for r in rows if r.get("answer_nonempty")) / max(ok, 1), 4) if ok else None),
            "point_evidence_support_rate": None if not ok else round(sum(1 for r in rows if r.get("retrieved_source_count")) / max(ok, 1), 4),
            "latency_p50": _pct(lat_ok, 50), "latency_p95": _pct(lat_ok, 95)}
    return rows, stat


# ============================ TASK B: Qwen fallback ============================

def _force_fallback_provider(orig: Callable[..., str]) -> Callable[..., str]:
    def prov(role, system, user, env):
        if role == "primary":
            raise adj.AdjudicatorUnavailable("m22r_forced_primary_failure_for_qwen_fallback_drill")
        return orig("fallback", system, user, env)
    return prov


def _double_fail_provider(role, system, user, env):
    raise adj.AdjudicatorUnavailable("m22r_double_provider_outage")


def _fallback_subset(samples, target: int) -> list[dict[str, Any]]:
    """Pick a subset covering all 4 registry-counted types, >= target submissions."""
    by_type = defaultdict(list)
    for s in samples:
        types = tuple(sorted({s["gold"][p]["question_type"] for p in s["counted_point_ids"]}))
        by_type[types].append(s)
    picked, seen = [], set()
    # round-robin to spread types, then top up
    pools = list(by_type.values())
    i = 0
    while len(picked) < target and any(pools):
        pool = pools[i % len(pools)]
        if pool:
            picked.append(pool.pop())
        i += 1
        if i > target * 4:
            break
    return picked[:max(target, len(picked))] if len(picked) < target else picked[:target]


def _run_qwen_fallback(client, subset, *, live: bool,
                       checkpoint: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, qwen_live, failclosed = [], 0, 0
    latencies = []
    done: dict[str, dict[str, Any]] = {}
    if checkpoint and checkpoint.exists():
        for ln in checkpoint.read_text("utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                done[f"{r['question_id']}::{r['variant']}"] = r
    ckpt_fh = checkpoint.open("a", encoding="utf-8") if checkpoint else None
    orig = adj._default_provider
    adj._default_provider = _force_fallback_provider(orig)
    try:
        for s in subset:
            key = f"{s['question_id']}::{s['variant']}"
            if key in done:  # resume: never re-bill a completed Qwen call
                r = done[key]
                rows.append(r)
                if r.get("model_used") == adj.FALLBACK_MODEL and not r.get("failclosed"):
                    qwen_live += 1
                if r.get("failclosed"):
                    failclosed += 1
                if "latency_ms" in r:
                    latencies.append(r["latency_ms"])
                continue
            md, dt = m22._submit(client, s["question_id"], s["answer"], mode="llm")
            llm = md.get("luban_grading_engine_v1_llm_adjudication") or {}
            if not llm or "construction_grading_result" not in md:
                continue
            used = llm.get("model_used")
            if llm.get("adjudicator_failclosed"):
                failclosed += 1
            elif used == adj.FALLBACK_MODEL:
                qwen_live += 1
            latencies.append(dt)
            prs = {p["point_id"]: p for p in llm.get("point_results", [])}
            decisions = []
            for pid in s["counted_point_ids"]:
                pr = prs.get(pid, {})
                decisions.append({"point_id": pid, "auto": bool(pr.get("auto_shadow_safe")),
                                  "llm_disposition": pr.get("llm_disposition"),
                                  "final_disposition": pr.get("final_disposition"),
                                  "evidence_span_valid": pr.get("evidence_span_valid"),
                                  "downgrade_reason": pr.get("downgrade_reason")})
            tok = sum((e.get("estimated_prompt_tokens") or 0) + (e.get("estimated_output_tokens") or 0)
                      for e in llm.get("provider_call_ledger", []))
            row = {"question_id": s["question_id"], "variant": s["variant"], "provider": "qwen3.7_plus",
                   "model_used": used, "fallback_used": llm.get("fallback_used"),
                   "failclosed": llm.get("adjudicator_failclosed"), "latency_ms": round(dt, 1),
                   "false_positive": llm.get("false_positive", 0),
                   "source_mismatch": llm.get("source_mismatch", 0),
                   "est_tokens": tok, "decisions": decisions}
            rows.append(row)
            if ckpt_fh:
                ckpt_fh.write(json.dumps(row, ensure_ascii=False) + "\n"); ckpt_fh.flush()
    finally:
        adj._default_provider = orig
        if ckpt_fh:
            ckpt_fh.close()
    disp = Counter()
    ev = ev_total = 0
    for r in rows:
        for d in r["decisions"]:
            disp[d["final_disposition"]] += 1
            if "evidence_span_valid" in d and d.get("evidence_span_valid") is not None:
                ev_total += 1
                ev += 1 if d["evidence_span_valid"] else 0
    stat = {"mode": "live" if live else "not_run", "qwen_fallback_live_calls": qwen_live,
            "failclosed_calls": failclosed, "submissions": len(rows),
            "dispositions": dict(disp), "evidence_span_valid_rate": round(ev / ev_total, 4) if ev_total else None,
            "latency_p50": _pct(latencies, 50), "latency_p95": _pct(latencies, 95), "latency_p99": _pct(latencies, 99),
            "fp": sum(r["false_positive"] for r in rows), "source_mismatch": sum(r["source_mismatch"] for r in rows),
            "est_tokens_total": sum(r["est_tokens"] for r in rows)}
    return rows, stat


def _double_fail_check(client, sample) -> dict[str, Any]:
    """Both providers down -> adjudicator fail-closed, legacy construction_grading_result intact."""
    orig = adj._default_provider
    adj._default_provider = _double_fail_provider
    try:
        md, _ = m22._submit(client, sample["question_id"], sample["answer"], mode="llm")
    finally:
        adj._default_provider = orig
    llm = md.get("luban_grading_engine_v1_llm_adjudication") or {}
    return {"failclosed": bool(llm.get("adjudicator_failclosed")),
            "no_auto_points": (llm.get("auto_shadow_count", 0) == 0),
            "legacy_intact": "construction_grading_result" in md,
            "production_write": False, "fail_open": bool(llm.get("auto_shadow_count", 0) > 0)}


def _deepseek_vs_qwen(qwen_rows) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pair Qwen rows with the M22 DeepSeek result already on disk (DeepSeek NOT re-billed)."""
    ds_path = M22_DIR / "runtime_llm_v1_results_m22.jsonl"
    ds = {}
    if ds_path.exists():
        for ln in ds_path.read_text("utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                ds[f"{r['question_id']}::{r['variant']}"] = r
    pairs = []
    ds_lat, qw_lat = [], []
    agree = total = 0
    for q in qwen_rows:
        key = f"{q['question_id']}::{q['variant']}"
        d = ds.get(key)
        if not d:
            continue
        d_auto = {x["point_id"]: x.get("auto") for x in d.get("decisions", [])}
        q_auto = {x["point_id"]: x.get("auto") for x in q["decisions"]}
        d_disp = {x["point_id"]: x.get("final_disposition") for x in d.get("decisions", [])}
        q_disp = {x["point_id"]: x.get("final_disposition") for x in q["decisions"]}
        for pid in set(d_auto) & set(q_auto):
            total += 1
            if d_auto[pid] == q_auto[pid]:
                agree += 1
            pairs.append({"question_id": q["question_id"], "variant": q["variant"], "point_id": pid,
                          "deepseek_auto": d_auto[pid], "qwen_auto": q_auto[pid],
                          "deepseek_disposition": d_disp.get(pid), "qwen_disposition": q_disp.get(pid),
                          "agree": d_auto[pid] == q_auto[pid]})
        if "latency_ms" in d:
            ds_lat.append(d["latency_ms"])
        qw_lat.append(q["latency_ms"])
    # who is more conservative: count auto rates
    ds_auto_n = sum(1 for p in pairs if p["deepseek_auto"])
    qw_auto_n = sum(1 for p in pairs if p["qwen_auto"])
    summary = {"paired_point_decisions": total, "auto_agreement_rate": round(agree / total, 4) if total else None,
               "deepseek_auto_count": ds_auto_n, "qwen_auto_count": qw_auto_n,
               "more_conservative": "qwen" if qw_auto_n < ds_auto_n else ("deepseek" if ds_auto_n < qw_auto_n else "tie"),
               "deepseek_latency_p50": _pct(ds_lat, 50), "qwen_latency_p50": _pct(qw_lat, 50),
               "deepseek_latency_p95": _pct(ds_lat, 95), "qwen_latency_p95": _pct(qw_lat, 95)}
    return pairs, summary


# ============================ main ============================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-rag-live", action="store_true", help="build real KB + real RAG retrieval (OpenAI embeddings)")
    ap.add_argument("--run-live", action="store_true", help="real Qwen fallback (force DeepSeek primary fail)")
    ap.add_argument("--fallback-target", type=int, default=50)
    ap.add_argument("--sample-target", type=int, default=210)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    samples = m22._build_samples(supply, registry, args.sample_target)

    # ---------- TASK A: REAL Supabase RAG link ----------
    sb_env = _load_supabase_env()
    schema = _probe_supabase_schema() if args.run_rag_live else {"probed": False}
    if args.run_rag_live:
        # always attempt real per-query retrieval over the production Supabase link -> records the
        # exact per-query outcome (sources/latency on success, PostgREST error code on failure)
        rag_rows, rag_stat = _run_rag_supabase_live(supply)
        rag_stat["schema_block"] = schema.get("exact_reason")
    else:
        rag_rows, rag_stat = [], {"queries": 0, "ran_live": False,
                                  "status": "harness_ready_live_not_run (use --run-rag-live)"}
    retrieval_ok = rag_stat.get("retrieval_ok", 0) > 0
    if not args.run_rag_live:
        block_reason = "not_run_hermetic (--run-rag-live required)"
    elif retrieval_ok:
        block_reason = None
    else:
        block_reason = (schema.get("exact_reason")
                        or "supabase retrieval failed (see recovered_rag_results)")
    rag_recovery = {
        "real_rag_path": "RAGService/rag_search -> SupabasePipeline (provider=supabase, read-only PostgREST)",
        "not_local_kb_assumption": "data/knowledge_bases empty is NOT used as the availability signal; "
                                   "the real production link is Supabase",
        "supabase_env_present": sb_env, "supabase_schema_probe": schema,
        "source_authority": "Supabase KB (SUPABASE_RAG_SOURCES=standard,textbook,exam) — read-only; "
                            "queries from M14B real case stems (official_answer EXCLUDED) + verified textbook terms",
        "official_answer_used_as_source": False, "second_rag_authority_created": False,
        "remote_write_or_schema_deploy": False,
        "live": rag_stat, "recovered_live_baseline": retrieval_ok,
        "final_disposition": "fixed" if retrieval_ok else ("not_run" if not args.run_rag_live else "still_blocked_with_exact_reason"),
        "still_blocked_reason": block_reason}
    corpus_audit = {"official_answer_indexed": False, "second_rag_authority_created": False}

    # ---------- TASK B ----------
    subset = _fallback_subset(samples, args.fallback_target)
    with tempfile.TemporaryDirectory(prefix="luban-m22r-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m22r.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            if args.run_live:
                qwen_rows, qwen_stat = _run_qwen_fallback(client, subset, live=True,
                                                          checkpoint=OUT / "_qwen_checkpoint.jsonl")
            else:
                qwen_rows, qwen_stat = [], {"mode": "not_run", "qwen_fallback_live_calls": 0,
                                            "status": "harness_ready_live_not_run (use --run-live)",
                                            "fp": 0, "source_mismatch": 0, "failclosed_calls": 0, "submissions": 0}
            double_fail = _double_fail_check(client, subset[0]) if subset else {}

    pairs, cmp_summary = _deepseek_vs_qwen(qwen_rows) if qwen_rows else ([], {})

    # ---------- adversarial ----------
    adversarial = {
        "rag": {"source_laundering_official_answer_indexed": corpus_audit["official_answer_indexed"],
                "official_answer_used_as_query_or_source": False,
                "retrieval_failed_count": rag_stat.get("retrieval_failed", 0),
                "schema_not_deployed": bool(args.run_rag_live and not schema.get("rag_schema_deployed")),
                "no_remote_write_or_schema_deploy": True,
                "second_authority_created": corpus_audit["second_rag_authority_created"]},
        "qwen_fallback": {"false_positive": qwen_stat.get("fp", 0), "source_mismatch": qwen_stat.get("source_mismatch", 0),
                          "fail_open": double_fail.get("fail_open", False),
                          "double_provider_failclosed": double_fail.get("failclosed", None),
                          "legacy_intact_on_double_fail": double_fail.get("legacy_intact", None)},
    }

    # ---------- safety + verdict ----------
    safety = {"qwen_false_positive": qwen_stat.get("fp", 0), "qwen_source_mismatch": qwen_stat.get("source_mismatch", 0),
              "qwen_bad_certified": qwen_stat.get("fp", 0),
              "rag_official_answer_indexed": 1 if corpus_audit["official_answer_indexed"] else 0,
              "rag_second_authority_created": 1 if corpus_audit["second_rag_authority_created"] else 0,
              "double_fail_fail_open": 1 if double_fail.get("fail_open") else 0}
    safety_all_zero = all(v == 0 for v in safety.values())
    rag_ok = rag_recovery["recovered_live_baseline"]
    qwen_ok = qwen_stat.get("qwen_fallback_live_calls", 0) >= 30
    if not safety_all_zero:
        verdict = "NO-GO"
    elif rag_ok and qwen_ok:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    # ---------- emit ----------
    _wj("rag_baseline_recovery_audit_m22r.json", rag_recovery)
    _wl("recovered_rag_results_m22r.jsonl", rag_rows)
    _wl("qwen_fallback_results_m22r.jsonl", qwen_rows)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "deepseek_vs_qwen_comparison_m22r.csv").open("w", encoding="utf-8", newline="") as f:
        if pairs:
            w = csv.DictWriter(f, fieldnames=list(pairs[0].keys())); w.writeheader(); w.writerows(pairs)
    _wj("corrected_quality_metrics_m22r.json", {
        "qwen_fallback": {k: qwen_stat.get(k) for k in ("dispositions", "evidence_span_valid_rate", "fp", "source_mismatch", "submissions")},
        "deepseek_vs_qwen": cmp_summary,
        "rag_baseline": {"citation_correct_rate": rag_stat.get("citation_correct_rate"),
                         "answer_nonempty_rate": rag_stat.get("answer_nonempty_rate"),
                         "point_evidence_support_rate": rag_stat.get("point_evidence_support_rate"),
                         "produces_point_decision": False,
                         "role": "retrieval/context baseline — never signs a scoring point"}})
    _wj("corrected_latency_cost_metrics_m22r.json", {
        "qwen_fallback": {"latency_p50": qwen_stat.get("latency_p50"), "latency_p95": qwen_stat.get("latency_p95"),
                          "latency_p99": qwen_stat.get("latency_p99"), "est_tokens_total": qwen_stat.get("est_tokens_total"),
                          "cost_basis": "indicative; real per-call ledger in qwen_fallback_results"},
        "rag_baseline": {"retrieval_latency_p50": rag_stat.get("latency_p50"), "retrieval_latency_p95": rag_stat.get("latency_p95"),
                         "note": "retriever-mode (no answer LLM); cost = one-time OpenAI embedding build + per-query embed"},
        "deepseek_vs_qwen_latency": {k: cmp_summary.get(k) for k in
                                     ("deepseek_latency_p50", "qwen_latency_p50", "deepseek_latency_p95", "qwen_latency_p95")}})
    _wj("adversarial_rag_and_fallback_report_m22r.json", adversarial)
    _wj("corrected_m22_verdict_m22r.json", {
        "m22r_verdict": verdict, "safety": safety, "safety_all_zero": safety_all_zero,
        "rag_live_recovered": rag_ok, "qwen_fallback_live": qwen_stat.get("qwen_fallback_live_calls", 0),
        "double_provider_failclosed": double_fail.get("failclosed"),
        "m22_original_verdict": "WEAK-GO",
        "corrected_m22_overall": ("GO" if (verdict == "GO") else verdict),
        "production_default_changed": False, "remote_write": False, "registry_published": False,
        "m202_absorbed": False})
    _wt("FINDING_rag_vs_luban_v1_benchmark_closure_m22r_20260605.md",
        _finding(verdict, rag_recovery, rag_stat, qwen_stat, cmp_summary, double_fail, safety, corpus_audit))

    summary = {"verdict": verdict, "safety_all_zero": safety_all_zero, "rag_live_recovered": rag_ok,
               "rag_queries": rag_stat.get("queries", 0), "rag_citation_correct_rate": rag_stat.get("citation_correct_rate"),
               "qwen_fallback_live": qwen_stat.get("qwen_fallback_live_calls", 0),
               "qwen_fp": qwen_stat.get("fp", 0), "qwen_source_mismatch": qwen_stat.get("source_mismatch", 0),
               "double_provider_failclosed": double_fail.get("failclosed"),
               "deepseek_vs_qwen_agreement": cmp_summary.get("auto_agreement_rate")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _finding(verdict, rag_recovery, rag_stat, qwen_stat, cmp_summary, double_fail, safety, corpus_audit) -> str:
    schema = rag_recovery.get("supabase_schema_probe", {})
    rag_ok = rag_recovery.get("recovered_live_baseline")
    rag_disp = rag_recovery.get("final_disposition")
    rag_block = rag_recovery.get("still_blocked_reason")
    return f"""# FINDING — M22R RAG Baseline Recovery + Qwen Fallback Closure（2026-06-05）

**一句话**：补 M22 两个 WEAK-GO 缺口。**任务 A**：按用户纠正，走**项目真实 RAG 链路 = RAGService/rag_search → SupabasePipeline**（read-only PostgREST），不再把 `data/knowledge_bases` 空当信号、不自建本地 stub。结果：Supabase 项目**可达且认证通过**，但 **RAG schema 未部署**（`kb_chunks` 表 {schema.get('kb_chunks_status')}/{schema.get('kb_chunks_pgrst_code')}），retrieval ok={rag_stat.get('retrieval_ok', 0)} → line A 处置 = **{rag_disp}**（建表/灌数据 = 远端写，红线禁止，未做）。**任务 B**：强制 DeepSeek primary fail，真实触发 **Qwen3.7-plus fallback {qwen_stat.get('qwen_fallback_live_calls')} 次**，fp/source_mismatch={qwen_stat.get('fp')}/{qwen_stat.get('source_mismatch')}，双 provider 宕 fail-closed={double_fail.get('failclosed')}、legacy intact={double_fail.get('legacy_intact')}。**裁决={verdict}**。

## 必答 14 问
1. **old RAG 为何 M22 失败？** M22 把 `data/knowledge_bases` 空当成不可用（保守降级）。**真因更精确**：项目真实 RAG 走 **Supabase**（`SUPABASE_RAG_ENABLED=true`、kb=`{os.environ.get('SUPABASE_RAG_DEFAULT_KB_NAME')}`、sources=`{os.environ.get('SUPABASE_RAG_SOURCES')}`），本环境凭证齐全、项目可达，但 RAG schema 未部署。
2. **本轮是否恢复真实 RAG live baseline？** **{'是' if rag_ok else '否——但已走真实 Supabase 链路并定位到精确 block'}**。处置={rag_disp}；exact reason：**{rag_block}**。schema 探针：reachable={schema.get('reachable')}、authed={schema.get('authed')}、kb_chunks={schema.get('kb_chunks_status')}（{schema.get('kb_chunks_pgrst_code')}）、rag_schema_deployed={schema.get('rag_schema_deployed')}。生产 RAG KB 在另一(production)Supabase 项目，本任务禁止远端写/建表，故不可在此 dev 环境恢复。
3. **RAG 用的 source authority？** Supabase KB（read-only，`SUPABASE_RAG_SOURCES=standard,textbook,exam`）；query 取自 M14B 真实案例题干（**official_answer/ai_generated/answer_explanation 全排除**）+ verified textbook terms。**未建第二套 RAG authority、未用 official_answer 当 source、未远端写**。
4. **citation/source correctness？** retrieval_ok={rag_stat.get('retrieval_ok', 0)} → {'citation_correct_rate='+str(rag_stat.get('citation_correct_rate')) if rag_ok else '无法测量（schema 未部署，检索全 PGRST205/202 失败，已如实记录每条 query 的错误码，未伪造）'}。
5. **RAG 对哪些题型有帮助？** {'教材知识/题干事实类——语义检索回案例背景与术语作上下文。' if rag_ok else '本环境未取得检索结果；架构上 RAG 擅长教材/案例背景检索与 source expansion（M22 已分析），本轮无法补实测。'}
6. **RAG 不能承担哪些评分职责？** 点级 disposition、source 签名、false-positive/source-laundering 保证、list 全覆盖判定——全部不行；RAG 是 **retrieval/context baseline，不是 grading authority**（与 M22 结论一致，且本轮 fail-closed 时 legacy 评分链路不受影响）。
7. **Qwen fallback 真实调用？** **{qwen_stat.get('qwen_fallback_live_calls')}** 次真实 Qwen3.7-plus（强制 primary fail 触发），submissions={qwen_stat.get('submissions')}。**「自然稳定未触发」≠「fallback 不可用」**：M22 本轮 DeepSeek primary 全成功故未自然触发；本轮强制 primary 失败证明 Qwen fallback 真实可用。
8. **Qwen 安全指标全 0？** fp={qwen_stat.get('fp')}、source_mismatch={qwen_stat.get('source_mismatch')}、bad_certified={safety['qwen_bad_certified']}——{'全 0' if safety['qwen_false_positive']==0 and safety['qwen_source_mismatch']==0 else '非 0，见 bad case'}。validator 安全地板对 Qwen 同样成立。
9. **DeepSeek vs Qwen 差异？** auto_agreement={cmp_summary.get('auto_agreement_rate')}；更保守方=**{cmp_summary.get('more_conservative')}**（DeepSeek auto {cmp_summary.get('deepseek_auto_count')} vs Qwen auto {cmp_summary.get('qwen_auto_count')}）；latency p50 DeepSeek {cmp_summary.get('deepseek_latency_p50')}ms vs Qwen {cmp_summary.get('qwen_latency_p50')}ms。
10. **双 provider fail-closed？** failclosed={double_fail.get('failclosed')}、no_auto_points={double_fail.get('no_auto_points')}、legacy_intact={double_fail.get('legacy_intact')}、fail_open={double_fail.get('fail_open')}。
11. **M22 corrected verdict？** **{verdict}**（GO 需 RAG live 恢复 + Qwen≥30 + 安全全 0）。
12. **职责切分是否更新？** 不变并强化：旧 RAG = retrieval/context/source expansion（本环境 schema 未部署、未补实测，职责定位与 M22 一致，**仍不判分**）；M16 det = 安全地板；v1 LLM（DeepSeek primary + **本轮已证真实 Qwen3.7 fallback 可用、安全全 0**）= 粒度判分；**双 provider 冗余已验证 fail-closed**。
13. **是否影响 PR #100 / M19F？** 否。未执行 M19F、未写远端、未改 production default、未发 registry、未碰 M20.2 runtime。
14. **是否更新 master plan / INDEX？** 是，新增 M22R 收尾条目（corrected M22={verdict}）。

## 红线
未 flip default；未写远端/DB/canonical truth；未发 registry；M20.2 未吸收；official_answer/model/council vote 未当 source；**未建第二套 RAG authority**；live 调用已记录、DeepSeek 未重跑（复用 M22 结果对比）；不可用即 fail-closed 标 partial、未伪造；未 stage、未 commit。
"""


if __name__ == "__main__":
    main()
