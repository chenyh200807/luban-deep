#!/usr/bin/env python3
"""No-write L5 consented real-student pilot gate for KnowQL/Nexus/GBrain.

This gate separates the next valid step after QA/operator Stage5 GO from broad
production default or canonical learner-truth authorization. It can authorize a
named, consented, randomized pilot only when real-student cohort evidence and a
signed pilot authorization package are present. It never flips runtime defaults,
writes official scores, publishes registry entries, writes learner truth, or
touches remote infrastructure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_L4_READINESS = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z"
    / "authorization_readiness.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l5_consented_pilot_gate_blocked"
    / "l5_consented_pilot_gate.json"
)
SCHEMA = "knowql_nexus_l5_consented_pilot_gate.v1"
REAL_STUDENT_EVIDENCE_SCHEMA = "knowql_nexus_real_student_cohort_evidence.v1"
AUTHORIZATION_SCHEMA = "knowql_nexus_l5_consented_pilot_authorization.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_dict(payload: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _l4_blockers(l4_readiness: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if l4_readiness.get("schema") != "knowql_nexus_l4_authorization_readiness.v1":
        blockers.append(f"l4_readiness_schema_mismatch:{l4_readiness.get('schema')}")
    if l4_readiness.get("live_readback_status") != "L4_LIVE_READBACK_READY":
        blockers.append("l4_live_readback_not_ready")
    if l4_readiness.get("safety_violations"):
        blockers.append("l4_safety_violations_present")
    for blocker in list(l4_readiness.get("production_blockers") or []):
        if blocker in {"stage5_human_gold_over_credit_blocker", "stage5_canary_not_ready"}:
            blockers.append(blocker)
    claim_ceiling = _as_dict(l4_readiness, "claim_ceiling")
    for field in (
        "real_student_efficacy_claim_allowed",
        "production_default_allowed",
        "official_score_allowed",
        "published_registry_allowed",
        "canonical_truth_write_allowed",
    ):
        if claim_ceiling.get(field) is True:
            blockers.append(f"l4_claim_ceiling_scope_leak:{field}")
    summary = _as_dict(l4_readiness, "summary")
    for field in ("production_write_count", "official_score_write_count", "canonical_truth_write_count"):
        if _to_int(summary.get(field)) != 0:
            blockers.append(f"l4_{field}_nonzero")
    return blockers


def _real_student_evidence_blockers(
    real_student_cohort_evidence: dict[str, Any] | None,
    *,
    min_subjects_per_arm: int,
) -> list[str]:
    evidence = real_student_cohort_evidence or {}
    blockers: list[str] = []
    if not evidence:
        return [
            "real_student_cohort_evidence_missing",
            "privacy_consent_boundary_missing",
            "sample_size_plan_missing",
        ]
    if evidence.get("schema") != REAL_STUDENT_EVIDENCE_SCHEMA:
        blockers.append(f"real_student_cohort_evidence_schema_mismatch:{evidence.get('schema')}")
    if not str(evidence.get("cohort_source") or "").strip():
        blockers.append("cohort_source_missing")
    if not str(evidence.get("privacy_consent_boundary") or "").strip():
        blockers.append("privacy_consent_boundary_missing")
    sample_size_plan = _as_dict(evidence, "sample_size_plan")
    if _to_int(sample_size_plan.get("min_subjects_per_arm")) < min_subjects_per_arm:
        blockers.append("sample_size_plan_missing")
    arms = sample_size_plan.get("arms")
    if isinstance(arms, list) and set(str(arm) for arm in arms) != {"A0", "B1", "B2"}:
        blockers.append("sample_arms_must_be_a0_b1_b2")
    randomization_unit = str(sample_size_plan.get("randomization_unit") or "").strip()
    if randomization_unit and randomization_unit != "learner":
        blockers.append("randomization_unit_must_be_learner")
    return blockers


def _authorization_blockers(authorization_package: dict[str, Any] | None) -> list[str]:
    package = authorization_package or {}
    if not package:
        return ["signed_consented_pilot_authorization_missing"]
    blockers: list[str] = []
    if package.get("schema") != AUTHORIZATION_SCHEMA:
        blockers.append(f"consented_pilot_authorization_schema_mismatch:{package.get('schema')}")
    decision = _as_dict(package, "authorization_decision")
    required_true = (
        "signed_authorization",
        "real_student_cohort_authorized",
        "privacy_consent_authorized",
        "sample_size_plan_authorized",
        "qa_operator_to_real_student_transition_authorized",
    )
    for field in required_true:
        if decision.get(field) is not True:
            blockers.append(
                "signed_consented_pilot_authorization_missing"
                if field == "signed_authorization"
                else f"{field}_missing"
            )
    forbidden_true = (
        "production_default_authorized",
        "official_score_authorized",
        "published_registry_authorized",
        "canonical_truth_authorized",
        "remote_write_authorized",
    )
    for field in forbidden_true:
        if decision.get(field) is True:
            blockers.append(f"pilot_scope_leak:{field}")
    return blockers


def build_l5_consented_pilot_gate(
    *,
    l4_readiness: dict[str, Any],
    real_student_cohort_evidence: dict[str, Any] | None = None,
    authorization_package: dict[str, Any] | None = None,
    min_subjects_per_arm: int = 30,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_l4_blockers(l4_readiness))
    blockers.extend(
        _real_student_evidence_blockers(
            real_student_cohort_evidence,
            min_subjects_per_arm=min_subjects_per_arm,
        )
    )
    blockers.extend(_authorization_blockers(authorization_package))
    blockers = sorted(set(blockers))
    allowed = not blockers
    return {
        "schema": SCHEMA,
        "verdict": "READY_FOR_CONSENTED_PILOT_EXECUTION"
        if allowed
        else "BLOCKED_PENDING_CONSENTED_PILOT_AUTHORIZATION",
        "blockers": blockers,
        "decisions": {
            "consented_pilot_ab_allowed": allowed,
            "real_student_efficacy_claim_allowed": False,
            "production_default_allowed": False,
            "official_score_allowed": False,
            "published_registry_write_allowed": False,
            "canonical_truth_write_allowed": False,
            "remote_write_allowed": False,
        },
        "pilot_scope": {
            "allowed_arms": ["A0", "B1", "B2"],
            "min_subjects_per_arm": min_subjects_per_arm,
            "randomization_unit": "learner",
            "authorized_surface": "consented_real_student_pilot_only" if allowed else "none",
            "qa_operator_evidence_can_seed_design": True,
            "qa_operator_evidence_can_claim_real_student_efficacy": False,
        },
        "safety": {
            "production_write_count": 0,
            "official_score_write_count": 0,
            "canonical_truth_write_count": 0,
            "learner_memory_write_count": 0,
            "remote_write_count": 0,
        },
        "not_exercised": [
            "production_default_flip",
            "official_score_write",
            "published_registry_write",
            "canonical_truth_write",
            "remote_write",
        ],
        "stop_conditions": [
            "missing_or_withdrawn_consent",
            "sample_size_plan_below_minimum",
            "non_randomized_assignment",
            "production_default_or_official_score_scope_leak",
            "canonical_truth_write_before_same_point_real_retest_authorization",
        ],
        "classification": {
            "authorization_package_only": True,
            "no_write": True,
            "production_authorized": False,
            "canonical_truth_authorized": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l4-readiness", type=Path, default=DEFAULT_L4_READINESS)
    parser.add_argument("--real-student-cohort-evidence", type=Path, default=None)
    parser.add_argument("--authorization-package", type=Path, default=None)
    parser.add_argument("--min-subjects-per-arm", type=int, default=30)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_l5_consented_pilot_gate(
        l4_readiness=_read_json(args.l4_readiness),
        real_student_cohort_evidence=_read_json(args.real_student_cohort_evidence)
        if args.real_student_cohort_evidence is not None
        else None,
        authorization_package=_read_json(args.authorization_package) if args.authorization_package is not None else None,
        min_subjects_per_arm=args.min_subjects_per_arm,
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"out": str(args.output), "verdict": report["verdict"], "blockers": report["blockers"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
