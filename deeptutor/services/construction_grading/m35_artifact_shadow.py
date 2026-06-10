from __future__ import annotations

from typing import Any


def build_m35_artifact_shadow_payload(
    *,
    question_id: str,
    student_id: str,
    student_answer: str,
) -> dict[str, Any]:
    """Build the M35 scoring-artifact shadow payload.

    Shadow only: no DB/RAG/remote reads, no canonical learner truth writes, and
    no official score authority. The artifact service supplies scoring points;
    rubric_grader_v1 owns the point-match projection.
    """
    from deeptutor.services.construction_grading import (
        question_grading_artifacts,
        rubric_grader_v1,
    )
    from deeptutor.services.construction_grading.m35_status import (
        m35_artifact_shadow_blocked,
        m35_runtime_status_from_v0,
    )

    artifact = question_grading_artifacts.build_question_grading_artifact(
        str(question_id or "").strip()
    )
    status_map = m35_runtime_status_from_v0(artifact if isinstance(artifact, dict) else {})
    quality_gates = artifact.get("quality_gates") if isinstance(artifact.get("quality_gates"), dict) else {}
    base = {
        "authority": "grading_engine_m35_artifact_shadow",
        "shadow_status": "ok",
        "evaluation_tier": "shape_stub",
        "quality_claim_allowed": False,
        "verdict_ceiling": "NO-GO_OR_SHAPE_ONLY",
        "question_id": str(question_id or "").strip(),
        "student_id": str(student_id or "").strip(),
        "artifact_version": artifact.get("version_id"),
        "legacy_artifact_status": status_map["legacy_artifact_status"],
        "m35_runtime_status": status_map["m35_runtime_status"],
        "official_score_allowed": False,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "writeback_performed": False,
        "db_write_count": 0,
        "remote_write_count": 0,
        "rag_lookup_count": 0,
        "source_validity": quality_gates.get(
            "source_validity", quality_gates.get("source_refs_verified_rate")
        ),
    }
    if artifact.get("artifact_missing"):
        return {
            **base,
            "shadow_status": "artifact_missing",
            "point_matches": [],
            "teacher_review_required": True,
        }
    if m35_artifact_shadow_blocked(status_map=status_map, quality_gates=quality_gates):
        return {
            **base,
            "shadow_status": "artifact_blocked",
            "point_matches": [],
            "teacher_review_required": True,
        }

    event = rubric_grader_v1.grade_artifact_shadow(
        qid=str(question_id or "").strip(),
        student_answer=str(student_answer or ""),
        artifact=artifact,
        judge_fn=_shape_stub_judge,
        student_id=str(student_id or "").strip(),
    )
    point_matches = list((event or {}).get("point_matches") or [])
    return {
        **base,
        "point_matches": [dict(point) for point in point_matches],
        "awarded_score_shadow": (event or {}).get("awarded_score"),
        "max_score_shadow": (event or {}).get("max_score"),
        "teacher_review_required": True,
    }


def _shape_stub_judge(point: dict[str, Any], answer: str) -> dict[str, Any]:
    """Deterministic shape-only judge for shadow payload plumbing.

    This is not a quality claim. It only lets the runtime drill exercise the
    artifact/rubric point-match shape without invoking a provider or writing truth.
    """
    answer_text = str(answer or "")
    required_terms = [
        str(term).strip()
        for term in list(point.get("required_terms") or [])
        if str(term).strip()
    ]
    if required_terms and all(term in answer_text for term in required_terms):
        return {
            "status": "hit",
            "evidence_span": answer_text[:120],
            "confidence": 0.0,
            "mistake_type": "",
        }
    return {
        "status": "miss",
        "evidence_span": "",
        "confidence": 0.0,
        "mistake_type": "shape_stub_no_quality_judgment",
    }
