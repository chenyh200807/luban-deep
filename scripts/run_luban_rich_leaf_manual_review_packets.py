#!/usr/bin/env python3
"""Build review-only packets for RichLeaf semantic manual-review items."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SUGGESTIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_review_suggestions_20260612/semantic_review_suggestions.json"
)
DEFAULT_SEMANTIC_QUEUE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_audit_queue_20260612/semantic_audit_queue.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_manual_review_packets_20260612/manual_review_packets.json"
)
SCHEMA = "luban_rich_leaf_manual_review_packets.v1"
SUGGESTIONS_SCHEMA = "luban_rich_leaf_semantic_review_suggestions.v1"
SEMANTIC_QUEUE_SCHEMA = "luban_rich_leaf_semantic_audit_queue.v1"
ALLOWED_DECISIONS = [
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _queue_index(semantic_queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = semantic_queue.get("semantic_audit_queue")
    if not isinstance(rows, list):
        rows = semantic_queue.get("audit_items") or []
    return {
        str(item.get("audit_item_id")): item
        for item in rows
        if isinstance(item, dict) and item.get("audit_item_id")
    }


def _classification_blocks(suggestions: dict[str, Any], semantic_queue: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if suggestions.get("schema") != SUGGESTIONS_SCHEMA:
        blockers.append(f"suggestions_schema_mismatch:{suggestions.get('schema')}")
    if semantic_queue.get("schema") != SEMANTIC_QUEUE_SCHEMA:
        blockers.append(f"semantic_queue_schema_mismatch:{semantic_queue.get('schema')}")
    suggestions_classification = suggestions.get("classification") if isinstance(suggestions.get("classification"), dict) else {}
    if suggestions_classification.get("suggestion_only") is not True:
        blockers.append("suggestions_not_suggestion_only")
    if suggestions_classification.get("decisions_recorded") is not False:
        blockers.append("suggestions_decisions_already_recorded")
    for key in ("runtime_install_allowed", "release_truth_claimed"):
        if suggestions_classification.get(key) is not False:
            blockers.append(f"suggestions_authority_allowed:{key}")
    queue_classification = semantic_queue.get("classification") if isinstance(semantic_queue.get("classification"), dict) else {}
    queue_safety = semantic_queue.get("safety") if isinstance(semantic_queue.get("safety"), dict) else {}
    if queue_classification.get("runtime_install_allowed") is not False:
        blockers.append("semantic_queue_runtime_install_allowed_not_false")
    release_truth_claimed = (
        queue_classification["release_truth_claimed"]
        if "release_truth_claimed" in queue_classification
        else queue_safety.get("release_truth_claimed")
    )
    if release_truth_claimed is not False:
        blockers.append("semantic_queue_release_truth_claimed_not_false")
    return blockers


def _packet(suggestion: dict[str, Any], queue_item: dict[str, Any] | None) -> dict[str, Any]:
    source_candidate = queue_item.get("source_candidate") if isinstance(queue_item, dict) else None
    if not isinstance(source_candidate, dict):
        source_candidate = {}
    return {
        "manual_review_packet_id": f"rich_leaf_manual_review_packet:{suggestion.get('audit_item_id')}",
        "audit_item_id": suggestion.get("audit_item_id"),
        "audit_source_type": suggestion.get("audit_source_type"),
        "leaf_id": suggestion.get("leaf_id"),
        "artifact_id": suggestion.get("artifact_id"),
        "missing_lane": suggestion.get("missing_lane"),
        "terminal_leaf": suggestion.get("terminal_leaf"),
        "suggestion_confidence": suggestion.get("suggestion_confidence"),
        "reason_codes": list(suggestion.get("reason_codes") or []),
        "source_candidate": {
            "source_lane": source_candidate.get("source_lane"),
            "source_path": source_candidate.get("source_path"),
            "record_id": source_candidate.get("record_id"),
            "span": source_candidate.get("span"),
            "span_hash": source_candidate.get("span_hash"),
            "matched_terms": list(source_candidate.get("matched_terms") or []),
        },
        "review_questions": [
            "Does the cited span semantically support the terminal leaf, not merely share a word?",
            "Does the source lane match the missing lane authority?",
            "Would accepting this source ref introduce question-bank or wrong-path pollution?",
            "Should this remain external_source_required or require retaxonomy?",
        ],
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "decision_recorded": False,
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def build_manual_review_packets(*, suggestions: dict[str, Any], semantic_queue: dict[str, Any]) -> dict[str, Any]:
    blockers = _classification_blocks(suggestions, semantic_queue)
    queue_by_id = _queue_index(semantic_queue)
    manual_suggestions = [
        item
        for item in suggestions.get("suggestions") or []
        if isinstance(item, dict) and item.get("suggested_decision") == "manual_review_required"
    ]
    packets = [_packet(suggestion, queue_by_id.get(str(suggestion.get("audit_item_id")))) for suggestion in manual_suggestions]
    lane_counts = Counter(str(packet.get("missing_lane") or "unknown") for packet in packets)
    source_type_counts = Counter(str(packet.get("audit_source_type") or "unknown") for packet in packets)
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "suggestions": suggestions.get("schema"),
            "semantic_queue": semantic_queue.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "manual_review_packets": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "suggestion_count": len(suggestions.get("suggestions") or []),
            "manual_review_packet_count": len(packets),
            "decision_count": 0,
            "blocker_count": len(blockers),
            "by_missing_lane": dict(sorted(lane_counts.items())),
            "by_audit_source_type": dict(sorted(source_type_counts.items())),
        },
        "manual_review_packets": packets,
        "blockers": blockers,
        "not_exercised": [
            "manual_reviewer_decision",
            "governance_signoff",
            "source_ref_acceptance",
            "runtime_supply_mutation",
            "production_default",
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
    parser.add_argument("--suggestions", type=Path, default=DEFAULT_SUGGESTIONS)
    parser.add_argument("--semantic-queue", type=Path, default=DEFAULT_SEMANTIC_QUEUE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_manual_review_packets(
        suggestions=_read_json(args.suggestions),
        semantic_queue=_read_json(args.semantic_queue),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
