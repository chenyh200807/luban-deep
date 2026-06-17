#!/usr/bin/env python3
"""Run a static regression gate for RichLeaf runtime supply candidates.

This gate proves candidate bundle shape and task projection safety. It does not
install runtime supply, write a canonical pointer, or claim release truth.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_SUPPLY_CANDIDATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_candidate_20260612/rich_leaf_runtime_supply_candidate.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_regression_20260612"
SCHEMA = "luban_rich_leaf_runtime_supply_regression.v1"
INPUT_SCHEMA = "luban_rich_leaf_runtime_supply_candidate_bundle.v1"

TASK_POLICIES: dict[str, dict[str, Any]] = {
    "grading": {
        "allowed_fields": ["rubric_link_index", "rules", "numeric_constraints", "negative_evidence", "source_refs"],
        "allowed_source_lanes": ["textbook", "standard", "lecture", "question"],
    },
    "tutoring": {
        "allowed_fields": ["definitions", "procedures", "teaching_cards", "rules", "source_refs", "common_mistakes"],
        "allowed_source_lanes": ["textbook", "standard", "lecture"],
    },
    "rag_answer": {
        "allowed_fields": ["definitions", "rules", "procedures", "source_refs"],
        "allowed_source_lanes": ["textbook", "standard", "lecture"],
    },
    "next_action": {
        "allowed_fields": ["teaching_cards", "exam_patterns", "common_mistakes", "learner_memory_event_templates"],
        "allowed_source_lanes": [],
    },
    "review": {
        "allowed_fields": ["all_candidate_fields"],
        "allowed_source_lanes": ["textbook", "standard", "lecture", "question"],
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _count_by_lane(units: list[dict[str, Any]]) -> dict[str, int]:
    lanes: Counter[str] = Counter()
    for unit in units:
        if isinstance(unit.get("source_ref"), dict):
            lanes[str(unit["source_ref"].get("source_lane") or "unknown")] += 1
            continue
        source_refs = unit.get("source_refs") if isinstance(unit.get("source_refs"), list) else []
        if source_refs and isinstance(source_refs[0], dict):
            lanes[str(source_refs[0].get("source_lane") or "unknown")] += 1
            continue
        lanes["unknown"] += 1
    return dict(sorted(lanes.items()))


def _safe_unit_projection(unit: dict[str, Any], *, include_source_ref: bool) -> dict[str, Any]:
    projection = {
        "unit_id": unit.get("unit_id"),
        "leaf_id": unit.get("leaf_id"),
        "artifact_id": unit.get("artifact_id"),
        "missing_lane": unit.get("missing_lane"),
        "provenance": unit.get("provenance") if isinstance(unit.get("provenance"), dict) else {},
        "candidate_only": True,
        "review_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
        "production_default": False,
    }
    if include_source_ref:
        source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
        projection["source_refs"] = [
            {
                "source_lane": source_ref.get("source_lane"),
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span": source_ref.get("span"),
                "span_hash": source_ref.get("span_hash"),
                "support_candidate": source_ref.get("support_candidate") is True,
            }
        ]
    return projection


def _task_projection(task: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    policy = TASK_POLICIES[task]
    allowed_lanes = set(policy["allowed_source_lanes"])
    projected: list[dict[str, Any]] = []
    excluded_lane_counts: Counter[str] = Counter()
    exclusion_reasons: Counter[str] = Counter()
    for unit in units:
        lane = str((unit.get("source_ref") or {}).get("source_lane") or "unknown")
        if "source_refs" not in policy["allowed_fields"]:
            exclusion_reasons["source_refs_not_allowed_for_task"] += 1
            continue
        if lane not in allowed_lanes:
            excluded_lane_counts[lane] += 1
            continue
        projected.append(_safe_unit_projection(unit, include_source_ref=True))

    if task == "review":
        projected = [_safe_unit_projection(unit, include_source_ref=True) for unit in units]
        excluded_lane_counts.clear()
        exclusion_reasons.clear()

    return {
        "task": task,
        "allowed_fields": policy["allowed_fields"],
        "allowed_source_lanes": policy["allowed_source_lanes"],
        "projected_unit_count": len(projected),
        "projected_lane_counts": _count_by_lane(projected),
        "excluded_lane_counts": dict(sorted(excluded_lane_counts.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "projected_units": projected,
    }


def _bundle_blockers(bundle: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if bundle.get("schema") != INPUT_SCHEMA:
        blockers.append("input_schema_mismatch")
    classification = bundle.get("classification") if isinstance(bundle.get("classification"), dict) else {}
    safety = bundle.get("safety") if isinstance(bundle.get("safety"), dict) else {}
    required_false = [
        (classification, "install_allowed", "classification_install_allowed"),
        (classification, "runtime_install_allowed", "classification_runtime_install_allowed"),
        (classification, "production_default", "classification_production_default"),
        (classification, "canonical_pointer_written", "classification_canonical_pointer_written"),
        (safety, "canonical_truth_written", "safety_canonical_truth_written"),
        (safety, "official_score_allowed", "safety_official_score_allowed"),
        (safety, "installed_runtime_supply", "safety_installed_runtime_supply"),
        (safety, "release_truth_claimed", "safety_release_truth_claimed"),
    ]
    for scope, key, reason in required_false:
        if scope.get(key) is True:
            blockers.append(reason)
    if safety.get("production_write_count", 0) not in (0, None):
        blockers.append("safety_production_write_count_nonzero")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("classification_candidate_review_flags_invalid")
    if classification.get("runtime_supply_candidate") is not True or classification.get("regression_required") is not True:
        blockers.append("classification_runtime_supply_regression_flags_invalid")
    return blockers


def _unit_blockers(units: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for unit in units:
        unit_id = str(unit.get("unit_id") or "unknown")
        if unit.get("install_allowed") is True:
            blockers.append(f"unit_install_allowed:{unit_id}")
        if unit.get("runtime_install_allowed") is True:
            blockers.append(f"unit_runtime_install_allowed:{unit_id}")
        if unit.get("production_default") is True:
            blockers.append(f"unit_production_default:{unit_id}")
        if unit.get("candidate_only") is not True or unit.get("review_only") is not True:
            blockers.append(f"unit_candidate_review_flags_invalid:{unit_id}")
        source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
        if not all(source_ref.get(key) for key in ("source_lane", "source_path", "record_id", "span", "span_hash")):
            blockers.append(f"unit_source_trace_missing:{unit_id}")
        if source_ref.get("source_lane") != unit.get("missing_lane"):
            blockers.append(f"unit_lane_mismatch:{unit_id}")
    return blockers


def run_runtime_supply_regression(*, runtime_supply_candidate: dict[str, Any]) -> dict[str, Any]:
    units = [unit for unit in runtime_supply_candidate.get("supply_units") or [] if isinstance(unit, dict)]
    blockers = _bundle_blockers(runtime_supply_candidate) + _unit_blockers(units)
    projections = [_task_projection(task, units) for task in TASK_POLICIES]
    verdict = "FAIL" if blockers else "PASS"
    return {
        "schema": SCHEMA,
        "input_schema": runtime_supply_candidate.get("schema"),
        "input_version": runtime_supply_candidate.get("version"),
        "verdict": verdict,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_supply_regression": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_supply_unit_count": len(units),
            "blocker_count": len(blockers),
            "task_projection_count": len(projections),
            "grading_projected_unit_count": next(p["projected_unit_count"] for p in projections if p["task"] == "grading"),
            "rag_answer_projected_unit_count": next(
                p["projected_unit_count"] for p in projections if p["task"] == "rag_answer"
            ),
            "tutoring_projected_unit_count": next(
                p["projected_unit_count"] for p in projections if p["task"] == "tutoring"
            ),
            "next_action_projected_unit_count": next(
                p["projected_unit_count"] for p in projections if p["task"] == "next_action"
            ),
        },
        "blockers": blockers,
        "task_projections": projections,
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
    parser.add_argument("--runtime-supply-candidate", type=Path, default=DEFAULT_RUNTIME_SUPPLY_CANDIDATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = run_runtime_supply_regression(runtime_supply_candidate=_read_json(args.runtime_supply_candidate))
    output = args.output_dir / "runtime_supply_regression.json"
    _write_json(output, report)
    print(json.dumps({"out": str(output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
