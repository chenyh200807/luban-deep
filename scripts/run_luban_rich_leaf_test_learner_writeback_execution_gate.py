#!/usr/bin/env python3
"""Fail-closed execution gate before any real test-learner writeback.

This gate intentionally blocks while signed authorization, concrete test
learner binding, and approved rollback evidence are missing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_dry_run_manifest_20260612/test_learner_writeback_dry_run_manifest.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_execution_gate_20260612/test_learner_writeback_execution_gate.json"
)
SCHEMA = "luban_rich_leaf_test_learner_writeback_execution_gate.v1"
DRY_RUN_SCHEMA = "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1"
UNBOUND_TARGET_USER = "not_bound_without_authorization"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dry_run_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != DRY_RUN_SCHEMA:
        blockers.append(f"dry_run_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION":
        blockers.append(f"dry_run_not_ready:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("dry_run_quality_claim_allowed")
    if payload.get("execution_mode") != "dry_run_manifest_only":
        blockers.append(f"dry_run_bad_execution_mode:{payload.get('execution_mode')}")
    target = payload.get("target_scope") if isinstance(payload.get("target_scope"), dict) else {}
    if target.get("target_user_id") != UNBOUND_TARGET_USER:
        blockers.append("dry_run_target_user_bound")
    if target.get("target_memory_kind") != "learning_evidence":
        blockers.append("dry_run_bad_memory_kind")
    batch = payload.get("write_batch_candidate") if isinstance(payload.get("write_batch_candidate"), dict) else {}
    if batch.get("write_allowed") is not False:
        blockers.append("dry_run_write_allowed")
    if int(batch.get("event_count") or 0) <= 0:
        blockers.append("dry_run_no_events")
    rollback = payload.get("rollback_selector") if isinstance(payload.get("rollback_selector"), dict) else {}
    if rollback.get("rollback_allowed") is not False:
        blockers.append("dry_run_rollback_allowed")
    if rollback.get("target_user_id") != UNBOUND_TARGET_USER:
        blockers.append("dry_run_rollback_bound_user")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"dry_run_blockers_present:{summary.get('blocker_count')}")
    if summary.get("writeback_executed") is not False:
        blockers.append("dry_run_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"dry_run_{key}")
    return blockers


def run_test_learner_writeback_execution_gate(*, test_learner_writeback_dry_run_manifest: dict[str, Any]) -> dict[str, Any]:
    blockers = _dry_run_blockers(test_learner_writeback_dry_run_manifest)
    summary = (
        test_learner_writeback_dry_run_manifest.get("summary")
        if isinstance(test_learner_writeback_dry_run_manifest.get("summary"), dict)
        else {}
    )
    blocking_reasons = [
        "signed_user_authorization_missing",
        "target_user_unbound",
        "rollback_plan_not_approved",
    ]
    verdict = "FAIL" if blockers else "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "test_learner_writeback_dry_run_manifest": test_learner_writeback_dry_run_manifest.get("schema"),
        },
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "execution_gate_only",
        "execution_decision": {
            "writeback_allowed": False,
            "writeback_executed": False,
            "target_user_id_bound": False,
            "signed_authorization_recorded": False,
            "rollback_plan_approved": False,
        },
        "blocking_reasons": blocking_reasons,
        "summary": {
            "blocker_count": len(blockers),
            "dry_run_planned_event_count": int(summary.get("planned_event_count") or 0),
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "blockers": blockers,
        "not_exercised_by_layer": {
            "memory_not_exercised": [
                "learner_state_service_append_memory_event",
                "learner_memory_db_write",
                "learner_memory_outbox_enqueue",
                "canonical_learner_truth_write",
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
            "test_learner_writeback_execution_gate": True,
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
    parser.add_argument("--test-learner-writeback-dry-run-manifest", type=Path, default=DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_test_learner_writeback_execution_gate(
        test_learner_writeback_dry_run_manifest=_read_json(args.test_learner_writeback_dry_run_manifest)
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
