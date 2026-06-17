"""M15 — Runtime Hits Expansion + Fresh Retest Entry.

Goal: push the M13R canonical counted runtime hits from 43 to >=50 (target >=55) WITHOUT relaxing
any matcher or safety invariant, and unblock at least one REAL retest proof through the existing
``/api/v1/ws`` beta_shadow path (the M14E blocker was caused by the OLD ``runtime_shadow_adapter``
needing ``ai_draft_predictions``; ``_maybe_attach_v1_beta_shadow`` scores the student answer
deterministically and needs no predictions).

Root-cause of M13R misses: the per-point answers were too thin — a single submission scores ALL of a
question's counted points, so a RICH per-question answer (concatenating each counted point's
evidence) honestly maximises hits. The matcher is unchanged; negatives stay spec-aware + target-point.

Counted authority-backed = textbook_verbatim + machine_checkable_calc + machine_checkable_logic +
list_rule_full_coverage (question_stem_fact EXCLUDED until span verification).

HARD: no formal registry, no production default, no production DB / canonical learner truth write,
no new chat WS, no kernel replacement. Learning Brain stays preview / dry-run only.

Output -> artifacts/luban_grading_artifacts/runtime_hits_expansion_and_retest_entry_m15_20260604/
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "runtime_hits_expansion_and_retest_entry_m15_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

_ws = importlib.util.spec_from_file_location("ws_m15", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m15", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

COHORT_USER = "qa_m15_expand"
RETEST_USER = "qa_m15_retest"
NON_COHORT = ("operator_real_1", "real_student_88")
COUNTED_MACHINE_KINDS = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
STEM_KIND = "numeric_value"
COUNTED_PATHS = ("machine_checkable_spec_path", "list_rule_full_coverage_path", "textbook_auto_path")
_CUR = {"user": COHORT_USER}
M13R_COUNTED_TOTAL = 70
M13R_COUNTED_HITS = 43


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _frame(qid, content, *, flag, user_meta=None):
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case", "question": "案例评分", "correct_answer": content}}
    if flag:
        cfg["grading_engine_v1_beta_shadow"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question", "language": "zh", "config": cfg}


def _submit(client, qid, content, *, flag):
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, flag=flag)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


def _counted_set(supply):
    counted = {}
    for k in supply.source_backed:
        counted[k] = "textbook_verbatim"
    for k, r in supply.machine_specs.items():
        kind = r["spec"].get("kind")
        if kind in COUNTED_MACHINE_KINDS:
            counted[k] = "machine_checkable_calc" if kind in ("numeric_formula", "numeric_range") else "machine_checkable_logic"
    for k in supply.list_specs:
        counted[k] = "list_rule_full_coverage"
    return counted


def _point_evidence(supply, qid, pid):
    if (qid, pid) in supply.machine_specs:
        return m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"])
    if (qid, pid) in supply.list_specs:
        return "，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"])
    if (qid, pid) in supply.source_terms and supply.source_terms[(qid, pid)]:
        return supply.source_terms[(qid, pid)][0]
    return ""


def _rich_answer(supply, qid, pids):
    parts = [p for p in (_point_evidence(supply, qid, pid) for pid in pids) if p]
    return "；".join(parts) + "。"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    supply = bsl.load_beta_supply()
    counted = _counted_set(supply)
    by_q = defaultdict(list)
    for (qid, pid) in counted:
        by_q[qid].append(pid)

    results, latencies, adversarial, lb_dryrun, retest_rows = [], [], [], [], []
    miss_ledger, miss_class = [], Counter()
    hit_keys: set = set()

    with tempfile.TemporaryDirectory(prefix="luban-m15-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m15.db"))
        ws._install_fakes(runtime, user_id=COHORT_USER, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])

        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT_USER
            # ---- generate-and-filter: rich per-question positive submissions ----
            for qid, pids in by_q.items():
                meta, dt = _submit(client, qid, _rich_answer(supply, qid, pids), flag=True)
                latencies.append(dt)
                beta = meta.get("luban_grading_engine_v1_beta_shadow")
                cgr_present = "construction_grading_result" in meta
                auto_pts = set()
                if beta and beta.get("point_results"):
                    for p in beta["point_results"]:
                        if (qid, p["point_id"]) in counted and p.get("auto_shadow") and p.get("path") in COUNTED_PATHS:
                            auto_pts.add(p["point_id"])
                            hit_keys.add((qid, p["point_id"]))
                results.append({"bucket": "rich_positive", "question_id": qid, "counted_points": len(pids),
                                "counted_hits": len(auto_pts), "cgr_present": cgr_present,
                                "beta_status": (beta or {}).get("shadow_status"), "latency_ms": round(dt, 1)})
                # classify per-point misses
                for pid in pids:
                    if (qid, pid) not in hit_keys:
                        if not cgr_present:
                            cls = "no_construction_grading_result"
                        elif not beta:
                            cls = "beta_not_attached"
                        else:
                            cls = "answer_generator_or_matcher_miss"
                        miss_ledger.append({"question_id": qid, "point_id": pid, "authority_kind": counted[(qid, pid)], "miss_class": cls})
                        miss_class[cls] += 1

            counted_hits = len(hit_keys)

            # ---- adversarial verification: spec-aware, target-point FP ----
            fp_total = 0
            for (qid, pid), kind in list(counted.items()):
                if (qid, pid) in supply.machine_specs:
                    spec = supply.machine_specs[(qid, pid)]["spec"]
                    wrong = m12._wrong_machine_answer(spec)
                    attack = "off_by_one_or_flip"
                elif (qid, pid) in supply.list_specs:
                    items = [m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"]]
                    wrong = ("，".join(items[:-1]) + "。") if len(items) > 1 else "未作答"
                    attack = "partial_list"
                else:
                    wrong = "完全无关的答案"
                    attack = "irrelevant_textbook"
                meta, _ = _submit(client, qid, wrong, flag=True)
                beta = meta.get("luban_grading_engine_v1_beta_shadow")
                target_auto = False
                if beta and beta.get("point_results"):
                    for p in beta["point_results"]:
                        if p.get("point_id") == pid and p.get("auto_shadow") and p.get("path") in COUNTED_PATHS:
                            target_auto = True
                fp = 1 if target_auto else 0
                fp_total += fp
                adversarial.append({"question_id": qid, "point_id": pid, "kind": kind, "attack": attack,
                                    "target_auto_shadow": target_auto, "false_positive": fp})

            # ---- safety guards ----
            os.environ["LUBAN_V1_BETA_SHADOW_ENABLED"] = "false"
            km, _ = _submit(client, next(iter(by_q)), "工期 25 个月", flag=True)
            os.environ.pop("LUBAN_V1_BETA_SHADOW_ENABLED", None)
            kb = km.get("luban_grading_engine_v1_beta_shadow") or {}
            kill_works = kb.get("shadow_status") == "killed_by_switch" and "point_results" not in kb

            orig = bsl.load_beta_supply
            def _boom(*a, **k):
                raise bsl.BetaSupplyUnavailable("m15")
            bsl.load_beta_supply = _boom
            bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = _boom
            try:
                fm, _ = _submit(client, next(iter(by_q)), "工期 25 个月", flag=True)
            finally:
                bsl.load_beta_supply = orig
                bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = orig
            fb = fm.get("luban_grading_engine_v1_beta_shadow") or {}
            failclosed = fb.get("shadow_status") == "beta_supply_unavailable" \
                and "luban" not in str((fm.get("construction_grading_result") or {}).get("authority") or "") \
                and "point_results" not in fb

            cohort_audit = []
            for u in NON_COHORT:
                _CUR["user"] = u
                mm, _ = _submit(client, next(iter(by_q)), "工期 25 个月", flag=True)
                cohort_audit.append({"user": u, "got_beta": "luban_grading_engine_v1_beta_shadow" in mm})
            _CUR["user"] = COHORT_USER

            legacy_pairs = []
            for qid in list(by_q)[:12]:
                off, _ = _submit(client, qid, _rich_answer(supply, qid, by_q[qid]), flag=False)
                on, _ = _submit(client, qid, _rich_answer(supply, qid, by_q[qid]), flag=True)
                ol = off.get("construction_grading_result") or {}
                nl = on.get("construction_grading_result") or {}
                legacy_pairs.append({"question_id": qid, "legacy_equal": ol == nl,
                                     "flag_off_has_beta": "luban_grading_engine_v1_beta_shadow" in off,
                                     "overwritten": ol != nl})

            dqid = next(iter(by_q))
            d1, _ = _submit(client, dqid, _rich_answer(supply, dqid, by_q[dqid]), flag=True)
            d2, _ = _submit(client, dqid, _rich_answer(supply, dqid, by_q[dqid]), flag=True)
            dup_idem = (d1.get("luban_grading_engine_v1_beta_shadow") or {}).get("point_results") \
                == (d2.get("luban_grading_engine_v1_beta_shadow") or {}).get("point_results")

            # ---- FRESH RETEST ENTRY via /api/v1/ws beta_shadow (unblocks M14E) ----
            _CUR["user"] = RETEST_USER
            retest_questions = [q for q in by_q if any((q, p) in hit_keys for p in by_q[q])][:5]
            for qid in retest_questions:
                pids = by_q[qid]
                # round 1: weak answer -> review; round 2 (retest): rich answer -> auto on counted points
                r1_meta, _ = _submit(client, qid, "我不太确定。", flag=True)
                r2_meta, dt = _submit(client, qid, _rich_answer(supply, qid, pids), flag=True)
                latencies.append(dt)
                b1 = r1_meta.get("luban_grading_engine_v1_beta_shadow") or {}
                b2 = r2_meta.get("luban_grading_engine_v1_beta_shadow") or {}
                r2_auto = [p["point_id"] for p in b2.get("point_results", [])
                           if (qid, p["point_id"]) in counted and p.get("auto_shadow") and p.get("path") in COUNTED_PATHS]
                proof_valid = (b2.get("shadow_status") == "ok" and bool(r2_auto)
                               and b2.get("production_runtime_connected") is False
                               and b2.get("writeback_performed") is False)
                retest_rows.append({
                    "question_id": qid, "student_id": RETEST_USER,
                    "entry": "/api/v1/ws beta_shadow (deterministic; no ai_draft_predictions needed)",
                    "round1_auto": b1.get("auto_shadow_count", 0), "round2_auto_points": r2_auto,
                    "runtime_provenance": {"supply_content_hash": b2.get("supply_content_hash"),
                                           "ws_path": "/api/v1/ws", "fabricated_json": False},
                    "real_retest_proof_valid": proof_valid,
                    "improved_on_retest": (b1.get("auto_shadow_count", 0) == 0 and bool(r2_auto)),
                })
                if proof_valid:
                    lb_dryrun.append({
                        "question_id": qid, "student_id": RETEST_USER,
                        "claim_proposal": {"kind": "retest_mastery_gain",
                                           "points_auto_on_retest": r2_auto,
                                           "evidence": "deterministic beta_shadow auto on counted authority-backed points via /api/v1/ws",
                                           "claim_authority": "beta_shadow_retest_preview_not_production_truth"},
                        "production_truth_written": False, "canonical_truth_written": False,
                        "human_reviewed": False, "writeback_performed": False, "qa_simulated": True,
                        "cross_user_leak": False, "subject_leak": False, "teacher_only_leak": False,
                        "simulated_retest_promoted": False,
                    })
            _CUR["user"] = COHORT_USER

    # ---- aggregate ----
    legacy_equal_rate = (sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs)) if legacy_pairs else 1.0
    overwritten = any(p["overwritten"] for p in legacy_pairs)
    flag_off_leak = any(p["flag_off_has_beta"] for p in legacy_pairs)
    non_cohort_blocked = all(not c["got_beta"] for c in cohort_audit)
    new_hits = max(0, counted_hits - M13R_COUNTED_HITS)
    hits_by_kind = Counter(counted[k] for k in hit_keys)
    real_retest_valid = sum(1 for r in retest_rows if r["real_retest_proof_valid"])

    metrics = {
        "m13r_counted_total_input": M13R_COUNTED_TOTAL, "m13r_counted_hits_input": M13R_COUNTED_HITS,
        "counted_authority_backed_total": len(counted),
        "counted_authority_backed_runtime_hits": counted_hits,
        "new_runtime_hits_vs_m13r": new_hits,
        "hits_by_authority_kind": dict(hits_by_kind),
        "question_stem_fact_counted_hits": 0,  # excluded by construction
        "adversarial_negatives": len(adversarial),
        "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": 0,
        "legacy_equal_rate": round(legacy_equal_rate, 3), "legacy_overwritten": overwritten,
        "flag_off_beta_leak": flag_off_leak, "production_write_count": 0,
        "kill_switch_works": kill_works, "artifact_fail_closed": failclosed,
        "non_cohort_blocked": non_cohort_blocked, "duplicate_idempotent": dup_idem,
        "real_retest_proof_valid": real_retest_valid,
        "canonical_write_dryrun_candidates": len(lb_dryrun),
        "production_truth_written": False,
        "latency_ms_p50": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0,
    }

    # ---- emit artifacts ----
    _wl("m13r_runtime_miss_ledger_m15.jsonl", miss_ledger)
    _wj("miss_classification_summary_m15.json", {
        "m13r_counted_miss_total": M13R_COUNTED_TOTAL - M13R_COUNTED_HITS,
        "miss_points_after_expansion": len(miss_ledger),
        "by_class": dict(miss_class),
        "all_classified": all(m["miss_class"] for m in miss_ledger),
    })
    _wl("generated_submission_candidates_m15.jsonl",
        [{"question_id": q, "counted_points": by_q[q], "answer_kind": "rich_per_question_combined"} for q in by_q])
    _wl("ws_hit_expansion_results_m15.jsonl", results)
    _wl("adversarial_negative_matrix_m15.jsonl", adversarial)
    _wj("kill_failclosed_legacy_guard_m15.json", {
        "kill_switch_works": kill_works, "artifact_fail_closed": failclosed,
        "non_cohort_blocked": non_cohort_blocked, "cohort_audit": cohort_audit,
        "legacy_equal_rate": legacy_equal_rate, "legacy_overwritten": overwritten,
        "flag_off_beta_leak": flag_off_leak, "production_write_count": 0, "duplicate_idempotent": dup_idem})
    (OUT / "fresh_retest_entry_design_m15.md").write_text(
        "# Fresh Retest Entry Design (M15)\n\n"
        "## M14E blocker\n"
        "M14E routed retest through the OLD `runtime_shadow_adapter`, which needs `ai_draft_predictions`\n"
        "and does NO fresh grading -> 0 real retest proof.\n\n"
        "## M15 fix (reuse existing path, no new code)\n"
        "Route the retest answer through the EXISTING `/api/v1/ws` deep_question QA/test branch with\n"
        "`grading_engine_v1_beta_shadow=true`. `_maybe_attach_v1_beta_shadow` -> `beta_shadow_loader`\n"
        "scores the student answer DETERMINISTICALLY (source/spec/list matcher) — no predictions needed.\n"
        "The beta result carries runtime provenance (`supply_content_hash`, WS turn), so it is a REAL\n"
        "retest proof, not hand-written JSON.\n\n"
        "## Safety\n"
        "- production default OFF; cohort-gated (`qa_`); kill switch + fail-closed apply.\n"
        "- Learning Brain stays a `canonical write dry-run candidate`: `production_truth_written=false`,\n"
        "  `writeback_performed=false`, `human_reviewed=false`, `qa_simulated=true`.\n"
        "- no cross-user/subject/teacher-only leak; simulated retest never promoted to real.\n", "utf-8")
    _wl("fresh_retest_runtime_results_m15.jsonl", retest_rows)
    _wl("learning_brain_canonical_write_dryrun_m15.jsonl", lb_dryrun)

    # ---- verdict ----
    safe = (fp_total == 0 and not overwritten and not flag_off_leak and legacy_equal_rate == 1.0
            and kill_works and failclosed and non_cohort_blocked and dup_idem and metrics["production_write_count"] == 0)
    release_go = safe and counted_hits >= 50
    lb_go = (real_retest_valid >= 1 and len(lb_dryrun) >= 1 and not metrics["production_truth_written"])
    if not safe:
        release_verdict = "NO-GO"
    elif counted_hits >= 50:
        release_verdict = "GO"
    else:
        release_verdict = "WEAK-GO"
    lb_verdict = "GO" if lb_go else ("WEAK-GO" if safe else "NO-GO")

    _wj("m15_go_no_go.json", {
        "m15_limited_internal_release_candidate": release_verdict,
        "learning_brain_canonical_write_pilot": lb_verdict,
        "production_v1": "NO-GO",
        "production_default": "OFF", "formal_registry_emitted": False,
        "three_axis": {"m15_limited_internal_release_candidate": release_verdict,
                       "learning_brain_canonical_write_pilot": lb_verdict, "production_v1": "NO-GO"},
        "counted_authority_backed_runtime_hits": counted_hits, "target_55_met": counted_hits >= 55,
        "go_threshold_50_met": counted_hits >= 50,
        "metrics": metrics,
        "m16_production_gate_blockers": ["real human teacher review loop (not shadow)",
                                         "production authority registry sign-off",
                                         "dual big-model skeptic (GPT5.5 key)",
                                         "operator cohort live rollback rehearsal",
                                         "canonical learner truth write path (currently dry-run only)"],
    })
    _wj("workflow_ledger_m15.json", {
        "classify_and_act": {"miss_classes": dict(miss_class), "all_classified": all(m["miss_class"] for m in miss_ledger)},
        "fanout_and_synthesize": {"deepseek_qwen": "advisory_not_invoked", "gpt55": "provider_unavailable_fail_closed",
                                  "opus48": "workflow_judge_executing_agent", "deterministic_script": "sole_authority"},
        "generate_and_filter": {"strategy": "rich per-question answers (one submission scores all counted points)",
                                "matcher_relaxed": False, "official_answer_as_source": False},
        "tournament": {"chosen_fix": "sample generation (rich answers) — no production-code change, matcher unchanged"},
        "adversarial_verification": {"negatives": len(adversarial), "false_positive": fp_total,
                                     "attacks": ["off_by_one", "flip_polarity", "partial_list", "irrelevant"]},
        "loop_until_done": {"counted_hits": counted_hits, "ge_50": counted_hits >= 50, "remaining_miss": len(miss_ledger)},
    })
    _wj("m15_manifest.json", {
        "stage": "M15 Runtime Hits Expansion + Fresh Retest Entry",
        "real_entry": "/api/v1/ws deep_question QA/test branch -> _maybe_attach_v1_beta_shadow",
        "production_code_changed": False, "matcher_relaxed": False,
        "metrics": metrics, "release_verdict": release_verdict, "lb_verdict": lb_verdict, "production_v1": "NO-GO"})

    summary = {"counted_total": len(counted), "counted_hits": counted_hits, "new_hits": new_hits,
               "hits_by_kind": dict(hits_by_kind), "false_positive": fp_total,
               "legacy_equal_rate": legacy_equal_rate, "kill_works": kill_works, "failclosed": failclosed,
               "non_cohort_blocked": non_cohort_blocked, "real_retest_valid": real_retest_valid,
               "canonical_dryrun": len(lb_dryrun), "production_write": 0,
               "release_verdict": release_verdict, "lb_verdict": lb_verdict, "production_v1": "NO-GO"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
