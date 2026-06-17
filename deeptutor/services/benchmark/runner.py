"""Canonical benchmark runner built on the benchmark registry."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from deeptutor.services.benchmark import BenchmarkRegistry, load_benchmark_registry
from deeptutor.services.benchmark.answer_citation_audit import audit_answer_citation_cases
from deeptutor.services.benchmark.exam_quality_bank import load_exam_quality_bank
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "fixtures" / "benchmark_phase1_registry.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "benchmark"


def _load_registry(registry_path: str | Path | None) -> BenchmarkRegistry:
    path = Path(registry_path).expanduser().resolve() if registry_path else DEFAULT_REGISTRY_PATH
    if not path.exists():
        raise FileNotFoundError(f"benchmark registry not found: {path}")
    return load_benchmark_registry(path)


def _dedupe_requested_suites(
    registry: BenchmarkRegistry,
    suite_names: Sequence[str] | None,
) -> list[str]:
    if suite_names is None:
        return list(registry.suite_names)
    requested: list[str] = []
    seen: set[str] = set()
    for raw_suite_name in suite_names:
        suite_name = str(raw_suite_name).strip()
        if not suite_name:
            continue
        if suite_name not in registry.suites:
            raise ValueError(f"Unknown benchmark suite: {suite_name}")
        if suite_name in seen:
            continue
        seen.add(suite_name)
        requested.append(suite_name)
    if not requested:
        raise ValueError("suite_names must not be empty")
    return requested


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


def _summarize_case_results(suite: str, case_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item["status"] for item in case_results)
    failure_counts = Counter(item["failure_type"] for item in case_results if item.get("failure_type"))
    tier_counts = Counter(item["case_tier"] for item in case_results if item.get("case_tier"))
    total = len(case_results)
    skipped = int(status_counts.get("SKIP", 0))
    executed = total - skipped
    passed = int(status_counts.get("PASS", 0))
    failed = int(status_counts.get("FAIL", 0))
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


def _build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item["status"] for item in case_results)
    failure_counts = Counter(item["failure_type"] for item in case_results if item.get("failure_type"))
    tier_counts = Counter(item["case_tier"] for item in case_results if item.get("case_tier"))
    total = len(case_results)
    skipped = int(status_counts.get("SKIP", 0))
    executed = total - skipped
    passed = int(status_counts.get("PASS", 0))
    failed = int(status_counts.get("FAIL", 0))
    gate_stable_cases = [
        item
        for item in case_results
        if item.get("case_tier") == "gate_stable" and item.get("status") != "SKIP"
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
        "gate_stable_pass_rate": round(gate_stable_passed / len(gate_stable_cases), 4)
        if gate_stable_cases
        else None,
        "regression_tier_failed": regression_tier_failed,
        "failure_taxonomy": [
            {"failure_type": failure_type, "count": int(count)}
            for failure_type, count in sorted(failure_counts.items(), key=lambda item: item[0])
        ],
    }


def _aggregate_failure_taxonomy(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    taxonomy = Counter(item["failure_type"] for item in case_results if item.get("failure_type"))
    return [
        {"failure_type": failure_type, "count": int(count)}
        for failure_type, count in sorted(taxonomy.items(), key=lambda item: item[0])
    ]


def _build_blind_spots(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blind_spots: list[dict[str, Any]] = []
    for item in case_results:
        if item.get("status") != "SKIP":
            continue
        blind_spots.append(
            {
                "suite": item.get("suite"),
                "case_id": item.get("case_id"),
                "case_name": item.get("case_name"),
                "reason": (item.get("evidence") or {}).get("reason") or "skipped_case",
            }
        )
    return blind_spots


def _case_metadata(case: Any) -> dict[str, Any]:
    return {
        "dataset_id": case.dataset_id,
        "dataset_version": case.dataset_version,
        "case_id": case.case_id,
        "contract_domain": case.contract_domain,
        "case_tier": case.case_tier,
        "execution_kind": case.execution_kind,
        "surface": case.surface,
        "expected_contract": case.expected_contract,
        "failure_taxonomy_scope": case.failure_taxonomy_scope,
        "source_fixture": case.source_fixture,
        "origin_type": case.origin_type,
        "origin_ref": case.origin_ref,
        "promotion_status": case.promotion_status,
        "promoted_from_case_id": case.promoted_from_case_id,
    }


def _canonicalize_case_result(
    *,
    benchmark_suite: str,
    source_suite: str,
    source_case_set: str,
    case_result: dict[str, Any],
    case_metadata: dict[str, Any],
) -> dict[str, Any]:
    canonical = dict(case_result)
    canonical["suite"] = benchmark_suite
    canonical["source_suite"] = source_suite
    canonical["source_case_set"] = source_case_set
    canonical["contract_domain"] = case_metadata.get("contract_domain")
    canonical["execution_kind"] = case_metadata.get("execution_kind")
    canonical["surface"] = case_metadata.get("surface")
    canonical["expected_contract"] = case_metadata.get("expected_contract")
    canonical["case_tier"] = case_metadata.get("case_tier") or canonical.get("case_tier")
    canonical["origin_type"] = case_metadata.get("origin_type")
    canonical["origin_ref"] = case_metadata.get("origin_ref")
    canonical["promotion_status"] = case_metadata.get("promotion_status")
    canonical["promoted_from_case_id"] = case_metadata.get("promoted_from_case_id")
    return canonical


def _compute_baseline_diff(
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
        baseline_status = baseline.get("status") if baseline else None
        current_status = current.get("status")
        if baseline_status == "PASS" and current_status == "FAIL":
            regressions.append({"case_key": case_key, "failure_type": current.get("failure_type")})
        elif baseline is None and current_status == "FAIL":
            new_failures.append({"case_key": case_key, "failure_type": current.get("failure_type")})
        elif baseline_status == "FAIL" and current_status == "PASS":
            recovered.append({"case_key": case_key})
    baseline_summary = baseline_payload.get("summary") or {}
    current_summary = current_payload.get("summary") or {}
    baseline_pass_rate = baseline_summary.get("pass_rate")
    current_pass_rate = current_summary.get("pass_rate")
    return {
        "baseline_run_id": (baseline_payload.get("run_manifest") or {}).get("run_id")
        or baseline_payload.get("run_id"),
        "current_run_id": (current_payload.get("run_manifest") or {}).get("run_id")
        or current_payload.get("run_id"),
        "baseline_pass_rate": baseline_pass_rate,
        "current_pass_rate": current_pass_rate,
        "pass_rate_delta": round(current_pass_rate - baseline_pass_rate, 4)
        if isinstance(baseline_pass_rate, (int, float)) and isinstance(current_pass_rate, (int, float))
        else None,
        "regressions": regressions,
        "new_failures": new_failures,
        "recovered": recovered,
    }


def _build_runtime_evidence_links(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for item in case_results:
        details = item.get("details") or {}
        evidence = item.get("evidence") or {}
        for key in ("artifact_path", "metrics_url", "trace_url"):
            value = details.get(key) or evidence.get(key)
            if value:
                links.append({"suite": item.get("suite"), "case_id": item.get("case_id"), key: value})
    return links


async def _run_semantic_case_set() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from deeptutor.services.observability.arr_runner import run_semantic_router_suite

    return await run_semantic_router_suite()


def _run_context_case_set() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from deeptutor.services.observability.arr_runner import run_context_orchestration_suite

    return run_context_orchestration_suite()


def _run_rag_case_set() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from deeptutor.services.observability.arr_runner import run_rag_grounding_suite

    return run_rag_grounding_suite()


async def _run_long_dialog_case_set(
    *,
    api_base_url: str | None,
    long_dialog_mode: str,
    response_mode: str,
    explicit_source_json: str | None = None,
    max_cases: int | None = None,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from deeptutor.services.observability.arr_runner import run_local_long_dialog_suite, run_long_dialog_suite

    if api_base_url:
        return await run_long_dialog_suite(
            mode=long_dialog_mode,
            explicit_source_json=explicit_source_json,
            max_cases=max_cases,
            output_dir=output_dir,
            api_base_url=api_base_url,
            response_mode=response_mode,
        )
    return await run_local_long_dialog_suite()


def _run_node_surface_case_set(
    *,
    case_metadata: dict[str, Any],
    command: list[str],
    pass_reason: str,
    fail_reason: str,
    timeout_reason: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case_metadata["case_id"])
    if shutil.which("node") is None:
        result = _make_case_result(
            suite="exploration_lab",
            case_id=case_id,
            case_name=case_id,
            status="SKIP",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            evidence={"reason": "missing_node_runtime", "source_fixture": case_metadata.get("source_fixture")},
            details={"command": command, "surface": case_metadata.get("surface")},
        )
        return _summarize_case_results("exploration_lab", [result]), [result]

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        result = _make_case_result(
            suite="exploration_lab",
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            failure_type="FAIL_TIMEOUT",
            evidence={
                "reason": timeout_reason,
                "stdout_tail": str(exc.stdout or "")[-1000:],
                "stderr_tail": str(exc.stderr or "")[-1000:],
                "source_fixture": case_metadata.get("source_fixture"),
            },
            details={"command": command, "surface": case_metadata.get("surface")},
        )
        return _summarize_case_results("exploration_lab", [result]), [result]
    if completed.returncode == 0:
        result = _make_case_result(
            suite="exploration_lab",
            case_id=case_id,
            case_name=case_id,
            status="PASS",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            evidence={
                "reason": pass_reason,
                "stdout_tail": completed.stdout[-1000:],
                "source_fixture": case_metadata.get("source_fixture"),
            },
            details={"command": command, "surface": case_metadata.get("surface")},
        )
        return _summarize_case_results("exploration_lab", [result]), [result]

    result = _make_case_result(
        suite="exploration_lab",
        case_id=case_id,
        case_name=case_id,
        status="FAIL",
        case_tier=str(case_metadata.get("case_tier") or "exploratory"),
        failure_type="FAIL_SURFACE_DELIVERY",
        evidence={
            "reason": fail_reason,
            "stdout_tail": completed.stdout[-1000:],
            "stderr_tail": completed.stderr[-1000:],
            "source_fixture": case_metadata.get("source_fixture"),
        },
        details={
            "command": command,
            "contract_domain": case_metadata.get("contract_domain"),
            "execution_kind": case_metadata.get("execution_kind"),
            "surface": case_metadata.get("surface"),
        },
    )
    return _summarize_case_results("exploration_lab", [result]), [result]


def _run_wx_surface_case_set(case_metadata: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _run_node_surface_case_set(
        case_metadata=case_metadata,
        command=["node", "wx_miniprogram/tests/test_renderer_parity.js"],
        pass_reason="node_renderer_parity_passed",
        fail_reason="node_renderer_parity_failed",
        timeout_reason="node_renderer_parity_timeout",
    )


def _run_yousenwebview_surface_case_set(case_metadata: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _run_node_surface_case_set(
        case_metadata=case_metadata,
        command=["node", "yousenwebview/tests/test_chat_send_surface_telemetry.js"],
        pass_reason="node_yousenwebview_surface_telemetry_passed",
        fail_reason="node_yousenwebview_surface_telemetry_failed",
        timeout_reason="node_yousenwebview_surface_telemetry_timeout",
    )


def _run_luban_case_grading_case_set(
    *,
    case_metadata: dict[str, Any],
    output_dir: Path | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case_metadata["case_id"])
    fixture = PROJECT_ROOT / str(case_metadata.get("source_fixture") or "")
    target_dir = (output_dir or DEFAULT_OUTPUT_DIR) / "luban_case_grading_shadow"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "poc_luban_case_grading_three_arms.py"),
        "--all",
        "--fixture",
        str(fixture),
        "--output-dir",
        str(target_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        result = _make_case_result(
            suite="luban-case-grading-shadow",
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            failure_type="FAIL_TIMEOUT",
            evidence={"reason": "case_grading_eval_timeout", "stdout_tail": str(exc.stdout or "")[-1000:]},
            details={"command": command, "source_fixture": case_metadata.get("source_fixture")},
        )
        return _summarize_case_results("luban-case-grading-shadow", [result]), [result]
    if completed.returncode != 0:
        result = _make_case_result(
            suite="luban-case-grading-shadow",
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            failure_type="FAIL_GRADING_EVAL",
            evidence={
                "reason": "case_grading_eval_failed",
                "stdout_tail": completed.stdout[-1000:],
                "stderr_tail": completed.stderr[-1000:],
            },
            details={"command": command, "source_fixture": case_metadata.get("source_fixture")},
        )
        return _summarize_case_results("luban-case-grading-shadow", [result]), [result]
    try:
        script_payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        script_payload = {"stdout_tail": completed.stdout[-1000:]}
    summary = script_payload.get("summary") if isinstance(script_payload.get("summary"), dict) else {}
    artifact_summary = summary.get("artifact_first") if isinstance(summary.get("artifact_first"), dict) else {}
    baseline_summary = summary.get("baseline") if isinstance(summary.get("baseline"), dict) else {}
    artifact_delta = artifact_summary.get("mean_abs_score_delta")
    baseline_delta = baseline_summary.get("mean_abs_score_delta")
    directional_go = (
        isinstance(artifact_delta, (int, float))
        and isinstance(baseline_delta, (int, float))
        and artifact_delta < baseline_delta
    )
    result = _make_case_result(
        suite="luban-case-grading-shadow",
        case_id=case_id,
        case_name=case_id,
        status="PASS",
        case_tier=str(case_metadata.get("case_tier") or "exploratory"),
        evidence={
            "reason": "case_grading_eval_completed",
            "directional_go": directional_go,
            "artifact_first": artifact_summary,
            "baseline": baseline_summary,
            "rag": summary.get("rag") if isinstance(summary.get("rag"), dict) else {},
            "json_path": script_payload.get("json_path"),
            "md_path": script_payload.get("md_path"),
        },
        details={"command": command, "source_fixture": case_metadata.get("source_fixture")},
    )
    return _summarize_case_results("luban-case-grading-shadow", [result]), [result]


def _run_answer_citation_case_set(
    *,
    case_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case_metadata["case_id"])
    fixture = PROJECT_ROOT / str(case_metadata.get("source_fixture") or "")
    try:
        audit = audit_answer_citation_cases(fixture)
    except Exception as exc:
        result = _make_case_result(
            suite="answer-citation-shadow",
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "exploratory"),
            failure_type="FAIL_UNSUPPORTED_CITATION",
            evidence={
                "reason": "answer_citation_audit_exception",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "source_fixture": case_metadata.get("source_fixture"),
            },
            details={"source_fixture": case_metadata.get("source_fixture")},
        )
        return _summarize_case_results("answer-citation-shadow", [result]), [result]

    citation_accuracy = float(audit.get("citation_accuracy") or 0.0)
    footer_coverage = float(audit.get("footer_coverage") or 0.0)
    hidden_leak_count = int(audit.get("hidden_leak_count") or 0)
    status = "PASS"
    failure_type: str | None = None
    if hidden_leak_count:
        status = "FAIL"
        failure_type = "FAIL_HIDDEN_AUTHORITY_LEAK"
    elif footer_coverage < 1.0:
        status = "FAIL"
        failure_type = "FAIL_CITATION_MISSING"
    elif citation_accuracy < 0.9:
        status = "FAIL"
        failure_type = "FAIL_UNSUPPORTED_CITATION"
    result = _make_case_result(
        suite="answer-citation-shadow",
        case_id=case_id,
        case_name=case_id,
        status=status,
        case_tier=str(case_metadata.get("case_tier") or "exploratory"),
        failure_type=failure_type,
        evidence={
            "reason": "answer_citation_audit_completed",
            "citation_accuracy": citation_accuracy,
            "footer_coverage": footer_coverage,
            "hidden_leak_count": hidden_leak_count,
            "suite": audit.get("suite"),
            "source_fixture": case_metadata.get("source_fixture"),
        },
        details={"results": audit.get("results") or []},
    )
    return _summarize_case_results("answer-citation-shadow", [result]), [result]


def _run_real_exam_quality_bank_case_set(
    *,
    case_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    suite_name = "real_exam_quality_spine"
    case_id = str(case_metadata["case_id"])
    fixture = PROJECT_ROOT / str(case_metadata.get("source_fixture") or "")
    started_at = time.perf_counter()
    try:
        bank_payload = json.loads(fixture.read_text(encoding="utf-8"))
        questions = load_exam_quality_bank(fixture)
    except FileNotFoundError:
        result = _make_case_result(
            suite=suite_name,
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "regression_tier"),
            failure_type="FAIL_SOURCE_LAUNDERING",
            evidence={"reason": "exam_quality_bank_missing", "source_fixture": case_metadata.get("source_fixture")},
            details={"source_fixture": str(fixture)},
        )
        return _summarize_case_results(suite_name, [result]), [result]
    except Exception as exc:
        result = _make_case_result(
            suite=suite_name,
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "regression_tier"),
            failure_type="FAIL_SOURCE_LAUNDERING",
            evidence={
                "reason": "exam_quality_bank_load_failed",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "source_fixture": case_metadata.get("source_fixture"),
            },
            details={"source_fixture": str(fixture)},
        )
        return _summarize_case_results(suite_name, [result]), [result]

    raw_questions = bank_payload.get("questions") if isinstance(bank_payload, dict) else None
    invalid: list[dict[str, Any]] = []
    source_missing = 0
    by_year: dict[str, dict[str, int]] = {}
    for question in questions:
        exact = question.exact_question
        correct = str(exact.get("correct_answer") or "").strip()
        options = exact.get("options") if isinstance(exact.get("options"), dict) else {}
        year_key = str(question.year)
        year_bucket = by_year.setdefault(year_key, {"single_choice": 0, "multiple_choice": 0})
        if question.type in year_bucket:
            year_bucket[question.type] += 1
        if not str(exact.get("stem") or "").strip():
            invalid.append({"question_id": question.question_id, "reason": "missing_stem"})
        if not correct or any(letter not in options for letter in correct):
            invalid.append({"question_id": question.question_id, "reason": "answer_not_in_options"})
        if question.type == "single_choice" and len(correct) != 1:
            invalid.append({"question_id": question.question_id, "reason": "single_choice_answer_not_single"})
        if question.type == "multiple_choice" and len(correct) < 2:
            invalid.append({"question_id": question.question_id, "reason": "multiple_choice_answer_not_multiple"})
        source = next(
            (
                raw.get("source")
                for raw in raw_questions or []
                if isinstance(raw, dict) and raw.get("question_id") == question.question_id
            ),
            {},
        )
        if not isinstance(source, dict) or not source.get("docs_2026_path"):
            source_missing += 1

    declared_count = int(bank_payload.get("question_count") or 0) if isinstance(bank_payload, dict) else 0
    raw_count = len(raw_questions) if isinstance(raw_questions, list) else -1
    count_mismatch = declared_count != len(questions) or raw_count != len(questions)
    no_questions = not questions
    status = "FAIL" if (invalid or source_missing or count_mismatch or no_questions) else "PASS"
    failure_type = None
    reason = "docs_2026_real_exam_bank_ready"
    if status == "FAIL":
        failure_type = "FAIL_ANSWER_KEY_OVERRIDE" if invalid else "FAIL_SOURCE_LAUNDERING"
        reason = "docs_2026_real_exam_bank_invalid"
    latency_ms = (time.perf_counter() - started_at) * 1000.0
    evidence = {
        "reason": reason,
        "question_count": len(questions),
        "declared_question_count": declared_count,
        "raw_question_count": raw_count,
        "years_included": bank_payload.get("years_included") if isinstance(bank_payload, dict) else [],
        "by_year": by_year,
        "source_docs_2026_root": bank_payload.get("source_docs_2026_root") if isinstance(bank_payload, dict) else None,
        "excluded_types": bank_payload.get("excluded_types") if isinstance(bank_payload, dict) else {},
        "invalid_preview": invalid[:5],
        "source_missing_count": source_missing,
        "source_fixture": case_metadata.get("source_fixture"),
    }
    result = _make_case_result(
        suite=suite_name,
        case_id=case_id,
        case_name=case_id,
        status=status,
        case_tier=str(case_metadata.get("case_tier") or "regression_tier"),
        failure_type=failure_type,
        evidence=evidence,
        latency_ms=latency_ms,
        details={"source_fixture": str(fixture)},
    )
    return _summarize_case_results(suite_name, [result]), [result]


def _run_metadata_gap_case_set(
    *,
    suite_name: str,
    case_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case_metadata["case_id"])
    result = _make_case_result(
        suite=suite_name,
        case_id=case_id,
        case_name=case_id,
        status="SKIP",
        case_tier=str(case_metadata.get("case_tier") or "exploratory"),
        evidence={
            "reason": "benchmark_case_runner_not_implemented",
            "expected_contract": case_metadata.get("expected_contract"),
            "failure_taxonomy_scope": list(case_metadata.get("failure_taxonomy_scope") or []),
            "source_fixture": case_metadata.get("source_fixture"),
        },
        details={
            "contract_domain": case_metadata.get("contract_domain"),
            "execution_kind": case_metadata.get("execution_kind"),
            "surface": case_metadata.get("surface"),
            "origin_ref": case_metadata.get("origin_ref"),
            "promotion_status": case_metadata.get("promotion_status"),
        },
    )
    return _summarize_case_results(suite_name, [result]), [result]


async def _run_surface_web_case_set(
    *,
    case_metadata: dict[str, Any],
    api_base_url: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case_metadata["case_id"])
    if not api_base_url:
        result = _make_case_result(
            suite="incident_replay",
            case_id=case_id,
            case_name=case_id,
            status="SKIP",
            case_tier=str(case_metadata.get("case_tier") or "incident_replay"),
            evidence={"reason": "missing_api_base_url", "source_fixture": case_metadata.get("source_fixture")},
            details={
                "contract_domain": case_metadata.get("contract_domain"),
                "execution_kind": case_metadata.get("execution_kind"),
                "surface": case_metadata.get("surface"),
            },
        )
        return _summarize_case_results("incident_replay", [result]), [result]

    from deeptutor.services.observability.surface_ack_smoke import run_surface_ack_smoke

    try:
        payload = run_surface_ack_smoke(
            api_base_url=api_base_url,
            surface=str(case_metadata.get("surface") or "web"),
            session_id=f"benchmark-surface-{int(time.time())}",
            turn_id=f"benchmark-turn-{int(time.time())}",
            metadata={"source": "benchmark_runner", "case_id": case_id},
        )
    except Exception as exc:
        result = _make_case_result(
            suite="incident_replay",
            case_id=case_id,
            case_name=case_id,
            status="FAIL",
            case_tier=str(case_metadata.get("case_tier") or "incident_replay"),
            failure_type="FAIL_SURFACE_DELIVERY",
            evidence={
                "reason": "surface_ack_smoke_exception",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "source_fixture": case_metadata.get("source_fixture"),
            },
            details={
                "api_base_url": api_base_url,
                "contract_domain": case_metadata.get("contract_domain"),
                "execution_kind": case_metadata.get("execution_kind"),
                "surface": case_metadata.get("surface"),
            },
        )
        return _summarize_case_results("incident_replay", [result]), [result]

    status = "PASS" if payload.get("passed") else "FAIL"
    result = _make_case_result(
        suite="incident_replay",
        case_id=case_id,
        case_name=case_id,
        status=status,
        case_tier=str(case_metadata.get("case_tier") or "incident_replay"),
        failure_type=None if status == "PASS" else "FAIL_SURFACE_DELIVERY",
        evidence={"surface": payload.get("surface"), "missing_requirements": payload.get("missing_requirements") or []},
        details={"metrics_url": payload.get("metrics_url"), "session_id": payload.get("session_id"), "turn_id": payload.get("turn_id")},
    )
    return _summarize_case_results("incident_replay", [result]), [result]


async def _collect_suite_execution(
    *,
    registry: BenchmarkRegistry,
    suite_name: str,
    api_base_url: str | None,
    long_dialog_mode: str,
    response_mode: str,
    explicit_long_dialog_source_json: str | None = None,
    long_dialog_max_cases: int | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    suite = registry.suites[suite_name]
    canonical_case_results: list[dict[str, Any]] = []
    legacy_suite_summaries: list[dict[str, Any]] = []
    legacy_case_results: list[dict[str, Any]] = []
    blind_spots: list[dict[str, Any]] = []
    for case_id in suite.case_ids:
        case = registry.cases[case_id]
        case_metadata = _case_metadata(case)
        include_in_legacy = True
        if case_id == "routing.semantic_router.case_set":
            legacy_summary, legacy_results = await _run_semantic_case_set()
        elif case_id == "routing.context_orchestration.case_set":
            legacy_summary, legacy_results = _run_context_case_set()
        elif case_id == "grounding.rag.case_set":
            legacy_summary, legacy_results = _run_rag_case_set()
        elif case_id == "quality.real_exam_bank.docs_2026.mcq":
            legacy_summary, legacy_results = _run_real_exam_quality_bank_case_set(
                case_metadata=case_metadata,
            )
        elif case_id == "continuity.long_dialog.focus":
            legacy_summary, legacy_results = await _run_long_dialog_case_set(
                api_base_url=api_base_url,
                long_dialog_mode=long_dialog_mode,
                response_mode=response_mode,
                explicit_source_json=explicit_long_dialog_source_json,
                max_cases=long_dialog_max_cases,
                output_dir=output_dir,
            )
        elif case_id == "surface.wx.renderer.parity":
            legacy_summary, legacy_results = _run_wx_surface_case_set(case_metadata)
            include_in_legacy = False
        elif case_id == "surface.yousenwebview.telemetry.smoke":
            legacy_summary, legacy_results = _run_yousenwebview_surface_case_set(case_metadata)
            include_in_legacy = False
        elif case_id == "grading.luban_case_golden.v0":
            legacy_summary, legacy_results = _run_luban_case_grading_case_set(
                case_metadata=case_metadata,
                output_dir=output_dir,
            )
            include_in_legacy = False
        elif case_id == "answer.citation.paper_style.v0":
            legacy_summary, legacy_results = _run_answer_citation_case_set(
                case_metadata=case_metadata,
            )
            include_in_legacy = False
        elif case_id == "surface.web.ack.smoke":
            legacy_summary, legacy_results = await _run_surface_web_case_set(
                case_metadata=case_metadata,
                api_base_url=api_base_url,
            )
            include_in_legacy = False
        else:
            legacy_summary, legacy_results = _run_metadata_gap_case_set(
                suite_name=suite_name,
                case_metadata=case_metadata,
            )
            include_in_legacy = False

        canonical_results = [
            _canonicalize_case_result(
                benchmark_suite=suite_name,
                source_suite=str(item["suite"]),
                source_case_set=case_id,
                case_result=item,
                case_metadata=case_metadata,
            )
            for item in legacy_results
        ]
        if include_in_legacy:
            legacy_suite_summaries.append(legacy_summary)
            legacy_case_results.extend(legacy_results)
        canonical_case_results.extend(canonical_results)
        blind_spots.extend(_build_blind_spots(canonical_results))
        if not canonical_results:
            blind_spots.append({"suite": suite_name, "case_id": case_id, "reason": "no_canonical_case_results", "source_fixture": case.source_fixture})
    return {
        "canonical_case_results": canonical_case_results,
        "legacy_suite_summaries": legacy_suite_summaries,
        "legacy_case_results": legacy_case_results,
        "blind_spots": blind_spots,
    }


async def run_benchmark(
    *,
    suite_names: Sequence[str] | None = None,
    registry_path: str | Path | None = None,
    baseline_payload: dict[str, Any] | None = None,
    api_base_url: str | None = None,
    response_mode: str = "smart",
    long_dialog_mode: str = "lite",
    explicit_long_dialog_source_json: str | None = None,
    long_dialog_max_cases: int | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    registry = _load_registry(registry_path)
    requested_suite_names = _dedupe_requested_suites(registry, suite_names)
    timestamp = int(time.time())
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    release_spine = get_release_lineage_snapshot()
    suite_summaries: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    legacy_suite_summaries: list[dict[str, Any]] = []
    legacy_case_results: list[dict[str, Any]] = []
    blind_spots: list[dict[str, Any]] = []
    effective_long_dialog_max_cases = long_dialog_max_cases or (
        1 if long_dialog_mode == "lite" else None
    )
    for suite_name in requested_suite_names:
        suite_execution = await _collect_suite_execution(
            registry=registry,
            suite_name=suite_name,
            api_base_url=api_base_url,
            long_dialog_mode=long_dialog_mode,
            response_mode=response_mode,
            explicit_long_dialog_source_json=explicit_long_dialog_source_json,
            long_dialog_max_cases=effective_long_dialog_max_cases,
            output_dir=output_dir,
        )
        canonical_results = suite_execution["canonical_case_results"]
        suite_summaries.append(_summarize_case_results(suite_name, canonical_results))
        case_results.extend(canonical_results)
        legacy_suite_summaries.extend(suite_execution["legacy_suite_summaries"])
        legacy_case_results.extend(suite_execution["legacy_case_results"])
        blind_spots.extend(suite_execution["blind_spots"])
    summary = _build_summary(case_results)
    legacy_summary = _build_summary(legacy_case_results)
    legacy_suite_names = {
        str(item.get("suite") or "").strip()
        for item in legacy_suite_summaries
        if str(item.get("suite") or "").strip()
    }
    legacy_execution_modes = {
        suite: "static_analysis"
        for suite in sorted(legacy_suite_names)
        if not suite.startswith("long-dialog")
    }
    long_dialog_suite = "long-dialog-focus" if long_dialog_mode == "lite" else "long-dialog-full"
    if long_dialog_suite in legacy_suite_names:
        legacy_execution_modes[long_dialog_suite] = "live_ws" if api_base_url else "in_process_runtime"
    payload: dict[str, Any] = {
        "run_manifest": {
            "run_id": f"benchmark-{timestamp}",
            "generated_at": generated_at,
            "registry_path": str(Path(registry_path).expanduser().resolve()) if registry_path else str(DEFAULT_REGISTRY_PATH),
            "registry_version": registry.version,
            "dataset_id": registry.dataset_id,
            "dataset_version": registry.dataset_version,
            "requested_suites": requested_suite_names,
            "runner": "canonical-benchmark-runner",
            "response_mode": response_mode,
            "long_dialog_mode": long_dialog_mode,
        },
        "release_spine": release_spine,
        "suite_summaries": suite_summaries,
        "case_results": case_results,
        "failure_taxonomy": _aggregate_failure_taxonomy(case_results),
        "summary": summary,
        "baseline_diff": None,
        "runtime_evidence_links": _build_runtime_evidence_links(case_results),
        "blind_spots": blind_spots,
        "legacy": {
            "run_id": f"arr-{long_dialog_mode}-{timestamp}",
            "generated_at": generated_at,
            "mode": long_dialog_mode,
            "release": release_spine,
            "suite_summaries": legacy_suite_summaries,
            "case_results": legacy_case_results,
            "summary": legacy_summary,
            "execution_context": {
                "api_base_url": api_base_url.rstrip("/") if api_base_url else None,
                "response_mode": str(response_mode or "smart"),
                "suite_execution_modes": legacy_execution_modes,
            },
            "baseline_diff": None,
            "gate_summary": {
                "bootstrap_mode": True,
                "gate_stable_pass_rate": legacy_summary.get("gate_stable_pass_rate"),
                "regression_tier_failed": legacy_summary.get("regression_tier_failed"),
                "new_regressions": 0,
            },
        },
    }
    payload["baseline_diff"] = _compute_baseline_diff(
        baseline_payload=baseline_payload,
        current_payload=payload,
    )
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    manifest = payload.get("run_manifest") or {}
    summary = payload.get("summary") or {}
    lines = [
        "# Benchmark Run",
        "",
        f"- run_id: `{manifest.get('run_id')}`",
        f"- generated_at: {manifest.get('generated_at')}",
        f"- registry_version: `{manifest.get('registry_version')}`",
        f"- dataset_id: `{manifest.get('dataset_id')}`",
        f"- requested_suites: `{', '.join(manifest.get('requested_suites') or [])}`",
        "",
        "## Summary",
        "",
        f"- total_cases: {summary.get('total_cases')}",
        f"- executed_cases: {summary.get('executed_cases')}",
        f"- passed: {summary.get('passed')}",
        f"- failed: {summary.get('failed')}",
        f"- skipped: {summary.get('skipped')}",
        f"- pass_rate: {summary.get('pass_rate')}",
        "",
        "## Blind Spots",
        "",
    ]
    blind_spots = payload.get("blind_spots") or []
    if not blind_spots:
        lines.append("- none")
    else:
        for item in blind_spots:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def write_benchmark_artifacts(
    payload: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = (output_dir or DEFAULT_OUTPUT_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = target_dir / f"benchmark_run_{stamp}.json"
    md_path = target_dir / f"benchmark_run_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
