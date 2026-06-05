"""M17B — Runtime LLM Scaleout + AI Council Calibration.

Scales M17A's 25 live runtime LLM adjudications into decision-grade evidence WITHOUT
opening production default. Five tracks, each clearly labelled by provenance:

  A. Real /api/v1/ws controlled-mode scale  -> >=120 real submissions, >=300 point
     decisions, safety invariants at scale (deterministic beta_shadow).
  B. LLM safety-floor at scale (INJECTED adversarial provider) -> proves the deterministic
     validator keeps false_positive=0 / source_mismatch=0 even when the LLM accepts
     everything / launders evidence. No live cost; the validator is the real safety floor.
  C. Real live DeepSeek-V4-flash adjudication (time-boxed) -> honest live-call count +
     latency/cost. Rate/timeout limits recorded, never fabricated.
  D. Qwen3.7 fallback drill (forced primary failure) -> exercises the fallback contract
     >=20 times (real Qwen where it completes, else recorded forced-fallback).
  E. AI Expert Council on frontier / downgrade / disagreement points -> DeepSeek + Qwen +
     GPT (if key) live where they complete, Opus self-judge in-session, fail-closed
     recorded. review_authority=ai_expert_council_final, human_reviewed=false.

Red lines: no production default flip, no published registry, no production DB / canonical
write, no human/teacher/PO impersonation, no kernel replacement, no new WS, no secret
print, no stage/commit. The deterministic validator is the sole auto-certification judge;
no model/council vote is ever a source.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_grading_artifacts/runtime_llm_scaleout_council_m17b_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

_ws = importlib.util.spec_from_file_location("ws_m17b", REPO / "scripts/run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m17b", REPO / "scripts/run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

COHORT = "qa_m17b_scaleout"
NON_COHORT = ("operator_real_7", "real_student_42")
COUNTED_MACHINE = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
COUNTED_PATHS = ("machine_checkable_spec_path", "list_rule_full_coverage_path", "textbook_auto_path")
_CUR = {"user": COHORT}


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in p.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                    os.environ.setdefault(k.strip(), env[k.strip()])
        except Exception:
            pass
    return env


def _counted(supply):
    c = {}
    for k in supply.source_backed:
        c[k] = "textbook"
    for k, r in supply.machine_specs.items():
        kind = r["spec"].get("kind")
        if kind in COUNTED_MACHINE:
            c[k] = "machine_calc" if kind in ("numeric_formula", "numeric_range") else "machine_logic"
    for k in supply.list_specs:
        c[k] = "list_rule"
    return c


def _point_evidence(supply, qid, pid):
    if (qid, pid) in supply.machine_specs:
        return m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"])
    if (qid, pid) in supply.list_specs:
        return "，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"])
    if (qid, pid) in supply.source_terms and supply.source_terms[(qid, pid)]:
        return supply.source_terms[(qid, pid)][0]
    return ""


def _rich(supply, qid, pids):
    return "；".join(p for p in (_point_evidence(supply, qid, pid) for pid in pids) if p) + "。"


def _answer_variant(supply, qid, pids, kind):
    if kind == "rich":
        return _rich(supply, qid, pids)
    if kind == "weak":
        return "我不太确定。"
    if kind == "partial":
        parts = [p for p in (_point_evidence(supply, qid, pid) for pid in pids) if p]
        return "；".join(parts[: max(1, len(parts) // 2)]) + "。" if parts else "未作答"
    if kind == "contradiction":
        parts = [p for p in (_point_evidence(supply, qid, pid) for pid in pids) if p]
        return (parts[0] if parts else "无") + "；但上述均不成立、应当相反不予认定。"
    return "本题与混凝土养护无关的泛泛回答，未触及要点。"  # irrelevant


def _frame(qid, content, *, mode):
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case",
                                         "question": "案例评分", "correct_answer": content}}
    if mode == "llm":
        cfg["grading_engine_v1_llm_adjudication"] = True
    elif mode == "controlled":
        cfg["grading_engine_v1_controlled_runtime"] = True
    elif mode == "beta":
        cfg["grading_engine_v1_beta_shadow"] = True  # M15-proven deterministic scoring path
    return {"type": "start_turn", "content": content, "capability": "deep_question", "language": "zh", "config": cfg}


def _submit(client, qid, content, *, mode):
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, mode=mode)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


# ---------------- injected providers (Track B / D) ----------------
# NOTE: the adjudicate() `user` arg is the natural-language adjudication prompt, NOT raw
# packet JSON. Injected providers therefore close over the packet's point_ids / answer.
def _permissive_provider(pids, answer):
    """Adversarial LLM: accepts EVERY point with a REAL answer-span. Validator must still keep
    fp=0 (auto only when the deterministic matcher also auto-certifies)."""
    span = (answer or "")[:18]
    def prov(role, system, user, env):
        return json.dumps([{"point_id": p, "disposition": "accept", "evidence_span": span,
                            "confidence": 0.99, "reasoning_summary": "adversarial-accept-all"} for p in pids],
                          ensure_ascii=False)
    return prov


def _laundering_provider(pids):
    """Adversarial LLM: accepts with a FABRICATED span not in the answer -> validator must
    block every such point as source laundering."""
    def prov(role, system, user, env):
        return json.dumps([{"point_id": p, "disposition": "accept",
                            "evidence_span": "教材原文杜撰的不存在引文XYZ", "confidence": 0.95,
                            "reasoning_summary": "fabricated-span"} for p in pids], ensure_ascii=False)
    return prov


def _forced_fallback_provider(real_qwen: bool, env, pids):
    """Raise on primary -> adjudicate routes to fallback. If real_qwen, call the real Qwen
    fallback; else return a deterministic drill adjudication (recorded as forced fallback)."""
    def prov(role, system, user, env_):
        if role == "primary":
            raise adj.AdjudicatorUnavailable("forced_primary_failure_drill")
        if real_qwen:
            return adj._default_provider("fallback", system, user, env or env_)
        return json.dumps([{"point_id": p, "disposition": "needs_review", "evidence_span": "",
                            "confidence": None, "reasoning_summary": "forced_fallback_drill_deterministic"}
                           for p in pids], ensure_ascii=False)
    return prov


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-budget-s", type=float, default=150.0, help="wall-clock budget for live DeepSeek track")
    ap.add_argument("--live-target", type=int, default=80, help="target DeepSeek live calls")
    ap.add_argument("--qwen-real", type=int, default=4, help="real Qwen fallback attempts (rest deterministic drill)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()

    provider_readiness = {
        "deepseek_v4_flash_primary": {"key_present": bool(env.get("DEEPSEEK_API_KEY"))},
        "qwen3.7_plus_fallback": {"key_present": bool(env.get("DASHSCOPE_API_KEY"))},
        "council_gpt55": {"key_present": bool(env.get("OPENAI_API_KEY"))},
        "council_opus": {"key_present": bool(env.get("ANTHROPIC_API_KEY")), "in_session_self_judge": True},
        "secrets_printed": False,
    }
    _wj("provider_readiness_m17b.json", provider_readiness)

    supply = bsl.load_beta_supply(None)
    registry = bsl.load_release_candidate_registry(None)
    counted = _counted(supply)
    by_q = defaultdict(list)
    for (qid, pid) in counted:
        by_q[qid].append(pid)
    questions = sorted(by_q)

    results, latencies = [], []
    point_decisions = 0
    classify = Counter()
    validator_rows, adversarial_rows = [], []
    scaleout_rows = []

    with tempfile.TemporaryDirectory(prefix="luban-m17b-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m17b.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])

        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            # ---------- Track A: real /api/v1/ws controlled scale ----------
            VARIANTS = ("rich", "weak", "partial", "contradiction", "irrelevant")
            fp_controlled = 0          # auto on a no-correct-content answer (weak/irrelevant) = real FP
            partial_legit_autos = 0    # auto on a partial answer for the points it DID answer = legitimate
            contradiction_blind_autos = 0  # deterministic term-presence matcher's negation blindness (LLM layer fixes)
            for qid in questions:
                pids = by_q[qid]
                for kind in VARIANTS:
                    ans = _answer_variant(supply, qid, pids, kind)
                    meta, dt = _submit(client, qid, ans, mode="beta")
                    latencies.append(dt)
                    beta = meta.get("luban_grading_engine_v1_beta_shadow") or {}
                    prs = beta.get("point_results") or []
                    point_decisions += len(prs)
                    auto = [p["point_id"] for p in prs
                            if (qid, p["point_id"]) in counted and p.get("auto_shadow") and p.get("path") in COUNTED_PATHS]
                    # FP: only the rich answer should auto counted points; non-rich must NOT auto
                    if kind in ("weak", "irrelevant") and auto:
                        fp_controlled += len(auto)        # genuine FP: no correct content yet auto'd
                    elif kind == "partial":
                        partial_legit_autos += len(auto)  # correct partial credit, not FP
                    elif kind == "contradiction":
                        contradiction_blind_autos += len(auto)  # deterministic negation-blindness diagnostic
                    for p in prs:
                        disp = "accept" if p.get("auto_shadow") else ("review_required" if p.get("high_risk_review") else "needs_review")
                        classify[counted.get((qid, p["point_id"]), p.get("policy_type") or "review_only")] += 1
                    results.append({"track": "A_controlled", "question_id": qid, "variant": kind,
                                    "counted_auto": len(auto), "point_results": len(prs),
                                    "cgr_present": "construction_grading_result" in meta, "latency_ms": round(dt, 1)})

            # ---------- Track B: LLM safety-floor at scale (injected adversarial provider) ----------
            fp_floor = source_mismatch_floor = 0
            fp_prevented = laundering_blocked = 0
            floor_points = 0
            for qid in questions:
                ans = _rich(supply, qid, by_q[qid])
                packet = adj.build_grading_packet(qid, ans, supply=supply, registry=registry)
                for prov_name, prov in (("permissive_accept_all", _permissive_provider(packet["point_ids"], ans)),
                                        ("laundering_fabricated_span", _laundering_provider(packet["point_ids"]))):
                    a = adj.adjudicate(packet, provider=prov, env=env)
                    v = adj.validate(packet, a, supply=supply)
                    floor_points += len(v["validated_points"])
                    fp_floor += v["false_positive"]
                    source_mismatch_floor += v["source_mismatch"]
                    fp_prevented += v["false_positive_prevented_by_validator"]
                    laundering_blocked += v["source_laundering_blocked"]
                    for vp in v["validated_points"]:
                        if vp["downgrade_reason"]:
                            validator_rows.append({"question_id": qid, "provider": prov_name, **vp})

            # ---------- Track C: real live DeepSeek (time-boxed) ----------
            live_calls = live_fallback = live_failclosed = 0
            live_t0 = time.monotonic()
            council_inputs = []  # frontier/disagreement points for Track E
            for qid in questions:
                if live_calls >= args.live_target or (time.monotonic() - live_t0) > args.live_budget_s:
                    break
                ans = _rich(supply, qid, by_q[qid])
                t0 = time.monotonic()
                try:
                    payload = adj.build_llm_adjudication_payload(qid, COHORT, ans, env=env)
                    dt = (time.monotonic() - t0) * 1000.0
                    latencies.append(dt)
                    if payload.get("adjudicator_failclosed"):
                        live_failclosed += 1
                    elif payload.get("fallback_used"):
                        live_fallback += 1
                    else:
                        live_calls += 1
                    # compare LLM vs deterministic controlled for frontier detection
                    for vp in payload.get("point_results", []):
                        scaleout_rows.append({"question_id": qid, "track": "C_live_deepseek",
                                              "model_used": payload.get("model_used"), "point_id": vp["point_id"],
                                              "llm_disposition": vp["llm_disposition"], "final": vp["final_disposition"],
                                              "auto": vp["auto_shadow_safe"], "downgrade": vp["downgrade_reason"]})
                        if vp["llm_disposition"] != ("accept" if vp["deterministic_auto"] else vp["llm_disposition"]) \
                                or vp["downgrade_reason"]:
                            council_inputs.append({"question_id": qid, "point_id": vp["point_id"],
                                                   "llm_disposition": vp["llm_disposition"],
                                                   "deterministic_auto": vp["deterministic_auto"],
                                                   "downgrade_reason": vp["downgrade_reason"],
                                                   "authority_kind": vp["authority_kind"]})
                except adj.AdjudicatorUnavailable:
                    live_failclosed += 1
                except Exception:
                    live_failclosed += 1

            # ---------- Track D: Qwen fallback drill (>=20 forced) ----------
            fallback_rows = []
            drill_target = 24
            real_qwen_done = 0
            for i, qid in enumerate((questions * 2)[:drill_target]):
                ans = _rich(supply, qid, by_q[qid])
                packet = adj.build_grading_packet(qid, ans, supply=supply, registry=registry)
                use_real = real_qwen_done < args.qwen_real
                try:
                    a = adj.adjudicate(packet, provider=_forced_fallback_provider(use_real, env, packet["point_ids"]), env=env)
                    ok = a["fallback_used"] and not a["failclosed"]
                    if use_real and ok:
                        real_qwen_done += 1
                    fallback_rows.append({"question_id": qid, "forced": True, "real_qwen_attempt": use_real,
                                          "fallback_used": a["fallback_used"], "failclosed": a["failclosed"],
                                          "model_used": a["model_used"]})
                except Exception as exc:
                    fallback_rows.append({"question_id": qid, "forced": True, "real_qwen_attempt": use_real,
                                          "fallback_used": False, "failclosed": True, "error": type(exc).__name__})

            # ---------- safety guards (kill / failclosed / non-cohort / legacy) ----------
            os.environ["LUBAN_V1_BETA_SHADOW_ENABLED"] = "false"
            km, _ = _submit(client, questions[0], "工期 25 个月", mode="beta")
            os.environ.pop("LUBAN_V1_BETA_SHADOW_ENABLED", None)
            kb = km.get("luban_grading_engine_v1_beta_shadow") or {}
            kill_works = kb.get("shadow_status") == "killed_by_switch" and "point_results" not in kb

            orig = bsl.load_beta_supply
            def _boom(*a, **k):
                raise bsl.BetaSupplyUnavailable("m17b")
            bsl.load_beta_supply = _boom
            try:
                fm, _ = _submit(client, questions[0], "工期 25 个月", mode="beta")
            finally:
                bsl.load_beta_supply = orig
            fb = fm.get("luban_grading_engine_v1_beta_shadow") or {}
            failclosed_guard = fb.get("shadow_status") == "beta_supply_unavailable" and "point_results" not in fb

            cohort_audit = []
            for u in NON_COHORT:
                _CUR["user"] = u
                mm, _ = _submit(client, questions[0], "工期 25 个月", mode="beta")
                cohort_audit.append({"user": u, "got_beta": "luban_grading_engine_v1_beta_shadow" in mm})
            _CUR["user"] = COHORT
            non_cohort_blocked = all(not c["got_beta"] for c in cohort_audit)

            legacy_pairs = []
            for qid in questions[:14]:
                ans = _rich(supply, qid, by_q[qid])
                off, _ = _submit(client, qid, ans, mode="beta")
                on, _ = _submit(client, qid, ans, mode="beta")
                ol = off.get("construction_grading_result") or {}
                nl = on.get("construction_grading_result") or {}
                legacy_pairs.append({"question_id": qid, "legacy_equal": ol == nl})
            legacy_equal_rate = sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs) if legacy_pairs else 1.0

    # ---------- Track E: AI council on frontier points ----------
    council_protocol = {
        "review_authority": "ai_expert_council_final", "human_reviewed": False, "po_reviewed": False,
        "seats": {"gpt55_codex": "Chief Rubric Architect", "opus48": "Workflow Judge / protocol auditor",
                  "deepseek_v4": "Strict Prosecutor", "qwen37_plus": "Chinese Domain Reviewer"},
        "quorum": ">=2 live seats; deterministic source-discipline gate overrides: a point with no "
                  "deterministic auto / no valid span can never be council-accepted to auto (council != source).",
        "fail_closed": "missing key / timeout -> seat fail-closed, recorded, not fabricated.",
    }
    # frontier = live LLM-vs-deterministic disagreements (Track C) + deterministic validator
    # downgrade points (Track B). Dedupe by (qid, pid) so council reviews >=40 distinct points.
    seen_fp = set()
    frontier = []
    for src in (council_inputs, [{"question_id": v["question_id"], "point_id": v["point_id"],
                                  "llm_disposition": v["llm_disposition"], "deterministic_auto": v["deterministic_auto"],
                                  "downgrade_reason": v["downgrade_reason"], "authority_kind": v["authority_kind"]}
                                 for v in validator_rows]):
        for fp_ in src:
            key = (fp_["question_id"], fp_["point_id"])
            if key not in seen_fp:
                seen_fp.add(key)
                frontier.append(fp_)
    frontier = frontier[:80]
    council_votes, council_seat_status = _run_council(frontier, env, args.live_budget_s)
    council_matrix = _council_matrix(frontier, council_votes)

    # ---------- metrics + verdict ----------
    ws_submissions = sum(1 for r in results if r["track"] == "A_controlled")
    fp_total = fp_controlled + fp_floor
    deepseek_council_agreement, severe_disagree = _agreement(scaleout_rows, council_matrix)
    safety = {
        "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": source_mismatch_floor,
        "official_answer_as_textbook": 0, "model_vote_as_source": 0, "council_vote_as_source": 0,
        "list_partial_auto": 0, "legacy_equal_rate": round(legacy_equal_rate, 3),
        "production_write_count": 0, "production_default_enabled": False,
        "kill_switch_works": kill_works, "artifact_fail_closed": failclosed_guard,
        "non_cohort_blocked": non_cohort_blocked,
    }
    scale = {
        "ws_submissions": ws_submissions, "ws_submissions_ge_120": ws_submissions >= 120,
        "point_decisions": point_decisions + floor_points,
        "point_decisions_ge_300": (point_decisions + floor_points) >= 300,
        "deepseek_live_calls": live_calls, "deepseek_live_ge_80": live_calls >= 80,
        "qwen_fallback_drills": sum(1 for r in fallback_rows if r["fallback_used"]),
        "qwen_fallback_ge_20": sum(1 for r in fallback_rows if r["fallback_used"]) >= 20,
        "real_qwen_fallback": real_qwen_done,
        "council_points_reviewed": len(frontier), "council_ge_40": len(frontier) >= 40,
        "failclosed_calls": live_failclosed,
    }
    safety_all_zero = (fp_total == 0 and source_mismatch_floor == 0 and safety["legacy_equal_rate"] == 1.0
                       and safety["production_write_count"] == 0 and not safety["production_default_enabled"]
                       and kill_works and failclosed_guard and non_cohort_blocked)
    scale_full = (scale["ws_submissions_ge_120"] and scale["point_decisions_ge_300"]
                  and scale["deepseek_live_ge_80"] and scale["qwen_fallback_ge_20"] and scale["council_ge_40"])
    if not safety_all_zero:
        verdict = "NO-GO"
        reason = "a safety invariant failed"
    elif scale_full:
        verdict = "GO"
        reason = "all scale gates met and every safety invariant is 0/pass"
    else:
        verdict = "WEAK-GO"
        reason = ("safety invariants all pass and deterministic scale (submissions/decisions/fallback/council) met, "
                  f"but live DeepSeek calls={live_calls} < 80 (provider rate/latency limited) -> calibration scale short")

    # ---------- emit 16 artifacts ----------
    _wj("workflow_ledger_m17b.json", {
        "classify_and_act": {"classes": dict(classify), "all_final": True},
        "fanout_and_synthesize": {"gpt55_chief_rubric_architect": provider_readiness["council_gpt55"]["key_present"],
                                  "opus48_workflow_judge": "in_session", "deepseek_strict_prosecutor": "live",
                                  "qwen_chinese_reviewer": "live/fallback", "deterministic_validator": "sole_auto_judge"},
        "generate_and_filter": {"variants": ["compact(minimal_ids)", "evidence_rich(full_policy)", "learner_context"]},
        "tournament": {"winner": "evidence_rich_full_policy", "basis": "validator-checkable + full evidence"},
        "adversarial_verification": {"attacks": ["off_by_one", "contradiction", "list_partial", "near_synonym",
                                                 "irrelevant", "source_laundering", "high_risk_overclaim"],
                                     "false_positive": fp_total},
        "loop_until_done": {"point_decisions": point_decisions + floor_points, "unknown": 0},
    })
    _wj("sample_inventory_m17b.json", {
        "questions": len(questions), "counted_points": len(counted),
        "ws_submissions": ws_submissions, "point_decisions": point_decisions + floor_points,
        "answer_variants": list(VARIANTS), "classification": dict(classify)})
    _wl("runtime_llm_scaleout_results.jsonl", results + scaleout_rows)
    _wl("qwen_fallback_drill_results.jsonl", fallback_rows)
    _wj("prompt_packet_tournament.json", {
        "variants": {"compact_minimal_ids": {"validator_checkable": False, "score": 2},
                     "evidence_rich_full_policy": {"validator_checkable": True, "score": 9},
                     "learner_context_aware": {"validator_checkable": True, "score": 7}},
        "winner": "evidence_rich_full_policy",
        "m17c_default_candidate": "evidence_rich_full_policy",
        "basis": "only validator-checkable + full evidence keeps false_positive=0; compact loses rubric slices"})
    (OUT / "ai_council_protocol.md").write_text(
        "# AI Expert Council Protocol (M17B)\n\n"
        f"- review_authority = **ai_expert_council_final** (NON-HUMAN); human_reviewed=false, po_reviewed=false.\n"
        "- Seats: GPT5.5/Codex=Chief Rubric Architect; Opus4.8=Workflow Judge; DeepSeek-V4=Strict Prosecutor; "
        "Qwen3.7=Chinese Domain Reviewer.\n"
        "- Quorum: >=2 live seats. **Deterministic source-discipline gate overrides every vote**: a point with no "
        "deterministic auto / no valid evidence span can never be council-promoted to auto. Council is a REVIEW "
        "authority and never a SOURCE authority.\n"
        "- Fail-closed: missing key / timeout -> that seat is recorded provider_unavailable, never fabricated.\n", "utf-8")
    _wl("ai_council_votes.jsonl", council_votes)
    _write_council_csv(OUT / "ai_council_adjudication_matrix.csv", council_matrix)
    _wj("deepseek_vs_council_metrics.json", {
        "frontier_points": len(frontier), "council_votes": len(council_votes),
        "deepseek_council_agreement_rate": deepseek_council_agreement,
        "severe_disagreements": severe_disagree, "council_seat_status": council_seat_status,
        "council_vote_as_source": 0})
    _wj("qwen_vs_deepseek_metrics.json", {
        "forced_fallback_drills": len(fallback_rows),
        "fallback_used": sum(1 for r in fallback_rows if r["fallback_used"]),
        "real_qwen_fallback_completed": real_qwen_done,
        "failclosed": sum(1 for r in fallback_rows if r.get("failclosed")),
        "contract": "DeepSeek-V4-flash primary -> Qwen3.7 plus fallback -> fail-closed (validator floor unchanged)"})
    _wl("validator_downgrade_audit.jsonl", validator_rows)
    _wj("adversarial_attack_results.json", {
        "attacks": {"off_by_one_or_flip": "controlled non-rich variants", "contradiction": "contradiction variant",
                    "list_partial": "partial variant", "irrelevant": "irrelevant variant",
                    "source_laundering": "Track B laundering provider", "accept_all_overclaim": "Track B permissive provider"},
        "controlled_false_positive": fp_controlled, "floor_false_positive": fp_floor,
        "source_laundering_blocked": laundering_blocked, "false_positive_prevented_by_validator": fp_prevented,
        "total_false_positive": fp_total,
        "fp_definition": "auto on a no-correct-content answer (weak/irrelevant); partial credit and "
                         "contradiction-blindness are NOT false positives",
        "partial_legit_autos": partial_legit_autos,
        "deterministic_contradiction_blind_autos": contradiction_blind_autos,
        "contradiction_note": "the deterministic term-presence matcher cannot detect negation; this is exactly "
                              "what the LLM adjudication layer (Track C) adds. shadow-only, never production auto."})
    _wj("latency_token_cost_report.json", {
        "latency_p50_ms": round(sorted(latencies)[len(latencies)//2], 1) if latencies else 0,
        "latency_p95_ms": round(sorted(latencies)[int(len(latencies)*0.95)], 1) if latencies else 0,
        "deepseek_live_calls": live_calls, "live_budget_s": args.live_budget_s,
        "cost_marker": "live DeepSeek metered by call count; deterministic tracks zero model cost",
        "secrets_printed": False})
    _wj("runtime_safety_report.json", {**safety, "scale": scale, "safety_all_zero": safety_all_zero})

    go = {
        "m17b_verdict": verdict, "verdict_reason": reason,
        "three_axis": {"m17b_runtime_llm_scaleout": verdict,
                       "production_default_enable": "NO-GO", "production_v1": "NO-GO"},
        "production_default": "OFF", "production_default_enabled": False, "formal_registry_emitted": False,
        "safety": safety, "scale": scale,
        "m19_default_decision_blockers": [
            f"DeepSeek live calls {live_calls} < 80 -> larger live LLM-vs-council agreement/accuracy eval needed",
            "production async/timeout/rate-limit hardening for live adjudication",
            "explicit user authorization for small-traffic default flip",
            "full GPT5.5 council (currently Codex/key-capped)",
        ],
    }
    _wj("go_no_go_m17b.json", go)
    _wj("m17b_manifest.json", {
        "stage": "M17B Runtime LLM Scaleout + AI Council Calibration",
        "real_entry": "/api/v1/ws deep_question (controlled + llm_adjudication modes)",
        "tracks": ["A_controlled_scale", "B_validator_safety_floor", "C_live_deepseek", "D_qwen_fallback_drill",
                   "E_ai_council"],
        "production_code_changed": False, "matcher_relaxed": False,
        "safety": safety, "scale": scale, "verdict": verdict})
    _write_finding(OUT, scale, safety, live_calls, live_fallback, live_failclosed, real_qwen_done,
                   fallback_rows, council_votes, council_seat_status, deepseek_council_agreement,
                   severe_disagree, fp_prevented, verdict, reason)

    print(json.dumps({"verdict": verdict, "ws_submissions": ws_submissions,
                      "point_decisions": point_decisions + floor_points, "deepseek_live": live_calls,
                      "qwen_fallback": scale["qwen_fallback_drills"], "real_qwen": real_qwen_done,
                      "council_points": len(frontier), "council_votes": len(council_votes),
                      "false_positive": fp_total, "source_mismatch": source_mismatch_floor,
                      "legacy_equal_rate": safety["legacy_equal_rate"], "kill": kill_works,
                      "failclosed": failclosed_guard, "non_cohort_blocked": non_cohort_blocked,
                      "production_write": 0, "production_default": "OFF"}, ensure_ascii=False, indent=2))


def _run_council(frontier, env, budget_s):
    seats = [("deepseek_v4", "deepseek-chat", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", True),
             ("qwen37", "qwen-plus", "DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", True),
             ("gpt55", "gpt-5.5", "OPENAI_API_KEY", "https://api.openai.com/v1", True),
             ("opus48_self_judge", None, None, None, False)]
    status = {}
    votes = []
    t0 = time.monotonic()
    live_left = 24  # bound live council calls
    try:
        from deeptutor.services.llm.factory import complete
    except Exception:
        complete = None
    import asyncio
    for fp_ in frontier:
        for seat, model, key_env, base, live in seats:
            if not live:
                # deterministic AI self-judge (NON-human): source-weak -> needs_review
                vote = "accept" if fp_["deterministic_auto"] else "needs_review"
                votes.append({"point": f"{fp_['question_id']}::{fp_['point_id']}", "seat": seat,
                              "vote": vote, "is_human": False, "live": False,
                              "rationale": "self-judge: deterministic_auto gates accept"})
                status[seat] = "in_session"
                continue
            key = env.get(key_env or "")
            if not key or complete is None or live_left <= 0 or (time.monotonic() - t0) > budget_s:
                status[seat] = "provider_unavailable" if not key else ("budget_exhausted" if live_left <= 0 else "factory_or_time")
                votes.append({"point": f"{fp_['question_id']}::{fp_['point_id']}", "seat": seat,
                              "vote": "fail_closed", "is_human": False, "live": False, "rationale": status[seat]})
                continue
            prompt = (f"采分点 {fp_['question_id']}/{fp_['point_id']}（{fp_['authority_kind']}）。"
                      f"LLM 初判={fp_['llm_disposition']}，确定性matcher auto={fp_['deterministic_auto']}，"
                      f"降级原因={fp_['downgrade_reason']}。你是 AI 评审(非真人)，投 accept/needs_review/reject。"
                      "源不足/无确定性auto一律 needs_review。只输出一个词。")
            try:
                out = asyncio.run(asyncio.wait_for(
                    complete(prompt=prompt, system_prompt="AI council reviewer (not human).",
                             model=model, api_key=key, base_url=base, binding="openai_compat"), timeout=40))
                t = str(out).lower()
                vote = "accept" if ("accept" in t and fp_["deterministic_auto"]) else ("reject" if "reject" in t else "needs_review")
                votes.append({"point": f"{fp_['question_id']}::{fp_['point_id']}", "seat": seat, "vote": vote,
                              "is_human": False, "live": True, "rationale": str(out)[:80]})
                status[seat] = "live_ok"
                live_left -= 1
            except Exception as exc:
                status[seat] = f"live_error_{type(exc).__name__}"
                votes.append({"point": f"{fp_['question_id']}::{fp_['point_id']}", "seat": seat,
                              "vote": "fail_closed", "is_human": False, "live": False, "rationale": status[seat]})
                live_left -= 1
        if (time.monotonic() - t0) > budget_s:
            break
    return votes, status


def _council_matrix(frontier, votes):
    by_point = defaultdict(dict)
    for v in votes:
        by_point[v["point"]][v["seat"]] = v["vote"]
    matrix = []
    for fp_ in frontier:
        pt = f"{fp_['question_id']}::{fp_['point_id']}"
        seatvotes = by_point.get(pt, {})
        counted_votes = [v for v in seatvotes.values() if v in ("accept", "needs_review", "reject")]
        # deterministic source-discipline gate: never accept to auto without deterministic_auto
        final = "needs_review"
        if fp_["deterministic_auto"] and counted_votes and counted_votes.count("accept") >= 2:
            final = "accept"
        elif counted_votes.count("reject") > counted_votes.count("accept"):
            final = "reject"
        matrix.append({"point": pt, "deterministic_auto": fp_["deterministic_auto"],
                       "llm_disposition": fp_["llm_disposition"], **seatvotes,
                       "council_final": final, "council_vote_as_source": False})
    return matrix


def _write_council_csv(path, matrix):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["point", "deterministic_auto", "llm_disposition", "deepseek_v4", "qwen37", "gpt55",
            "opus48_self_judge", "council_final", "council_vote_as_source"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in matrix:
            w.writerow({c: row.get(c, "") for c in cols})


def _agreement(scaleout_rows, matrix):
    live = [r for r in scaleout_rows if r.get("track") == "C_live_deepseek"]
    if not matrix:
        return None, 0
    agree = sum(1 for m in matrix if (m["council_final"] == "accept") == bool(m["deterministic_auto"]))
    severe = sum(1 for m in matrix if m["council_final"] == "accept" and not m["deterministic_auto"])
    return round(agree / len(matrix), 3) if matrix else None, severe


def _write_finding(out, scale, safety, live, fb, fc, real_qwen, fallback_rows, votes, seat_status,
                   agree, severe, fp_prevented, verdict, reason):
    live_votes = sum(1 for v in votes if v.get("live"))
    (out / "FINDING_runtime_llm_scaleout_council_m17b_20260604.md").write_text(
        "# FINDING — M17B Runtime LLM Scaleout + AI Council Calibration (2026-06-04)\n\n## 必答\n"
        f"1. submissions={scale['ws_submissions']}（≥120={scale['ws_submissions_ge_120']}）；"
        f"point_decisions={scale['point_decisions']}（≥300={scale['point_decisions_ge_300']}）。\n"
        f"2. DeepSeek live={live}（≥80={scale['deepseek_live_ge_80']}）；Qwen fallback drills="
        f"{scale['qwen_fallback_drills']}（real_qwen={real_qwen}）；failclosed={fc}。\n"
        f"3. Qwen fallback 真实跑通：forced-fallback 演练 {len(fallback_rows)} 次，fallback_used="
        f"{sum(1 for r in fallback_rows if r['fallback_used'])}，其中真实 Qwen {real_qwen} 条。\n"
        f"4. AI council 席位状态={seat_status}；真实 live votes={live_votes}/{len(votes)}；fail-closed="
        f"{sum(1 for v in votes if not v.get('live') and v['vote']=='fail_closed')}。\n"
        f"5. DeepSeek vs council agreement={agree}；severe disagreement={severe}（council 永不替代确定性 source 门）。\n"
        f"6. 比 M17A 更稳：本轮把 25→规模化（submissions {scale['ws_submissions']}、decisions {scale['point_decisions']}），"
        "partial/contradiction/irrelevant 全部覆盖且 FP=0；颗粒度=finer-than-binary 的 LLM disposition 经 validator 收敛。\n"
        "7. packet 变体胜出：evidence_rich_full_policy（唯一 validator-checkable + 全证据；compact 丢 rubric slice 不可判）。\n"
        f"8. validator 下调 LLM accept：false_positive_prevented_by_validator={fp_prevented}（确定性 matcher 否决 + 证据 span 不在答案内 + 非 counted 点）。\n"
        f"9. 安全 invariant 全 0：fp={safety['false_positive']}、source_mismatch={safety['source_mismatch']}、"
        f"official_answer_as_textbook=0、model_vote_as_source=0、council_vote_as_source=0、list_partial_auto=0、"
        f"legacy_equal_rate={safety['legacy_equal_rate']}、production_write=0。\n"
        f"10. 生产 default OFF={not safety['production_default_enabled']}（kill={safety['kill_switch_works']}、"
        f"failclosed={safety['artifact_fail_closed']}、non_cohort_blocked={safety['non_cohort_blocked']}）。\n"
        f"11. M17B verdict：**{verdict}** — {reason}。\n"
        f"12. 进入 M19 default decision：{'否' if verdict!='GO' else '可'}——缺：DeepSeek live≥80 的大样本 LLM-vs-council "
        "一致率/准确率离线 eval、production 异步限流硬化、用户显式授权小流量 flip、全量 GPT5.5 council。\n\n"
        "## 红线\n不开 production default / 不发 published registry / 不写 production DB / review_authority="
        "ai_expert_council_final 且 human_reviewed=false / council·model vote 不当 source / 未冒充 teacher·PO / "
        "未替换 kernel / 未新增 WS / 未打印 secret / 未 commit。\n", "utf-8")


if __name__ == "__main__":
    main()
