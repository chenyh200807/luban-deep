#!/usr/bin/env python3
"""Materialize AI-council shadow decisions for RichLeaf shadow residual guard review packets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_GUARD_REVIEW_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_packets_20260612/shadow_residual_guard_review_packets.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decisions_20260612/shadow_residual_guard_review_decisions.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
INPUT_SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
DEFAULT_DECISION = "confirm_guard_patch_candidate"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decision(packet: dict[str, Any]) -> dict[str, Any]:
    trace = packet.get("evidence_trace") if isinstance(packet.get("evidence_trace"), dict) else {}
    return {
        "decision_id": f"shadow_residual_guard_review_decision:{packet.get('guard_review_packet_id')}",
        "guard_review_packet_id": packet.get("guard_review_packet_id"),
        "guard_plan_item_id": packet.get("guard_plan_item_id"),
        "audit_record_id": packet.get("audit_record_id"),
        "packet_id": packet.get("packet_id"),
        "work_order_id": packet.get("work_order_id"),
        "leaf_id": packet.get("leaf_id"),
        "decision": DEFAULT_DECISION,
        "decision_recorded": True,
        "reviewer_role": "ai_council_shadow_guard_reviewer",
        "reviewer_id": "codex_ai_council_shadow_guard_v1",
        "rationale": "Shadow guard review packets were generated from validated negative-evidence guard plans; keep guard candidate under review before any patch or runtime enforcement.",
        "confidence": "medium",
        "shadow_only": True,
        "human_reviewer_signoff": False,
        "governance_signoff": False,
        "evidence_trace": {
            "reason_codes": list(trace.get("reason_codes") or []),
            "source_lanes": list(trace.get("source_lanes") or []),
            "record_ids": list(trace.get("record_ids") or []),
            "field_ids": list(trace.get("field_ids") or []),
            "artifact_ids": list(trace.get("artifact_ids") or []),
            "residual_case_ids": list(trace.get("residual_case_ids") or []),
            "tasks": list(trace.get("tasks") or []),
            "guard_evidence_count": int(trace.get("guard_evidence_count") or 0),
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


def build_shadow_residual_guard_review_decisions(*, guard_review_packets: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if guard_review_packets.get("schema") != INPUT_SCHEMA:
        blockers.append(f"guard_review_packets_schema_mismatch:{guard_review_packets.get('schema')}")
    if guard_review_packets.get("verdict") != "PASS":
        blockers.append(f"guard_review_packets_failed:{guard_review_packets.get('verdict')}")

    classification = (
        guard_review_packets.get("classification") if isinstance(guard_review_packets.get("classification"), dict) else {}
    )
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("guard_review_packets_review_flags_invalid")
    if classification.get("shadow_residual_guard_review_packets") is not True:
        blockers.append("guard_review_packets_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("guard_review_packets_shadow_flag_invalid")
    if classification.get("decisions_recorded") is not False:
        blockers.append("guard_review_packets_decisions_already_recorded")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"guard_review_packets_authority_allowed:{key}")

    summary = guard_review_packets.get("summary") if isinstance(guard_review_packets.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"guard_review_packets_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("decision_count") or 0) != 0:
        blockers.append(f"guard_review_packets_decision_count_nonzero:{summary.get('decision_count')}")

    packets = (
        guard_review_packets.get("guard_review_packets")
        if isinstance(guard_review_packets.get("guard_review_packets"), list)
        else []
    )
    if int(summary.get("guard_review_packet_count") or 0) != len(packets):
        blockers.append("guard_review_packets_count_mismatch")

    decisions: list[dict[str, Any]] = []
    for packet in packets:
        if not isinstance(packet, dict):
            blockers.append("guard_review_packet_not_object")
            continue
        packet_id = packet.get("guard_review_packet_id")
        if not packet_id or not packet.get("guard_plan_item_id") or not packet.get("work_order_id") or not packet.get("leaf_id"):
            blockers.append(f"guard_review_packet_missing_join_key:{packet_id}")
        if packet.get("decision_recorded") is not False:
            blockers.append(f"guard_review_packet_decision_recorded:{packet_id}")
        if DEFAULT_DECISION not in set(packet.get("allowed_decisions") or []):
            blockers.append(f"guard_review_packet_missing_default_decision:{packet_id}")
        if packet.get("candidate_only") is not True or packet.get("review_only") is not True:
            blockers.append(f"guard_review_packet_flags_invalid:{packet_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if packet.get(key) is not False:
                blockers.append(f"guard_review_packet_authority_allowed:{packet_id}:{key}")
        decisions.append(_decision(packet))

    if blockers:
        decisions = []

    return {
        "schema": SCHEMA,
        "input_schema": guard_review_packets.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_review_decisions": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": True,
            "human_reviewer_signoff": False,
            "governance_signoff": False,
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
            "guard_review_packet_count": len(packets),
            "decision_count": len(decisions),
            "blocker_count": len(blockers),
        },
        "decisions": decisions,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_signoff",
            "governance_signoff",
            "candidate_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
            "runtime_install",
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
    parser.add_argument("--guard-review-packets", type=Path, default=DEFAULT_GUARD_REVIEW_PACKETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_shadow_residual_guard_review_decisions(guard_review_packets=_read_json(args.guard_review_packets))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
