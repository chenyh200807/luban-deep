#!/usr/bin/env python3
"""Audit RichLeaf Learning Evidence candidates against current Learning Brain standards.

This is a read-only compatibility audit. It proves candidate workbench payloads
remain outside the current Learning Brain authority unless separately authorized
and rebuilt through the canonical learning-evidence/writeback/readback path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json"
)
DEFAULT_PCP_NBA_CANDIDATE_PROJECTION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json"
)
DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_dry_run_manifest_20260612/test_learner_writeback_dry_run_manifest.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_EXECUTION_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_execution_gate_20260612/test_learner_writeback_execution_gate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_current_standard_compat_audit_20260612/current_standard_compat_audit.json"
)

SCHEMA = "luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1"
BRIDGE_SCHEMA = "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
PCP_SCHEMA = "luban_rich_leaf_pcp_nba_candidate_projection.v1"
SANDBOX_SCHEMA = "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
DRY_RUN_SCHEMA = "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1"
EXECUTION_GATE_SCHEMA = "luban_rich_leaf_test_learner_writeback_execution_gate.v1"

CURRENT_STANDARD_SOURCE_FEATURES = {
    "construction_grading",
    "assessment_testset",
    "conversation_synthesis",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _classification(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("classification") if isinstance(payload.get("classification"), dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else {}


def _safety(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("safety") if isinstance(payload.get("safety"), dict) else {}


def _check_review_only_payload(
    payload: dict[str, Any],
    blockers: list[str],
    *,
    label: str,
    schema: str,
    expected_verdicts: set[str],
    marker_key: str,
) -> None:
    if payload.get("schema") != schema:
        blockers.append(f"{label}_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") not in expected_verdicts:
        blockers.append(f"{label}_unexpected_verdict:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append(f"{label}_quality_claim_allowed")

    classification = _classification(payload)
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append(f"{label}_review_flags_invalid")
    if classification.get(marker_key) is not True:
        blockers.append(f"{label}_classification_invalid")
    for key in (
        "learner_memory_write_allowed",
        "runtime_install_allowed",
        "production_default",
        "release_truth_claimed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"{label}_authority_allowed:{key}")

    safety = _safety(payload)
    for key in (
        "canonical_truth_written",
        "canonical_learner_truth_written",
        "official_score_allowed",
        "installed_runtime_supply",
        "release_truth_claimed",
    ):
        if key in safety and safety.get(key) is not False:
            blockers.append(f"{label}_safety_{key}")
    for key in (
        "production_write_count",
        "learner_memory_write_count",
        "personalization_context_pack_readback_count",
        "training_intent_write_count",
        "next_best_action_write_count",
    ):
        if key in safety and int(safety.get(key) or 0) != 0:
            blockers.append(f"{label}_safety_{key}")


def _event_finding(event: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    event_id = str(event.get("candidate_event_id") or "unknown")
    quality = event.get("quality") if isinstance(event.get("quality"), dict) else {}
    source_feature = str(event.get("source_feature") or "")
    candidate_only = event.get("candidate_only") is True or quality.get("candidate_only") is True
    writeback_eligible = quality.get("writeback_eligible")

    reasons: list[str] = []
    if source_feature not in CURRENT_STANDARD_SOURCE_FEATURES:
        reasons.append("source_feature_not_accepted")
    if candidate_only:
        reasons.append("candidate_only")
    if writeback_eligible is False:
        reasons.append("writeback_eligible_false")
    if event.get("preview_only") is True:
        reasons.append("preview_only")
    if event.get("claim_promotion_allowed") is False:
        reasons.append("claim_promotion_not_allowed")
    if event.get("canonical_truth_written") is False:
        reasons.append("canonical_truth_not_written")

    if writeback_eligible is not False:
        blockers.append(f"candidate_event_writeback_eligible:{event_id}")
    if event.get("candidate_only") is not True:
        blockers.append(f"candidate_event_not_candidate_only:{event_id}")
    if event.get("claim_promotion_allowed") is not False:
        blockers.append(f"candidate_event_claim_promotion_allowed:{event_id}")
    if event.get("canonical_truth_written") is not False:
        blockers.append(f"candidate_event_canonical_truth_written:{event_id}")

    return {
        "candidate_event_id": event_id,
        "source_feature": source_feature,
        "current_standard_payload": False,
        "current_standard_readback_verified": False,
        "writeback_eligible": writeback_eligible is True,
        "candidate_only": candidate_only,
        "incompatibility_reasons": reasons,
    }


def _check_pcp_projection(payload: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    summary = _summary(payload)
    for key in ("pcp_readback_count", "training_intent_write_count", "next_best_action_write_count", "learner_memory_write_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"{key}_nonzero")
    classification = _classification(payload)
    for key in ("personalization_context_pack_readback_allowed", "next_best_action_write_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"pcp_projection_authority_allowed:{key}")
    pcp_candidate = payload.get("personalization_context_pack_candidate")
    pcp_candidate = pcp_candidate if isinstance(pcp_candidate, dict) else {}
    if pcp_candidate.get("readback_verified") is not False:
        blockers.append("pcp_candidate_readback_verified_claimed")
    authority = pcp_candidate.get("authority") if isinstance(pcp_candidate.get("authority"), dict) else {}
    if authority.get("claims") != "candidate_projection_not_learning_synthesis":
        blockers.append("pcp_candidate_claim_authority_not_candidate_projection")
    if authority.get("prescription") != "not_exercised_training_intent":
        blockers.append("pcp_candidate_prescription_authority_claimed")
    for action in payload.get("next_action_candidates") or []:
        if not isinstance(action, dict):
            blockers.append("next_action_candidate_not_object")
            continue
        action_id = str(action.get("action_id") or "unknown")
        if action.get("candidate_only") is not True:
            blockers.append(f"next_action_candidate_not_candidate_only:{action_id}")
        if action.get("status") != "candidate_not_prescription":
            blockers.append(f"next_action_candidate_status_claimed:{action_id}")
        if action.get("prescription_authority") != "not_exercised_training_intent":
            blockers.append(f"next_action_candidate_prescription_claimed:{action_id}")
    return {
        "current_standard_pcp": False,
        "current_standard_readback_verified": False,
        "pcp_readback_count": int(summary.get("pcp_readback_count") or 0),
        "training_intent_write_count": int(summary.get("training_intent_write_count") or 0),
        "next_best_action_write_count": int(summary.get("next_best_action_write_count") or 0),
        "reasons": [
            "candidate_projection_not_learning_synthesis",
            "personalization_context_pack_readback_not_exercised",
            "training_intent_not_exercised",
            "next_best_action_not_exercised",
        ],
    }


def _check_sandbox(payload: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    summary = _summary(payload)
    if int(summary.get("synthesis_observed_candidate_count") or 0) != 0:
        blockers.append("sandbox_synthesis_observed_candidate_count_nonzero")
    if int(summary.get("synthesis_compiled_object_count") or 0) != 0:
        blockers.append("sandbox_synthesis_compiled_object_count_nonzero")
    classification = _classification(payload)
    if classification.get("sandbox_write_scope") != "artifact_only":
        blockers.append("sandbox_write_scope_not_artifact_only")
    return {
        "sandbox_write_scope": classification.get("sandbox_write_scope"),
        "synthesis_observed_candidate_count": int(summary.get("synthesis_observed_candidate_count") or 0),
        "synthesis_compiled_object_count": int(summary.get("synthesis_compiled_object_count") or 0),
        "current_standard_synthesis_consumed_candidate": False,
    }


def _check_dry_run_manifest(payload: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    summary = _summary(payload)
    target = payload.get("target_scope") if isinstance(payload.get("target_scope"), dict) else {}
    batch = payload.get("write_batch_candidate") if isinstance(payload.get("write_batch_candidate"), dict) else {}
    if target.get("target_user_id") != "not_bound_without_authorization":
        blockers.append("dry_run_target_user_bound")
    if batch.get("write_allowed") is not False:
        blockers.append("dry_run_write_allowed")
    if summary.get("writeback_executed") is not False:
        blockers.append("dry_run_writeback_executed")
    return {
        "target_user_id_bound": target.get("target_user_id") != "not_bound_without_authorization",
        "write_allowed": batch.get("write_allowed") is True,
        "planned_event_count": int(summary.get("planned_event_count") or 0),
        "writeback_executed": summary.get("writeback_executed") is True,
    }


def _check_execution_gate(payload: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    decision = payload.get("execution_decision") if isinstance(payload.get("execution_decision"), dict) else {}
    summary = _summary(payload)
    if payload.get("verdict") != "BLOCKED_PENDING_SIGNED_AUTHORIZATION":
        blockers.append(f"execution_gate_not_blocked:{payload.get('verdict')}")
    if decision.get("writeback_allowed") is not False:
        blockers.append("execution_gate_writeback_allowed")
    if decision.get("writeback_executed") is not False:
        blockers.append("execution_gate_writeback_executed")
    if decision.get("target_user_id_bound") is not False:
        blockers.append("execution_gate_target_user_bound")
    if decision.get("signed_authorization_recorded") is not False:
        blockers.append("execution_gate_signed_authorization_recorded")
    return {
        "writeback_allowed": decision.get("writeback_allowed") is True,
        "writeback_executed": decision.get("writeback_executed") is True,
        "target_user_id_bound": decision.get("target_user_id_bound") is True,
        "signed_authorization_recorded": decision.get("signed_authorization_recorded") is True,
        "dry_run_planned_event_count": int(summary.get("dry_run_planned_event_count") or 0),
    }


def run_learning_evidence_current_standard_compat_audit(
    *,
    learning_evidence_candidate_bridge: dict[str, Any],
    pcp_nba_candidate_projection: dict[str, Any],
    test_learner_sandbox_readback_gate: dict[str, Any],
    test_learner_writeback_dry_run_manifest: dict[str, Any],
    test_learner_writeback_execution_gate: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    _check_review_only_payload(
        learning_evidence_candidate_bridge,
        blockers,
        label="learning_evidence_candidate_bridge",
        schema=BRIDGE_SCHEMA,
        expected_verdicts={"PASS"},
        marker_key="learning_evidence_candidate_bridge",
    )
    _check_review_only_payload(
        pcp_nba_candidate_projection,
        blockers,
        label="pcp_nba_candidate_projection",
        schema=PCP_SCHEMA,
        expected_verdicts={"PASS"},
        marker_key="pcp_nba_candidate_projection",
    )
    _check_review_only_payload(
        test_learner_sandbox_readback_gate,
        blockers,
        label="test_learner_sandbox_readback_gate",
        schema=SANDBOX_SCHEMA,
        expected_verdicts={"PASS"},
        marker_key="test_learner_sandbox_readback_gate",
    )
    _check_review_only_payload(
        test_learner_writeback_dry_run_manifest,
        blockers,
        label="test_learner_writeback_dry_run_manifest",
        schema=DRY_RUN_SCHEMA,
        expected_verdicts={"DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION"},
        marker_key="test_learner_writeback_dry_run_manifest",
    )
    _check_review_only_payload(
        test_learner_writeback_execution_gate,
        blockers,
        label="test_learner_writeback_execution_gate",
        schema=EXECUTION_GATE_SCHEMA,
        expected_verdicts={"BLOCKED_PENDING_SIGNED_AUTHORIZATION"},
        marker_key="test_learner_writeback_execution_gate",
    )

    events = [
        event
        for event in learning_evidence_candidate_bridge.get("learning_evidence_event_candidates") or []
        if isinstance(event, dict)
    ]
    if not events:
        blockers.append("no_candidate_events")
    event_findings = [_event_finding(event, blockers) for event in events]
    accepted_source_feature_count = sum(
        1 for event in events if str(event.get("source_feature") or "") in CURRENT_STANDARD_SOURCE_FEATURES
    )
    pcp_finding = _check_pcp_projection(pcp_nba_candidate_projection, blockers)
    sandbox_finding = _check_sandbox(test_learner_sandbox_readback_gate, blockers)
    dry_run_finding = _check_dry_run_manifest(test_learner_writeback_dry_run_manifest, blockers)
    execution_gate_finding = _check_execution_gate(test_learner_writeback_execution_gate, blockers)

    pcp_summary = _summary(pcp_nba_candidate_projection)
    sandbox_summary = _summary(test_learner_sandbox_readback_gate)
    dry_run_summary = _summary(test_learner_writeback_dry_run_manifest)
    gate_summary = _summary(test_learner_writeback_execution_gate)
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "learning_evidence_candidate_bridge": learning_evidence_candidate_bridge.get("schema"),
            "pcp_nba_candidate_projection": pcp_nba_candidate_projection.get("schema"),
            "test_learner_sandbox_readback_gate": test_learner_sandbox_readback_gate.get("schema"),
            "test_learner_writeback_dry_run_manifest": test_learner_writeback_dry_run_manifest.get("schema"),
            "test_learner_writeback_execution_gate": test_learner_writeback_execution_gate.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "current_standard_compat_audit_only",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "learning_evidence_current_standard_compat_audit": True,
            "current_standard_readback_verified": False,
            "learner_memory_write_allowed": False,
            "personalization_context_pack_readback_allowed": False,
            "next_best_action_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "candidate_event_count": len(events),
            "not_current_standard_payload_count": len(event_findings),
            "standard_accepted_source_feature_count": accepted_source_feature_count,
            "current_standard_readback_verified": False,
            "pcp_readback_count": int(pcp_summary.get("pcp_readback_count") or 0),
            "training_intent_write_count": int(pcp_summary.get("training_intent_write_count") or 0),
            "next_best_action_write_count": int(pcp_summary.get("next_best_action_write_count") or 0),
            "sandbox_synthesis_observed_candidate_count": int(sandbox_summary.get("synthesis_observed_candidate_count") or 0),
            "sandbox_synthesis_compiled_object_count": int(sandbox_summary.get("synthesis_compiled_object_count") or 0),
            "dry_run_planned_event_count": int(dry_run_summary.get("planned_event_count") or 0),
            "execution_gate_dry_run_planned_event_count": int(gate_summary.get("dry_run_planned_event_count") or 0),
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "blocker_count": len(blockers),
        },
        "candidate_event_compat_findings": event_findings,
        "pcp_nba_compat_finding": pcp_finding,
        "sandbox_compat_finding": sandbox_finding,
        "dry_run_manifest_finding": dry_run_finding,
        "execution_gate_finding": execution_gate_finding,
        "blockers": blockers,
        "not_exercised": [
            "learner_memory_db_write",
            "canonical_learner_truth_write",
            "learning_synthesis_current_standard_consumption",
            "personalization_context_pack_readback",
            "training_intent_creation",
            "next_best_action_generation",
            "test_learner_writeback",
            "production_db_write",
        ],
        "safety": {
            "canonical_truth_written": False,
            "canonical_learner_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-evidence-candidate-bridge", type=Path, default=DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE)
    parser.add_argument("--pcp-nba-candidate-projection", type=Path, default=DEFAULT_PCP_NBA_CANDIDATE_PROJECTION)
    parser.add_argument("--test-learner-sandbox-readback-gate", type=Path, default=DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE)
    parser.add_argument("--test-learner-writeback-dry-run-manifest", type=Path, default=DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST)
    parser.add_argument("--test-learner-writeback-execution-gate", type=Path, default=DEFAULT_TEST_LEARNER_WRITEBACK_EXECUTION_GATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_learning_evidence_current_standard_compat_audit(
        learning_evidence_candidate_bridge=_read_json(args.learning_evidence_candidate_bridge),
        pcp_nba_candidate_projection=_read_json(args.pcp_nba_candidate_projection),
        test_learner_sandbox_readback_gate=_read_json(args.test_learner_sandbox_readback_gate),
        test_learner_writeback_dry_run_manifest=_read_json(args.test_learner_writeback_dry_run_manifest),
        test_learner_writeback_execution_gate=_read_json(args.test_learner_writeback_execution_gate),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
