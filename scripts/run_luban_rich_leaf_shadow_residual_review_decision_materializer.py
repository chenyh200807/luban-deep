#!/usr/bin/env python3
"""Materialize AI-council shadow decisions for RichLeaf shadow residual review packets."""
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
DEFAULT_DECISION_SEED = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_seed_20260612/shadow_residual_review_decision_seed.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decisions_20260612/ai_council_shadow_review_decisions.json"
)
SCHEMA = "luban_rich_leaf_shadow_residual_review_decisions.v1"


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


def _decision_from_seed(seed: dict[str, Any], packet: dict[str, Any], reviewer_id: str) -> dict[str, Any] | None:
    decision = seed.get("suggested_decision")
    if decision not in set(packet.get("allowed_decisions") or []):
        return None
    reason_codes = seed.get("reason_codes") if isinstance(seed.get("reason_codes"), list) else []
    rationale = (
        "AI-council shadow review accepted the seed as a review-only residual action; "
        f"scope={seed.get('review_scope')}; reason_codes={','.join(map(str, reason_codes)) or 'not_recorded'}."
    )
    return {
        "packet_id": seed.get("packet_id"),
        "decision": decision,
        "reviewer_role": "ai_council_shadow_reviewer",
        "reviewer_id": reviewer_id,
        "rationale": rationale,
        "confidence": seed.get("suggestion_confidence") if seed.get("suggestion_confidence") in {"low", "medium", "high"} else "medium",
        "decision_recorded": True,
        "shadow_only": True,
        "source_seed_id": seed.get("seed_id"),
        "work_order_id": seed.get("work_order_id"),
        "leaf_id": seed.get("leaf_id"),
        "patch_generation_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def materialize_shadow_residual_review_decisions(
    *, review_packets: dict[str, Any], decision_seed: dict[str, Any], reviewer_id: str
) -> dict[str, Any]:
    blockers: list[str] = []
    if not reviewer_id:
        blockers.append("reviewer_id_missing")
    if review_packets.get("schema") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append(f"input_review_packets_schema_mismatch:{review_packets.get('schema')}")
    if review_packets.get("verdict") != "PASS":
        blockers.append(f"input_review_packets_failed:{review_packets.get('verdict')}")
    if decision_seed.get("schema") != "luban_rich_leaf_shadow_residual_review_decision_seed.v1":
        blockers.append(f"input_decision_seed_schema_mismatch:{decision_seed.get('schema')}")
    if decision_seed.get("verdict") != "PASS":
        blockers.append(f"input_decision_seed_failed:{decision_seed.get('verdict')}")
    classification = decision_seed.get("classification") if isinstance(decision_seed.get("classification"), dict) else {}
    if classification.get("suggestion_only") is not True:
        blockers.append("input_decision_seed_not_suggestion_only")
    if classification.get("decisions_recorded") is not False:
        blockers.append("input_decision_seed_decisions_recorded")
    for key in ("patch_generation_allowed", "runtime_install_allowed", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"input_decision_seed_authority_allowed:{key}")

    packets = _packet_index(review_packets)
    decisions: list[dict[str, Any]] = []
    if not blockers:
        for seed in decision_seed.get("decision_seed_suggestions") or []:
            if not isinstance(seed, dict):
                blockers.append("decision_seed_entry_not_object")
                continue
            packet_id = str(seed.get("packet_id") or "")
            packet = packets.get(packet_id)
            if packet is None:
                blockers.append(f"decision_seed_packet_missing:{packet_id}")
                continue
            if seed.get("reviewer_must_confirm") is not True or seed.get("decision_recorded") is not False:
                blockers.append(f"decision_seed_confirmation_or_record_flag_invalid:{packet_id}")
                continue
            decision = _decision_from_seed(seed, packet, reviewer_id)
            if decision is None:
                blockers.append(f"decision_seed_suggested_decision_not_allowed:{packet_id}:{seed.get('suggested_decision')}")
                continue
            decisions.append(decision)

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "review_packets": review_packets.get("schema"),
            "decision_seed": decision_seed.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": bool(decisions),
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "packet_count": len(packets),
            "seed_suggestion_count": len(decision_seed.get("decision_seed_suggestions") or []),
            "decision_count": len(decisions),
            "blocker_count": len(blockers),
        },
        "decisions": decisions,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_signoff",
            "governance_signoff",
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
    parser.add_argument("--review-packets", type=Path, default=DEFAULT_REVIEW_PACKETS)
    parser.add_argument("--decision-seed", type=Path, default=DEFAULT_DECISION_SEED)
    parser.add_argument("--reviewer-id", default="codex_ai_council_shadow_v1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = materialize_shadow_residual_review_decisions(
        review_packets=_read_json(args.review_packets),
        decision_seed=_read_json(args.decision_seed),
        reviewer_id=args.reviewer_id,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
