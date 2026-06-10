from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


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


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
