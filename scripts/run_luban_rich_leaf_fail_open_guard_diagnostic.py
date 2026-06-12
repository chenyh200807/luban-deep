#!/usr/bin/env python3
"""Render review-only fail-open guard diagnostics from RichLeaf candidates."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_CONTEXT_PACK_SMOKE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_context_pack_smoke_20260612/context_pack_smoke.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_fail_open_guard_diagnostic_20260612/fail_open_guard_diagnostic.json"
)
SCHEMA = "luban_rich_leaf_fail_open_guard_diagnostic.v1"
CANDIDATE_CLAIM_STATUSES = {"candidate_only", "needs_review", "hypothesis"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_candidate_field_count(context_pack_smoke: dict[str, Any]) -> int:
    summary = context_pack_smoke.get("summary") if isinstance(context_pack_smoke.get("summary"), dict) else {}
    value = summary.get("review_candidate_field_count")
    return value if isinstance(value, int) else 0


def _source_ref_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for ref in artifact.get("source_refs") or []:
        if isinstance(ref, dict) and ref.get("source_ref_id"):
            refs[str(ref["source_ref_id"])] = ref
    return refs


def _candidate_negative_evidence(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in artifact.get("negative_evidence") or []:
        if not isinstance(field, dict):
            continue
        if field.get("candidate_only") is not True:
            continue
        if field.get("claim_status") not in CANDIDATE_CLAIM_STATUSES:
            continue
        fields.append(field)
    return fields


def run_fail_open_guard_diagnostic(
    *, field_promotion_review: dict[str, Any], context_pack_smoke: dict[str, Any]
) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"input_schema_mismatch:field_promotion_review:{field_promotion_review.get('schema')}")
    if context_pack_smoke.get("schema") != "luban_rich_leaf_context_pack_smoke.v1":
        blockers.append(f"input_schema_mismatch:context_pack_smoke:{context_pack_smoke.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"input_field_promotion_review_failed:{field_promotion_review.get('verdict')}")
    if context_pack_smoke.get("verdict") != "PASS":
        blockers.append(f"input_context_pack_smoke_failed:{context_pack_smoke.get('verdict')}")

    by_leaf: dict[str, dict[str, Any]] = {}
    negative_evidence_count = 0
    artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    for artifact in artifacts:
        artifact_id = str(artifact.get("artifact_id") or "")
        leaf_id = str(artifact.get("leaf_id") or "")
        if not leaf_id:
            continue
        ref_index = _source_ref_index(artifact)
        fields = _candidate_negative_evidence(artifact)
        if not fields:
            continue
        entry = by_leaf.setdefault(
            leaf_id,
            {
                "leaf_id": leaf_id,
                "artifact_ids": [],
                "negative_evidence_count": 0,
                "field_ids": [],
                "source_lanes": set(),
                "record_ids": [],
                "source_ref_ids": [],
                "negative_evidence_types": set(),
                "rationales": [],
                "guard_suggestion": "block_positive_context_until_source_ref_reviewed",
            },
        )
        if artifact_id and artifact_id not in entry["artifact_ids"]:
            entry["artifact_ids"].append(artifact_id)
        for field in fields:
            negative_evidence_count += 1
            entry["negative_evidence_count"] += 1
            field_id = str(field.get("field_id") or "")
            if field_id:
                entry["field_ids"].append(field_id)
            evidence_type = field.get("negative_evidence_type")
            if evidence_type:
                entry["negative_evidence_types"].add(str(evidence_type))
            rationale = field.get("rationale") or field.get("statement")
            if rationale:
                entry["rationales"].append(str(rationale))
            for source_ref_id in field.get("source_ref_ids") or []:
                source_ref_id = str(source_ref_id)
                if source_ref_id:
                    entry["source_ref_ids"].append(source_ref_id)
                ref = ref_index.get(source_ref_id, {})
                if ref.get("source_lane"):
                    entry["source_lanes"].add(str(ref["source_lane"]))
                if ref.get("record_id"):
                    entry["record_ids"].append(str(ref["record_id"]))

    review_candidate_count = _review_candidate_field_count(context_pack_smoke)
    if negative_evidence_count and review_candidate_count <= 0:
        blockers.append("negative_evidence_not_visible_in_review_pack")

    leaf_diagnostics = []
    for entry in by_leaf.values():
        leaf_diagnostics.append(
            {
                "leaf_id": entry["leaf_id"],
                "artifact_ids": sorted(entry["artifact_ids"]),
                "negative_evidence_count": entry["negative_evidence_count"],
                "field_ids": sorted(set(entry["field_ids"])),
                "source_lanes": sorted(entry["source_lanes"]),
                "record_ids": sorted(set(entry["record_ids"])),
                "source_ref_ids": sorted(set(entry["source_ref_ids"])),
                "negative_evidence_types": sorted(entry["negative_evidence_types"]),
                "rationales": sorted(set(entry["rationales"])),
                "guard_suggestion": entry["guard_suggestion"],
            }
        )
    leaf_diagnostics.sort(key=lambda item: (-int(item["negative_evidence_count"]), str(item["leaf_id"])))

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "field_promotion_review": field_promotion_review.get("schema"),
            "context_pack_smoke": context_pack_smoke.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "fail_open_guard_diagnostic": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "input_promoted_artifact_count": len(artifacts),
            "negative_evidence_candidate_count": negative_evidence_count,
            "review_candidate_field_count": review_candidate_count,
            "top_leaf_count": len(leaf_diagnostics),
            "blocker_count": len(blockers),
        },
        "leaf_diagnostics": leaf_diagnostics,
        "blockers": blockers,
        "not_exercised": [
            "runtime_fail_open_reduction",
            "production_runtime_enforcement",
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
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--context-pack-smoke", type=Path, default=DEFAULT_CONTEXT_PACK_SMOKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_fail_open_guard_diagnostic(
        field_promotion_review=_read_json(args.field_promotion_review),
        context_pack_smoke=_read_json(args.context_pack_smoke),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
