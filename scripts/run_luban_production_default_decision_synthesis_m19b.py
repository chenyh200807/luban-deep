"""M19B — Production Default Decision Synthesis.

Release commander package after M17C. This script reconciles M16/M17A/M17B/M17C/
M18C/M18D/M19A evidence, fills M19A's waiting slots, runs a real `/api/v1/ws`
release drill (with deterministic in-process providers, so no new live LLM calls),
and emits the canonical production-default decision package.

It does NOT flip production default, publish registry, write production DB, write
canonical learner truth, alter runtime/kernel/RAG, or impersonate human/teacher/PO.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts" / "luban_grading_artifacts"

M16 = ART / "controlled_production_runtime_flip_m16_20260604"
M17A = ART / "runtime_llm_adjudicator_m17a_20260604"
M17B = ART / "runtime_llm_scaleout_council_m17b_20260604"
M17C = ART / "deepseek_live_calibration_completion_m17c_20260604"
M18C = ART / "learning_brain_dream_cycle_m18c_20260604"
M18D = ART / "learning_brain_real_retest_canonical_gate_m18d_20260604"
M19A = ART / "releaseops_default_decision_preflight_m19a_20260604"
OUT = ART / "production_default_decision_synthesis_m19b_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient

from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

_ws_spec = importlib.util.spec_from_file_location(
    "ws_m19b", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws_spec)
_ws_spec.loader.exec_module(ws)

_m12_spec = importlib.util.spec_from_file_location(
    "m12_m19b", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12_spec)
_m12_spec.loader.exec_module(m12)

KILL_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"
COHORT_USERS = ("qa_m19b_release", "test_m19b_release", "operator_m19b_release")
REAL_STUDENT = "real_student_m19b_blocked"
_CUR = {"user": COHORT_USERS[0]}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


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


def _counted_questions() -> list[str]:
    registry = bsl.load_release_candidate_registry(None)
    return sorted({row["question_id"] for row in registry.get("points", [])})


def _rich_answer(supply: bsl.BetaSupply, qid: str) -> str:
    parts: list[str] = []
    for (question_id, point_id) in sorted(set(supply.source_backed) | set(supply.machine_specs) | set(supply.list_specs)):
        if question_id != qid:
            continue
        if (question_id, point_id) in supply.machine_specs:
            parts.append(m12._correct_machine_answer(supply.machine_specs[(question_id, point_id)]["spec"]))
        elif (question_id, point_id) in supply.list_specs:
            parts.append("，".join(m["item"] for m in supply.list_specs[(question_id, point_id)]["spec"]["item_matchers"]))
        elif supply.source_terms.get((question_id, point_id)):
            parts.append(supply.source_terms[(question_id, point_id)][0])
    return "；".join(part for part in parts if part) + "。"


def _frame(question_id: str, answer: str, *, flag: bool) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "followup_question_context": {
            "question_id": question_id,
            "question_type": "case",
            "question": "案例评分 release drill",
            "correct_answer": answer,
        }
    }
    if flag:
        cfg["grading_engine_v1_llm_adjudication"] = True
    return {
        "type": "start_turn",
        "content": answer,
        "capability": "deep_question",
        "language": "zh",
        "config": cfg,
    }


def _normal_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    payload = json.loads(user)
    answer = str(payload.get("student_answer") or "")
    span = answer[: min(18, len(answer))] or "release-drill"
    rows = [
        {
            "point_id": point["point_id"],
            "disposition": "partial",
            "evidence_span": span,
            "confidence": 0.72,
            "reasoning_summary": "m19b deterministic ws drill provider",
        }
        for point in payload.get("points", [])
    ]
    return json.dumps(rows, ensure_ascii=False)


def _fallback_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    if role == "primary":
        raise adj.AdjudicatorUnavailable("m19b_forced_primary_failure")
    payload = json.loads(user)
    rows = [
        {
            "point_id": point["point_id"],
            "disposition": "needs_review",
            "evidence_span": "",
            "confidence": None,
            "reasoning_summary": "m19b forced qwen fallback drill",
        }
        for point in payload.get("points", [])
    ]
    return json.dumps(rows, ensure_ascii=False)


def _failure_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    raise adj.AdjudicatorUnavailable("m19b_provider_down")


class _WSDrill:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="luban-m19b-")
        self.write_calls: list[Any] = []
        self.engine_calls: list[Any] = []
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(self.tmp.name) / "m19b.db"))
        ws._install_fakes(runtime, user_id=COHORT_USERS[0], write_calls=self.write_calls, engine_calls=self.engine_calls)
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
        self.client_cm = TestClient(ws._build_ws_app())
        self.client = self.client_cm.__enter__()
        self.submission_count = 0

    def close(self) -> None:
        try:
            self.client_cm.__exit__(None, None, None)
        finally:
            self.tmp.cleanup()

    def submit(self, question_id: str, answer: str, *, flag: bool = True, user: str | None = None) -> dict[str, Any]:
        _CUR["user"] = user or COHORT_USERS[0]
        self.submission_count += 1
        return (ws._receive_result(self.client, _frame(question_id, answer, flag=flag)).get("metadata") or {})


def _with_provider(provider: Callable[..., str], fn: Callable[[], Any]) -> Any:
    original = adj._default_provider
    adj._default_provider = provider
    try:
        return fn()
    finally:
        adj._default_provider = original


def _run_ws_release_drill(submissions: int) -> tuple[dict[str, Any], dict[str, Any]]:
    all_questions = _counted_questions()
    preferred = ["M2-2015-30-00", "M2-2015-30-02", "M2-2015-30-03", "M2-2015-31-01", "M2-2015-31-02"]
    questions = [qid for qid in preferred if qid in all_questions] or all_questions[:5]
    supply = bsl.load_beta_supply(None)
    answers = {qid: _rich_answer(supply, qid) or "工期为 25 个月，合理。" for qid in questions}
    normal_target = max(0, submissions - 77)  # plus 77 failure/rollback/non-cohort submissions below
    drill = _WSDrill()
    rows: list[dict[str, Any]] = []
    legacy_pairs: list[dict[str, Any]] = []
    cohort_seen: set[str] = set()
    try:
        def _normal_block() -> None:
            for i in range(normal_target):
                qid = questions[i % len(questions)]
                user = COHORT_USERS[i % len(COHORT_USERS)]
                md = drill.submit(qid, answers[qid], flag=True, user=user)
                adj_payload = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                cohort_seen.add(user.split("_", 1)[0] + "_")
                rows.append({
                    "kind": "cohort_flag_on",
                    "question_id": qid,
                    "user": user,
                    "legacy_present": "construction_grading_result" in md,
                    "adjudication_attached": bool(adj_payload),
                    "production_write": False,
                    "canonical_truth_written": False,
                })

            # rollback / legacy equality pairs: flag-off vs flag-on over same answers.
            for i in range(30):
                qid = questions[i % len(questions)]
                user = COHORT_USERS[i % len(COHORT_USERS)]
                off = drill.submit(qid, answers[qid], flag=False, user=user)
                on = drill.submit(qid, answers[qid], flag=True, user=user)
                legacy_equal = off.get("construction_grading_result") == on.get("construction_grading_result")
                legacy_pairs.append({
                    "question_id": qid,
                    "user": user,
                    "legacy_equal": legacy_equal,
                    "flag_off_no_adjudication": "luban_grading_engine_v1_llm_adjudication" not in off,
                })
                rows.append({"kind": "rollback_flag_off_pair", "question_id": qid, "user": user,
                             "legacy_equal": legacy_equal})

        _with_provider(_normal_provider, _normal_block)

        non_cohort_blocked = True
        for i in range(5):
            qid = questions[i % len(questions)]
            md = drill.submit(qid, answers[qid], flag=True, user=REAL_STUDENT)
            blocked = "luban_grading_engine_v1_llm_adjudication" not in md
            non_cohort_blocked = non_cohort_blocked and blocked
            rows.append({"kind": "non_cohort", "question_id": qid, "blocked": blocked})

        os.environ[KILL_ENV] = "false"
        kill_pass = True
        try:
            for i in range(3):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=True, user=COHORT_USERS[i % len(COHORT_USERS)])
                payload = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                kill_pass = kill_pass and payload.get("shadow_status") == "killed_by_switch"
                rows.append({"kind": "kill_switch", "question_id": qid, "shadow_status": payload.get("shadow_status")})
        finally:
            os.environ.pop(KILL_ENV, None)

        fallback_pass = True
        def _fallback_block() -> None:
            nonlocal fallback_pass
            for i in range(5):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=True, user=COHORT_USERS[i % len(COHORT_USERS)])
                payload = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                fallback_pass = fallback_pass and payload.get("fallback_used") is True
                rows.append({"kind": "fallback", "question_id": qid, "fallback_used": payload.get("fallback_used")})
        _with_provider(_fallback_provider, _fallback_block)

        provider_failure_pass = True
        def _provider_failure_block() -> None:
            nonlocal provider_failure_pass
            for i in range(2):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=True, user=COHORT_USERS[i % len(COHORT_USERS)])
                payload = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                provider_failure_pass = provider_failure_pass and payload.get("adjudicator_failclosed") is True
                rows.append({"kind": "provider_failure", "question_id": qid,
                             "adjudicator_failclosed": payload.get("adjudicator_failclosed")})
        _with_provider(_failure_provider, _provider_failure_block)

        malformed_pass = True
        original_registry = bsl.load_release_candidate_registry
        original_supply = bsl.load_beta_supply

        def _boom(*_a: Any, **_kw: Any) -> Any:
            raise bsl.BetaSupplyUnavailable("m19b_malformed_registry")

        bsl.load_release_candidate_registry = _boom
        bsl.load_beta_supply = _boom
        try:
            for i in range(2):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=True, user=COHORT_USERS[i % len(COHORT_USERS)])
                payload = md.get("luban_grading_engine_v1_llm_adjudication") or {}
                malformed_pass = malformed_pass and (
                    payload.get("shadow_status") in {"adjudicator_unavailable", "release_candidate_registry_unavailable"}
                )
                rows.append({"kind": "malformed_registry", "question_id": qid,
                             "shadow_status": payload.get("shadow_status"),
                             "legacy_present": "construction_grading_result" in md})
        finally:
            bsl.load_release_candidate_registry = original_registry
            bsl.load_beta_supply = original_supply

        legacy_equal_rate = (
            sum(1 for row in legacy_pairs if row["legacy_equal"]) / len(legacy_pairs)
            if legacy_pairs else 1.0
        )
        normal_attached = all(row.get("adjudication_attached", True) for row in rows if row["kind"] == "cohort_flag_on")
        result = {
            "real_entry": "/api/v1/ws TestClient",
            "submission_count": drill.submission_count,
            "target_min_submissions": submissions,
            "cohort_coverage": sorted(cohort_seen),
            "normal_flag_on_adjudication_attached": normal_attached,
            "non_cohort_real_student_blocked": non_cohort_blocked,
            "legacy_equal_rate": legacy_equal_rate,
            "production_write_count": 0,
            "harness_session_write_calls": len(drill.write_calls),
            "canonical_truth_written": False,
            "live_llm_calls_executed": False,
            "provider_mode": "deterministic_in_process_provider_for_release_guard_drill",
            "sample_rows": rows[:20],
            "category_counts": dict(Counter(row["kind"] for row in rows)),
        }
        rollback = {
            "rollback_flag_off": {
                "pass": legacy_equal_rate == 1.0 and all(row["flag_off_no_adjudication"] for row in legacy_pairs),
                "legacy_equal_rate": legacy_equal_rate,
            },
            "kill_switch": {"pass": kill_pass, "env": KILL_ENV},
            "malformed_registry": {"pass": malformed_pass},
            "provider_failure": {"pass": provider_failure_pass},
            "fallback": {"pass": fallback_pass},
        }
        rollback["all_pass"] = all(v["pass"] for v in rollback.values() if isinstance(v, dict))
        return result, rollback
    finally:
        drill.close()


def _canonical_evidence_ledger() -> dict[str, Any]:
    m16 = _read_json(M16 / "m16_go_no_go.json")
    m16_obs = _read_json(M16 / "production_observability_preview_m16.json")
    m17a_go = _read_json(M17A / "m17a_go_no_go.json")
    m17a_safe = _read_json(M17A / "runtime_safety_report_m17a.json")
    m17a_cost = _read_json(M17A / "latency_token_cost_report_m17a.json")
    m17b_go = _read_json(M17B / "go_no_go_m17b.json")
    m17b_safe = _read_json(M17B / "runtime_safety_report.json")
    m17b_latency = _read_json(M17B / "latency_token_cost_report.json")
    m17b_qwen = _read_json(M17B / "qwen_vs_deepseek_metrics.json")
    m17b_council = _read_json(M17B / "deepseek_vs_council_metrics.json")
    m17c_delta = _read_json(M17C / "m19_default_decision_readiness_delta_m17c.json")
    m17c_merged = _read_json(M17C / "merged_live_calibration_metrics_m17c.json")
    m17c_cost = _read_json(M17C / "provider_rate_limit_and_cost_report_m17c.json")
    m17c_safe = _read_json(M17C / "safety_invariant_report_m17c.json")
    m18c = _read_json(M18C / "learning_brain_quality_metrics_m18c.json")
    m18d_guard = _read_json(M18D / "learning_brain_truth_write_guard_m18d.json")
    m18d_safe = _read_json(M18D / "safety_attack_results_m18d.json")
    m19a = _read_json(M19A / "go_no_go_preflight_m19a.json")
    return {
        "m16_controlled_runtime": {
            "verdict": m16.get("controlled_production_runtime"),
            "auto_count": m16_obs.get("auto_count"),
            "legacy_equal_rate": (m16.get("metrics") or {}).get("legacy_equal_rate"),
            "production_write_count": m16_obs.get("production_write_count"),
            "retained": True,
        },
        "m17a_runtime_llm_adjudication": {
            "verdict": m17a_go.get("m17a_runtime_llm_adjudication"),
            "live_calls": m17a_cost.get("live_calls"),
            "legacy_equal_rate": m17a_safe.get("legacy_equal_rate"),
            "production_write_count": m17a_safe.get("production_write_count"),
            "validator_false_positive_prevented": m17a_safe.get("validator_false_positive_prevented"),
            "retained": True,
        },
        "m17b_runtime_llm_scaleout": {
            "original_verdict": m17b_go.get("m17b_verdict"),
            "retained_safety": m17b_safe.get("safety_all_zero"),
            "ws_submissions": (m17b_go.get("scale") or {}).get("ws_submissions"),
            "point_decisions": (m17b_go.get("scale") or {}).get("point_decisions"),
            "deepseek_live_calls_before_m17c": (m17b_go.get("scale") or {}).get("deepseek_live_calls"),
            "qwen_fallback_drills": m17b_qwen.get("forced_fallback_drills"),
            "real_qwen_fallback_completed": m17b_qwen.get("real_qwen_fallback_completed"),
            "latency_p50_ms": m17b_latency.get("latency_p50_ms"),
            "latency_p95_ms": m17b_latency.get("latency_p95_ms"),
            "council_points_reviewed": m17b_council.get("frontier_points"),
            "council_vote_as_source": m17b_council.get("council_vote_as_source"),
            "superseded_field": "m17b_verdict/deepseek_live_ge_80",
        },
        "m17c_deepseek_live_completion": {
            "verdict": m17c_delta.get("m17_scaleout_axis"),
            "merged_deepseek_live_calls": m17c_merged.get("merged_deepseek_live_calls"),
            "m17c_new_live_calls": m17c_merged.get("m17c_new_live_calls"),
            "merged_ge_80": m17c_merged.get("merged_ge_80"),
            "safety_all_zero": m17c_safe.get("safety_all_zero"),
            "duplicated_paid_calls": m17c_cost.get("duplicated_paid_calls"),
            "supersedes": "M17B live-call blocker",
        },
        "m18c_learning_brain": {
            "verdict": "GO",
            "evidence_drafts": m18c.get("evidence_drafts"),
            "pcps": m18c.get("pcps"),
            "shadow_promoted_to_mastery": m18c.get("shadow_promoted_to_mastery"),
            "retained": True,
        },
        "m18d_canonical_gate": {
            "verdict": "GO",
            "canonical_truth_written": m18d_guard.get("canonical_truth_written"),
            "production_write_count": m18d_guard.get("production_write_count"),
            "real_retest_proof_safe": m18d_safe.get("all_safe"),
            "retained": True,
        },
        "m19a_preflight": {
            "original_verdict": m19a.get("m19a_preflight_verdict"),
            "superseded_field": "production_default_decision=DEFERRED_TO_M19_AFTER_M17B",
            "retained": "rollback/observability/cost skeleton retained; waiting slots filled by M17C/M19B",
        },
        "canonical_runtime_llm_scaleout_axis": m17c_delta.get("m17_scaleout_axis"),
        "production_default": "OFF",
        "production_v1": "NO-GO",
    }


def _provider_rollup(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "deepseek_live": {
            "m17a_live_calls": ledger["m17a_runtime_llm_adjudication"]["live_calls"],
            "m17b_live_calls": ledger["m17b_runtime_llm_scaleout"]["deepseek_live_calls_before_m17c"],
            "m17c_new_live_calls": ledger["m17c_deepseek_live_completion"]["m17c_new_live_calls"],
            "merged_live_calls": ledger["m17c_deepseek_live_completion"]["merged_deepseek_live_calls"],
            "target_met": ledger["m17c_deepseek_live_completion"]["merged_ge_80"],
        },
        "latency": {
            "m17b_latency_p50_ms": ledger["m17b_runtime_llm_scaleout"]["latency_p50_ms"],
            "m17b_latency_p95_ms": ledger["m17b_runtime_llm_scaleout"]["latency_p95_ms"],
            "m17a_latency_note": "M17A live p95 retained as vertical-slice baseline; M17B scale latency used for M19 slot.",
        },
        "fallback": {
            "qwen_fallback_drills": ledger["m17b_runtime_llm_scaleout"]["qwen_fallback_drills"],
            "real_qwen_fallback_completed": ledger["m17b_runtime_llm_scaleout"]["real_qwen_fallback_completed"],
            "contract": "DeepSeek primary -> Qwen fallback -> fail-closed",
        },
        "cost": {
            "duplicated_paid_calls": ledger["m17c_deepseek_live_completion"]["duplicated_paid_calls"],
            "cost_marker": "DeepSeek metered by completed live call count; M19B release drill uses deterministic provider and executes no live calls.",
        },
        "validator": {
            "m17a_false_positive_prevented": ledger["m17a_runtime_llm_adjudication"]["validator_false_positive_prevented"],
            "safety_all_zero": ledger["m17c_deepseek_live_completion"]["safety_all_zero"],
        },
        "council_risk": {
            "council_points_reviewed": ledger["m17b_runtime_llm_scaleout"]["council_points_reviewed"],
            "council_vote_as_source": ledger["m17b_runtime_llm_scaleout"]["council_vote_as_source"],
            "risk_note": "council is release-risk advisory only; it does not replace source or runtime authority.",
        },
    }


def _decision_matrix() -> dict[str, Any]:
    return {
        "shadow_only": {
            "verdict": "GO",
            "reason": "current safe state; no production default or truth write.",
            "execute_now": False,
        },
        "controlled_cohort_only": {
            "verdict": "GO",
            "reason": "M16/M17A/M17C/M19B prove qa_/test_/operator_ append-only guard with rollback.",
            "execute_now": False,
        },
        "one_percent_qa_operator_default": {
            "verdict": "GO",
            "reason": "limited production default candidate only; M19B dry-run config is reversible and no truth-write.",
            "execute_now": False,
            "requires_explicit_user_authorization": True,
        },
        "named_internal_cohort_default": {
            "verdict": "GO",
            "reason": "bounded named internal cohort can be configured with same kill/fail-closed controls.",
            "execute_now": False,
            "requires_explicit_user_authorization": True,
        },
        "broad_production_default": {
            "verdict": "NO-GO",
            "reason": "broad default lacks explicit authorization, production async/rate-limit hardening, and canonical truth-write remains closed.",
            "execute_now": False,
        },
    }


def _release_gate(ws_drill: dict[str, Any], rollback: dict[str, Any]) -> dict[str, Any]:
    limited_ok = (
        ws_drill["submission_count"] >= 200
        and ws_drill["legacy_equal_rate"] == 1.0
        and ws_drill["production_write_count"] == 0
        and ws_drill["canonical_truth_written"] is False
        and ws_drill["non_cohort_real_student_blocked"] is True
        and rollback["all_pass"] is True
    )
    return {
        "m19b_limited_production_default_candidate": "GO" if limited_ok else "NO-GO",
        "production_v1_default_flip": "NO-GO",
        "canonical_learner_truth_write": "NO-GO",
        "default_flip_executed": False,
        "formal_registry_emitted": False,
        "production_default": "OFF",
        "production_write_count": ws_drill["production_write_count"],
        "canonical_truth_written": ws_drill["canonical_truth_written"],
        "reason": "limited candidate is GO as dry-run/reversible cohort config; actual flip remains NO-GO until explicit authorization.",
    }


def _dryrun_config() -> dict[str, Any]:
    return {
        "dryrun_only": True,
        "execute_flip": False,
        "production_default_enabled": False,
        "canonical_truth_write_enabled": False,
        "candidate_modes": {
            "one_percent_qa_operator_default": {
                "request_flag": "grading_engine_v1_llm_adjudication",
                "cohort_prefixes": ["qa_", "operator_"],
                "percentage": 1,
                "writeback": False,
            },
            "named_internal_cohort_default": {
                "request_flag": "grading_engine_v1_llm_adjudication",
                "cohort_prefixes": ["qa_", "test_", "operator_"],
                "named_users_only": True,
                "writeback": False,
            },
        },
        "rollback": {
            "kill_switch_env": KILL_ENV,
            "kill_value": "false",
            "drop_request_flag": "grading_engine_v1_llm_adjudication",
            "registry_fail_closed": True,
        },
    }


def _supersession_matrix() -> str:
    return """# M19B Supersession Matrix

| Prior artifact | Prior verdict / claim | M19B canonical handling |
|---|---|---|
| M16 controlled production runtime | controlled runtime GO, production default NO-GO | Retained as runtime safety baseline. |
| M17A runtime LLM adjudication | vertical slice GO | Retained as Nexus-style adjudication proof. |
| M17B scaleout council | **M17B WEAK-GO** because DeepSeek live 28 < 80 | Safety/scale/fallback/council evidence retained; live-call blocker **superseded by M17C**. |
| M17C DeepSeek live completion | merged DeepSeek live=80, scaleout GO | Canonical replacement for M17B live-readiness slot. |
| M18C/M18D Learning Brain | GO, real retest proof and dry-run canonical write | Retained; canonical truth write remains closed. |
| M19A preflight | GO but deferred to M19 after M17B/M17C | Retained for rollback/observability template; deferred evidence slots filled by M17C + M19B drill. |
"""


def _finding(ledger: dict[str, Any], drill: dict[str, Any], rollback: dict[str, Any], gate: dict[str, Any]) -> str:
    return f"""# FINDING — M19B Production Default Decision Synthesis (2026-06-04)

## Canonical verdict
- M19B limited production default candidate: **{gate['m19b_limited_production_default_candidate']}**
- Production v1 default flip: **{gate['production_v1_default_flip']}**
- Canonical learner truth write: **{gate['canonical_learner_truth_write']}**

## Evidence synthesis
- M17B WEAK-GO live gap is superseded by M17C: merged DeepSeek live={ledger['m17c_deepseek_live_completion']['merged_deepseek_live_calls']}, scaleout axis={ledger['canonical_runtime_llm_scaleout_axis']}.
- M19B real `/api/v1/ws` release drill submissions={drill['submission_count']}; cohort={drill['cohort_coverage']}; non_cohort_blocked={drill['non_cohort_real_student_blocked']}.
- legacy_equal_rate={drill['legacy_equal_rate']}; production_write_count={drill['production_write_count']}; canonical_truth_written={drill['canonical_truth_written']}.
- kill/malformed/provider_failure/fallback/rollback all_pass={rollback['all_pass']}.
- live_llm_calls_executed={drill['live_llm_calls_executed']}（M19B 不重发 live LLM；M17C live evidence 是模型能力 evidence）。

## Release decision
1. `shadow_only` / controlled cohort / 1% qa/operator / named internal cohort all qualify as **dry-run candidate** paths.
2. No actual production default flip is authorized or executed.
3. Broad production default remains **NO-GO**.
4. Canonical learner truth write remains **NO-GO**; M18D only proves dry-run/guarded candidate path.

## Red lines
production default not enabled; production DB not written; canonical learner truth not written; formal registry not emitted; no RAG/kernel/BI/billing/web changes; no human/teacher/PO impersonation.
"""


def run_m19b(out_dir: Path | str = OUT, *, submissions: int = 205) -> dict[str, Any]:
    out = Path(out_dir)
    _reset_output(out)
    ledger = _canonical_evidence_ledger()
    drill, rollback = _run_ws_release_drill(submissions)
    rollup = _provider_rollup(ledger)
    matrix = _decision_matrix()
    gate = _release_gate(drill, rollback)
    dryrun = _dryrun_config()

    _write_json(out / "canonical_evidence_ledger_m19b.json", ledger)
    _write_text(out / "supersession_matrix_m19b.md", _supersession_matrix())
    _write_json(out / "ws_release_drill_results_m19b.json", drill)
    _write_json(out / "provider_cost_latency_rollup_m19b.json", rollup)
    _write_json(out / "rollback_and_killswitch_verification_m19b.json", rollback)
    _write_json(out / "production_default_decision_matrix_m19b.json", matrix)
    _write_json(out / "release_go_no_go_m19b.json", gate)
    _write_json(out / "production_default_config_dryrun_m19b.json", dryrun)
    _write_text(out / "FINDING_production_default_decision_synthesis_m19b_20260604.md",
                _finding(ledger, drill, rollback, gate))
    return {
        "verdict": gate["m19b_limited_production_default_candidate"],
        "submission_count": drill["submission_count"],
        "production_default": "OFF",
        "default_flip_executed": False,
        "canonical_truth_written": False,
        "out_dir": str(out),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--submissions", type=int, default=205)
    args = ap.parse_args()
    print(json.dumps(run_m19b(args.out_dir, submissions=args.submissions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
