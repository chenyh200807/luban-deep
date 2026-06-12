#!/usr/bin/env python3
"""Build AI-council shadow review envelopes for RichLeaf manual packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_ai_council_manual_review_packets.v1"
MANUAL_SCHEMA = "luban_rich_leaf_manual_review_packets.v1"
DEFAULT_MANUAL_REVIEW_PACKETS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_manual_review_packets_20260612/manual_review_packets.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_ai_council_manual_review_packets_20260612/ai_council_manual_review_packets.json"
)
PLANNED_MEMBERS = [
    {"member_id": "codex_gpt55_architect", "provider": "openai", "model": "gpt-5.5", "role": "rubric_artifact_architect"},
    {"member_id": "opus48_arbiter", "provider": "anthropic", "model": "claude-opus-4.8", "role": "semantic_arbiter"},
    {"member_id": "fable5_defense", "provider": "fable", "model": "fable-5", "role": "defense_reviewer"},
    {"member_id": "deepseek_v4_prosecutor", "provider": "deepseek", "model": "deepseek-v4-flash", "role": "strict_prosecutor"},
    {"member_id": "qwen37_domain_reviewer", "provider": "dashscope", "model": "qwen3.7-plus", "role": "chinese_domain_reviewer"},
]
REQUIRED_CHECKS = [
    "supports_exact_leaf",
    "source_lane_matches_missing_lane",
    "span_support_level",
    "wrong_path_risk",
    "question_pollution_risk",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _classification_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != MANUAL_SCHEMA:
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


def _packet_blocker(packet: dict[str, Any]) -> str | None:
    source = packet.get("source_candidate") if isinstance(packet.get("source_candidate"), dict) else {}
    if not source.get("span_hash") or not source.get("span") or not source.get("record_id"):
        return f"manual_packet_missing_source_candidate:{packet.get('audit_item_id')}"
    if packet.get("decision_recorded") is not False:
        return f"manual_packet_decision_already_recorded:{packet.get('audit_item_id')}"
    return None


def _council_packet(packet: dict[str, Any], created_at: str) -> dict[str, Any]:
    source = packet.get("source_candidate") if isinstance(packet.get("source_candidate"), dict) else {}
    return {
        "council_review_packet_id": f"rich_leaf_ai_council_review:{packet.get('audit_item_id')}",
        "manual_review_packet_id": packet.get("manual_review_packet_id"),
        "audit_item_id": packet.get("audit_item_id"),
        "schema_version": SCHEMA,
        "created_at": created_at,
        "review_scope": "semantic_manual_review_shadow",
        "input_payload_hash": _hash(packet),
        "source_payload_hash": _hash(source),
        "manual_packet": packet,
        "planned_council_members": PLANNED_MEMBERS,
        "quorum_policy": {
            "required_member_count": 3,
            "preferred_member_count": len(PLANNED_MEMBERS),
            "consensus_threshold": 0.6,
            "tie_breaker": "opus48_arbiter_or_codex_gpt55_architect",
            "manual_override_allowed": False,
        },
        "member_output_schema": {
            "decision": packet.get("allowed_decisions") or [],
            "confidence": "number_0_to_1",
            "rationale": "short_text",
            "evidence_checks": {check: "required" for check in REQUIRED_CHECKS},
            "accepted_span_hashes": "list",
            "rejected_span_hashes": "list",
            "status": "completed_or_error",
        },
        "evidence_check_schema": {
            "required_checks": REQUIRED_CHECKS,
            "span_support_levels": ["none", "weak", "partial", "strong"],
            "risk_levels": ["none", "low", "medium", "high"],
        },
        "allowed_decisions": packet.get("allowed_decisions") or [],
        "candidate_only": True,
        "review_only": True,
        "ai_council_shadow_only": True,
        "source_ref_mutation_allowed": False,
        "patch_generation_allowed": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def build_ai_council_manual_review_packets(*, manual_review_packets: dict[str, Any]) -> dict[str, Any]:
    blockers = _classification_blockers(manual_review_packets)
    packets = [
        packet
        for packet in manual_review_packets.get("manual_review_packets") or []
        if isinstance(packet, dict)
    ]
    for packet in packets:
        blocker = _packet_blocker(packet)
        if blocker:
            blockers.append(blocker)
    created_at = datetime.now(timezone.utc).isoformat()
    council_packets = [] if blockers else [_council_packet(packet, created_at) for packet in packets]
    return {
        "schema": SCHEMA,
        "input_schema": manual_review_packets.get("schema"),
        "verdict": "FAIL" if blockers else "READY_FOR_AI_COUNCIL_SHADOW_REVIEW",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "ai_council_shadow_only": True,
            "decisions_recorded": False,
            "source_ref_mutation_allowed": False,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "official_score_allowed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "manual_review_packet_count": len(packets),
            "council_review_packet_count": len(council_packets),
            "planned_member_count": len(PLANNED_MEMBERS),
            "blocker_count": len(blockers),
        },
        "council_review_packets": council_packets,
        "blockers": blockers,
        "not_exercised": [
            "provider_invocation",
            "member_vote_recording",
            "consensus_decision",
            "source_ref_acceptance",
            "runtime_supply_mutation",
            "production_default",
            "release_truth_governance",
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_ai_council_manual_review_packets(manual_review_packets=_read_json(args.manual_review_packets))
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "READY_FOR_AI_COUNCIL_SHADOW_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
