#!/usr/bin/env python3
"""Build a no-write L4 authorization readiness report for KnowQL/Nexus/GBrain."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
RUN_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

DEFAULT_L1_SUMMARY = ARTIFACT_ROOT / "pgo_l1_live_shadow_ab_20260615T095041Z" / "summary.json"
DEFAULT_L2_SUMMARY = ARTIFACT_ROOT / "knowql_nexus_l2_learning_ab_20260615T125634Z" / "summary.json"
DEFAULT_L3_SUMMARY = ARTIFACT_ROOT / "knowql_nexus_l3_cohort_ab_20260615T140840Z" / "summary.json"
DEFAULT_OUT_DIR = ARTIFACT_ROOT / f"knowql_nexus_l4_authorization_readiness_{RUN_STAMP}"
DEFAULT_OUTPUT = DEFAULT_OUT_DIR / "authorization_readiness.json"
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUT_DIR / "authorization_readiness.md"
DEFAULT_SUMMARY_OUTPUT = DEFAULT_OUT_DIR / "summary.json"
DEFAULT_NEGATIVE_EVIDENCE_OUTPUT = DEFAULT_OUT_DIR / "negative_evidence.jsonl"

SCHEMA = "knowql_nexus_l4_authorization_readiness.v1"
REAL_STUDENT_EVIDENCE_SCHEMA = "knowql_nexus_real_student_cohort_evidence.v1"
AUTHORIZATION_PACKAGE_SCHEMA = "knowql_nexus_l4_production_authorization_package.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _as_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safety_violations(name: str, payload: dict[str, Any]) -> list[str]:
    safety = _as_dict(payload, "safety")
    decision = _as_dict(payload, "decision")
    violations: list[str] = []
    for field in (
        "canonical_truth_write_count",
        "official_score_write_count",
        "unsafe_write_signal_count",
        "production_write_count",
    ):
        if _to_int(safety.get(field)) != 0:
            violations.append(f"{name}:{field}_nonzero")
    if decision.get("canonical_truth_written") is not False:
        violations.append(f"{name}:canonical_truth_written_not_false")
    if decision.get("official_score_written") is not False:
        violations.append(f"{name}:official_score_written_not_false")
    return violations


def _write_counts(*summaries: dict[str, Any]) -> dict[str, int]:
    counts = {
        "canonical_truth_write_count": 0,
        "official_score_write_count": 0,
        "unsafe_write_signal_count": 0,
        "production_write_count": 0,
    }
    for summary in summaries:
        safety = _as_dict(summary, "safety")
        for field in counts:
            counts[field] += _to_int(safety.get(field))
    return counts


def _gate(name: str, passed: bool, reasons: list[str], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "reasons": reasons,
        "evidence": evidence or {},
    }


def _l1_gate(l1_summary: dict[str, Any]) -> dict[str, Any]:
    decision = _as_dict(l1_summary, "decision")
    comparison = _as_dict(l1_summary, "comparison")
    safety = _as_dict(l1_summary, "safety")
    reasons: list[str] = []
    if decision.get("status") != "L1_SHADOW_AB_GO":
        reasons.append(f"l1_status_not_go:{decision.get('status')}")
    if _to_int(comparison.get("completed_pairs")) < _to_int(comparison.get("min_pairs")):
        reasons.append("l1_completed_pairs_below_prereg_minimum")
    if _to_int(safety.get("b_pgo_shadow_effective_count")) <= 0:
        reasons.append("l1_b_pgo_shadow_missing")
    if _to_int(safety.get("b_knowql_runtime_consumed_count")) <= 0:
        reasons.append("l1_b_knowql_runtime_missing")
    if _to_int(safety.get("pgo_g3_preview_readback_count")) <= 0:
        reasons.append("l1_pgo_g3_preview_missing")
    return _gate(
        "l1_shadow_performance",
        not reasons,
        reasons,
        {
            "completed_pairs": _to_int(comparison.get("completed_pairs")),
            "p95_latency_delta_pct": _to_float(comparison.get("p95_latency_delta_pct")),
            "b_pgo_shadow_effective_count": _to_int(safety.get("b_pgo_shadow_effective_count")),
            "b_knowql_runtime_consumed_count": _to_int(safety.get("b_knowql_runtime_consumed_count")),
            "pgo_g3_preview_readback_count": _to_int(safety.get("pgo_g3_preview_readback_count")),
        },
    )


def _l2_gate(l2_summary: dict[str, Any]) -> dict[str, Any]:
    decision = _as_dict(l2_summary, "decision")
    comparison = _as_dict(l2_summary, "comparison")
    safety = _as_dict(l2_summary, "safety")
    reasons: list[str] = []
    if decision.get("status") != "L2_LEARNING_AB_GO":
        reasons.append(f"l2_status_not_go:{decision.get('status')}")
    if decision.get("safety_status") != "L2_SAFETY_GO":
        reasons.append(f"l2_safety_not_go:{decision.get('safety_status')}")
    if decision.get("effect_status") != "L2_EFFECT_POSITIVE":
        reasons.append(f"l2_effect_not_positive:{decision.get('effect_status')}")
    if _to_int(safety.get("a0_pgo_shadow_present_count")) != 0:
        reasons.append("l2_a0_pgo_contamination")
    if _to_int(safety.get("b1_pgo_shadow_present_count")) != 0:
        reasons.append("l2_b1_pgo_contamination")
    if _to_int(safety.get("b2_pgo_shadow_effective_count")) <= 0:
        reasons.append("l2_b2_pgo_shadow_missing")
    if _to_int(safety.get("b2_knowql_runtime_consumed_count")) <= 0:
        reasons.append("l2_b2_knowql_runtime_missing")
    if _to_int(safety.get("b2_g3_preview_readback_count")) <= 0:
        reasons.append("l2_b2_g3_preview_missing")
    if _to_int(safety.get("b2_nba_intervention_applied_count")) <= 0:
        reasons.append("l2_b2_nba_missing")
    return _gate(
        "l2_learning_efficiency",
        not reasons,
        reasons,
        {
            "b2_outcome_miss_reduction_lift_vs_b1": _to_float(
                comparison.get("b2_outcome_miss_reduction_lift_vs_b1")
            ),
            "b2_p95_latency_delta_pct_vs_b1": _to_float(comparison.get("b2_p95_latency_delta_pct_vs_b1")),
            "b2_payload_delta_pct_vs_b1": _to_float(comparison.get("b2_payload_delta_pct_vs_b1")),
            "b2_pgo_shadow_effective_count": _to_int(safety.get("b2_pgo_shadow_effective_count")),
            "b2_knowql_runtime_consumed_count": _to_int(safety.get("b2_knowql_runtime_consumed_count")),
            "b2_g3_preview_readback_count": _to_int(safety.get("b2_g3_preview_readback_count")),
            "b2_nba_intervention_applied_count": _to_int(safety.get("b2_nba_intervention_applied_count")),
        },
    )


def _l3_gate(l3_summary: dict[str, Any]) -> dict[str, Any]:
    decision = _as_dict(l3_summary, "decision")
    comparison = _as_dict(l3_summary, "comparison")
    cohort = _as_dict(l3_summary, "cohort")
    safety = _as_dict(l3_summary, "safety")
    subjects_by_arm = cohort.get("subjects_by_arm") if isinstance(cohort.get("subjects_by_arm"), dict) else {}
    min_subjects = _to_int(comparison.get("min_subjects_per_arm"))
    reasons: list[str] = []
    if decision.get("status") != "L3_COHORT_AB_GO":
        reasons.append(f"l3_status_not_go:{decision.get('status')}")
    if decision.get("safety_status") != "L3_SAFETY_GO":
        reasons.append(f"l3_safety_not_go:{decision.get('safety_status')}")
    if decision.get("effect_status") != "L3_EFFECT_POSITIVE":
        reasons.append(f"l3_effect_not_positive:{decision.get('effect_status')}")
    if cohort.get("cohort_mode") != "authorized_qa_operator":
        reasons.append(f"l3_cohort_mode_not_authorized_qa_operator:{cohort.get('cohort_mode')}")
    if cohort.get("distinct_learner_per_subject") is not True:
        reasons.append("l3_distinct_learner_per_subject_false")
    for arm in ("A0", "B1", "B2"):
        if _to_int(subjects_by_arm.get(arm)) < min_subjects:
            reasons.append(f"l3_{arm.lower()}_subjects_below_minimum")
    if decision.get("human_learner_claim_allowed") is not False:
        reasons.append("l3_human_learner_claim_overreach")
    if decision.get("production_learner_claim_allowed") is not False:
        reasons.append("l3_production_learner_claim_overreach")
    if _to_int(safety.get("b2_pgo_shadow_effective_count")) <= 0:
        reasons.append("l3_b2_pgo_shadow_missing")
    if _to_int(safety.get("b2_knowql_runtime_consumed_count")) <= 0:
        reasons.append("l3_b2_knowql_runtime_missing")
    if _to_int(safety.get("b2_g3_preview_readback_count")) <= 0:
        reasons.append("l3_b2_g3_preview_missing")
    if _to_int(safety.get("b2_nba_intervention_applied_count")) <= 0:
        reasons.append("l3_b2_nba_missing")
    return _gate(
        "l3_authorized_cohort",
        not reasons,
        reasons,
        {
            "cohort_mode": cohort.get("cohort_mode"),
            "subjects_by_arm": subjects_by_arm,
            "distinct_learner_per_subject": cohort.get("distinct_learner_per_subject"),
            "b2_real_cohort_outcome_miss_reduction_lift_vs_b1": _to_float(
                comparison.get("b2_real_cohort_outcome_miss_reduction_lift_vs_b1")
            ),
            "b2_p95_latency_delta_pct_vs_b1": _to_float(comparison.get("b2_p95_latency_delta_pct_vs_b1")),
            "b2_payload_delta_pct_vs_b1": _to_float(comparison.get("b2_payload_delta_pct_vs_b1")),
        },
    )


def _real_student_evidence_gate(real_student_cohort_evidence: dict[str, Any] | None) -> dict[str, Any]:
    reasons: list[str] = []
    evidence = real_student_cohort_evidence or {}
    if not evidence:
        reasons.append("real_student_cohort_evidence_missing")
    elif evidence.get("schema") != REAL_STUDENT_EVIDENCE_SCHEMA:
        reasons.append(f"real_student_cohort_evidence_schema_mismatch:{evidence.get('schema')}")
    if not str(evidence.get("cohort_source") or "").strip():
        reasons.append("cohort_source_missing")
    if not str(evidence.get("privacy_consent_boundary") or "").strip():
        reasons.append("privacy_consent_boundary_missing")
    sample_size_plan = evidence.get("sample_size_plan") if isinstance(evidence.get("sample_size_plan"), dict) else {}
    if _to_int(sample_size_plan.get("min_subjects_per_arm")) <= 0:
        reasons.append("sample_size_plan_missing")
    return _gate(
        "real_student_cohort_evidence",
        not reasons,
        reasons,
        {
            "cohort_source": evidence.get("cohort_source"),
            "privacy_consent_boundary_present": bool(str(evidence.get("privacy_consent_boundary") or "").strip()),
            "min_subjects_per_arm": _to_int(sample_size_plan.get("min_subjects_per_arm")),
        },
    )


def _authorization_decision(authorization_package: dict[str, Any] | None) -> tuple[dict[str, bool], list[str]]:
    package = authorization_package or {}
    reasons: list[str] = []
    if package and package.get("schema") != AUTHORIZATION_PACKAGE_SCHEMA:
        reasons.append(f"authorization_package_schema_mismatch:{package.get('schema')}")
    decision = package.get("authorization_decision") if isinstance(package.get("authorization_decision"), dict) else package
    flags = {
        "real_student_cohort_authorized": decision.get("real_student_cohort_authorized") is True,
        "real_student_efficacy_claim_authorized": decision.get("real_student_efficacy_claim_authorized") is True,
        "production_default_authorized": decision.get("production_default_authorized") is True,
        "official_score_authorized": decision.get("official_score_authorized") is True,
        "published_registry_authorized": decision.get("published_registry_authorized") is True,
        "canonical_truth_authorized": decision.get("canonical_truth_authorized") is True,
    }
    if any(flags.values()) and decision.get("operator_signature_recorded") is not True:
        reasons.append("operator_signature_missing")
    return flags, reasons


def _production_blockers(
    *,
    gates: dict[str, dict[str, Any]],
    authorization_flags: dict[str, bool],
    authorization_reasons: list[str],
) -> list[str]:
    blockers: list[str] = []
    for key in ("l1_shadow_performance", "l2_learning_efficiency", "l3_authorized_cohort"):
        if not gates[key]["passed"]:
            blockers.append(f"{key}_not_ready")
    blockers.extend(authorization_reasons)
    if not gates["real_student_cohort_evidence"]["passed"]:
        reasons = set(gates["real_student_cohort_evidence"]["reasons"])
        if "privacy_consent_boundary_missing" in reasons:
            blockers.append("privacy_consent_boundary_missing")
        if "sample_size_plan_missing" in reasons:
            blockers.append("sample_size_plan_missing")
    if not authorization_flags["real_student_cohort_authorized"]:
        blockers.append("real_student_cohort_authorization_missing")
    if not authorization_flags["production_default_authorized"]:
        blockers.append("production_default_authorization_missing")
    if not authorization_flags["official_score_authorized"]:
        blockers.append("official_score_authorization_missing")
    if not authorization_flags["published_registry_authorized"]:
        blockers.append("published_registry_authorization_missing")
    if not authorization_flags["canonical_truth_authorized"]:
        blockers.append("canonical_truth_authorization_missing")
    return sorted(set(blockers))


def _negative_evidence(
    *,
    production_blockers: list[str],
    safety_violations: list[str],
    gates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for violation in safety_violations:
        rows.append({"kind": "safety_violation", "code": violation, "scope": "l4_readiness"})
    for blocker in production_blockers:
        rows.append({"kind": "production_blocker", "code": blocker, "scope": "production_authorization"})
    for gate_name, gate in gates.items():
        if not gate.get("passed"):
            rows.append(
                {
                    "kind": "gate_not_passed",
                    "code": gate_name,
                    "scope": "l4_readiness",
                    "reasons": gate.get("reasons") or [],
                }
            )
    return rows


def build_l4_authorization_readiness(
    *,
    l1_summary: dict[str, Any],
    l2_summary: dict[str, Any],
    l3_summary: dict[str, Any],
    real_student_cohort_evidence: dict[str, Any] | None = None,
    authorization_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safety_violations = []
    safety_violations.extend(_safety_violations("l1_summary", l1_summary))
    safety_violations.extend(_safety_violations("l2_summary", l2_summary))
    safety_violations.extend(_safety_violations("l3_summary", l3_summary))
    gates = {
        "l1_shadow_performance": _l1_gate(l1_summary),
        "l2_learning_efficiency": _l2_gate(l2_summary),
        "l3_authorized_cohort": _l3_gate(l3_summary),
        "real_student_cohort_evidence": _real_student_evidence_gate(real_student_cohort_evidence),
    }
    authorization_flags, authorization_reasons = _authorization_decision(authorization_package)
    production_blockers = _production_blockers(
        gates=gates,
        authorization_flags=authorization_flags,
        authorization_reasons=authorization_reasons,
    )
    live_readback_ready = (
        not safety_violations
        and gates["l1_shadow_performance"]["passed"]
        and gates["l2_learning_efficiency"]["passed"]
        and gates["l3_authorized_cohort"]["passed"]
    )
    production_authorized = (
        live_readback_ready
        and gates["real_student_cohort_evidence"]["passed"]
        and not production_blockers
    )
    if safety_violations:
        verdict = "NO_GO_SAFETY_INVARIANT"
    elif production_authorized:
        verdict = "READY_FOR_FINAL_PRODUCTION_SIGNOFF"
    else:
        verdict = "BLOCKED_FOR_PRODUCTION_AUTHORIZATION"
    write_counts = _write_counts(l1_summary, l2_summary, l3_summary)
    negative_evidence = _negative_evidence(
        production_blockers=production_blockers,
        safety_violations=safety_violations,
        gates=gates,
    )
    decisions = {
        "live_readback_claim_allowed": live_readback_ready,
        "real_student_efficacy_claim_allowed": (
            live_readback_ready
            and gates["real_student_cohort_evidence"]["passed"]
            and authorization_flags["real_student_cohort_authorized"]
            and authorization_flags["real_student_efficacy_claim_authorized"]
        ),
        "production_default_allowed": production_authorized and authorization_flags["production_default_authorized"],
        "official_score_allowed": production_authorized and authorization_flags["official_score_authorized"],
        "published_registry_allowed": production_authorized and authorization_flags["published_registry_authorized"],
        "canonical_truth_write_allowed": production_authorized and authorization_flags["canonical_truth_authorized"],
    }
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "live_readback_status": "L4_LIVE_READBACK_READY" if live_readback_ready else "L4_LIVE_READBACK_BLOCKED",
        "production_authorization_status": (
            "L4_PRODUCTION_AUTHORIZATION_READY"
            if production_authorized
            else "L4_PRODUCTION_AUTHORIZATION_BLOCKED"
        ),
        "gates": gates,
        "production_blockers": production_blockers,
        "safety_violations": safety_violations,
        "negative_evidence": negative_evidence,
        "claim_ceiling": {
            "authorized_scope": "test2_qa_operator_live_readback",
            "live_readback_claim_allowed": live_readback_ready,
            "real_student_efficacy_claim_allowed": decisions["real_student_efficacy_claim_allowed"],
            "production_default_allowed": decisions["production_default_allowed"],
            "official_score_allowed": decisions["official_score_allowed"],
            "published_registry_allowed": decisions["published_registry_allowed"],
            "canonical_truth_write_allowed": decisions["canonical_truth_write_allowed"],
        },
        "decisions": decisions,
        "summary": {
            "production_blocker_count": len(production_blockers),
            "safety_violation_count": len(safety_violations),
            "live_readback_gate_count": 3,
            "live_readback_passed_count": sum(
                1
                for key in ("l1_shadow_performance", "l2_learning_efficiency", "l3_authorized_cohort")
                if gates[key]["passed"]
            ),
            **write_counts,
        },
        "safety": {
            **write_counts,
            "canonical_truth_written": write_counts["canonical_truth_write_count"] > 0,
            "official_score_written": write_counts["official_score_write_count"] > 0,
        },
        "not_exercised": [
            "real_student_cohort_ab",
            "production_default_flip",
            "official_score",
            "published_registry",
            "canonical_truth_write",
        ],
        "blocked_actions": [
            "real_student_efficacy_claim",
            "production_default_flip",
            "official_score_write",
            "published_registry_write",
            "canonical_truth_write",
            "remote_write",
        ],
        "stop_conditions": [
            "any canonical/official/unsafe write appears before signed authorization",
            "non cohort or non opt-in request consumes PGO/default path",
            "A0 or B1 shows PGO/KnowQL/G3 contamination",
            "QA/operator identity is represented as real student evidence",
            "official score appears before published registry and release truth authorization",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "l4_authorization_readiness": True,
            "authorization_package_only": True,
            "current_authorized_surface": "test2_qa_operator_live_readback",
            "production_authorized": production_authorized,
            "release_truth_claimed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    decisions = _as_dict(report, "decisions")
    summary = _as_dict(report, "summary")
    lines = [
        "# KnowQL Nexus L4 Authorization Readiness",
        "",
        f"- verdict={report.get('verdict')}",
        f"- live_readback_status={report.get('live_readback_status')}",
        f"- production_authorization_status={report.get('production_authorization_status')}",
        f"- production_blocker_count={summary.get('production_blocker_count')}",
        f"- canonical_truth_write_allowed={str(decisions.get('canonical_truth_write_allowed')).lower()}",
        f"- official_score_allowed={str(decisions.get('official_score_allowed')).lower()}",
        f"- published_registry_allowed={str(decisions.get('published_registry_allowed')).lower()}",
        f"- production_default_allowed={str(decisions.get('production_default_allowed')).lower()}",
        "",
        "## Production Blockers",
        "",
    ]
    blockers = report.get("production_blockers") if isinstance(report.get("production_blockers"), list) else []
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(["", "## Safety Violations", ""])
    violations = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    lines.extend(f"- {violation}" for violation in violations)
    if not violations:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l1-summary", type=Path, default=DEFAULT_L1_SUMMARY)
    parser.add_argument("--l2-summary", type=Path, default=DEFAULT_L2_SUMMARY)
    parser.add_argument("--l3-summary", type=Path, default=DEFAULT_L3_SUMMARY)
    parser.add_argument("--real-student-cohort-evidence", type=Path, default=None)
    parser.add_argument("--authorization-package", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--negative-evidence-output", type=Path, default=DEFAULT_NEGATIVE_EVIDENCE_OUTPUT)
    args = parser.parse_args(argv)
    report = build_l4_authorization_readiness(
        l1_summary=_read_json(args.l1_summary),
        l2_summary=_read_json(args.l2_summary),
        l3_summary=_read_json(args.l3_summary),
        real_student_cohort_evidence=_read_json(args.real_student_cohort_evidence)
        if args.real_student_cohort_evidence is not None
        else None,
        authorization_package=_read_json(args.authorization_package) if args.authorization_package is not None else None,
    )
    _write_json(args.output, report)
    _write_json(
        args.summary_output,
        {
            "schema": report["schema"],
            "verdict": report["verdict"],
            "live_readback_status": report["live_readback_status"],
            "production_authorization_status": report["production_authorization_status"],
            "summary": report["summary"],
            "claim_ceiling": report["claim_ceiling"],
            "production_blockers": report["production_blockers"],
            "safety_violations": report["safety_violations"],
            "blocked_actions": report["blocked_actions"],
        },
    )
    _write_jsonl(args.negative_evidence_output, report["negative_evidence"])
    _write_text(args.markdown_output, render_markdown(report))
    print(
        json.dumps(
            {
                "out": str(args.output),
                "markdown_out": str(args.markdown_output),
                "summary_out": str(args.summary_output),
                "negative_evidence_out": str(args.negative_evidence_output),
                "verdict": report["verdict"],
                "live_readback_status": report["live_readback_status"],
                "production_authorization_status": report["production_authorization_status"],
                "summary": report["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["verdict"] == "NO_GO_SAFETY_INVARIANT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
