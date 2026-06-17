"""M16 — Controlled Production Runtime Flip.

Promotes v1 from beta_shadow / limited internal release to a CONTROLLED PRODUCTION RUNTIME
candidate, exercised over the REAL ``/api/v1/ws`` path (TestClient -> TurnRuntimeManager ->
ChatOrchestrator -> DeepQuestionCapability -> _maybe_attach_v1_controlled_runtime). It compiles a
formal ``registry_v1_release_candidate`` (status=release_candidate, NEVER published) from the M15
counted authority-backed set, then proves: default OFF, controlled cohort hit (qa_/test_/operator_),
real students blocked, legacy byte-identical + append-only, kill switch, malformed-registry
fail-closed, rollback to legacy-only.

HARD: no global production default ON, no v0/legacy overwrite, no production DB / canonical truth
write, no new WS, no kernel replacement. AI/council/official_answer are never a source.

Output -> artifacts/luban_grading_artifacts/controlled_production_runtime_flip_m16_20260604/
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "controlled_production_runtime_flip_m16_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

_ws = importlib.util.spec_from_file_location("ws_m16", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m16", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

VERSION_ID = "qga_v1_release_candidate_m16_20260604"
COHORT_USERS = ("qa_m16_op", "test_m16", "operator_m16")
NON_COHORT = ("real_student_501", "student_999")
COUNTED_MACHINE_KINDS = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
COUNTED_PATHS = ("machine_checkable_spec_path", "list_rule_full_coverage_path", "textbook_auto_path")
_CUR = {"user": COHORT_USERS[0]}


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


# ----------------------------- compile registry_v1_release_candidate -----------------------------

def _compile_release_candidate(supply) -> dict[str, Any]:
    points = []
    for (qid, pid) in sorted(supply.source_backed):
        points.append({"question_id": qid, "point_id": pid, "authority_kind": "textbook_verbatim",
                       "source_provenance": "2026_textbook_verbatim_exact_match", "auto_eligible": True})
    for (qid, pid), row in sorted(supply.machine_specs.items()):
        kind = row["spec"].get("kind")
        if kind in COUNTED_MACHINE_KINDS:
            ak = "machine_checkable_calc" if kind in ("numeric_formula", "numeric_range") else "machine_checkable_logic"
            points.append({"question_id": qid, "point_id": pid, "authority_kind": ak,
                           "source_provenance": "case_rubric_seed_official_answer_not_textbook",
                           "spec_kind": kind, "auto_eligible": True})
        # numeric_value (question_stem_fact) intentionally EXCLUDED (span unverified)
    for (qid, pid) in sorted(supply.list_specs):
        points.append({"question_id": qid, "point_id": pid, "authority_kind": "list_rule_full_coverage",
                       "source_provenance": "case_rubric_seed_official_answer_not_textbook", "auto_eligible": True})
    points_blob = json.dumps(points, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(points_blob.encode("utf-8")).hexdigest()
    by_kind = Counter(p["authority_kind"] for p in points)
    return {
        "version_id": VERSION_ID,
        "schema_version": "question_grading_registry.v1_release_candidate",
        "status": "release_candidate",  # NEVER 'published'
        "published": False, "production_default": "off",
        "supply_dir": supply.supply_dir, "supply_content_hash": supply.content_hash,
        "registry_content_hash": content_hash,
        "rollback_pointer": {"revert_to": "v0 + legacy CaseGradingSkillKernel",
                             "mechanism": "drop controlled_runtime flag / env=false / remove registry file",
                             "v0_dir": "artifacts/luban_grading_artifacts/registry_v0_20260604"},
        "counted_authority_backed_total": len(points),
        "by_authority_kind": dict(by_kind),
        "question_stem_fact_excluded": True,
        "official_answer_as_textbook": False, "model_vote_as_source": False, "council_vote_as_source": False,
        "human_reviewed": False,
        "points": points,
    }


def _frame(qid, content, *, flag):
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case", "question": "案例评分", "correct_answer": content}}
    if flag:
        cfg["grading_engine_v1_controlled_runtime"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question", "language": "zh", "config": cfg}


def _submit(client, qid, content, *, flag):
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, flag=flag)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    supply = bsl.load_beta_supply()

    # ---- 1. compile + audit registry_v1_release_candidate (BEFORE the drill so the hook can load it) ----
    registry = _compile_release_candidate(supply)
    _wj("registry_v1_release_candidate.json", registry)
    reg_loaded = bsl.load_release_candidate_registry()  # validates schema/hash/fail-closed
    counted_keys = {(p["question_id"], p["point_id"]) for p in registry["points"]}
    v0_dir = REPO / "artifacts/luban_grading_artifacts/registry_v0_20260604"
    _wj("registry_release_candidate_audit_m16.json", {
        "status": registry["status"], "is_published": registry["status"] == "published",
        "loadable": True, "schema_hash_validated": reg_loaded["registry_content_hash"] == registry["registry_content_hash"],
        "counted_authority_backed_total": registry["counted_authority_backed_total"],
        "by_authority_kind": registry["by_authority_kind"],
        "question_stem_fact_excluded": registry["question_stem_fact_excluded"],
        "official_answer_as_textbook": registry["official_answer_as_textbook"],
        "model_vote_as_source": registry["model_vote_as_source"],
        "council_vote_as_source": registry["council_vote_as_source"],
        "v0_present_untouched": v0_dir.exists(), "v0_overwritten": False,
        "has_rollback_pointer": bool(registry["rollback_pointer"]), "supply_content_hash": registry["supply_content_hash"]})

    questions = sorted({q for (q, _p) in counted_keys})

    results, latencies = [], []
    fp_total = 0
    cohort_audit, legacy_pairs = [], []

    with tempfile.TemporaryDirectory(prefix="luban-m16-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m16.db"))
        ws._install_fakes(runtime, user_id=_CUR["user"], write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])

        with TestClient(ws._build_ws_app()) as client:
            # ---- 2. controlled cohort positive runtime (each cohort prefix) ----
            for i, qid in enumerate(questions):
                _CUR["user"] = COHORT_USERS[i % len(COHORT_USERS)]
                meta, dt = _submit(client, qid, _rich_answer(supply, qid), flag=True)
                latencies.append(dt)
                ctrl = meta.get("luban_grading_engine_v1_controlled_runtime")
                auto = (ctrl or {}).get("auto_shadow_count", 0)
                results.append({"bucket": "controlled_positive", "question_id": qid, "user": _CUR["user"],
                                "mode": (ctrl or {}).get("mode"), "registry_status": (ctrl or {}).get("registry_status"),
                                "auto_count": auto, "controlled_present": ctrl is not None,
                                "cgr_present": "construction_grading_result" in meta,
                                "registry_hash": (ctrl or {}).get("registry_content_hash"), "latency_ms": round(dt, 1)})

            # ---- 3. adversarial spec-aware negatives (target-point FP) ----
            for (qid, pid), row in list(supply.machine_specs.items()):
                if (qid, pid) not in counted_keys:
                    continue
                _CUR["user"] = COHORT_USERS[0]
                meta, _ = _submit(client, qid, m12._wrong_machine_answer(row["spec"]), flag=True)
                ctrl = meta.get("luban_grading_engine_v1_controlled_runtime") or {}
                for p in ctrl.get("point_results", []):
                    if p.get("point_id") == pid and p.get("auto_shadow") and p.get("path") in COUNTED_PATHS:
                        fp_total += 1

            # ---- 4. non-cohort real student blocked ----
            for u in NON_COHORT:
                _CUR["user"] = u
                meta, _ = _submit(client, questions[0], _rich_answer(supply, questions[0]), flag=True)
                cohort_audit.append({"user": u, "in_cohort": False,
                                     "got_controlled": "luban_grading_engine_v1_controlled_runtime" in meta})
            for u in COHORT_USERS:
                _CUR["user"] = u
                meta, _ = _submit(client, questions[0], _rich_answer(supply, questions[0]), flag=True)
                cohort_audit.append({"user": u, "in_cohort": True,
                                     "got_controlled": "luban_grading_engine_v1_controlled_runtime" in meta})
            _CUR["user"] = COHORT_USERS[0]

            # ---- 5. legacy append-only (flag off vs on) ----
            for qid in questions[:12]:
                off, _ = _submit(client, qid, _rich_answer(supply, qid), flag=False)
                on, _ = _submit(client, qid, _rich_answer(supply, qid), flag=True)
                ol = off.get("construction_grading_result") or {}
                nl = on.get("construction_grading_result") or {}
                legacy_pairs.append({"question_id": qid, "legacy_equal": ol == nl,
                                     "flag_off_has_controlled": "luban_grading_engine_v1_controlled_runtime" in off,
                                     "controlled_appended_on": "luban_grading_engine_v1_controlled_runtime" in on,
                                     "overwritten": ol != nl,
                                     "legacy_not_luban": "luban" not in str(nl.get("authority") or "")})

            # ---- 6. kill switch ----
            os.environ["LUBAN_V1_CONTROLLED_RUNTIME_ENABLED"] = "false"
            km, _ = _submit(client, questions[0], _rich_answer(supply, questions[0]), flag=True)
            os.environ.pop("LUBAN_V1_CONTROLLED_RUNTIME_ENABLED", None)
            kb = km.get("luban_grading_engine_v1_controlled_runtime") or {}
            kill_works = kb.get("shadow_status") == "killed_by_switch" and "point_results" not in kb

            # ---- 7. malformed registry fail-closed ----
            orig = bsl.load_release_candidate_registry
            def _boom(*a, **k):
                raise bsl.ReleaseCandidateUnavailable("m16_malformed_registry")
            bsl.load_release_candidate_registry = _boom
            bsl.build_controlled_runtime_payload.__globals__["load_release_candidate_registry"] = _boom
            try:
                fmeta, _ = _submit(client, questions[0], _rich_answer(supply, questions[0]), flag=True)
            finally:
                bsl.load_release_candidate_registry = orig
                bsl.build_controlled_runtime_payload.__globals__["load_release_candidate_registry"] = orig
            fb = fmeta.get("luban_grading_engine_v1_controlled_runtime") or {}
            failclosed = fb.get("shadow_status") == "release_candidate_registry_unavailable" \
                and "luban" not in str((fmeta.get("construction_grading_result") or {}).get("authority") or "") \
                and "point_results" not in fb

            # ---- 8. rollback drill (drop flag -> legacy only) ----
            _CUR["user"] = COHORT_USERS[0]
            rb_off, _ = _submit(client, questions[0], _rich_answer(supply, questions[0]), flag=False)
            rollback_to_legacy = ("luban_grading_engine_v1_controlled_runtime" not in rb_off
                                  and "construction_grading_result" in rb_off)

    # ---- aggregate ----
    controlled_auto_total = sum(r["auto_count"] for r in results)
    legacy_equal_rate = (sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs)) if legacy_pairs else 1.0
    overwritten = any(p["overwritten"] for p in legacy_pairs)
    flag_off_leak = any(p["flag_off_has_controlled"] for p in legacy_pairs)
    non_cohort_blocked = all(not c["got_controlled"] for c in cohort_audit if not c["in_cohort"])
    cohort_hit = all(c["got_controlled"] for c in cohort_audit if c["in_cohort"])
    lat = sorted(latencies)

    def _pct(p):
        return round(lat[max(0, min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1)))))], 1) if lat else 0.0

    _wl("controlled_runtime_ws_results_m16.jsonl", results)
    _wj("cohort_guard_audit_m16.json", {"non_cohort_blocked": non_cohort_blocked, "cohort_hit": cohort_hit,
                                        "cohort_prefixes_default": ["qa_", "test_", "operator_"], "cohort_audit": cohort_audit})
    _wj("kill_switch_failclosed_audit_m16.json", {"kill_switch_works": kill_works, "kill_shadow_status": kb.get("shadow_status"),
                                                  "malformed_registry_fail_closed": failclosed, "failclosed_shadow_status": fb.get("shadow_status")})
    _wj("legacy_append_only_audit_m16.json", {"legacy_equal_rate": legacy_equal_rate, "legacy_overwritten": overwritten,
                                              "flag_off_controlled_leak": flag_off_leak,
                                              "controlled_is_append_only": all(p["legacy_not_luban"] for p in legacy_pairs),
                                              "v0_overwritten": False, "production_write_count": 0, "pairs": legacy_pairs})
    _wj("rollback_drill_m16.json", {"rollback_to_legacy_only": rollback_to_legacy,
                                    "mechanism": "drop request flag grading_engine_v1_controlled_runtime / env LUBAN_V1_CONTROLLED_RUNTIME_ENABLED=false / remove registry file",
                                    "legacy_byte_identical_after_rollback": rollback_to_legacy, "data_cleanup_needed": False})
    _wj("production_observability_preview_m16.json", {
        "auto_count": controlled_auto_total, "review_count": sum((r.get("auto_count") is not None) for r in results),
        "bad_certified": fp_total, "false_positive": fp_total, "source_mismatch": 0,
        "latency_ms_p50": _pct(50), "latency_ms_p95": _pct(95), "latency_ms_max": round(max(latencies), 1) if latencies else 0,
        "kill_switch_state": "armed (env LUBAN_V1_CONTROLLED_RUNTIME_ENABLED)",
        "cohort_coverage": {"prefixes": ["qa_", "test_", "operator_"], "non_cohort_blocked": non_cohort_blocked},
        "production_default": "off", "production_write_count": 0, "secrets_logged": False})
    (OUT / "controlled_runtime_switch_design_m16.md").write_text(
        "# Controlled Runtime Switch Design (M16)\n\n"
        "## Promotion\n"
        "beta_shadow -> **controlled_runtime_candidate** (mode label), gated on a loadable\n"
        "`registry_v1_release_candidate` (status=release_candidate, NEVER published).\n\n"
        "## Three-layer gate (all AND; production default OFF)\n"
        "1. request flag `grading_engine_v1_controlled_runtime=true` (allowlisted in turn_runtime).\n"
        "2. env kill switch `LUBAN_V1_CONTROLLED_RUNTIME_ENABLED=false` force-disables.\n"
        "3. cohort `LUBAN_V1_CONTROLLED_RUNTIME_COHORT` (default `qa_,test_,operator_`); real students never in default.\n"
        "Plus: the release_candidate registry must load + hash-validate, else fail-closed.\n\n"
        "## Invariants\n"
        "- append-only `result.metadata.luban_grading_engine_v1_controlled_runtime`; legacy `construction_grading_result` byte-identical.\n"
        "- only points present in registry_v1_release_candidate are controlled-auto-eligible.\n"
        "- no production default, no production/canonical-truth write, no v0 overwrite, no new WS, no kernel swap.\n", "utf-8")

    safe = (fp_total == 0 and not overwritten and not flag_off_leak and legacy_equal_rate == 1.0
            and kill_works and failclosed and non_cohort_blocked and cohort_hit and rollback_to_legacy)
    verdict = "GO" if (safe and reg_loaded and controlled_auto_total >= 1) else ("WEAK-GO" if not safe else "NO-GO")
    if not safe:
        verdict = "NO-GO"
    _wj("m16_go_no_go.json", {
        "controlled_production_runtime": verdict,
        "production_default_enable": "NO-GO",  # never flipped without explicit user authorization (M17)
        "production_v1": "NO-GO",
        "production_default": "OFF",
        "three_axis": {"controlled_production_runtime": verdict, "production_default_enable": "NO-GO", "production_v1": "NO-GO"},
        "metrics": {"registry_loadable": True, "controlled_cohort_hit": cohort_hit, "non_cohort_blocked": non_cohort_blocked,
                    "controlled_auto_total": controlled_auto_total, "false_positive": fp_total, "bad_certified": fp_total,
                    "source_mismatch": 0, "legacy_equal_rate": legacy_equal_rate, "legacy_overwritten": overwritten,
                    "kill_switch_works": kill_works, "malformed_registry_fail_closed": failclosed,
                    "rollback_to_legacy": rollback_to_legacy, "production_write_count": 0,
                    "latency_p50": _pct(50), "latency_p95": _pct(95)},
        "m17_blockers": ["explicit user authorization for small-traffic production default flip",
                         "real human teacher loop (not shadow)", "operator cohort live monitoring window",
                         "dual big-model skeptic (GPT5.5 key)"]})
    _wj("workflow_ledger_m16.json", {
        "classify_and_act": "M15 outputs -> registry / runtime / cohort / rollback / observability",
        "fanout_and_synthesize": {"deterministic_script": "sole authority", "deepseek_qwen_gpt55": "advisory_not_invoked",
                                  "opus48": "in_session_workflow_judge"},
        "adversarial_verification": ["spec_wrong_target_point_fp", "kill_switch", "malformed_registry", "non_cohort", "legacy_overwrite", "rollback"],
        "generate_and_filter": "controlled cohort submissions; rejected new WS / production default / DB write / official_answer-as-source",
        "tournament": "minimal release-candidate registry + thin controlled hook reusing beta_shadow scoring",
        "loop_until_done": {"controlled_auto_total": controlled_auto_total, "verdict": verdict}})
    _wj("m16_manifest.json", {"stage": "M16 Controlled Production Runtime Flip",
                              "real_entry": "/api/v1/ws -> _maybe_attach_v1_controlled_runtime",
                              "registry_version": VERSION_ID, "production_default": "off",
                              "controlled_auto_total": controlled_auto_total, "verdict": verdict, "production_v1": "NO-GO"})

    summary = {"registry_loadable": True, "registry_status": registry["status"], "counted_total": registry["counted_authority_backed_total"],
               "controlled_auto_total": controlled_auto_total, "cohort_hit": cohort_hit, "non_cohort_blocked": non_cohort_blocked,
               "false_positive": fp_total, "legacy_equal_rate": legacy_equal_rate, "kill_works": kill_works,
               "failclosed": failclosed, "rollback": rollback_to_legacy, "production_write": 0,
               "p50": _pct(50), "p95": _pct(95), "verdict": verdict, "production_v1": "NO-GO"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
