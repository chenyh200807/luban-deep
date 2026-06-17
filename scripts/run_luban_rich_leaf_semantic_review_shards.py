#!/usr/bin/env python3
"""Create review-only semantic review shards from a RichLeaf audit queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC_QUEUE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_queue_20260612/semantic_audit_queue.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612"
SCHEMA = "luban_rich_leaf_semantic_review_shards.v1"
SHARD_SCHEMA = "luban_rich_leaf_semantic_review_shard.v1"
ALLOWED_DECISIONS = [
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_item_id": item.get("audit_item_id"),
        "audit_source_type": item.get("audit_source_type"),
        "leaf_id": item.get("leaf_id"),
        "artifact_id": item.get("artifact_id"),
        "name_path": item.get("name_path"),
        "missing_lane": item.get("missing_lane"),
        "source_candidate": item.get("source_candidate"),
        "question_context": item.get("question_context") if isinstance(item.get("question_context"), dict) else {},
        "machine_context": item.get("machine_context") if isinstance(item.get("machine_context"), dict) else {},
        "question_context_candidates": list(item.get("question_context_candidates") or []),
        "allowed_decisions": list(item.get("allowed_decisions") or ALLOWED_DECISIONS),
        "review_questions": [
            "Does the source span semantically support this exact leaf, not only a parent or generic topic?",
            "Is the source lane appropriate for the missing lane?",
            "Is question evidence only used as question context unless missing_lane is question?",
            "If rejected, should the next action be stronger source search, external source required, or leaf split?",
        ],
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
    }


def _decision_output_schema() -> dict[str, Any]:
    return {
        "schema": "luban_rich_leaf_semantic_audit_decisions.v1",
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "required_fields": ["audit_item_id", "decision", "reviewer_role", "reviewer_id", "rationale", "confidence"],
        "confidence_values": ["low", "medium", "high"],
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def _shard_payload(shard_index: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SHARD_SCHEMA,
        "shard_id": f"semantic_review_shard_{shard_index:03d}",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
        },
        "review_instructions": {
            "task": "Review each audit item and emit decisions in the decision_output_schema only.",
            "do_not": [
                "Do not install runtime supply.",
                "Do not claim release truth.",
                "Do not create official scoring authority.",
                "Do not treat question evidence as textbook/standard/lecture support.",
            ],
        },
        "decision_output_schema": _decision_output_schema(),
        "summary": {"audit_item_count": len(items)},
        "audit_items": [_review_item(item) for item in items],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def build_semantic_review_shards_report(
    *, semantic_queue: dict[str, Any], shard_size: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if shard_size < 1:
        raise ValueError("shard_size must be >= 1")
    items = [item for item in semantic_queue.get("semantic_audit_queue") or [] if isinstance(item, dict)]
    shards = [_shard_payload(index, items[start : start + shard_size]) for index, start in enumerate(range(0, len(items), shard_size))]
    manifest = {
        "schema": SCHEMA,
        "semantic_queue_schema": semantic_queue.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
        },
        "summary": {"audit_item_count": len(items), "shard_count": len(shards), "shard_size": shard_size},
        "shards": [
            {
                "shard_id": shard["shard_id"],
                "path": f"{shard['shard_id']}.json",
                "audit_item_count": shard["summary"]["audit_item_count"],
            }
            for shard in shards
        ],
        "decision_output_schema": _decision_output_schema(),
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }
    return manifest, shards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-queue", type=Path, default=DEFAULT_SEMANTIC_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--shard-size", type=int, default=25)
    args = parser.parse_args(argv)

    manifest, shards = build_semantic_review_shards_report(semantic_queue=_read_json(args.semantic_queue), shard_size=args.shard_size)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for shard in shards:
        _write_json(args.output_dir / f"{shard['shard_id']}.json", shard)
    _write_json(args.output_dir / "semantic_review_shards_manifest.json", manifest)
    print(json.dumps({"out": str(args.output_dir), "summary": manifest["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
