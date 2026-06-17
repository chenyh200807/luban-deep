#!/usr/bin/env python3
"""Assemble RichLeafArtifact candidates from review-only rich field candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import (
    source_span_hash,
    validate_rich_leaf_artifact,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_candidates_20260612/rich_leaf_field_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_artifact_candidates_20260612"
SCHEMA = "luban_rich_leaf_artifact_candidate_batch.v1"
BUNDLE_VERSION = "v_rich_leaf_artifact_candidate_20260612"

FIELD_FAMILIES = (
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


def _hash_seed(*parts: Any) -> str:
    seed = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _source_ref_id(trace: dict[str, Any]) -> str:
    return f"src_{_hash_seed(trace.get('source_lane'), trace.get('record_id'), trace.get('span'))}"


def _source_ref_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    span = str(trace.get("span") or "")
    source_lane = str(trace.get("source_lane") or "")
    return {
        "source_ref_id": _source_ref_id(trace),
        "source_registry_id": "rich_leaf_reviewed_source_refs",
        "source_dataset_id": f"docs2026_{source_lane or 'unknown'}",
        "source_version": "2026.0",
        "extractor_version": "rich_leaf_field_candidate_compiler.v1",
        "source_lane": source_lane,
        "path": trace.get("source_path"),
        "record_id": trace.get("record_id"),
        "span": span,
        "span_hash": source_span_hash(span),
        "candidate_only": True,
        "review_only": True,
    }


def _field_from_candidate(candidate: dict[str, Any], source_ref_id: str) -> dict[str, Any]:
    family = str(candidate.get("family") or "")
    field = {
        "field_id": candidate.get("field_candidate_id"),
        "claim_status": "candidate_only",
        "source_ref_ids": [source_ref_id],
        "candidate_only": True,
        "review_only": True,
        "derived_from_candidate_id": candidate.get("derived_from_candidate_id"),
        "audit_item_id": candidate.get("audit_item_id"),
    }
    for key, value in candidate.items():
        if key in {
            "field_candidate_id",
            "family",
            "leaf_id",
            "artifact_id",
            "claim_status",
            "candidate_only",
            "review_only",
            "runtime_install_allowed",
            "release_truth_claimed",
            "source_ref_trace",
        }:
            continue
        field[key] = value
    if family == "rules" and "statement" not in field:
        field["statement"] = field.get("rule_text")
    if family == "definitions" and "definition" not in field:
        field["definition"] = field.get("text")
    if family == "procedures" and "steps" not in field:
        field["steps"] = [field.get("procedure_text")] if field.get("procedure_text") else []
    if family == "teaching_cards" and "card" not in field:
        field["card"] = field.get("source_excerpt")
    return {k: v for k, v in field.items() if v is not None}


def _append_field(artifact: dict[str, Any], family: str, field: dict[str, Any]) -> None:
    if family == "common_mistakes":
        mistake_group = str(field.pop("mistake_group", "hypothesized_mistakes") or "hypothesized_mistakes")
        if mistake_group not in {"observed_mistakes", "hypothesized_mistakes"}:
            mistake_group = "hypothesized_mistakes"
        artifact["common_mistakes"][mistake_group].append(field)
        return
    artifact[family].append(field)


def _empty_artifact(*, leaf_id: str, artifact_id: str) -> dict[str, Any]:
    artifact = {
        "artifact_id": f"{artifact_id}:rich_leaf_candidate",
        "leaf_id": leaf_id,
        "bundle_version": BUNDLE_VERSION,
        "candidate_status": "reviewed_candidate",
        "source_refs": [],
        "concepts": [],
        "definitions": [],
        "rules": [],
        "procedures": [],
        "numeric_constraints": [],
        "negative_evidence": [],
        "teaching_cards": [],
        "rubric_link_index": [],
        "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
        "exam_patterns": [],
        "learner_memory_event_templates": [],
    }
    return artifact


def _valid_field_candidate(candidate: dict[str, Any]) -> bool:
    trace = candidate.get("source_ref_trace") if isinstance(candidate.get("source_ref_trace"), dict) else {}
    return (
        bool(candidate.get("field_candidate_id"))
        and bool(candidate.get("leaf_id"))
        and bool(candidate.get("artifact_id"))
        and str(candidate.get("family") or "") in FIELD_FAMILIES
        and candidate.get("claim_status") == "candidate_only"
        and candidate.get("candidate_only") is True
        and candidate.get("review_only") is True
        and candidate.get("runtime_install_allowed") is False
        and candidate.get("release_truth_claimed") is False
        and bool(trace.get("source_lane"))
        and bool(trace.get("record_id"))
        and bool(trace.get("span"))
    )


def _artifact_family_count(artifact: dict[str, Any], family: str) -> int:
    value = artifact.get(family)
    if isinstance(value, list):
        return len([field for field in value if isinstance(field, dict)])
    if family == "common_mistakes" and isinstance(value, dict):
        return sum(
            len([field for field in value.get(group) or [] if isinstance(field, dict)])
            for group in ("observed_mistakes", "hypothesized_mistakes")
        )
    return 0


def assemble_artifact_candidates(*, field_candidates: dict[str, Any]) -> dict[str, Any]:
    raw_candidates = [
        candidate
        for candidate in field_candidates.get("field_candidates") or []
        if isinstance(candidate, dict)
    ]
    skipped: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in raw_candidates:
        if not _valid_field_candidate(candidate):
            skipped.append(
                {
                    "field_candidate_id": candidate.get("field_candidate_id"),
                    "leaf_id": candidate.get("leaf_id"),
                    "artifact_id": candidate.get("artifact_id"),
                    "reason": "invalid_field_candidate_shape",
                }
            )
            continue
        by_key[(str(candidate["leaf_id"]), str(candidate["artifact_id"]))].append(candidate)

    artifacts: list[dict[str, Any]] = []
    validation_reports: list[dict[str, Any]] = []
    blockers: list[str] = []
    for (leaf_id, artifact_id), candidates in sorted(by_key.items()):
        artifact = _empty_artifact(leaf_id=leaf_id, artifact_id=artifact_id)
        source_refs_by_id: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            trace = candidate["source_ref_trace"]
            source_ref = _source_ref_from_trace(trace)
            source_ref_id = source_ref["source_ref_id"]
            source_refs_by_id[source_ref_id] = source_ref
            family = str(candidate["family"])
            _append_field(artifact, family, _field_from_candidate(candidate, source_ref_id))
        artifact["source_refs"] = list(source_refs_by_id.values())
        report = validate_rich_leaf_artifact(artifact).to_dict()
        validation_reports.append({"leaf_id": leaf_id, "artifact_id": artifact["artifact_id"], **report})
        if report["ok"]:
            artifacts.append(artifact)
        else:
            blockers.extend([f"{artifact['artifact_id']}:{blocker}" for blocker in report["blockers"]])

    by_family: Counter[str] = Counter()
    for artifact in artifacts:
        for family in FIELD_FAMILIES:
            by_family[family] += _artifact_family_count(artifact, family)
    return {
        "schema": SCHEMA,
        "field_candidate_schema": field_candidates.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "rich_leaf_artifact_candidate_batch": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_field_candidate_count": len(raw_candidates),
            "artifact_candidate_count": len(artifacts),
            "validation_failure_count": len(blockers),
            "skipped_field_candidate_count": len(skipped),
            "field_family_counts": dict(sorted(by_family.items())),
        },
        "rich_leaf_artifact_candidates": artifacts,
        "validation_reports": validation_reports,
        "skipped_field_candidates": skipped,
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
    parser.add_argument("--field-candidates", type=Path, default=DEFAULT_FIELD_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = assemble_artifact_candidates(field_candidates=_read_json(args.field_candidates))
    output = args.output_dir / "rich_leaf_artifact_candidates.json"
    _write_json(output, report)
    print(json.dumps({"out": str(output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
