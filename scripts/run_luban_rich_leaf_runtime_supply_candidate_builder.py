#!/usr/bin/env python3
"""Build review-only RichLeaf runtime supply candidates from reviewed source refs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEWED_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_reviewed_candidates_20260612/reviewed_rich_leaf_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_candidate_20260612"
SCHEMA = "luban_rich_leaf_runtime_supply_candidate_bundle.v1"
VERSION = "v_rich_leaf_runtime_supply_candidate_20260612"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _unit_id(candidate: dict[str, Any], source_ref: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(candidate.get("candidate_id") or ""),
            str(candidate.get("leaf_id") or ""),
            str(candidate.get("missing_lane") or ""),
            str(source_ref.get("record_id") or ""),
            str(source_ref.get("span_hash") or ""),
        ]
    )
    return f"rich_leaf_supply_unit_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _rejection_reason(candidate: dict[str, Any]) -> str:
    if candidate.get("runtime_install_allowed") is not False or candidate.get("release_truth_claimed") is not False:
        return "candidate_runtime_or_release_allowed"
    if candidate.get("official_score_allowed") is not False:
        return "candidate_official_score_allowed"
    if candidate.get("candidate_status") != "reviewed_candidate":
        return "candidate_status_not_reviewed"
    if candidate.get("candidate_only") is not True or candidate.get("review_only") is not True:
        return "candidate_review_flags_invalid"
    patch = candidate.get("field_patch") if isinstance(candidate.get("field_patch"), dict) else {}
    source_ref = patch.get("source_ref") if isinstance(patch.get("source_ref"), dict) else {}
    if patch.get("field") != "source_refs" or patch.get("operation") != "add_source_ref":
        return "field_patch_not_source_ref_addition"
    if not candidate.get("leaf_id") or not candidate.get("artifact_id") or not candidate.get("missing_lane"):
        return "candidate_join_keys_missing"
    if source_ref.get("source_lane") != candidate.get("missing_lane"):
        return "source_lane_mismatch"
    if not source_ref.get("record_id") or not source_ref.get("span") or not source_ref.get("span_hash"):
        return "source_ref_trace_missing"
    if source_ref.get("source_lane") == "question" and candidate.get("missing_lane") != "question":
        return "question_lane_cannot_support_non_question"
    return ""


def _supply_unit(candidate: dict[str, Any]) -> dict[str, Any]:
    source_ref = candidate["field_patch"]["source_ref"]
    return {
        "unit_id": _unit_id(candidate, source_ref),
        "leaf_id": candidate.get("leaf_id"),
        "artifact_id": candidate.get("artifact_id"),
        "missing_lane": candidate.get("missing_lane"),
        "source_ref": {
            "source_lane": source_ref.get("source_lane"),
            "source_path": source_ref.get("source_path"),
            "record_id": source_ref.get("record_id"),
            "span": source_ref.get("span"),
            "span_hash": source_ref.get("span_hash"),
            "support_candidate": source_ref.get("support_candidate") is True,
        },
        "provenance": {
            "candidate_id": candidate.get("candidate_id"),
            "audit_item_id": candidate.get("audit_item_id"),
            "review_decision": (candidate.get("review_authority") or {}).get("decision")
            if isinstance(candidate.get("review_authority"), dict)
            else None,
            "reviewer_role": (candidate.get("review_authority") or {}).get("reviewer_role")
            if isinstance(candidate.get("review_authority"), dict)
            else None,
        },
        "candidate_only": True,
        "review_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def build_runtime_supply_candidate(*, reviewed_candidates: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in reviewed_candidates.get("reviewed_candidates") or []
        if isinstance(candidate, dict)
    ]
    rejected: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    for candidate in candidates:
        reason = _rejection_reason(candidate)
        if reason:
            rejected.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "leaf_id": candidate.get("leaf_id"),
                    "artifact_id": candidate.get("artifact_id"),
                    "missing_lane": candidate.get("missing_lane"),
                    "reason": reason,
                }
            )
            continue
        units.append(_supply_unit(candidate))
    bundle_hash = _sha256(units)
    if units:
        status = "candidate_ready_for_regression"
    elif candidates:
        status = "no_valid_supply_units"
    else:
        status = "no_reviewed_candidates"
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "status": status,
        "reviewed_candidate_schema": reviewed_candidates.get("schema"),
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_supply_candidate": True,
            "regression_required": True,
            "install_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
        },
        "summary": {
            "reviewed_candidate_count": len(candidates),
            "supply_unit_count": len(units),
            "rejected_candidate_count": len(rejected),
        },
        "manifest": {
            "bundle_hash": bundle_hash,
            "hash_algorithm": "sha256",
            "included_file": "rich_leaf_runtime_supply_candidate.json",
            "source_artifact_schema": reviewed_candidates.get("schema"),
        },
        "supply_units": units,
        "rejected_candidates": rejected,
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
    parser.add_argument("--reviewed-candidates", type=Path, default=DEFAULT_REVIEWED_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = build_runtime_supply_candidate(reviewed_candidates=_read_json(args.reviewed_candidates))
    output = args.output_dir / "rich_leaf_runtime_supply_candidate.json"
    _write_json(output, report)
    print(json.dumps({"out": str(output), "status": report["status"], "summary": report["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
