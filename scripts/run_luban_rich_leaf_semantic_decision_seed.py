#!/usr/bin/env python3
"""Seed deterministic RichLeaf semantic review decisions for unresolved source gaps only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_SHARDS_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612"
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decisions_20260612"
SCHEMA = "luban_rich_leaf_semantic_audit_decisions.v1"
POLLUTION_MARKERS = (
    "题库",
    "真题",
    "答案解析",
    "学生答卷",
    "unresolved in_corpus",
    "index_dump",
    "practice",
    "mcq",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _shard_payloads_from_dir(review_shards_dir: Path) -> list[dict[str, Any]]:
    manifest = _read_json(review_shards_dir / "semantic_review_shards_manifest.json")
    payloads: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        if isinstance(shard, dict) and shard.get("path"):
            payloads.append(_read_json(review_shards_dir / str(shard["path"])))
    return payloads


def _is_unresolved_without_source(item: dict[str, Any]) -> bool:
    return item.get("audit_source_type") == "source_evidence_unresolved" and not isinstance(item.get("source_candidate"), dict)


def _is_polluted_support_lane(item: dict[str, Any]) -> bool:
    source_candidate = item.get("source_candidate") if isinstance(item.get("source_candidate"), dict) else {}
    if not source_candidate or item.get("missing_lane") == "question":
        return False
    blob = json.dumps(
        {
            "source_path": source_candidate.get("source_path"),
            "record_id": source_candidate.get("record_id"),
            "span": source_candidate.get("span"),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).lower()
    return any(marker.lower() in blob for marker in POLLUTION_MARKERS)


def build_decision_seed(*, shard_payloads: list[dict[str, Any]], reviewer_id: str) -> dict[str, Any]:
    audit_items = [
        item
        for shard in shard_payloads
        for item in (shard.get("audit_items") or [])
        if isinstance(item, dict)
    ]
    decisions: list[dict[str, Any]] = []
    for item in audit_items:
        if _is_unresolved_without_source(item):
            missing_lane = item.get("missing_lane")
            decisions.append(
                {
                    "audit_item_id": item.get("audit_item_id"),
                    "decision": "needs_external_source",
                    "reviewer_role": "deterministic_unresolved_source_seed",
                    "reviewer_id": reviewer_id,
                    "rationale": (
                        f"No lane-matched source_candidate was available for missing_lane={missing_lane}; "
                        "this seed records only the source authority gap and does not accept any source_ref."
                    ),
                    "confidence": "high",
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                }
            )
            continue
        if _is_polluted_support_lane(item):
            decisions.append(
                {
                    "audit_item_id": item.get("audit_item_id"),
                    "decision": "reject_wrong_leaf_source",
                    "reviewer_role": "deterministic_source_pollution_seed",
                    "reviewer_id": reviewer_id,
                    "rationale": (
                        "The source_candidate contains polluted or question-like support-lane evidence; "
                        "this seed rejects the source_ref candidate and does not infer semantic support."
                    ),
                    "confidence": "high",
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                }
            )
    return {
        "schema": SCHEMA,
        "classification": {
            "review_only": True,
            "seed_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_item_count": len(audit_items),
            "seed_decision_count": len(decisions),
            "unseeded_item_count": len(audit_items) - len(decisions),
        },
        "decisions": decisions,
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
    parser.add_argument("--review-shards-dir", type=Path, default=DEFAULT_REVIEW_SHARDS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reviewer-id", default="deterministic_unresolved_source_seed")
    args = parser.parse_args(argv)

    payload = build_decision_seed(shard_payloads=_shard_payloads_from_dir(args.review_shards_dir), reviewer_id=args.reviewer_id)
    output = args.output_dir / "semantic_decision_seed_unresolved.json"
    _write_json(output, payload)
    print(json.dumps({"out": str(output), "summary": payload["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
