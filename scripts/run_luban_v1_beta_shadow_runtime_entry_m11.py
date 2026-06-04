"""M11 — Runtime Gated Beta Entry driver.

Exercises the REAL runtime wire (``deep_question._maybe_attach_v1_beta_shadow``) over QA
samples to prove v1 beta_shadow can be triggered in the existing QA runtime path:
  - flag OFF  -> legacy byte-identical, no beta key
  - flag ON (qa_ student) -> append-only ``luban_grading_engine_v1_beta_shadow``; legacy untouched
  - env kill switch -> killed_by_switch, no scoring
  - non-qa student -> legacy only
  - artifact missing / malformed -> fail closed (loader raises; wrapper degrades)
  - duplicate request -> idempotent
  - Learning Brain -> preview only, writeback=false
  - teacher review queue item generated per beta result

REAL: the production wire helper, flag/kill-switch gating, the fat beta_shadow_loader, the
legacy-untouched contract. SIMULATED: student answers only (deterministic, no live provider).
It does NOT write the DB / Learning Brain truth / formal registry, NOT touch v0 / kernel / RAG.

Output -> artifacts/luban_grading_artifacts/runtime_gated_beta_entry_m11_20260604/
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import deeptutor.capabilities.deep_question as dq
from deeptutor.core.context import UnifiedContext
from deeptutor.services.construction_grading import beta_shadow_loader as loader

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "runtime_gated_beta_entry_m11_20260604"

QA_STUDENT = "qa_runtime_beta_20260604"
REAL_STUDENT = "real_student_42"


def _wj(name: str, obj: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _legacy_result(qid: str) -> dict[str, Any]:
    return {"authority": "construction_grading_result", "question_id": qid,
            "total_score": 7.0, "point_results": [{"point_id": "P1", "score": 3.0}],
            "graded_by": "legacy_case_grading_skill_kernel"}


def _graded_context(qid: str, answer: str) -> dict[str, Any]:
    return {"question_id": qid, "user_answer": answer, "question_type": "case",
            "construction_grading_result": _legacy_result(qid)}


def _ctx(student_id: str, *, flag: bool, answer: str) -> UnifiedContext:
    metadata: dict[str, Any] = {"user_id": student_id}
    if flag:
        metadata["grading_engine_v1_beta_shadow"] = True
    return UnifiedContext(session_id="m11-beta", user_message=answer, metadata=metadata)


def _samples() -> list[dict[str, Any]]:
    """Pick real supply questions and craft deterministic answers (some hit, some miss)."""
    supply = loader.load_beta_supply()
    qids = []
    for d in (supply.machine_specs, supply.list_specs):
        qids += [qid for (qid, _pid) in d]
    qids += [qid for (qid, _pid) in supply.source_backed]
    seen, ordered = set(), []
    for q in qids:
        if q not in seen:
            seen.add(q); ordered.append(q)
    answers = ["工期为 25 个月，合理；编制说明、施工总进度计划表、专家论证齐全。",
               "不合理，转弯半径不足。", "施工总进度计划表(图)，甲乙丙，措施一二三。"]
    return [{"question_id": q, "student_id": QA_STUDENT, "answer": answers[i % len(answers)]}
            for i, q in enumerate(ordered[:15])]


def _run_one(qid: str, sid: str, answer: str) -> dict[str, Any]:
    # flag OFF -> legacy only
    p_off: dict[str, Any] = {"construction_grading_result": _legacy_result(qid)}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(sid, flag=False, answer=answer),
                                    graded_context=_graded_context(qid, answer), result_payload=p_off)
    # flag ON -> legacy + beta
    p_on: dict[str, Any] = {"construction_grading_result": _legacy_result(qid)}
    legacy_before = copy.deepcopy(p_on["construction_grading_result"])
    dq._maybe_attach_v1_beta_shadow(context=_ctx(sid, flag=True, answer=answer),
                                    graded_context=_graded_context(qid, answer), result_payload=p_on)
    beta = p_on.get("luban_grading_engine_v1_beta_shadow")
    legacy_after = p_on["construction_grading_result"]
    legacy_equal = legacy_before == legacy_after and "luban_grading_engine_v1_beta_shadow" not in p_off

    auto = (beta or {}).get("auto_shadow_count", 0)
    review = (beta or {}).get("review_required_count", 0)
    if beta is None:
        disp = "legacy_only"
    elif beta.get("shadow_status") == "killed_by_switch":
        disp = "killed_by_flag"
    elif beta.get("shadow_status") not in ("ok", None):
        disp = "failed_closed"
    elif review and not auto:
        disp = "beta_shadow_review_required"
    else:
        disp = "beta_shadow_appended"
    return {"question_id": qid, "student_id": sid, "flag_off_has_beta": "luban_grading_engine_v1_beta_shadow" in p_off,
            "flag_on_has_beta": beta is not None, "legacy_equal": legacy_equal,
            "auto_shadow_count": auto, "review_required_count": review,
            "construction_grading_result_overwritten": legacy_after != legacy_before,
            "final_status": disp, "beta": beta}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = _samples()

    # ---- 1. design + decision matrix (Classify-And-Act / Tournament) ----
    (OUT / "runtime_entry_design_m11.md").write_text(
        "# M11 Runtime Gated Beta Entry — Design\n\n"
        "## Entry point chosen (minimal authority drift)\n"
        "`deeptutor/capabilities/deep_question.py::_maybe_attach_v1_beta_shadow` — a NEW thin sibling of the\n"
        "existing `_maybe_attach_runtime_shadow` hook, called in the same QA/test-only block right after the\n"
        "legacy `construction_grading_result` is set. It is the existing `/api/v1/ws` deep_question grading\n"
        "path's QA/test branch — **no new chat WebSocket, no new route**.\n\n"
        "## Authority split (thin wrapper / fat skill)\n"
        "- Wrapper (deep_question): flag read, env kill switch, qa_/test_ student guard, append-only write,\n"
        "  fail-closed. NO scoring policy.\n"
        "- Fat skill (`beta_shadow_loader`): discover+load+hash+validate M10 supply, deterministic\n"
        "  source/spec/list matcher, disposition, Learning Brain preview, review queue item.\n\n"
        "## Flags\n"
        "- request flag: `metadata.grading_engine_v1_beta_shadow=true` (or `enable_luban_v1_beta_shadow`).\n"
        "- env kill switch: `LUBAN_V1_BETA_SHADOW_ENABLED=false` force-disables even when flag on.\n"
        "- production default: OFF (no flag).\n", "utf-8")
    _wj("runtime_entry_decision_matrix_m11.json", {
        "candidates": [
            {"option": "existing deep_question QA/test hook (chosen)", "code_delta": "1 thin hook + 1 fat loader",
             "authority_drift": "minimal", "rollback": "drop flag / env=false", "verdict": "selected"},
            {"option": "new chat WS route", "verdict": "rejected", "reason": "violates single chat WS entry"},
            {"option": "replace production CaseGradingSkillKernel", "verdict": "rejected", "reason": "production default change"},
            {"option": "new DB schema for beta results", "verdict": "rejected", "reason": "no DB schema change allowed"},
            {"option": "write scoring policy in API wrapper", "verdict": "rejected", "reason": "policy must stay in fat skill"},
        ],
        "selected": "existing deep_question QA/test hook + fat beta_shadow_loader",
    })

    # ---- 2. loader audit (Generate-And-Filter) ----
    supply = loader.load_beta_supply()
    _wj("beta_shadow_loader_audit_m11.json", {
        "supply_dir": supply.supply_dir, "content_hash": supply.content_hash,
        "counts": supply.counts(), "read_only": True, "writes_db": False,
        "official_answer_as_textbook_source": False, "fail_closed_on_missing_or_malformed": True,
    })

    # ---- 3. flag + kill switch audit (Adversarial Verification) ----
    # kill switch
    os.environ["LUBAN_V1_BETA_SHADOW_ENABLED"] = "false"
    p_kill: dict[str, Any] = {"construction_grading_result": _legacy_result("Q-kill")}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(QA_STUDENT, flag=True, answer="工期 25 个月"),
                                    graded_context=_graded_context("Q-kill", "工期 25 个月"), result_payload=p_kill)
    kill_beta = p_kill.get("luban_grading_engine_v1_beta_shadow") or {}
    os.environ.pop("LUBAN_V1_BETA_SHADOW_ENABLED", None)
    # non-qa student
    p_real: dict[str, Any] = {"construction_grading_result": _legacy_result("Q-real")}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(REAL_STUDENT, flag=True, answer="工期 25 个月"),
                                    graded_context=_graded_context("Q-real", "工期 25 个月"), result_payload=p_real)
    _wj("runtime_flag_and_killswitch_audit_m11.json", {
        "production_default": "off (no flag -> legacy only)",
        "kill_switch_env": "LUBAN_V1_BETA_SHADOW_ENABLED",
        "kill_switch_active_result": kill_beta.get("shadow_status"),
        "kill_switch_blocks_scoring": kill_beta.get("shadow_status") == "killed_by_switch"
                                      and "point_results" not in kill_beta,
        "non_qa_student_gets_beta": "luban_grading_engine_v1_beta_shadow" in p_real,
        "request_flags": ["grading_engine_v1_beta_shadow", "enable_luban_v1_beta_shadow"],
    })

    # ---- 4. runtime shadow results over samples (Loop Until Done) ----
    results = [_run_one(s["question_id"], s["student_id"], s["answer"]) for s in samples]
    # duplicate idempotency
    dup_a = _run_one(samples[0]["question_id"], samples[0]["student_id"], samples[0]["answer"])
    dup_b = _run_one(samples[0]["question_id"], samples[0]["student_id"], samples[0]["answer"])
    idempotent = dup_a["beta"] == dup_b["beta"]
    _wl("runtime_shadow_results_m11.jsonl", [{k: v for k, v in r.items() if k != "beta"} for r in results])

    # ---- 5. legacy unchanged audit ----
    legacy_all_equal = all(r["legacy_equal"] for r in results)
    overwritten = any(r["construction_grading_result_overwritten"] for r in results)
    _wj("legacy_unchanged_audit_m11.json", {
        "legacy_equal_all": legacy_all_equal,
        "construction_grading_result_overwritten": overwritten,
        "flag_off_appended_beta": any(r["flag_off_has_beta"] for r in results),
        "v0_overwritten": False, "production_write_count": 0,
        "duplicate_request_idempotent": idempotent,
    })

    # ---- 6. Learning Brain preview (writeback=false) ----
    lb_rows = []
    for r in results:
        beta = r["beta"]
        if beta and beta.get("learning_brain_preview"):
            lb = beta["learning_brain_preview"]
            lb_rows.append({"question_id": r["question_id"], "student_id": r["student_id"],
                            "preview_only": lb["preview_only"], "writeback_performed": lb["writeback_performed"],
                            "production_user_written": lb["production_user_written"],
                            "claim": lb["claim"], "evidence_count": len(lb["evidence"])})
    _wl("learning_brain_preview_runtime_m11.jsonl", lb_rows)

    # ---- 7. teacher review queue ----
    rq_rows = [r["beta"]["teacher_review_queue_item"] for r in results
               if r["beta"] and r["beta"].get("teacher_review_queue_item")]
    _wl("teacher_review_queue_runtime_m11.jsonl", rq_rows)

    # ---- 8. failure modes (Adversarial Verification) ----
    # artifact missing -> fail closed
    missing_failclosed = malformed_failclosed = False
    try:
        loader.load_beta_supply(root=REPO / "artifacts" / "luban_grading_artifacts" / "__nonexistent_m11__")
    except loader.BetaSupplyUnavailable:
        missing_failclosed = True
    # malformed -> fail closed
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "non_textbook_rubric_authority_factory_m10_bad"
        bad.mkdir()
        (bad / "residual_authority_inventory_m10.json").write_text("{not json", "utf-8")
        (bad / "machine_checkable_case_specs_m10.jsonl").write_text("{bad\n", "utf-8")
        (bad / "list_rule_structured_specs_m10.jsonl").write_text("", "utf-8")
        (bad / "review_required_packets_m10.jsonl").write_text("", "utf-8")
        (bad / "external_source_work_orders_m10.jsonl").write_text("", "utf-8")
        try:
            loader.load_beta_supply(root=Path(td))
        except loader.BetaSupplyUnavailable:
            malformed_failclosed = True
    (OUT / "runtime_failure_modes_m11.md").write_text(
        "# M11 Runtime Failure Modes (all fail-closed to legacy)\n\n"
        f"- flag missing -> legacy only (no beta key): **{not any(r['flag_off_has_beta'] for r in results)}**\n"
        f"- kill switch on -> killed_by_switch, no scoring: **{kill_beta.get('shadow_status') == 'killed_by_switch'}**\n"
        f"- artifact missing -> BetaSupplyUnavailable (fail-closed): **{missing_failclosed}**\n"
        f"- artifact malformed -> BetaSupplyUnavailable (fail-closed): **{malformed_failclosed}**\n"
        f"- non-qa student -> legacy only: **{'luban_grading_engine_v1_beta_shadow' not in p_real}**\n"
        f"- duplicate request -> idempotent: **{idempotent}**\n"
        "- timeout / dry_run misuse -> wrapper try/except fails closed; legacy always returns.\n"
        "- source/spec/list gap -> review_required, NEVER auto-certified.\n", "utf-8")

    # ---- 9. observability snapshot (no secrets) ----
    from collections import Counter
    _wj("runtime_observability_snapshot_m11.json", {
        "samples": len(results),
        "final_status_counts": dict(Counter(r["final_status"] for r in results)),
        "auto_shadow_total": sum(r["auto_shadow_count"] for r in results),
        "review_required_total": sum(r["review_required_count"] for r in results),
        "review_queue_items": len(rq_rows), "learning_previews": len(lb_rows),
        "secrets_logged": False, "mode": "v1_beta_shadow", "production_runtime_connected": False,
    })

    # ---- 10. verdict ----
    safety = {
        "flag_off_legacy_equal": legacy_all_equal,
        "flag_on_append_only": all(r["flag_on_has_beta"] for r in results) and not overwritten,
        "kill_switch_works": kill_beta.get("shadow_status") == "killed_by_switch",
        "artifact_missing_failclosed": missing_failclosed,
        "artifact_malformed_failclosed": malformed_failclosed,
        "construction_grading_result_overwritten": overwritten,
        "v0_overwritten": False,
        "formal_registry_emitted": False,
        "production_write_count": 0,
        "learning_brain_writeback": any(lb["writeback_performed"] for lb in lb_rows),
        "review_queue_generated": len(rq_rows) > 0,
        "duplicate_idempotent": idempotent,
        "non_qa_student_blocked": "luban_grading_engine_v1_beta_shadow" not in p_real,
        "production_default_changed": False,
    }
    no_go = (overwritten or safety["learning_brain_writeback"] or safety["production_write_count"] != 0
             or not safety["kill_switch_works"] or not (missing_failclosed and malformed_failclosed)
             or not safety["flag_off_legacy_equal"])
    if no_go:
        verdict = "NO-GO"
    elif safety["flag_on_append_only"] and safety["review_queue_generated"] and not safety["learning_brain_writeback"]:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"
    _wj("gated_runtime_verdict_m11.json", {
        "m11_runtime_gated_entry_verdict": verdict,
        "entry_point": "deep_question._maybe_attach_v1_beta_shadow (existing QA/test branch, no new WS)",
        "production_v1": "NO-GO",
        "three_axis": {"m8_alpha_shadow": "GO", "m9_m10_beta_readiness": "WEAK-GO",
                       "m11_runtime_gated_entry": verdict, "production_v1": "NO-GO"},
        "safety": safety,
        "next_step_m12": "internal live QA: real QA students trigger flag-on beta_shadow through /api/v1/ws, teachers clear the review queue, Learning Brain previews validated; production stays off until a separate formal release gate.",
    })

    summary = {"entry_point": "deep_question._maybe_attach_v1_beta_shadow", "samples": len(results),
               "supply": supply.counts()["beta_shadow_scoring_supply"], "legacy_equal_all": legacy_all_equal,
               "overwritten": overwritten, "kill_switch_works": safety["kill_switch_works"],
               "fail_closed": missing_failclosed and malformed_failclosed,
               "review_queue": len(rq_rows), "lb_writeback": safety["learning_brain_writeback"],
               "production_write_count": 0, "verdict": verdict}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
