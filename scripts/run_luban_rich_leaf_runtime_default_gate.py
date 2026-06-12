#!/usr/bin/env python3
"""Gate a RichLeaf RuntimeTokenPack for controlled default review without installing it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v1_20260612/runtime_token_pack.json"
)
DEFAULT_RUNTIME_SUPPLY_REGRESSION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_supply_regression_materialized_20260612/runtime_supply_regression.json"
)
DEFAULT_STREAMING_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_streaming_ab_20260612/streaming_ab_sample16.json"
)
DEFAULT_SEMANTIC_RUNTIME_LIVE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_semantic_runtime_live_ab_materialized_20260612/semantic_runtime_live_ab_full274_full_baseline.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_default_gate_20260612/runtime_default_gate.json"
)
SCHEMA = "luban_rich_leaf_runtime_default_gate.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safety_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("runtime_install_allowed") is not False:
        blockers.append(f"{name}_runtime_install_allowed")
    if classification.get("production_default") is not False:
        blockers.append(f"{name}_production_default")
    if classification.get("release_truth_claimed") is True:
        blockers.append(f"{name}_release_truth_claimed")
    if safety.get("installed_runtime_supply") is True:
        blockers.append(f"{name}_installed_runtime_supply")
    if safety.get("production_write_count", 0) not in (0, None):
        blockers.append(f"{name}_production_write_count_nonzero")
    if safety.get("release_truth_claimed") is not False:
        blockers.append(f"{name}_safety_release_truth_claimed")
    return blockers


def _arm(arms: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for arm in arms:
        if isinstance(arm, dict) and arm.get("arm") == name:
            return arm
    return {}


def _streaming_deltas(streaming_ab: dict[str, Any]) -> tuple[float, float]:
    arms = streaming_ab.get("arms") if isinstance(streaming_ab.get("arms"), list) else []
    thin = _arm(arms, "runtime_token_pack_thin")
    full = _arm(arms, "runtime_supply_full_span")
    ttft_delta = round(float(thin.get("mean_ttft_ms") or 0.0) - float(full.get("mean_ttft_ms") or 0.0), 2)
    context_delta = round(float(thin.get("mean_context_char_count") or 0.0) - float(full.get("mean_context_char_count") or 0.0), 2)
    return ttft_delta, context_delta


def run_runtime_default_gate(
    *,
    runtime_token_pack: dict[str, Any],
    runtime_supply_regression: dict[str, Any],
    streaming_ab: dict[str, Any],
    semantic_runtime_live_ab: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != "luban_rich_leaf_runtime_token_pack.v1":
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if runtime_token_pack.get("status") != "candidate_ready_for_streaming_ab":
        blockers.append(f"runtime_token_pack_not_ready:{runtime_token_pack.get('status')}")
    if runtime_supply_regression.get("schema") != "luban_rich_leaf_runtime_supply_regression.v1":
        blockers.append(f"runtime_supply_regression_schema_mismatch:{runtime_supply_regression.get('schema')}")
    if runtime_supply_regression.get("verdict") != "PASS":
        blockers.append(f"runtime_supply_regression_not_pass:{runtime_supply_regression.get('verdict')}")
    if streaming_ab.get("schema") != "luban_rich_leaf_runtime_token_pack_streaming_ab.v1":
        blockers.append(f"streaming_ab_schema_mismatch:{streaming_ab.get('schema')}")
    if streaming_ab.get("runtime_exercised") is not True:
        blockers.append("streaming_ab_not_exercised")
    if semantic_runtime_live_ab.get("verdict") != "PASS_LIVE_RUNTIME_AB_SHADOW":
        blockers.append(f"semantic_runtime_live_ab_not_pass:{semantic_runtime_live_ab.get('verdict')}")
    for name, payload in (
        ("runtime_token_pack", runtime_token_pack),
        ("runtime_supply_regression", runtime_supply_regression),
        ("streaming_ab", streaming_ab),
    ):
        blockers.extend(_safety_blockers(name, payload))
    token_summary = runtime_token_pack.get("summary") if isinstance(runtime_token_pack.get("summary"), dict) else {}
    supply_summary = runtime_supply_regression.get("summary") if isinstance(runtime_supply_regression.get("summary"), dict) else {}
    streaming_summary = streaming_ab.get("summary") if isinstance(streaming_ab.get("summary"), dict) else {}
    ttft_delta, context_delta = _streaming_deltas(streaming_ab)
    verdict = "READY_FOR_CONTROLLED_DEFAULT_REVIEW" if not blockers else "BLOCKED"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "runtime_default_decision": {
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "requires_signed_operator_decision": True,
            "requires_rollback_plan": True,
            "requires_shadow_observability": True,
        },
        "summary": {
            "blocker_count": len(blockers),
            "token_pack_unit_count": int(token_summary.get("token_pack_unit_count") or 0),
            "supply_unit_count": int(supply_summary.get("input_supply_unit_count") or 0),
            "streaming_sample_count": int(streaming_summary.get("sample_count") or 0),
            "streaming_provider_call_count": int(streaming_summary.get("provider_call_count") or 0),
            "streaming_ttft_delta_ms": ttft_delta,
            "streaming_context_char_delta": context_delta,
            "semantic_live_ab_verdict": semantic_runtime_live_ab.get("verdict"),
        },
        "blockers": blockers,
        "not_exercised": [
            "canonical_pointer_write",
            "runtime_default_install",
            "production_db_write",
            "release_truth_governance",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_default_gate": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
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
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--runtime-supply-regression", type=Path, default=DEFAULT_RUNTIME_SUPPLY_REGRESSION)
    parser.add_argument("--streaming-ab", type=Path, default=DEFAULT_STREAMING_AB)
    parser.add_argument("--semantic-runtime-live-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_LIVE_AB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_runtime_default_gate(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        runtime_supply_regression=_read_json(args.runtime_supply_regression),
        streaming_ab=_read_json(args.streaming_ab),
        semantic_runtime_live_ab=_read_json(args.semantic_runtime_live_ab),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "READY_FOR_CONTROLLED_DEFAULT_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
