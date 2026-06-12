#!/usr/bin/env python3
"""Build a no-write controlled-default authorization package for RichLeaf."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DEFAULT_GATE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_default_gate_20260612/runtime_default_gate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_controlled_default_authorization_20260612/controlled_default_authorization_package.json"
)
SCHEMA = "luban_rich_leaf_controlled_default_authorization_package.v1"
RUNTIME_DEFAULT_GATE_SCHEMA = "luban_rich_leaf_runtime_default_gate.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gate_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != RUNTIME_DEFAULT_GATE_SCHEMA:
        blockers.append(f"runtime_default_gate_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_CONTROLLED_DEFAULT_REVIEW":
        blockers.append(f"runtime_default_gate_not_ready:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("runtime_default_gate_quality_claim_allowed")
    decision = payload.get("runtime_default_decision") if isinstance(payload.get("runtime_default_decision"), dict) else {}
    if decision.get("default_install_allowed") is not False:
        blockers.append("runtime_default_gate_default_install_allowed")
    if decision.get("canonical_pointer_write_allowed") is not False:
        blockers.append("runtime_default_gate_canonical_pointer_write_allowed")
    for key in ("requires_signed_operator_decision", "requires_rollback_plan", "requires_shadow_observability"):
        if decision.get(key) is not True:
            blockers.append(f"runtime_default_gate_missing_{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"runtime_default_gate_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("token_pack_unit_count") or 0) <= 0:
        blockers.append("runtime_default_gate_no_token_pack_units")
    if int(summary.get("streaming_provider_call_count") or 0) <= 0:
        blockers.append("runtime_default_gate_no_streaming_evidence")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "canonical_pointer_written", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"runtime_default_gate_classification_{key}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append("runtime_default_gate_production_write_count")
    if safety.get("installed_runtime_supply") is not False:
        blockers.append("runtime_default_gate_installed_runtime_supply")
    if safety.get("release_truth_claimed") is not False:
        blockers.append("runtime_default_gate_release_truth_claimed")
    return blockers


def run_controlled_default_authorization_package(*, runtime_default_gate: dict[str, Any]) -> dict[str, Any]:
    blockers = _gate_blockers(runtime_default_gate)
    summary = runtime_default_gate.get("summary") if isinstance(runtime_default_gate.get("summary"), dict) else {}
    return {
        "schema": SCHEMA,
        "input_schemas": {"runtime_default_gate": runtime_default_gate.get("schema")},
        "verdict": "BLOCKED" if blockers else "READY_FOR_OPERATOR_SIGNATURE",
        "quality_claim_allowed": False,
        "execution_mode": "authorization_package_only",
        "authorization_decision": {
            "explicit_user_authorization_required": True,
            "operator_signature_recorded": False,
            "controlled_default_authorized": False,
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "remote_write_allowed": False,
            "release_truth_authorized": False,
        },
        "candidate_scope": {
            "runtime_token_pack_unit_count": int(summary.get("token_pack_unit_count") or 0),
            "supply_unit_count": int(summary.get("supply_unit_count") or 0),
            "streaming_sample_count": int(summary.get("streaming_sample_count") or 0),
            "streaming_provider_call_count": int(summary.get("streaming_provider_call_count") or 0),
            "streaming_ttft_delta_ms": float(summary.get("streaming_ttft_delta_ms") or 0.0),
            "semantic_live_ab_verdict": summary.get("semantic_live_ab_verdict"),
        },
        "rollback_plan": {
            "plan_status": "draft_review_required",
            "pre_flip_pointer_snapshot_required": True,
            "kill_switch_required": True,
            "rollback_to_previous_runtime_supply_required": True,
            "post_flip_shadow_monitor_required": True,
        },
        "observability_plan": {
            "plan_status": "draft_review_required",
            "required_metrics": [
                "answerable_rate",
                "fail_open_rate",
                "evidence_citation_rate",
                "ttft_ms",
                "full_latency_ms",
                "provider_error_rate",
            ],
            "required_stop_conditions": [
                "fail_open_rate_regression",
                "provider_error_spike",
                "evidence_citation_drop",
                "latency_p95_regression",
            ],
        },
        "blocked_actions": [
            "canonical_pointer_write",
            "runtime_default_install",
            "production_db_write",
            "remote_write",
            "release_truth_claim",
        ],
        "summary": {
            "blocker_count": len(blockers),
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "blockers": blockers,
        "missing_authorizations": [
            "signed_operator_authorization_record",
            "approved_rollback_plan",
            "approved_observability_plan",
            "controlled_default_scope",
            "separate_release_truth_governance",
        ],
        "not_exercised": [
            "canonical_pointer_write",
            "runtime_default_install",
            "production_db_write",
            "remote_write",
            "release_truth_governance",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "controlled_default_authorization_package": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "remote_write_count": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-default-gate", type=Path, default=DEFAULT_RUNTIME_DEFAULT_GATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_controlled_default_authorization_package(runtime_default_gate=_read_json(args.runtime_default_gate))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "READY_FOR_OPERATOR_SIGNATURE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
