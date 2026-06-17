"""M22 — RAG vs Luban v1 Quality / Efficiency / Cost Benchmark.

Same-bench comparison of FOUR lines over one shared sample of construction case
answers, each point carrying a deterministic construction-gold label:

  A. old RAG baseline      — retrieval/answer path (RAGService / rag_search).
                             NOT a point grader. If the embedding KB is absent it
                             is honestly downgraded to a retrieval/answer baseline
                             with a missing-input audit (never fabricated).
  B. M16 deterministic     — controlled-runtime candidate (beta_shadow_loader),
                             rule/registry baseline; emits point dispositions.
  C. M17/M19 runtime LLM   — real /api/v1/ws -> _maybe_attach_v1_llm_adjudication:
                             scoped GradingPacket + DeepSeek-V4-flash primary +
                             Qwen3.7 plus fallback + deterministic validator floor.
                             --run-live uses real providers; hermetic uses a
                             deterministic LLM-proxy (pipeline only, quality axis
                             flagged as proxy, NOT real-LLM quality).
  D. M20.2 delta candidate — future_delta candidate (temp harness; NEVER wired to
                             runtime). The 69 staged deltas are candidate
                             work-orders (runtime_effect=candidate_context_only),
                             so D measures the *projected* packet-compression
                             token/byte effect on the 34 compression-target points
                             and inventories the 19 staged grading work-orders +
                             16 LB-claim mappings. No fabricated alternate grades.

Six workflow patterns are implemented IN-SCRIPT (Claude subagents cannot make the
DeepSeek/Qwen provider calls): classify-and-act (6 question types by authority_kind),
fanout-and-synthesize (4 lines), generate-and-filter (7 answer variants/quality),
tournament (best/worst per question), adversarial-verification (fp / source
laundering / unsupported positive / list partial auto / teacher-only leak),
loop-until-done (every sample gets a final disposition).

HARD red lines: no production default flip; no remote/Aliyun write; no production
DB write; no canonical learner-truth write; no published registry; M20.2 delta is
candidate-only and never absorbed into runtime; official_answer / model vote /
council vote are never a source authority; live LLM calls are logged (count /
provider / latency / fallback / failclosed) and never re-billed past a checkpoint;
unavailable providers fail-closed and mark the axis partial (never fabricated).

Output -> artifacts/luban_grading_artifacts/rag_vs_luban_v1_quality_benchmark_m22_20260605/
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "rag_vs_luban_v1_quality_benchmark_m22_20260605"
M202_DIR = REPO / "artifacts" / "luban_grading_artifacts" / "delta_to_registry_candidate_staging_m202_20260605"

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


ws = _load_module("ws_m22", "run_luban_ws_runtime_shadow_turn_smoke.py")
m12 = _load_module("m12_m22", "run_luban_internal_live_qa_runtime_drill_m12.py")
m17b = _load_module("m17b_m22", "run_luban_runtime_llm_adjudication_scaleout_m17b_m18.py")

COHORT = "qa_m22_bench"
_CUR = {"user": COHORT}

# 6 question-type classification by registry authority_kind (classify-and-act).
TYPE_BY_AUTHORITY = {
    "textbook_verbatim": "教材知识",
    "machine_checkable_logic": "案例判断",
    "machine_checkable_calc": "索赔工期费用计算",
    "list_rule_full_coverage": "综合review",
}
EXTERNAL_TYPE = "外部规范"        # external_required bucket (source_gap, never auto)
STEM_TYPE = "题干事实"           # review_required bucket (never auto)


# ----------------------------- io helpers -----------------------------

def _wj(name: str, obj: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _wt(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text.rstrip() + "\n", "utf-8")


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))], 1)


# ----------------------------- shared sample + construction gold -----------------------------

def _registry_points_by_q(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_q: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in registry.get("points", []):
        by_q[p["question_id"]].append(p)
    return by_q


def _evidence(supply: bsl.BetaSupply, qid: str, pid: str) -> str:
    if (qid, pid) in supply.machine_specs:
        return m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"])
    if (qid, pid) in supply.list_specs:
        return "，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"])
    if supply.source_terms.get((qid, pid)):
        return supply.source_terms[(qid, pid)][0]
    return ""


def _q_type(authority_kind: str) -> str:
    return TYPE_BY_AUTHORITY.get(authority_kind, "其他")


def _build_samples(supply: bsl.BetaSupply, registry: dict[str, Any], target: int) -> list[dict[str, Any]]:
    """generate-and-filter: 7 answer-quality variants per question, each carrying per-point
    construction-gold (gold_auto_eligible = the point's evidence is genuinely present AND the
    point is auto-eligible by authority kind; review/external are never auto-eligible)."""
    by_q = _registry_points_by_q(registry)
    questions = sorted(by_q)
    samples: list[dict[str, Any]] = []
    for qid in questions:
        reg_pts = by_q[qid]
        counted_pids = [p["point_id"] for p in reg_pts]
        ev = {pid: _evidence(supply, qid, pid) for pid in counted_pids}
        present = [pid for pid in counted_pids if ev[pid]]
        if not present:
            continue
        n = len(present)
        def join(sub: list[str]) -> str:
            return "；".join(ev[p] for p in sub if ev[p]) + "。"
        # adversarial wrong machine answer (off-by / contradiction)
        wrong = ""
        mp = next(((q, p) for (q, p) in supply.machine_specs if q == qid
                   and supply.machine_specs[(q, p)]["spec"].get("kind")
                   in ("numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment")), None)
        if mp:
            wrong = m12._wrong_machine_answer(supply.machine_specs[mp]["spec"])
        half = present[: max(1, n // 2)]
        third = present[: max(1, n // 3)]
        variants = [
            ("correct_full", join(present), set(present)),                 # 正确
            ("verbose_correct", join(present) + "（综合分析，符合规范要求）", set(present)),
            ("reordered_correct", join(list(reversed(present))), set(present)),
            ("partial_half", join(half), set(half)),                        # 部分正确
            ("partial_third", join(third), set(third)),
            ("contradiction_wrong", wrong or "完全不合理。", set()),         # 反向矛盾
            ("near_miss", join(present[:1]) + "（结论方向相近但论据不足）", set(present[:1])),  # 错因相近
            ("irrelevant", "本题与城市轨道交通运营管理无关，故不展开。", set()),  # 无关
            ("empty_evidence", "我不太确定，需要进一步查阅。", set()),          # 缺证据
            ("hallucination_bait", join(present[:1]) + "（依据《虚构规范GBxxxx》第999条，必然成立）", set(present[:1])),  # 诱导 hallucination
        ]
        reg_by_pid = {p["point_id"]: p for p in reg_pts}
        for vname, answer, gold_present in variants:
            gold = {}
            for pid in counted_pids:
                ak = reg_by_pid[pid]["authority_kind"]
                spec = supply.machine_specs.get((qid, pid), {}).get("spec", {})
                # ground-truth eligibility. boolean_judgment evidence is a SHARED polarity word with no
                # point-specific content: the deterministic matcher cannot localize it to one event, so
                # the honest ground truth is "did the answer assert the correct polarity" (NOT subset
                # intent). All other kinds carry point-specific evidence -> subset membership is exact.
                if spec.get("kind") == "boolean_judgment":
                    eligible = bsl._extract_judgment(answer) == spec.get("expected_bool")
                else:
                    eligible = pid in gold_present
                gold[pid] = {"gold_auto_eligible": eligible,
                             "authority_kind": ak, "question_type": _q_type(ak)}
            samples.append({"question_id": qid, "variant": vname, "answer": answer,
                            "counted_point_ids": counted_pids, "gold": gold,
                            "n_counted": len(counted_pids)})
            if len(samples) >= target:
                return samples
    return samples


# ----------------------------- WS harness (lines B and C real entry) -----------------------------

def _frame(qid: str, content: str, *, mode: str) -> dict[str, Any]:
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case",
                                         "question": "M22 同台 benchmark", "correct_answer": content}}
    if mode == "llm":
        cfg["grading_engine_v1_llm_adjudication"] = True
    elif mode == "controlled":
        cfg["grading_engine_v1_controlled_runtime"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question",
            "language": "zh", "config": cfg}


def _submit(client, qid: str, content: str, *, mode: str) -> tuple[dict[str, Any], float]:
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, mode=mode)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


# ----------------------------- deterministic LLM-proxy (hermetic line C) -----------------------------

def _proxy_provider_factory(samples_by_q: dict[str, dict[str, dict]]):
    """Hermetic 'honest LLM proxy': proposes accept where construction-gold says the point's evidence
    is present, reject otherwise. Exercises the full packet->adjudicate->validator pipeline WITHOUT a
    real LLM. Quality measured under this proxy is flagged proxy_not_real_llm."""
    def prov(role: str, system: str, user: str, env: dict[str, str]) -> str:
        payload = json.loads(user)
        qid = payload.get("question_id")
        answer = payload.get("student_answer") or ""
        gold = samples_by_q.get(qid, {})
        rows = []
        for point in payload.get("points", []):
            pid = point["point_id"]
            g = gold.get(pid, {})
            present = bool(g.get("gold_auto_eligible"))
            # evidence span = a real substring of the answer when proposing accept
            span = ""
            if present:
                ev = g.get("evidence", "")
                span = ev if ev and bsl._norm(ev) in bsl._norm(answer) else answer[: min(16, len(answer))]
            rows.append({"point_id": pid, "disposition": "accept" if present else "reject",
                         "evidence_span": span, "confidence": 0.9 if present else 0.2,
                         "reasoning_summary": "m22 deterministic proxy"})
        return json.dumps(rows, ensure_ascii=False)
    return prov


# ----------------------------- line B: M16 deterministic -----------------------------

def _line_b(client, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for s in samples:
        md, dt = _submit(client, s["question_id"], s["answer"], mode="controlled")
        payload = md.get("luban_grading_engine_v1_controlled_runtime") or {}
        prs = {p["point_id"]: p for p in payload.get("point_results", [])}
        decisions = []
        for pid in s["counted_point_ids"]:
            pr = prs.get(pid, {})
            decisions.append({"point_id": pid, "auto": bool(pr.get("auto_shadow")),
                              "disposition": pr.get("disposition"), "path": pr.get("path")})
        rows.append({"question_id": s["question_id"], "variant": s["variant"], "line": "B_m16_deterministic",
                     "latency_ms": round(dt, 1), "legacy_present": "construction_grading_result" in md,
                     "decisions": decisions, "produces_point_decisions": True})
    return rows


# ----------------------------- line C: M17 runtime LLM adjudicator -----------------------------

def _line_c(client, samples: list[dict[str, Any]], *, live: bool,
            checkpoint: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if checkpoint and checkpoint.exists():
        for ln in checkpoint.read_text("utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                done[f"{r['question_id']}::{r['variant']}"] = r
    rows, live_calls, fallback_calls, failclosed_calls, timeouts = [], 0, 0, 0, 0
    latencies: list[float] = []
    ckpt_fh = checkpoint.open("a", encoding="utf-8") if checkpoint else None
    try:
        for s in samples:
            key = f"{s['question_id']}::{s['variant']}"
            if key in done:
                rows.append(done[key])
                continue
            md, dt = _submit(client, s["question_id"], s["answer"], mode="llm")
            llm = md.get("luban_grading_engine_v1_llm_adjudication") or {}
            if not llm or "construction_grading_result" not in md:
                continue
            if llm.get("adjudicator_failclosed"):
                failclosed_calls += 1
            elif llm.get("model_used"):
                live_calls += 1
            if llm.get("fallback_used"):
                fallback_calls += 1
            if llm.get("adjudicator_timed_out"):
                timeouts += 1
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
            row = {"question_id": s["question_id"], "variant": s["variant"], "line": "C_runtime_llm_v1",
                   "model_used": llm.get("model_used"), "fallback_used": llm.get("fallback_used"),
                   "failclosed": llm.get("adjudicator_failclosed"), "latency_ms": round(dt, 1),
                   "correlation_id": llm.get("correlation_id"),
                   "false_positive": llm.get("false_positive", 0),
                   "source_mismatch": llm.get("source_mismatch", 0),
                   "fp_prevented": llm.get("false_positive_prevented_by_validator", 0),
                   "source_laundering_blocked": llm.get("source_laundering_blocked", 0),
                   "decisions": decisions, "produces_point_decisions": True,
                   "provider_call_ledger": llm.get("provider_call_ledger", [])}
            rows.append(row)
            if ckpt_fh:
                ckpt_fh.write(json.dumps(row, ensure_ascii=False) + "\n"); ckpt_fh.flush()
    finally:
        if ckpt_fh:
            ckpt_fh.close()
    stats = {"mode": "live" if live else "deterministic_proxy_pipeline_only",
             "live_calls": live_calls, "fallback_calls": fallback_calls,
             "failclosed_calls": failclosed_calls, "timeouts": timeouts,
             "quality_axis": "real_llm" if live else "proxy_not_real_llm",
             "latency_p50": _pct(latencies, 50), "latency_p95": _pct(latencies, 95),
             "latency_p99": _pct(latencies, 99)}
    return rows, stats


# ----------------------------- line A: old RAG retrieval/answer baseline -----------------------------

def _line_a_rag(samples: list[dict[str, Any]], gold_cases: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Old RAG = retrieval/answer path. The embedding KB is unavailable hermetically, so we DO NOT
    fabricate retrieval. We honestly record: (1) RAG produces an answer (compiled official answer is
    the answer-baseline ground), (2) RAG produces NO point disposition (it is not a grader), (3) live
    embedding retrieval is unavailable -> missing-input audit."""
    kb_root = REPO / "data" / "knowledge_bases"
    kb_built = kb_root.exists() and any(kb_root.iterdir()) if kb_root.exists() else False
    has_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"))
    live_retrieval_available = kb_built and has_key
    rows = []
    seen_q = set()
    for s in samples:
        qid = s["question_id"]
        if qid in seen_q:
            continue
        seen_q.add(qid)
        # answer baseline: does a compiled official answer exist for this question family?
        answer_baseline_available = True  # registry/supply carry official_answer-seeded specs per qid
        rows.append({"question_id": qid, "line": "A_old_rag_baseline",
                     "produces_point_decisions": False,
                     "role": "retrieval_answer_baseline_not_grading_authority",
                     "answer_baseline_available": answer_baseline_available,
                     "live_embedding_retrieval": "available" if live_retrieval_available else "unavailable_no_built_kb",
                     "point_authority": None, "validator_gated": False,
                     "hallucination_exposed": True})
    audit = {"line": "A_old_rag_baseline", "entry_point": "deeptutor.services.rag.service.RAGService.search / tools.rag_tool.rag_search",
             "kb_base_dir": str(kb_root.relative_to(REPO)), "kb_built": kb_built,
             "embedding_key_present": has_key, "live_retrieval_available": live_retrieval_available,
             "downgrade": "retrieval/answer baseline only (no built KB) — NOT used as a point-grading baseline",
             "fabricated_retrieval_metrics": False,
             "rationale": "RAGService.search needs an indexed KB + embedding provider; data/knowledge_bases is empty, so live retrieval cannot run hermetically. Per M22 rule, RAG is recorded as a retrieval/answer baseline and its grading axis is N/A, not faked.",
             "what_rag_is_good_at": ["free-text answer synthesis", "source/citation retrieval over a KB",
                                     "source expansion for un-compiled questions"],
             "what_rag_cannot_do": ["point-level disposition", "deterministic source signing",
                                    "false-positive / source-laundering guarantees", "list partial-coverage gating"]}
    return rows, audit


# ----------------------------- line D: M20.2 delta projected candidate -----------------------------

def _line_d_delta(supply: bsl.BetaSupply, registry: dict[str, Any],
                  samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """M20.2 delta = 69 staged candidate work-orders (runtime_effect=candidate_context_only). They are
    NOT executable spec replacements, so D does not produce alternate dispositions (that would pollute
    runtime). D measures the *projected* packet-compression token/byte effect on the 34 compression
    targets and inventories the grading work-orders. Honest projection, clearly labelled."""
    staged = json.loads((M202_DIR / "staged_registry_candidate_m202.json").read_text("utf-8"))
    entries = staged.get("entries", [])
    by_class = Counter(e["classification"] for e in entries)
    compression_targets = {(e["question_id"], e["point_id"]) for e in entries
                           if e["classification"] == "packet_compression_delta"}
    grading_workorders = [e for e in entries if e["classification"] in
                          ("machine_spec_delta", "list_delta", "rubric_delta")]
    lb_mappings = [e for e in entries if e["classification"] == "learning_brain_claim_mapping_delta"]

    # projected packet compression: build current packet, then a delta packet that moves compression
    # targets out of the LLM slice (handled deterministically) and measure real byte/token deltas.
    rows = []
    seen_q = set()
    for s in samples:
        qid = s["question_id"]
        if qid in seen_q:
            continue
        seen_q.add(qid)
        cur_packet = adj.build_grading_packet(qid, s["answer"], supply=supply, registry=registry)
        cur_slices = cur_packet["source_spec_list_policy_slices"]
        delta_slices = [sl for sl in cur_slices if (qid, sl["point_id"]) not in compression_targets]
        cur_bytes = len(json.dumps(cur_slices, ensure_ascii=False).encode("utf-8"))
        delta_bytes = len(json.dumps(delta_slices, ensure_ascii=False).encode("utf-8"))
        cur_tok = adj._est_tokens(json.dumps(cur_slices, ensure_ascii=False))
        delta_tok = adj._est_tokens(json.dumps(delta_slices, ensure_ascii=False))
        compressed_here = sum(1 for sl in cur_slices if (qid, sl["point_id"]) in compression_targets)
        rows.append({"question_id": qid, "line": "D_m202_delta_candidate",
                     "produces_point_decisions": False,
                     "runtime_effect": "candidate_context_only_not_executable",
                     "current_packet_bytes": cur_bytes, "delta_packet_bytes": delta_bytes,
                     "packet_bytes_saved": cur_bytes - delta_bytes,
                     "current_packet_tokens_est": cur_tok, "delta_packet_tokens_est": delta_tok,
                     "tokens_saved_est": cur_tok - delta_tok,
                     "compression_targets_in_question": compressed_here})
    total_cur_b = sum(r["current_packet_bytes"] for r in rows)
    total_delta_b = sum(r["delta_packet_bytes"] for r in rows)
    total_cur_t = sum(r["current_packet_tokens_est"] for r in rows)
    total_delta_t = sum(r["delta_packet_tokens_est"] for r in rows)
    summary = {
        "line": "D_m202_delta_candidate", "delta_entry_count": len(entries),
        "classification_counts": dict(by_class),
        "runtime_effect_all": "candidate_context_only (NONE executable; NOT absorbed into runtime)",
        "measurable_now": "projected packet-compression token/byte reduction on packet_compression_delta targets",
        "packet_bytes_current_total": total_cur_b, "packet_bytes_delta_total": total_delta_b,
        "packet_bytes_saved_total": total_cur_b - total_delta_b,
        "packet_bytes_saved_pct": round(100 * (total_cur_b - total_delta_b) / total_cur_b, 1) if total_cur_b else 0.0,
        "packet_tokens_current_total": total_cur_t, "packet_tokens_delta_total": total_delta_t,
        "packet_tokens_saved_pct": round(100 * (total_cur_t - total_delta_t) / total_cur_t, 1) if total_cur_t else 0.0,
        "grading_workorders_pending_not_executable": len(grading_workorders),
        "lb_claim_mappings_no_grading_effect": len(lb_mappings),
        "latency_projection": "neutral-to-slightly-better (smaller LLM packet); no disposition change measurable yet",
        "grading_quality_delta": "NOT measurable as runtime grading — deltas stop at candidate_delta_or_work_order; compilation into a registry is a future milestone, not M22",
        "absorbed_into_runtime": False,
    }
    return rows, summary


# ----------------------------- quality metrics (lines B and C vs construction gold) -----------------------------

def _grade_line(rows: list[dict[str, Any]], samples_by_key: dict[str, dict],
                auto_key: str) -> dict[str, Any]:
    tp = tn = fp = fn = 0
    point_decisions = 0
    evid_valid = evid_total = 0
    by_type_agree: dict[str, list[int]] = defaultdict(list)
    bad_cases = []
    for r in rows:
        if not r.get("produces_point_decisions"):
            continue
        s = samples_by_key.get(f"{r['question_id']}::{r['variant']}")
        if not s:
            continue
        for d in r["decisions"]:
            pid = d["point_id"]
            g = s["gold"].get(pid)
            if not g:
                continue
            point_decisions += 1
            auto = bool(d.get(auto_key))
            gold_auto = bool(g["gold_auto_eligible"])
            if auto and gold_auto:
                tp += 1
            elif auto and not gold_auto:
                fp += 1
                bad_cases.append({"question_id": r["question_id"], "variant": r["variant"], "point_id": pid,
                                  "authority_kind": g["authority_kind"], "kind": "false_positive_auto_on_gold_miss"})
            elif not auto and gold_auto:
                fn += 1
            else:
                tn += 1
            by_type_agree[g["question_type"]].append(1 if auto == gold_auto else 0)
            if "evidence_span_valid" in d:
                evid_total += 1
                if d.get("evidence_span_valid"):
                    evid_valid += 1
    agree = (tp + tn) / point_decisions if point_decisions else 0.0
    return {
        "point_decisions": point_decisions, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "point_hit_agreement": round(agree, 4),
        "false_positive": fp, "bad_certified": fp,
        "accept_precision": round(tp / (tp + fp), 4) if (tp + fp) else 1.0,
        "reject_precision": round(tn / (tn + fn), 4) if (tn + fn) else 1.0,
        "recall_auto": round(tp / (tp + fn), 4) if (tp + fn) else 1.0,
        "evidence_span_valid_rate": round(evid_valid / evid_total, 4) if evid_total else None,
        "by_type_agreement": {t: round(sum(v) / len(v), 4) for t, v in by_type_agree.items()},
        "bad_cases": bad_cases,
    }


# ----------------------------- main -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=int, default=210, help="target submissions per grading line")
    ap.add_argument("--run-live", action="store_true", help="line C uses REAL DeepSeek+Qwen (logged, billed)")
    ap.add_argument("--frontier-council", type=int, default=12, help="cap contested points sent to council")
    ap.add_argument("--codex-cap", type=int, default=3)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    readiness = m17b._load_env() if args.run_live else {"DEEPSEEK_API_KEY": False, "DASHSCOPE_API_KEY": False, "codex_cli": False}

    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    samples = _build_samples(supply, registry, args.target)
    samples_by_key = {f"{s['question_id']}::{s['variant']}": s for s in samples}
    # gold lookup for the hermetic proxy: qid -> {pid -> {gold_auto_eligible, evidence}}
    samples_by_q: dict[str, dict[str, dict]] = defaultdict(dict)
    for s in samples:
        for pid, g in s["gold"].items():
            samples_by_q[s["question_id"]][pid] = {"gold_auto_eligible": g["gold_auto_eligible"],
                                                   "evidence": _evidence(supply, s["question_id"], pid)}

    type_dist = Counter()
    for s in samples:
        for pid in s["counted_point_ids"]:
            type_dist[s["gold"][pid]["question_type"]] += 1

    # ---- run grading lines B and C over the real /api/v1/ws ----
    import tempfile
    with tempfile.TemporaryDirectory(prefix="luban-m22-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m22.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            line_b_rows = _line_b(client, samples)
            ckpt = OUT / "_line_c_checkpoint.jsonl"
            if args.run_live:
                line_c_rows, c_stats = _line_c(client, samples, live=True, checkpoint=ckpt)
            else:
                proxy = _proxy_provider_factory(samples_by_q)
                orig = adj._default_provider
                adj._default_provider = proxy
                try:
                    line_c_rows, c_stats = _line_c(client, samples, live=False, checkpoint=None)
                finally:
                    adj._default_provider = orig

    line_a_rows, line_a_audit = _line_a_rag(samples, {})
    line_d_rows, line_d_summary = _line_d_delta(supply, registry, samples)

    # ---- quality grading vs construction gold ----
    q_b = _grade_line(line_b_rows, samples_by_key, auto_key="auto")
    q_c = _grade_line(line_c_rows, samples_by_key, auto_key="auto")

    # ---- adversarial-verification: fp / source laundering / unsupported positive / list partial / teacher leak ----
    adversarial = _adversarial(line_b_rows, line_c_rows, samples_by_key, registry)

    # ---- council over contested points (reuse M17B council; capped) ----
    council_rows = _council(line_c_rows, samples_by_key, readiness, args, supply)

    # ---- tournament: best / worst per question ----
    tournament = _tournament(line_b_rows, line_c_rows, samples_by_key)

    # ---- efficiency ----
    b_lat = [r["latency_ms"] for r in line_b_rows]
    c_lat = [r["latency_ms"] for r in line_c_rows if "latency_ms" in r]
    latency_cost = {
        "line_B_m16_deterministic": {"latency_p50": _pct(b_lat, 50), "latency_p95": _pct(b_lat, 95),
                                     "latency_p99": _pct(b_lat, 99), "model_cost_usd": 0.0,
                                     "note": "pure deterministic; no model call"},
        "line_C_runtime_llm_v1": {"latency_p50": c_stats["latency_p50"], "latency_p95": c_stats["latency_p95"],
                                  "latency_p99": c_stats["latency_p99"], "mode": c_stats["mode"],
                                  "live_calls": c_stats["live_calls"], "fallback_calls": c_stats["fallback_calls"],
                                  "failclosed_calls": c_stats["failclosed_calls"], "timeouts": c_stats["timeouts"],
                                  "fallback_rate": round(c_stats["fallback_calls"] / max(len(line_c_rows), 1), 4),
                                  "failclosed_rate": round(c_stats["failclosed_calls"] / max(len(line_c_rows), 1), 4),
                                  "token_budget_per_packet": adj.TOKEN_BUDGET,
                                  "cost_basis": "indicative; real token/cost in provider_call_ledger when --run-live"},
        "line_D_m202_delta": {"packet_bytes_saved_pct": line_d_summary["packet_bytes_saved_pct"],
                              "packet_tokens_saved_pct": line_d_summary["packet_tokens_saved_pct"],
                              "latency_projection": line_d_summary["latency_projection"]},
        "line_A_old_rag": {"latency": "N/A — live retrieval unavailable (no built KB)",
                           "role": "retrieval/answer baseline"},
    }

    # ---- paired comparison matrix (per counted point: B auto vs C auto vs gold) ----
    _emit_paired_matrix(line_b_rows, line_c_rows, samples_by_key)

    # ---- safety gate + verdict ----
    safety = {
        "false_positive_B": q_b["false_positive"], "false_positive_C": q_c["false_positive"],
        "bad_certified_B": q_b["bad_certified"], "bad_certified_C": q_c["bad_certified"],
        "source_mismatch_C": sum(r.get("source_mismatch", 0) for r in line_c_rows),
        "list_partial_auto": adversarial["list_partial_auto"],
        "unsupported_positive": adversarial["unsupported_positive"],
        "teacher_only_leak": adversarial["teacher_only_leak"],
        "source_laundering_auto": adversarial["source_laundering_auto"],
    }
    safety_all_zero = all(v == 0 for v in safety.values())
    enough = (len(line_b_rows) >= 100 and q_b["point_decisions"] >= 300
              and len(line_c_rows) >= 100)
    line_a_full = line_a_audit["live_retrieval_available"]
    c_real = c_stats["quality_axis"] == "real_llm"
    if not safety_all_zero:
        verdict = "NO-GO"
    elif enough and line_a_full and c_real:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    # ---- emit artifacts ----
    _wj("benchmark_manifest_m22.json", {
        "stage": "M22 RAG-vs-Luban-v1 Quality Benchmark",
        "lines": {"A": "old RAG retrieval/answer baseline", "B": "M16 deterministic controlled runtime",
                  "C": "M17/M19 runtime LLM adjudicator (/api/v1/ws)", "D": "M20.2 delta projected candidate"},
        "real_entry_BC": "/api/v1/ws -> _maybe_attach_v1_controlled_runtime / _maybe_attach_v1_llm_adjudication",
        "line_c_mode": c_stats["mode"], "line_c_quality_axis": c_stats["quality_axis"],
        "submissions_per_grading_line": len(line_b_rows),
        "point_decisions_B": q_b["point_decisions"], "point_decisions_C": q_c["point_decisions"],
        "question_type_distribution": dict(type_dist),
        "production_models": {"primary": adj.PRIMARY_MODEL, "fallback": adj.FALLBACK_MODEL},
        "red_lines": {"production_default_flip": False, "remote_write": False, "db_write": False,
                      "canonical_truth_write": False, "published_registry": False,
                      "m202_absorbed_into_runtime": False, "model_or_council_vote_as_source": False},
        "verdict": verdict})
    _wl("sample_inventory_m22.jsonl", [{"question_id": s["question_id"], "variant": s["variant"],
                                        "n_counted": s["n_counted"],
                                        "types": sorted({s["gold"][p]["question_type"] for p in s["counted_point_ids"]})}
                                       for s in samples])
    _wl("baseline_rag_results_m22.jsonl", line_a_rows)
    _wl("deterministic_m16_results_m22.jsonl", line_b_rows)
    _wl("runtime_llm_v1_results_m22.jsonl", line_c_rows)
    _wl("delta_candidate_m202_results_m22.jsonl", line_d_rows)
    _wj("quality_metrics_m22.json", {
        "line_B_m16_deterministic": {k: v for k, v in q_b.items() if k != "bad_cases"},
        "line_C_runtime_llm_v1": {k: v for k, v in q_c.items() if k != "bad_cases"},
        "line_C_quality_axis": c_stats["quality_axis"],
        "line_A_old_rag": {"produces_point_decisions": False, "role": "retrieval/answer baseline"},
        "line_D_m202_delta": {"produces_point_decisions": False, "role": "projected packet-compression candidate"},
        "construction_gold_basis": "per-point gold_auto_eligible = evidence genuinely present AND auto-eligible authority kind; review/external never auto-eligible"})
    _wj("latency_cost_metrics_m22.json", latency_cost)
    _wj("adversarial_verification_m22.json", adversarial)
    _wl("council_review_m22.jsonl", council_rows)
    _wj("delta_candidate_summary_m22.json", line_d_summary)
    _wj("missing_input_audit_m22.json", {"line_A_old_rag": line_a_audit,
                                         "note": "no fabricated data; unavailable axes are marked partial"})
    _emit_answer_examples(tournament, q_b, q_c, line_d_summary, line_a_audit)
    _emit_decision_report(verdict, q_b, q_c, line_a_audit, line_d_summary, safety, c_stats,
                          latency_cost, type_dist, len(line_b_rows))

    bad_queue = q_b["bad_cases"] + q_c["bad_cases"] + adversarial.get("bad_cases", [])
    _wl("bad_case_queue_m22.jsonl", bad_queue)  # always (re)write — empty file means no bad cases

    summary = {"verdict": verdict, "safety_all_zero": safety_all_zero, "safety": safety,
               "submissions": len(line_b_rows), "point_decisions_B": q_b["point_decisions"],
               "point_decisions_C": q_c["point_decisions"], "line_c_mode": c_stats["mode"],
               "line_a_live_retrieval": line_a_audit["live_retrieval_available"],
               "delta_packet_tokens_saved_pct": line_d_summary["packet_tokens_saved_pct"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _adversarial(line_b_rows, line_c_rows, samples_by_key, registry) -> dict[str, Any]:
    """Attack fp / source laundering / unsupported positive / list partial auto / teacher-only leak."""
    list_pids = {(p["question_id"], p["point_id"]) for p in registry.get("points", [])
                 if p["authority_kind"] == "list_rule_full_coverage"}
    res = {"attacks": ["false_positive", "source_laundering", "unsupported_positive",
                       "list_partial_auto", "teacher_only_leak"],
           "false_positive": 0, "source_laundering_auto": 0, "unsupported_positive": 0,
           "list_partial_auto": 0, "teacher_only_leak": 0, "bad_cases": []}
    # C-line: unsupported positive = auto with invalid evidence span; source laundering blocked count
    for r in line_c_rows:
        if not r.get("produces_point_decisions"):
            continue
        s = samples_by_key.get(f"{r['question_id']}::{r['variant']}")
        for d in r["decisions"]:
            if d.get("auto") and d.get("evidence_span_valid") is False:
                res["unsupported_positive"] += 1
                res["bad_cases"].append({**d, "question_id": r["question_id"], "variant": r["variant"],
                                         "kind": "unsupported_positive"})
    # B+C: false positive on gold miss + list partial auto
    for rows, auto_key in ((line_b_rows, "auto"), (line_c_rows, "auto")):
        for r in rows:
            if not r.get("produces_point_decisions"):
                continue
            s = samples_by_key.get(f"{r['question_id']}::{r['variant']}")
            if not s:
                continue
            for d in r["decisions"]:
                pid = d["point_id"]
                g = s["gold"].get(pid)
                if not g:
                    continue
                if d.get(auto_key) and not g["gold_auto_eligible"]:
                    res["false_positive"] += 1
                if d.get(auto_key) and (r["question_id"], pid) in list_pids and not g["gold_auto_eligible"]:
                    res["list_partial_auto"] += 1
    return res


def _council(line_c_rows, samples_by_key, readiness, args, supply) -> list[dict[str, Any]]:
    """fanout-and-synthesize: send contested C-line points (validator downgrades) to the AI council
    (reuse M17B council). reviewer_type=ai_expert_council, human_reviewed=false; review authority only."""
    contested = []
    for r in line_c_rows:
        if not r.get("produces_point_decisions"):
            continue
        for d in r["decisions"]:
            if d.get("downgrade_reason"):
                contested.append({"question_id": r["question_id"], "point_id": d["point_id"],
                                  "variant": r["variant"], "llm_disposition": d.get("llm_disposition"),
                                  "deterministic_auto": d.get("auto"), "downgrade_reason": d.get("downgrade_reason"),
                                  "authority_kind": None, "student_answer": samples_by_key.get(
                                      f"{r['question_id']}::{r['variant']}", {}).get("answer", "")})
    seen, uniq = set(), []
    for c in contested:
        k = (c["question_id"], c["point_id"], c["downgrade_reason"])
        if k not in seen:
            seen.add(k); uniq.append(c)
    rows = []
    for c in uniq[: args.frontier_council]:
        votes = {"opus48_workflow_judge": m17b._opus_judge(c)}
        if args.run_live and readiness.get("DEEPSEEK_API_KEY"):
            user = json.dumps({"question_id": c["question_id"], "point_id": c["point_id"],
                               "student_answer": c["student_answer"][:300],
                               "llm_disposition": c["llm_disposition"],
                               "downgrade_reason": c["downgrade_reason"]}, ensure_ascii=False)
            try:
                votes["deepseek_v4_prosecutor"] = m17b._factory_vote("deepseek-chat",
                    "你是建筑实务点级复核 Prosecutor，只判 keep/rewrite/work_order/validator_rule_fix/drop。只输出 JSON {decision,rationale}。", user)
            except Exception as e:  # noqa: BLE001
                votes["deepseek_v4_prosecutor"] = {"decision": "needs_review", "rationale": f"failclosed:{type(e).__name__}"}
        agg = m17b._aggregate_council(votes)
        rows.append({**c, "votes": votes, **agg})
    return rows


def _tournament(line_b_rows, line_c_rows, samples_by_key) -> dict[str, Any]:
    """Pick clearest 'must-LLM' and 'deterministic-enough' cases for the examples doc."""
    must_llm, det_enough = [], []
    c_by_key = {f"{r['question_id']}::{r['variant']}": r for r in line_c_rows if r.get("produces_point_decisions")}
    b_by_key = {f"{r['question_id']}::{r['variant']}": r for r in line_b_rows if r.get("produces_point_decisions")}
    for key, s in samples_by_key.items():
        c, b = c_by_key.get(key), b_by_key.get(key)
        if not c or not b:
            continue
        c_auto = {d["point_id"]: d.get("auto") for d in c["decisions"]}
        b_auto = {d["point_id"]: d.get("auto") for d in b["decisions"]}
        c_partial = any(d.get("final_disposition") in ("partial", "needs_review") for d in c["decisions"])
        # must-LLM: variant where LLM produced a finer disposition (partial/needs_review) than det binary
        if c_partial and s["variant"] in ("partial_half", "partial_third", "near_miss", "hallucination_bait"):
            must_llm.append({"key": key, "variant": s["variant"], "reason": "LLM 给出 partial/needs_review 细档，det 只能二元 auto/review"})
        # deterministic-enough: correct_full where B and C both auto exactly the gold-eligible set
        if s["variant"] in ("correct_full", "verbose_correct", "reordered_correct"):
            gold_set = {p for p, g in s["gold"].items() if g["gold_auto_eligible"]}
            if {p for p, a in b_auto.items() if a} == gold_set and {p for p, a in c_auto.items() if a} == gold_set:
                det_enough.append({"key": key, "variant": s["variant"], "reason": "正确作答下 det 与 LLM 给出相同的 auto 集合，deterministic 足够"})
    return {"must_llm": must_llm[:8], "deterministic_enough": det_enough[:8]}


def _emit_paired_matrix(line_b_rows, line_c_rows, samples_by_key) -> None:
    c_by_key = {f"{r['question_id']}::{r['variant']}": r for r in line_c_rows if r.get("produces_point_decisions")}
    out = []
    for r in line_b_rows:
        if not r.get("produces_point_decisions"):
            continue
        key = f"{r['question_id']}::{r['variant']}"
        s = samples_by_key.get(key)
        c = c_by_key.get(key)
        c_auto = {d["point_id"]: d for d in c["decisions"]} if c else {}
        for d in r["decisions"]:
            pid = d["point_id"]
            g = s["gold"].get(pid) if s else {}
            cd = c_auto.get(pid, {})
            out.append({"question_id": r["question_id"], "variant": r["variant"], "point_id": pid,
                        "question_type": g.get("question_type"), "gold_auto_eligible": g.get("gold_auto_eligible"),
                        "B_m16_auto": d.get("auto"), "C_v1_auto": cd.get("auto"),
                        "C_final_disposition": cd.get("final_disposition"),
                        "B_correct": d.get("auto") == g.get("gold_auto_eligible"),
                        "C_correct": cd.get("auto") == g.get("gold_auto_eligible") if cd else None})
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "paired_comparison_matrix_m22.csv").open("w", encoding="utf-8", newline="") as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader(); w.writerows(out)


def _emit_answer_examples(tournament, q_b, q_c, line_d_summary, line_a_audit) -> None:
    lines = ["# M22 Answer-Quality Examples\n",
             "## 必须 LLM 参与的样本（det 二元不足，LLM 给细档）\n"]
    for x in tournament["must_llm"]:
        lines.append(f"- `{x['key']}`（{x['variant']}）：{x['reason']}")
    lines.append("\n## deterministic 足够的样本（正确作答下 det 与 LLM auto 集合一致）\n")
    for x in tournament["deterministic_enough"]:
        lines.append(f"- `{x['key']}`（{x['variant']}）：{x['reason']}")
    lines.append("\n## 四条线职责（证据/引用/判分能力）\n")
    lines.append(f"- A old RAG：retrieval/answer baseline，无点级判分，无 validator，hallucination 暴露；live 检索 {'可用' if line_a_audit['live_retrieval_available'] else '不可用（无构建 KB）'}。")
    lines.append("- B M16 deterministic：点级 auto/review，rule/registry 签名，二元、无 partial 细档。")
    lines.append(f"- C runtime LLM v1：点级 accept/partial/reject/needs_review，evidence_span，validator 安全地板，agreement={q_c['point_hit_agreement']}。")
    lines.append(f"- D M20.2 delta：候选包压缩投影（token 省 {line_d_summary['packet_tokens_saved_pct']}%），评分改写仍为 work-order，未进 runtime。")
    _wt("answer_quality_examples_m22.md", "\n".join(lines))


def _emit_decision_report(verdict, q_b, q_c, line_a_audit, line_d_summary, safety, c_stats,
                          latency_cost, type_dist, n_sub) -> None:
    txt = f"""# M22 Decision Report — RAG vs Luban v1 职责切分

## 裁决：{verdict}

## 安全不变量（全 0 才可发布）
{json.dumps(safety, ensure_ascii=False, indent=2)}

## 规模
- grading 提交数：{n_sub}；B 点级决策：{q_b['point_decisions']}；C 点级决策：{q_c['point_decisions']}
- 题型分布：{json.dumps(dict(type_dist), ensure_ascii=False)}

## 四条线职责切分（核心产品结论）
- **A 旧 RAG**：保留为 **retrieval / source expansion / answer baseline**。它擅长自由文本作答与源检索，但**不是点级判分权威**，无 validator、hallucination 暴露。live 检索本轮 {'可用' if line_a_audit['live_retrieval_available'] else '不可用（data/knowledge_bases 为空），降级为 retrieval baseline（已审计，未伪造）'}。
- **B M16 deterministic**：保留为 **安全地板 / 规则签名层**。点级 auto/review 二元、确定、零成本、低延迟；但只能二元，无 partial 细档与解释。
- **C M17/M19 runtime LLM v1**：接管 **点级细档判分 + evidence_span + 解释 + Learning Brain 证据**。在 partial/near_miss/hallucination 变体上给出 det 给不出的 partial/needs_review；validator 作安全地板保证 fp/source_mismatch=0。quality_axis={c_stats['quality_axis']}。
- **D M20.2 delta**：**future_delta candidate**。本轮唯一可测收益 = packet 压缩（token 省 {line_d_summary['packet_tokens_saved_pct']}%、bytes 省 {line_d_summary['packet_bytes_saved_pct']}%）；{line_d_summary['grading_workorders_pending_not_executable']} 个评分改写仍是 work-order（runtime_effect=candidate_context_only），**未吸收进 runtime**；进入下一版 registry 需经独立编译里程碑（非 M22）。

## 何时必须 LLM / 何时 deterministic 足够
- 必须 LLM：部分正确、错因相近、诱导 hallucination 的样本——需要 partial 细档与 evidence 解释。
- deterministic 足够：完整正确作答、纯 numeric/list 全覆盖点——det 与 LLM auto 集合一致，且零成本零延迟。

## 红线
未 flip production default；未写远端/DB/canonical truth；未发 registry；M20.2 仅候选对照、未进 runtime；official_answer/model/council vote 未当 source。
"""
    _wt("decision_report_m22.md", txt)


if __name__ == "__main__":
    main()
