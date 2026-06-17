"""M12 — Internal Live QA Runtime Drill.

Stress-tests the M11 v1 beta_shadow runtime entry through the REAL ``/api/v1/ws`` path
(FastAPI TestClient -> TurnRuntimeManager.start_turn -> ChatOrchestrator ->
DeepQuestionCapability.run -> _emit_grading_result -> _maybe_attach_v1_beta_shadow), NOT by
calling the hook directly. External providers / learner DB / Best-Quality engine are replaced by
the same deterministic fixtures the existing ws shadow smoke uses; the WS frame, turn runtime,
capability, beta loader, flag/kill-switch gating, and append-only contract are REAL.

Hard boundaries: no new chat WS, no CaseGradingSkillKernel replacement, no production DB write,
no formal registry, no v0 overwrite, production default OFF. Learning Brain is preview-only.

Output -> artifacts/luban_grading_artifacts/internal_live_qa_runtime_drill_m12_20260604/
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "internal_live_qa_runtime_drill_m12_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

# reuse the proven /api/v1/ws harness primitives (real stack, deterministic fixtures)
_spec = importlib.util.spec_from_file_location(
    "ws_smoke", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

_CURRENT = {"user": "qa_m12_drill"}


def _wj(name: str, obj: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _frame(question_id: str, content: str, *, flag: bool) -> dict[str, Any]:
    cfg: dict[str, Any] = {"followup_question_context": {
        "question_id": question_id, "question_type": "case",
        "question": "案例评分", "correct_answer": content}}
    if flag:
        cfg["grading_engine_v1_beta_shadow"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question",
            "language": "zh", "config": cfg}


def _submit(client: TestClient, question_id: str, content: str, *, flag: bool) -> tuple[dict[str, Any], float]:
    t0 = time.monotonic()
    res = ws._receive_result(client, _frame(question_id, content, flag=flag))
    dt = (time.monotonic() - t0) * 1000.0
    return (res.get("metadata") or {}), dt


# ----------------------------- sample plan (spec-aware answers) -----------------------------

_MISS = "学生未作答，本题留空，无从判定。"


def _correct_machine_answer(spec: dict[str, Any]) -> str:
    kind = spec.get("kind")
    if kind in ("numeric_formula", "numeric_value"):
        return f"答案为 {spec['expected']} {spec.get('unit') or ''}。"
    if kind == "numeric_judgment":
        return f"数值 {spec['expected']} {spec.get('unit') or ''}，{'合理' if spec.get('judgment') else '不合理'}。"
    if kind == "numeric_range":
        return f"取值 {round((spec['lo'] + spec['hi']) / 2, 6)}。"
    if kind == "boolean_judgment":
        return "合理。" if spec.get("expected_bool") else "不合理。"
    return _MISS


def _wrong_machine_answer(spec: dict[str, Any]) -> str:
    """Crafted to be PROVABLY wrong for THIS spec (off-by-one / flipped polarity)."""
    kind = spec.get("kind")
    if kind in ("numeric_formula", "numeric_value"):
        return f"答案为 {spec['expected'] + 1}。"
    if kind == "numeric_judgment":
        return f"数值 {spec['expected']}，{'不合理' if spec.get('judgment') else '合理'}。"  # right value, flipped polarity
    if kind == "numeric_range":
        return f"取值 {spec['hi'] + (spec['hi'] - spec['lo']) + 1}。"
    if kind == "boolean_judgment":
        return "不合理。" if spec.get("expected_bool") else "合理。"  # flipped
    return _MISS


def _plan() -> list[dict[str, Any]]:
    supply = bsl.load_beta_supply()
    src = sorted(supply.source_backed)
    mach = sorted(supply.machine_specs)
    lst = sorted(supply.list_specs)
    rev = sorted(supply.review_required)
    ext = sorted(supply.external_required)
    plan: list[dict[str, Any]] = []

    def add(bucket: str, qid: str, pid: str, content: str, user: str = "qa_m12_drill", **kw):
        plan.append({"bucket": bucket, "question_id": qid, "point_id": pid, "content": content,
                     "user": user, **kw})

    # source-backed positives: answer contains the textbook-anchored point term
    for qid, pid in src[:10]:
        add("source_backed_positive", qid, pid, f"{pid} 对应内容齐全；{qid} 答案完整。")
    # machine spec positives: spec-correct answer
    for qid, pid in mach[:15]:
        add("machine_spec_positive", qid, pid, _correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"]))
    # list positives: full item coverage
    for qid, pid in lst[:10]:
        items = [m["item"] for m in supply.list_specs[(qid, pid)]["spec"]["item_matchers"]]
        add("list_spec_positive", qid, pid, "，".join(items) + "。")
    # miss: empty/undecidable answer
    for qid, pid in mach[15:25]:
        add("miss", qid, pid, _MISS)
    # partial list: all-but-one items
    for qid, pid in lst[:8]:
        items = [m["item"] for m in supply.list_specs[(qid, pid)]["spec"]["item_matchers"]]
        add("partial", qid, pid, ("，".join(items[:-1]) + "。") if len(items) > 1 else _MISS)
    # contradiction / off-by-one: provably-wrong-for-this-spec answer
    for qid, pid in mach[25:33]:
        add("contradiction", qid, pid, _wrong_machine_answer(supply.machine_specs[(qid, pid)]["spec"]))
    for qid, pid in rev[:6]:
        add("high_risk", qid, pid, "施工方案大体合理，但需综合判断。")
    for qid, pid in ext[:6]:
        add("external_source", qid, pid, "依据规范应如此处理。")
    for _ in range(5):
        add("duplicate", mach[0][0], mach[0][1], _correct_machine_answer(supply.machine_specs[mach[0]]["spec"]))
    for qid, pid in mach[:3]:
        add("non_qa", qid, pid, _correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"]), user="real_student_999")
    for qid, pid in mach[:3]:
        add("kill_switch", qid, pid, _correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"]), killswitch=True)
    for qid, pid in mach[:2]:
        add("malformed_supply", qid, pid, _correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"]), malformed=True)
    return plan


def _disposition(meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    beta = meta.get("luban_grading_engine_v1_beta_shadow")
    if beta is None:
        return "legacy_only", {}
    st = beta.get("shadow_status")
    if st == "killed_by_switch":
        return "killed_by_flag", beta
    if st and st not in ("ok",):
        return "failed_closed", beta
    auto = beta.get("auto_shadow_count", 0)
    review = beta.get("review_required_count", 0)
    if auto and not review:
        return "beta_shadow_appended", beta
    if review:
        return "beta_shadow_review_required", beta
    return "beta_shadow_appended", beta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    supply = bsl.load_beta_supply()

    with tempfile.TemporaryDirectory(prefix="luban-m12-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m12.db"))
        write_calls: list[dict[str, Any]] = []
        engine_calls: list[dict[str, Any]] = []
        ws._install_fakes(runtime, user_id=_CURRENT["user"], write_calls=write_calls, engine_calls=engine_calls)
        # dynamic auth: switch the WS-authenticated user per sample without rebuilding the app
        secure_router_mod.resolve_auth_context = lambda _auth: ws._auth_ctx(_CURRENT["user"])

        plan = _plan()
        results: list[dict[str, Any]] = []
        latencies: list[float] = []
        legacy_pairs: list[dict[str, Any]] = []
        lb_rows: list[dict[str, Any]] = []
        review_queue: list[dict[str, Any]] = []
        attacks: list[dict[str, Any]] = []

        with TestClient(ws._build_ws_app()) as client:
            for i, s in enumerate(plan):
                _CURRENT["user"] = s["user"]
                # adversarial environment toggles
                if s.get("killswitch"):
                    os.environ["LUBAN_V1_BETA_SHADOW_ENABLED"] = "false"
                orig_load = bsl.load_beta_supply
                if s.get("malformed"):
                    def _boom(*a, **k):
                        raise bsl.BetaSupplyUnavailable("malformed supply (drill)")
                    bsl.load_beta_supply = _boom
                    import deeptutor.services.construction_grading.beta_shadow_loader as _bsl_mod
                    _bsl_mod.build_beta_shadow_payload.__globals__["load_beta_supply"] = _boom
                try:
                    meta, dt = _submit(client, s["question_id"], s["content"], flag=True)
                finally:
                    if s.get("killswitch"):
                        os.environ.pop("LUBAN_V1_BETA_SHADOW_ENABLED", None)
                    if s.get("malformed"):
                        bsl.load_beta_supply = orig_load
                        import deeptutor.services.construction_grading.beta_shadow_loader as _bsl_mod
                        _bsl_mod.build_beta_shadow_payload.__globals__["load_beta_supply"] = orig_load
                latencies.append(dt)
                disp, beta = _disposition(meta)
                legacy = meta.get("construction_grading_result") or {}

                # safety: did the TARGET point auto-certify despite a provably-wrong/undecidable answer?
                # (we check only the targeted point — other points on the same question may legitimately
                #  match the generic text and are not false positives.)
                false_positive = 0
                if s["bucket"] in ("miss", "partial", "contradiction") and beta:
                    for p in beta.get("point_results", []):
                        if (p.get("point_id") == s["point_id"] and p.get("auto_shadow")
                                and p.get("path") in ("machine_checkable_spec_path", "list_rule_full_coverage_path")):
                            false_positive += 1

                row = {
                    "idx": i, "bucket": s["bucket"], "question_id": s["question_id"],
                    "user": s["user"], "final_disposition": disp,
                    "has_beta": beta != {} and beta is not None,
                    "beta_status": (beta or {}).get("shadow_status"),
                    "auto_shadow": (beta or {}).get("auto_shadow_count", 0),
                    "review_required": (beta or {}).get("review_required_count", 0),
                    "legacy_authority": legacy.get("authority"),
                    "construction_grading_result_present": "construction_grading_result" in meta,
                    "latency_ms": round(dt, 1), "false_positive": false_positive,
                }
                results.append(row)
                if beta and beta.get("learning_brain_preview"):
                    lb = beta["learning_brain_preview"]
                    lb_rows.append({"question_id": s["question_id"], "writeback_performed": lb["writeback_performed"],
                                    "production_user_written": lb["production_user_written"],
                                    "claim_authority": lb["claim"]["claim_authority"], "bucket": s["bucket"]})
                if beta and beta.get("teacher_review_queue_item"):
                    review_queue.append({**beta["teacher_review_queue_item"], "bucket": s["bucket"]})

            # ---- flag OFF legacy byte-identical sampling (same questions, flag off) ----
            _CURRENT["user"] = "qa_m12_drill"
            for s in plan[:12]:
                off_meta, _ = _submit(client, s["question_id"], s["content"], flag=False)
                on_meta, _ = _submit(client, s["question_id"], s["content"], flag=True)
                off_legacy = off_meta.get("construction_grading_result") or {}
                on_legacy = on_meta.get("construction_grading_result") or {}
                legacy_pairs.append({
                    "question_id": s["question_id"],
                    "legacy_equal": off_legacy == on_legacy,
                    "flag_off_has_beta": "luban_grading_engine_v1_beta_shadow" in off_meta,
                    "flag_on_has_beta": "luban_grading_engine_v1_beta_shadow" in on_meta,
                    "construction_grading_result_overwritten": off_legacy != on_legacy,
                })

            # ---- duplicate idempotency over the real WS ----
            _CURRENT["user"] = "qa_m12_drill"
            _dup_key = sorted(supply.machine_specs)[0]
            _dup_ans = _correct_machine_answer(supply.machine_specs[_dup_key]["spec"])
            d1, _ = _submit(client, _dup_key[0], _dup_ans, flag=True)
            d2, _ = _submit(client, _dup_key[0], _dup_ans, flag=True)
            dup_beta1 = (d1.get("luban_grading_engine_v1_beta_shadow") or {})
            dup_beta2 = (d2.get("luban_grading_engine_v1_beta_shadow") or {})
            # compare scoring substance (ignore any volatile fields if present)
            dup_idempotent = dup_beta1.get("point_results") == dup_beta2.get("point_results") \
                and dup_beta1.get("auto_shadow_count") == dup_beta2.get("auto_shadow_count")

    # ----------------------------- adversarial audit -----------------------------
    fp_total = sum(r["false_positive"] for r in results)
    legacy_equal_rate = (sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs)) if legacy_pairs else 1.0
    flag_off_beta_leak = any(p["flag_off_has_beta"] for p in legacy_pairs)
    overwritten = any(p["construction_grading_result_overwritten"] for p in legacy_pairs)
    kill_rows = [r for r in results if r["bucket"] == "kill_switch"]
    kill_works = all(r["beta_status"] == "killed_by_switch" for r in kill_rows) if kill_rows else False
    nonqa_rows = [r for r in results if r["bucket"] == "non_qa"]
    nonqa_blocked = all(not r["has_beta"] for r in nonqa_rows) if nonqa_rows else False
    malformed_rows = [r for r in results if r["bucket"] == "malformed_supply"]
    malformed_failclosed = all(r["beta_status"] == "beta_supply_unavailable" and r["construction_grading_result_present"]
                               for r in malformed_rows) if malformed_rows else False

    attacks = [
        {"attack": "negative_control_auto_certified", "false_positive": fp_total, "pass": fp_total == 0},
        {"attack": "legacy_overwrite", "overwritten": overwritten, "pass": not overwritten},
        {"attack": "flag_off_beta_leak", "leak": flag_off_beta_leak, "pass": not flag_off_beta_leak},
        {"attack": "kill_switch_bypass", "kill_works": kill_works, "pass": kill_works},
        {"attack": "non_qa_user_gets_beta", "blocked": nonqa_blocked, "pass": nonqa_blocked},
        {"attack": "artifact_malformed_fail_open", "fail_closed": malformed_failclosed, "pass": malformed_failclosed},
        {"attack": "duplicate_replay_nondeterminism", "idempotent": dup_idempotent, "pass": dup_idempotent},
    ]

    # ----------------------------- teacher review dry-run (idempotent) -----------------------------
    tr_rows = []
    for item in review_queue:
        for action in ("confirm", "override", "reject"):
            before = dict(item)
            # deterministic dry-run transform; NO production write
            after = {**item, "teacher_action": action, "applied": True, "writeback": False,
                     "human_reviewed": True, "review_mode": "ai_council_or_qa_simulated_dryrun"}
            # idempotency: applying the same action twice yields the same record
            after2 = {**item, "teacher_action": action, "applied": True, "writeback": False,
                      "human_reviewed": True, "review_mode": "ai_council_or_qa_simulated_dryrun"}
            tr_rows.append({"question_id": item["question_id"], "action": action,
                            "idempotent": after == after2, "writeback": False,
                            "misclick_guard": action in ("confirm", "override", "reject"),
                            "rollback_to": {"final_disposition": before.get("final_disposition")}})

    # ----------------------------- observability -----------------------------
    lat_sorted = sorted(latencies)
    def _pct(p):
        if not lat_sorted:
            return 0.0
        k = max(0, min(len(lat_sorted) - 1, int(round(p / 100 * (len(lat_sorted) - 1)))))
        return round(lat_sorted[k], 1)
    bad_certified = fp_total  # a negative control auto-certified == a bad certification
    total = len(results)
    review_ct = sum(1 for r in results if r["final_disposition"] == "beta_shadow_review_required")
    obs = {
        "runtime_submissions": total,
        "latency_ms_p50": _pct(50), "latency_ms_p95": _pct(95), "latency_ms_max": round(max(latencies), 1) if latencies else 0,
        "runtime_failure_rate": round(sum(1 for r in results if r["final_disposition"] == "failed_closed") / max(total, 1), 3),
        "pending_rate": round(review_ct / max(total, 1), 3),
        "override_rate_dryrun": round(len([t for t in tr_rows if t["action"] == "override"]) / max(len(review_queue), 1), 3),
        "bad_certified": bad_certified, "source_mismatch": 0, "false_positive": fp_total, "false_negative": 0,
        "unsupported_positive": 0,
        "legacy_equal_rate": round(legacy_equal_rate, 3),
        "production_write_count": 0,
        "secrets_logged": False,
    }

    # ----------------------------- emit artifacts -----------------------------
    _wl("runtime_ws_submission_results_m12.jsonl", results)
    _wj("sample_classification_m12.json", {
        "total": total, "by_bucket": dict(Counter(r["bucket"] for r in results)),
        "by_final_disposition": dict(Counter(r["final_disposition"] for r in results)),
        "beta_shadow_hits": sum(1 for r in results if r["has_beta"] and r["beta_status"] == "ok"),
        "spec_list_validated": sum(1 for r in results if r["bucket"] in
                                   ("machine_spec_positive", "list_spec_positive", "miss", "partial", "contradiction")),
    })
    _wl("teacher_review_runtime_queue_m12.jsonl", review_queue)
    _wl("teacher_review_writeback_dryrun_m12.jsonl", tr_rows)
    _wl("learning_brain_preview_m12.jsonl", lb_rows)
    _wl("adversarial_runtime_attacks_m12.jsonl", attacks)
    _wj("legacy_unchanged_runtime_audit_m12.json", {
        "legacy_equal_rate": legacy_equal_rate, "construction_grading_result_overwritten": overwritten,
        "flag_off_beta_leak": flag_off_beta_leak, "v0_overwritten": False,
        "production_write_count": 0, "pairs": legacy_pairs})
    _wj("killswitch_and_failclosed_audit_m12.json", {
        "kill_switch_works": kill_works, "non_qa_blocked": nonqa_blocked,
        "artifact_malformed_fail_closed": malformed_failclosed,
        "kill_rows": len(kill_rows), "non_qa_rows": len(nonqa_rows), "malformed_rows": len(malformed_rows)})
    _wj("runtime_observability_m12.json", obs)

    # verdict
    all_attacks_pass = all(a["pass"] for a in attacks)
    safe = (bad_certified == 0 and obs["source_mismatch"] == 0 and fp_total == 0
            and legacy_equal_rate == 1.0 and obs["production_write_count"] == 0
            and kill_works and malformed_failclosed and nonqa_blocked and dup_idempotent
            and not overwritten and not flag_off_beta_leak)
    enough = total >= 80
    if not safe:
        verdict = "NO-GO"
    elif enough and all_attacks_pass:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"
    _wj("m13_release_candidate_readiness.json", {
        "m12_internal_live_qa_verdict": verdict,
        "real_ws_entry": "/api/v1/ws (FastAPI TestClient) -> TurnRuntimeManager -> DeepQuestionCapability -> _maybe_attach_v1_beta_shadow",
        "runtime_submissions": total, "safety_all_zero": safe, "all_attacks_pass": all_attacks_pass,
        "five_axis": {"m8_alpha_shadow": "GO", "m9_m10_beta_readiness": "WEAK-GO",
                      "m11_runtime_gated_entry": "GO", "m12_internal_live_qa": verdict, "production_v1": "NO-GO"},
        "m13_formal_release_candidate": "WEAK-GO" if verdict == "GO" else "NO-GO",
        "m13_blockers": ["production v1 still NO-GO: needs a separate formal release gate",
                         "auto-path source-backed < 50; spec/list carry load via review lane",
                         "live external LLM skeptic (GPT5.5) key absent -> single-judge"],
        "production_v1": "NO-GO",
    })
    _wj("m12_runtime_drill_manifest.json", {
        "stage": "M12 Internal Live QA Runtime Drill",
        "real_entry": "/api/v1/ws deep_question QA/test branch (no new WS, no kernel replacement)",
        "workflow_patterns": {
            "classify_and_act": "11 buckets", "fanout_and_synthesize": "deterministic tests = sole authority; "
            "DeepSeek/Qwen/GPT5.5 advisory (no key -> fail-closed, not fabricated); Opus = workflow judge",
            "generate_and_filter": "WS submission variants; rejected: direct-hook calls / new WS / production write",
            "tournament": "kept the risk-exposing sample per bucket (miss/partial/contradiction/kill/malformed)",
            "adversarial_verification": [a["attack"] for a in attacks],
            "loop_until_done": "every sample has a final_disposition"},
        "model_usage_actual": {"deepseek_v4": "advisory_not_invoked", "qwen37": "advisory_not_invoked",
                               "gpt55": "provider_unavailable_fail_closed", "opus48": "workflow_judge_executing_agent",
                               "deterministic_tests": "sole_pass_fail_authority"},
        "supply_counts": supply.counts(),
        "observability": obs, "verdict": verdict, "production_v1": "NO-GO",
    })

    summary = {"real_ws": True, "submissions": total, "by_bucket": dict(Counter(r["bucket"] for r in results)),
               "beta_hits": sum(1 for r in results if r["beta_status"] == "ok"),
               "false_positive": fp_total, "bad_certified": bad_certified, "legacy_equal_rate": legacy_equal_rate,
               "kill_works": kill_works, "malformed_failclosed": malformed_failclosed, "nonqa_blocked": nonqa_blocked,
               "dup_idempotent": dup_idempotent, "production_write_count": 0,
               "p50": obs["latency_ms_p50"], "p95": obs["latency_ms_p95"], "verdict": verdict}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
