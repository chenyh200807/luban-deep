#!/usr/bin/env python3
"""Merge RichLeaf evidence candidates into one review-only semantic audit queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC_PACKETS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_packets_20260612/semantic_audit_packets.json"
)
DEFAULT_SOURCE_EVIDENCE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_source_evidence_agent_20260612/source_evidence_agent_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_queue_20260612"
SCHEMA = "luban_rich_leaf_semantic_audit_queue.v1"
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


def _source_candidate_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    source_ref = packet.get("source_ref_candidate") if isinstance(packet.get("source_ref_candidate"), dict) else {}
    return {
        "source_lane": source_ref.get("source_lane"),
        "source_path": source_ref.get("path"),
        "record_id": source_ref.get("record_id"),
        "span": source_ref.get("span"),
        "span_hash": source_ref.get("span_hash"),
        "matched_terms": list(source_ref.get("matched_terms") or []),
        "score": source_ref.get("retrieval_score"),
        "support_candidate": True,
        "candidate_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
    }


def _patch_item(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_item_id": f"audit_queue:patch:{packet.get('patch_id')}",
        "audit_source_type": "patch_semantic_packet",
        "source_packet_id": packet.get("packet_id"),
        "patch_id": packet.get("patch_id"),
        "leaf_id": packet.get("leaf_id"),
        "artifact_id": packet.get("artifact_id"),
        "name_path": packet.get("name_path"),
        "missing_lane": packet.get("missing_lane"),
        "source_candidate": _source_candidate_from_packet(packet),
        "question_context": packet.get("query_context") if isinstance(packet.get("query_context"), dict) else {},
        "machine_context": packet.get("machine_precheck") if isinstance(packet.get("machine_precheck"), dict) else {},
        "question_context_candidates": [],
        "allowed_decisions": list(packet.get("allowed_decisions") or ALLOWED_DECISIONS),
        "review_status": "semantic_review_pending",
        "semantic_verdict_recorded": False,
        "candidate_only": True,
        "review_only": True,
        "apply_allowed": False,
        "runtime_install_allowed": False,
    }


def _source_item(order: dict[str, Any], candidate: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "audit_item_id": f"audit_queue:source:{order.get('artifact_id')}:{order.get('missing_lane')}:{index}",
        "audit_source_type": "source_evidence_candidate",
        "source_packet_id": None,
        "patch_id": None,
        "leaf_id": order.get("leaf_id"),
        "artifact_id": order.get("artifact_id"),
        "name_path": order.get("name_path"),
        "missing_lane": order.get("missing_lane"),
        "source_candidate": {
            "source_lane": candidate.get("source_lane"),
            "source_path": candidate.get("source_path"),
            "record_id": candidate.get("record_id"),
            "span": candidate.get("span"),
            "span_hash": candidate.get("span_hash"),
            "matched_terms": list(candidate.get("matched_terms") or []),
            "score": candidate.get("score"),
            "support_candidate": candidate.get("support_candidate") is True,
            "candidate_only": True,
            "install_allowed": False,
            "runtime_install_allowed": False,
        },
        "question_context": {},
        "machine_context": {"source_evidence_status": order.get("status")},
        "question_context_candidates": [],
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "review_status": "semantic_review_pending",
        "semantic_verdict_recorded": False,
        "candidate_only": True,
        "review_only": True,
        "apply_allowed": False,
        "runtime_install_allowed": False,
    }


def _unresolved_item(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_item_id": f"audit_queue:unresolved:{order.get('artifact_id')}:{order.get('missing_lane')}",
        "audit_source_type": "source_evidence_unresolved",
        "source_packet_id": None,
        "patch_id": None,
        "leaf_id": order.get("leaf_id"),
        "artifact_id": order.get("artifact_id"),
        "name_path": order.get("name_path"),
        "missing_lane": order.get("missing_lane"),
        "source_candidate": None,
        "question_context": {},
        "machine_context": {"source_evidence_status": order.get("status")},
        "question_context_candidates": list(order.get("question_context_candidates") or []),
        "allowed_decisions": ["needs_external_source", "needs_leaf_split_or_retaxonomy"],
        "review_status": "semantic_review_pending",
        "semantic_verdict_recorded": False,
        "candidate_only": True,
        "review_only": True,
        "apply_allowed": False,
        "runtime_install_allowed": False,
    }


def build_semantic_audit_queue_report(*, semantic_packets: dict[str, Any], source_evidence: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    packets = [packet for packet in semantic_packets.get("semantic_audit_packets") or [] if isinstance(packet, dict)]
    items.extend(_patch_item(packet) for packet in packets)

    source_candidate_count = 0
    unresolved_count = 0
    for order in source_evidence.get("source_evidence_work_orders") or []:
        if not isinstance(order, dict):
            continue
        candidates = [candidate for candidate in order.get("candidate_sources") or [] if isinstance(candidate, dict)]
        if candidates:
            for index, candidate in enumerate(candidates):
                items.append(_source_item(order, candidate, index))
                source_candidate_count += 1
        else:
            items.append(_unresolved_item(order))
            unresolved_count += 1

    return {
        "schema": SCHEMA,
        "semantic_packets_schema": semantic_packets.get("schema"),
        "source_evidence_schema": source_evidence.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "patch_semantic_packet_count": len(packets),
            "source_evidence_candidate_count": source_candidate_count,
            "source_evidence_unresolved_count": unresolved_count,
            "audit_item_count": len(items),
        },
        "semantic_audit_queue": items,
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
    parser.add_argument("--semantic-packets", type=Path, default=DEFAULT_SEMANTIC_PACKETS)
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = build_semantic_audit_queue_report(
        semantic_packets=_read_json(args.semantic_packets),
        source_evidence=_read_json(args.source_evidence),
    )
    output_path = args.output_dir / "semantic_audit_queue.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
