#!/usr/bin/env python3
"""Build review-only audit records from RichLeaf shadow residual review decisions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_packets_20260612/shadow_residual_review_packets.json"
)
DEFAULT_REVIEW_DECISIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decisions_20260612/ai_council_shadow_review_decisions.json"
)
DEFAULT_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_validation_20260612/shadow_residual_review_decision_validation.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_audit_record_20260612/shadow_residual_audit_record.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_audit_record.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _packet_index(review_packets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(packet.get("packet_id")): packet
        for packet in review_packets.get("review_packets") or []
        if isinstance(packet, dict) and packet.get("packet_id")
    }


def _decision_index(review_decisions: dict[str, Any], blockers: list[str]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for decision in review_decisions.get("decisions") or []:
        if not isinstance(decision, dict):
            blockers.append("decision_entry_not_object")
            continue
        packet_id = str(decision.get("packet_id") or "")
        if not packet_id:
            blockers.append("decision_missing_packet_id")
            continue
        if decision.get("decision_recorded") is not True or decision.get("shadow_only") is not True:
            blockers.append(f"decision_record_or_shadow_flag_invalid:{packet_id}")
        if (
            decision.get("patch_generation_allowed") is not False
            or decision.get("runtime_install_allowed") is not False
            or decision.get("release_truth_claimed") is not False
        ):
            blockers.append(f"decision_authority_allowed:{packet_id}")
        indexed[packet_id] = decision
    return indexed


def _next_compiler_action(decision: str | None) -> str:
    if decision == "confirm_guard_needed":
        return "guard_review_required"
    if decision == "request_source_ref_reaudit":
        return "source_ref_reaudit_required"
    if decision == "request_leaf_retaxonomy":
        return "leaf_retaxonomy_required"
    if decision == "dismiss_after_review":
        return "dismissed_after_shadow_review"
    return "not_classified"


def _record(packet: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    trace = packet.get("work_order_trace") if isinstance(packet.get("work_order_trace"), dict) else {}
    return {
        "audit_record_id": f"shadow_residual_audit_record:{packet.get('packet_id')}",
        "packet_id": packet.get("packet_id"),
        "work_order_id": packet.get("work_order_id"),
        "leaf_id": packet.get("leaf_id"),
        "review_scope": packet.get("review_scope"),
        "trigger_reason": packet.get("trigger_reason"),
        "decision": decision.get("decision"),
        "next_compiler_action": _next_compiler_action(decision.get("decision")),
        "reviewer_role": decision.get("reviewer_role"),
        "reviewer_id": decision.get("reviewer_id"),
        "rationale": decision.get("rationale"),
        "confidence": decision.get("confidence"),
        "shadow_only": True,
        "source_seed_id": decision.get("source_seed_id"),
        "work_order_trace": {
            "artifact_ids": list(trace.get("artifact_ids") or []),
            "field_ids": list(trace.get("field_ids") or []),
            "record_ids": list(trace.get("record_ids") or []),
            "source_lanes": list(trace.get("source_lanes") or []),
            "reason_codes": list(trace.get("reason_codes") or []),
            "guard_evidence_count": int(trace.get("guard_evidence_count") or 0),
            "residual_case_ids": list(trace.get("residual_case_ids") or []),
            "tasks": list(trace.get("tasks") or []),
        },
        "candidate_only": True,
        "review_only": True,
        "patch_generation_allowed": False,
        "source_ref_mutation_allowed": False,
        "runtime_install_allowed": False,
        "runtime_guard_enforcement_allowed": False,
        "release_truth_claimed": False,
        "quality_claim_allowed": False,
        "learner_memory_write_allowed": False,
    }


def build_shadow_residual_audit_record(
    *, review_packets: dict[str, Any], review_decisions: dict[str, Any], decision_validation: dict[str, Any]
) -> dict[str, Any]:
    blockers: list[str] = []
    if review_packets.get("schema") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append(f"review_packets_schema_mismatch:{review_packets.get('schema')}")
    if review_packets.get("verdict") != "PASS":
        blockers.append(f"review_packets_failed:{review_packets.get('verdict')}")
    if review_decisions.get("schema") != "luban_rich_leaf_shadow_residual_review_decisions.v1":
        blockers.append(f"review_decisions_schema_mismatch:{review_decisions.get('schema')}")
    if review_decisions.get("verdict") != "PASS":
        blockers.append(f"review_decisions_failed:{review_decisions.get('verdict')}")
    decisions_classification = (
        review_decisions.get("classification") if isinstance(review_decisions.get("classification"), dict) else {}
    )
    if decisions_classification.get("ai_council_shadow_only") is not True:
        blockers.append("review_decisions_not_ai_council_shadow_only")
    for key in ("patch_generation_allowed", "runtime_install_allowed", "release_truth_claimed", "quality_claim_allowed"):
        if decisions_classification.get(key) is not False:
            blockers.append(f"review_decisions_authority_allowed:{key}")
    if decision_validation.get("schema") != "luban_rich_leaf_shadow_residual_review_decision_validation.v1":
        blockers.append(f"decision_validation_schema_mismatch:{decision_validation.get('schema')}")
    if decision_validation.get("verdict") != "PASS":
        blockers.append(f"decision_validation_not_pass:{decision_validation.get('verdict')}")
    validation_summary = (
        decision_validation.get("summary") if isinstance(decision_validation.get("summary"), dict) else {}
    )
    for key in ("missing_decision_count", "invalid_decision_count", "duplicate_decision_count", "stale_decision_count", "blocker_count"):
        if int(validation_summary.get(key) or 0) != 0:
            blockers.append(f"decision_validation_{key}:{validation_summary.get(key)}")

    packets = _packet_index(review_packets)
    decisions = _decision_index(review_decisions, blockers)
    records: list[dict[str, Any]] = []
    if not blockers:
        for packet_id, packet in packets.items():
            decision = decisions.get(packet_id)
            if decision is None:
                blockers.append(f"decision_missing_for_packet:{packet_id}")
                continue
            records.append(_record(packet, decision))

    action_counts = {
        "guard_review_required_count": sum(1 for record in records if record["next_compiler_action"] == "guard_review_required"),
        "source_ref_reaudit_required_count": sum(
            1 for record in records if record["next_compiler_action"] == "source_ref_reaudit_required"
        ),
        "leaf_retaxonomy_required_count": sum(1 for record in records if record["next_compiler_action"] == "leaf_retaxonomy_required"),
        "dismissed_after_shadow_review_count": sum(
            1 for record in records if record["next_compiler_action"] == "dismissed_after_shadow_review"
        ),
    }
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "review_packets": review_packets.get("schema"),
            "review_decisions": review_decisions.get("schema"),
            "decision_validation": decision_validation.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_audit_record": True,
            "ai_council_shadow_only": True,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        },
        "summary": {
            "packet_count": len(packets),
            "decision_count": len(decisions),
            "audit_record_count": len(records),
            "blocker_count": len(blockers),
            **action_counts,
        },
        "shadow_residual_audit_records": records,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_signoff",
            "governance_signoff",
            "candidate_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
            "learner_memory_writeback",
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-packets", type=Path, default=DEFAULT_REVIEW_PACKETS)
    parser.add_argument("--review-decisions", type=Path, default=DEFAULT_REVIEW_DECISIONS)
    parser.add_argument("--decision-validation", type=Path, default=DEFAULT_DECISION_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_shadow_residual_audit_record(
        review_packets=_read_json(args.review_packets),
        review_decisions=_read_json(args.review_decisions),
        decision_validation=_read_json(args.decision_validation),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
