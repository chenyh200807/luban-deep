#!/usr/bin/env python3
"""Validate RichLeaf semantic review decisions before audit-record ingestion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_SHARDS_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612"
DEFAULT_DECISIONS_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decisions_20260612"
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decision_validation_20260612"
SCHEMA = "luban_rich_leaf_semantic_review_decision_validation.v1"
DECISION_SCHEMA = "luban_rich_leaf_semantic_audit_decisions.v1"
ALLOWED_DECISIONS = {
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
}
CONFIDENCE_VALUES = {"low", "medium", "high"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _audit_item_ids(shard_payloads: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for shard in shard_payloads:
        for item in shard.get("audit_items") or []:
            if isinstance(item, dict) and item.get("audit_item_id"):
                ids.append(str(item["audit_item_id"]))
    return ids


def _is_valid_decision(decision: dict[str, Any]) -> bool:
    required = ["audit_item_id", "decision", "reviewer_role", "reviewer_id", "rationale", "confidence"]
    if any(not decision.get(key) for key in required):
        return False
    if decision.get("decision") not in ALLOWED_DECISIONS:
        return False
    if decision.get("confidence") not in CONFIDENCE_VALUES:
        return False
    if decision.get("runtime_install_allowed") is True or decision.get("release_truth_claimed") is True:
        return False
    return True


def _decision_payloads_from_dir(decisions_dir: Path) -> list[dict[str, Any]]:
    if not decisions_dir.exists():
        return []
    return [_read_json(path) for path in sorted(decisions_dir.glob("*.json")) if path.is_file()]


def _shard_payloads_from_dir(review_shards_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        if isinstance(shard, dict) and shard.get("path"):
            payloads.append(_read_json(review_shards_dir / str(shard["path"])))
    return payloads


def validate_semantic_review_decisions(
    *,
    manifest: dict[str, Any],
    shard_payloads: list[dict[str, Any]],
    decision_payloads: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_ids = set(_audit_item_ids(shard_payloads))
    seen: set[str] = set()
    duplicate_decisions: list[dict[str, Any]] = []
    invalid_decisions: list[dict[str, Any]] = []
    stale_decisions: list[dict[str, Any]] = []
    valid_decisions: list[dict[str, Any]] = []

    for payload in decision_payloads:
        if payload.get("schema") != DECISION_SCHEMA:
            invalid_decisions.append({"reason": "schema_mismatch", "payload_schema": payload.get("schema")})
            continue
        for decision in payload.get("decisions") or []:
            if not isinstance(decision, dict):
                invalid_decisions.append({"reason": "decision_not_object", "decision": decision})
                continue
            audit_item_id = str(decision.get("audit_item_id") or "")
            if audit_item_id not in expected_ids:
                stale_decisions.append(decision)
                continue
            if not _is_valid_decision(decision):
                invalid_decisions.append(decision)
                continue
            if audit_item_id in seen:
                duplicate_decisions.append(decision)
                continue
            seen.add(audit_item_id)
            valid_decisions.append(decision)

    missing_ids = sorted(expected_ids - seen)
    verdict = "PASS"
    if invalid_decisions or duplicate_decisions:
        verdict = "FAIL"
    elif missing_ids:
        verdict = "INCOMPLETE"

    report = {
        "schema": SCHEMA,
        "review_shards_schema": manifest.get("schema"),
        "verdict": verdict,
        "classification": {
            "review_only": True,
            "decisions_recorded": bool(valid_decisions),
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_item_count": len(expected_ids),
            "decision_count": len(valid_decisions),
            "missing_decision_count": len(missing_ids),
            "invalid_decision_count": len(invalid_decisions),
            "duplicate_decision_count": len(duplicate_decisions),
            "orphan_decision_count": 0,
            "stale_decision_count": len(stale_decisions),
        },
        "missing_audit_item_ids": missing_ids,
        "invalid_decisions": invalid_decisions,
        "duplicate_decisions": duplicate_decisions,
        "orphan_decisions": [],
        "stale_decisions_ignored": stale_decisions,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }
    merged = {
        "schema": DECISION_SCHEMA,
        "classification": {
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "decisions": valid_decisions,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }
    return report, merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-shards-dir", type=Path, default=DEFAULT_REVIEW_SHARDS_DIR)
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    manifest = _read_json(args.review_shards_dir / "semantic_review_shards_manifest.json")
    shard_payloads = _shard_payloads_from_dir(args.review_shards_dir, manifest)
    decision_payloads = _decision_payloads_from_dir(args.decisions_dir)
    report, merged = validate_semantic_review_decisions(
        manifest=manifest,
        shard_payloads=shard_payloads,
        decision_payloads=decision_payloads,
    )
    _write_json(args.output_dir / "semantic_review_decision_validation.json", report)
    _write_json(args.output_dir / "merged_semantic_audit_decisions.json", merged)
    print(json.dumps({"out": str(args.output_dir), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
