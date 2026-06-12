#!/usr/bin/env python3
"""Build an artifact-only dry-run manifest for future test-learner writeback.

This manifest prepares idempotency keys, rollback selectors, and event write
candidates without binding a real learner id or writing learner memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION_PACKAGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_authorization_package_20260612/test_learner_writeback_authorization_package.json"
)
DEFAULT_SANDBOX_EVENTS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/sandbox_memory_events.jsonl"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_dry_run_manifest_20260612/test_learner_writeback_dry_run_manifest.json"
)
SCHEMA = "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1"
SANDBOX_SCHEMA = "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
AUTHORIZATION_PACKAGE_SCHEMA = "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
UNBOUND_TARGET_USER = "not_bound_without_authorization"
TARGET_SOURCE_FEATURE = "rich_leaf_authorized_test_writeback"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _sandbox_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != SANDBOX_SCHEMA:
        blockers.append(f"sandbox_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"sandbox_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("sandbox_quality_claim_allowed")
    if payload.get("execution_mode") != "artifact_only_sandbox_readback":
        blockers.append(f"sandbox_bad_execution_mode:{payload.get('execution_mode')}")
    sandbox = payload.get("sandbox") if isinstance(payload.get("sandbox"), dict) else {}
    if sandbox.get("write_scope") != "artifact_only":
        blockers.append("sandbox_not_artifact_only")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"sandbox_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("sandbox_readback_event_count") or 0) <= 0:
        blockers.append("sandbox_no_readback")
    for key in ("learner_memory_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"sandbox_{key}")
    return blockers


def _authorization_package_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != AUTHORIZATION_PACKAGE_SCHEMA:
        blockers.append(f"authorization_package_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_USER_AUTHORIZATION_DECISION":
        blockers.append(f"authorization_package_not_ready:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("authorization_package_quality_claim_allowed")
    if payload.get("execution_mode") != "authorization_package_only":
        blockers.append(f"authorization_package_bad_execution_mode:{payload.get('execution_mode')}")
    decision = payload.get("authorization_decision") if isinstance(payload.get("authorization_decision"), dict) else {}
    if decision.get("user_authorization_recorded") is not False:
        blockers.append("authorization_package_user_authorization_recorded")
    if decision.get("test_learner_writeback_authorized") is not False:
        blockers.append("authorization_package_writeback_authorized")
    if decision.get("allowed_write_scope") != "none_without_signed_authorization":
        blockers.append("authorization_package_bad_allowed_scope")
    if decision.get("canonical_truth_authorized") is not False:
        blockers.append("authorization_package_canonical_truth_authorized")
    if decision.get("production_db_authorized") is not False:
        blockers.append("authorization_package_production_db_authorized")
    rollback = payload.get("rollback_plan") if isinstance(payload.get("rollback_plan"), dict) else {}
    if rollback.get("plan_status") != "draft_review_required":
        blockers.append("authorization_package_bad_rollback_status")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"authorization_package_blockers_present:{summary.get('blocker_count')}")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"authorization_package_{key}")
    return blockers


def _row_blockers(row: dict[str, Any]) -> list[str]:
    event_id = str(row.get("event_id") or "unknown")
    blockers: list[str] = []
    if row.get("memory_kind") != "learning_evidence":
        blockers.append(f"sandbox_row_bad_memory_kind:{event_id}")
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    if payload.get("event_type") != "learning_evidence" or payload.get("memory_kind") != "learning_evidence":
        blockers.append(f"sandbox_row_bad_event_semantics:{event_id}")
    if payload.get("candidate_only") is not True or payload.get("preview_only") is not True:
        blockers.append(f"sandbox_row_not_candidate_preview:{event_id}")
    if payload.get("claim_promotion_allowed") is not False:
        blockers.append(f"sandbox_row_claim_promotion_allowed:{event_id}")
    if payload.get("canonical_truth_written") is not False:
        blockers.append(f"sandbox_row_canonical_truth_written:{event_id}")
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    for key in ("writeback_eligible", "progress_countable", "truth_eligible", "stable_truth_eligible"):
        if quality.get(key) is not False:
            blockers.append(f"sandbox_row_quality_{key}:{event_id}")
    return blockers


def _event_write_candidate(row: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    source_event_id = str(row.get("event_id") or _stable_id("source_event", row))
    payload_json = dict(row.get("payload_json") or {})
    target_payload = {
        "target_user_id": UNBOUND_TARGET_USER,
        "source_feature": TARGET_SOURCE_FEATURE,
        "source_event_id": source_event_id,
        "payload_json": payload_json,
        "batch_id": batch_id,
    }
    return {
        "planned_event_id": _stable_id("rich_leaf_writeback_dry_run_event", target_payload),
        "source_event_id": source_event_id,
        "target_user_id": UNBOUND_TARGET_USER,
        "source_feature": TARGET_SOURCE_FEATURE,
        "source_id": str(row.get("source_id") or source_event_id),
        "memory_kind": "learning_evidence",
        "idempotency_key": _stable_id("rich_leaf_writeback_dry_run_idempotency", target_payload),
        "write_allowed": False,
        "payload_json": payload_json,
    }


def run_test_learner_writeback_dry_run_manifest(
    *,
    test_learner_sandbox_readback_gate: dict[str, Any],
    test_learner_writeback_authorization_package: dict[str, Any],
    sandbox_events: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_sandbox_blockers(test_learner_sandbox_readback_gate))
    blockers.extend(_authorization_package_blockers(test_learner_writeback_authorization_package))
    sandbox_summary = (
        test_learner_sandbox_readback_gate.get("summary")
        if isinstance(test_learner_sandbox_readback_gate.get("summary"), dict)
        else {}
    )
    package_scope = (
        test_learner_writeback_authorization_package.get("candidate_scope")
        if isinstance(test_learner_writeback_authorization_package.get("candidate_scope"), dict)
        else {}
    )
    expected_count = int(sandbox_summary.get("sandbox_readback_event_count") or 0)
    if int(package_scope.get("max_candidate_event_count") or 0) != expected_count:
        blockers.append("authorization_package_candidate_count_drift")

    rows: list[dict[str, Any]] = []
    if sandbox_events.exists():
        rows = _read_jsonl(sandbox_events)
    else:
        blockers.append(f"sandbox_events_missing:{sandbox_events}")
    if len(rows) != expected_count:
        blockers.append("sandbox_events_count_drift")
    for row in rows:
        blockers.extend(_row_blockers(row))

    batch_id = _stable_id(
        "rich_leaf_writeback_dry_run_batch",
        {"rows": [row.get("event_id") for row in rows], "target_source_feature": TARGET_SOURCE_FEATURE},
    )
    event_candidates = [] if blockers else [_event_write_candidate(row, batch_id=batch_id) for row in rows]
    idempotency_keys = {candidate["idempotency_key"] for candidate in event_candidates}
    if len(idempotency_keys) != len(event_candidates):
        blockers.append("duplicate_idempotency_keys")

    target_scope = {
        "target_user_id": UNBOUND_TARGET_USER,
        "target_memory_kind": "learning_evidence",
        "target_source_feature": TARGET_SOURCE_FEATURE,
        "target_user_scope": "test_learner_only_after_explicit_authorization",
    }
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "test_learner_sandbox_readback_gate": test_learner_sandbox_readback_gate.get("schema"),
            "test_learner_writeback_authorization_package": test_learner_writeback_authorization_package.get("schema"),
        },
        "verdict": "FAIL" if blockers else "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_manifest_only",
        "target_scope": target_scope,
        "write_batch_candidate": {
            "batch_id": batch_id,
            "event_count": len(event_candidates),
            "idempotency_key_count": len(idempotency_keys),
            "write_allowed": False,
        },
        "rollback_selector": {
            "target_user_id": UNBOUND_TARGET_USER,
            "source_feature": TARGET_SOURCE_FEATURE,
            "batch_id": batch_id,
            "rollback_allowed": False,
        },
        "event_write_candidates": event_candidates,
        "summary": {
            "blocker_count": len(blockers),
            "candidate_event_count": expected_count,
            "planned_event_count": len(event_candidates),
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
            "test_learner_writeback_dry_run_manifest": True,
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
    parser.add_argument("--test-learner-sandbox-readback-gate", type=Path, default=DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE)
    parser.add_argument(
        "--test-learner-writeback-authorization-package",
        type=Path,
        default=DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION_PACKAGE,
    )
    parser.add_argument("--sandbox-events", type=Path, default=DEFAULT_SANDBOX_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_test_learner_writeback_dry_run_manifest(
        test_learner_sandbox_readback_gate=_read_json(args.test_learner_sandbox_readback_gate),
        test_learner_writeback_authorization_package=_read_json(args.test_learner_writeback_authorization_package),
        sandbox_events=args.sandbox_events,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
