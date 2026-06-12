#!/usr/bin/env python3
"""Build a no-write release governance review packet for RichLeaf."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_COMPILER_STATUS_LEDGER = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_compiler_status_ledger_20260612/compiler_status_ledger_after_token_pack_gate.json"
)
DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_controlled_default_authorization_20260612/controlled_default_authorization_package.json"
)
DEFAULT_WRITEBACK_EXECUTION_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_test_learner_writeback_execution_gate_materialized_20260612/test_learner_writeback_execution_gate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_release_governance_review_20260612/release_governance_review_packet.json"
)
SCHEMA = "luban_rich_leaf_release_governance_review_packet.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safety_violations(name: str, payload: dict[str, Any]) -> list[str]:
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    violations: list[str] = []
    if int(safety.get("production_write_count") or 0) != 0:
        violations.append(f"{name}:production_write_count_nonzero")
    if int(safety.get("learner_memory_write_count") or 0) != 0:
        violations.append(f"{name}:learner_memory_write_count_nonzero")
    if safety.get("release_truth_claimed") is not False:
        violations.append(f"{name}:release_truth_claimed")
    if safety.get("installed_runtime_supply") is True:
        violations.append(f"{name}:installed_runtime_supply")
    if safety.get("canonical_truth_written") is True:
        violations.append(f"{name}:canonical_truth_written")
    if safety.get("official_score_allowed") is True:
        violations.append(f"{name}:official_score_allowed")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is True:
            violations.append(f"{name}:classification_{key}")
    return violations


def _release_blockers(
    *,
    compiler_status_ledger: dict[str, Any],
    controlled_default_authorization: dict[str, Any],
    writeback_execution_gate: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if compiler_status_ledger.get("schema") != "luban_rich_leaf_compiler_status_ledger.v1":
        blockers.append(f"compiler_status_schema_mismatch:{compiler_status_ledger.get('schema')}")
    if controlled_default_authorization.get("schema") != "luban_rich_leaf_controlled_default_authorization_package.v1":
        blockers.append(f"controlled_default_authorization_schema_mismatch:{controlled_default_authorization.get('schema')}")
    if writeback_execution_gate.get("schema") != "luban_rich_leaf_test_learner_writeback_execution_gate.v1":
        blockers.append(f"writeback_execution_gate_schema_mismatch:{writeback_execution_gate.get('schema')}")

    if compiler_status_ledger.get("overall_verdict") not in {
        "WEAK_GO_SHADOW_CANDIDATE",
        "PASS_SHADOW_CANDIDATE_READY_FOR_AUTHORIZED_NEXT_GATES",
    }:
        blockers.append(f"compiler_status_not_shadow_ready:{compiler_status_ledger.get('overall_verdict')}")
    compiler_summary = compiler_status_ledger.get("summary") if isinstance(compiler_status_ledger.get("summary"), dict) else {}
    if int(compiler_summary.get("missing_semantic_decision_count") or 0) != 0:
        blockers.append("semantic_decisions_incomplete")
    if int(compiler_summary.get("safety_violation_count") or 0) != 0:
        blockers.append("compiler_safety_violations_present")

    auth_decision = (
        controlled_default_authorization.get("authorization_decision")
        if isinstance(controlled_default_authorization.get("authorization_decision"), dict)
        else {}
    )
    if controlled_default_authorization.get("verdict") != "READY_FOR_OPERATOR_SIGNATURE":
        blockers.append(f"controlled_default_authorization_not_ready:{controlled_default_authorization.get('verdict')}")
    if auth_decision.get("operator_signature_recorded") is not True:
        blockers.append("operator_signature_missing")
    if auth_decision.get("controlled_default_authorized") is not True:
        blockers.append("controlled_default_authorization_missing")
    if auth_decision.get("release_truth_authorized") is not True:
        blockers.append("release_truth_authorization_missing")

    if writeback_execution_gate.get("verdict") == "BLOCKED_PENDING_SIGNED_AUTHORIZATION":
        blockers.append("learning_brain_signed_authorization_missing")
    write_summary = writeback_execution_gate.get("summary") if isinstance(writeback_execution_gate.get("summary"), dict) else {}
    if int(write_summary.get("learner_memory_write_count") or 0) != 0:
        blockers.append("unexpected_learner_memory_write_count")
    if int(write_summary.get("production_write_count") or 0) != 0:
        blockers.append("unexpected_production_write_count")
    return blockers


def run_release_governance_review_packet(
    *,
    compiler_status_ledger: dict[str, Any],
    controlled_default_authorization: dict[str, Any],
    writeback_execution_gate: dict[str, Any],
) -> dict[str, Any]:
    safety_violations = []
    safety_violations.extend(_safety_violations("compiler_status_ledger", compiler_status_ledger))
    safety_violations.extend(_safety_violations("controlled_default_authorization", controlled_default_authorization))
    safety_violations.extend(_safety_violations("writeback_execution_gate", writeback_execution_gate))
    release_blockers = _release_blockers(
        compiler_status_ledger=compiler_status_ledger,
        controlled_default_authorization=controlled_default_authorization,
        writeback_execution_gate=writeback_execution_gate,
    )
    if safety_violations:
        verdict = "NO_GO_SAFETY_INVARIANT"
    elif release_blockers:
        verdict = "BLOCKED_FOR_RELEASE_TRUTH"
    else:
        verdict = "READY_FOR_FINAL_GOVERNANCE_SIGNOFF"

    compiler_summary = compiler_status_ledger.get("summary") if isinstance(compiler_status_ledger.get("summary"), dict) else {}
    write_summary = writeback_execution_gate.get("summary") if isinstance(writeback_execution_gate.get("summary"), dict) else {}
    auth_summary = (
        controlled_default_authorization.get("summary")
        if isinstance(controlled_default_authorization.get("summary"), dict)
        else {}
    )
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "compiler_status_ledger": compiler_status_ledger.get("schema"),
            "controlled_default_authorization": controlled_default_authorization.get("schema"),
            "writeback_execution_gate": writeback_execution_gate.get("schema"),
        },
        "verdict": verdict,
        "quality_claim_allowed": False,
        "release_decision": {
            "release_truth_claim_allowed": False,
            "official_score_allowed": False,
            "production_default_allowed": False,
            "canonical_truth_write_allowed": False,
            "production_db_write_allowed": False,
            "requires_final_governance_signoff": True,
        },
        "summary": {
            "release_blocker_count": len(release_blockers),
            "safety_violation_count": len(safety_violations),
            "semantic_decision_count": int(compiler_summary.get("semantic_decision_count") or 0),
            "missing_semantic_decision_count": int(compiler_summary.get("missing_semantic_decision_count") or 0),
            "provider_call_count": int(compiler_summary.get("provider_call_count") or 0),
            "runtime_token_pack_unit_count": int(compiler_summary.get("runtime_token_pack_unit_count") or 0),
            "planned_learning_event_count": int(compiler_summary.get("planned_learning_event_count") or 0),
            "writeback_executed": bool(write_summary.get("writeback_executed")),
            "controlled_default_write_executed": bool(auth_summary.get("write_executed")),
            "learner_memory_write_count": int(write_summary.get("learner_memory_write_count") or 0),
            "production_write_count": int(write_summary.get("production_write_count") or 0)
            + int(auth_summary.get("production_write_count") or 0),
        },
        "release_blockers": release_blockers,
        "safety_violations": safety_violations,
        "not_exercised": [
            "final_governance_signoff",
            "release_truth_claim",
            "official_score",
            "canonical_truth_write",
            "production_db_write",
            "runtime_default_install",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "release_governance_review_packet": True,
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
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-status-ledger", type=Path, default=DEFAULT_COMPILER_STATUS_LEDGER)
    parser.add_argument("--controlled-default-authorization", type=Path, default=DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION)
    parser.add_argument("--writeback-execution-gate", type=Path, default=DEFAULT_WRITEBACK_EXECUTION_GATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_release_governance_review_packet(
        compiler_status_ledger=_read_json(args.compiler_status_ledger),
        controlled_default_authorization=_read_json(args.controlled_default_authorization),
        writeback_execution_gate=_read_json(args.writeback_execution_gate),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "NO_GO_SAFETY_INVARIANT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
