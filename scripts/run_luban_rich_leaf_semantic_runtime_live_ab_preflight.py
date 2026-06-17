#!/usr/bin/env python3
"""Preflight gate for a future live RichLeaf semantic runtime A/B.

This gate intentionally does not run live providers or production RAG. It checks
that the promoted RichLeaf context has passed the current offline/nearline
projection gates and emits a concrete live A/B plan with all live dimensions
marked not_exercised.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_NEARLINE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_nearline_ab_20260612/semantic_runtime_nearline_ab.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_preflight_20260612/live_ab_preflight.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1"
PLANNED_ARMS = [
    "current_rag_runtime",
    "legacy_runtime_or_projection",
    "rich_leaf_promoted_context",
    "artifact_first_llm_judge",
]
REQUIRED_NEARLINE_NOT_EXERCISED = {
    "production_rag_retrieval",
    "live_llm_semantic_judgment",
    "live_runtime_latency",
    "live_runtime_token_usage",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _classification_blocks(prefix: str, payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{prefix}_{key}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"{prefix}_safety_{key}")
    if safety.get("production_write_count") not in (0, False):
        blockers.append(f"{prefix}_safety_production_write_count_nonzero")


def run_live_ab_preflight(*, field_promotion_review: dict[str, Any], nearline_ab: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"field_promotion_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"field_promotion_not_pass:{field_promotion_review.get('verdict')}")
    _classification_blocks("field_promotion", field_promotion_review, blockers)
    field_summary = field_promotion_review.get("summary") if isinstance(field_promotion_review.get("summary"), dict) else {}
    if int(field_summary.get("source_backed_field_count") or 0) <= 0:
        blockers.append("field_promotion_no_source_backed_fields")
    if int(field_summary.get("validation_failure_count") or 0) != 0:
        blockers.append("field_promotion_validation_failures_present")

    if nearline_ab.get("schema") != "luban_rich_leaf_semantic_runtime_nearline_ab.v1":
        blockers.append(f"nearline_schema_mismatch:{nearline_ab.get('schema')}")
    if nearline_ab.get("verdict") != "PASS":
        blockers.append(f"nearline_not_pass:{nearline_ab.get('verdict')}")
    if nearline_ab.get("verdict_ceiling") != "NEARLINE_RETRIEVAL_PROJECTION":
        blockers.append(f"nearline_bad_ceiling:{nearline_ab.get('verdict_ceiling')}")
    if nearline_ab.get("quality_claim_allowed") is not False:
        blockers.append("nearline_quality_claim_allowed")
    _classification_blocks("nearline", nearline_ab, blockers)
    nearline_summary = nearline_ab.get("summary") if isinstance(nearline_ab.get("summary"), dict) else {}
    if int(nearline_summary.get("eval_case_count") or 0) <= 0:
        blockers.append("nearline_no_eval_cases")
    if int(nearline_summary.get("blocker_count") or 0) != 0:
        blockers.append("nearline_blockers_present")
    if float(nearline_summary.get("treatment_fail_open_rate") or 0.0) != 0.0:
        blockers.append("nearline_treatment_fail_open")
    if float(nearline_summary.get("treatment_evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("nearline_no_treatment_citations")
    if float(nearline_summary.get("treatment_answerable_rate") or 0.0) < float(
        nearline_summary.get("current_rag_answerable_rate") or 0.0
    ):
        blockers.append("nearline_treatment_answerable_below_current_rag")
    if float(nearline_summary.get("treatment_token_proxy_delta_vs_current_rag") or 0.0) > 0.0:
        blockers.append("nearline_treatment_token_proxy_regression")
    missing_nearline_not_exercised = sorted(REQUIRED_NEARLINE_NOT_EXERCISED - set(nearline_ab.get("not_exercised") or []))
    for item in missing_nearline_not_exercised:
        blockers.append(f"nearline_missing_not_exercised:{item}")

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "field_promotion_review": field_promotion_review.get("schema"),
            "nearline_ab": nearline_ab.get("schema"),
        },
        "execution_mode": "preflight_only",
        "verdict": "BLOCKED_FOR_LIVE_RUNTIME_AB" if blockers else "READY_FOR_LIVE_RUNTIME_AB",
        "verdict_ceiling": "PREFLIGHT_ONLY",
        "quality_claim_allowed": False,
        "cohort_scope": "local_artifact_preflight",
        "auth_mode": "none",
        "runtime_entry": {
            "entrypoint": "not_exercised",
            "runtime_exercised": False,
            "runtime_trace_ids": [],
        },
        "provider_call_policy": {
            "provider_calls_allowed": False,
            "provider_call_count": 0,
            "models": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_recorded": False,
        },
        "source_bundle": {
            "field_promotion_schema": field_promotion_review.get("schema"),
            "nearline_schema": nearline_ab.get("schema"),
            "nearline_verdict_ceiling": nearline_ab.get("verdict_ceiling"),
            "runtime_supply_candidate_id": None,
            "bundle_version": None,
            "manifest_hash": None,
            "pack_hash": None,
        },
        "evidence_validation": {
            "citation_rate": float(nearline_summary.get("treatment_evidence_citation_rate") or 0.0),
            "fail_open_rate": float(nearline_summary.get("treatment_fail_open_rate") or 0.0),
            "question_lane_citation_rate": 0.0,
            "wrong_path_rate": None,
            "span_hash_validation_exercised": False,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_live_ab_preflight": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "blocker_count": len(blockers),
            "promoted_artifact_candidate_count": int(field_summary.get("promoted_artifact_candidate_count") or 0),
            "source_backed_field_count": int(field_summary.get("source_backed_field_count") or 0),
            "nearline_eval_case_count": int(nearline_summary.get("eval_case_count") or 0),
            "nearline_current_rag_answerable_rate": float(nearline_summary.get("current_rag_answerable_rate") or 0.0),
            "nearline_treatment_answerable_rate": float(nearline_summary.get("treatment_answerable_rate") or 0.0),
            "nearline_treatment_fail_open_rate": float(nearline_summary.get("treatment_fail_open_rate") or 0.0),
            "nearline_treatment_token_proxy_delta_vs_current_rag": float(
                nearline_summary.get("treatment_token_proxy_delta_vs_current_rag") or 0.0
            ),
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "planned_arms": PLANNED_ARMS,
        "planned_metrics": [
            "accuracy_or_answerable_rate",
            "token_usage",
            "latency_ms",
            "evidence_citation_rate",
            "fail_open_rate",
            "high_risk_or_abstention_rate",
        ],
        "blockers": blockers,
        "not_exercised_by_layer": {
            "review_not_exercised": [],
            "runtime_not_exercised": [
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
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--nearline-ab", type=Path, default=DEFAULT_NEARLINE_AB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_live_ab_preflight(
        field_promotion_review=_read_json(args.field_promotion_review),
        nearline_ab=_read_json(args.nearline_ab),
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "READY_FOR_LIVE_RUNTIME_AB" else 1


if __name__ == "__main__":
    raise SystemExit(main())
