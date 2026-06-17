#!/usr/bin/env python3
"""Build typed LLM work packets for RichLeaf full-corpus deep compilation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_source_corpus_coverage_gate_20260612/source_corpus_coverage_gate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_llm_deep_compile_packets_20260612/llm_deep_compile_packets.json"
)
SCHEMA = "luban_rich_leaf_llm_deep_compile_packets.v1"
COVERAGE_SCHEMA = "luban_rich_leaf_source_corpus_coverage_gate.v1"
REQUIRED_FIELDS = [
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "common_mistakes",
    "exam_patterns",
    "source_refs",
    "negative_evidence",
    "teaching_cards",
    "grading_relevance",
    "learner_memory_event_templates",
]
FORBIDDEN_ACTIONS = [
    "edit_taxonomy",
    "mint_source_truth",
    "claim_release_truth",
    "write_runtime_default",
    "write_canonical_learner_truth",
    "write_production_db",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _input_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != COVERAGE_SCHEMA:
        blockers.append(f"coverage_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") not in {"GAP_WORK_ORDERS_READY", "PASS_FULL_SOURCE_CORPUS_COVERAGE"}:
        blockers.append(f"coverage_not_ready:{payload.get('verdict')}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("runtime_install_allowed") is True:
        blockers.append("coverage_runtime_install_allowed")
    if classification.get("release_truth_claimed") is True:
        blockers.append("coverage_release_truth_claimed")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append("coverage_production_write_count")
    if safety.get("release_truth_claimed") is True:
        blockers.append("coverage_safety_release_truth_claimed")
    return blockers


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _packet(index: int, work_orders: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "packet_id": f"llm_deep_compile_shard_{index:03d}",
        "llm_role": "rich_leaf_deep_compiler",
        "execution_mode": "shadow_candidate_compile_only",
        "work_orders": [
            {
                "work_order_id": str(order.get("work_order_id") or ""),
                "relative_path": str(order.get("relative_path") or ""),
                "source_lane": str(order.get("source_lane") or ""),
                "sha256": str(order.get("sha256") or ""),
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            }
            for order in work_orders
        ],
        "output_contract": {
            "schema": "rich_leaf_deep_compile_candidate.v1",
            "required_fields": REQUIRED_FIELDS,
            "source_ref_requirements": [
                "use_only_supplied_relative_path_and_sha256",
                "include_source_span_for_every_claim",
                "mark_unresolved_when_source_span_is_insufficient",
                "do_not_use_question_bank_as_source_truth",
            ],
            "lifecycle": {
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "official_score_allowed": False,
            },
        },
        "review_routing": {
            "required_next_roles": [
                "evidence_span_auditor",
                "prosecutor",
                "defense",
                "arbiter",
                "bucket_taxonomist",
            ],
            "materialize_decisions_before_runtime": True,
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }


def run_llm_deep_compile_packets(*, source_corpus_coverage_gate: dict[str, Any], shard_size: int = 25) -> dict[str, Any]:
    blockers = _input_blockers(source_corpus_coverage_gate)
    if shard_size <= 0:
        blockers.append("invalid_shard_size")
        shard_size = 25
    work_orders = [
        order
        for order in source_corpus_coverage_gate.get("gap_work_orders") or []
        if isinstance(order, dict)
    ]
    packets = [_packet(index, chunk) for index, chunk in enumerate(_chunks(work_orders, shard_size))]
    verdict = "NO_GO_INPUT_SAFETY_INVARIANT" if blockers else "READY_FOR_LLM_DEEP_COMPILE_SHADOW"
    return {
        "schema": SCHEMA,
        "input_schemas": {"source_corpus_coverage_gate": source_corpus_coverage_gate.get("schema")},
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "llm_packet_generation_only",
        "summary": {
            "work_order_count": len(work_orders),
            "packet_count": len(packets),
            "shard_size": shard_size,
            "blocker_count": len(blockers),
            "provider_call_count": 0,
            "production_write_count": 0,
            "runtime_install_count": 0,
        },
        "packets": packets,
        "blockers": blockers,
        "not_exercised": [
            "llm_provider_call",
            "semantic_review",
            "runtime_default_install",
            "canonical_truth_write",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "llm_deep_compile_packets": True,
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
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-gate", type=Path, default=DEFAULT_COVERAGE_GATE)
    parser.add_argument("--shard-size", type=int, default=25)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_llm_deep_compile_packets(
        source_corpus_coverage_gate=_read_json(args.coverage_gate),
        shard_size=args.shard_size,
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["verdict"] == "NO_GO_INPUT_SAFETY_INVARIANT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
