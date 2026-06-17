#!/usr/bin/env python3
"""Materialize fail-closed shadow decisions for RichLeaf manual review packets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANUAL_REVIEW_PACKETS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_manual_review_packets_20260612/manual_review_packets.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_review_decisions_materialized_20260612/codex_manual_shadow_review_decisions.json"
)
SCHEMA = "luban_rich_leaf_semantic_audit_decisions.v1"
MANUAL_PACKETS_SCHEMA = "luban_rich_leaf_manual_review_packets.v1"
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


def _classification_blockers(payload: dict[str, Any], reviewer_id: str) -> list[str]:
    blockers: list[str] = []
    if not reviewer_id:
        blockers.append("reviewer_id_missing")
    if payload.get("schema") != MANUAL_PACKETS_SCHEMA:
        blockers.append(f"manual_packets_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"manual_packets_not_pass:{payload.get('verdict')}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("decisions_recorded") is not False:
        blockers.append("manual_packets_decisions_already_recorded")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"manual_packets_authority_allowed:{key}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append("manual_packets_production_write_count_nonzero")
    if safety.get("release_truth_claimed") is not False:
        blockers.append("manual_packets_release_truth_claimed")
    return blockers


def _has_traceable_source(source: dict[str, Any]) -> bool:
    return bool(source.get("record_id") and source.get("span") and source.get("span_hash"))


def _decision_for_packet(packet: dict[str, Any]) -> tuple[str, str, str]:
    source = packet.get("source_candidate") if isinstance(packet.get("source_candidate"), dict) else {}
    missing_lane = str(packet.get("missing_lane") or "")
    source_lane = str(source.get("source_lane") or "")
    if not _has_traceable_source(source):
        return (
            "needs_external_source",
            "high",
            "Manual review packet has no traceable candidate span, record_id, and span_hash; fail-closed to stronger source search.",
        )
    if source_lane != missing_lane:
        return (
            "reject_wrong_leaf_source",
            "high",
            f"Source lane {source_lane!r} does not match missing authority lane {missing_lane!r}; fail-closed against source-lane pollution.",
        )
    return (
        "needs_external_source",
        "low",
        "Manual review packet was created because deterministic semantic support was insufficient; fail-closed and require stronger evidence before acceptance.",
    )


def _decision(packet: dict[str, Any], reviewer_id: str) -> dict[str, Any]:
    decision, confidence, rationale = _decision_for_packet(packet)
    if decision not in set(packet.get("allowed_decisions") or []) & ALLOWED_DECISIONS:
        decision = "needs_external_source"
        confidence = "low"
        rationale = "Allowed decision set did not include the preferred fail-closed decision; requiring external source evidence."
    source = packet.get("source_candidate") if isinstance(packet.get("source_candidate"), dict) else {}
    return {
        "audit_item_id": packet.get("audit_item_id"),
        "decision": decision,
        "reviewer_role": "codex_manual_shadow_fail_closed_reviewer",
        "reviewer_id": reviewer_id,
        "rationale": rationale,
        "confidence": confidence,
        "decision_recorded": True,
        "shadow_only": True,
        "candidate_only": True,
        "manual_shadow_review_only": True,
        "leaf_id": packet.get("leaf_id"),
        "artifact_id": packet.get("artifact_id"),
        "missing_lane": packet.get("missing_lane"),
        "source_suggestion": {
            "manual_review_packet_id": packet.get("manual_review_packet_id"),
            "reason_codes": list(packet.get("reason_codes") or []),
            "source_lane": source.get("source_lane"),
            "span_hash": source.get("span_hash"),
        },
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def materialize_manual_review_shadow_decisions(
    *, manual_review_packets: dict[str, Any], reviewer_id: str
) -> dict[str, Any]:
    blockers = _classification_blockers(manual_review_packets, reviewer_id)
    packets = [
        packet
        for packet in manual_review_packets.get("manual_review_packets") or []
        if isinstance(packet, dict)
    ]
    decisions = [] if blockers else [_decision(packet, reviewer_id) for packet in packets]
    accepted_count = sum(1 for decision in decisions if decision.get("decision") == "accept_source_ref_candidate")
    return {
        "schema": SCHEMA,
        "input_schema": manual_review_packets.get("schema"),
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "manual_shadow_review_only": True,
            "decisions_recorded": bool(decisions),
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "manual_review_packet_count": len(packets),
            "decision_count": len(decisions),
            "accepted_source_ref_count": accepted_count,
            "blocker_count": len(blockers),
        },
        "decisions": decisions,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_signoff",
            "multi_provider_council_quorum",
            "governance_signoff",
            "runtime_supply_install",
            "production_default",
            "canonical_truth_write",
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
    parser.add_argument("--manual-review-packets", type=Path, default=DEFAULT_MANUAL_REVIEW_PACKETS)
    parser.add_argument("--reviewer-id", default="codex_manual_shadow_fail_closed_v1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = materialize_manual_review_shadow_decisions(
        manual_review_packets=_read_json(args.manual_review_packets),
        reviewer_id=args.reviewer_id,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["blocker_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
