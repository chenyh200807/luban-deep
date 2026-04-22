from __future__ import annotations

import asyncio
import html
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot
from deeptutor.services.query_intent import (
    build_grounding_decision,
    build_grounding_decision_from_metadata,
)
from deeptutor.services.question_followup import (
    looks_like_question_followup,
    resolve_submission_attempt,
)
from deeptutor.services.rag.exact_authority import (
    extract_exact_question_authority_from_metadata,
    resolve_exact_authority_response_from_authority,
    should_force_exact_authority,
)
from deeptutor.services.semantic_router import resolve_question_semantic_routing
from deeptutor.services.session.context_router import ContextRouteInput, decide_context_route
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "arr"
SEMANTIC_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "semantic_router_eval_cases.json"
CONTEXT_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "context_orchestration_eval_cases.json"
RAG_GROUNDING_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_grounding_eval_cases.json"
LONG_DIALOG_FOCUS_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "long_dialog_focus_eval_cases.json"
LONG_DIALOG_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_long_dialog_v1_retest.py"


def _main_repo_root_from_worktree(project_root: Path) -> Path | None:
    git_pointer = project_root / ".git"
    if not git_pointer.is_file():
        return None
    raw = git_pointer.read_text(encoding="utf-8").strip()
    if not raw.startswith("gitdir:"):
        return None
    gitdir_value = raw.split(":", 1)[1].strip()
    gitdir = Path(gitdir_value).expanduser()
    if not gitdir.is_absolute():
        gitdir = (git_pointer.parent / gitdir).resolve()
    if gitdir.parent.name != "worktrees":
        return None
    common_git_dir = gitdir.parent.parent
    if common_git_dir.name != ".git":
        return None
    return common_git_dir.parent


def _default_long_dialog_source_candidates() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _append(candidate: Path) -> None:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    roots = [PROJECT_ROOT.parent]
    main_repo_root = _main_repo_root_from_worktree(PROJECT_ROOT)
    if main_repo_root is not None:
        roots.append(main_repo_root.parent)

    for root in roots:
        _append(
            root
            / "FastAPI20251222_broken_backup_20260414_002321"
            / "artifacts"
            / "long_dialog_round7_full_detail_20260328.json"
        )
        _append(
            root
            / "FastAPI20251222"
            / "artifacts"
            / "long_dialog_round7_full_detail_20260328.json"
        )
    return candidates


def _make_case_result(
    *,
    suite: str,
    case_id: str,
    case_name: str,
    status: str,
    case_tier: str,
    failure_type: str | None = None,
    evidence: dict[str, Any] | None = None,
    latency_ms: float | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "suite": suite,
        "case_id": case_id,
        "case_name": case_name,
        "status": status,
        "case_tier": case_tier,
        "gate_eligible": case_tier in {"gate_stable", "regression_tier"},
        "repeated_pass_required": case_tier == "regression_tier",
        "failure_type": failure_type,
        "evidence": evidence or {},
        "latency_ms": round(float(latency_ms), 1) if latency_ms is not None else None,
        "details": details or {},
    }


def _summarize_suite(suite: str, case_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item["status"] for item in case_results)
    failure_counts = Counter(
        item["failure_type"] for item in case_results if item.get("failure_type")
    )
    tier_counts = Counter(item["case_tier"] for item in case_results if item.get("case_tier"))
    total = len(case_results)
    executed = total - int(status_counts.get("SKIP", 0))
    passed = int(status_counts.get("PASS", 0))
    failed = int(status_counts.get("FAIL", 0))
    skipped = int(status_counts.get("SKIP", 0))
    return {
        "suite": suite,
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / executed, 4) if executed else None,
        "failure_taxonomy": [
            {"failure_type": failure_type, "count": int(count)}
            for failure_type, count in sorted(failure_counts.items(), key=lambda item: item[0])
        ],
        "case_tiers": {tier: int(count) for tier, count in sorted(tier_counts.items(), key=lambda item: item[0])},
    }


async def run_semantic_router_suite() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(SEMANTIC_FIXTURE_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for case in cases:
        llm_action = case.get("llm_action")
        metadata = case.get("metadata") or {"active_object": case.get("active_object")}

        async def fake_interpret(
            _message: str,
            _context: dict[str, object] | None,
        ) -> dict[str, object] | None:
            return llm_action

        started_at = time.perf_counter()
        routing = await resolve_question_semantic_routing(
            user_message=case["user_message"],
            metadata=metadata,
            history_context="",
            interpret_followup_action=fake_interpret,
            resolve_submission_attempt=resolve_submission_attempt,
            looks_like_question_followup=looks_like_question_followup,
            looks_like_practice_generation_request=looks_like_practice_generation_request,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000.0

        actual_relation = routing.turn_semantic_decision["relation_to_active_object"]
        actual_next_action = routing.turn_semantic_decision["next_action"]
        expected_relation = case["expected_relation"]
        expected_next_action = case["expected_next_action"]
        passed = actual_relation == expected_relation and actual_next_action == expected_next_action
        results.append(
            _make_case_result(
                suite="semantic-router",
                case_id=case["name"],
                case_name=case["name"],
                status="PASS" if passed else "FAIL",
                case_tier="gate_stable",
                failure_type=None if passed else "FAIL_ROUTE_WRONG",
                evidence={
                    "expected_relation": expected_relation,
                    "actual_relation": actual_relation,
                    "expected_next_action": expected_next_action,
                    "actual_next_action": actual_next_action,
                },
                latency_ms=latency_ms,
            )
        )

    return _summarize_suite("semantic-router", results), results


def run_context_orchestration_suite() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(CONTEXT_FIXTURE_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for case in cases:
        started_at = time.perf_counter()
        decision = decide_context_route(
            ContextRouteInput(
                user_message=case["user_message"],
                has_active_question=bool(case.get("has_active_question", False)),
                has_active_plan=bool(case.get("has_active_plan", False)),
                notebook_references=tuple(case.get("notebook_references", []) or []),
                history_references=tuple(case.get("history_references", []) or []),
                personal_recall_hint=bool(case.get("personal_recall_hint", False)),
            )
        )
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        expected_route = case["expected_route"]
        actual_route = decision.route_label
        passed = actual_route == expected_route
        results.append(
            _make_case_result(
                suite="context-orchestration",
                case_id=case["name"],
                case_name=case["name"],
                status="PASS" if passed else "FAIL",
                case_tier="gate_stable",
                failure_type=None if passed else "FAIL_CONTEXT_LOSS",
                evidence={
                    "expected_route": expected_route,
                    "actual_route": actual_route,
                },
                latency_ms=latency_ms,
            )
        )

    return _summarize_suite("context-orchestration", results), results


def run_rag_grounding_suite() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(RAG_GROUNDING_FIXTURE_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for case in cases:
        started_at = time.perf_counter()
        kind = str(case.get("kind") or "").strip()
        passed = False
        evidence: dict[str, Any] = {}
        failure_type = "FAIL_GROUNDEDNESS"

        if kind == "exact_authority":
            authority = extract_exact_question_authority_from_metadata(case.get("metadata"))
            actual_force = should_force_exact_authority(authority or {}) if authority else False
            rendered = resolve_exact_authority_response_from_authority(authority) if authority else None
            expected_force = bool(case.get("expected_force_exact"))
            expected_fragments = [str(item) for item in case.get("expected_response_contains") or []]
            rendered_text = str(rendered or "")
            fragments_ok = all(fragment in rendered_text for fragment in expected_fragments)
            passed = actual_force == expected_force and (
                fragments_ok if expected_force else rendered is None
            )
            evidence = {
                "expected_force_exact": expected_force,
                "actual_force_exact": actual_force,
                "rendered_preview": rendered_text[:300],
            }
            failure_type = "FAIL_RAG_MISS" if authority is None else "FAIL_GROUNDEDNESS"
        elif kind == "grounding_decision":
            decision = build_grounding_decision(
                query=case["query"],
                default_kb=case.get("default_kb"),
                knowledge_bases=case.get("knowledge_bases"),
                rag_enabled=bool(case.get("rag_enabled", True)),
                tutorbot_context=bool(case.get("tutorbot_context", False)),
                followup_question=bool(case.get("followup_question", False)),
                answer_type=case.get("answer_type"),
            )
            expected = case.get("expected") or {}
            passed = all(getattr(decision, key) == value for key, value in expected.items())
            evidence = {key: getattr(decision, key) for key in expected}
        elif kind == "grounding_decision_from_metadata":
            decision = build_grounding_decision_from_metadata(
                query=case["query"],
                runtime_metadata=case.get("runtime_metadata"),
                rag_enabled=bool(case.get("rag_enabled", True)),
                tutorbot_context=bool(case.get("tutorbot_context", False)),
                exact_question_candidate=bool(case.get("exact_question_candidate", False)),
                practice_generation_request=bool(case.get("practice_generation_request", False)),
            )
            expected = case.get("expected") or {}
            passed = all(getattr(decision, key) == value for key, value in expected.items())
            evidence = {key: getattr(decision, key) for key in expected}
        else:
            raise ValueError(f"Unsupported rag-grounding case kind: {kind}")

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        results.append(
            _make_case_result(
                suite="rag-grounding",
                case_id=case["name"],
                case_name=case["name"],
                status="PASS" if passed else "FAIL",
                case_tier="gate_stable",
                failure_type=None if passed else failure_type,
                evidence=evidence,
                latency_ms=latency_ms,
            )
        )

    return _summarize_suite("rag-grounding", results), results


async def run_local_long_dialog_suite() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(LONG_DIALOG_FOCUS_FIXTURE_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for case in cases:
        started_at = time.perf_counter()
        failure_type: str | None = None
        evidence: dict[str, Any] = {"step_results": []}

        for index, step in enumerate(case.get("steps") or [], start=1):
            step_kind = str(step.get("kind") or "").strip()
            if step_kind == "semantic":
                llm_action = step.get("llm_action")

                async def fake_interpret(
                    _message: str,
                    _context: dict[str, object] | None,
                ) -> dict[str, object] | None:
                    return llm_action

                routing = await resolve_question_semantic_routing(
                    user_message=step["user_message"],
                    metadata={"active_object": step["active_object"]},
                    history_context="",
                    interpret_followup_action=fake_interpret,
                    resolve_submission_attempt=resolve_submission_attempt,
                    looks_like_question_followup=looks_like_question_followup,
                    looks_like_practice_generation_request=looks_like_practice_generation_request,
                )
                actual_relation = routing.turn_semantic_decision["relation_to_active_object"]
                actual_next_action = routing.turn_semantic_decision["next_action"]
                evidence["step_results"].append(
                    {
                        "step_index": index,
                        "kind": step_kind,
                        "expected_relation": step["expected_relation"],
                        "actual_relation": actual_relation,
                        "expected_next_action": step["expected_next_action"],
                        "actual_next_action": actual_next_action,
                    }
                )
                if (
                    actual_relation != step["expected_relation"]
                    or actual_next_action != step["expected_next_action"]
                ):
                    failure_type = "FAIL_CONTINUITY"
                    break
            elif step_kind == "context":
                decision = decide_context_route(
                    ContextRouteInput(
                        user_message=step["user_message"],
                        has_active_question=bool(step.get("has_active_question", False)),
                        has_active_plan=bool(step.get("has_active_plan", False)),
                        notebook_references=tuple(step.get("notebook_references", []) or []),
                        history_references=tuple(step.get("history_references", []) or []),
                        personal_recall_hint=bool(step.get("personal_recall_hint", False)),
                    )
                )
                actual_route = decision.route_label
                evidence["step_results"].append(
                    {
                        "step_index": index,
                        "kind": step_kind,
                        "expected_route": step["expected_route"],
                        "actual_route": actual_route,
                    }
                )
                if actual_route != step["expected_route"]:
                    failure_type = "FAIL_CONTEXT_LOSS"
                    break
            else:
                raise ValueError(f"Unsupported long-dialog step kind: {step_kind}")

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        results.append(
            _make_case_result(
                suite="long-dialog-focus",
                case_id=case["name"],
                case_name=case["name"],
                status="FAIL" if failure_type else "PASS",
                case_tier="regression_tier",
                failure_type=failure_type,
                evidence=evidence,
                latency_ms=latency_ms,
            )
        )

    return _summarize_suite("long-dialog-focus", results), results


def resolve_long_dialog_source_path(explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
        return candidate if candidate.exists() else None
    for candidate in _default_long_dialog_source_candidates():
        if candidate.exists():
            return candidate
    return None


def assess_long_dialog_readiness(
    explicit_path: str | None = None,
    *,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    source_path = resolve_long_dialog_source_path(explicit_path)
    python_executable = sys.executable or "python3.11"
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPTUTOR_OPENAI_API_KEY")
        or os.getenv("OPENAI_APIKEY")
        or ""
    )
    reasons: list[str] = []
    if source_path is None:
        reasons.append("missing_source_json")
    if not api_base_url and not api_key:
        reasons.append("missing_openai_api_key")
    if not LONG_DIALOG_SCRIPT_PATH.exists():
        reasons.append("missing_long_dialog_script")
    return {
        "ready": not reasons,
        "source_path": str(source_path) if source_path else None,
        "python_executable": python_executable,
        "api_base_url": api_base_url.rstrip("/") if api_base_url else None,
        "reasons": reasons,
    }


def _map_long_dialog_failure(case_result: dict[str, Any]) -> str | None:
    summary = case_result.get("summary") or {}
    if summary.get("hard_errors"):
        return "FAIL_INFRA"
    if summary.get("followup_object_mismatch_count"):
        return "FAIL_CONTINUITY"
    if summary.get("context_reset_count"):
        return "FAIL_CONTEXT_LOSS"
    if summary.get("anchor_miss_count"):
        return "FAIL_PRODUCT_BEHAVIOR"
    if summary.get("slow_turns"):
        return "FAIL_TIMEOUT"
    if (
        summary.get("question_count_mismatch_count")
        or summary.get("compare_table_miss_count")
        or summary.get("stale_replay_count")
    ):
        return "FAIL_PRODUCT_BEHAVIOR"
    return None


async def run_long_dialog_suite(
    *,
    mode: str,
    explicit_source_json: str | None = None,
    max_cases: int | None = None,
    output_dir: Path | None = None,
    api_base_url: str | None = None,
    response_mode: str = "smart",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    readiness = assess_long_dialog_readiness(explicit_source_json, api_base_url=api_base_url)
    suite_name = "long-dialog-focus" if mode == "lite" else "long-dialog-full"
    if not readiness["ready"]:
        if mode == "lite":
            return await run_local_long_dialog_suite()
        results = [
            _make_case_result(
                suite=suite_name,
                case_id=suite_name,
                case_name=suite_name,
                status="SKIP",
                case_tier="regression_tier",
                evidence={"reasons": readiness["reasons"]},
                details={"readiness": readiness},
            )
        ]
        return _summarize_suite(suite_name, results), results

    suite_output_dir = (output_dir or DEFAULT_OUTPUT_DIR) / f"long_dialog_{int(time.time())}"
    suite_output_dir.mkdir(parents=True, exist_ok=True)
    turn_mode = "focus" if mode == "lite" else "full"
    command = [
        readiness["python_executable"],
        str(LONG_DIALOG_SCRIPT_PATH),
        "--output-dir",
        str(suite_output_dir),
        "--turn-mode",
        turn_mode,
        "--response-mode",
        str(response_mode or "smart"),
    ]
    if readiness["source_path"]:
        command.extend(["--source-json", readiness["source_path"]])
    if readiness.get("api_base_url"):
        command.extend(["--api-base-url", str(readiness["api_base_url"])])
    if max_cases:
        command.extend(["--max-cases", str(max_cases)])

    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        results = [
            _make_case_result(
                suite=suite_name,
                case_id=suite_name,
                case_name=suite_name,
                status="FAIL",
                case_tier="regression_tier",
                failure_type="FAIL_INFRA",
                evidence={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-1000:],
                },
                details={"command": command},
            )
        ]
        return _summarize_suite(suite_name, results), results

    json_artifacts = sorted(suite_output_dir.glob("long_dialog_v1_retest_*.json"))
    if not json_artifacts:
        results = [
            _make_case_result(
                suite=suite_name,
                case_id=suite_name,
                case_name=suite_name,
                status="FAIL",
                case_tier="regression_tier",
                failure_type="FAIL_INFRA",
                evidence={"reason": "missing_long_dialog_json_artifact"},
                details={"command": command},
            )
        ]
        return _summarize_suite(suite_name, results), results

    payload = json.loads(json_artifacts[-1].read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case_result in payload:
        failure_type = _map_long_dialog_failure(case_result)
        summary = case_result.get("summary") or {}
        status = "FAIL" if failure_type else "PASS"
        results.append(
            _make_case_result(
                suite=suite_name,
                case_id=case_result["case_id"],
                case_name=case_result.get("title") or case_result["case_id"],
                status=status,
                case_tier="regression_tier",
                failure_type=failure_type,
                evidence={
                    "semantic_score": summary.get("semantic_score"),
                    "satisfaction_score": summary.get("satisfaction_score"),
                    "hard_errors": summary.get("hard_errors"),
                    "followup_object_mismatch_count": summary.get("followup_object_mismatch_count"),
                    "context_reset_count": summary.get("context_reset_count"),
                    "slow_turns": summary.get("slow_turns"),
                },
                latency_ms=summary.get("avg_latency_ms"),
                details={"artifact_path": str(json_artifacts[-1])},
            )
        )

    return _summarize_suite(suite_name, results), results


def compute_baseline_diff(
    *,
    baseline_payload: dict[str, Any] | None,
    current_payload: dict[str, Any],
) -> dict[str, Any] | None:
    if not baseline_payload:
        return None

    baseline_cases = {
        f"{item['suite']}::{item['case_id']}": item
        for item in baseline_payload.get("case_results") or []
    }
    current_cases = {
        f"{item['suite']}::{item['case_id']}": item
        for item in current_payload.get("case_results") or []
    }

    regressions: list[dict[str, Any]] = []
    new_failures: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []

    for case_key, current in sorted(current_cases.items(), key=lambda item: item[0]):
        baseline = baseline_cases.get(case_key)
        current_status = current.get("status")
        baseline_status = baseline.get("status") if baseline else None
        if baseline_status == "PASS" and current_status == "FAIL":
            regressions.append(
                {
                    "case_key": case_key,
                    "failure_type": current.get("failure_type"),
                }
            )
        elif baseline is None and current_status == "FAIL":
            new_failures.append(
                {
                    "case_key": case_key,
                    "failure_type": current.get("failure_type"),
                }
            )
        elif baseline_status == "FAIL" and current_status == "PASS":
            recovered.append({"case_key": case_key})

    baseline_summary = baseline_payload.get("summary") or {}
    current_summary = current_payload.get("summary") or {}
    baseline_pass_rate = baseline_summary.get("pass_rate")
    current_pass_rate = current_summary.get("pass_rate")

    return {
        "baseline_run_id": baseline_payload.get("run_id"),
        "current_run_id": current_payload.get("run_id"),
        "baseline_pass_rate": baseline_pass_rate,
        "current_pass_rate": current_pass_rate,
        "pass_rate_delta": round(current_pass_rate - baseline_pass_rate, 4)
        if isinstance(baseline_pass_rate, (int, float)) and isinstance(current_pass_rate, (int, float))
        else None,
        "regressions": regressions,
        "new_failures": new_failures,
        "recovered": recovered,
    }


def _build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item["status"] for item in case_results)
    failure_counts = Counter(
        item["failure_type"] for item in case_results if item.get("failure_type")
    )
    tier_counts = Counter(item["case_tier"] for item in case_results if item.get("case_tier"))
    total = len(case_results)
    skipped = int(status_counts.get("SKIP", 0))
    executed = total - skipped
    passed = int(status_counts.get("PASS", 0))
    failed = int(status_counts.get("FAIL", 0))
    gate_stable_cases = [
        item for item in case_results if item.get("case_tier") == "gate_stable" and item.get("status") != "SKIP"
    ]
    regression_tier_cases = [item for item in case_results if item.get("case_tier") == "regression_tier"]
    gate_stable_passed = len([item for item in gate_stable_cases if item.get("status") == "PASS"])
    regression_tier_failed = len([item for item in regression_tier_cases if item.get("status") == "FAIL"])
    return {
        "total_cases": total,
        "executed_cases": executed,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / executed, 4) if executed else None,
        "case_tiers": {tier: int(count) for tier, count in sorted(tier_counts.items(), key=lambda item: item[0])},
        "gate_stable_pass_rate": round(gate_stable_passed / len(gate_stable_cases), 4) if gate_stable_cases else None,
        "regression_tier_failed": regression_tier_failed,
        "failure_taxonomy": [
            {"failure_type": failure_type, "count": int(count)}
            for failure_type, count in sorted(failure_counts.items(), key=lambda item: item[0])
        ],
    }


async def run_arr(
    *,
    mode: str,
    baseline_payload: dict[str, Any] | None = None,
    explicit_long_dialog_source_json: str | None = None,
    long_dialog_max_cases: int | None = None,
    output_dir: Path | None = None,
    api_base_url: str | None = None,
    response_mode: str = "smart",
) -> dict[str, Any]:
    if mode not in {"lite", "full"}:
        raise ValueError(f"Unsupported ARR mode: {mode}")

    suite_summaries: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []

    semantic_summary, semantic_results = await run_semantic_router_suite()
    suite_summaries.append(semantic_summary)
    case_results.extend(semantic_results)

    context_summary, context_results = run_context_orchestration_suite()
    suite_summaries.append(context_summary)
    case_results.extend(context_results)

    rag_summary, rag_results = run_rag_grounding_suite()
    suite_summaries.append(rag_summary)
    case_results.extend(rag_results)

    long_dialog_summary, long_dialog_results = await run_long_dialog_suite(
        mode=mode,
        explicit_source_json=explicit_long_dialog_source_json,
        max_cases=long_dialog_max_cases or (1 if mode == "lite" else None),
        output_dir=output_dir,
        api_base_url=api_base_url,
        response_mode=response_mode,
    )
    suite_summaries.append(long_dialog_summary)
    case_results.extend(long_dialog_results)

    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    release_snapshot = get_release_lineage_snapshot()
    run_id = f"arr-{mode}-{int(time.time())}"
    payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "mode": mode,
        "release": release_snapshot,
        "suite_summaries": suite_summaries,
        "case_results": case_results,
        "summary": _build_summary(case_results),
        "execution_context": {
            "api_base_url": api_base_url.rstrip("/") if api_base_url else None,
            "response_mode": str(response_mode or "smart"),
            "suite_execution_modes": {
                "semantic-router": "static_analysis",
                "context-orchestration": "static_analysis",
                "rag-grounding": "static_analysis",
                "long-dialog-focus" if mode == "lite" else "long-dialog-full": (
                    "live_ws" if api_base_url else "in_process_runtime"
                ),
            },
        },
    }
    payload["baseline_diff"] = compute_baseline_diff(
        baseline_payload=baseline_payload,
        current_payload=payload,
    )
    payload["gate_summary"] = {
        "bootstrap_mode": True,
        "gate_stable_pass_rate": payload["summary"].get("gate_stable_pass_rate"),
        "regression_tier_failed": payload["summary"].get("regression_tier_failed"),
        "new_regressions": len((payload.get("baseline_diff") or {}).get("regressions") or []),
    }
    return payload


def render_arr_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    report = build_arr_report_payload(payload)
    latency_summary = report["latency_summary"]
    gate_summary = report["gate_summary"]
    baseline_diff = report["baseline_diff"]
    lines = [
        "# ARR Run",
        "",
        f"**Run ID**: `{payload.get('run_id')}`",
        f"**时间**: {payload.get('generated_at')}",
        f"**模式**: `{payload.get('mode')}`",
        f"**Release**: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        "",
        "## 总览",
        "",
        f"- 总 case: {summary.get('total_cases', 0)}",
        f"- 已执行: {summary.get('executed_cases', 0)}",
        f"- PASS: {summary.get('passed', 0)}",
        f"- FAIL: {summary.get('failed', 0)}",
        f"- SKIP: {summary.get('skipped', 0)}",
        f"- Pass rate: {summary.get('pass_rate')}",
        f"- Gate stable pass rate: {gate_summary.get('gate_stable_pass_rate')}",
        f"- Regression tier failed: {gate_summary.get('regression_tier_failed')}",
        "",
        "## 时延分析",
        "",
        f"- avg latency(ms): {latency_summary.get('avg_latency_ms')}",
        f"- p50 latency(ms): {latency_summary.get('p50_latency_ms')}",
        f"- p95 latency(ms): {latency_summary.get('p95_latency_ms')}",
        f"- max latency(ms): {latency_summary.get('max_latency_ms')}",
        "",
        "## 分套件",
        "",
        "| Suite | Total | Pass | Fail | Skip | Pass Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for suite_summary in payload.get("suite_summaries") or []:
        lines.append(
            f"| {suite_summary['suite']} | {suite_summary['total_cases']} | "
            f"{suite_summary['passed']} | {suite_summary['failed']} | "
            f"{suite_summary['skipped']} | {suite_summary['pass_rate']} |"
        )

    lines.extend(["", "## 状态分布", ""])
    if not report["status_distribution"]:
        lines.append("- 无")
    else:
        for item in report["status_distribution"]:
            lines.append(f"- `{item['name']}`: {item['count']} ({item['pct']}%)")

    lines.extend(["", "## Case Tier 分布", ""])
    if not report["case_tier_distribution"]:
        lines.append("- 无")
    else:
        for item in report["case_tier_distribution"]:
            lines.append(f"- `{item['name']}`: {item['count']} ({item['pct']}%)")

    lines.extend(["", "## Failure Type 分布", ""])
    if not report["failure_type_distribution"]:
        lines.append("- 无")
    else:
        for item in report["failure_type_distribution"]:
            lines.append(f"- `{item['name']}`: {item['count']} ({item['pct']}%)")

    lines.extend(["", "## 失败用例", ""])
    if not report["failures"]:
        lines.append("- 无")
    else:
        for item in report["failures"]:
            lines.append(
                f"- `{item['case_key']}` -> {item.get('failure_type') or 'UNKNOWN'} "
                f"| tier={item.get('case_tier')} "
                f"| latency_ms={item.get('latency_ms')} "
                f"| evidence={json.dumps(item.get('evidence') or {}, ensure_ascii=False)}"
            )
            lines.append(f"  reason: {item.get('reason')}")
            lines.append(f"  remediation: {item.get('remediation')}")

    lines.extend(["", "## 跳过用例", ""])
    if not report["skips"]:
        lines.append("- 无")
    else:
        for item in report["skips"]:
            lines.append(
                f"- `{item['case_key']}` -> "
                f"{json.dumps(item.get('evidence') or {}, ensure_ascii=False)}"
            )

    lines.extend(["", "## Baseline Diff", ""])
    lines.append(f"- Baseline run: {baseline_diff.get('baseline_run_id')}")
    lines.append(f"- Pass rate delta: {baseline_diff.get('pass_rate_delta')}")
    lines.append(f"- Regressions: {len(baseline_diff.get('regressions') or [])}")
    lines.append(f"- New failures: {len(baseline_diff.get('new_failures') or [])}")
    lines.append(f"- Recovered: {len(baseline_diff.get('recovered') or [])}")
    for label in ("regressions", "new_failures", "recovered"):
        items = baseline_diff.get(label) or []
        if not items:
            continue
        lines.append(f"- {label}:")
        for item in items:
            lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")

    lines.extend(["", "## 限制与说明", ""])
    for item in report["report_limitations"]:
        lines.append(f"- {item}")

    return "\n".join(lines)


def load_baseline_payload(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    baseline_path = Path(path).expanduser().resolve()
    if not baseline_path.exists():
        raise FileNotFoundError(f"ARR baseline not found: {baseline_path}")
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def load_arr_baseline_payload(path: str | None) -> dict[str, Any] | None:
    explicit = load_baseline_payload(path)
    if explicit is not None:
        return explicit
    from deeptutor.services.observability.control_plane_store import get_control_plane_store

    latest = get_control_plane_store().latest_run("arr_runs")
    return (latest or {}).get("payload") if latest else None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _build_latency_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = sorted(
        float(item["latency_ms"])
        for item in case_results
        if isinstance(item.get("latency_ms"), (int, float))
    )
    if not latencies:
        return {
            "count": 0,
            "avg_latency_ms": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "max_latency_ms": None,
        }
    return {
        "count": len(latencies),
        "avg_latency_ms": _round_or_none(sum(latencies) / len(latencies), 1),
        "p50_latency_ms": _round_or_none(latencies[len(latencies) // 2], 1),
        "p95_latency_ms": _round_or_none(
            latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)],
            1,
        ),
        "max_latency_ms": _round_or_none(max(latencies), 1),
    }


def _build_distribution_rows(entries: list[dict[str, Any]], *, key: str, total: int) -> list[dict[str, Any]]:
    counter = Counter(str(item.get(key) or "").strip() for item in entries if str(item.get(key) or "").strip())
    rows: list[dict[str, Any]] = []
    for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "name": name,
                "count": int(count),
                "pct": _round_or_none(count / total * 100, 1) if total else 0.0,
            }
        )
    return rows


def _build_failure_reason(case: dict[str, Any]) -> tuple[str, str, float]:
    failure_type = str(case.get("failure_type") or "").strip()
    evidence = case.get("evidence") or {}
    if failure_type == "FAIL_ROUTE_WRONG":
        return (
            f"语义路由与预期不一致，evidence={_format_json(evidence)}",
            "优先检查 semantic router 的 relation/next_action 判定与 active object 上下文。",
            0.9,
        )
    if failure_type == "FAIL_CONTEXT_LOSS":
        return (
            f"上下文承接丢失或 route 错位，evidence={_format_json(evidence)}",
            "优先检查 context orchestration、历史引用和 active object 恢复链路。",
            0.9,
        )
    if failure_type == "FAIL_CONTINUITY":
        return (
            f"多轮 continuity 断裂，evidence={_format_json(evidence)}",
            "优先回放 long-dialog case，核查 question authority、follow-up anchor 与 continuity contract。",
            0.9,
        )
    if failure_type == "FAIL_GROUNDEDNESS":
        return (
            f"grounding 结果不满足预期，evidence={_format_json(evidence)}",
            "优先检查 grounding decision 和 RAG 路由条件，不要先堆 fallback。",
            0.85,
        )
    if failure_type == "FAIL_RAG_MISS":
        return (
            f"RAG authority 或 exact authority 未命中，evidence={_format_json(evidence)}",
            "优先检查 authority extraction、KB 绑定和 exact question contract。",
            0.85,
        )
    if failure_type == "FAIL_INFRA":
        return (
            f"基础设施或依赖执行失败，evidence={_format_json(evidence)}",
            "先检查 runtime readiness、外部依赖、输入 artifact 和执行环境，不要先改语义逻辑。",
            0.95,
        )
    if failure_type == "FAIL_TIMEOUT":
        return (
            f"执行超时或慢响应，evidence={_format_json(evidence)}",
            "优先检查外部依赖、长对话运行模式和时延瓶颈。",
            0.85,
        )
    if failure_type == "FAIL_PRODUCT_BEHAVIOR":
        return (
            f"产品行为与预期不符，evidence={_format_json(evidence)}",
            "优先检查主链路输出 contract，而不是只改观测层说明。",
            0.8,
        )
    return (
        f"当前失败类型={failure_type or 'UNKNOWN'}，evidence={_format_json(evidence)}",
        "需要先补充失败分类规则或人工诊断。",
        0.6,
    )


def build_arr_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    case_results = list(payload.get("case_results") or [])
    execution_context = dict(payload.get("execution_context") or {})
    total_cases = int(summary.get("total_cases") or len(case_results) or 0)
    failed_cases = [item for item in case_results if item.get("status") == "FAIL"]
    skipped_cases = [item for item in case_results if item.get("status") == "SKIP"]
    baseline_diff = payload.get("baseline_diff")
    report_limitations: list[str] = []
    if not baseline_diff:
        report_limitations.append("未提供 baseline 或历史基线，diff 只展示当前快照。")
    if not case_results:
        report_limitations.append("当前没有 case_results，无法展开失败细节与时延分布。")
    if not any(item.get("failure_type") for item in case_results):
        report_limitations.append("当前没有失败用例，失败详情与 failure taxonomy 为空。")
    report_limitations.append("当前 ARR 尚未采集 token_usage、transcript grading、judge calibration 等旧仓增强字段。")
    if execution_context.get("api_base_url"):
        report_limitations.append("当前只有 long-dialog suite 走真实 /api/v1/ws；semantic/context/rag 仍是静态分析回归。")
    else:
        report_limitations.append("当前 full ARR 的 long-dialog 仍可能走本进程 runtime；若要真实服务验证，请传入 --api-base-url。")

    failures = [
        (
            lambda reason, remediation, confidence: {
                "case_key": f"{item['suite']}::{item['case_id']}",
                "case_name": item.get("case_name") or item.get("case_id"),
                "suite": item.get("suite"),
                "case_tier": item.get("case_tier"),
                "failure_type": item.get("failure_type"),
                "latency_ms": item.get("latency_ms"),
                "evidence": item.get("evidence") or {},
                "details": item.get("details") or {},
                "reason": reason,
                "remediation": remediation,
                "confidence": confidence,
            }
        )(*_build_failure_reason(item))
        for item in failed_cases
    ]
    skips = [
        {
            "case_key": f"{item['suite']}::{item['case_id']}",
            "suite": item.get("suite"),
            "case_tier": item.get("case_tier"),
            "evidence": item.get("evidence") or {},
        }
        for item in skipped_cases
    ]

    return {
        "run_summary": {
            "run_id": payload.get("run_id"),
            "generated_at": payload.get("generated_at"),
            "mode": payload.get("mode"),
            "release_id": (payload.get("release") or {}).get("release_id"),
            "total_cases": total_cases,
            "executed_cases": int(summary.get("executed_cases") or 0),
            "passed": int(summary.get("passed") or 0),
            "failed": int(summary.get("failed") or 0),
            "skipped": int(summary.get("skipped") or 0),
            "pass_rate": summary.get("pass_rate"),
            "pass_rate_pct": _round_or_none((summary.get("pass_rate") or 0.0) * 100, 1)
            if isinstance(summary.get("pass_rate"), (int, float))
            else None,
        },
        "gate_summary": dict(payload.get("gate_summary") or {}),
        "suite_breakdown": list(payload.get("suite_summaries") or []),
        "case_tier_distribution": [
            {
                "name": name,
                "count": int(count),
                "pct": _round_or_none(count / total_cases * 100, 1) if total_cases else 0.0,
            }
            for name, count in sorted((summary.get("case_tiers") or {}).items(), key=lambda item: item[0])
        ],
        "failure_type_distribution": [
            {
                "name": item["failure_type"],
                "count": int(item["count"]),
                "pct": _round_or_none(item["count"] / total_cases * 100, 1) if total_cases else 0.0,
            }
            for item in (summary.get("failure_taxonomy") or [])
        ],
        "status_distribution": _build_distribution_rows(case_results, key="status", total=total_cases),
        "latency_summary": _build_latency_summary(case_results),
        "failures": failures,
        "skips": skips,
        "baseline_diff": baseline_diff
        or {
            "baseline_run_id": None,
            "pass_rate_delta": None,
            "regressions": [],
            "new_failures": [],
            "recovered": [],
        },
        "execution_context": execution_context,
        "report_limitations": report_limitations,
    }


def _format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_arr_html(payload: dict[str, Any]) -> str:
    report = build_arr_report_payload(payload)
    run = report["run_summary"]
    gate = report["gate_summary"]
    baseline = report["baseline_diff"]

    def rows_html(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
        if not rows:
            return "<p>无</p>"
        header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
        body = []
        for row in rows:
            cells = "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key, _ in columns)
            body.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    suite_rows = rows_html(
        report["suite_breakdown"],
        [
            ("suite", "Suite"),
            ("total_cases", "Total"),
            ("passed", "Pass"),
            ("failed", "Fail"),
            ("skipped", "Skip"),
            ("pass_rate", "Pass Rate"),
        ],
    )
    failure_rows = rows_html(
        report["failures"],
        [
            ("case_key", "Case"),
            ("failure_type", "Failure Type"),
            ("case_tier", "Tier"),
            ("latency_ms", "Latency(ms)"),
            ("confidence", "Confidence"),
        ],
    )
    status_rows = rows_html(report["status_distribution"], [("name", "Status"), ("count", "Count"), ("pct", "Pct")])
    tier_rows = rows_html(
        report["case_tier_distribution"], [("name", "Tier"), ("count", "Count"), ("pct", "Pct")]
    )
    failure_type_rows = rows_html(
        report["failure_type_distribution"], [("name", "Type"), ("count", "Count"), ("pct", "Pct")]
    )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report["report_limitations"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>ARR Report - {html.escape(str(run.get('run_id') or 'unknown'))}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin: 0 0 12px; }}
    h2 {{ margin-top: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }}
    pre {{ white-space: pre-wrap; background: #0f172a; color: #e5e7eb; padding: 12px; border-radius: 10px; }}
    ul {{ margin: 8px 0 0 20px; }}
  </style>
</head>
<body>
  <h1>ARR Report</h1>
  <div class="grid">
    <div class="card">
      <h2>Run Summary</h2>
      <p><strong>Run ID:</strong> <span class="mono">{html.escape(str(run.get('run_id') or ''))}</span></p>
      <p><strong>Mode:</strong> {html.escape(str(run.get('mode') or ''))}</p>
      <p><strong>Release:</strong> <span class="mono">{html.escape(str(run.get('release_id') or 'unknown'))}</span></p>
      <p><strong>Pass:</strong> {run.get('passed')}/{run.get('total_cases')} ({run.get('pass_rate_pct')}%)</p>
      <p><strong>Failed:</strong> {run.get('failed')} | <strong>Skipped:</strong> {run.get('skipped')}</p>
    </div>
    <div class="card">
      <h2>Gate Summary</h2>
      <p><strong>gate_stable_pass_rate:</strong> {html.escape(str(gate.get('gate_stable_pass_rate')))}</p>
      <p><strong>regression_tier_failed:</strong> {html.escape(str(gate.get('regression_tier_failed')))}</p>
      <p><strong>new_regressions:</strong> {html.escape(str(gate.get('new_regressions')))}</p>
      <p><strong>bootstrap_mode:</strong> {html.escape(str(gate.get('bootstrap_mode')))}</p>
    </div>
    <div class="card">
      <h2>Latency</h2>
      <p><strong>avg:</strong> {html.escape(str(report['latency_summary'].get('avg_latency_ms')))} ms</p>
      <p><strong>p50:</strong> {html.escape(str(report['latency_summary'].get('p50_latency_ms')))} ms</p>
      <p><strong>p95:</strong> {html.escape(str(report['latency_summary'].get('p95_latency_ms')))} ms</p>
      <p><strong>max:</strong> {html.escape(str(report['latency_summary'].get('max_latency_ms')))} ms</p>
    </div>
    <div class="card">
      <h2>Baseline Diff</h2>
      <p><strong>baseline_run_id:</strong> <span class="mono">{html.escape(str(baseline.get('baseline_run_id') or 'none'))}</span></p>
      <p><strong>pass_rate_delta:</strong> {html.escape(str(baseline.get('pass_rate_delta')))}</p>
      <p><strong>regressions:</strong> {len(baseline.get('regressions') or [])}</p>
      <p><strong>new_failures:</strong> {len(baseline.get('new_failures') or [])}</p>
      <p><strong>recovered:</strong> {len(baseline.get('recovered') or [])}</p>
    </div>
  </div>
  <h2>Suite Breakdown</h2>
  {suite_rows}
  <h2>Status Distribution</h2>
  {status_rows}
  <h2>Case Tier Distribution</h2>
  {tier_rows}
  <h2>Failure Type Distribution</h2>
  {failure_type_rows}
  <h2>Failure Details</h2>
  {failure_rows}
  <h2>Baseline Detail</h2>
  <pre>{html.escape(_format_json(baseline))}</pre>
  <h2>Report Limitations</h2>
  <ul>{limitations}</ul>
</body>
</html>
"""


def write_arr_artifacts(payload: dict[str, Any], *, output_dir: Path | None = None) -> dict[str, str]:
    target_dir = (output_dir or DEFAULT_OUTPUT_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    mode = payload.get("mode") or "lite"
    json_path = target_dir / f"arr_run_{mode}_{stamp}.json"
    md_path = target_dir / f"arr_run_{mode}_{stamp}.md"
    html_path = target_dir / f"arr_report_{mode}_{stamp}.html"
    analysis_json_path = target_dir / f"arr_analysis_{mode}_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_arr_markdown(payload), encoding="utf-8")
    html_path.write_text(render_arr_html(payload), encoding="utf-8")
    analysis_json_path.write_text(
        json.dumps(build_arr_report_payload(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "html_path": str(html_path),
        "analysis_json_path": str(analysis_json_path),
    }
