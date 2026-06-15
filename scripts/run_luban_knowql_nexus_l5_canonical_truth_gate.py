#!/usr/bin/env python3
"""No-write L5 canonical learner-truth gate for KnowQL/Nexus/GBrain."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_L4_READINESS = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l4_authorization_readiness_20260615T143645Z"
    / "authorization_readiness.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l5_canonical_truth_gate_blocked"
    / "canonical_truth_gate.json"
)
SCHEMA = "knowql_nexus_l5_canonical_truth_gate.v1"
AUTHORIZATION_SCHEMA = "knowql_nexus_l5_canonical_truth_authorization.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _authorization_blockers(authorization_package: dict[str, Any] | None) -> list[str]:
    if not authorization_package:
        return ["signed_canonical_truth_authorization_missing"]
    blockers: list[str] = []
    if authorization_package.get("schema") != AUTHORIZATION_SCHEMA:
        blockers.append(f"canonical_truth_authorization_schema_mismatch:{authorization_package.get('schema')}")
    decision = _as_dict(authorization_package, "authorization_decision")
    if decision.get("signed_authorization") is not True:
        blockers.append("signed_canonical_truth_authorization_missing")
    if decision.get("canonical_truth_authorized") is not True:
        blockers.append("canonical_truth_authorization_missing")
    if decision.get("remote_write_authorized") is True:
        blockers.append("remote_write_scope_must_be_separate")
    return blockers


def _proof_blockers(canonical_truth_proof: dict[str, Any] | None) -> list[str]:
    if not canonical_truth_proof:
        return [
            "teacher_final_or_certified_policy_missing",
            "same_point_real_retest_proof_missing",
            "stable_learner_claim_missing",
        ]
    blockers: list[str] = []
    if canonical_truth_proof.get("teacher_final_or_certified_policy") is not True:
        blockers.append("teacher_final_or_certified_policy_missing")
    if canonical_truth_proof.get("same_point_real_retest_proof") is not True:
        blockers.append("same_point_real_retest_proof_missing")
    if canonical_truth_proof.get("stable_learner_claim") is not True:
        blockers.append("stable_learner_claim_missing")
    if canonical_truth_proof.get("claim_id_readback") is not True:
        blockers.append("claim_id_readback_missing")
    return blockers


def build_l5_canonical_truth_gate(
    *,
    l4_readiness: dict[str, Any],
    authorization_package: dict[str, Any] | None = None,
    canonical_truth_proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if l4_readiness.get("schema") != "knowql_nexus_l4_authorization_readiness.v1":
        blockers.append(f"l4_readiness_schema_mismatch:{l4_readiness.get('schema')}")
    if l4_readiness.get("live_readback_status") != "L4_LIVE_READBACK_READY":
        blockers.append("l4_live_readback_not_ready")
    if l4_readiness.get("safety_violations"):
        blockers.append("l4_safety_violations_present")
    if l4_readiness.get("production_authorization_status") != "L4_PRODUCTION_AUTHORIZATION_READY":
        blockers.append("l4_production_authorization_blocked")
    for blocker in list(l4_readiness.get("production_blockers") or []):
        if blocker in {"canonical_truth_authorization_missing", "real_student_cohort_authorization_missing"}:
            blockers.append(blocker)
    claim_ceiling = _as_dict(l4_readiness, "claim_ceiling")
    if claim_ceiling.get("canonical_truth_write_allowed") is not False:
        blockers.append("l4_claim_ceiling_already_allows_canonical_truth")
    summary = _as_dict(l4_readiness, "summary")
    for field in ("canonical_truth_write_count", "learner_memory_write_count", "production_write_count"):
        if _to_int(summary.get(field)) != 0:
            blockers.append(f"l4_{field}_nonzero")
    blockers.extend(_authorization_blockers(authorization_package))
    blockers.extend(_proof_blockers(canonical_truth_proof))
    verdict = "READY_FOR_FINAL_CANONICAL_TRUTH_SIGNOFF" if not blockers else "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "blockers": sorted(set(blockers)),
        "decisions": {
            "canonical_truth_write_allowed": False,
            "learner_memory_event_write_allowed": False,
            "read_model_write_allowed": False,
            "remote_write_allowed": False,
        },
        "safety": {
            "canonical_truth_write_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "not_exercised": [
            "canonical_truth_write",
            "learner_memory_event_write",
            "read_model_write",
            "remote_write",
        ],
        "stop_conditions": [
            "teacher_final_or_certified_policy_required",
            "same_point_real_retest_required",
            "stable_learner_claim_required",
            "claim_id_readback_required",
            "preview_or_simulated_evidence_attempted_promotion",
        ],
        "classification": {
            "authorization_package_only": True,
            "no_write": True,
            "canonical_truth_authorized": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l4-readiness", type=Path, default=DEFAULT_L4_READINESS)
    parser.add_argument("--authorization-package", type=Path, default=None)
    parser.add_argument("--canonical-truth-proof", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_l5_canonical_truth_gate(
        l4_readiness=_read_json(args.l4_readiness),
        authorization_package=_read_json(args.authorization_package) if args.authorization_package is not None else None,
        canonical_truth_proof=_read_json(args.canonical_truth_proof) if args.canonical_truth_proof is not None else None,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
