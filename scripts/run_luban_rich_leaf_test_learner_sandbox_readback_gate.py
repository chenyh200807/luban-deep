#!/usr/bin/env python3
"""Artifact-only sandbox readback gate for RichLeaf learning evidence candidates.

The gate writes a local sandbox JSONL artifact and reads it back into the
LearnerStateEvent shape to prove candidate evidence remains excluded from
Learning Brain synthesis. It never calls LearnerStateService.append_memory_event
and never writes production/canonical learner memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json"
)
DEFAULT_PCP_NBA_CANDIDATE_PROJECTION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json"
)
DEFAULT_SANDBOX_EVENTS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/sandbox_memory_events.jsonl"
)
SCHEMA = "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
BRIDGE_SCHEMA = "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
PROJECTION_SCHEMA = "luban_rich_leaf_pcp_nba_candidate_projection.v1"


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


def _bridge_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != BRIDGE_SCHEMA:
        blockers.append(f"bridge_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"bridge_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("bridge_quality_claim_allowed")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if safety.get("learner_memory_write_count") not in (0, False):
        blockers.append("bridge_learner_memory_write_count")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("bridge_canonical_learner_truth_written")
    return blockers


def _projection_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != PROJECTION_SCHEMA:
        blockers.append(f"pcp_projection_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "PASS":
        blockers.append(f"pcp_projection_not_pass:{payload.get('verdict')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("pcp_projection_quality_claim_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for key in ("learner_memory_write_count", "pcp_readback_count", "training_intent_write_count", "next_best_action_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"pcp_projection_summary_{key}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("learner_memory_write_allowed", "personalization_context_pack_readback_allowed", "next_best_action_write_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"pcp_projection_classification_{key}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"pcp_projection_safety_{key}")
    return blockers


def _candidate_event_blockers(event: dict[str, Any]) -> list[str]:
    event_id = str(event.get("candidate_event_id") or "unknown")
    blockers: list[str] = []
    if event.get("event_type") != "learning_evidence" or event.get("memory_kind") != "learning_evidence":
        blockers.append(f"candidate_event_bad_semantics:{event_id}")
    if event.get("candidate_only") is not True or event.get("preview_only") is not True:
        blockers.append(f"candidate_event_not_preview_candidate:{event_id}")
    if event.get("claim_promotion_allowed") is not False:
        blockers.append(f"candidate_event_claim_promotion_allowed:{event_id}")
    quality = event.get("quality") if isinstance(event.get("quality"), dict) else {}
    for key in ("writeback_eligible", "progress_countable", "truth_eligible", "stable_truth_eligible"):
        if quality.get(key) is not False:
            blockers.append(f"candidate_event_quality_{key}:{event_id}")
    return blockers


def _sandbox_row(event: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    event_id = str(event.get("candidate_event_id") or _stable_id("sandbox_event", event))
    payload_json = dict(event)
    return {
        "event_id": event_id,
        "user_id": user_id,
        "source_feature": "rich_leaf_shadow_candidate",
        "source_id": str(event.get("question_id") or event_id),
        "source_bot_id": "construction-exam-sandbox",
        "memory_kind": "learning_evidence",
        "payload_json": payload_json,
        "dedupe_key": _stable_id("rich_leaf_sandbox_dedupe", {"user_id": user_id, "event_id": event_id}),
        "created_at": "2026-06-12T00:00:00+08:00",
    }


def _event_from_row(row: dict[str, Any]) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=str(row.get("event_id") or ""),
        user_id=str(row.get("user_id") or ""),
        source_feature=str(row.get("source_feature") or ""),
        source_id=str(row.get("source_id") or ""),
        source_bot_id=str(row.get("source_bot_id") or "") or None,
        memory_kind=str(row.get("memory_kind") or ""),
        payload_json=dict(row.get("payload_json") or {}),
        dedupe_key=str(row.get("dedupe_key") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _write_sandbox_events(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_sandbox_events(path: Path) -> list[LearnerStateEvent]:
    events: list[LearnerStateEvent] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if isinstance(row, dict):
            events.append(_event_from_row(row))
    return events


def run_test_learner_sandbox_readback_gate(
    *,
    learning_evidence_candidate_bridge: dict[str, Any],
    pcp_nba_candidate_projection: dict[str, Any],
    sandbox_events: Path | None = None,
    sandbox_user_id: str = "rich_leaf_sandbox_learner",
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_bridge_blockers(learning_evidence_candidate_bridge))
    blockers.extend(_projection_blockers(pcp_nba_candidate_projection))
    raw_events = [
        event
        for event in learning_evidence_candidate_bridge.get("learning_evidence_event_candidates") or []
        if isinstance(event, dict)
    ]
    if not raw_events:
        blockers.append("no_candidate_events")
    valid_events: list[dict[str, Any]] = []
    for event in raw_events:
        event_blockers = _candidate_event_blockers(event)
        blockers.extend(event_blockers)
        if not event_blockers:
            valid_events.append(event)

    sandbox_rows: list[dict[str, Any]] = []
    readback_events: list[LearnerStateEvent] = []
    synthesis = {"projection": {"observed_candidates": [], "compiled_objects": {}}}
    if not blockers:
        sandbox_rows = [_sandbox_row(event, user_id=sandbox_user_id) for event in valid_events]
        if sandbox_events is not None:
            _write_sandbox_events(sandbox_events, sandbox_rows)
            readback_events = _read_sandbox_events(sandbox_events)
        else:
            readback_events = [_event_from_row(row) for row in sandbox_rows]
        synthesis = synthesize_learning_truth(readback_events, synthesis_status="sandbox_dry_run")

    projection = synthesis.get("projection") if isinstance(synthesis.get("projection"), dict) else {}
    observed = projection.get("observed_candidates") if isinstance(projection.get("observed_candidates"), list) else []
    compiled = projection.get("compiled_objects") if isinstance(projection.get("compiled_objects"), dict) else {}
    if observed:
        blockers.append("sandbox_candidate_leaked_into_observed_candidates")
    if compiled:
        blockers.append("sandbox_candidate_leaked_into_compiled_objects")

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "learning_evidence_candidate_bridge": learning_evidence_candidate_bridge.get("schema"),
            "pcp_nba_candidate_projection": pcp_nba_candidate_projection.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "artifact_only_sandbox_readback",
        "sandbox": {
            "sandbox_user_id": sandbox_user_id,
            "sandbox_events_path": str(sandbox_events) if sandbox_events is not None else "",
            "write_scope": "artifact_only",
        },
        "summary": {
            "blocker_count": len(blockers),
            "candidate_event_count": len(raw_events),
            "valid_candidate_event_count": len(valid_events),
            "sandbox_event_write_count": len(sandbox_rows) if not blockers else 0,
            "sandbox_readback_event_count": len(readback_events) if not blockers else 0,
            "synthesis_observed_candidate_count": len(observed),
            "synthesis_compiled_object_count": len(compiled),
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "blockers": blockers,
        "not_exercised_by_layer": {
            "memory_not_exercised": [
                "learner_state_service_append_memory_event",
                "learner_memory_db_write",
                "learner_memory_outbox_enqueue",
                "canonical_learner_truth_write",
            ],
            "learning_brain_not_exercised": [
                "production_learning_synthesis",
                "personalization_context_pack_readback",
                "training_intent_creation",
                "next_best_action_generation",
            ],
            "release_not_exercised": ["governance_signoff", "production_default_decision"],
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_sandbox_readback_gate": True,
            "sandbox_write_scope": "artifact_only",
            "learner_memory_write_allowed": False,
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
    parser.add_argument("--pcp-nba-candidate-projection", type=Path, default=DEFAULT_PCP_NBA_CANDIDATE_PROJECTION)
    parser.add_argument("--sandbox-events", type=Path, default=DEFAULT_SANDBOX_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_test_learner_sandbox_readback_gate(
        learning_evidence_candidate_bridge=_read_json(args.learning_evidence_candidate_bridge),
        pcp_nba_candidate_projection=_read_json(args.pcp_nba_candidate_projection),
        sandbox_events=args.sandbox_events,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
