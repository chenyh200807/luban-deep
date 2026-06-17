#!/usr/bin/env python3
"""Build review-only audit records from validated RichLeaf guard review decisions."""
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
DEFAULT_GUARD_REVIEW_DECISIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decisions_20260612/shadow_residual_guard_review_decisions.json"
)
DEFAULT_VALIDATION_REPORT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decision_validation_20260612/shadow_residual_guard_review_decision_validation.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_audit_record_20260612/shadow_residual_guard_audit_record.json"
)

SCHEMA = "luban_rich_leaf_shadow_residual_guard_audit_record.v1"
PACKETS_SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
DECISIONS_SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_decisions.v1"
VALIDATION_SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1"

ALLOWED_DECISIONS = {
    "confirm_guard_patch_candidate",
    "request_guard_scope_narrowing",
    "request_source_ref_reaudit",
    "reject_guard_not_needed",
}
ACTION_BY_DECISION = {
    "confirm_guard_patch_candidate": "guard_patch_candidate_review_required",
    "request_guard_scope_narrowing": "guard_scope_narrowing_required",
    "request_source_ref_reaudit": "source_ref_reaudit_required",
    "reject_guard_not_needed": "dismissed_after_guard_review",
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


def _trace(payload: dict[str, Any]) -> dict[str, Any]:
    trace = payload.get("evidence_trace") if isinstance(payload.get("evidence_trace"), dict) else {}
    return {
        "reason_codes": list(trace.get("reason_codes") or []),
        "source_lanes": list(trace.get("source_lanes") or []),
        "record_ids": list(trace.get("record_ids") or []),
        "field_ids": list(trace.get("field_ids") or []),
        "artifact_ids": list(trace.get("artifact_ids") or []),
        "residual_case_ids": list(trace.get("residual_case_ids") or []),
        "tasks": list(trace.get("tasks") or []),
        "guard_evidence_count": int(trace.get("guard_evidence_count") or 0),
    }


def _check_common_authority(
    payload: dict[str, Any],
    blockers: list[str],
    *,
    label: str,
    marker_key: str | None = None,
    require_shadow: bool = False,
    forbid_decisions_recorded: bool | None = None,
) -> None:
    classification = _classification(payload)
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append(f"{label}_review_flags_invalid")
    if marker_key and classification.get(marker_key) is not True:
        blockers.append(f"{label}_classification_invalid")
    if require_shadow and classification.get("ai_council_shadow_only") is not True:
        blockers.append(f"{label}_shadow_flag_invalid")
    if forbid_decisions_recorded is not None and classification.get("decisions_recorded") is not forbid_decisions_recorded:
        blockers.append(f"{label}_decisions_recorded_invalid")
    if classification.get("human_reviewer_signoff") not in (None, False):
        blockers.append(f"{label}_human_signoff_claimed")
    if classification.get("governance_signoff") not in (None, False):
        blockers.append(f"{label}_governance_signoff_claimed")
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
            blockers.append(f"{label}_authority_allowed:{key}")


def _check_validation(validation_report: dict[str, Any], blockers: list[str]) -> None:
    if validation_report.get("schema") != VALIDATION_SCHEMA:
        blockers.append(f"validation_schema_mismatch:{validation_report.get('schema')}")
    if validation_report.get("input_schema") != PACKETS_SCHEMA:
        blockers.append(f"validation_input_schema_mismatch:{validation_report.get('input_schema')}")
    if validation_report.get("verdict") != "PASS":
        blockers.append(f"validation_not_pass:{validation_report.get('verdict')}")
    _check_common_authority(
        validation_report,
        blockers,
        label="validation",
        marker_key="shadow_residual_guard_review_decision_validation",
    )
    summary = _summary(validation_report)
    for key in (
        "missing_decision_count",
        "invalid_decision_count",
        "duplicate_decision_count",
        "stale_decision_count",
        "blocker_count",
    ):
        count = int(summary.get(key) or 0)
        if count != 0:
            blockers.append(f"validation_{key}:{count}")


def _packet_map(guard_review_packets: dict[str, Any], blockers: list[str]) -> dict[str, dict[str, Any]]:
    if guard_review_packets.get("schema") != PACKETS_SCHEMA:
        blockers.append(f"guard_review_packets_schema_mismatch:{guard_review_packets.get('schema')}")
    if guard_review_packets.get("verdict") != "PASS":
        blockers.append(f"guard_review_packets_not_pass:{guard_review_packets.get('verdict')}")
    _check_common_authority(
        guard_review_packets,
        blockers,
        label="guard_review_packets",
        marker_key="shadow_residual_guard_review_packets",
        require_shadow=True,
        forbid_decisions_recorded=False,
    )
    summary = _summary(guard_review_packets)
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"guard_review_packets_blockers_present:{summary.get('blocker_count')}")
    packets = (
        guard_review_packets.get("guard_review_packets")
        if isinstance(guard_review_packets.get("guard_review_packets"), list)
        else []
    )
    if int(summary.get("guard_review_packet_count") or 0) != len(packets):
        blockers.append("guard_review_packets_count_mismatch")

    result: dict[str, dict[str, Any]] = {}
    for packet in packets:
        if not isinstance(packet, dict):
            blockers.append("guard_review_packet_not_object")
            continue
        packet_id = packet.get("guard_review_packet_id")
        if not packet_id:
            blockers.append("guard_review_packet_missing_id")
            continue
        if packet_id in result:
            blockers.append(f"guard_review_packet_duplicate:{packet_id}")
        result[str(packet_id)] = packet
        if not packet.get("guard_plan_item_id") or not packet.get("work_order_id") or not packet.get("leaf_id"):
            blockers.append(f"guard_review_packet_missing_join_key:{packet_id}")
        if packet.get("decision_recorded") is not False:
            blockers.append(f"guard_review_packet_decision_recorded:{packet_id}")
        if packet.get("candidate_only") is not True or packet.get("review_only") is not True:
            blockers.append(f"guard_review_packet_review_flags_invalid:{packet_id}")
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
    return result


def _decisions(guard_review_decisions: dict[str, Any], blockers: list[str]) -> list[dict[str, Any]]:
    if guard_review_decisions.get("schema") != DECISIONS_SCHEMA:
        blockers.append(f"guard_review_decisions_schema_mismatch:{guard_review_decisions.get('schema')}")
    if guard_review_decisions.get("input_schema") != PACKETS_SCHEMA:
        blockers.append(f"guard_review_decisions_input_schema_mismatch:{guard_review_decisions.get('input_schema')}")
    if guard_review_decisions.get("verdict") != "PASS":
        blockers.append(f"guard_review_decisions_not_pass:{guard_review_decisions.get('verdict')}")
    _check_common_authority(
        guard_review_decisions,
        blockers,
        label="guard_review_decisions",
        marker_key="shadow_residual_guard_review_decisions",
        require_shadow=True,
        forbid_decisions_recorded=True,
    )
    summary = _summary(guard_review_decisions)
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"guard_review_decisions_blockers_present:{summary.get('blocker_count')}")
    decisions = guard_review_decisions.get("decisions") if isinstance(guard_review_decisions.get("decisions"), list) else []
    if int(summary.get("decision_count") or 0) != len(decisions):
        blockers.append("guard_review_decisions_count_mismatch")
    return [decision for decision in decisions if isinstance(decision, dict)]


def _check_decision(
    decision: dict[str, Any], packet_by_id: dict[str, dict[str, Any]], blockers: list[str]
) -> None:
    decision_id = decision.get("decision_id")
    packet_id = decision.get("guard_review_packet_id")
    if not decision_id:
        blockers.append("decision_missing_id")
        return
    if not packet_id or packet_id not in packet_by_id:
        blockers.append(f"decision_packet_missing:{decision_id}:{packet_id}")
        return
    packet = packet_by_id[str(packet_id)]
    for key in ("guard_plan_item_id", "audit_record_id", "packet_id", "work_order_id", "leaf_id"):
        if decision.get(key) != packet.get(key):
            blockers.append(f"decision_packet_join_mismatch:{decision_id}:{key}")
    if decision.get("decision") not in ALLOWED_DECISIONS:
        blockers.append(f"decision_unknown:{decision_id}:{decision.get('decision')}")
    if decision.get("decision") not in set(packet.get("allowed_decisions") or []):
        blockers.append(f"decision_not_allowed_by_packet:{decision_id}:{decision.get('decision')}")
    if decision.get("decision_recorded") is not True or decision.get("shadow_only") is not True:
        blockers.append(f"decision_flags_invalid:{decision_id}")
    if decision.get("candidate_only") is not True or decision.get("review_only") is not True:
        blockers.append(f"decision_review_flags_invalid:{decision_id}")
    if decision.get("human_reviewer_signoff") is not False or decision.get("governance_signoff") is not False:
        blockers.append(f"decision_signoff_claimed:{decision_id}")
    trace = _trace(decision)
    if not trace["reason_codes"] or not trace["source_lanes"] or not trace["record_ids"]:
        blockers.append(f"decision_trace_missing:{decision_id}")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if decision.get(key) is not False:
            blockers.append(f"decision_authority_allowed:{decision_id}:{key}")


def _audit_record(decision: dict[str, Any]) -> dict[str, Any]:
    decision_value = str(decision.get("decision"))
    return {
        "guard_audit_record_id": f"shadow_residual_guard_audit_record:{decision.get('guard_review_packet_id')}",
        "guard_review_packet_id": decision.get("guard_review_packet_id"),
        "guard_plan_item_id": decision.get("guard_plan_item_id"),
        "upstream_audit_record_id": decision.get("audit_record_id"),
        "packet_id": decision.get("packet_id"),
        "work_order_id": decision.get("work_order_id"),
        "leaf_id": decision.get("leaf_id"),
        "decision_id": decision.get("decision_id"),
        "decision": decision_value,
        "next_compiler_action": ACTION_BY_DECISION[decision_value],
        "review_authority": {
            "reviewer_role": decision.get("reviewer_role"),
            "reviewer_id": decision.get("reviewer_id"),
            "confidence": decision.get("confidence"),
            "shadow_only": True,
            "human_reviewer_signoff": False,
            "governance_signoff": False,
        },
        "evidence_trace": _trace(decision),
        "candidate_only": True,
        "review_only": True,
        "shadow_only": True,
        "patch_generation_allowed": False,
        "source_ref_mutation_allowed": False,
        "runtime_install_allowed": False,
        "runtime_guard_enforcement_allowed": False,
        "release_truth_claimed": False,
        "quality_claim_allowed": False,
        "learner_memory_write_allowed": False,
    }


def build_shadow_residual_guard_audit_record(
    *,
    guard_review_packets: dict[str, Any],
    guard_review_decisions: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    _check_validation(validation_report, blockers)
    packet_by_id = _packet_map(guard_review_packets, blockers)
    decisions = _decisions(guard_review_decisions, blockers)

    validation_summary = _summary(validation_report)
    if int(validation_summary.get("guard_review_packet_count") or 0) != len(packet_by_id):
        blockers.append("validation_packet_count_mismatch")
    if int(validation_summary.get("decision_count") or 0) != len(decisions):
        blockers.append("validation_decision_count_mismatch")

    decision_packet_ids: set[str] = set()
    for decision in decisions:
        packet_id = decision.get("guard_review_packet_id")
        if packet_id in decision_packet_ids:
            blockers.append(f"decision_duplicate_packet:{packet_id}")
        decision_packet_ids.add(str(packet_id))
        _check_decision(decision, packet_by_id, blockers)
    missing_packet_ids = sorted(set(packet_by_id) - decision_packet_ids)
    if missing_packet_ids:
        blockers.append(f"decision_missing_packets:{','.join(missing_packet_ids)}")

    records: list[dict[str, Any]] = []
    if not blockers:
        records = [_audit_record(decision) for decision in decisions]

    counts = {decision: 0 for decision in ALLOWED_DECISIONS}
    for decision in decisions:
        value = decision.get("decision")
        if value in counts:
            counts[str(value)] += 1

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "guard_review_packets": guard_review_packets.get("schema"),
            "guard_review_decisions": guard_review_decisions.get("schema"),
            "guard_review_decision_validation": validation_report.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_audit_record": True,
            "ai_council_shadow_only": True,
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
            "guard_review_packet_count": len(packet_by_id),
            "decision_count": len(decisions),
            "audit_record_count": len(records),
            "confirm_guard_patch_candidate_count": counts["confirm_guard_patch_candidate"],
            "request_guard_scope_narrowing_count": counts["request_guard_scope_narrowing"],
            "request_source_ref_reaudit_count": counts["request_source_ref_reaudit"],
            "reject_guard_not_needed_count": counts["reject_guard_not_needed"],
            "blocker_count": len(blockers),
        },
        "shadow_residual_guard_audit_records": records,
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
    parser.add_argument("--guard-review-decisions", type=Path, default=DEFAULT_GUARD_REVIEW_DECISIONS)
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_shadow_residual_guard_audit_record(
        guard_review_packets=_read_json(args.guard_review_packets),
        guard_review_decisions=_read_json(args.guard_review_decisions),
        validation_report=_read_json(args.validation_report),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
