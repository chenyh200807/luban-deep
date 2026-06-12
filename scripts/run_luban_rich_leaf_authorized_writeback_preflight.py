#!/usr/bin/env python3
"""Authorization preflight before any test-learner RichLeaf writeback.

This script does not write learner memory. It records the explicit authority
required before candidate evidence may be written into a test learner account.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json"
)
DEFAULT_PCP_NBA_CANDIDATE_PROJECTION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_authorized_writeback_preflight_20260612/authorized_writeback_preflight.json"
)
SCHEMA = "luban_rich_leaf_authorized_writeback_preflight.v1"
SANDBOX_SCHEMA = "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
PCP_SCHEMA = "luban_rich_leaf_pcp_nba_candidate_projection.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sandbox_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != SANDBOX_SCHEMA:
        blockers.append(f"sandbox_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"sandbox_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("sandbox_quality_claim_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("sandbox_no_candidate_events")
    if int(summary.get("sandbox_readback_event_count") or 0) <= 0:
        blockers.append("sandbox_no_readback_events")
    if int(summary.get("synthesis_observed_candidate_count") or 0) != 0:
        blockers.append("sandbox_synthesis_observed_candidate_count")
    if int(summary.get("synthesis_compiled_object_count") or 0) != 0:
        blockers.append("sandbox_synthesis_compiled_object_count")
    for key in ("learner_memory_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"sandbox_summary_{key}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("sandbox_write_scope") != "artifact_only":
        blockers.append("sandbox_not_artifact_only")
    if classification.get("learner_memory_write_allowed") is not False:
        blockers.append("sandbox_learner_memory_write_allowed")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("sandbox_canonical_learner_truth_written")
    return blockers


def _pcp_projection_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != PCP_SCHEMA:
        blockers.append(f"pcp_projection_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"pcp_projection_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("pcp_projection_quality_claim_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("top_claim_candidate_count") or 0) <= 0:
        blockers.append("pcp_projection_no_claim_candidates")
    for key in ("learner_memory_write_count", "pcp_readback_count", "training_intent_write_count", "next_best_action_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"pcp_projection_summary_{key}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("learner_memory_write_allowed", "personalization_context_pack_readback_allowed", "next_best_action_write_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"pcp_projection_classification_{key}")
    return blockers


def run_authorized_writeback_preflight(
    *,
    test_learner_sandbox_readback_gate: dict[str, Any],
    pcp_nba_candidate_projection: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_sandbox_blockers(test_learner_sandbox_readback_gate))
    blockers.extend(_pcp_projection_blockers(pcp_nba_candidate_projection))
    sandbox_summary = test_learner_sandbox_readback_gate.get("summary") if isinstance(test_learner_sandbox_readback_gate.get("summary"), dict) else {}
    pcp_summary = pcp_nba_candidate_projection.get("summary") if isinstance(pcp_nba_candidate_projection.get("summary"), dict) else {}
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "test_learner_sandbox_readback_gate": test_learner_sandbox_readback_gate.get("schema"),
            "pcp_nba_candidate_projection": pcp_nba_candidate_projection.get("schema"),
        },
        "verdict": "FAIL" if blockers else "READY_FOR_AUTHORIZATION_REVIEW",
        "quality_claim_allowed": False,
        "execution_mode": "authorization_preflight_only",
        "authorization": {
            "explicit_user_authorization_required": True,
            "test_learner_writeback_authorized": False,
            "allowed_write_scope": "none_without_authorization",
            "canonical_truth_authorized": False,
            "production_db_authorized": False,
        },
        "writeback_plan_candidate": {
            "target_memory_kind": "learning_evidence",
            "target_source_feature": "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
            "max_candidate_event_count": int(sandbox_summary.get("valid_candidate_event_count") or 0),
            "canonical_truth_after_writeback": "still_forbidden_without_separate_authorization",
        },
        "summary": {
            "blocker_count": len(blockers),
            "candidate_event_count": int(sandbox_summary.get("candidate_event_count") or 0),
            "sandbox_readback_event_count": int(sandbox_summary.get("sandbox_readback_event_count") or 0),
            "top_claim_candidate_count": int(pcp_summary.get("top_claim_candidate_count") or 0),
            "next_action_candidate_count": int(pcp_summary.get("next_action_candidate_count") or 0),
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "missing_authorizations": [
            "explicit_user_authorization",
            "test_learner_identity_scope",
            "teacher_final_or_governance_review",
            "rollback_plan_for_test_learner_writeback",
            "separate_canonical_truth_authorization",
        ],
        "blockers": blockers,
        "not_exercised_by_layer": {
            "memory_not_exercised": [
                "learner_state_service_append_memory_event",
                "learner_memory_db_write",
                "learner_memory_outbox_enqueue",
                "supabase_learner_memory_events_write",
            ],
            "learning_brain_not_exercised": [
                "production_learning_synthesis",
                "personalization_context_pack_readback",
                "training_intent_creation",
                "next_best_action_generation",
                "canonical_truth_write",
            ],
            "release_not_exercised": ["governance_signoff", "production_default_decision"],
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "authorized_writeback_preflight": True,
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
    parser.add_argument("--pcp-nba-candidate-projection", type=Path, default=DEFAULT_PCP_NBA_CANDIDATE_PROJECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_authorized_writeback_preflight(
        test_learner_sandbox_readback_gate=_read_json(args.test_learner_sandbox_readback_gate),
        pcp_nba_candidate_projection=_read_json(args.pcp_nba_candidate_projection),
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "READY_FOR_AUTHORIZATION_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
