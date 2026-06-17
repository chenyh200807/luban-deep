from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex


_PGO_SUPPLY_DIR = Path(__file__).parent / "runtime_supply" / "v_case_rubric_scored_pgo"
_PGO_BANK_NAME = "case_rubric_scored_pgo.json"
_PGO_POINTER_NAME = "canonical_pointer.json"


@dataclass(frozen=True)
class M35ArtifactQuery:
    question_id: str
    purpose: Literal["grading", "explanation", "review_plan"]
    shape: Literal["rubric_table", "point_matches", "review_action"]
    citation_required: bool
    budget_tier: Literal["low", "medium", "high"]


def retrieve_m35_scoring_context(
    query: M35ArtifactQuery,
    *,
    artifact_store: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Read a typed M35 scoring context from a supplied artifact store.

    No RAG lookup, raw chunk return, DB write, or learner-memory write happens
    here. Missing or ungrounded artifacts fail open.
    """
    artifact = artifact_store.get(query.question_id)
    if artifact is None:
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "artifact_missing",
        }

    scoring_points = list(artifact.get("scoring_points") or [])
    source_ref_count = sum(
        len(point.get("source_refs") or [])
        for point in scoring_points
        if isinstance(point, dict)
    )

    if query.citation_required and source_ref_count == 0:
        return {
            "found": True,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "citation_required_but_missing",
        }

    quality_gates = artifact.get("quality_gates") if isinstance(artifact.get("quality_gates"), dict) else {}
    return {
        "found": True,
        "question_id": query.question_id,
        "artifact_version": artifact.get("artifact_version"),
        "purpose": query.purpose,
        "shape": query.shape,
        "budget": {"tier": query.budget_tier},
        "ground": {"source_ref_count": source_ref_count},
        "confidence": {
            "source_validity": _as_float(
                quality_gates.get("source_validity", quality_gates.get("source_refs_verified_rate"))
            ),
        },
        "scoring_points": scoring_points,
    }


def retrieve_rubric(
    query: M35ArtifactQuery,
    *,
    runtime_supply_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Retrieve a narrow KnowQL-style rubric projection from the PGO supply.

    This is a deterministic query executor, not a grader. It only verifies the
    tracked runtime supply, filters by question id, and projects already-compiled
    official-answer slices into the requested shape.
    """
    supply = _load_pgo_supply(Path(runtime_supply_dir) if runtime_supply_dir is not None else _PGO_SUPPLY_DIR)
    if supply.get("status") != "ok":
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "runtime_supply_unavailable",
            "blockers": supply.get("blockers") or [],
        }

    records = [
        record
        for record in supply.get("records", [])
        if isinstance(record, dict) and str(record.get("qid") or "") == query.question_id
    ]
    if not records:
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "artifact_missing",
        }

    source_ref_count = sum(1 for record in records if record.get("official_slice"))
    if query.citation_required and source_ref_count == 0:
        return {
            "found": True,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "citation_required_but_missing",
        }

    include_teacher_fields = query.purpose == "grading" and query.shape == "rubric_table"
    scoring_points = [
        _project_pgo_record(record, include_teacher_fields=include_teacher_fields)
        for record in records
    ]
    manifest = supply["manifest"]
    return {
        "found": True,
        "question_id": query.question_id,
        "artifact_version": manifest["namespace"],
        "purpose": query.purpose,
        "shape": query.shape,
        "budget": {"tier": query.budget_tier, "runtime": "deterministic_pgo_supply"},
        "ground": {
            "source_ref_count": source_ref_count,
            "source_schemas": manifest.get("source_schemas") or [],
            "citation_required": query.citation_required,
        },
        "confidence": {
            "source_validity": 1.0,
            "verdict_ceiling": "release_candidate_review_only",
            "status": manifest.get("status"),
            "published": manifest.get("published"),
            "production_default": manifest.get("production_default"),
        },
        "scoring_points": scoring_points,
    }


def _load_pgo_supply(slot_dir: Path) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        bundle = json.loads((slot_dir / _PGO_BANK_NAME).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - invalid supply must fail open.
        return {"status": "blocked", "blockers": [f"bank_unreadable:{type(exc).__name__}"]}
    try:
        pointer = json.loads((slot_dir / _PGO_POINTER_NAME).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - invalid supply must fail open.
        return {"status": "blocked", "blockers": [f"canonical_pointer_unreadable:{type(exc).__name__}"]}

    manifest = bundle.get("manifest") if isinstance(bundle, dict) else {}
    records = bundle.get("records") if isinstance(bundle, dict) else []
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(records, list):
        records = []
        blockers.append("records_not_list")

    actual_hash = _sha256_hex(records)
    manifest_hash = str(manifest.get("content_hash") or "")
    pointer_hash = str(pointer.get("expected_content_hash") or pointer.get("content_hash") or "")
    if not actual_hash or actual_hash != manifest_hash:
        blockers.append("content_hash_mismatch")
    if not actual_hash or actual_hash != pointer_hash:
        blockers.append("canonical_pointer_hash_mismatch")
    if manifest.get("published") is not False:
        blockers.append("published_not_false")
    if manifest.get("production_default") != "off":
        blockers.append("production_default_not_off")
    if not str(manifest.get("namespace") or "").strip():
        blockers.append("namespace_missing")
    for record in records:
        if not isinstance(record, dict):
            blockers.append("record_not_dict")
            continue
        if record.get("official_score_allowed") is True:
            blockers.append("official_score_allowed_record_present")
        if record.get("canonical_write_allowed") is True:
            blockers.append("canonical_write_allowed_record_present")

    return {
        "status": "blocked" if blockers else "ok",
        "blockers": sorted(set(blockers)),
        "manifest": manifest,
        "records": records,
    }


def _project_pgo_record(
    record: dict[str, Any],
    *,
    include_teacher_fields: bool = True,
) -> dict[str, Any]:
    projection = {
        "point_id": record.get("point_id"),
        "criterion": record.get("text"),
        "policy": record.get("policy"),
        "policy_type": record.get("policy_type"),
        "sub_type": record.get("sub_type"),
        "required_terms": list(record.get("required_terms") or []),
        "exact_term_required": bool(record.get("exact_term_required")),
        "source_schema": record.get("source_schema"),
        "source_qid": record.get("qid"),
        "official_score_allowed": record.get("official_score_allowed") is True,
        "canonical_write_allowed": record.get("canonical_write_allowed") is True,
    }
    if not include_teacher_fields:
        projection["teacher_only_fields_redacted"] = True
        projection["ground"] = {"official_answer_backed": bool(record.get("official_slice"))}
        return projection

    projection.update(
        {
            "official_slice": record.get("official_slice"),
            "official_total_score": record.get("official_total_score"),
            "official_total_score_authority": record.get("official_total_score_authority"),
            "score_authority": record.get("score_authority"),
            "per_point_score_authority": record.get("per_point_score_authority"),
            "answer_key_authority": record.get("answer_key_authority"),
            "factory_resolution_lane": record.get("factory_resolution_lane"),
        }
    )
    return projection


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
