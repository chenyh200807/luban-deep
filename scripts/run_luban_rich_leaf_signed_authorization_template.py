#!/usr/bin/env python3
"""Build unsigned no-write authorization templates for RichLeaf next gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_controlled_default_authorization_20260612/controlled_default_authorization_package.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_test_learner_writeback_authorization_package_materialized_20260612/test_learner_writeback_authorization_package.json"
)
DEFAULT_RELEASE_GOVERNANCE_REVIEW = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_release_governance_review_20260612/release_governance_review_packet.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_signed_authorization_template_20260612/signed_authorization_template.json"
)

SCHEMA = "luban_rich_leaf_signed_authorization_template.v1"
CONTROLLED_DEFAULT_SCHEMA = "luban_rich_leaf_controlled_default_authorization_package.v1"
WRITEBACK_AUTH_SCHEMA = "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
RELEASE_GOVERNANCE_SCHEMA = "luban_rich_leaf_release_governance_review_packet.v1"
UNBOUND_TARGET_USER = "UNBOUND_SIGNED_AUTHORIZATION_REQUIRED"


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


def _classification(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("classification") if isinstance(payload.get("classification"), dict) else {}


def _safety(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("safety") if isinstance(payload.get("safety"), dict) else {}


def _controlled_default_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != CONTROLLED_DEFAULT_SCHEMA:
        blockers.append(f"controlled_default_authorization:schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_OPERATOR_SIGNATURE":
        blockers.append(f"controlled_default_authorization:not_ready:{payload.get('verdict')}")
    decision = payload.get("authorization_decision") if isinstance(payload.get("authorization_decision"), dict) else {}
    false_fields = (
        "operator_signature_recorded",
        "controlled_default_authorized",
        "default_install_allowed",
        "canonical_pointer_write_allowed",
        "production_db_write_allowed",
        "remote_write_allowed",
        "release_truth_authorized",
    )
    for field in false_fields:
        if decision.get(field) is not False:
            blockers.append(f"controlled_default_authorization:{field}_true")
    summary = _summary(payload)
    if bool(summary.get("write_executed")):
        blockers.append("controlled_default_authorization:write_executed")
    for field in ("runtime_default_install_count", "canonical_pointer_write_count", "production_write_count", "remote_write_count"):
        if int(summary.get(field) or 0) != 0:
            blockers.append(f"controlled_default_authorization:{field}_nonzero")
    return blockers


def _writeback_authorization_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != WRITEBACK_AUTH_SCHEMA:
        blockers.append(f"test_learner_writeback_authorization:schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_USER_AUTHORIZATION_DECISION":
        blockers.append(f"test_learner_writeback_authorization:not_ready:{payload.get('verdict')}")
    decision = payload.get("authorization_decision") if isinstance(payload.get("authorization_decision"), dict) else {}
    if decision.get("explicit_user_authorization_required") is not True:
        blockers.append("test_learner_writeback_authorization:missing_explicit_user_authorization_required")
    for field in (
        "user_authorization_recorded",
        "test_learner_writeback_authorized",
        "canonical_truth_authorized",
        "production_db_authorized",
    ):
        if decision.get(field) is not False:
            blockers.append(f"test_learner_writeback_authorization:{field}_true")
    summary = _summary(payload)
    if bool(summary.get("writeback_executed")):
        blockers.append("test_learner_writeback_authorization:writeback_executed")
    for field in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(field) or 0) != 0:
            blockers.append(f"test_learner_writeback_authorization:{field}_nonzero")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("test_learner_writeback_authorization:no_candidate_events")
    return blockers


def _release_governance_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != RELEASE_GOVERNANCE_SCHEMA:
        blockers.append(f"release_governance_review:schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") not in {"BLOCKED_FOR_RELEASE_TRUTH", "READY_FOR_FINAL_GOVERNANCE_SIGNOFF"}:
        blockers.append(f"release_governance_review:unexpected_verdict:{payload.get('verdict')}")
    decision = payload.get("release_decision") if isinstance(payload.get("release_decision"), dict) else {}
    for field in (
        "release_truth_claim_allowed",
        "official_score_allowed",
        "production_default_allowed",
        "canonical_truth_write_allowed",
        "production_db_write_allowed",
    ):
        if decision.get(field) is not False:
            blockers.append(f"release_governance_review:{field}_true")
    if decision.get("requires_final_governance_signoff") is not True:
        blockers.append("release_governance_review:missing_final_governance_requirement")
    if payload.get("safety_violations") not in ([], None):
        blockers.append("release_governance_review:safety_violations_present")
    return blockers


def _safety_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = _classification(payload)
    safety = _safety(payload)
    for field in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(field) is True:
            blockers.append(f"{name}:classification_{field}_true")
    for field in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(field) is True:
            blockers.append(f"{name}:safety_{field}_true")
    for field in ("production_write_count", "learner_memory_write_count", "remote_write_count"):
        if int(safety.get(field) or 0) != 0:
            blockers.append(f"{name}:safety_{field}_nonzero")
    if safety.get("canonical_learner_truth_written") is True:
        blockers.append(f"{name}:safety_canonical_learner_truth_written_true")
    return blockers


def _build_controlled_default_template(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("candidate_scope") if isinstance(payload.get("candidate_scope"), dict) else {}
    return {
        "template_id": "rich_leaf_controlled_default_operator_signature_v1",
        "signature_status": "unsigned",
        "required_signer_role": "operator_or_governance_owner",
        "operator_id": "UNBOUND_SIGNED_AUTHORIZATION_REQUIRED",
        "decision_id": "UNBOUND_SIGNED_AUTHORIZATION_REQUIRED",
        "allowed_scope": "controlled_shadow_default_only_after_signature",
        "runtime_default_install_allowed": False,
        "canonical_pointer_write_allowed": False,
        "production_db_write_allowed": False,
        "remote_write_allowed": False,
        "release_truth_allowed": False,
        "rollback_plan_approval_required": True,
        "observability_plan_approval_required": True,
        "required_evidence": {
            "runtime_token_pack_unit_count": int(scope.get("runtime_token_pack_unit_count") or 0),
            "supply_unit_count": int(scope.get("supply_unit_count") or 0),
            "streaming_sample_count": int(scope.get("streaming_sample_count") or 0),
            "streaming_provider_call_count": int(scope.get("streaming_provider_call_count") or 0),
            "streaming_ttft_delta_ms": float(scope.get("streaming_ttft_delta_ms") or 0.0),
        },
        "must_remain_false_until_signed": [
            "runtime_default_install_allowed",
            "canonical_pointer_write_allowed",
            "production_db_write_allowed",
            "remote_write_allowed",
            "release_truth_allowed",
        ],
    }


def _build_writeback_template(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("candidate_scope") if isinstance(payload.get("candidate_scope"), dict) else {}
    summary = _summary(payload)
    return {
        "template_id": "rich_leaf_test_learner_writeback_signature_v1",
        "signature_status": "unsigned",
        "required_signer_role": "operator_or_learning_brain_owner",
        "target_user_id": UNBOUND_TARGET_USER,
        "target_memory_kind": scope.get("target_memory_kind") or "learning_evidence",
        "target_source_feature": scope.get("target_source_feature") or "rich_leaf_authorized_test_writeback",
        "candidate_event_count": int(summary.get("candidate_event_count") or scope.get("max_candidate_event_count") or 0),
        "writeback_allowed": False,
        "learner_memory_write_allowed": False,
        "canonical_learner_truth_allowed": False,
        "production_db_write_allowed": False,
        "personalization_context_pack_readback_claim_allowed": False,
        "rollback_plan_approval_required": True,
        "pre_write_snapshot_required": True,
        "post_write_readback_required": True,
        "must_remain_false_until_signed": [
            "writeback_allowed",
            "learner_memory_write_allowed",
            "canonical_learner_truth_allowed",
            "production_db_write_allowed",
        ],
    }


def _build_release_template(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _summary(payload)
    return {
        "template_id": "rich_leaf_release_truth_governance_signature_v1",
        "signature_status": "unsigned",
        "required_signer_role": "release_governance_owner",
        "release_truth_claim_allowed": False,
        "official_score_allowed": False,
        "production_default_allowed": False,
        "canonical_truth_write_allowed": False,
        "production_db_write_allowed": False,
        "requires_final_governance_signoff": True,
        "required_evidence": {
            "semantic_decision_count": int(summary.get("semantic_decision_count") or 0),
            "runtime_token_pack_unit_count": int(summary.get("runtime_token_pack_unit_count") or 0),
            "planned_learning_event_count": int(summary.get("planned_learning_event_count") or 0),
            "safety_violation_count": int(summary.get("safety_violation_count") or 0),
            "release_blocker_count": int(summary.get("release_blocker_count") or 0),
        },
        "must_remain_false_until_final_governance": [
            "release_truth_claim_allowed",
            "official_score_allowed",
            "production_default_allowed",
            "canonical_truth_write_allowed",
            "production_db_write_allowed",
        ],
    }


def run_signed_authorization_template(
    *,
    controlled_default_authorization: dict[str, Any],
    test_learner_writeback_authorization: dict[str, Any],
    release_governance_review: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_controlled_default_blockers(controlled_default_authorization))
    blockers.extend(_writeback_authorization_blockers(test_learner_writeback_authorization))
    blockers.extend(_release_governance_blockers(release_governance_review))
    blockers.extend(_safety_blockers("controlled_default_authorization", controlled_default_authorization))
    blockers.extend(_safety_blockers("test_learner_writeback_authorization", test_learner_writeback_authorization))
    blockers.extend(_safety_blockers("release_governance_review", release_governance_review))

    verdict = "BLOCKED_INPUT_SAFETY_INVARIANT" if blockers else "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE"
    writeback_summary = _summary(test_learner_writeback_authorization)
    release_summary = _summary(release_governance_review)
    return {
        "schema": SCHEMA,
        "input_line": controlled_default_authorization.get("input_line") or "v1_legacy",
        "input_schemas": {
            "controlled_default_authorization": controlled_default_authorization.get("schema"),
            "test_learner_writeback_authorization": test_learner_writeback_authorization.get("schema"),
            "release_governance_review": release_governance_review.get("schema"),
        },
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "unsigned_authorization_template_only",
        "signature_templates": {
            "controlled_default_operator": _build_controlled_default_template(controlled_default_authorization),
            "test_learner_writeback": _build_writeback_template(test_learner_writeback_authorization),
            "release_truth_governance": _build_release_template(release_governance_review),
        },
        "summary": {
            "template_count": 3,
            "blocker_count": len(blockers),
            "planned_learning_event_count": int(release_summary.get("planned_learning_event_count") or 0),
            "candidate_event_count": int(writeback_summary.get("candidate_event_count") or 0),
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "blockers": blockers,
        "not_exercised": [
            "operator_signature_recording",
            "runtime_default_install",
            "canonical_pointer_write",
            "test_learner_memory_write",
            "personalization_context_pack_readback",
            "release_truth_claim",
            "official_score",
            "production_db_write",
            "remote_write",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "signed_authorization_template": True,
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
            "remote_write_count": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controlled-default-authorization", type=Path, default=DEFAULT_CONTROLLED_DEFAULT_AUTHORIZATION)
    parser.add_argument("--test-learner-writeback-authorization", type=Path, default=DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION)
    parser.add_argument("--release-governance-review", type=Path, default=DEFAULT_RELEASE_GOVERNANCE_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_signed_authorization_template(
        controlled_default_authorization=_read_json(args.controlled_default_authorization),
        test_learner_writeback_authorization=_read_json(args.test_learner_writeback_authorization),
        release_governance_review=_read_json(args.release_governance_review),
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["verdict"] == "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
