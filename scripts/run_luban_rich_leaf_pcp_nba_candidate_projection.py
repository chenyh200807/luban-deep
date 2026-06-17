#!/usr/bin/env python3
"""Dry-run project RichLeaf learning-evidence candidates toward PCP/NBA shapes.

This runner deliberately stops before real Learning Brain readback: it does not
write learner memory, synthesize canonical truth, create training_intent, or
produce an authoritative NextBestAction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json"
)
SCHEMA = "luban_rich_leaf_pcp_nba_candidate_projection.v1"
INPUT_SCHEMA = "luban_rich_leaf_learning_evidence_candidate_bridge.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _bridge_blocks(payload: dict[str, Any], blockers: list[str]) -> None:
    if payload.get("schema") != INPUT_SCHEMA:
        blockers.append(f"learning_evidence_bridge_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"learning_evidence_bridge_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("learning_evidence_bridge_quality_claim_allowed")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"learning_evidence_bridge_authority_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("learning_evidence_bridge_review_flags_invalid")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed", "canonical_learner_truth_written"):
        if safety.get(key) is not False:
            blockers.append(f"learning_evidence_bridge_safety_{key}")
    if safety.get("learner_memory_write_count") not in (0, False):
        blockers.append("learning_evidence_bridge_learner_memory_write_count")
    if safety.get("production_write_count") not in (0, False):
        blockers.append("learning_evidence_bridge_production_write_count")


def _event_blockers(event: dict[str, Any]) -> list[str]:
    event_id = str(event.get("candidate_event_id") or "unknown")
    blockers: list[str] = []
    if event.get("event_type") != "learning_evidence" or event.get("memory_kind") != "learning_evidence":
        blockers.append(f"candidate_event_bad_semantics:{event_id}")
    if event.get("candidate_only") is not True or event.get("preview_only") is not True:
        blockers.append(f"candidate_event_not_preview_candidate:{event_id}")
    for key in ("claim_promotion_allowed", "mastery_raised", "canonical_truth_written"):
        if event.get(key) is not False:
            blockers.append(f"candidate_event_{key}:{event_id}")
    quality = event.get("quality") if isinstance(event.get("quality"), dict) else {}
    for key in ("writeback_eligible", "progress_countable", "truth_eligible", "stable_truth_eligible"):
        if quality.get(key) is not False:
            blockers.append(f"candidate_event_quality_{key}:{event_id}")
    trace = event.get("rich_leaf_trace") if isinstance(event.get("rich_leaf_trace"), dict) else {}
    for key in ("case_id", "task", "artifact_id", "leaf_id", "field_id", "family"):
        if not str(trace.get(key) or "").strip():
            blockers.append(f"candidate_event_missing_trace_{key}:{event_id}")
    if not trace.get("cited_source_ref_ids"):
        blockers.append(f"candidate_event_missing_cited_source_refs:{event_id}")
    return blockers


def _claim_candidates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for event in events:
        trace = event.get("rich_leaf_trace") if isinstance(event.get("rich_leaf_trace"), dict) else {}
        leaf_id = str(trace.get("leaf_id") or "")
        field_id = str(trace.get("field_id") or "")
        claim_key = f"{leaf_id}:{field_id}"
        event_id = str(event.get("candidate_event_id") or "")
        claim = claims.setdefault(
            claim_key,
            {
                "claim_id": _stable_id("rich_leaf_claim_candidate", {"leaf_id": leaf_id, "field_id": field_id}),
                "claim_status": "candidate_preview",
                "candidate_only": True,
                "truth_eligible": False,
                "concept_id": leaf_id,
                "label": f"{leaf_id}/{field_id}",
                "artifact_id": str(trace.get("artifact_id") or ""),
                "field_id": field_id,
                "family": str(trace.get("family") or ""),
                "evidence_refs": [],
                "source_ref_ids": [],
            },
        )
        if event_id:
            claim["evidence_refs"].append(event_id)
        claim["source_ref_ids"].extend(str(ref_id) for ref_id in trace.get("cited_source_ref_ids") or [] if str(ref_id))
    for claim in claims.values():
        claim["evidence_refs"] = sorted(set(claim["evidence_refs"]))
        claim["source_ref_ids"] = sorted(set(claim["source_ref_ids"]))
    return sorted(claims.values(), key=lambda item: item["claim_id"])


def _next_action_candidates(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, claim in enumerate(claims[:3], 1):
        actions.append(
            {
                "action_id": _stable_id("rich_leaf_next_action_candidate", {"claim_id": claim.get("claim_id")}),
                "candidate_only": True,
                "source": "rich_leaf_pcp_nba_candidate_projection",
                "prescription_authority": "not_exercised_training_intent",
                "status": "candidate_not_prescription",
                "rank": index,
                "personalization_level": "generic_candidate",
                "target": str(claim.get("label") or "review_required"),
                "evidence_refs": list(claim.get("evidence_refs") or []),
                "retest_target": None,
            }
        )
    return actions


def run_pcp_nba_candidate_projection(*, learning_evidence_candidate_bridge: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    _bridge_blocks(learning_evidence_candidate_bridge, blockers)
    raw_events = [
        event
        for event in learning_evidence_candidate_bridge.get("learning_evidence_event_candidates") or []
        if isinstance(event, dict)
    ]
    if not raw_events:
        blockers.append("no_learning_evidence_event_candidates")
    valid_events: list[dict[str, Any]] = []
    for event in raw_events:
        event_blockers = _event_blockers(event)
        blockers.extend(event_blockers)
        if not event_blockers:
            valid_events.append(event)

    claim_candidates = _claim_candidates(valid_events)
    next_actions = _next_action_candidates(claim_candidates)
    pcp_candidate = {
        "schema_version": 1,
        "source": "PersonalizationContextPackCandidate",
        "candidate_only": True,
        "readback_verified": False,
        "personalization_level": "generic_candidate",
        "authority": {
            "evidence": "learning_evidence_candidate_bridge",
            "claims": "candidate_projection_not_learning_synthesis",
            "prescription": "not_exercised_training_intent",
        },
        "top_claim_candidates": claim_candidates[:5],
        "next_action_candidates": next_actions,
    }
    return {
        "schema": SCHEMA,
        "input_schema": learning_evidence_candidate_bridge.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_candidate_projection",
        "summary": {
            "blocker_count": len(blockers),
            "candidate_event_count": len(raw_events),
            "valid_candidate_event_count": len(valid_events),
            "top_claim_candidate_count": len(claim_candidates),
            "next_action_candidate_count": len(next_actions),
            "learner_memory_write_count": 0,
            "pcp_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
            "provider_call_count": 0,
        },
        "personalization_context_pack_candidate": pcp_candidate,
        "next_action_candidates": next_actions,
        "blockers": blockers,
        "not_exercised_by_layer": {
            "memory_not_exercised": [
                "learner_memory_db_write",
                "canonical_learner_truth_write",
            ],
            "learning_brain_not_exercised": [
                "learning_synthesis",
                "personalization_context_pack_readback",
                "training_intent_creation",
                "next_best_action_generation",
                "retest_delta",
            ],
            "release_not_exercised": ["governance_signoff", "production_default_decision"],
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "pcp_nba_candidate_projection": True,
            "learner_memory_write_allowed": False,
            "personalization_context_pack_readback_allowed": False,
            "next_best_action_write_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-evidence-candidate-bridge", type=Path, default=DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_pcp_nba_candidate_projection(
        learning_evidence_candidate_bridge=_read_json(args.learning_evidence_candidate_bridge)
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
