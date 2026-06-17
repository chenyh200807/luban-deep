#!/usr/bin/env python3
"""Render reviewer input packets from RichLeaf shadow residual work orders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SHADOW_RESIDUAL_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_work_orders_20260612/shadow_residual_work_orders.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_packets_20260612/shadow_residual_review_packets.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_review_packets.v1"
ALLOWED_DECISIONS = [
    "confirm_guard_needed",
    "request_source_ref_reaudit",
    "request_leaf_retaxonomy",
    "dismiss_after_review",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_scope(trigger_reason: str) -> str:
    if trigger_reason == "local_adapter_runtime_residual":
        return "runtime_residual_source_ref_review"
    return "preventive_negative_evidence_guard_review"


def _review_questions(trigger_reason: str) -> list[str]:
    questions = [
        "Does this work order point to the exact leaf rather than a parent or sibling topic?",
        "Do the referenced source lanes and record ids support a reusable compiler decision?",
        "Should this leaf block positive runtime context until source evidence is re-reviewed?",
    ]
    if trigger_reason == "local_adapter_runtime_residual":
        questions.insert(0, "Which source_ref or field caused the observed local-adapter residual?")
    else:
        questions.insert(0, "Is the negative evidence strong enough to keep this leaf under guard review?")
    return questions


def _packet(order: dict[str, Any]) -> dict[str, Any]:
    work_order_id = str(order.get("work_order_id") or "")
    trigger_reason = str(order.get("trigger_reason") or "")
    return {
        "packet_id": f"shadow_residual_review_packet:{work_order_id}",
        "work_order_id": work_order_id,
        "leaf_id": order.get("leaf_id"),
        "trigger_reason": trigger_reason,
        "priority": order.get("priority"),
        "review_scope": _review_scope(trigger_reason),
        "work_order_trace": {
            "artifact_ids": list(order.get("artifact_ids") or []),
            "field_ids": list(order.get("field_ids") or []),
            "families": list(order.get("families") or []),
            "tasks": list(order.get("tasks") or []),
            "residual_case_ids": list(order.get("residual_case_ids") or []),
            "reason_codes": list(order.get("reason_codes") or []),
            "guard_evidence_count": int(order.get("guard_evidence_count") or 0),
            "source_lanes": list(order.get("source_lanes") or []),
            "record_ids": list(order.get("record_ids") or []),
        },
        "review_questions": _review_questions(trigger_reason),
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "decision_recorded": False,
        "patch_generation_allowed": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "candidate_only": True,
        "review_only": True,
    }


def run_shadow_residual_review_packets(*, shadow_residual_work_orders: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if shadow_residual_work_orders.get("schema") != "luban_rich_leaf_shadow_residual_work_orders.v1":
        blockers.append(f"input_schema_mismatch:{shadow_residual_work_orders.get('schema')}")
    if shadow_residual_work_orders.get("verdict") != "PASS":
        blockers.append(f"input_shadow_residual_work_orders_failed:{shadow_residual_work_orders.get('verdict')}")
    classification = (
        shadow_residual_work_orders.get("classification")
        if isinstance(shadow_residual_work_orders.get("classification"), dict)
        else {}
    )
    if classification.get("quality_claim_allowed") is not False:
        blockers.append("input_shadow_residual_work_orders_quality_claim_allowed")

    packets: list[dict[str, Any]] = []
    for order in shadow_residual_work_orders.get("compiler_work_orders") or []:
        if not isinstance(order, dict):
            blockers.append("input_work_order_not_object")
            continue
        work_order_id = str(order.get("work_order_id") or "")
        if not work_order_id or not order.get("leaf_id"):
            blockers.append(f"input_work_order_missing_join_key:{work_order_id}")
        if order.get("candidate_only") is not True or order.get("review_only") is not True:
            blockers.append(f"input_work_order_review_flags_invalid:{work_order_id}")
        if (
            order.get("apply_allowed") is not False
            or order.get("runtime_install_allowed") is not False
            or order.get("release_truth_claimed") is not False
        ):
            blockers.append(f"input_work_order_apply_or_runtime_allowed:{work_order_id}")
        packets.append(_packet(order))

    non_joinable = [
        residual
        for residual in shadow_residual_work_orders.get("non_joinable_residuals") or []
        if isinstance(residual, dict)
    ]
    return {
        "schema": SCHEMA,
        "input_schema": shadow_residual_work_orders.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_packets": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "input_work_order_count": len(shadow_residual_work_orders.get("compiler_work_orders") or []),
            "review_packet_count": len(packets),
            "non_joinable_residual_count": len(non_joinable),
            "blocker_count": len(blockers),
        },
        "review_packets": packets,
        "non_joinable_residuals": non_joinable,
        "blockers": blockers,
        "not_exercised": [
            "semantic_decision_recording",
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
    parser.add_argument("--shadow-residual-work-orders", type=Path, default=DEFAULT_SHADOW_RESIDUAL_WORK_ORDERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_shadow_residual_review_packets(shadow_residual_work_orders=_read_json(args.shadow_residual_work_orders))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
