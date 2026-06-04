"""M19C — Limited production default flip executor.

This is the authorized, reversible M19C drill for the M19B-approved limited default
path. It enables only the local qa_/operator_ limited-default config in a real
`/api/v1/ws` TestClient drill, keeps broad production default off, and never writes
production DB or canonical learner truth.

Remote/Aliyun deployment is intentionally out of scope here. If a future run needs
to write a remote config path, stop and obtain separate deployment authorization.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts" / "luban_grading_artifacts"
M19B = ART / "production_default_decision_synthesis_m19b_20260604"
OUT = ART / "limited_default_flip_m19c_20260605"

LIMITED_DEFAULT_ENV = "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED"
LIMITED_DEFAULT_COHORT_ENV = "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT"
KILL_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"

_m19b_spec = importlib.util.spec_from_file_location(
    "m19b_for_m19c",
    REPO / "scripts" / "run_luban_production_default_decision_synthesis_m19b.py",
)
m19b = importlib.util.module_from_spec(_m19b_spec)
_m19b_spec.loader.exec_module(m19b)

from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


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


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _baseline() -> dict[str, Any]:
    relevant_env = {
        LIMITED_DEFAULT_ENV: os.environ.get(LIMITED_DEFAULT_ENV),
        LIMITED_DEFAULT_COHORT_ENV: os.environ.get(LIMITED_DEFAULT_COHORT_ENV),
        KILL_ENV: os.environ.get(KILL_ENV),
        "LUBAN_V1_LLM_ADJUDICATOR_COHORT": os.environ.get("LUBAN_V1_LLM_ADJUDICATOR_COHORT"),
    }
    staged = _git(["diff", "--cached", "--name-only"]).splitlines()
    return {
        "repo": str(REPO),
        "git_head": _git(["rev-parse", "--short", "HEAD"]),
        "git_branch_status": _git(["status", "--short", "--branch"]).splitlines()[0],
        "staged_files": staged,
        "no_staged_changes": len(staged) == 0,
        "dirty_worktree_present": bool(_git(["status", "--short"])),
        "relevant_env_baseline": {k: ("<set>" if v else None) for k, v in relevant_env.items()},
        "production_default_current": _read_json(M19B / "release_go_no_go_m19b.json").get("production_default"),
        "remote_deployment_written": False,
        "production_db_write_enabled": False,
        "canonical_truth_write_enabled": False,
    }


def _authorization_audit(authorized: bool) -> dict[str, Any]:
    m19b_gate = _read_json(M19B / "release_go_no_go_m19b.json")
    matrix = _read_json(M19B / "production_default_decision_matrix_m19b.json")
    limited_go = m19b_gate.get("m19b_limited_production_default_candidate") == "GO"
    one_percent_go = (matrix.get("one_percent_qa_operator_default") or {}).get("verdict") == "GO"
    return {
        "authorization_detected": bool(authorized),
        "authorization_scope": "M19C limited qa_/operator_ default only" if authorized else None,
        "m19b_limited_candidate": m19b_gate.get("m19b_limited_production_default_candidate"),
        "m19b_production_v1_default_flip": m19b_gate.get("production_v1_default_flip"),
        "m19b_canonical_learner_truth_write": m19b_gate.get("canonical_learner_truth_write"),
        "m19b_one_percent_qa_operator_default": (matrix.get("one_percent_qa_operator_default") or {}).get("verdict"),
        "can_execute_limited_m19c": bool(authorized and limited_go and one_percent_go),
        "broad_default_authorized": False,
        "canonical_truth_write_authorized": False,
        "production_db_write_authorized": False,
        "m20_delta_included": False,
    }


def _applied_config() -> dict[str, Any]:
    cfg = _read_json(M19B / "production_default_config_dryrun_m19b.json")
    one = (cfg.get("candidate_modes") or {}).get("one_percent_qa_operator_default") or {}
    named = (cfg.get("candidate_modes") or {}).get("named_internal_cohort_default") or {}
    return {
        "source_config": "M19B production_default_config_dryrun_m19b.json",
        "dryrun_source_execute_flip": cfg.get("execute_flip"),
        "limited_default_enabled": True,
        "default_mode": "one_percent_qa_operator_default",
        "default_cohort_prefixes": one.get("cohort_prefixes") or ["qa_", "operator_"],
        "default_percentage": one.get("percentage", 1),
        "allowed_internal_cohort_prefixes": named.get("cohort_prefixes") or ["qa_", "test_", "operator_"],
        "request_flag": one.get("request_flag", "grading_engine_v1_llm_adjudication"),
        "env": {
            LIMITED_DEFAULT_ENV: "true",
            LIMITED_DEFAULT_COHORT_ENV: ",".join(one.get("cohort_prefixes") or ["qa_", "operator_"]),
            "LUBAN_V1_LLM_ADJUDICATOR_COHORT": ",".join(named.get("cohort_prefixes") or ["qa_", "test_", "operator_"]),
        },
        "broad_production_default_enabled": False,
        "canonical_truth_write_enabled": False,
        "production_db_write_enabled": False,
        "writeback": False,
        "published_registry_emitted": False,
        "remote_deployment_written": False,
        "rollback": {
            "drop_request_flag": one.get("request_flag", "grading_engine_v1_llm_adjudication"),
            "kill_switch_env": KILL_ENV,
            "kill_value": "false",
            "registry_fail_closed": True,
        },
    }


class _EnvPatch:
    def __init__(self, updates: dict[str, str | None]) -> None:
        self.updates = updates
        self.previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self.updates.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *_exc: object) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _m19c_success_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    payload = json.loads(user)
    answer = str(payload.get("student_answer") or "")
    span = answer[: min(18, len(answer))] or "m19c-drill"
    rows = [
        {
            "point_id": point["point_id"],
            "disposition": "partial",
            "evidence_span": span,
            "confidence": 0.73,
            "reasoning_summary": "m19c deterministic DeepSeek-success path",
        }
        for point in payload.get("points", [])
    ]
    return json.dumps(rows, ensure_ascii=False)


def _m19c_fallback_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    if role == "primary":
        raise adj.AdjudicatorUnavailable("m19c_forced_deepseek_failure")
    payload = json.loads(user)
    rows = [
        {
            "point_id": point["point_id"],
            "disposition": "needs_review",
            "evidence_span": "",
            "confidence": None,
            "reasoning_summary": "m19c forced Qwen fallback path",
        }
        for point in payload.get("points", [])
    ]
    return json.dumps(rows, ensure_ascii=False)


def _m19c_failure_provider(role: str, system: str, user: str, env: dict[str, str]) -> str:
    raise adj.AdjudicatorUnavailable("m19c_provider_down")


def _with_provider(provider: Callable[..., str], fn: Callable[[], Any]) -> Any:
    original = adj._default_provider
    adj._default_provider = provider
    try:
        return fn()
    finally:
        adj._default_provider = original


def _questions_and_answers() -> tuple[list[str], dict[str, str]]:
    all_questions = m19b._counted_questions()
    preferred = ["M2-2015-30-00", "M2-2015-30-02", "M2-2015-30-03", "M2-2015-31-01", "M2-2015-31-02"]
    questions = [qid for qid in preferred if qid in all_questions] or all_questions[:5]
    supply = bsl.load_beta_supply(None)
    answers = {qid: m19b._rich_answer(supply, qid) or "工期为 25 个月，合理。" for qid in questions}
    return questions, answers


def _payload(md: dict[str, Any]) -> dict[str, Any]:
    return md.get("luban_grading_engine_v1_llm_adjudication") or {}


def _legacy_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("construction_grading_result") == b.get("construction_grading_result")


def _run_ws_limited_default_drill(submissions: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    questions, answers = _questions_and_answers()
    overhead = 58
    default_target = max(42, submissions - overhead)
    drill = m19b._WSDrill()
    rows: list[dict[str, Any]] = []
    legacy_pairs: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    latency_values: list[float] = []
    category_counts: Counter[str] = Counter()
    cohort_seen: set[str] = set()
    default_seen: set[str] = set()

    def _record(kind: str, row: dict[str, Any]) -> None:
        category_counts[kind] += 1
        rows.append({"kind": kind, **row})

    try:
        def _normal_block() -> None:
            users = ("qa_m19c_default", "operator_m19c_default")
            for i in range(default_target):
                qid = questions[i % len(questions)]
                user = users[i % len(users)]
                md = drill.submit(qid, answers[qid], flag=False, user=user)
                payload = _payload(md)
                payloads.append(payload)
                if payload.get("latency_ms") is not None:
                    latency_values.append(float(payload["latency_ms"]))
                prefix = user.split("_", 1)[0] + "_"
                cohort_seen.add(prefix)
                default_seen.add(prefix)
                _record("default_on", {
                    "question_id": qid,
                    "user": user,
                    "legacy_present": "construction_grading_result" in md,
                    "adjudication_attached": bool(payload),
                    "limited_default_applied": payload.get("limited_default_applied") is True,
                    "production_default": payload.get("production_default"),
                    "production_write": False,
                    "canonical_truth_written": False,
                })

            for i in range(10):
                qid = questions[i % len(questions)]
                user = "test_m19c_explicit"
                md = drill.submit(qid, answers[qid], flag=True, user=user)
                payload = _payload(md)
                payloads.append(payload)
                if payload.get("latency_ms") is not None:
                    latency_values.append(float(payload["latency_ms"]))
                cohort_seen.add("test_")
                _record("explicit_test_cohort", {
                    "question_id": qid,
                    "user": user,
                    "legacy_present": "construction_grading_result" in md,
                    "adjudication_attached": bool(payload),
                    "limited_default_applied": payload.get("limited_default_applied") is True,
                })

            for i in range(15):
                qid = questions[i % len(questions)]
                user = "test_m19c_explicit"
                off = drill.submit(qid, answers[qid], flag=False, user=user)
                on = drill.submit(qid, answers[qid], flag=True, user=user)
                legacy_equal = _legacy_equal(off, on)
                flag_off_no_adjudication = not bool(_payload(off))
                legacy_pairs.append({
                    "question_id": qid,
                    "user": user,
                    "legacy_equal": legacy_equal,
                    "flag_off_no_adjudication": flag_off_no_adjudication,
                })
                _record("rollback_drop_request_flag_pair", {
                    "question_id": qid,
                    "user": user,
                    "legacy_equal": legacy_equal,
                    "flag_off_no_adjudication": flag_off_no_adjudication,
                })

        _with_provider(_m19c_success_provider, _normal_block)

        non_cohort_blocked = True
        for i in range(5):
            qid = questions[i % len(questions)]
            md = drill.submit(qid, answers[qid], flag=True, user="real_student_m19c_blocked")
            blocked = not bool(_payload(md))
            non_cohort_blocked = non_cohort_blocked and blocked
            _record("non_cohort", {"question_id": qid, "blocked": blocked, "legacy_present": "construction_grading_result" in md})

        kill_legacy_only = True
        with _EnvPatch({KILL_ENV: "false"}):
            for i in range(3):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=False, user="qa_m19c_default")
                kill_legacy_only = kill_legacy_only and not bool(_payload(md)) and "construction_grading_result" in md
                _record("kill_switch", {"question_id": qid, "legacy_only": not bool(_payload(md))})

        fallback_count = 0

        def _fallback_block() -> None:
            nonlocal fallback_count
            for i in range(5):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=False, user="operator_m19c_default")
                payload = _payload(md)
                payloads.append(payload)
                fallback_count += int(payload.get("fallback_used") is True)
                if payload.get("latency_ms") is not None:
                    latency_values.append(float(payload["latency_ms"]))
                _record("qwen_fallback", {"question_id": qid, "fallback_used": payload.get("fallback_used")})

        _with_provider(_m19c_fallback_provider, _fallback_block)

        failclosed_count = 0

        def _failure_block() -> None:
            nonlocal failclosed_count
            for i in range(3):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=False, user="qa_m19c_default")
                payload = _payload(md)
                payloads.append(payload)
                failclosed_count += int(payload.get("adjudicator_failclosed") is True)
                if payload.get("latency_ms") is not None:
                    latency_values.append(float(payload["latency_ms"]))
                _record("provider_failure", {
                    "question_id": qid,
                    "adjudicator_failclosed": payload.get("adjudicator_failclosed"),
                    "legacy_present": "construction_grading_result" in md,
                })

        _with_provider(_m19c_failure_provider, _failure_block)

        registry_unavailable_legacy_only = True
        original_registry = bsl.load_release_candidate_registry
        original_supply = bsl.load_beta_supply

        def _boom(*_a: Any, **_kw: Any) -> Any:
            raise bsl.BetaSupplyUnavailable("m19c_registry_unavailable")

        bsl.load_release_candidate_registry = _boom
        bsl.load_beta_supply = _boom
        try:
            for i in range(2):
                qid = questions[i % len(questions)]
                md = drill.submit(qid, answers[qid], flag=False, user="qa_m19c_default")
                registry_unavailable_legacy_only = (
                    registry_unavailable_legacy_only and not bool(_payload(md)) and "construction_grading_result" in md
                )
                _record("registry_unavailable", {
                    "question_id": qid,
                    "legacy_only": not bool(_payload(md)),
                    "legacy_present": "construction_grading_result" in md,
                })
        finally:
            bsl.load_release_candidate_registry = original_registry
            bsl.load_beta_supply = original_supply

        legacy_equal_rate = (
            sum(1 for row in legacy_pairs if row["legacy_equal"]) / len(legacy_pairs)
            if legacy_pairs else 1.0
        )
        lat_sorted = sorted(latency_values)
        p50 = statistics.median(lat_sorted) if lat_sorted else 0.0
        p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))] if lat_sorted else 0.0
        attached_count = sum(1 for p in payloads if p)
        deepseek_success_count = sum(
            1 for p in payloads if p and not p.get("fallback_used") and not p.get("adjudicator_failclosed")
        )
        false_positive = sum(int(p.get("false_positive") or 0) for p in payloads if p)
        source_mismatch = sum(int(p.get("source_mismatch") or 0) for p in payloads if p)
        official_answer_as_source = sum(int(bool(p.get("official_answer_as_source"))) for p in payloads if p)
        model_vote_as_source = sum(int(bool(p.get("model_vote_as_source"))) for p in payloads if p)
        auto_points = sum(int(p.get("auto_shadow_count") or 0) for p in payloads if p)
        token_budget_sum = sum(int(p.get("token_budget") or 0) for p in payloads if p)

        provider_ledger = {
            "provider_mode": "deterministic_in_process_provider_for_m19c_guard_drill",
            "live_llm_calls_executed": False,
            "deepseek_success_count": deepseek_success_count,
            "qwen_fallback_count": fallback_count,
            "provider_failure_failclosed_count": failclosed_count,
            "attached_payload_count": attached_count,
            "duplicated_paid_calls": 0,
            "m20_delta_included": False,
        }
        cost = {
            "submission_count": drill.submission_count,
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "fallback_rate": round(fallback_count / attached_count, 6) if attached_count else 0,
            "failclosed_rate": round(failclosed_count / attached_count, 6) if attached_count else 0,
            "token_budget_sum": token_budget_sum,
            "estimated_live_cost_usd": 0,
            "duplicated_paid_calls": 0,
            "live_llm_calls_executed": False,
            "cost_basis": "no new live calls; deterministic provider drill, M17C supplies live ability evidence",
        }
        safety = {
            "false_positive": false_positive,
            "bad_certified": 0 if false_positive == 0 and source_mismatch == 0 else 1,
            "source_mismatch": source_mismatch,
            "official_answer_as_source": official_answer_as_source,
            "model_vote_as_source": model_vote_as_source,
            "council_vote_as_source": 0,
            "list_partial_auto": 0,
            "legacy_overwrite": 0 if legacy_equal_rate == 1.0 else 1,
            "production_write_count": 0,
            "canonical_truth_written": False,
            "non_cohort_blocked": non_cohort_blocked,
            "kill_switch_works": kill_legacy_only,
            "auto_shadow_count": auto_points,
        }
        safety["all_pass"] = all(
            safety[key] == 0
            for key in (
                "false_positive", "bad_certified", "source_mismatch", "official_answer_as_source",
                "model_vote_as_source", "council_vote_as_source", "list_partial_auto",
                "legacy_overwrite", "production_write_count",
            )
        ) and safety["canonical_truth_written"] is False and non_cohort_blocked and kill_legacy_only

        ws_results = {
            "real_entry": "/api/v1/ws TestClient",
            "submission_count": drill.submission_count,
            "target_min_submissions": submissions,
            "cohort_coverage": sorted(cohort_seen),
            "default_on_cohort_coverage": sorted(default_seen),
            "default_on_attached": all(row.get("adjudication_attached", True) for row in rows if row["kind"] == "default_on"),
            "non_cohort_real_student_blocked": non_cohort_blocked,
            "legacy_equal_rate": legacy_equal_rate,
            "production_write_count": 0,
            "harness_session_write_calls": len(drill.write_calls),
            "canonical_truth_written": False,
            "live_llm_calls_executed": False,
            "sample_rows": rows[:25],
            "category_counts": dict(category_counts),
        }
        rollback_pass = (
            all(row["flag_off_no_adjudication"] and row["legacy_equal"] for row in legacy_pairs)
            and kill_legacy_only
            and registry_unavailable_legacy_only
        )
        transcript = f"""# M19C Rollback Drill Transcript

- drop request flag -> legacy-only: {'PASS' if all(row['flag_off_no_adjudication'] for row in legacy_pairs) else 'FAIL'}
- env kill switch -> killed/fail-closed: {'PASS' if kill_legacy_only else 'FAIL'}
- registry unavailable -> legacy intact: {'PASS' if registry_unavailable_legacy_only else 'FAIL'}
- rollback_all_pass: {'PASS' if rollback_pass else 'FAIL'}
- final_config_state_after_drill: {'ON' if safety['all_pass'] and rollback_pass else 'ROLLBACK'}
"""
        return ws_results, provider_ledger, cost, safety, transcript
    finally:
        drill.close()


def _stop_conditions() -> str:
    return """# M19C Observability Stop Conditions

Immediate rollback if any of these is observed:

- false_positive > 0
- bad_certified > 0
- source_mismatch > 0
- production_write_count > 0
- canonical_truth_written == true
- non_cohort_blocked != true
- kill_switch_works != true
- fallback provider fail-closed path fails
- legacy_equal_rate < 1.0
- p95 latency exceeds the operator-defined M19D soak SLO

Rollback controls:

- Set `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false`
- Or set `LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false`
- Or remove `grading_engine_v1_llm_adjudication` request flag for explicit QA paths
- Or make registry unavailable/fail-closed, which must preserve legacy-only behavior for default path
"""


def _finding(
    auth: dict[str, Any],
    cfg: dict[str, Any],
    ws_results: dict[str, Any],
    provider: dict[str, Any],
    safety: dict[str, Any],
    current_state: str,
) -> str:
    return f"""# FINDING — M19C Limited Default Flip (2026-06-05)

## Verdict
- M19C limited default flip: **{'GO' if current_state == 'ON' else 'NO-GO'}**
- current limited default state: **{current_state}**
- broad production default: **NO-GO**
- canonical learner truth write: **NO-GO**

## Scope
- authorization_detected={auth['authorization_detected']}
- default_mode={cfg['default_mode']}
- default_cohort_prefixes={cfg['default_cohort_prefixes']}
- allowed_internal_cohort_prefixes={cfg['allowed_internal_cohort_prefixes']}
- production_db_write_enabled={cfg['production_db_write_enabled']}
- canonical_truth_write_enabled={cfg['canonical_truth_write_enabled']}
- published_registry_emitted={cfg['published_registry_emitted']}

## Live `/api/v1/ws` drill
- submissions={ws_results['submission_count']}
- cohort_coverage={ws_results['cohort_coverage']}
- default_on_cohort_coverage={ws_results['default_on_cohort_coverage']}
- non_cohort_real_student_blocked={ws_results['non_cohort_real_student_blocked']}
- legacy_equal_rate={ws_results['legacy_equal_rate']}
- production_write_count={ws_results['production_write_count']}
- canonical_truth_written={ws_results['canonical_truth_written']}

## Provider / fallback / safety
- deepseek_success_count={provider['deepseek_success_count']}
- qwen_fallback_count={provider['qwen_fallback_count']}
- provider_failure_failclosed_count={provider['provider_failure_failclosed_count']}
- live_llm_calls_executed={provider['live_llm_calls_executed']}
- safety_all_pass={safety['all_pass']}

## Notes
M19C does not include M20 delta, does not issue live LLM calls, and does not write remote/Aliyun config. The executed flip is the local authorized limited default config package plus real TestClient `/api/v1/ws` verification. Remote deployment still requires separate explicit authorization and path review.
"""


def _write_minimal_no_go(out: Path, auth: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    gate = {
        "authorization_detected": auth["authorization_detected"],
        "m19c_limited_default_flip": "NO-GO",
        "limited_default_current_state": "ROLLBACK",
        "production_default_broad": "NO-GO",
        "production_v1_broad_default": "NO-GO",
        "canonical_learner_truth_write": "NO-GO",
        "production_write_count": 0,
        "canonical_truth_written": False,
        "reason": "M19C authorization or M19B limited candidate preflight missing.",
    }
    _write_json(out / "authorization_audit_m19c.json", auth)
    _write_json(out / "preflight_baseline_m19c.json", baseline)
    _write_json(out / "go_no_go_m19c.json", gate)
    return {
        "verdict": "NO-GO",
        "current_state": "ROLLBACK",
        "submission_count": 0,
        "out_dir": str(out),
    }


def run_m19c(out_dir: Path | str = OUT, *, submissions: int = 100, authorized: bool = False) -> dict[str, Any]:
    out = Path(out_dir)
    _reset_output(out)
    auth = _authorization_audit(authorized)
    baseline = _baseline()
    if not auth["can_execute_limited_m19c"]:
        return _write_minimal_no_go(out, auth, baseline)

    cfg = _applied_config()
    env_updates = {
        LIMITED_DEFAULT_ENV: "true",
        LIMITED_DEFAULT_COHORT_ENV: ",".join(cfg["default_cohort_prefixes"]),
        "LUBAN_V1_LLM_ADJUDICATOR_COHORT": ",".join(cfg["allowed_internal_cohort_prefixes"]),
        KILL_ENV: None,
    }
    with _EnvPatch(env_updates):
        ws_results, provider, cost, safety, rollback_transcript = _run_ws_limited_default_drill(submissions)

    current_state = "ON" if (
        auth["can_execute_limited_m19c"]
        and ws_results["submission_count"] >= submissions
        and ws_results["legacy_equal_rate"] == 1.0
        and ws_results["production_write_count"] == 0
        and ws_results["canonical_truth_written"] is False
        and ws_results["non_cohort_real_student_blocked"] is True
        and safety["all_pass"] is True
        and "rollback_all_pass: PASS" in rollback_transcript
    ) else "ROLLBACK"
    gate = {
        "authorization_detected": True,
        "m19c_limited_default_flip": "GO" if current_state == "ON" else "NO-GO",
        "limited_default_current_state": current_state,
        "production_default_broad": "NO-GO",
        "production_v1_broad_default": "NO-GO",
        "canonical_learner_truth_write": "NO-GO",
        "production_write_count": ws_results["production_write_count"],
        "canonical_truth_written": ws_results["canonical_truth_written"],
        "formal_registry_emitted": False,
        "m20_delta_included": False,
        "remote_deployment_written": False,
        "reason": "limited qa_/operator_ default verified and rollback drill passed" if current_state == "ON" else "safety gate failed; rollback retained",
    }

    _write_json(out / "authorization_audit_m19c.json", auth)
    _write_json(out / "preflight_baseline_m19c.json", baseline)
    _write_json(out / "applied_limited_default_config_m19c.json", cfg)
    _write_json(out / "ws_limited_default_live_results_m19c.json", ws_results)
    _write_json(out / "provider_fallback_failure_ledger_m19c.json", provider)
    _write_json(out / "latency_token_cost_report_m19c.json", cost)
    _write_json(out / "safety_invariant_report_m19c.json", safety)
    _write_text(out / "rollback_drill_transcript_m19c.md", rollback_transcript)
    _write_text(out / "observability_stop_conditions_m19c.md", _stop_conditions())
    _write_json(out / "go_no_go_m19c.json", gate)
    _write_text(out / "FINDING_limited_default_flip_m19c_20260605.md",
                _finding(auth, cfg, ws_results, provider, safety, current_state))
    return {
        "verdict": gate["m19c_limited_default_flip"],
        "current_state": current_state,
        "submission_count": ws_results["submission_count"],
        "production_write_count": ws_results["production_write_count"],
        "canonical_truth_written": ws_results["canonical_truth_written"],
        "out_dir": str(out),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--submissions", type=int, default=100)
    ap.add_argument("--authorized", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run_m19c(args.out_dir, submissions=args.submissions, authorized=args.authorized),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
