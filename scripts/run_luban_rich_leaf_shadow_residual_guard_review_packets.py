#!/usr/bin/env python3
"""Build review-only guard review packets from RichLeaf shadow residual guard patch plans."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_GUARD_PATCH_PLAN = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_patch_plan_20260612/shadow_residual_guard_patch_plan.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_packets_20260612/shadow_residual_guard_review_packets.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_guard_review_packets.v1"
INPUT_SCHEMA = "luban_rich_leaf_shadow_residual_guard_patch_plan.v1"
ALLOWED_DECISIONS = [
    "confirm_guard_patch_candidate",
    "request_guard_scope_narrowing",
    "request_source_ref_reaudit",
    "reject_guard_not_needed",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _packet(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "guard_review_packet_id": f"shadow_residual_guard_review_packet:{item.get('guard_plan_item_id')}",
        "guard_plan_item_id": item.get("guard_plan_item_id"),
        "audit_record_id": item.get("audit_record_id"),
        "packet_id": item.get("packet_id"),
        "work_order_id": item.get("work_order_id"),
        "leaf_id": item.get("leaf_id"),
        "review_scope": "runtime_guard_candidate_review",
        "planned_guard_action": item.get("planned_guard_action"),
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "review_questions": [
            "Does the cited negative evidence justify blocking positive runtime context for this leaf until source_ref review?",
            "Is the guard scope limited to the listed source lanes, records, fields, artifacts, and tasks?",
            "Should this packet move to source_ref reaudit instead of guard patch review?",
        ],
        "evidence_trace": {
            "reason_codes": list(item.get("reason_codes") or []),
            "source_lanes": list(item.get("source_lanes") or []),
            "record_ids": list(item.get("record_ids") or []),
            "field_ids": list(item.get("field_ids") or []),
            "artifact_ids": list(item.get("artifact_ids") or []),
            "residual_case_ids": list(item.get("residual_case_ids") or []),
            "tasks": list(item.get("tasks") or []),
            "guard_evidence_count": int(item.get("guard_evidence_count") or 0),
        },
        "decision_recorded": False,
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


def build_shadow_residual_guard_review_packets(*, guard_patch_plan: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if guard_patch_plan.get("schema") != INPUT_SCHEMA:
        blockers.append(f"guard_patch_plan_schema_mismatch:{guard_patch_plan.get('schema')}")
    if guard_patch_plan.get("verdict") != "PASS":
        blockers.append(f"guard_patch_plan_failed:{guard_patch_plan.get('verdict')}")

    classification = guard_patch_plan.get("classification") if isinstance(guard_patch_plan.get("classification"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("guard_patch_plan_review_flags_invalid")
    if classification.get("shadow_residual_guard_patch_plan") is not True:
        blockers.append("guard_patch_plan_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("guard_patch_plan_shadow_flag_invalid")
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
            blockers.append(f"guard_patch_plan_authority_allowed:{key}")

    summary = guard_patch_plan.get("summary") if isinstance(guard_patch_plan.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"guard_patch_plan_blockers_present:{summary.get('blocker_count')}")

    items = guard_patch_plan.get("guard_plan_items") if isinstance(guard_patch_plan.get("guard_plan_items"), list) else []
    if int(summary.get("guard_plan_item_count") or 0) != len(items):
        blockers.append("guard_patch_plan_item_count_mismatch")

    packets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            blockers.append("guard_plan_item_not_object")
            continue
        item_id = item.get("guard_plan_item_id")
        if not item_id or not item.get("audit_record_id") or not item.get("work_order_id") or not item.get("leaf_id"):
            blockers.append(f"guard_plan_item_missing_join_key:{item_id}")
        if item.get("planned_guard_action") != "block_positive_context_until_source_ref_reviewed":
            blockers.append(f"guard_plan_item_unknown_action:{item_id}:{item.get('planned_guard_action')}")
        if item.get("plan_status") != "review_required":
            blockers.append(f"guard_plan_item_status_invalid:{item_id}:{item.get('plan_status')}")
        if item.get("candidate_only") is not True or item.get("review_only") is not True:
            blockers.append(f"guard_plan_item_flags_invalid:{item_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if item.get(key) is not False:
                blockers.append(f"guard_plan_item_authority_allowed:{item_id}:{key}")
        packets.append(_packet(item))

    if blockers:
        packets = []

    return {
        "schema": SCHEMA,
        "input_schema": guard_patch_plan.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_review_packets": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": False,
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
            "guard_plan_item_count": len(items),
            "guard_review_packet_count": len(packets),
            "decision_count": 0,
            "blocker_count": len(blockers),
        },
        "guard_review_packets": packets,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_decision",
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
    parser.add_argument("--guard-patch-plan", type=Path, default=DEFAULT_GUARD_PATCH_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_shadow_residual_guard_review_packets(guard_patch_plan=_read_json(args.guard_patch_plan))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
