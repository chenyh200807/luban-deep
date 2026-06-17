#!/usr/bin/env python3
"""Fail-closed contract runner for RichLeaf semantic runtime live A/B.

This script is intentionally not a provider caller by default. It records that
the live A/B runner exists, verifies the preflight shape, and blocks execution
until provider/runtime authorization is explicit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LIVE_AB_PREFLIGHT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_preflight_20260612/live_ab_preflight.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_20260612/semantic_runtime_live_ab.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_live_ab.v1"
REQUIRED_PREFLIGHT_NOT_EXERCISED = {
    "production_rag_retrieval",
    "legacy_runtime_live_path",
    "live_llm_semantic_judgment",
    "live_runtime_latency",
    "live_runtime_token_usage",
}
PLANNED_ARMS = [
    "current_rag_runtime",
    "legacy_runtime_or_projection",
    "rich_leaf_promoted_context",
    "artifact_first_llm_judge",
]
REQUIRED_LIVE_RESULT_METRICS = {
    "answerable_rate",
    "accuracy_rate",
    "evidence_citation_rate",
    "fail_open_rate",
    "mean_token_usage",
    "mean_latency_ms",
}


def _token_per_answerable(arm: dict[str, Any]) -> float:
    answerable_rate = float(arm.get("answerable_rate") or 0.0)
    mean_token_usage = float(arm.get("mean_token_usage") or 0.0)
    if answerable_rate <= 0.0:
        return float("inf")
    return round(mean_token_usage / answerable_rate, 4)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _preflight_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1":
        blockers.append(f"preflight_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_LIVE_RUNTIME_AB":
        blockers.append(f"preflight_not_ready:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "PREFLIGHT_ONLY":
        blockers.append(f"preflight_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("preflight_quality_claim_allowed")
    if payload.get("execution_mode") != "preflight_only":
        blockers.append(f"preflight_bad_execution_mode:{payload.get('execution_mode')}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"preflight_runtime_or_release_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"preflight_blockers_present:{summary.get('blocker_count')}")
    if summary.get("live_runtime_executed") is not False:
        blockers.append("preflight_live_runtime_executed")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("preflight_provider_calls_present")
    runtime_not_exercised = set(
        (payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}).get(
            "runtime_not_exercised"
        )
        or []
    )
    for item in sorted(REQUIRED_PREFLIGHT_NOT_EXERCISED - runtime_not_exercised):
        blockers.append(f"preflight_missing_runtime_not_exercised:{item}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"preflight_safety_{key}")
    if safety.get("production_write_count") not in (0, False):
        blockers.append("preflight_safety_production_write_count_nonzero")
    return blockers


def _live_results_blockers(payload: dict[str, Any] | None) -> list[str]:
    blockers: list[str] = []
    if not isinstance(payload, dict):
        return ["live_results_missing"]
    if payload.get("schema") != "luban_rich_leaf_semantic_runtime_live_ab_results.v1":
        blockers.append(f"live_results_schema_mismatch:{payload.get('schema')}")
    if payload.get("execution_authority") != "authorized_live_runtime_trace":
        blockers.append(f"live_results_bad_authority:{payload.get('execution_authority')}")
    if payload.get("runtime_exercised") is not True:
        blockers.append("live_results_runtime_not_exercised")
    if not payload.get("runtime_trace_ids"):
        blockers.append("live_results_missing_trace_ids")
    if int(payload.get("provider_call_count") or 0) <= 0:
        blockers.append("live_results_no_provider_calls")
    if int(payload.get("total_tokens") or 0) <= 0:
        blockers.append("live_results_no_token_usage")
    if not payload.get("models"):
        blockers.append("live_results_missing_models")

    arms = payload.get("arms") if isinstance(payload.get("arms"), list) else []
    arm_by_name = {str(arm.get("arm")): arm for arm in arms if isinstance(arm, dict)}
    for arm_name in PLANNED_ARMS:
        arm = arm_by_name.get(arm_name)
        if not arm:
            blockers.append(f"live_results_missing_arm:{arm_name}")
            continue
        if arm.get("status") != "completed":
            blockers.append(f"live_results_arm_not_completed:{arm_name}:{arm.get('status')}")
        for metric in sorted(REQUIRED_LIVE_RESULT_METRICS):
            if metric not in arm:
                blockers.append(f"live_results_arm_missing_metric:{arm_name}:{metric}")
        if int(arm.get("sample_count") or 0) <= 0:
            blockers.append(f"live_results_arm_no_samples:{arm_name}")
        if int(arm.get("provider_call_count") or 0) <= 0:
            blockers.append(f"live_results_arm_no_provider_calls:{arm_name}")
        if float(arm.get("fail_open_rate") or 0.0) != 0.0:
            blockers.append(f"live_results_arm_fail_open:{arm_name}")
        if float(arm.get("evidence_citation_rate") or 0.0) <= 0.0:
            blockers.append(f"live_results_arm_no_citations:{arm_name}")
        if float(arm.get("mean_token_usage") or 0.0) <= 0.0:
            blockers.append(f"live_results_arm_no_token_usage:{arm_name}")
        if float(arm.get("mean_latency_ms") or 0.0) <= 0.0:
            blockers.append(f"live_results_arm_no_latency:{arm_name}")

    treatment = arm_by_name.get("rich_leaf_promoted_context") or {}
    current_rag = arm_by_name.get("current_rag_runtime") or {}
    if treatment and current_rag:
        if float(treatment.get("accuracy_rate") or 0.0) < float(current_rag.get("accuracy_rate") or 0.0):
            blockers.append("live_results_treatment_accuracy_below_current_rag")
        treatment_tokens = float(treatment.get("mean_token_usage") or 0.0)
        current_tokens = float(current_rag.get("mean_token_usage") or 0.0)
        treatment_answerable = float(treatment.get("answerable_rate") or 0.0)
        current_answerable = float(current_rag.get("answerable_rate") or 0.0)
        token_efficiency_ok = _token_per_answerable(treatment) <= _token_per_answerable(current_rag)
        raw_token_ok = treatment_tokens <= current_tokens
        if not raw_token_ok and not (treatment_answerable > current_answerable and token_efficiency_ok):
            blockers.append("live_results_treatment_token_regression")
    return blockers


def _live_effect_table(live_results: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(live_results, dict):
        return [
            {
                "arm": arm,
                "status": "not_exercised",
                "sample_count": 0,
                "provider_call_count": 0,
                "quality_claim_allowed": False,
            }
            for arm in PLANNED_ARMS
        ]
    arms = live_results.get("arms") if isinstance(live_results.get("arms"), list) else []
    return [
        {
            "arm": str(arm.get("arm")),
            "status": str(arm.get("status")),
            "sample_count": int(arm.get("sample_count") or 0),
            "provider_call_count": int(arm.get("provider_call_count") or 0),
            "answerable_rate": float(arm.get("answerable_rate") or 0.0),
            "accuracy_rate": float(arm.get("accuracy_rate") or 0.0),
            "evidence_citation_rate": float(arm.get("evidence_citation_rate") or 0.0),
            "fail_open_rate": float(arm.get("fail_open_rate") or 0.0),
            "mean_token_usage": float(arm.get("mean_token_usage") or 0.0),
            "mean_token_per_answerable": _token_per_answerable(arm),
            "mean_latency_ms": float(arm.get("mean_latency_ms") or 0.0),
            "quality_claim_allowed": False,
        }
        for arm in arms
        if isinstance(arm, dict)
    ]


def run_live_ab(
    *,
    live_ab_preflight: dict[str, Any],
    allow_provider_calls: bool = False,
    live_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = _preflight_blockers(live_ab_preflight)
    if not blockers and not allow_provider_calls:
        blockers.append("provider_authorization_missing")
    if not blockers and allow_provider_calls:
        blockers.extend(_live_results_blockers(live_results))

    if any(blocker.startswith("preflight_") for blocker in blockers):
        verdict = "NO_GO_LIVE_PREFLIGHT_INVALID"
        execution_mode = "live_runtime_ab_not_exercised"
    elif "provider_authorization_missing" in blockers:
        verdict = "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED"
        execution_mode = "live_runtime_ab_blocked"
    elif any(blocker.startswith("live_results_") for blocker in blockers):
        verdict = "NO_GO_LIVE_RESULTS_INVALID"
        execution_mode = "live_runtime_ab_invalid"
    else:
        verdict = "PASS_LIVE_RUNTIME_AB_SHADOW"
        execution_mode = "live_runtime_ab_trace_ingested"

    preflight_summary = live_ab_preflight.get("summary") if isinstance(live_ab_preflight.get("summary"), dict) else {}
    live_case_count = 0
    if isinstance(live_results, dict):
        sample_counts = [
            int(arm.get("sample_count") or 0)
            for arm in (live_results.get("arms") if isinstance(live_results.get("arms"), list) else [])
            if isinstance(arm, dict)
        ]
        live_case_count = min(sample_counts) if sample_counts else 0
    live_runtime_executed = verdict == "PASS_LIVE_RUNTIME_AB_SHADOW"
    provider_call_count = int(live_results.get("provider_call_count") or 0) if isinstance(live_results, dict) else 0
    quality_claim_allowed = verdict == "PASS_LIVE_RUNTIME_AB_SHADOW"
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "live_ab_preflight": live_ab_preflight.get("schema"),
        },
        "verdict": verdict,
        "verdict_ceiling": "LIVE_RUNTIME_SHADOW_ONLY" if live_runtime_executed else "LIVE_RUNTIME_NOT_EXERCISED",
        "quality_claim_allowed": quality_claim_allowed,
        "quality_claim_scope": "live_shadow_only" if quality_claim_allowed else "not_allowed",
        "execution_mode": execution_mode,
        "cohort_scope": "authorized_live_runtime_shadow" if live_runtime_executed else "not_exercised_without_provider_authorization",
        "auth_mode": "none" if not allow_provider_calls else "provider_calls_requested",
        "runtime_entry": {
            "entrypoint": str(live_results.get("runtime_entrypoint") or "controlled_live_runtime_ab_runner")
            if live_runtime_executed and isinstance(live_results, dict)
            else "not_exercised",
            "runtime_exercised": live_runtime_executed,
            "runtime_trace_ids": list(live_results.get("runtime_trace_ids") or [])
            if live_runtime_executed and isinstance(live_results, dict)
            else [],
        },
        "provider_call_policy": {
            "provider_calls_allowed": bool(allow_provider_calls and live_runtime_executed),
            "provider_call_count": provider_call_count if live_runtime_executed else 0,
            "models": list(live_results.get("models") or []) if live_runtime_executed and isinstance(live_results, dict) else [],
            "prompt_tokens": int(live_results.get("prompt_tokens") or 0) if live_runtime_executed and isinstance(live_results, dict) else 0,
            "completion_tokens": int(live_results.get("completion_tokens") or 0)
            if live_runtime_executed and isinstance(live_results, dict)
            else 0,
            "total_tokens": int(live_results.get("total_tokens") or 0) if live_runtime_executed and isinstance(live_results, dict) else 0,
            "cost_recorded": bool(live_results.get("cost_recorded")) if live_runtime_executed and isinstance(live_results, dict) else False,
        },
        "arms": _live_effect_table(live_results) if live_runtime_executed else _live_effect_table(None),
        "effect_table": _live_effect_table(live_results) if live_runtime_executed else [],
        "summary": {
            "blocker_count": len(blockers),
            "planned_arm_count": len(PLANNED_ARMS),
            "live_case_count": live_case_count if live_runtime_executed else 0,
            "live_runtime_executed": live_runtime_executed,
            "provider_call_count": provider_call_count if live_runtime_executed else 0,
            "preflight_promoted_artifact_candidate_count": int(
                preflight_summary.get("promoted_artifact_candidate_count") or 0
            ),
            "preflight_source_backed_field_count": int(preflight_summary.get("source_backed_field_count") or 0),
            "preflight_nearline_eval_case_count": int(preflight_summary.get("nearline_eval_case_count") or 0),
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_live_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "blockers": blockers,
        "not_exercised_by_layer": {
            "runtime_not_exercised": []
            if live_runtime_executed
            else [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
            ],
            "release_not_exercised": [
                "production_default_decision",
                "release_truth_governance",
            ],
        },
        "not_exercised": [
            "learner_outcome_gain",
            "production_default_decision",
            "release_truth_governance",
        ]
        if live_runtime_executed
        else [
            "production_rag_retrieval",
            "legacy_runtime_live_path",
            "live_llm_semantic_judgment",
            "live_runtime_latency",
            "live_runtime_token_usage",
            "learner_outcome_gain",
            "production_default_decision",
            "release_truth_governance",
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-ab-preflight", type=Path, default=DEFAULT_LIVE_AB_PREFLIGHT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)

    report = run_live_ab(
        live_ab_preflight=_read_json(args.live_ab_preflight),
        allow_provider_calls=args.allow_provider_calls,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
