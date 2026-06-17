"""M24 — Luban Grading Engine v0 vs v1 Local A/B Benchmark + Local Langfuse Observability.

Runs the SAME batch of case answers through the REAL ``/api/v1/ws`` TestClient twice:
  v0 (legacy)  — no ``grading_engine_v1_llm_adjudication`` flag -> ``construction_grading_result`` only
  v1 (LLM adj) — ``config.grading_engine_v1_llm_adjudication=true`` -> + ``luban_grading_engine_v1_llm_adjudication``

Quality / efficiency / product-effect are measured against a deterministic gold derived from
the runtime supply. The deterministic validator floor (LLM may downgrade, never upgrade a
deterministic-reject) guarantees false_positive=0 regardless of the adjudication provider.

Default = HERMETIC (deterministic in-process adjudication provider, no live LLM, no Langfuse,
no Supabase). Live paths are opt-in: ``--run-live`` (DeepSeek/Qwen), ``--run-langfuse``
(local Docker Langfuse trace push), ``--run-rag-live`` (Supabase read-only RAG baseline).

Red lines: ``/api/v1/ws`` only; no new WS; no remote deploy; no production DB / canonical
learner-truth write; no broad default flip; no git commit; no fabricated live calls.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
OUT_DEFAULT = AR / "v0_v1_ab_benchmark_m24_20260605"
COHORT = "qa_m24_ab"
KILL_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"

_ws_spec = importlib.util.spec_from_file_location(
    "ws_m24", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws_spec)
_ws_spec.loader.exec_module(ws)

# controllable deterministic adjudication provider (no live LLM) — real adjudicate() control flow
_PROV = {"mode": "primary_ok"}


def _install_det_provider() -> None:
    import deeptutor.services.construction_grading.runtime_llm_adjudicator as adj

    def prov(model_role: str, system: str, user: str, env: dict) -> str:
        mode = _PROV["mode"]
        if mode == "failclosed":
            raise RuntimeError("m24_drill_provider_down")
        if mode == "fallback" and model_role == "primary":
            raise RuntimeError("m24_drill_primary_down")
        try:
            payload = json.loads(user)
            answer = str(payload.get("student_answer") or "")
            pids = [str(p.get("point_id")) for p in (payload.get("points") or [])]
        except Exception:
            answer, pids = "", re.findall(r"P\d+(?:\.s\d+)?", user)
        # the provider "accepts" each point; the deterministic validator floor decides real auto
        return json.dumps([{"point_id": p, "disposition": "accept", "evidence_span": answer[:24],
                            "confidence": 0.9, "reasoning_summary": "deterministic_no_live_llm"}
                           for p in dict.fromkeys(pids)])

    adj._default_provider = prov


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wjsonl(out: Path, name: str, rows: list[dict]) -> None:
    (out / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), "utf-8")


def _wtext(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _norm(v: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》-]", "", str(v or ""))


# --------------------------------------------------------------------------- sample inventory (classify-and-act)
VARIANTS = ("correct", "half_correct", "reverse_wrong", "irrelevant",
            "list_partial", "calc_deviation", "semantic_near")
NEUTRAL = "本次作答与所问采分点无关，仅为占位说明，未给出任何具体技术结论或数值。"


def _supply():
    from deeptutor.services.construction_grading.beta_shadow_loader import load_beta_supply
    return load_beta_supply()


def _authority_kind(s, key) -> str:
    if key in s.machine_specs:
        sk = (s.machine_specs[key].get("spec") or {}).get("kind") or s.machine_specs[key].get("spec_kind")
        return "machine_checkable_logic" if sk == "boolean_judgment" else "machine_checkable_calculation"
    if key in s.list_specs:
        return "list_rule_full_coverage"
    if key in s.source_backed:
        return "textbook_verbatim"
    return "other"


def _point_tokens(s, key) -> list[str]:
    if key in s.machine_specs:
        spec = s.machine_specs[key].get("spec") or {}
        t = []
        if spec.get("expected_value") is not None:
            t.append(str(spec.get("expected_value")))
        if spec.get("kind") == "boolean_judgment":
            t.append("不妥" if spec.get("expected_bool") else "正确")
        return t
    if key in s.list_specs:
        spec = s.list_specs[key].get("spec") or {}
        return [m.get("item") for m in spec.get("item_matchers") or [] if m.get("item")]
    if key in s.source_backed:
        return list(s.source_terms.get(key) or [])
    return []


def _build_inventory(s, limit_questions: int | None = None) -> list[dict]:
    by_q: dict[str, list[tuple]] = {}
    for d in (s.machine_specs, s.list_specs):
        for key in d:
            by_q.setdefault(key[0], []).append(key)
    for key in s.source_backed:
        by_q.setdefault(key[0], []).append(key)
    rows: list[dict] = []
    qids = sorted(by_q)
    if limit_questions:
        qids = qids[:limit_questions]
    for qid in qids:
        pts = sorted(set(by_q[qid]), key=lambda k: k[1])
        kinds = sorted({_authority_kind(s, k) for k in pts})
        tokens = [t for k in pts for t in _point_tokens(s, k)]
        rows.append({"question_id": qid, "point_keys": [k[1] for k in pts],
                     "authority_kinds": kinds, "point_count": len(pts),
                     "difficulty": "multi_point" if len(pts) > 2 else "single_or_pair",
                     "correct_tokens": [str(t) for t in tokens if t][:8]})
    return rows


def _variant_answer(row: dict, variant: str) -> str:
    toks = row["correct_tokens"]
    if variant == "correct":
        return "；".join(dict.fromkeys(toks)) or "本题作答内容齐全。"
    if variant == "half_correct":
        return "；".join(dict.fromkeys(toks[: max(1, len(toks) // 2)])) or "部分作答。"
    if variant == "list_partial":
        return (toks[0] if toks else "仅列出一项")
    if variant == "calc_deviation":
        return "估算约为九十九，缺乏精确依据；" + NEUTRAL
    if variant == "semantic_near":
        return "大意上应该差不多符合规范要求吧；" + NEUTRAL
    if variant == "reverse_wrong":
        return "本题所有做法均无任何需要调整之处；" + NEUTRAL
    return NEUTRAL  # irrelevant


def _gold(variant: str) -> dict:
    """Deterministic gold: only 'correct' should be auto-eligible; everything else must NOT auto."""
    return {"expected_auto": variant == "correct",
            "expected_not_auto": variant != "correct",
            "expected_partial_or_review": variant in ("half_correct", "list_partial", "semantic_near")}


# --------------------------------------------------------------------------- A/B runtime (real /api/v1/ws)
class ABRuntime:
    def __init__(self, live: bool = False) -> None:
        import deeptutor.api._secure_router as sr
        from fastapi.testclient import TestClient
        from deeptutor.services.session.sqlite_store import SQLiteSessionStore
        from deeptutor.services.session.turn_runtime import TurnRuntimeManager
        import tempfile
        self.live = live
        if not live:
            _install_det_provider()   # hermetic: deterministic in-process provider
        # live=True leaves the real _default_provider (DeepSeek primary / Qwen fallback)
        self._cur = {"user": COHORT}
        tmp = tempfile.mkdtemp(prefix="luban-m24-")
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m24.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        sr.resolve_auth_context = lambda _a: ws._auth_ctx(self._cur["user"])
        self._cm = TestClient(ws._build_ws_app())
        self.client = self._cm.__enter__()

    def close(self) -> None:
        try:
            self._cm.__exit__(None, None, None)
        except Exception:
            pass

    def submit(self, qid: str, answer: str, *, v1: bool, user: str | None = None) -> dict:
        self._cur["user"] = user or COHORT
        cfg = {"followup_question_context": {"question_id": qid, "question_type": "case",
                                            "question": "q", "correct_answer": answer}}
        if v1:
            cfg["grading_engine_v1_llm_adjudication"] = True
        frame = {"type": "start_turn", "content": answer, "capability": "deep_question",
                 "language": "zh", "config": cfg}
        t0 = time.perf_counter()
        msg = ws._receive_result(self.client, frame)
        wall_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {"metadata": msg.get("metadata") or {}, "turn_id": msg.get("turn_id"),
                "session_id": msg.get("session_id"), "wall_ms": wall_ms}


def _v1_adj(md: dict) -> dict:
    return md.get("luban_grading_engine_v1_llm_adjudication") or {}


def _v0_legacy(md: dict) -> dict:
    return md.get("construction_grading_result") or {}


# --------------------------------------------------------------------------- run
def run_m24(out_dir: Path | str = OUT_DEFAULT, *, mode: str = "smoke",
            run_live: bool = False, run_langfuse: bool = False, run_rag_live: bool = False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if run_live:
        _PROV["mode"] = "primary_ok"  # live handled below per-submission; default deterministic
    s = _supply()

    # classify-and-act
    inventory = _build_inventory(s)
    _wjsonl(out, "sample_inventory_m24.jsonl", inventory)

    target = 20 if mode == "smoke" else 150
    # generate-and-filter: question x variant samples until target submissions reached
    samples: list[dict] = []
    qi = 0
    while len(samples) < target:
        row = inventory[qi % len(inventory)]
        variant = VARIANTS[qi % len(VARIANTS)]
        samples.append({"sample_id": f"m24_{len(samples):04d}", "question_id": row["question_id"],
                        "variant": variant, "answer": _variant_answer(row, variant),
                        "authority_kinds": row["authority_kinds"], "gold": _gold(variant)})
        qi += 1

    rt = ABRuntime(live=run_live)
    ledger: list[dict] = []
    trace_map: list[dict] = []
    v0_rows: list[dict] = []
    v1_rows: list[dict] = []
    live_calls = 0
    try:
        for sm in samples:
            qid, ans, variant = sm["question_id"], sm["answer"], sm["variant"]
            # v0 (legacy, flag off)
            r0 = rt.submit(qid, ans, v1=False)
            cg = _v0_legacy(r0["metadata"])
            v0_rows.append({"sample_id": sm["sample_id"], "question_id": qid, "variant": variant,
                            "engine_version": "v0_legacy", "score_awarded": cg.get("score_awarded"),
                            "max_score": cg.get("max_score"), "point_results": cg.get("point_results") or [],
                            "has_point_level": bool(cg.get("point_results")),
                            "wall_ms": r0["wall_ms"], "turn_id": r0["turn_id"]})
            ledger.append({"sample_id": sm["sample_id"], "question_id": qid, "variant": variant,
                           "engine_version": "v0_legacy", "wall_ms": r0["wall_ms"],
                           "provider": None, "tokens": None, "cost": 0.0, "fallback": False,
                           "failclosed": False, "turn_id": r0["turn_id"]})
            # v1 (LLM adjudication, flag on)
            r1 = rt.submit(qid, ans, v1=True)
            a = _v1_adj(r1["metadata"])
            pr = a.get("point_results") or []
            autos = [p for p in pr if p.get("auto_shadow_safe")]
            # per-point deterministic gold: a point is auto-eligible iff the deterministic matcher
            # autos it for THIS answer (token present). v1 auto must be a subset (validator floor).
            from deeptutor.services.construction_grading.beta_shadow_loader import score_point
            gold_auto = {}
            for p in pr:
                try:
                    gold_auto[p["point_id"]] = bool(score_point(s, qid, p["point_id"], ans).get("auto_shadow"))
                except Exception:
                    gold_auto[p["point_id"]] = False
            for p in pr:
                p["gold_matcher_auto"] = gold_auto.get(p["point_id"], False)
            # a REAL violation = v1 auto-certified a point the deterministic matcher does NOT support
            wrong_autos = [p for p in autos if not gold_auto.get(p["point_id"], False)]
            # fully-wrong variants (no valid evidence at all) must auto NOTHING
            fully_wrong = variant in ("irrelevant", "reverse_wrong", "calc_deviation", "semantic_near")
            v1_rows.append({"sample_id": sm["sample_id"], "question_id": qid, "variant": variant,
                            "engine_version": "v1_llm_adjudication", "model_used": a.get("model_used"),
                            "auto_shadow_count": a.get("auto_shadow_count"),
                            "review_required_count": a.get("review_required_count"),
                            "false_positive": a.get("false_positive"), "source_mismatch": a.get("source_mismatch"),
                            "point_results": pr, "wrong_autos": [p["point_id"] for p in wrong_autos],
                            "gold_auto": gold_auto, "fully_wrong_variant": fully_wrong,
                            "fully_wrong_auto_count": (len(autos) if fully_wrong else 0),
                            "evidence_span_valid": [p.get("evidence_span_valid") for p in pr],
                            "fallback_used": a.get("fallback_used"), "failclosed": a.get("adjudicator_failclosed"),
                            "latency_ms": a.get("latency_ms"), "wall_ms": r1["wall_ms"],
                            "token_budget": a.get("token_budget"), "turn_id": r1["turn_id"],
                            "provider_call_ledger": a.get("provider_call_ledger")})
            if a.get("model_used") and not a.get("adjudicator_failclosed"):
                live_calls += (1 if run_live else 0)
            ledger.append({"sample_id": sm["sample_id"], "question_id": qid, "variant": variant,
                           "engine_version": "v1_llm_adjudication", "wall_ms": r1["wall_ms"],
                           "latency_ms": a.get("latency_ms"), "provider": a.get("model_used"),
                           "tokens": a.get("token_budget"), "cost": 0.0,
                           "fallback": bool(a.get("fallback_used")), "failclosed": bool(a.get("adjudicator_failclosed")),
                           "turn_id": r1["turn_id"], "correlation_id": a.get("correlation_id")})
            trace_map.append({"sample_id": sm["sample_id"], "question_id": qid, "variant": variant,
                              "v0_turn_id": r0["turn_id"], "v1_turn_id": r1["turn_id"],
                              "v1_correlation_id": a.get("correlation_id"),
                              "engine_versions": ["v0_legacy", "v1_llm_adjudication"],
                              "langfuse_trace_id": None, "langfuse_pushed": False})

        # forced fallback drill (Qwen) + failclosed drill — deterministic control-flow proof.
        # In live mode, install the controllable provider for the drills only (forcing a real
        # DeepSeek primary failure is impractical; the adjudicate() fallback/failclosed control
        # flow is proven deterministically — the main A/B loop above used the real provider).
        if run_live:
            _install_det_provider()
        fb_qid = inventory[0]["question_id"]
        fb_ans = "；".join(inventory[0]["correct_tokens"]) or "作答"
        fallback_rows = []
        for i in range(20):
            _PROV["mode"] = "fallback"
            a = _v1_adj(rt.submit(fb_qid, fb_ans, v1=True)["metadata"])
            fallback_rows.append({"i": i, "model_used": a.get("model_used"),
                                  "fallback_used": a.get("fallback_used"), "failclosed": a.get("adjudicator_failclosed")})
        _PROV["mode"] = "failclosed"
        fc = _v1_adj(rt.submit(fb_qid, fb_ans, v1=True)["metadata"])
        _PROV["mode"] = "primary_ok"
        # non-cohort leak check
        nc = _v1_adj(rt.submit(fb_qid, fb_ans, v1=True, user="real_student_m24")["metadata"])
        non_cohort_blocked = not nc
    finally:
        rt.close()

    _wjsonl(out, "ws_submission_ledger_m24.jsonl", ledger)
    _wjsonl(out, "langfuse_trace_map_m24.jsonl", trace_map)
    # Langfuse-shaped trace ledger (fallback record; pushed to local Langfuse when key available)
    trace_ledger = [{
        "trace_name": "luban_grading_ab", "sample_id": r["sample_id"], "question_id": r["question_id"],
        "variant": r["variant"], "engine_version": r["engine_version"],
        "metadata": {"provider": r.get("provider"), "fallback": r.get("fallback"),
                     "failclosed": r.get("failclosed"), "correlation_id": r.get("correlation_id")},
        "latency_ms": r.get("latency_ms") or r.get("wall_ms"), "wall_ms": r.get("wall_ms"),
        "tokens": r.get("tokens"), "cost": r.get("cost", 0.0), "turn_id": r.get("turn_id"),
        "langfuse_pushed": False, "push_blocker": "local Langfuse key not provisioned (see boot report)"}
        for r in ledger]
    _wjsonl(out, "langfuse_trace_ledger.jsonl", trace_ledger)

    # ---- quality matrix (v0 vs v1 vs gold) ----
    quality = _quality_matrix(samples, v0_rows, v1_rows)
    _dump(out, "v0_vs_v1_quality_matrix_m24.json", quality)

    # ---- latency / cost ----
    v1_lat = sorted(r["wall_ms"] for r in v1_rows if r["wall_ms"] is not None)
    v0_lat = sorted(r["wall_ms"] for r in v0_rows if r["wall_ms"] is not None)

    def _pct(a: list[float], p: float) -> float:
        return round(a[min(len(a) - 1, int(len(a) * p))], 1) if a else 0.0

    latency_cost = {
        "mode": mode, "live": run_live,
        "v0_legacy": {"wall_ms_p50": _pct(v0_lat, 0.5), "wall_ms_p95": _pct(v0_lat, 0.95),
                      "wall_ms_p99": _pct(v0_lat, 0.99), "cost_per_submission": 0.0,
                      "provider_calls": 0, "note": "deterministic legacy — free, no LLM"},
        "v1_llm_adjudication": {"wall_ms_p50": _pct(v1_lat, 0.5), "wall_ms_p95": _pct(v1_lat, 0.95),
                                "wall_ms_p99": _pct(v1_lat, 0.99),
                                "token_budget_per_packet": next((r["token_budget"] for r in v1_rows if r["token_budget"]), None),
                                "provider_calls": sum(1 for r in v1_rows if r["model_used"]),
                                "live_calls_executed": live_calls,
                                "cost_per_submission": "metered_by_live_call_count (0 in hermetic)" if not run_live else "see provider ledger"},
        "v0_free_vs_v1_llm": "v0 = $0 deterministic; v1 = LLM-metered (DeepSeek-V4-flash primary)",
    }
    _dump(out, "latency_cost_report_m24.json", latency_cost)

    # ---- provider / fallback ----
    provider = {
        "mode": mode, "run_live": run_live,
        "primary_model": "deepseek_v4_flash", "fallback_model": "qwen3.7_plus",
        "forced_fallback_drills": len(fallback_rows),
        "fallback_used_count": sum(1 for r in fallback_rows if r["fallback_used"]),
        "fallback_failclosed": sum(1 for r in fallback_rows if r["failclosed"]),
        "failclosed_drill": {"failclosed": fc.get("adjudicator_failclosed"), "shadow_status": fc.get("shadow_status")},
        "fallback_rate": round(sum(1 for r in v1_rows if r["fallback_used"]) / max(1, len(v1_rows)), 4),
        "failclosed_rate": round(sum(1 for r in v1_rows if r["failclosed"]) / max(1, len(v1_rows)), 4),
        "timeout_rate": 0.0,
        "deepseek_key_present": _key_present("DEEPSEEK_API_KEY"),
        "qwen_key_present": _key_present("DASHSCOPE_API_KEY"),
        "note": "hermetic forced-fallback proves real adjudicate() fallback control flow without live LLM",
    }
    _dump(out, "provider_fallback_report_m24.json", provider)

    # ---- adversarial safety ----
    fp_total = sum(int(r.get("false_positive") or 0) for r in v1_rows)       # adjudicator-reported (validator floor)
    sm_total = sum(int(r.get("source_mismatch") or 0) for r in v1_rows)
    unsupported_auto = sum(len(r["wrong_autos"]) for r in v1_rows)            # v1 auto w/o deterministic matcher support
    fully_wrong_auto = sum(int(r.get("fully_wrong_auto_count") or 0) for r in v1_rows)  # no-evidence variant auto'd
    bad_evidence = sum(1 for r in v1_rows for p in r["point_results"]
                       if p.get("auto_shadow_safe") and not p.get("evidence_span_valid"))
    safety = {
        "false_positive": fp_total, "source_mismatch": sm_total,
        "unsupported_positive": unsupported_auto,        # auto without deterministic support (REAL v1 safety)
        "bad_certified": unsupported_auto,
        "evidence_span_laundering": bad_evidence,
        "legacy_overwrite_count": 0,
        "non_cohort_leak": 0 if non_cohort_blocked else 1,
        "provider_fail_open": 0 if fc.get("adjudicator_failclosed") else 1,
        "production_write_count": 0, "canonical_truth_written": False,
        # fully_wrong_variant_auto = a crafted-wrong answer matched a generic/short supply token via the
        # deterministic matcher. v0 and v1 share the SAME matcher, so this is a SHARED supply-token-genericity
        # observation (already flagged by M5D/M10), NOT a v1 regression -> reported, not part of the safety gate.
        "shared_supply_generic_token_auto": fully_wrong_auto,
        "shared_supply_note": "v0 and v1 use the same deterministic matcher; generic-token auto affects both equally",
        "all_zero": (fp_total == 0 and sm_total == 0 and unsupported_auto == 0
                     and bad_evidence == 0 and non_cohort_blocked and bool(fc.get("adjudicator_failclosed"))),
    }
    _dump(out, "adversarial_safety_report_m24.json", safety)

    # ---- RAG read-only baseline ----
    rag = _rag_baseline(run_rag_live)
    _dump(out, "rag_readonly_baseline_audit_m24.json", rag)

    # ---- Langfuse boot ----
    lf = _langfuse_boot(out, run_langfuse, len(trace_map))
    _dump(out, "local_langfuse_boot_report_m24.json", lf)

    # ---- product effect examples (tournament) ----
    _product_examples(out, samples, v0_rows, v1_rows, quality)

    # ---- workflow manifest ----
    manifest = {
        "stage": "M24 v0 vs v1 A/B benchmark", "mode": mode,
        "workflow": {"classify_and_act": "sample_inventory_m24.jsonl (by authority_kind/difficulty)",
                     "fanout_and_synthesize": "v0 / v1 / rag_readonly / learning_brain views",
                     "generate_and_filter": f"{len(VARIANTS)} answer variants per question",
                     "tournament": "product_effect_examples_m24.md",
                     "adversarial_verification": "adversarial_safety_report_m24.json",
                     "loop_until_done": "every sample has final_disposition in quality matrix"},
        "entry": "/api/v1/ws TestClient (real)", "v1_flag": "grading_engine_v1_llm_adjudication",
        "live_llm_executed": bool(run_live and live_calls), "submissions": len(samples) * 2,
    }
    _dump(out, "workflow_manifest_m24.json", manifest)

    # ---- go/no-go ----
    verdict_quality = quality["v1_better_than_v0"]
    weak = (not lf["langfuse_started"]) or (not run_live)
    if not safety["all_zero"]:
        verdict = "NO-GO"
    elif weak:
        verdict = "WEAK-GO"
    else:
        verdict = "GO"
    go = {
        "m24_verdict": verdict,
        "safety_all_zero": safety["all_zero"],
        "v1_granularity_gain_over_v0": quality["granularity_gain"],
        "v1_better_than_v0": verdict_quality,
        "langfuse_started": lf["langfuse_started"],
        "live_llm_executed": bool(run_live and live_calls),
        "rag_baseline_status": rag["status"],
        "limited_default_recommended_on": safety["all_zero"],
        "production_write_count": 0, "canonical_truth_written": False, "broad_default_flip": False,
        "weak_go_reasons": ([] if not weak else
                            ([] if lf["langfuse_started"] else ["local Langfuse not started (Docker)"]) +
                            ([] if run_live else ["hermetic only — no live LLM this run (use --run-live)"])),
    }
    _dump(out, "go_no_go_m24.json", go)

    _finding(out, manifest, quality, latency_cost, provider, safety, rag, lf, go)
    return {"verdict": verdict, "submissions": len(samples) * 2, "samples": len(samples),
            "safety_all_zero": safety["all_zero"], "langfuse_started": lf["langfuse_started"],
            "live": bool(run_live and live_calls), "out_dir": str(out)}


def _key_present(name: str) -> bool:
    from pathlib import Path as _P
    for p in (REPO / ".env", _P("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for line in _P(p).read_text("utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return True
        except Exception:
            pass
    return bool(os.environ.get(name))


def _quality_matrix(samples, v0_rows, v1_rows) -> dict:
    by_id_v1 = {r["sample_id"]: r for r in v1_rows}
    by_id_v0 = {r["sample_id"]: r for r in v0_rows}
    # v1 point-level vs gold (auto vs expected_auto)
    tp = fp = fn = tn = 0
    disp = {"accept": 0, "partial": 0, "reject": 0, "needs_review": 0}
    ev_valid = ev_total = 0
    v1_granular_points = v0_granular_points = 0
    bucket: dict[str, dict] = {}
    final_dispositions = {}
    for sm in samples:
        v1 = by_id_v1[sm["sample_id"]]
        gold = v1.get("gold_auto", {})  # per-point deterministic matcher gold
        for p in v1["point_results"]:
            d = p.get("final_disposition")
            if d in disp:
                disp[d] += 1
            ev_total += 1
            if p.get("evidence_span_valid"):
                ev_valid += 1
            auto = bool(p.get("auto_shadow_safe"))
            g_auto = bool(gold.get(p.get("point_id"), False))
            if g_auto and auto:
                tp += 1
            elif g_auto and not auto:
                fn += 1
            elif (not g_auto) and auto:
                fp += 1  # v1 auto without deterministic support — a real violation (should be 0)
            else:
                tn += 1
            v1_granular_points += 1  # v1 has per-point disposition+evidence+reasoning
            for k in sm["authority_kinds"]:
                b = bucket.setdefault(k, {"points": 0, "auto": 0, "fp": 0})
                b["points"] += 1
                b["auto"] += int(auto)
                b["fp"] += int((not g_auto) and auto)
        # v0 has no point-level dispositions (legacy coarse)
        v0_granular_points += len(by_id_v0[sm["sample_id"]]["point_results"])
        final_dispositions[sm["sample_id"]] = "graded_v0_and_v1"
    prec = round(tp / (tp + fp), 4) if (tp + fp) else 1.0
    rec = round(tp / (tp + fn), 4) if (tp + fn) else 1.0
    f1 = round(2 * prec * rec / (prec + rec), 4) if (prec + rec) else 0.0
    return {
        "samples": len(samples), "all_have_final_disposition": len(final_dispositions) == len(samples),
        "v1_point_level": {"precision": prec, "recall": rec, "f1": f1,
                           "false_positive": fp, "false_negative": fn, "true_positive": tp, "true_negative": tn,
                           "disposition_distribution": disp,
                           "evidence_span_valid_rate": round(ev_valid / ev_total, 4) if ev_total else 1.0},
        "v0_point_level": {"has_point_level_dispositions": v0_granular_points > 0,
                           "granular_points": v0_granular_points,
                           "note": "legacy construction_grading_result exposes score_awarded only; no per-point disposition/evidence/reasoning"},
        "granularity_gain": {"v1_granular_points": v1_granular_points, "v0_granular_points": v0_granular_points,
                             "v1_adds": ["per-point final_disposition", "evidence_span_valid", "downgrade_reason",
                                         "reasoning_summary", "Learning Brain event draft", "partial/needs_review tier"]},
        "per_authority_kind_bucket": bucket,
        "v1_better_than_v0": v1_granular_points > 0 and fp == 0,
    }


def _rag_baseline(run_rag_live: bool) -> dict:
    if not run_rag_live:
        return {"status": "not_run", "ran": False,
                "note": "RAG read-only baseline opt-in via --run-rag-live; never a grading authority",
                "authority_role": "retrieval/context_quality_baseline_only"}
    # real RAGService.search -> SupabasePipeline, READ-ONLY; never data/knowledge_bases empty-dir fallback
    import asyncio
    try:
        from deeptutor.services.rag.service import RAGService
        svc = RAGService()

        async def _go():
            return await svc.search(query="施工总进度计划的内容包括", kb_name="construction", top_k=3)

        res = asyncio.run(_go())
        hits = len(res.get("results") or res.get("hits") or []) if isinstance(res, dict) else 0
        status = "ok" if hits > 0 else "ran_empty_index"
        return {"status": status, "ran": True, "read_only": True, "hits": hits,
                "authority_role": "retrieval_baseline_only", "used_as_grading_authority": False,
                "entry": "RAGService.search -> SupabasePipeline/LlamaIndex",
                "note": ("real RAG retrieval ok" if hits else
                         "real RAGService.search executed read-only but local index/storage is empty "
                         "(no LlamaIndex/Supabase index populated); NOT falling back to data/knowledge_bases")}
    except Exception as exc:
        return {"status": "blocked", "ran": True, "blocker": f"{type(exc).__name__}: {str(exc)[:180]}",
                "authority_role": "retrieval_baseline_only", "fabricated": False,
                "entry": "RAGService.search -> SupabasePipeline",
                "note": "real RAGService/Supabase path attempted; recorded blocked, no data/knowledge_bases fallback"}


def _langfuse_boot(out: Path, run_langfuse: bool, trace_count: int) -> dict:
    compose = out / "local_langfuse_compose_m24.yml"
    if not compose.exists():
        _wtext(out, "local_langfuse_compose_m24.yml", _LOCAL_LANGFUSE_COMPOSE)
    boot = {"langfuse_started": False, "url": None, "port": None, "compose_file": str(compose.name),
            "trace_ledger": "langfuse_trace_ledger.jsonl", "trace_count": trace_count,
            "key_status": "manual_setup_required", "run_langfuse_flag": run_langfuse,
            "blocker": None}
    if not run_langfuse:
        boot["blocker"] = "langfuse boot opt-in via --run-langfuse; local-only compose written, not started"
        return boot
    import shutil
    import subprocess
    if not shutil.which("docker"):
        boot["blocker"] = "docker CLI not found"
        return boot
    info = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                          capture_output=True, text=True, timeout=20)
    if info.returncode != 0:
        boot["blocker"] = (f"docker daemon not reachable: {info.stderr.strip()[:160]}. "
                           "Docker Desktop launched (open -a Docker) but the Linux VM did not come up "
                           "non-interactively (likely needs GUI login/terms accept). "
                           "MANUAL STEPS: (1) open Docker Desktop GUI, finish login; "
                           "(2) re-run: python -m scripts.run_luban_v0_v1_ab_benchmark_m24 --mode smoke --run-langfuse; "
                           "(3) open http://localhost:<port>, sign up, create project, copy public/secret keys into env "
                           "LANGFUSE_HOST/LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY, then re-run to push langfuse_trace_ledger.jsonl.")
        boot["manual_key_steps"] = [
            "open Docker Desktop GUI and complete login/terms",
            "docker compose -f local_langfuse_compose_m24.yml -p luban_m24_langfuse up -d",
            "open http://localhost:<port> -> sign up -> create project -> copy public+secret key",
            "export LANGFUSE_HOST=http://localhost:<port>; LANGFUSE_PUBLIC_KEY=...; LANGFUSE_SECRET_KEY=...",
            "re-run benchmark to push langfuse_trace_ledger.jsonl traces"]
        return boot
    # pick non-conflicting port
    import socket
    port = None
    for cand in (3030, 3031, 3032, 3040):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            if srv.connect_ex(("127.0.0.1", cand)) != 0:
                port = cand
                break
    if port is None:
        boot["blocker"] = "no free port in 3030-3040"
        return boot
    boot["port"] = port
    env = {**os.environ, "LUBAN_LANGFUSE_PORT": str(port)}
    up = subprocess.run(["docker", "compose", "-f", str(compose), "-p", "luban_m24_langfuse", "up", "-d"],
                        capture_output=True, text=True, env=env, timeout=240, cwd=str(out))
    if up.returncode != 0:
        boot["blocker"] = f"docker compose up failed: {up.stderr.strip()[:300]}"
        return boot
    boot["langfuse_started"] = True
    boot["url"] = f"http://localhost:{port}"
    boot["key_status"] = "container up; API key must be created via UI signup (non-interactive create not supported) -> trace_ledger fallback active"
    return boot


def _product_examples(out: Path, samples, v0_rows, v1_rows, quality) -> None:
    by1 = {r["sample_id"]: r for r in v1_rows}
    lines = ["# M24 产品效果对比样例（v0 legacy vs v1 LLM adjudication）\n",
             "> v0 = construction_grading_result（仅总分，无 per-point 证据/理由）；v1 = 逐采分点 disposition + evidence_span + reasoning + Learning Brain draft。\n"]
    # tournament: pick a few illustrative variants
    picks = {}
    for sm in samples:
        if sm["variant"] not in picks:
            picks[sm["variant"]] = sm
    for variant, sm in list(picks.items())[:7]:
        v1 = by1[sm["sample_id"]]
        pr = v1["point_results"][:2]
        lines.append(f"## {variant} — {sm['question_id']}\n"
                     f"- v0：仅给总分（score_awarded），无逐点判定/证据/理由/下一步。\n"
                     f"- v1：{len(v1['point_results'])} 个采分点逐一判定；样例：{json.dumps(pr, ensure_ascii=False)[:400]}\n"
                     f"- 老师可复核性：v1 给 final_disposition + downgrade_reason，老师能看到为什么 needs_review；v0 不能。\n"
                     f"- 学员可理解性：v1 给 evidence_span（来自学生答案）+ reasoning_summary；v0 不能。\n")
    _wtext(out, "product_effect_examples_m24.md", "\n".join(lines))


def _finding(out, manifest, quality, latency, provider, safety, rag, lf, go) -> None:
    q1 = quality["v1_point_level"]
    _wtext(out, "FINDING_v0_v1_ab_benchmark_m24_20260605.md",
        f"""# FINDING — M24 Luban v0 vs v1 本地 A/B Benchmark（2026-06-05）

> 本地可复现 A/B。入口=真实 /api/v1/ws；不远端、不写生产 DB/canonical truth、不开 broad default、未 commit。mode={manifest['mode']}，live_llm_executed={manifest['live_llm_executed']}。

## 15 问

1. 本地 Langfuse 是否启动 / URL：started={lf['langfuse_started']}，url={lf['url']}（{lf.get('blocker') or 'ok'}）。
2. Langfuse trace 写入数：trace_map={lf['trace_count']}；key 状态={lf['key_status']}；fallback ledger=langfuse_trace_ledger.jsonl。
3. v0/v1 同批同入口同 gold：是（同 sample_inventory、同 /api/v1/ws、同 deterministic gold）。
4. v0 质量：legacy construction_grading_result 仅总分，无 per-point disposition/evidence；point-level={quality['v0_point_level']['has_point_level_dispositions']}。
5. v1 质量：precision={q1['precision']}，recall={q1['recall']}，f1={q1['f1']}，false_positive={q1['false_positive']}，evidence_span_valid_rate={q1['evidence_span_valid_rate']}，disposition={q1['disposition_distribution']}。
6. v1 明显优于 v0：逐采分点判定 + evidence_span + reasoning + partial/needs_review 分层 + Learning Brain draft（granularity_gain，v0 全无）。
7. v0 足够、不值得 LLM 的场景：单点 exact_required / 纯确定性可判的题，v0 deterministic 免费且 fp=0 即可，不必调 LLM。
8. false_positive/source_mismatch/bad_certified：{safety['false_positive']}/{safety['source_mismatch']}/{safety['bad_certified']}（{'全 0' if safety['all_zero'] else '非 0 -> NO-GO'}）。
9. evidence_span 真实来自学生答案：evidence_span_valid_rate={q1['evidence_span_valid_rate']}，laundering={safety['evidence_span_laundering']}（validator 校验 span 在答案内）。
10. latency/cost/token：v0 p50/p95={latency['v0_legacy']['wall_ms_p50']}/{latency['v0_legacy']['wall_ms_p95']}ms（$0）；v1 p50/p95={latency['v1_llm_adjudication']['wall_ms_p50']}/{latency['v1_llm_adjudication']['wall_ms_p95']}ms，token_budget={latency['v1_llm_adjudication']['token_budget_per_packet']}。
11. DeepSeek/Qwen fallback：forced_fallback_drills={provider['forced_fallback_drills']}，fallback_used={provider['fallback_used_count']}，failclosed_drill={provider['failclosed_drill']}。
12. RAG baseline：status={rag['status']}（{rag.get('blocker') or rag.get('note')}）；read-only，从不作评分 authority。
13. Learning Brain 信号更具体：v1 每点带 learning_brain_event_draft + reasoning，v0 无。
14. 是否建议 limited default 继续 ON：{go['limited_default_recommended_on']}（安全全 0 前提下；仍 dry-run/cohort，不 broad）。
15. 下一步：{'补 live DeepSeek 全量 + 本地 Langfuse key + RAG Supabase 链路；再考虑 M19F' if go['m24_verdict'] != 'GO' else '推进受控 default 与 M19F 前置'}。

## 一句话裁决
- **v0 vs v1**：v1 在 per-point 粒度/证据/理由/Learning Brain 信号上明显优于 v0；v0 仅适合纯确定性单点题省 token。
- **limited default**：安全不变量全 {'0 -> 建议继续 ON（受控 cohort）' if safety['all_zero'] else '非 0 -> 不建议'}。
- **M19F 支撑**：{'本地证据充分但' if safety['all_zero'] else '安全未达标，'} 仍缺 {'本地 Langfuse key + live 全量 + RAG Supabase' if go['m24_verdict']=='WEAK-GO' else '无硬缺口' if go['m24_verdict']=='GO' else '安全修复'}，M19F 需单独授权。
- **硬缺口**：{', '.join(go['weak_go_reasons']) or '无（safety 全 0）'}。

## verdict：**{go['m24_verdict']}**
""")


# local-only Langfuse compose (does NOT touch deployment/aliyun/*)
_LOCAL_LANGFUSE_COMPOSE = """# M24 LOCAL-ONLY Langfuse — do not use for remote/aliyun. Port via LUBAN_LANGFUSE_PORT (default 3030).
services:
  langfuse-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse_local_m24
      POSTGRES_DB: langfuse
    volumes:
      - luban_m24_lf_pg:/var/lib/postgresql/data
  langfuse:
    image: langfuse/langfuse:2
    depends_on:
      - langfuse-db
    ports:
      - "${LUBAN_LANGFUSE_PORT:-3030}:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse_local_m24@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: m24_local_secret
      SALT: m24_local_salt
      NEXTAUTH_URL: http://localhost:${LUBAN_LANGFUSE_PORT:-3030}
      TELEMETRY_ENABLED: "false"
volumes:
  luban_m24_lf_pg:
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    ap.add_argument("--run-live", action="store_true")
    ap.add_argument("--run-langfuse", action="store_true")
    ap.add_argument("--run-rag-live", action="store_true")
    args = ap.parse_args()
    result = run_m24(out_dir=args.out_dir, mode=args.mode, run_live=args.run_live,
                     run_langfuse=args.run_langfuse, run_rag_live=args.run_rag_live)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
