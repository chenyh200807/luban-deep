#!/usr/bin/env python3
"""Build suggestion-only decision seeds for RichLeaf shadow residual review packets."""
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
DEFAULT_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_validation_20260612/shadow_residual_review_decision_validation.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_seed_20260612/shadow_residual_review_decision_seed.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_review_decision_seed.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _packet_index(review_packets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(packet.get("packet_id")): packet
        for packet in review_packets.get("review_packets") or []
        if isinstance(packet, dict) and packet.get("packet_id")
    }


def _suggested_decision(packet: dict[str, Any]) -> str:
    if packet.get("review_scope") == "runtime_residual_source_ref_review":
        return "request_source_ref_reaudit"
    if int((packet.get("work_order_trace") or {}).get("guard_evidence_count") or 0) > 0:
        return "confirm_guard_needed"
    allowed = set(packet.get("allowed_decisions") or [])
    if "confirm_guard_needed" in allowed:
        return "confirm_guard_needed"
    if "request_source_ref_reaudit" in allowed:
        return "request_source_ref_reaudit"
    return "dismiss_after_review"


def _seed_for(packet: dict[str, Any]) -> dict[str, Any]:
    suggested = _suggested_decision(packet)
    allowed = set(packet.get("allowed_decisions") or [])
    if suggested not in allowed and allowed:
        suggested = sorted(allowed)[0]
    return {
        "seed_id": f"shadow_residual_review_decision_seed:{packet.get('packet_id')}",
        "packet_id": packet.get("packet_id"),
        "work_order_id": packet.get("work_order_id"),
        "leaf_id": packet.get("leaf_id"),
        "review_scope": packet.get("review_scope"),
        "suggested_decision": suggested,
        "suggestion_confidence": "medium",
        "reason_codes": list((packet.get("work_order_trace") or {}).get("reason_codes") or []),
        "reviewer_must_confirm": True,
        "decision_recorded": False,
        "patch_generation_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "candidate_only": True,
        "review_only": True,
    }


def run_shadow_residual_review_decision_seed(
    *, review_packets: dict[str, Any], decision_validation: dict[str, Any]
) -> dict[str, Any]:
    blockers: list[str] = []
    if review_packets.get("schema") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append(f"input_review_packets_schema_mismatch:{review_packets.get('schema')}")
    if review_packets.get("verdict") != "PASS":
        blockers.append(f"input_review_packets_failed:{review_packets.get('verdict')}")
    if decision_validation.get("schema") != "luban_rich_leaf_shadow_residual_review_decision_validation.v1":
        blockers.append(f"input_decision_validation_schema_mismatch:{decision_validation.get('schema')}")
    if decision_validation.get("verdict") not in {"PASS", "INCOMPLETE"}:
        blockers.append(f"input_decision_validation_bad_verdict:{decision_validation.get('verdict')}")
    classification = (
        decision_validation.get("classification")
        if isinstance(decision_validation.get("classification"), dict)
        else {}
    )
    if classification.get("patch_generation_allowed") is not False:
        blockers.append("input_decision_validation_patch_generation_allowed")
    if classification.get("quality_claim_allowed") is not False:
        blockers.append("input_decision_validation_quality_claim_allowed")

    packets = _packet_index(review_packets)
    missing_ids = [str(packet_id) for packet_id in decision_validation.get("missing_packet_ids") or []]
    seeds = [_seed_for(packets[packet_id]) for packet_id in missing_ids if packet_id in packets]
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "review_packets": review_packets.get("schema"),
            "decision_validation": decision_validation.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_review_decision_seed": True,
            "suggestion_only": True,
            "decisions_recorded": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": len(packets),
            "missing_packet_count": len(missing_ids),
            "seed_suggestion_count": len(seeds),
            "blocker_count": len(blockers),
        },
        "decision_seed_suggestions": seeds,
        "blockers": blockers,
        "not_exercised": [
            "decision_recording",
            "decision_validation_replay",
            "candidate_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
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
    parser.add_argument("--review-packets", type=Path, default=DEFAULT_REVIEW_PACKETS)
    parser.add_argument("--decision-validation", type=Path, default=DEFAULT_DECISION_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_shadow_residual_review_decision_seed(
        review_packets=_read_json(args.review_packets),
        decision_validation=_read_json(args.decision_validation),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
