#!/usr/bin/env python3
"""Close the v2.3 RichLeaf -> Learning Brain candidate bridge.

This runner only summarizes candidate artifacts. It does not write learner
memory, install runtime defaults, update canonical truth, or call providers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_v23_learning_brain_candidate_closure.v1"
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v23_20260612/runtime_token_pack_v23.json"
)
DEFAULT_NEAR_LIVE_AB = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_near_live_shadow_ab_20260612/v23_near_live_shadow_ab.json"
)
DEFAULT_BRIDGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge_v23.json"
)
DEFAULT_PROJECTION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection_v23.json"
)
DEFAULT_SANDBOX_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate_v23.json"
)
DEFAULT_LIVE_PROVIDER_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_provider_shadow_ab_20260612/v23_live_provider_shadow_ab_sample8_deepseek_promptfix.json"
)
DEFAULT_LIVE_RESIDUAL_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_residual_work_orders_20260612/live_residual_work_orders_sample8_promptfix.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_learning_brain_candidate_closure_20260612/learning_brain_candidate_closure_v23.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else {}


def _safety_blocks(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("candidate_only", "review_only"):
        if key in classification and classification.get(key) is not True:
            blockers.append(f"{name}:classification.{key}_not_true")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if key in classification and classification.get(key) is not False:
            blockers.append(f"{name}:classification.{key}_not_false")
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if key in safety and safety.get(key) is not False:
            blockers.append(f"{name}:safety.{key}_not_false")
    for key in (
        "production_write_count",
        "learner_memory_write_count",
        "personalization_context_pack_readback_count",
        "training_intent_write_count",
        "next_best_action_write_count",
    ):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"{name}:safety.{key}_nonzero")
    if safety.get("canonical_learner_truth_written") is True:
        blockers.append(f"{name}:safety.canonical_learner_truth_written_not_false")
    return blockers


def build_v23_learning_brain_candidate_closure(
    *,
    runtime_token_pack: dict[str, Any],
    near_live_ab: dict[str, Any],
    bridge: dict[str, Any],
    projection: dict[str, Any],
    sandbox_gate: dict[str, Any],
    live_provider_ab: dict[str, Any] | None = None,
    live_residual_work_orders: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    expected = {
        "runtime_token_pack": (runtime_token_pack, "luban_rich_leaf_runtime_token_pack.v2.3"),
        "near_live_ab": (near_live_ab, "luban_rich_leaf_v23_near_live_shadow_ab.v1"),
        "bridge": (bridge, "luban_rich_leaf_learning_evidence_candidate_bridge.v1"),
        "projection": (projection, "luban_rich_leaf_pcp_nba_candidate_projection.v1"),
        "sandbox_gate": (sandbox_gate, "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"),
    }
    if live_provider_ab is not None:
        expected["live_provider_ab"] = (live_provider_ab, "luban_rich_leaf_v23_live_provider_shadow_ab.v1")
    if live_residual_work_orders is not None:
        expected["live_residual_work_orders"] = (
            live_residual_work_orders,
            "luban_rich_leaf_v23_live_residual_work_orders.v1",
        )
    for name, (payload, schema) in expected.items():
        if payload.get("schema") != schema:
            blockers.append(f"{name}:schema_mismatch:{payload.get('schema')}")
        blockers.extend(_safety_blocks(name, payload))

    if runtime_token_pack.get("status") != "candidate_ready_for_shadow_ab_full_accounted":
        blockers.append(f"runtime_token_pack:bad_status:{runtime_token_pack.get('status')}")
    if near_live_ab.get("verdict") != "PASS_V23_NEAR_LIVE_SHADOW_AB":
        blockers.append(f"near_live_ab:bad_verdict:{near_live_ab.get('verdict')}")
    if bridge.get("verdict") != "PASS":
        blockers.append(f"bridge:bad_verdict:{bridge.get('verdict')}")
    if projection.get("verdict") != "PASS":
        blockers.append(f"projection:bad_verdict:{projection.get('verdict')}")
    if sandbox_gate.get("verdict") != "PASS":
        blockers.append(f"sandbox_gate:bad_verdict:{sandbox_gate.get('verdict')}")
    if live_provider_ab is not None and live_provider_ab.get("verdict") != "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB":
        blockers.append(f"live_provider_ab:bad_verdict:{live_provider_ab.get('verdict')}")
    if live_residual_work_orders is not None and live_residual_work_orders.get("verdict") != "PASS_LIVE_RESIDUAL_WORK_ORDERS_READY":
        blockers.append(f"live_residual_work_orders:bad_verdict:{live_residual_work_orders.get('verdict')}")

    runtime_summary = _summary(runtime_token_pack)
    near_live_summary = _summary(near_live_ab)
    bridge_summary = _summary(bridge)
    projection_summary = _summary(projection)
    sandbox_summary = _summary(sandbox_gate)
    live_summary = _summary(live_provider_ab or {})
    residual_summary = _summary(live_residual_work_orders or {})
    runtime_unit_count = int(runtime_summary.get("leaf_scoped_runtime_unit_count") or 0)
    bridge_event_count = int(bridge_summary.get("candidate_event_count") or 0)
    sandbox_readback_count = int(sandbox_summary.get("sandbox_readback_event_count") or 0)
    if bridge_event_count != runtime_unit_count:
        blockers.append(f"bridge_event_count_mismatch:{bridge_event_count}!={runtime_unit_count}")
    if sandbox_readback_count != bridge_event_count:
        blockers.append(f"sandbox_readback_count_mismatch:{sandbox_readback_count}!={bridge_event_count}")
    if int(sandbox_summary.get("synthesis_observed_candidate_count") or 0) != 0:
        blockers.append("sandbox_candidate_leaked_into_observed_candidates")
    if int(sandbox_summary.get("synthesis_compiled_object_count") or 0) != 0:
        blockers.append("sandbox_candidate_leaked_into_compiled_objects")
    # Review-only consumption proof: when the sandbox gate reports the candidate
    # observation channel, every bridged candidate must be observed by synthesis
    # (silent drop is a closure blocker). Absent key = legacy artifact, no check.
    raw_observation_count = sandbox_summary.get("synthesis_candidate_observation_count")
    synthesis_candidate_observation_count = int(raw_observation_count or 0)
    if raw_observation_count is not None and synthesis_candidate_observation_count != bridge_event_count:
        blockers.append(
            f"synthesis_candidate_observation_count_mismatch:{synthesis_candidate_observation_count}!={bridge_event_count}"
        )

    return {
        "schema": SCHEMA,
        "verdict": (
            "FAIL_SAFETY_OR_CONTRACT"
            if blockers
            else "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
        ),
        "quality_claim_allowed": False,
        "claim_scope": {
            "candidate_full_accounted": True,
            "runtime_shadow_candidate": True,
            "learning_evidence_candidate_bridge_exercised": True,
            "artifact_only_sandbox_readback_exercised": True,
            "live_provider_v23_sample_exercised": live_provider_ab is not None,
            "compiler_feedback_work_orders_ready": live_residual_work_orders is not None,
            "canonical_learner_truth_allowed": False,
            "production_default_allowed": False,
            "release_truth_allowed": False,
        },
        "summary": {
            "original_v2_source_file_units": int(runtime_summary.get("original_v2_unit_count") or 0),
            "original_units_accounted": int(runtime_summary.get("original_unit_accounted_count") or 0),
            "leaf_scoped_runtime_units": runtime_unit_count,
            "non_runtime_excluded_or_gap": int(runtime_summary.get("non_runtime_excluded_or_gap_count") or 0),
            "taxonomy_gap_candidates": int(runtime_summary.get("taxonomy_gap_candidate_count") or 0),
            "near_live_case_count": int(near_live_summary.get("case_count") or 0),
            "near_live_provider_call_count": int(near_live_summary.get("provider_call_count") or 0),
            "near_live_live_runtime_executed": bool(near_live_summary.get("live_runtime_executed")),
            "live_provider_sample_count": int(live_summary.get("sample_count") or 0),
            "live_provider_call_count": int(live_summary.get("provider_call_count") or 0),
            "live_provider_total_tokens": int(live_summary.get("total_tokens") or 0),
            "live_residual_work_order_count": int(residual_summary.get("work_order_count") or 0),
            "candidate_event_count": bridge_event_count,
            "claim_candidate_count": int(projection_summary.get("top_claim_candidate_count") or 0),
            "next_action_candidate_count": int(projection_summary.get("next_action_candidate_count") or 0),
            "sandbox_event_write_count": int(sandbox_summary.get("sandbox_event_write_count") or 0),
            "sandbox_readback_event_count": sandbox_readback_count,
            "synthesis_observed_candidate_count": int(sandbox_summary.get("synthesis_observed_candidate_count") or 0),
            "synthesis_compiled_object_count": int(sandbox_summary.get("synthesis_compiled_object_count") or 0),
            "synthesis_candidate_observation_count": synthesis_candidate_observation_count,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
            "blocker_count": len(blockers),
        },
        "decision_table": [
            {
                "gate": "RichLeaf v2.3 full-accounted candidate",
                "verdict": "PASS",
                "evidence": "runtime_token_pack_v23",
            },
            {
                "gate": "candidate learning evidence bridge",
                "verdict": "PASS" if bridge.get("verdict") == "PASS" else "FAIL",
                "evidence": "learning_evidence_candidate_bridge_v23",
            },
            {
                "gate": "PCP/NBA candidate projection",
                "verdict": "PASS" if projection.get("verdict") == "PASS" else "FAIL",
                "evidence": "pcp_nba_candidate_projection_v23",
            },
            {
                "gate": "artifact-only sandbox readback",
                "verdict": "PASS" if sandbox_gate.get("verdict") == "PASS" else "FAIL",
                "evidence": "test_learner_sandbox_readback_gate_v23",
            },
            {
                "gate": "v2.3 projected live provider A/B",
                "verdict": "PASS" if live_provider_ab is not None else "NOT_EXERCISED",
                "evidence": "v23_live_provider_shadow_ab",
            },
            {
                "gate": "compiler feedback residual work orders",
                "verdict": "PASS" if live_residual_work_orders is not None else "NOT_EXERCISED",
                "evidence": "v23_live_residual_work_orders",
            },
            {
                "gate": "canonical learner memory write",
                "verdict": "NOT_EXERCISED",
                "evidence": "learner_memory_write_count=0",
            },
            {
                "gate": "production default / release truth",
                "verdict": "NOT_EXERCISED",
                "evidence": "runtime_install_allowed=false; release_truth_claimed=false",
            },
        ],
        "blockers": blockers,
        "not_exercised": [
            "canonical_taxonomy_extension_for_23_gaps",
            "canonical_learner_truth_write",
            "production_learner_memory_db_write",
            "training_intent_write",
            "next_best_action_write",
            "runtime_default_install",
            "release_governance_signoff",
        ]
        + ([] if live_provider_ab is not None else ["live_provider_v23_four_arm_ab"])
        + ([] if live_residual_work_orders is not None else ["compiler_feedback_from_live_residuals"]),
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "learning_brain_candidate_closure": True,
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
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--near-live-ab", type=Path, default=DEFAULT_NEAR_LIVE_AB)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    parser.add_argument("--sandbox-gate", type=Path, default=DEFAULT_SANDBOX_GATE)
    parser.add_argument("--live-provider-ab", type=Path, default=DEFAULT_LIVE_PROVIDER_AB)
    parser.add_argument("--live-residual-work-orders", type=Path, default=DEFAULT_LIVE_RESIDUAL_WORK_ORDERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        near_live_ab=_read_json(args.near_live_ab),
        bridge=_read_json(args.bridge),
        projection=_read_json(args.projection),
        sandbox_gate=_read_json(args.sandbox_gate),
        live_provider_ab=_read_json(args.live_provider_ab) if args.live_provider_ab.exists() else None,
        live_residual_work_orders=_read_json(args.live_residual_work_orders)
        if args.live_residual_work_orders.exists()
        else None,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
