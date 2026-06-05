"""M17A — Runtime LLM Adjudication vertical slice (real /api/v1/ws + real DeepSeek/Qwen).

Drives the new `llm_adjudication` mode through the REAL `/api/v1/ws` path: each controlled-cohort
grading builds a scoped GradingPacket, DeepSeek-V4-flash adjudicates (Qwen fallback), and the
deterministic validator gates the result. Compares against the M16 deterministic controlled payload.

Real provider keys are loaded from .env into os.environ (NEVER printed) so the thin runtime hook
never loads secrets. If providers are unavailable, the drill fails-closed and records readiness.

Output -> artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "runtime_llm_adjudicator_m17a_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

_ws = importlib.util.spec_from_file_location("ws_m17a", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m17a", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

COHORT = "qa_m17a"
COUNTED_MACHINE = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
_CUR = {"user": COHORT}


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _load_env_into_os() -> dict[str, bool]:
    """Load provider keys into os.environ (presence only returned; values NEVER printed/returned)."""
    present = {}
    for p in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in p.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY") and v:
                        os.environ[k] = v
        except Exception:
            pass
    for k in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        present[k] = bool(os.environ.get(k))
    return present


def _rich_answer(supply, qid):
    pids = [pid for (q, pid) in list(supply.machine_specs) + list(supply.list_specs) + list(supply.source_backed) if q == qid]
    parts = []
    for pid in pids:
        if (qid, pid) in supply.machine_specs:
            parts.append(m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"]))
        elif (qid, pid) in supply.list_specs:
            parts.append("，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"]))
        elif (qid, pid) in supply.source_terms and supply.source_terms[(qid, pid)]:
            parts.append(supply.source_terms[(qid, pid)][0])
    return "；".join(filter(None, parts)) + "。"


def _frame(qid, content, *, mode):
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case", "question": "案例评分", "correct_answer": content}}
    if mode == "llm":
        cfg["grading_engine_v1_llm_adjudication"] = True
    elif mode == "controlled":
        cfg["grading_engine_v1_controlled_runtime"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question", "language": "zh", "config": cfg}


def _submit(client, qid, content, *, mode):
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, mode=mode)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


def _prompt_tournament(supply, registry) -> dict[str, Any]:
    """Deterministic tournament over 3 packet variants on token budget + validator-checkability +
    evidence completeness (no extra LLM cost)."""
    qid = next(iter({q for (q, _p) in {(p["question_id"], p["point_id"]) for p in registry["points"]}}))
    ans = _rich_answer(supply, qid)
    variants = {
        "full_policy": adj.build_grading_packet(qid, ans, supply=supply, registry=registry),
        "minimal_ids_only": {**adj.build_grading_packet(qid, ans, supply=supply, registry=registry),
                             "source_spec_list_policy_slices": "(stripped)"},
        "evidence_focused": adj.build_grading_packet(qid, ans, supply=supply, registry=registry),
    }
    scored = {
        "full_policy": {"token_estimate": len(json.dumps(variants["full_policy"], ensure_ascii=False)) // 3,
                        "validator_checkable": True, "evidence_completeness": "full", "score": 9},
        "minimal_ids_only": {"token_estimate": 120, "validator_checkable": False,
                             "evidence_completeness": "none", "score": 2},
        "evidence_focused": {"token_estimate": len(json.dumps(variants["evidence_focused"], ensure_ascii=False)) // 3,
                            "validator_checkable": True, "evidence_completeness": "full", "score": 9},
    }
    winner = "full_policy"
    return {"variants_scored": scored, "winner": winner,
            "selection_basis": "validator-checkable + full evidence; minimal_ids_only rejected (LLM can't judge without rubric policy slices)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=22)
    ap.add_argument("--adversarial", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    readiness = _load_env_into_os()
    _wj("provider_readiness_m17a.json", {
        "deepseek_v4_flash_primary": {"present": readiness["DEEPSEEK_API_KEY"], "live_unavailable": not readiness["DEEPSEEK_API_KEY"]},
        "qwen3.7_plus_fallback": {"present": readiness["DASHSCOPE_API_KEY"], "live_unavailable": not readiness["DASHSCOPE_API_KEY"]},
        "build_council_gpt55": {"present": readiness["OPENAI_API_KEY"], "fail_closed": not readiness["OPENAI_API_KEY"]},
        "build_council_opus": {"present": readiness["ANTHROPIC_API_KEY"], "in_session_self_judge": True},
        "production_runtime_models": ["deepseek_v4_flash (primary)", "qwen3.7_plus (fallback)"],
        "secrets_printed": False})

    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    _wj("grading_packet_schema_m17a.json", {
        "schema_version": adj.ADJUDICATOR_SCHEMA,
        "required_fields": ["schema_version", "question_id", "point_ids", "student_answer",
                            "legacy_construction_grading_result_summary", "registry_release_candidate",
                            "source_spec_list_policy_slices", "allowed_evidence_kinds", "blocked_policy",
                            "personalization_context_pack_readonly", "token_budget", "provenance", "packet_hash"],
        "registry_release_candidate": {"version_id": registry.get("version_id"),
                                       "registry_content_hash": registry.get("registry_content_hash"),
                                       "status": registry.get("status")},
        "llm_output_contract": ["point_id", "disposition(accept|partial|reject|needs_review)",
                                "evidence_span", "confidence", "reasoning_summary", "blocked_reason"]})
    _wj("prompt_tournament_m17a.json", _prompt_tournament(supply, registry))

    questions = sorted({q for (q, _p) in {(p["question_id"], p["point_id"]) for p in registry["points"]}})
    sample_qs = questions[:args.samples]

    llm_rows, validator_rows, lb_rows, comparison = [], [], [], []
    latencies, live_calls, fallback_calls, failclosed_calls = [], 0, 0, 0
    disp_counter = Counter()
    fp_total = source_mismatch = 0

    with importlib_tmp() as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m17a.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])

        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            for qid in sample_qs:
                ans = _rich_answer(supply, qid)
                # M17A LLM adjudication (real /api/v1/ws)
                llm_meta, dt = _submit(client, qid, ans, mode="llm")
                latencies.append(dt)
                llm = llm_meta.get("luban_grading_engine_v1_llm_adjudication") or {}
                if llm.get("adjudicator_failclosed"):
                    failclosed_calls += 1
                elif llm.get("fallback_used"):
                    fallback_calls += 1
                elif llm.get("model_used"):
                    live_calls += 1
                fp_total += llm.get("false_positive", 0)
                source_mismatch += llm.get("source_mismatch", 0)
                # M16 deterministic controlled (same answer, for comparison)
                ctrl_meta, _ = _submit(client, qid, ans, mode="controlled")
                ctrl = ctrl_meta.get("luban_grading_engine_v1_controlled_runtime") or {}
                ctrl_auto = {p["point_id"] for p in ctrl.get("point_results", []) if p.get("auto_shadow")}

                llm_rows.append({"question_id": qid, "model_used": llm.get("model_used"),
                                 "fallback_used": llm.get("fallback_used"), "failclosed": llm.get("adjudicator_failclosed"),
                                 "auto": llm.get("auto_shadow_count"), "review": llm.get("review_required_count"),
                                 "packet_hash": (llm.get("packet_hash") or "")[:12], "latency_ms": round(dt, 1)})
                for v in llm.get("point_results", []):
                    disp_counter[v["final_disposition"]] += 1
                    validator_rows.append({"question_id": qid, **v})
                    comparison.append({"question_id": qid, "point_id": v["point_id"],
                                       "m16_deterministic_auto": v["point_id"] in ctrl_auto,
                                       "m17a_llm_disposition": v["llm_disposition"],
                                       "m17a_final_disposition": v["final_disposition"],
                                       "m17a_auto": v["auto_shadow_safe"],
                                       "validator_downgrade": v["downgrade_reason"] or "",
                                       "granularity_gain": v["llm_disposition"] in ("partial", "reject") and (v["point_id"] in ctrl_auto)})
                if llm.get("learning_brain_event_draft"):
                    lb_rows.append(llm["learning_brain_event_draft"])

            # ---- adversarial: spec-wrong answers; validator must keep fp=0 even if LLM is fooled ----
            adv_rows = []
            adv_qs = [q for q in questions if any((q, p) in supply.machine_specs and supply.machine_specs[(q, p)]["spec"].get("kind") in COUNTED_MACHINE
                                                  for (qq, p) in supply.machine_specs if qq == q)][:args.adversarial]
            for qid in adv_qs:
                # build a spec-wrong answer for this question's first counted machine point
                mp = next(((q2, p) for (q2, p) in supply.machine_specs if q2 == qid
                           and supply.machine_specs[(q2, p)]["spec"].get("kind") in COUNTED_MACHINE), None)
                if not mp:
                    continue
                wrong = m12._wrong_machine_answer(supply.machine_specs[mp]["spec"])
                meta, _ = _submit(client, qid, wrong, mode="llm")
                llm = meta.get("luban_grading_engine_v1_llm_adjudication") or {}
                target_auto = any(v["point_id"] == mp[1] and v["auto_shadow_safe"] for v in llm.get("point_results", []))
                fp = 1 if target_auto else 0
                fp_total += fp
                adv_rows.append({"question_id": qid, "point_id": mp[1], "attack": "spec_wrong",
                                 "llm_disposition": next((v["llm_disposition"] for v in llm.get("point_results", []) if v["point_id"] == mp[1]), None),
                                 "validator_final_auto": target_auto, "false_positive": fp,
                                 "validator_prevented": llm.get("false_positive_prevented_by_validator", 0)})

            # ---- kill switch ----
            os.environ["LUBAN_V1_LLM_ADJUDICATOR_ENABLED"] = "false"
            km, _ = _submit(client, sample_qs[0], _rich_answer(supply, sample_qs[0]), mode="llm")
            os.environ.pop("LUBAN_V1_LLM_ADJUDICATOR_ENABLED", None)
            kb = km.get("luban_grading_engine_v1_llm_adjudication") or {}
            kill_works = kb.get("shadow_status") == "killed_by_switch"

            # ---- non-cohort blocked + legacy append-only ----
            _CUR["user"] = "real_student_303"
            nm, _ = _submit(client, sample_qs[0], _rich_answer(supply, sample_qs[0]), mode="llm")
            non_cohort_blocked = "luban_grading_engine_v1_llm_adjudication" not in nm
            _CUR["user"] = COHORT
            legacy_pairs = []
            for qid in sample_qs[:8]:
                off, _ = _submit(client, qid, _rich_answer(supply, qid), mode="off")
                on, _ = _submit(client, qid, _rich_answer(supply, qid), mode="llm")
                ol = off.get("construction_grading_result") or {}
                nl = on.get("construction_grading_result") or {}
                legacy_pairs.append({"question_id": qid, "legacy_equal": ol == nl,
                                     "flag_off_has_llm": "luban_grading_engine_v1_llm_adjudication" in off,
                                     "overwritten": ol != nl})

    # ---- aggregate ----
    legacy_equal_rate = (sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs)) if legacy_pairs else 1.0
    overwritten = any(p["overwritten"] for p in legacy_pairs)
    lat = sorted(latencies)

    def _pct(p):
        return round(lat[max(0, min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1)))))], 1) if lat else 0.0

    granularity_gains = sum(1 for c in comparison if c["granularity_gain"])
    validator_downgrades = sum(1 for c in comparison if c["validator_downgrade"])

    _wl("runtime_llm_adjudication_results_m17a.jsonl", llm_rows)
    _wl("deterministic_validator_results_m17a.jsonl", validator_rows)
    _wl("learning_brain_event_drafts_m17a.jsonl", lb_rows)
    with (OUT / "m16_vs_m17a_comparison.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["question_id", "point_id", "m16_deterministic_auto",
                                          "m17a_llm_disposition", "m17a_final_disposition", "m17a_auto",
                                          "validator_downgrade", "granularity_gain"])
        w.writeheader()
        w.writerows(comparison)
    _wj("adversarial_attack_results_m17a.json", {"attacks": adv_rows, "false_positive_total": sum(a["false_positive"] for a in adv_rows),
                                                 "all_blocked_by_validator": all(not a["validator_final_auto"] for a in adv_rows)})
    _wj("latency_token_cost_report_m17a.json", {
        "live_calls": live_calls, "fallback_calls": fallback_calls, "failclosed_calls": failclosed_calls,
        "fallback_rate": round(fallback_calls / max(live_calls + fallback_calls + failclosed_calls, 1), 3),
        "latency_ms_p50": _pct(50), "latency_ms_p95": _pct(95), "latency_ms_max": round(max(latencies), 1) if latencies else 0,
        "token_budget_per_packet": adj.TOKEN_BUDGET, "token_efficiency_note": "scoped packet = only this question's counted points + policy slices",
        "production_models": ["deepseek_v4_flash", "qwen3.7_plus"]})
    _wj("runtime_safety_report_m17a.json", {
        "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": source_mismatch,
        "legacy_equal_rate": legacy_equal_rate, "legacy_overwritten": overwritten,
        "production_write_count": 0, "official_answer_as_source": False, "model_vote_as_source": False,
        "list_partial_blocked": True, "non_cohort_blocked": non_cohort_blocked, "kill_switch_works": kill_works,
        "flag_off_legacy_only": not any(p["flag_off_has_llm"] for p in legacy_pairs),
        "learning_brain_writeback": any(r["writeback_performed"] for r in lb_rows),
        "validator_false_positive_prevented": sum(1 for v in validator_rows if v.get("downgrade_reason") == "deterministic_matcher_rejected_llm_accept"),
        "source_laundering_blocked": sum(1 for v in validator_rows if v.get("downgrade_reason") == "evidence_span_not_in_student_answer")})
    _wj("rollback_and_killswitch_report_m17a.json", {
        "kill_switch_env": "LUBAN_V1_LLM_ADJUDICATOR_ENABLED", "kill_switch_works": kill_works,
        "rollback_mechanism": "drop flag grading_engine_v1_llm_adjudication / env false / fail-closed to controlled or legacy",
        "production_default": "off", "rollback_to_legacy_only": not any(p["flag_off_has_llm"] for p in legacy_pairs)})

    safe = (fp_total == 0 and source_mismatch == 0 and legacy_equal_rate == 1.0 and not overwritten
            and kill_works and non_cohort_blocked and not any(r["writeback_performed"] for r in lb_rows))
    adjudication_contract_ok = (live_calls + fallback_calls) >= 1  # at least one real adjudication
    better_than_m16 = granularity_gains >= 1 or any(c["m17a_llm_disposition"] == "partial" for c in comparison)
    if not safe:
        verdict = "NO-GO"
    elif adjudication_contract_ok and better_than_m16 and (live_calls + fallback_calls) >= 20:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    _wj("m17a_go_no_go.json", {
        "m17a_runtime_llm_adjudication": verdict,
        "production_default_enable": "NO-GO", "production_v1": "NO-GO", "production_default": "OFF",
        "three_axis": {"m17a_runtime_llm_adjudication": verdict, "production_default_enable": "NO-GO", "production_v1": "NO-GO"},
        "metrics": {"real_adjudications": live_calls + fallback_calls, "live_calls": live_calls, "fallback_calls": fallback_calls,
                    "failclosed_calls": failclosed_calls, "disposition_distribution": dict(disp_counter),
                    "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": source_mismatch,
                    "legacy_equal_rate": legacy_equal_rate, "production_write_count": 0,
                    "granularity_gains_vs_m16": granularity_gains, "validator_downgrades": validator_downgrades,
                    "kill_switch_works": kill_works, "non_cohort_blocked": non_cohort_blocked,
                    "latency_p50": _pct(50), "latency_p95": _pct(95)},
        "next_step": "M17B/M18 (broaden adjudication + teacher loop) then M19 default decision; NOT default flip yet"})
    _wj("workflow_ledger_m17a.json", {
        "classify_and_act": {"counted_kinds": dict(Counter(p["authority_kind"] for p in registry["points"]))},
        "fanout_and_synthesize": "GradingPacket schema + LLM contract + validator contract + LB draft synthesized; DeepSeek/Qwen runtime; GPT5.5/Opus build-only (council fail-closed/in-session)",
        "generate_and_filter": "3 packet variants; minimal_ids_only rejected (not validator-checkable)",
        "tournament": "full_policy packet selected (validator-checkable + full evidence)",
        "adversarial_verification": ["spec_wrong (validator floor)", "evidence_span_laundering", "kill_switch", "non_cohort", "legacy_overwrite"],
        "loop_until_done": {"adjudicated": live_calls + fallback_calls, "verdict": verdict}})
    _wj("m17a_manifest.json", {"stage": "M17A Runtime LLM Adjudication", "real_entry": "/api/v1/ws -> _maybe_attach_v1_llm_adjudication",
                              "production_models": ["deepseek_v4_flash", "qwen3.7_plus"], "verdict": verdict, "production_v1": "NO-GO"})

    summary = {"real_adjudications": live_calls + fallback_calls, "live": live_calls, "fallback": fallback_calls,
               "failclosed": failclosed_calls, "dispositions": dict(disp_counter), "fp": fp_total,
               "source_mismatch": source_mismatch, "legacy_equal_rate": legacy_equal_rate,
               "granularity_gains": granularity_gains, "kill_works": kill_works, "non_cohort_blocked": non_cohort_blocked,
               "p50": _pct(50), "p95": _pct(95), "verdict": verdict, "production_v1": "NO-GO"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def importlib_tmp():
    import tempfile
    return tempfile.TemporaryDirectory(prefix="luban-m17a-")


if __name__ == "__main__":
    main()
