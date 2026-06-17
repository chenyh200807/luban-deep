#!/usr/bin/env python3
"""Validate RichLeaf shadow residual review decisions before any patch generation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_packets_20260612/shadow_residual_review_packets.json"
)
DEFAULT_DECISIONS_DIR = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decisions_20260612"
)
DEFAULT_OUTPUT_DIR = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_validation_20260612"
)
SCHEMA = "luban_rich_leaf_shadow_residual_review_decision_validation.v1"
DECISION_SCHEMA = "luban_rich_leaf_shadow_residual_review_decisions.v1"
CONFIDENCE_VALUES = {"low", "medium", "high"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decision_payloads_from_dir(decisions_dir: Path) -> list[dict[str, Any]]:
    if not decisions_dir.exists():
        return []
    return [_read_json(path) for path in sorted(decisions_dir.glob("*.json")) if path.is_file()]


def _packet_index(review_packets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(packet.get("packet_id")): packet
        for packet in review_packets.get("review_packets") or []
        if isinstance(packet, dict) and packet.get("packet_id")
    }


def _is_valid_decision(decision: dict[str, Any], packet: dict[str, Any]) -> bool:
    required = ["packet_id", "decision", "reviewer_role", "reviewer_id", "rationale", "confidence"]
    if any(not decision.get(key) for key in required):
        return False
    if decision.get("decision") not in set(packet.get("allowed_decisions") or []):
        return False
    if decision.get("confidence") not in CONFIDENCE_VALUES:
        return False
    for key in ("patch_generation_allowed", "runtime_install_allowed", "release_truth_claimed"):
        if decision.get(key) is not False:
            return False
    if decision.get("decision_recorded") is not True:
        return False
    return True


def validate_shadow_residual_review_decisions(
    *, review_packets: dict[str, Any], decision_payloads: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    blockers: list[str] = []
    if review_packets.get("schema") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append(f"input_schema_mismatch:{review_packets.get('schema')}")
    if review_packets.get("verdict") != "PASS":
        blockers.append(f"input_review_packets_failed:{review_packets.get('verdict')}")

    packets = _packet_index(review_packets)
    seen: set[str] = set()
    valid_decisions: list[dict[str, Any]] = []
    invalid_decisions: list[dict[str, Any]] = []
    duplicate_decisions: list[dict[str, Any]] = []
    stale_decisions: list[dict[str, Any]] = []

    for payload in decision_payloads:
        if payload.get("schema") != DECISION_SCHEMA:
            invalid_decisions.append({"reason": "schema_mismatch", "payload_schema": payload.get("schema")})
            continue
        for decision in payload.get("decisions") or []:
            if not isinstance(decision, dict):
                invalid_decisions.append({"reason": "decision_not_object", "decision": decision})
                continue
            packet_id = str(decision.get("packet_id") or "")
            packet = packets.get(packet_id)
            if packet is None:
                stale_decisions.append(decision)
                continue
            if not _is_valid_decision(decision, packet):
                invalid_decisions.append(decision)
                continue
            if packet_id in seen:
                duplicate_decisions.append(decision)
                continue
            seen.add(packet_id)
            valid_decisions.append(decision)

    missing_packet_ids = sorted(set(packets) - seen)
    verdict = "PASS"
    if blockers or invalid_decisions or duplicate_decisions:
        verdict = "FAIL"
    elif missing_packet_ids:
        verdict = "INCOMPLETE"

    report = {
        "schema": SCHEMA,
        "input_schema": review_packets.get("schema"),
        "verdict": verdict,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_decision_validation": True,
            "decisions_recorded": bool(valid_decisions),
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": len(packets),
            "decision_count": len(valid_decisions),
            "missing_decision_count": len(missing_packet_ids),
            "invalid_decision_count": len(invalid_decisions),
            "duplicate_decision_count": len(duplicate_decisions),
            "stale_decision_count": len(stale_decisions),
            "blocker_count": len(blockers),
        },
        "missing_packet_ids": missing_packet_ids,
        "invalid_decisions": invalid_decisions,
        "duplicate_decisions": duplicate_decisions,
        "stale_decisions_ignored": stale_decisions,
        "blockers": blockers,
        "not_exercised": [
            "audit_record_ingestion",
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
    merged = {
        "schema": DECISION_SCHEMA,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
            "patch_generation_allowed": False,
        },
        "decisions": valid_decisions,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }
    return report, merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-packets", type=Path, default=DEFAULT_REVIEW_PACKETS)
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report, merged = validate_shadow_residual_review_decisions(
        review_packets=_read_json(args.review_packets),
        decision_payloads=_decision_payloads_from_dir(args.decisions_dir),
    )
    _write_json(args.output_dir / "shadow_residual_review_decision_validation.json", report)
    _write_json(args.output_dir / "merged_shadow_residual_review_decisions.json", merged)
    print(json.dumps({"out": str(args.output_dir), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
