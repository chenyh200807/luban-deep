#!/usr/bin/env python3
"""Build a review-only authorization package for test-learner writeback.

The package is not authorization and is not a writer. It only makes the
required scope, rollback evidence, and forbidden actions explicit before any
future test learner memory write can be considered.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORIZED_WRITEBACK_PREFLIGHT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_authorized_writeback_preflight_20260612/authorized_writeback_preflight.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_authorization_package_20260612/test_learner_writeback_authorization_package.json"
)
SCHEMA = "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
PREFLIGHT_SCHEMA = "luban_rich_leaf_authorized_writeback_preflight.v1"


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
    if payload.get("schema") != PREFLIGHT_SCHEMA:
        blockers.append(f"preflight_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_AUTHORIZATION_REVIEW":
        blockers.append(f"preflight_not_ready:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("preflight_quality_claim_allowed")
    if payload.get("execution_mode") != "authorization_preflight_only":
        blockers.append(f"preflight_bad_execution_mode:{payload.get('execution_mode')}")

    auth = payload.get("authorization") if isinstance(payload.get("authorization"), dict) else {}
    if auth.get("explicit_user_authorization_required") is not True:
        blockers.append("preflight_missing_explicit_authorization_requirement")
    if auth.get("test_learner_writeback_authorized") is not False:
        blockers.append("preflight_writeback_authorized")
    if auth.get("allowed_write_scope") != "none_without_authorization":
        blockers.append("preflight_bad_allowed_scope")
    if auth.get("canonical_truth_authorized") is not False:
        blockers.append("preflight_canonical_truth_authorized")
    if auth.get("production_db_authorized") is not False:
        blockers.append("preflight_production_db_authorized")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"preflight_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("preflight_no_candidate_events")
    if summary.get("writeback_executed") is not False:
        blockers.append("preflight_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"preflight_{key}")

    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("test_learner_writeback_allowed") is not False:
        blockers.append("preflight_writeback_allowed")
    if classification.get("learner_memory_write_allowed") is not False:
        blockers.append("preflight_learner_memory_write_allowed")
    return blockers


def run_test_learner_writeback_authorization_package(*, authorized_writeback_preflight: dict[str, Any]) -> dict[str, Any]:
    blockers = _preflight_blockers(authorized_writeback_preflight)
    summary = (
        authorized_writeback_preflight.get("summary")
        if isinstance(authorized_writeback_preflight.get("summary"), dict)
        else {}
    )
    plan = (
        authorized_writeback_preflight.get("writeback_plan_candidate")
        if isinstance(authorized_writeback_preflight.get("writeback_plan_candidate"), dict)
        else {}
    )
    return {
        "schema": SCHEMA,
        "input_schemas": {"authorized_writeback_preflight": authorized_writeback_preflight.get("schema")},
        "verdict": "FAIL" if blockers else "READY_FOR_USER_AUTHORIZATION_DECISION",
        "quality_claim_allowed": False,
        "execution_mode": "authorization_package_only",
        "authorization_decision": {
            "explicit_user_authorization_required": True,
            "user_authorization_recorded": False,
            "test_learner_writeback_authorized": False,
            "allowed_write_scope": "none_without_signed_authorization",
            "canonical_truth_authorized": False,
            "production_db_authorized": False,
        },
        "candidate_scope": {
            "target_memory_kind": plan.get("target_memory_kind") or "learning_evidence",
            "target_source_feature": plan.get("target_source_feature") or "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
            "max_candidate_event_count": int(plan.get("max_candidate_event_count") or summary.get("candidate_event_count") or 0),
            "top_claim_candidate_count": int(summary.get("top_claim_candidate_count") or 0),
            "next_action_candidate_count": int(summary.get("next_action_candidate_count") or 0),
        },
        "rollback_plan": {
            "plan_status": "draft_review_required",
            "pre_write_snapshot_required": True,
            "delete_by_source_feature_required": True,
            "rollback_artifacts": [
                "pre_write_learner_memory_snapshot",
                "write_batch_manifest",
                "post_write_readback_report",
            ],
        },
        "operator_checklist": [
            "confirm_explicit_user_authorization_text",
            "bind_concrete_test_learner_id",
            "capture_pre_write_learner_memory_snapshot",
            "write_only_learning_evidence_with_source_feature",
            "verify_post_write_readback_then_keep_canonical_truth_false",
        ],
        "blocked_actions": [
            "production_db_write",
            "canonical_learner_truth_write",
            "personalization_context_pack_readback_claim",
            "training_intent_write",
            "next_best_action_write",
            "runtime_default_install",
        ],
        "summary": {
            "blocker_count": len(blockers),
            "candidate_event_count": int(summary.get("candidate_event_count") or 0),
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "missing_authorizations": [
            "signed_user_authorization_record",
            "concrete_test_learner_id",
            "teacher_final_or_governance_review",
            "approved_rollback_plan",
            "separate_canonical_truth_authorization",
        ],
        "blockers": blockers,
        "not_exercised_by_layer": {
            "memory_not_exercised": [
                "learner_state_service_append_memory_event",
                "learner_memory_db_write",
                "learner_memory_outbox_enqueue",
            ],
            "learning_brain_not_exercised": [
                "production_learning_synthesis",
                "personalization_context_pack_readback",
                "training_intent_creation",
                "next_best_action_generation",
            ],
            "release_not_exercised": ["canonical_truth_write", "production_default_decision"],
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_writeback_authorization_package": True,
            "test_learner_writeback_allowed": False,
            "learner_memory_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-writeback-preflight", type=Path, default=DEFAULT_AUTHORIZED_WRITEBACK_PREFLIGHT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_test_learner_writeback_authorization_package(
        authorized_writeback_preflight=_read_json(args.authorized_writeback_preflight)
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "READY_FOR_USER_AUTHORIZATION_DECISION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
