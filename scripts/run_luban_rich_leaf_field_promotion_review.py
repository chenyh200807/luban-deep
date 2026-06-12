#!/usr/bin/env python3
"""Review RichLeaf field candidates for source-backed context-pack consumption.

This is still a workbench artifact. It promotes field claim status inside a
review-only candidate batch so context-pack smoke tests can exercise the rich
fields, but it does not install runtime supply, write canonical truth, or grant
official scoring authority.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import validate_rich_leaf_artifact


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_artifact_candidates_20260612/rich_leaf_artifact_candidates.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
SCHEMA = "luban_rich_leaf_field_promotion_review.v1"

SOURCE_BACKED_LANES = {"textbook", "standard", "lecture"}
SOURCE_BACKED_FIELD_FAMILIES = {"concepts", "definitions", "rules", "procedures", "numeric_constraints"}
PROMOTABLE_FIELD_FAMILIES = (
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "negative_evidence",
    "teaching_cards",
    "rubric_link_index",
    "common_mistakes",
    "exam_patterns",
    "learner_memory_event_templates",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _field_id(field: dict[str, Any], family: str, index: int) -> str:
    return str(field.get("field_id") or field.get("id") or f"{family}_{index}")


def _source_ref_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for ref in artifact.get("source_refs") or []:
        if isinstance(ref, dict) and ref.get("source_ref_id"):
            refs[str(ref["source_ref_id"])] = ref
    return refs


def _source_lanes_for_field(field: dict[str, Any], refs: dict[str, dict[str, Any]]) -> set[str]:
    lanes: set[str] = set()
    for ref_id in field.get("source_ref_ids") or []:
        ref = refs.get(str(ref_id))
        if isinstance(ref, dict) and ref.get("source_lane"):
            lanes.add(str(ref["source_lane"]))
    return lanes


def _iter_family_fields(artifact: dict[str, Any], family: str) -> list[dict[str, Any]]:
    value = artifact.get(family)
    if isinstance(value, list):
        return [field for field in value if isinstance(field, dict)]
    if family == "common_mistakes" and isinstance(value, dict):
        fields: list[dict[str, Any]] = []
        for key in ("observed_mistakes", "hypothesized_mistakes"):
            for field in value.get(key) or []:
                if isinstance(field, dict):
                    fields.append(field)
        return fields
    return []


def _promotion_decision(
    *,
    family: str,
    field: dict[str, Any],
    source_lanes: set[str],
) -> tuple[str, str]:
    if field.get("claim_status") != "candidate_only":
        return str(field.get("claim_status") or "candidate_only"), "unchanged_non_candidate_status"
    if not source_lanes:
        return "candidate_only", "missing_source_ref_lane"
    if family in SOURCE_BACKED_FIELD_FAMILIES and source_lanes <= SOURCE_BACKED_LANES:
        return "source_backed", "source_lane_supports_knowledge_field"
    if (
        family == "teaching_cards"
        and source_lanes <= SOURCE_BACKED_LANES
        and field.get("not_for_official_scoring") is True
        and (field.get("source_excerpt") or field.get("card"))
    ):
        return "source_backed", "source_backed_teaching_card_not_for_official_scoring"
    if (
        family == "exam_patterns"
        and source_lanes == {"question"}
        and field.get("knowledge_source_allowed") is False
    ):
        return "assessment_evidence", "question_lane_exam_pattern_only"
    return "candidate_only", "not_promotable_under_current_taxonomy"


def _set_field_status(field: dict[str, Any], status: str) -> None:
    field["claim_status"] = status
    field["review_only"] = True
    if status == "candidate_only":
        field["candidate_only"] = True
    else:
        field["candidate_only"] = False


def review_field_promotions(*, artifact_candidates: dict[str, Any]) -> dict[str, Any]:
    raw_artifacts = [
        artifact
        for artifact in artifact_candidates.get("rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    promoted_artifacts: list[dict[str, Any]] = []
    promotion_decisions: list[dict[str, Any]] = []
    validation_reports: list[dict[str, Any]] = []
    blockers: list[str] = []
    status_counts: Counter[str] = Counter()

    for raw_artifact in raw_artifacts:
        artifact = copy.deepcopy(raw_artifact)
        refs = _source_ref_index(artifact)
        for family in PROMOTABLE_FIELD_FAMILIES:
            for index, field in enumerate(_iter_family_fields(artifact, family)):
                fid = _field_id(field, family, index)
                before = str(field.get("claim_status") or "candidate_only")
                source_lanes = _source_lanes_for_field(field, refs)
                after, rationale = _promotion_decision(family=family, field=field, source_lanes=source_lanes)
                _set_field_status(field, after)
                status_counts[after] += 1
                promotion_decisions.append(
                    {
                        "artifact_id": artifact.get("artifact_id"),
                        "leaf_id": artifact.get("leaf_id"),
                        "field_id": fid,
                        "family": family,
                        "from_status": before,
                        "to_status": after,
                        "source_lanes": sorted(source_lanes),
                        "rationale": rationale,
                        "runtime_install_allowed": False,
                        "release_truth_claimed": False,
                    }
                )

        report = validate_rich_leaf_artifact(artifact).to_dict()
        validation_reports.append({"artifact_id": artifact.get("artifact_id"), "leaf_id": artifact.get("leaf_id"), **report})
        if report["ok"]:
            promoted_artifacts.append(artifact)
        else:
            blockers.extend([f"{artifact.get('artifact_id')}:{blocker}" for blocker in report["blockers"]])

    return {
        "schema": SCHEMA,
        "input_schema": artifact_candidates.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "field_promotion_review": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_artifact_candidate_count": len(raw_artifacts),
            "promoted_artifact_candidate_count": len(promoted_artifacts),
            "promotion_decision_count": len(promotion_decisions),
            "source_backed_field_count": status_counts["source_backed"],
            "assessment_evidence_field_count": status_counts["assessment_evidence"],
            "still_candidate_only_field_count": status_counts["candidate_only"],
            "validation_failure_count": len(blockers),
        },
        "promoted_rich_leaf_artifact_candidates": promoted_artifacts,
        "promotion_decisions": promotion_decisions,
        "validation_reports": validation_reports,
        "blockers": blockers,
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
    parser.add_argument("--artifact-candidates", type=Path, default=DEFAULT_ARTIFACT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = review_field_promotions(artifact_candidates=_read_json(args.artifact_candidates))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
