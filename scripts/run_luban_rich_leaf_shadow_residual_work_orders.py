#!/usr/bin/env python3
"""Turn near-live shadow residuals into review-only RichLeaf compiler work orders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_NEAR_LIVE_SHADOW_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_shadow_ab_20260612/near_live_shadow_ab.json"
)
DEFAULT_FAIL_OPEN_GUARD_DIAGNOSTIC = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_fail_open_guard_diagnostic_20260612/fail_open_guard_diagnostic.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_work_orders_20260612/shadow_residual_work_orders.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_work_orders.v1"
LOCAL_ADAPTER_ARM = "rich_leaf_local_adapter"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_runtime_residual(row: dict[str, Any]) -> bool:
    return bool(
        row.get("fail_open")
        or not row.get("answerable")
        or int(row.get("question_lane_citation_count") or 0) > 0
        or not row.get("term_hit", True)
    )


def _runtime_reason_codes(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("fail_open"):
        reasons.append("fail_open")
    if not row.get("answerable"):
        reasons.append("not_answerable")
    if int(row.get("question_lane_citation_count") or 0) > 0:
        reasons.append("question_lane_citation")
    if not row.get("term_hit", True):
        reasons.append("term_miss")
    return reasons


def _work_order_base(*, leaf_id: str, trigger_reason: str, priority: str) -> dict[str, Any]:
    return {
        "work_order_id": "",
        "leaf_id": leaf_id,
        "trigger_reason": trigger_reason,
        "priority": priority,
        "action": "review_source_refs_and_pack_guard_for_leaf",
        "candidate_only": True,
        "review_only": True,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def run_shadow_residual_work_orders(
    *, near_live_shadow_ab: dict[str, Any], fail_open_guard_diagnostic: dict[str, Any]
) -> dict[str, Any]:
    blockers: list[str] = []
    if near_live_shadow_ab.get("schema") != "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1":
        blockers.append(f"input_schema_mismatch:near_live_shadow_ab:{near_live_shadow_ab.get('schema')}")
    if fail_open_guard_diagnostic.get("schema") != "luban_rich_leaf_fail_open_guard_diagnostic.v1":
        blockers.append(f"input_schema_mismatch:fail_open_guard_diagnostic:{fail_open_guard_diagnostic.get('schema')}")
    if near_live_shadow_ab.get("verdict") != "PASS":
        blockers.append(f"input_near_live_shadow_ab_failed:{near_live_shadow_ab.get('verdict')}")
    if fail_open_guard_diagnostic.get("verdict") != "PASS":
        blockers.append(f"input_fail_open_guard_diagnostic_failed:{fail_open_guard_diagnostic.get('verdict')}")
    if near_live_shadow_ab.get("quality_claim_allowed") is not False:
        blockers.append("input_near_live_shadow_quality_claim_allowed")
    guard_classification = (
        fail_open_guard_diagnostic.get("classification")
        if isinstance(fail_open_guard_diagnostic.get("classification"), dict)
        else {}
    )
    if guard_classification.get("quality_claim_allowed") is not False:
        blockers.append("input_fail_open_guard_quality_claim_allowed")

    orders_by_leaf: dict[str, dict[str, Any]] = {}
    non_joinable_residuals: list[dict[str, Any]] = []
    runtime_residual_count = 0

    for row in near_live_shadow_ab.get("sample_rows") or []:
        if isinstance(row, dict) and _is_runtime_residual(row):
            non_joinable_residuals.append(
                {
                    "arm": row.get("arm"),
                    "case_id": row.get("case_id"),
                    "reason_codes": _runtime_reason_codes(row),
                    "join_blocker": "missing_leaf_id",
                }
            )

    for row in near_live_shadow_ab.get("local_adapter_rows") or []:
        if not isinstance(row, dict) or row.get("arm") != LOCAL_ADAPTER_ARM or not _is_runtime_residual(row):
            continue
        leaf_id = str(row.get("leaf_id") or "")
        if not leaf_id:
            non_joinable_residuals.append(
                {
                    "arm": row.get("arm"),
                    "case_id": row.get("case_id"),
                    "reason_codes": _runtime_reason_codes(row),
                    "join_blocker": "missing_leaf_id",
                }
            )
            continue
        runtime_residual_count += 1
        order = orders_by_leaf.setdefault(
            leaf_id,
            {
                **_work_order_base(leaf_id=leaf_id, trigger_reason="local_adapter_runtime_residual", priority="high"),
                "artifact_ids": [],
                "field_ids": [],
                "families": [],
                "tasks": [],
                "residual_case_ids": [],
                "reason_codes": [],
                "guard_evidence_count": 0,
                "source_lanes": [],
                "record_ids": [],
            },
        )
        for key, value_key in (("artifact_ids", "artifact_id"), ("field_ids", "field_id"), ("families", "family"), ("tasks", "task")):
            value = row.get(value_key)
            if value and str(value) not in order[key]:
                order[key].append(str(value))
        case_id = row.get("case_id")
        if case_id and str(case_id) not in order["residual_case_ids"]:
            order["residual_case_ids"].append(str(case_id))
        for reason in _runtime_reason_codes(row):
            if reason not in order["reason_codes"]:
                order["reason_codes"].append(reason)

    guard_review_order_count = 0
    for diagnostic in fail_open_guard_diagnostic.get("leaf_diagnostics") or []:
        if not isinstance(diagnostic, dict):
            continue
        leaf_id = str(diagnostic.get("leaf_id") or "")
        if not leaf_id:
            continue
        evidence_count = int(diagnostic.get("negative_evidence_count") or 0)
        if evidence_count <= 0:
            continue
        order = orders_by_leaf.get(leaf_id)
        if order is None:
            guard_review_order_count += 1
            order = {
                **_work_order_base(
                    leaf_id=leaf_id,
                    trigger_reason="preventive_negative_evidence_guard_review",
                    priority="medium",
                ),
                "artifact_ids": [],
                "field_ids": [],
                "families": [],
                "tasks": [],
                "residual_case_ids": [],
                "reason_codes": ["negative_evidence_guard_review"],
                "guard_evidence_count": evidence_count,
                "source_lanes": [],
                "record_ids": [],
            }
            orders_by_leaf[leaf_id] = order
        else:
            order["guard_evidence_count"] = evidence_count
            if "negative_evidence_guard_review" not in order["reason_codes"]:
                order["reason_codes"].append("negative_evidence_guard_review")
        for key in ("artifact_ids", "field_ids", "source_lanes", "record_ids"):
            for value in diagnostic.get(key) or []:
                if value and str(value) not in order[key]:
                    order[key].append(str(value))

    compiler_work_orders = sorted(orders_by_leaf.values(), key=lambda item: (item["priority"] != "high", item["leaf_id"]))
    for index, order in enumerate(compiler_work_orders, start=1):
        order["work_order_id"] = f"rich_leaf_shadow_residual_work_order_{index:04d}"
        for key in ("artifact_ids", "field_ids", "families", "tasks", "residual_case_ids", "reason_codes", "source_lanes", "record_ids"):
            order[key] = sorted(set(order[key]))

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "near_live_shadow_ab": near_live_shadow_ab.get("schema"),
            "fail_open_guard_diagnostic": fail_open_guard_diagnostic.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_work_orders": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "runtime_residual_case_count": runtime_residual_count,
            "runtime_residual_work_order_count": sum(
                1 for order in compiler_work_orders if order["trigger_reason"] == "local_adapter_runtime_residual"
            ),
            "guard_review_work_order_count": guard_review_order_count,
            "non_joinable_residual_count": len(non_joinable_residuals),
            "work_order_count": len(compiler_work_orders),
            "blocker_count": len(blockers),
        },
        "compiler_work_orders": compiler_work_orders,
        "non_joinable_residuals": non_joinable_residuals,
        "blockers": blockers,
        "not_exercised": [
            "compiler_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
            "quality_claim",
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
    parser.add_argument("--near-live-shadow-ab", type=Path, default=DEFAULT_NEAR_LIVE_SHADOW_AB)
    parser.add_argument("--fail-open-guard-diagnostic", type=Path, default=DEFAULT_FAIL_OPEN_GUARD_DIAGNOSTIC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_shadow_residual_work_orders(
        near_live_shadow_ab=_read_json(args.near_live_shadow_ab),
        fail_open_guard_diagnostic=_read_json(args.fail_open_guard_diagnostic),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
