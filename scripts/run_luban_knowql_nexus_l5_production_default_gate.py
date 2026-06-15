#!/usr/bin/env python3
"""No-write L5 production-default gate for KnowQL/Nexus/GBrain."""
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
    / "artifacts/luban_grading_artifacts/knowql_nexus_l5_production_default_gate_blocked"
    / "production_default_gate.json"
)
SCHEMA = "knowql_nexus_l5_production_default_gate.v1"
AUTHORIZATION_SCHEMA = "knowql_nexus_l5_production_default_authorization.v1"


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


def _authorization_flags(authorization_package: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if not authorization_package:
        return False, ["signed_production_default_authorization_missing"]
    blockers: list[str] = []
    if authorization_package.get("schema") != AUTHORIZATION_SCHEMA:
        blockers.append(f"production_default_authorization_schema_mismatch:{authorization_package.get('schema')}")
    decision = _as_dict(authorization_package, "authorization_decision")
    if decision.get("signed_authorization") is not True:
        blockers.append("signed_production_default_authorization_missing")
    if decision.get("production_default_authorized") is not True:
        blockers.append("production_default_authorization_missing")
    if decision.get("rollback_kill_switch_verified") is not True:
        blockers.append("rollback_kill_switch_verification_missing")
    if decision.get("published_registry_authorized") is not True:
        blockers.append("published_registry_authorization_missing")
    return not blockers, blockers


def build_l5_production_default_gate(
    *,
    l4_readiness: dict[str, Any],
    authorization_package: dict[str, Any] | None = None,
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
        if blocker in {
            "stage5_human_gold_over_credit_blocker",
            "stage5_canary_not_ready",
            "production_default_authorization_missing",
            "published_registry_authorization_missing",
            "official_score_authorization_missing",
        }:
            blockers.append(blocker)
    claim_ceiling = _as_dict(l4_readiness, "claim_ceiling")
    if claim_ceiling.get("production_default_allowed") is not False:
        blockers.append("l4_claim_ceiling_already_allows_production_default")
    summary = _as_dict(l4_readiness, "summary")
    for field in ("production_write_count", "official_score_write_count", "canonical_truth_write_count"):
        if _to_int(summary.get(field)) != 0:
            blockers.append(f"l4_{field}_nonzero")
    authorized, authorization_blockers = _authorization_flags(authorization_package)
    blockers.extend(authorization_blockers)
    allowed = not blockers and authorized
    verdict = "READY_FOR_FINAL_PRODUCTION_DEFAULT_SIGNOFF" if allowed else "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "blockers": sorted(set(blockers)),
        "decisions": {
            "production_default_allowed": False,
            "env_mutation_allowed": False,
            "published_registry_write_allowed": False,
            "official_score_allowed": False,
            "remote_write_allowed": False,
        },
        "safety": {
            "production_write_count": 0,
            "official_score_write_count": 0,
            "canonical_truth_write_count": 0,
            "remote_write_count": 0,
        },
        "not_exercised": [
            "production_default_flip",
            "env_mutation",
            "published_registry_write",
            "remote_write",
        ],
        "stop_conditions": [
            "stage5_human_gold_over_credit_blocker_present",
            "non_cohort_leak_detected",
            "rollback_kill_switch_missing",
            "host_container_sha_mismatch",
            "official_score_write_before_release_truth",
        ],
        "classification": {
            "authorization_package_only": True,
            "no_write": True,
            "production_authorized": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l4-readiness", type=Path, default=DEFAULT_L4_READINESS)
    parser.add_argument("--authorization-package", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_l5_production_default_gate(
        l4_readiness=_read_json(args.l4_readiness),
        authorization_package=_read_json(args.authorization_package) if args.authorization_package is not None else None,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
