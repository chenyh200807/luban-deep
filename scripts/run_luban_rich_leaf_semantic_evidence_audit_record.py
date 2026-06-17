#!/usr/bin/env python3
"""Create review-only semantic evidence audit records from a RichLeaf audit queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC_QUEUE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_queue_20260612/semantic_audit_queue.json"
)
DEFAULT_DECISIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decision_validation_20260612/merged_semantic_audit_decisions.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612"
SCHEMA = "luban_rich_leaf_semantic_evidence_audit_record.v1"
ALLOWED_DECISIONS = {
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decision_index(decisions: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not decisions:
        return {}, []
    indexed: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, Any]] = []
    for decision in decisions.get("decisions") or []:
        if not isinstance(decision, dict):
            invalid.append({"reason": "decision_not_object", "decision": decision})
            continue
        audit_item_id = decision.get("audit_item_id")
        decision_value = decision.get("decision")
        if not audit_item_id or decision_value not in ALLOWED_DECISIONS:
            invalid.append({"reason": "invalid_decision_or_missing_audit_item_id", "decision": decision})
            continue
        indexed[str(audit_item_id)] = decision
    return indexed, invalid


def _not_exercised_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_item_id": item.get("audit_item_id"),
        "audit_source_type": item.get("audit_source_type"),
        "leaf_id": item.get("leaf_id"),
        "artifact_id": item.get("artifact_id"),
        "missing_lane": item.get("missing_lane"),
        "review_decision_status": "not_exercised",
        "decision": None,
        "reviewer_role": None,
        "reviewer_id": None,
        "rationale": None,
        "confidence": None,
        "source_candidate": item.get("source_candidate"),
        "question_context_candidates": list(item.get("question_context_candidates") or []),
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def _recorded_decision(item: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        **_not_exercised_record(item),
        "review_decision_status": "recorded",
        "decision": decision.get("decision"),
        "reviewer_role": decision.get("reviewer_role"),
        "reviewer_id": decision.get("reviewer_id"),
        "rationale": decision.get("rationale"),
        "confidence": decision.get("confidence"),
    }


def build_semantic_evidence_audit_record_report(
    *, semantic_queue: dict[str, Any], decisions: dict[str, Any] | None
) -> dict[str, Any]:
    decision_by_id, invalid_decisions = _decision_index(decisions)
    queue_items = [item for item in semantic_queue.get("semantic_audit_queue") or [] if isinstance(item, dict)]
    queue_ids = {str(item.get("audit_item_id")) for item in queue_items if item.get("audit_item_id")}
    orphan_decisions = [
        {"reason": "audit_item_id_not_in_queue", "decision": decision}
        for audit_item_id, decision in decision_by_id.items()
        if audit_item_id not in queue_ids
    ]
    invalid_decisions.extend(orphan_decisions)
    records = [
        _recorded_decision(item, decision_by_id[str(item.get("audit_item_id"))])
        if str(item.get("audit_item_id")) in decision_by_id and str(item.get("audit_item_id")) in queue_ids
        else _not_exercised_record(item)
        for item in queue_items
    ]
    decision_record_count = sum(1 for record in records if record["review_decision_status"] == "recorded")
    return {
        "schema": SCHEMA,
        "semantic_queue_schema": semantic_queue.get("schema"),
        "decision_schema": decisions.get("schema") if isinstance(decisions, dict) else None,
        "classification": {
            "review_only": True,
            "semantic_verdict_recorded": decision_record_count > 0,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_item_count": len(queue_items),
            "decision_record_count": decision_record_count,
            "not_exercised_count": len(queue_items) - decision_record_count,
            "invalid_decision_count": len(invalid_decisions),
        },
        "invalid_decisions": invalid_decisions,
        "semantic_evidence_audit_records": records,
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
    parser.add_argument("--semantic-queue", type=Path, default=DEFAULT_SEMANTIC_QUEUE)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--no-decisions", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    decisions = None if args.no_decisions else _read_json(args.decisions)
    report = build_semantic_evidence_audit_record_report(
        semantic_queue=_read_json(args.semantic_queue),
        decisions=decisions,
    )
    output_path = args.output_dir / "semantic_evidence_audit_record.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["invalid_decision_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
