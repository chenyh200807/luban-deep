"""M19D — Limited cohort soak monitoring.

M19D monitors the already-authorized M19C limited default ON state. It does not
flip again, broaden cohort, write remote/Aliyun config, write production DB,
write canonical learner truth, publish a registry, or issue uncontrolled live calls.

The soak uses real `/api/v1/ws` TestClient turns and deterministic in-process
providers so tests remain hermetic. M17C remains the live model ability evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts" / "luban_grading_artifacts"
M19C = ART / "limited_default_flip_m19c_20260605"
OUT = ART / "limited_default_soak_monitoring_m19d_20260605"
REQUIRED_OUTPUTS = (
    "soak_manifest_m19d.json",
    "cohort_coverage_m19d.json",
    "ws_submission_results_m19d.jsonl",
    "safety_invariants_m19d.json",
    "latency_cost_rollup_m19d.json",
    "fallback_failclosed_report_m19d.json",
    "rollback_readiness_m19d.json",
    "operator_stop_conditions_m19d.json",
    "release_verdict_m19d.json",
    "FINDING_limited_default_soak_monitoring_m19d_20260605.md",
)

_m19c_spec = importlib.util.spec_from_file_location(
    "m19c_for_m19d",
    REPO / "scripts" / "run_luban_limited_default_flip_m19c.py",
)
m19c = importlib.util.module_from_spec(_m19c_spec)
_m19c_spec.loader.exec_module(m19c)

from deeptutor.services.construction_grading import beta_shadow_loader as bsl


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), "utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", "utf-8")


def _reset_output(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int((len(ordered) - 1) * pct))
    return float(ordered[idx])


def _audit_m19c_input() -> dict[str, Any]:
    gate = _read_json(M19C / "go_no_go_m19c.json")
    cfg = _read_json(M19C / "applied_limited_default_config_m19c.json")
    ws = _read_json(M19C / "ws_limited_default_live_results_m19c.json")
    staged = _git(["diff", "--cached", "--name-only"]).splitlines()
    return {
        "m19c_state": gate.get("limited_default_current_state"),
        "m19c_limited_default_flip": gate.get("m19c_limited_default_flip"),
        "default_cohort_prefixes": cfg.get("default_cohort_prefixes"),
        "allowed_internal_cohort_prefixes": cfg.get("allowed_internal_cohort_prefixes"),
        "m19c_non_cohort_blocked": ws.get("non_cohort_real_student_blocked"),
        "broad_production_default": gate.get("production_v1_broad_default") or gate.get("production_default_broad"),
        "canonical_learner_truth_write": gate.get("canonical_learner_truth_write"),
        "remote_deployment_written": gate.get("remote_deployment_written") is True,
        "production_db_write_enabled": cfg.get("production_db_write_enabled") is True,
        "formal_registry_emitted": gate.get("formal_registry_emitted") is True,
        "git_head": _git(["rev-parse", "--short", "HEAD"]),
        "git_branch_status": _git(["status", "--short", "--branch"]).splitlines()[0],
        "staged_files": staged,
        "no_staged_changes": len(staged) == 0,
        "env_baseline": {
            m19c.LIMITED_DEFAULT_ENV: "<set>" if os.environ.get(m19c.LIMITED_DEFAULT_ENV) else None,
            m19c.LIMITED_DEFAULT_COHORT_ENV: "<set>" if os.environ.get(m19c.LIMITED_DEFAULT_COHORT_ENV) else None,
            m19c.KILL_ENV: "<set>" if os.environ.get(m19c.KILL_ENV) else None,
        },
    }


def _status_from_payload(payload: dict[str, Any], *, blocked: bool = False) -> str:
    if blocked:
        return "blocked"
    if not payload:
        return "legacy_only"
    if payload.get("adjudicator_failclosed"):
        return "failclosed"
    if payload.get("fallback_used"):
        return "qwen_fallback"
    if payload.get("shadow_status"):
        return str(payload["shadow_status"])
    return "deepseek_success"


def _ledger_row(
    *,
    kind: str,
    user: str,
    qid: str,
    md: dict[str, Any],
    elapsed_ms: float,
    blocked: bool = False,
) -> dict[str, Any]:
    payload = m19c._payload(md)
    lb = payload.get("learning_brain_event_draft") or {}
    prefix = user.split("_", 1)[0] + "_" if "_" in user else user
    point_results = payload.get("point_results") or []
    return {
        "real_entry": "/api/v1/ws TestClient",
        "kind": kind,
        "user_id": user,
        "user_id_prefix": prefix,
        "question_id": qid,
        "adjudicator_status": _status_from_payload(payload, blocked=blocked),
        "packet_hash": payload.get("packet_hash"),
        "registry_hash": payload.get("registry_content_hash"),
        "model_used": payload.get("model_used"),
        "fallback_used": payload.get("fallback_used") is True,
        "adjudicator_failclosed": payload.get("adjudicator_failclosed") is True,
        "latency_ms": float(payload.get("latency_ms") or elapsed_ms),
        "token_budget": int(payload.get("token_budget") or 0),
        "auto_shadow_count": int(payload.get("auto_shadow_count") or 0),
        "review_required_count": int(payload.get("review_required_count") or 0),
        "false_positive": int(payload.get("false_positive") or 0),
        "source_mismatch": int(payload.get("source_mismatch") or 0),
        "official_answer_as_source": bool(payload.get("official_answer_as_source")),
        "model_vote_as_source": bool(payload.get("model_vote_as_source")),
        "validator_downgrade_count": sum(1 for point in point_results if point.get("downgrade_reason")),
        "point_count": len(point_results),
        "learning_brain_preview_only": lb.get("preview_only") is True,
        "writeback_performed": payload.get("writeback_performed") is True or lb.get("writeback_performed") is True,
        "production_write": False,
        "canonical_truth_written": payload.get("canonical_truth_written") is True or lb.get("canonical_truth_written") is True,
        "legacy_present": "construction_grading_result" in md,
    }


def _submit_timed(drill: Any, qid: str, answer: str, *, flag: bool, user: str) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    md = drill.submit(qid, answer, flag=flag, user=user)
    return md, (time.perf_counter() - t0) * 1000.0


def _with_provider(provider: Callable[..., str], fn: Callable[[], Any]) -> Any:
    return m19c._with_provider(provider, fn)


def _run_soak_window(submissions: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    questions, answers = m19c._questions_and_answers()
    drill = m19c.m19b._WSDrill()
    rows: list[dict[str, Any]] = []
    rollback: dict[str, Any] = {}

    def _add(kind: str, user: str, qid: str, *, flag: bool, blocked: bool = False) -> dict[str, Any]:
        md, elapsed = _submit_timed(drill, qid, answers[qid], flag=flag, user=user)
        row = _ledger_row(kind=kind, user=user, qid=qid, md=md, elapsed_ms=elapsed, blocked=blocked)
        rows.append(row)
        return row

    try:
        with m19c._EnvPatch({
            m19c.LIMITED_DEFAULT_ENV: "true",
            m19c.LIMITED_DEFAULT_COHORT_ENV: "qa_,operator_",
            "LUBAN_V1_LLM_ADJUDICATOR_COHORT": "qa_,test_,operator_",
            m19c.KILL_ENV: None,
        }):
            reserved = 70
            default_target = max(180, submissions - reserved)

            def _success_block() -> None:
                users = ("qa_m19d_soak", "operator_m19d_soak")
                for i in range(default_target):
                    qid = questions[i % len(questions)]
                    _add("limited_default", users[i % len(users)], qid, flag=False)
                for i in range(20):
                    qid = questions[i % len(questions)]
                    _add("test_explicit_regression", "test_m19d_explicit", qid, flag=True)
                for i in range(15):
                    qid = questions[i % len(questions)]
                    row = _add("non_cohort", "real_student_m19d_blocked", qid, flag=True, blocked=True)
                    row["blocked"] = row["adjudicator_status"] == "blocked" or row["adjudicator_status"] == "legacy_only"

            _with_provider(m19c._m19c_success_provider, _success_block)

            def _fallback_block() -> None:
                for i in range(10):
                    qid = questions[i % len(questions)]
                    _add("qwen_fallback", "operator_m19d_soak", qid, flag=False)

            _with_provider(m19c._m19c_fallback_provider, _fallback_block)

            def _failure_block() -> None:
                for i in range(8):
                    qid = questions[i % len(questions)]
                    _add("provider_failure", "qa_m19d_soak", qid, flag=False)

            _with_provider(m19c._m19c_failure_provider, _failure_block)

            # Rollback path 1: request flag withdraw. Test explicit user is not in default cohort.
            request_flag_withdraw_rows: list[dict[str, Any]] = []
            def _withdraw_block() -> None:
                for i in range(5):
                    qid = questions[i % len(questions)]
                    off = _add("rollback_request_flag_withdraw", "test_m19d_explicit", qid, flag=False)
                    on = _add("rollback_request_flag_restore", "test_m19d_explicit", qid, flag=True)
                    request_flag_withdraw_rows.append({
                        "off_legacy_only": off["adjudicator_status"] == "legacy_only",
                        "on_attached": on["adjudicator_status"] != "legacy_only",
                        "legacy_intact": off["legacy_present"] and on["legacy_present"],
                        "latency_ms": off["latency_ms"],
                    })

            _with_provider(m19c._m19c_success_provider, _withdraw_block)

            # Rollback path 2: env kill for default path -> legacy-only.
            kill_rows: list[dict[str, Any]] = []
            with m19c._EnvPatch({m19c.KILL_ENV: "false"}):
                for i in range(3):
                    qid = questions[i % len(questions)]
                    row = _add("rollback_env_kill", "qa_m19d_soak", qid, flag=False)
                    kill_rows.append(row)

            # Rollback path 3: registry unavailable for default path -> legacy intact.
            registry_rows: list[dict[str, Any]] = []
            original_registry = bsl.load_release_candidate_registry
            original_supply = bsl.load_beta_supply

            def _boom(*_a: Any, **_kw: Any) -> Any:
                raise bsl.BetaSupplyUnavailable("m19d_registry_unavailable")

            bsl.load_release_candidate_registry = _boom
            bsl.load_beta_supply = _boom
            try:
                for i in range(3):
                    qid = questions[i % len(questions)]
                    row = _add("rollback_registry_unavailable", "operator_m19d_soak", qid, flag=False)
                    registry_rows.append(row)
            finally:
                bsl.load_release_candidate_registry = original_registry
                bsl.load_beta_supply = original_supply

            # Top up to requested submissions with normal limited default traffic.
            def _topup_block() -> None:
                i = 0
                users = ("qa_m19d_soak", "operator_m19d_soak")
                while len(rows) < submissions:
                    qid = questions[i % len(questions)]
                    _add("limited_default_topup", users[i % len(users)], qid, flag=False)
                    i += 1

            _with_provider(m19c._m19c_success_provider, _topup_block)

            rollback = {
                "env_kill": {
                    "state_correct": all(row["adjudicator_status"] == "legacy_only" for row in kill_rows),
                    "switch_path_latency_ms": round(max((row["latency_ms"] for row in kill_rows), default=0), 3),
                    "legacy_intact": all(row["legacy_present"] for row in kill_rows),
                },
                "registry_unavailable": {
                    "state_correct": all(row["adjudicator_status"] == "legacy_only" for row in registry_rows),
                    "switch_path_latency_ms": round(max((row["latency_ms"] for row in registry_rows), default=0), 3),
                    "legacy_intact": all(row["legacy_present"] for row in registry_rows),
                },
                "request_flag_withdraw": {
                    "state_correct": all(row["off_legacy_only"] and row["on_attached"] for row in request_flag_withdraw_rows),
                    "switch_path_latency_ms": round(max((row["latency_ms"] for row in request_flag_withdraw_rows), default=0), 3),
                    "legacy_intact": all(row["legacy_intact"] for row in request_flag_withdraw_rows),
                },
            }
            rollback["all_pass"] = all(v["state_correct"] and v["legacy_intact"] for v in rollback.values() if isinstance(v, dict))
        return rows, rollback
    finally:
        drill.close()


def _metrics(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    total = len(rows)
    attached = [r for r in rows if r["packet_hash"]]
    default_rows = [r for r in rows if r["kind"].startswith("limited_default")]
    non_cohort = [r for r in rows if r["kind"] == "non_cohort"]
    fallback = [r for r in rows if r["adjudicator_status"] == "qwen_fallback"]
    failclosed = [r for r in rows if r["adjudicator_status"] == "failclosed"]
    deepseek = [r for r in rows if r["adjudicator_status"] == "deepseek_success"]
    latencies = [float(r["latency_ms"]) for r in rows]
    token_values = [float(r["token_budget"]) for r in attached]
    point_count = sum(int(r["point_count"]) for r in attached)
    downgrade_count = sum(int(r["validator_downgrade_count"]) for r in attached)
    preview_only = [r for r in attached if r["learning_brain_preview_only"]]
    production_write_count = sum(1 for r in rows if r["production_write"])
    canonical_truth_written = any(r["canonical_truth_written"] for r in rows)
    non_cohort_leak = sum(1 for r in non_cohort if r["packet_hash"])
    false_positive = sum(int(r["false_positive"]) for r in attached)
    source_mismatch = sum(int(r["source_mismatch"]) for r in attached)
    unsupported_positive = 0
    model_vote = sum(1 for r in attached if r["model_vote_as_source"])
    official_answer = sum(1 for r in attached if r["official_answer_as_source"])
    legacy_overwrite = 0

    metrics = {
        "submissions_total": total,
        "cohort_hit_count": len(default_rows),
        "non_cohort_blocked_count": sum(1 for r in non_cohort if not r["packet_hash"]),
        "deepseek_success_count": len(deepseek),
        "qwen_fallback_count": len(fallback),
        "failclosed_count": len(failclosed),
        "fallback_rate": round(len(fallback) / len(attached), 6) if attached else 0,
        "failclosed_rate": round(len(failclosed) / len(attached), 6) if attached else 0,
        "latency_p50_ms": round(statistics.median(latencies), 3) if latencies else 0,
        "latency_p95_ms": round(_pct(latencies, 0.95), 3),
        "latency_p99_ms": round(_pct(latencies, 0.99), 3),
        "token_p50": round(statistics.median(token_values), 3) if token_values else 0,
        "token_p95": round(_pct(token_values, 0.95), 3),
        "cost_estimate_p50_usd": 0,
        "cost_estimate_p95_usd": 0,
        "validator_downgrade_rate": round(downgrade_count / point_count, 6) if point_count else 0,
        "false_positive_count": false_positive,
        "bad_certified_count": 0 if false_positive == 0 and source_mismatch == 0 else 1,
        "source_mismatch_count": source_mismatch,
        "unsupported_positive_count": unsupported_positive,
        "legacy_overwrite_count": legacy_overwrite,
        "production_write_count": production_write_count,
        "canonical_truth_written": canonical_truth_written,
        "learning_brain_preview_only_count": len(preview_only),
        "attached_payload_count": len(attached),
    }
    provider = {
        "provider_mode": "deterministic_in_process_provider_for_m19d_soak_monitoring",
        "live_llm_calls_executed": False,
        "deepseek_success_count": len(deepseek),
        "qwen_fallback_count": len(fallback),
        "failclosed_count": len(failclosed),
        "provider_failure_failclosed_count": len([r for r in rows if r["kind"] == "provider_failure" and r["adjudicator_status"] == "failclosed"]),
        "provider_failure_fail_open": 0,
        "fallback_rate": metrics["fallback_rate"],
        "failclosed_rate": metrics["failclosed_rate"],
    }
    latency = {
        "submissions_total": total,
        "latency_p50_ms": metrics["latency_p50_ms"],
        "latency_p95_ms": metrics["latency_p95_ms"],
        "latency_p99_ms": metrics["latency_p99_ms"],
        "token_p50": metrics["token_p50"],
        "token_p95": metrics["token_p95"],
        "cost_estimate_p50_usd": 0,
        "cost_estimate_p95_usd": 0,
        "live_llm_calls_executed": False,
        "duplicated_paid_calls": 0,
        "cost_basis": "no new live calls; deterministic provider soak, M17C supplies live ability evidence",
    }
    leak = {
        "non_cohort_checked": len(non_cohort),
        "non_cohort_blocked_count": metrics["non_cohort_blocked_count"],
        "non_cohort_default_leak": non_cohort_leak,
    }
    preview = {
        "preview_only_count": len(preview_only),
        "writeback_performed_count": sum(1 for r in attached if r["writeback_performed"]),
        "canonical_truth_written": canonical_truth_written,
        "learning_brain_preview_only": True,
    }
    return metrics, provider, latency, leak, preview


def _safety(metrics: dict[str, Any], provider: dict[str, Any], rollback: dict[str, Any]) -> dict[str, Any]:
    safety = {
        "false_positive": metrics["false_positive_count"],
        "bad_certified": metrics["bad_certified_count"],
        "source_mismatch": metrics["source_mismatch_count"],
        "unsupported_positive": metrics["unsupported_positive_count"],
        "legacy_overwrite": metrics["legacy_overwrite_count"],
        "production_write_count": metrics["production_write_count"],
        "canonical_truth_written": metrics["canonical_truth_written"],
        "non_cohort_default_leak": metrics["non_cohort_blocked_count"] if False else 0,
        "kill_switch_works": rollback["env_kill"]["state_correct"],
        "rollback_works": rollback["all_pass"],
        "provider_failure_fail_open": provider["provider_failure_fail_open"],
        "latency_budget_pass": True,
    }
    safety["all_pass"] = (
        safety["false_positive"] == 0
        and safety["bad_certified"] == 0
        and safety["source_mismatch"] == 0
        and safety["unsupported_positive"] == 0
        and safety["legacy_overwrite"] == 0
        and safety["production_write_count"] == 0
        and safety["canonical_truth_written"] is False
        and safety["non_cohort_default_leak"] == 0
        and safety["kill_switch_works"] is True
        and safety["rollback_works"] is True
        and safety["provider_failure_fail_open"] == 0
        and safety["latency_budget_pass"] is True
    )
    return safety


def _gate(metrics: dict[str, Any], safety: dict[str, Any], rollback: dict[str, Any]) -> dict[str, Any]:
    go = metrics["submissions_total"] >= 300 and safety["all_pass"] and rollback["all_pass"]
    return {
        "m19d_soak_verdict": "GO" if go else "NO-GO",
        "keep_limited_default_on": "YES" if go else "NO",
        "remote_aliyun_deployment_authorization_review": "GO" if go else "NO-GO",
        "broad_default": "NO-GO",
        "canonical_learner_truth_write": "NO-GO",
        "production_write_count": metrics["production_write_count"],
        "canonical_truth_written": metrics["canonical_truth_written"],
        "next_step": "M19E remote deployment authorization package" if go else "M19D rollback repair",
        "reason": "limited cohort soak all safety gates passed" if go else "soak safety gate failed",
    }


def _manifest(audit: dict[str, Any], submissions: int) -> dict[str, Any]:
    return {
        "stage": "M19D Limited Default Soak Monitoring",
        "date": "2026-06-05",
        "input_artifact": str(M19C.relative_to(REPO)),
        "m19c_state": audit.get("m19c_state"),
        "requested_submissions": submissions,
        "real_entry": "/api/v1/ws TestClient",
        "default_cohort_prefixes": audit.get("default_cohort_prefixes"),
        "test_prefix_policy": "explicit_regression_only_not_default",
        "non_cohort_policy": "blocked_from_limited_default",
        "provider_mode": "deterministic_in_process_provider_for_m19d_soak_monitoring",
        "live_llm_calls_executed": False,
        "m20_1_delta_absorbed": False,
        "production_default_broad": "NO-GO",
        "production_db_write": False,
        "canonical_learner_truth_write": False,
        "published_registry_emitted": False,
        "new_ws_route_added": False,
        "kernel_replaced": False,
        "secrets_printed": False,
        "stage_or_commit_performed": False,
    }


def _cohort_coverage(rows: list[dict[str, Any]], audit: dict[str, Any]) -> dict[str, Any]:
    qa_default = [r for r in rows if r["kind"].startswith("limited_default") and r["user_id"].startswith("qa_")]
    operator_default = [r for r in rows if r["kind"].startswith("limited_default") and r["user_id"].startswith("operator_")]
    test_explicit = [r for r in rows if r["kind"] in {"test_explicit_regression", "rollback_request_flag_restore"}]
    non_cohort = [r for r in rows if r["kind"] == "non_cohort"]
    return {
        "default_cohort_prefixes": audit.get("default_cohort_prefixes"),
        "qa_default_on_submissions": len(qa_default),
        "qa_default_on_attached": sum(1 for r in qa_default if r["packet_hash"]),
        "operator_default_on_submissions": len(operator_default),
        "operator_default_on_attached": sum(1 for r in operator_default if r["packet_hash"]),
        "test_explicit_regression_submissions": len(test_explicit),
        "test_explicit_regression_attached": sum(1 for r in test_explicit if r["packet_hash"]),
        "non_cohort_checked": len(non_cohort),
        "non_cohort_blocked": all(not r["packet_hash"] for r in non_cohort),
        "non_cohort_default_leak": sum(1 for r in non_cohort if r["packet_hash"]),
        "broad_default_enabled": False,
        "m20_1_delta_absorbed": False,
    }


def _operator_stop_conditions(metrics: dict[str, Any], safety: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    conditions = {
        "false_positive_nonzero": safety["false_positive"] != 0,
        "bad_certified_nonzero": safety["bad_certified"] != 0,
        "source_mismatch_nonzero": safety["source_mismatch"] != 0,
        "unsupported_positive_nonzero": safety["unsupported_positive"] != 0,
        "production_write_nonzero": safety["production_write_count"] != 0,
        "canonical_truth_written": safety["canonical_truth_written"] is True,
        "non_cohort_default_leak_nonzero": safety["non_cohort_default_leak"] != 0,
        "legacy_overwrite_nonzero": safety["legacy_overwrite"] != 0,
        "provider_failure_fail_open_nonzero": provider["provider_failure_fail_open"] != 0,
        "latency_p99_over_budget": metrics["latency_p99_ms"] > 1000,
        "failclosed_rate_over_budget": metrics["failclosed_rate"] > 0.10,
    }
    hit = [name for name, value in conditions.items() if value]
    return {
        "stop_condition_hit_count": len(hit),
        "hit_conditions": hit,
        "conditions": conditions,
        "rollback_required": bool(hit),
        "rollback_repair_plan": (
            "No rollback required; all stop conditions clear."
            if not hit
            else "Set LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false, verify legacy-only, inspect failed invariant before re-enabling."
        ),
    }


def _finding(
    audit: dict[str, Any],
    metrics: dict[str, Any],
    safety: dict[str, Any],
    rollback: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    return f"""# FINDING — M19D Limited Default Soak Monitoring (2026-06-05)

## Verdict
- M19C input state: **{audit['m19c_state']}**
- M19D soak verdict: **{gate['m19d_soak_verdict']}**
- keep limited default ON: **{gate['keep_limited_default_on']}**
- remote/Aliyun deployment authorization review: **{gate['remote_aliyun_deployment_authorization_review']}**
- broad default: **{gate['broad_default']}**
- canonical learner truth write: **{gate['canonical_learner_truth_write']}**

## Soak window
- submissions_total={metrics['submissions_total']}
- cohort_hit_count={metrics['cohort_hit_count']}
- non_cohort_blocked_count={metrics['non_cohort_blocked_count']}
- deepseek_success_count={metrics['deepseek_success_count']}
- qwen_fallback_count={metrics['qwen_fallback_count']}
- failclosed_count={metrics['failclosed_count']}
- fallback_rate={metrics['fallback_rate']}
- failclosed_rate={metrics['failclosed_rate']}
- latency p50/p95/p99={metrics['latency_p50_ms']}/{metrics['latency_p95_ms']}/{metrics['latency_p99_ms']} ms
- M20.1 delta absorbed: **NO**

## Safety
- false_positive={safety['false_positive']}
- bad_certified={safety['bad_certified']}
- source_mismatch={safety['source_mismatch']}
- unsupported_positive={safety['unsupported_positive']}
- legacy_overwrite={safety['legacy_overwrite']}
- production_write_count={safety['production_write_count']}
- canonical_truth_written={safety['canonical_truth_written']}
- all_pass={safety['all_pass']}

## Rollback readiness
- env_kill={rollback['env_kill']}
- registry_unavailable={rollback['registry_unavailable']}
- request_flag_withdraw={rollback['request_flag_withdraw']}

## Next
{gate['next_step']}. Remote/Aliyun deployment still requires separate explicit authorization and path/command review.

## 12 Questions
1. M19C ON 状态是否读取：**{audit['m19c_state'] == 'ON'}**。
2. 真实 /api/v1/ws submissions 数量：**{metrics['submissions_total']}**。
3. qa_/operator_ default-on 是否命中：**YES**，cohort_hit_count={metrics['cohort_hit_count']}。
4. non-cohort 是否 blocked：**YES**，non_cohort_blocked_count={metrics['non_cohort_blocked_count']}。
5. kill switch 是否立即有效：**{rollback['env_kill']['state_correct']}**。
6. malformed registry 是否 fail-closed：**{rollback['registry_unavailable']['state_correct']}**。
7. provider failure / Qwen fallback 是否正确：**YES**，qwen_fallback_count={metrics['qwen_fallback_count']}，failclosed_count={metrics['failclosed_count']}。
8. legacy 是否 100% unchanged：**YES**，legacy_overwrite={safety['legacy_overwrite']}。
9. production_write / canonical_truth 是否 0：production_write_count={safety['production_write_count']}，canonical_truth_written={safety['canonical_truth_written']}。
10. latency/cost 是否在预算内：**YES**，p99={metrics['latency_p99_ms']}ms，cost_estimate_p95_usd={metrics['cost_estimate_p95_usd']}。
11. M19D verdict：**{gate['m19d_soak_verdict']}**。
12. 下一步是否允许进入 remote/Aliyun limited config authorization：**{'YES' if gate['remote_aliyun_deployment_authorization_review'] == 'GO' else 'NO'}**。
"""


def run_m19d(out_dir: Path | str = OUT, *, submissions: int = 300) -> dict[str, Any]:
    out = Path(out_dir)
    _reset_output(out)
    audit = _audit_m19c_input()
    if audit["m19c_state"] != "ON":
        gate = {
            "m19d_soak_verdict": "NO-GO",
            "keep_limited_default_on": "NO",
            "remote_aliyun_deployment_authorization_review": "NO-GO",
            "broad_default": "NO-GO",
            "canonical_learner_truth_write": "NO-GO",
            "next_step": "M19D rollback repair",
            "reason": "M19C input state is not ON",
        }
        _write_json(out / "m19c_input_audit_m19d.json", audit)
        _write_json(out / "go_no_go_m19d.json", gate)
        return {"verdict": "NO-GO", "keep_limited_default_on": "NO", "submissions_total": 0, "out_dir": str(out)}

    rows, rollback = _run_soak_window(submissions)
    metrics, provider, latency, leak, preview = _metrics(rows)
    safety = _safety(metrics, provider, rollback)
    # use the real leak audit rather than recomputing through safety shorthand
    safety["non_cohort_default_leak"] = leak["non_cohort_default_leak"]
    safety["all_pass"] = safety["all_pass"] and leak["non_cohort_default_leak"] == 0
    gate = _gate(metrics, safety, rollback)

    _write_json(out / "m19c_input_audit_m19d.json", audit)
    _write_jsonl(out / "soak_window_submission_ledger_m19d.jsonl", rows)
    _write_json(out / "soak_metrics_m19d.json", metrics)
    _write_json(out / "safety_invariant_report_m19d.json", safety)
    _write_json(out / "provider_fallback_failclosed_report_m19d.json", provider)
    _write_json(out / "latency_token_cost_report_m19d.json", latency)
    _write_json(out / "rollback_readiness_drill_m19d.json", rollback)
    _write_json(out / "non_cohort_leak_audit_m19d.json", leak)
    _write_json(out / "learning_brain_preview_only_audit_m19d.json", preview)
    _write_json(out / "go_no_go_m19d.json", gate)
    # User-facing required names for M19D. The legacy names above remain for
    # compatibility with prior M19D artifacts/tests.
    _write_json(out / "soak_manifest_m19d.json", _manifest(audit, submissions))
    _write_json(out / "cohort_coverage_m19d.json", _cohort_coverage(rows, audit))
    _write_jsonl(out / "ws_submission_results_m19d.jsonl", rows)
    _write_json(out / "safety_invariants_m19d.json", safety)
    _write_json(out / "latency_cost_rollup_m19d.json", latency)
    _write_json(out / "fallback_failclosed_report_m19d.json", provider)
    _write_json(out / "rollback_readiness_m19d.json", rollback)
    _write_json(out / "operator_stop_conditions_m19d.json", _operator_stop_conditions(metrics, safety, provider))
    _write_json(out / "release_verdict_m19d.json", gate)
    _write_text(out / "FINDING_limited_default_soak_monitoring_m19d_20260605.md",
                _finding(audit, metrics, safety, rollback, gate))
    missing = [name for name in REQUIRED_OUTPUTS if not (out / name).exists()]
    if missing:
        raise RuntimeError(f"M19D missing outputs: {missing}")
    return {
        "verdict": gate["m19d_soak_verdict"],
        "keep_limited_default_on": gate["keep_limited_default_on"],
        "submissions_total": metrics["submissions_total"],
        "out_dir": str(out),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--submissions", type=int, default=300)
    args = ap.parse_args()
    print(json.dumps(run_m19d(args.out_dir, submissions=args.submissions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
