#!/usr/bin/env python3
"""Summarize RichLeaf compiler status without promoting candidate artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_compiler_status_ledger.v1"
DEFAULT_LEGACY_QUALITY_AUDIT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_legacy_compilation_quality_audit_20260612/legacy_quality_audit.json"
)
DEFAULT_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_review_decision_validation_materialized_20260612/semantic_review_decision_validation.json"
)
DEFAULT_MANUAL_REVIEW_PACKETS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_manual_review_packets_20260612/manual_review_packets.json"
)
DEFAULT_SEMANTIC_RUNTIME_LIVE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_runtime_live_ab_materialized_20260612/semantic_runtime_live_ab.json"
)
DEFAULT_WRITEBACK_EXECUTION_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_test_learner_writeback_execution_gate_materialized_20260612/test_learner_writeback_execution_gate.json"
)
DEFAULT_RUNTIME_DEFAULT_GATE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_default_gate_20260612/runtime_default_gate.json"
)
DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_controlled_default_authorization_20260612/controlled_default_authorization_package.json"
)
DEFAULT_RELEASE_GOVERNANCE_REVIEW = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_release_governance_review_20260612/release_governance_review_packet.json"
)
DEFAULT_SIGNED_AUTHORIZATION_TEMPLATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_signed_authorization_template_20260612/signed_authorization_template.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_compiler_status_ledger_20260612/compiler_status_ledger.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else {}


def _check_safety(name: str, payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if key in classification and classification.get(key) is not False:
            violations.append(f"{name}:classification.{key}_not_false")
    for key in ("installed_runtime_supply", "release_truth_claimed", "canonical_truth_written", "official_score_allowed"):
        if key in safety and safety.get(key) is not False:
            violations.append(f"{name}:safety.{key}_not_false")
    if int(safety.get("production_write_count") or 0) != 0:
        violations.append(f"{name}:safety.production_write_count_nonzero")
    if int(safety.get("learner_memory_write_count") or 0) != 0:
        violations.append(f"{name}:safety.learner_memory_write_count_nonzero")
    if safety.get("canonical_learner_truth_written") is True:
        violations.append(f"{name}:safety.canonical_learner_truth_written_not_false")
    return violations


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def build_compiler_status_ledger(
    *,
    legacy_quality_audit: dict[str, Any],
    decision_validation: dict[str, Any],
    manual_review_packets: dict[str, Any],
    semantic_runtime_live_ab: dict[str, Any],
    writeback_execution_gate: dict[str, Any],
    runtime_default_gate: dict[str, Any] | None = None,
    controlled_default_authorization: dict[str, Any] | None = None,
    release_governance_review: dict[str, Any] | None = None,
    signed_authorization_template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safety_violations: list[str] = []
    named_payloads = {
        "legacy_quality_audit": legacy_quality_audit,
        "decision_validation": decision_validation,
        "manual_review_packets": manual_review_packets,
        "semantic_runtime_live_ab": semantic_runtime_live_ab,
        "writeback_execution_gate": writeback_execution_gate,
    }
    if runtime_default_gate is not None:
        named_payloads["runtime_default_gate"] = runtime_default_gate
    if controlled_default_authorization is not None:
        named_payloads["controlled_default_authorization"] = controlled_default_authorization
    if release_governance_review is not None:
        named_payloads["release_governance_review"] = release_governance_review
    if signed_authorization_template is not None:
        named_payloads["signed_authorization_template"] = signed_authorization_template
    for name, payload in named_payloads.items():
        safety_violations.extend(_check_safety(name, payload))

    legacy_summary = _summary(legacy_quality_audit)
    decision_summary = _summary(decision_validation)
    manual_summary = _summary(manual_review_packets)
    live_summary = _summary(semantic_runtime_live_ab)
    writeback_summary = _summary(writeback_execution_gate)
    runtime_default_summary = _summary(runtime_default_gate or {})
    release_governance_summary = _summary(release_governance_review or {})
    signed_template_summary = _summary(signed_authorization_template or {})

    missing_decisions = int(decision_summary.get("missing_decision_count") or 0)
    manual_packets = int(manual_summary.get("manual_review_packet_count") or 0)
    provider_calls = int(live_summary.get("provider_call_count") or 0)
    learner_writes = int(writeback_summary.get("learner_memory_write_count") or 0)
    production_writes = int(writeback_summary.get("production_write_count") or 0)
    planned_learning_events = int(
        writeback_summary.get("planned_event_count")
        or writeback_summary.get("dry_run_planned_event_count")
        or 0
    )
    runtime_default_ready = (
        isinstance(runtime_default_gate, dict)
        and runtime_default_gate.get("verdict") == "READY_FOR_CONTROLLED_DEFAULT_REVIEW"
    )
    controlled_default_status = (
        "ready_for_operator_signature"
        if isinstance(controlled_default_authorization, dict)
        and controlled_default_authorization.get("verdict") == "READY_FOR_OPERATOR_SIGNATURE"
        else "not_exercised"
    )
    release_governance_exercised = isinstance(release_governance_review, dict)
    release_governance_blockers = [
        str(blocker)
        for blocker in ((release_governance_review or {}).get("release_blockers") or [])
        if str(blocker)
    ]
    signed_template_status = (
        "ready_for_external_signature_capture"
        if isinstance(signed_authorization_template, dict)
        and signed_authorization_template.get("verdict") == "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE"
        else "not_exercised"
    )

    blockers: list[str] = []
    if manual_packets and missing_decisions:
        blockers.append(f"manual_review_backlog:{manual_packets}")
    if missing_decisions:
        blockers.append(f"semantic_decisions_incomplete:{missing_decisions}")
    if semantic_runtime_live_ab.get("verdict") == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED":
        blockers.append("live_provider_authorization_missing")
    if writeback_execution_gate.get("verdict") == "BLOCKED_PENDING_SIGNED_AUTHORIZATION":
        blockers.append("learning_brain_signed_authorization_missing")
    if release_governance_exercised:
        blockers.extend(release_governance_blockers)
    elif "release_truth_governance" in (semantic_runtime_live_ab.get("not_exercised") or []):
        blockers.append("release_governance_not_exercised")
    if production_writes or learner_writes:
        blockers.append("unexpected_write_counts_present")
    blockers = _unique(blockers)

    if safety_violations:
        overall_verdict = "NO_GO_SAFETY_INVARIANT"
    elif not blockers:
        overall_verdict = "PASS_SHADOW_CANDIDATE_READY_FOR_AUTHORIZED_NEXT_GATES"
    else:
        overall_verdict = "WEAK_GO_SHADOW_CANDIDATE"

    if manual_packets and missing_decisions:
        manual_status = "ready_for_ai_council_review"
    elif manual_packets:
        manual_status = "shadow_decisions_completed"
    else:
        manual_status = "none"
    live_status = "blocked_provider_authorization" if semantic_runtime_live_ab.get("verdict") == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED" else str(semantic_runtime_live_ab.get("verdict"))
    write_status = (
        "blocked_pending_signed_authorization"
        if writeback_execution_gate.get("verdict") == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
        else str(writeback_execution_gate.get("verdict"))
    )
    runtime_default_status = "ready_for_controlled_default_review" if runtime_default_ready else "not_exercised"
    recommended_next_actions: list[str] = []
    if missing_decisions:
        recommended_next_actions.append("run_ai_council_manual_review_packets")
    if semantic_runtime_live_ab.get("verdict") == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED":
        recommended_next_actions.append("run_authorized_live_provider_ab")
    if runtime_default_ready:
        recommended_next_actions.append("obtain_signed_runtime_default_decision_and_rollback_plan")
    recommended_next_actions.extend(
        [
            "obtain_signed_test_learner_writeback_authorization",
            "run_release_governance_review_after_shadow_gates",
        ]
    )

    return {
        "schema": SCHEMA,
        "input_schemas": {name: payload.get("schema") for name, payload in named_payloads.items()},
        "overall_verdict": overall_verdict,
        "quality_claim_allowed": False,
        "release_truth_claimed": False,
        "runtime_default_status": runtime_default_status,
        "learning_brain_write_status": write_status,
        "summary": {
            "legacy_artifact_dir_count": int(legacy_summary.get("artifact_dir_count") or 0),
            "legacy_direct_reuse_blocked_count": int(legacy_summary.get("direct_reuse_blocked_count") or 0),
            "legacy_quality_gap_count": int(legacy_summary.get("quality_gap_count") or 0),
            "legacy_safety_violation_count": int(legacy_summary.get("safety_violation_count") or 0),
            "semantic_audit_item_count": int(decision_summary.get("audit_item_count") or 0),
            "semantic_decision_count": int(decision_summary.get("decision_count") or 0),
            "missing_semantic_decision_count": missing_decisions,
            "manual_review_packet_count": manual_packets,
            "provider_call_count": provider_calls,
            "live_runtime_executed": bool(live_summary.get("live_runtime_executed")),
            "planned_learning_event_count": planned_learning_events,
            "runtime_token_pack_unit_count": int(runtime_default_summary.get("token_pack_unit_count") or 0),
            "runtime_default_streaming_sample_count": int(runtime_default_summary.get("streaming_sample_count") or 0),
            "runtime_default_streaming_ttft_delta_ms": float(runtime_default_summary.get("streaming_ttft_delta_ms") or 0.0),
            "signed_authorization_template_count": int(signed_template_summary.get("template_count") or 0),
            "release_governance_blocker_count": int(
                release_governance_summary.get("release_blocker_count") or len(release_governance_blockers)
            ),
            "learner_memory_write_count": learner_writes,
            "production_write_count": production_writes,
            "safety_violation_count": len(safety_violations),
            "blocker_count": len(blockers),
        },
        "stage_status": {
            "legacy_quality": {
                "status": "blocked_for_direct_reuse",
                "verdict": legacy_quality_audit.get("verdict"),
            },
            "semantic_review": {
                "status": "incomplete" if missing_decisions else "validated",
                "verdict": decision_validation.get("verdict"),
            },
            "manual_review": {
                "status": manual_status,
                "packet_count": manual_packets,
                "by_missing_lane": manual_summary.get("by_missing_lane") or {},
            },
            "live_runtime_ab": {
                "status": live_status,
                "verdict": semantic_runtime_live_ab.get("verdict"),
                "provider_call_count": provider_calls,
            },
            "learning_brain_writeback": {
                "status": write_status,
                "verdict": writeback_execution_gate.get("verdict"),
                "learner_memory_write_count": learner_writes,
            },
            "runtime_default_gate": {
                "status": runtime_default_status,
                "verdict": (runtime_default_gate or {}).get("verdict"),
                "default_installed": False,
            },
            "controlled_default_authorization": {
                "status": controlled_default_status,
                "verdict": (controlled_default_authorization or {}).get("verdict"),
                "default_installed": False,
            },
            "release_governance": {
                "status": "blocked_for_release_truth"
                if (release_governance_review or {}).get("verdict") == "BLOCKED_FOR_RELEASE_TRUTH"
                else (
                    "ready_for_final_governance_signoff"
                    if (release_governance_review or {}).get("verdict") == "READY_FOR_FINAL_GOVERNANCE_SIGNOFF"
                    else "not_exercised"
                ),
                "verdict": (release_governance_review or {}).get("verdict"),
                "release_truth_claimed": False,
            },
            "signed_authorization_template": {
                "status": signed_template_status,
                "verdict": (signed_authorization_template or {}).get("verdict"),
                "template_count": int(signed_template_summary.get("template_count") or 0),
                "write_executed": False,
            },
        },
        "blockers": blockers,
        "safety_violations": safety_violations,
        "recommended_next_actions": recommended_next_actions,
        "not_exercised": [
            "runtime_default",
            "canonical_truth_write",
            "official_score",
            "production_db_write",
            "release_truth_governance",
        ],
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
    parser.add_argument("--legacy-quality-audit", type=Path, default=DEFAULT_LEGACY_QUALITY_AUDIT)
    parser.add_argument("--decision-validation", type=Path, default=DEFAULT_DECISION_VALIDATION)
    parser.add_argument("--manual-review-packets", type=Path, default=DEFAULT_MANUAL_REVIEW_PACKETS)
    parser.add_argument("--semantic-runtime-live-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_LIVE_AB)
    parser.add_argument("--writeback-execution-gate", type=Path, default=DEFAULT_WRITEBACK_EXECUTION_GATE)
    parser.add_argument("--runtime-default-gate", type=Path, default=DEFAULT_RUNTIME_DEFAULT_GATE)
    parser.add_argument("--controlled-default-authorization", type=Path, default=DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION)
    parser.add_argument("--release-governance-review", type=Path, default=DEFAULT_RELEASE_GOVERNANCE_REVIEW)
    parser.add_argument("--signed-authorization-template", type=Path, default=DEFAULT_SIGNED_AUTHORIZATION_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_compiler_status_ledger(
        legacy_quality_audit=_read_json(args.legacy_quality_audit),
        decision_validation=_read_json(args.decision_validation),
        manual_review_packets=_read_json(args.manual_review_packets),
        semantic_runtime_live_ab=_read_json(args.semantic_runtime_live_ab),
        writeback_execution_gate=_read_json(args.writeback_execution_gate),
        runtime_default_gate=_read_json(args.runtime_default_gate) if args.runtime_default_gate.exists() else None,
        controlled_default_authorization=_read_json(args.controlled_default_authorization)
        if args.controlled_default_authorization.exists()
        else None,
        release_governance_review=_read_json(args.release_governance_review)
        if args.release_governance_review.exists()
        else None,
        signed_authorization_template=_read_json(args.signed_authorization_template)
        if args.signed_authorization_template.exists()
        else None,
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "overall_verdict": report["overall_verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["overall_verdict"] == "NO_GO_SAFETY_INVARIANT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
