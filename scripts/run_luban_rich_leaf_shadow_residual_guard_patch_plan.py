#!/usr/bin/env python3
"""Build review-only guard patch plan items from RichLeaf shadow residual audit records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_audit_record_20260612/shadow_residual_audit_record.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_patch_plan_20260612/shadow_residual_guard_patch_plan.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_guard_patch_plan.v1"
INPUT_SCHEMA = "luban_rich_leaf_shadow_residual_audit_record.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _trace(record: dict[str, Any]) -> dict[str, Any]:
    trace = record.get("work_order_trace") if isinstance(record.get("work_order_trace"), dict) else {}
    return {
        "artifact_ids": list(trace.get("artifact_ids") or []),
        "field_ids": list(trace.get("field_ids") or []),
        "record_ids": list(trace.get("record_ids") or []),
        "source_lanes": list(trace.get("source_lanes") or []),
        "reason_codes": list(trace.get("reason_codes") or []),
        "guard_evidence_count": int(trace.get("guard_evidence_count") or 0),
        "residual_case_ids": list(trace.get("residual_case_ids") or []),
        "tasks": list(trace.get("tasks") or []),
    }


def _plan_item(record: dict[str, Any]) -> dict[str, Any]:
    trace = _trace(record)
    return {
        "guard_plan_item_id": f"shadow_residual_guard_plan:{record.get('audit_record_id')}",
        "audit_record_id": record.get("audit_record_id"),
        "packet_id": record.get("packet_id"),
        "work_order_id": record.get("work_order_id"),
        "leaf_id": record.get("leaf_id"),
        "planned_guard_action": "block_positive_context_until_source_ref_reviewed",
        "plan_status": "review_required",
        "action_source": "shadow_residual_audit_record",
        "reason_codes": trace["reason_codes"],
        "source_lanes": trace["source_lanes"],
        "record_ids": trace["record_ids"],
        "field_ids": trace["field_ids"],
        "artifact_ids": trace["artifact_ids"],
        "residual_case_ids": trace["residual_case_ids"],
        "tasks": trace["tasks"],
        "guard_evidence_count": trace["guard_evidence_count"],
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


def build_shadow_residual_guard_patch_plan(*, audit_record: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if audit_record.get("schema") != INPUT_SCHEMA:
        blockers.append(f"audit_record_schema_mismatch:{audit_record.get('schema')}")
    if audit_record.get("verdict") != "PASS":
        blockers.append(f"audit_record_failed:{audit_record.get('verdict')}")

    classification = audit_record.get("classification") if isinstance(audit_record.get("classification"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("audit_record_review_flags_invalid")
    if classification.get("shadow_residual_audit_record") is not True:
        blockers.append("audit_record_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("audit_record_shadow_flag_invalid")
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
            blockers.append(f"audit_record_authority_allowed:{key}")

    summary = audit_record.get("summary") if isinstance(audit_record.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"audit_record_blockers_present:{summary.get('blocker_count')}")

    records = (
        audit_record.get("shadow_residual_audit_records")
        if isinstance(audit_record.get("shadow_residual_audit_records"), list)
        else []
    )
    if int(summary.get("audit_record_count") or 0) != len(records):
        blockers.append("audit_record_count_mismatch")

    plan_items: list[dict[str, Any]] = []
    source_ref_reaudit_count = 0
    leaf_retaxonomy_count = 0
    dismissed_count = 0
    for record in records:
        if not isinstance(record, dict):
            blockers.append("audit_record_entry_not_object")
            continue
        record_id = record.get("audit_record_id")
        if not record_id or not record.get("packet_id") or not record.get("work_order_id") or not record.get("leaf_id"):
            blockers.append(f"audit_record_missing_join_key:{record_id}")
        if record.get("candidate_only") is not True or record.get("review_only") is not True or record.get("shadow_only") is not True:
            blockers.append(f"audit_record_entry_flags_invalid:{record_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if record.get(key) is not False:
                blockers.append(f"audit_record_entry_authority_allowed:{record_id}:{key}")
        action = record.get("next_compiler_action")
        if action == "guard_review_required":
            plan_items.append(_plan_item(record))
        elif action == "source_ref_reaudit_required":
            source_ref_reaudit_count += 1
        elif action == "leaf_retaxonomy_required":
            leaf_retaxonomy_count += 1
        elif action == "dismissed_after_shadow_review":
            dismissed_count += 1
        else:
            blockers.append(f"audit_record_unknown_action:{record_id}:{action}")

    if blockers:
        plan_items = []

    return {
        "schema": SCHEMA,
        "input_schema": audit_record.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_guard_patch_plan": True,
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
            "audit_record_count": len(records),
            "guard_plan_item_count": len(plan_items),
            "source_ref_reaudit_required_count": source_ref_reaudit_count,
            "leaf_retaxonomy_required_count": leaf_retaxonomy_count,
            "dismissed_after_shadow_review_count": dismissed_count,
            "blocker_count": len(blockers),
        },
        "guard_plan_items": plan_items,
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
    parser.add_argument("--audit-record", type=Path, default=DEFAULT_AUDIT_RECORD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_shadow_residual_guard_patch_plan(audit_record=_read_json(args.audit_record))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
