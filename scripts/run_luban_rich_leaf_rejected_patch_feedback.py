#!/usr/bin/env python3
"""Create review-only feedback work orders from rejected RichLeaf patch audits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PATCH_AUDIT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_patch_evidence_audit_20260611/patch_evidence_audit.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_rejected_patch_feedback_20260612"
SCHEMA = "luban_rich_leaf_rejected_patch_feedback.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _feedback_codes(reason_codes: list[str]) -> list[str]:
    codes: list[str] = []
    if "option_marker_only_match" in reason_codes:
        codes.append("option_marker_pollution")
    if "no_name_path_specific_term_in_span" in reason_codes:
        codes.append("wrong_leaf_source")
    if "span_hash_mismatch" in reason_codes:
        codes.append("source_trace_hash_invalid")
    if "practice_or_question_source_pollution" in reason_codes:
        codes.append("source_lane_pollution")
    if "source_lane_missing_lane_mismatch" in reason_codes:
        codes.append("source_lane_mismatch")
    return codes or ["rejected_patch_needs_source_research"]


def _next_action(feedback_codes: list[str]) -> str:
    if "option_marker_pollution" in feedback_codes:
        return "rerun_source_search_with_non_option_specific_leaf_terms"
    if "wrong_leaf_source" in feedback_codes:
        return "rerun_source_search_with_leaf_path_terms"
    if "source_trace_hash_invalid" in feedback_codes:
        return "reextract_source_span_and_hash"
    if "source_lane_pollution" in feedback_codes:
        return "exclude_polluted_source_and_search_authority_lane"
    if "source_lane_mismatch" in feedback_codes:
        return "rerun_source_search_for_missing_lane"
    return "manual_source_evidence_review_required"


def _work_order(audit: dict[str, Any]) -> dict[str, Any]:
    reason_codes = [str(reason) for reason in audit.get("reason_codes") or []]
    feedback_codes = _feedback_codes(reason_codes)
    return {
        "patch_id": audit.get("patch_id"),
        "artifact_id": audit.get("artifact_id"),
        "leaf_id": audit.get("leaf_id"),
        "name_path": audit.get("name_path"),
        "missing_lane": audit.get("missing_lane"),
        "source_lane": audit.get("source_lane"),
        "record_id": audit.get("record_id"),
        "path": audit.get("path"),
        "status": "rejected_patch_feedback",
        "reason_codes": reason_codes,
        "feedback_codes": feedback_codes,
        "matched_terms": list(audit.get("matched_terms") or []),
        "next_action": _next_action(feedback_codes),
        "source_ref_candidate_reusable": False,
        "promotion_allowed": False,
        "runtime_install_allowed": False,
    }


def build_rejected_patch_feedback_report(*, patch_audit_report: dict[str, Any]) -> dict[str, Any]:
    rejected = [
        audit
        for audit in patch_audit_report.get("patch_audits") or []
        if isinstance(audit, dict) and audit.get("audit_decision") == "machine_reject"
    ]
    work_orders = [_work_order(audit) for audit in rejected]
    return {
        "schema": SCHEMA,
        "source_patch_audit_schema": patch_audit_report.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "work_orders_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "rejected_patch_count": len(rejected),
            "work_order_count": len(work_orders),
            "option_marker_pollution_count": sum(
                1 for order in work_orders if "option_marker_pollution" in order["feedback_codes"]
            ),
            "wrong_leaf_source_count": sum(1 for order in work_orders if "wrong_leaf_source" in order["feedback_codes"]),
        },
        "rejected_patch_work_orders": work_orders,
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
    parser.add_argument("--patch-audit", type=Path, default=DEFAULT_PATCH_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    patch_audit_report = _read_json(args.patch_audit)
    report = build_rejected_patch_feedback_report(patch_audit_report=patch_audit_report)
    output_path = args.output_dir / "rejected_patch_feedback_work_orders.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
