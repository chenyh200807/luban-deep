"""Stream C — teacher-review writeback preview (dry-run first, no second memory).

A QA reviewer adjudicates an AI draft (``engine="best_quality_4model"``) point by
point. This module turns that review JSON into the EXISTING learning_evidence
payload — it owns NO grading authority and creates NO new table / no second
memory store. It reuses:

  - ``CaseGradingResult`` / ``CaseRubricItemResult`` (schema.py)
  - ``build_learning_evidence_payload`` (learning_evidence.py)
  - ``write_grading_error_events`` (writeback.py) — only when writeback is
    explicitly enabled AND a learner_state_service is supplied (test-env).

Authority rules (hard):
  - A point becomes confident MASTERY evidence only when its final disposition is
    a full hit that is either trusted-adjudication-confirmed or AI-auto_certified,
    and it is NOT high_risk / unsupported — UNLESS a trusted override upgrades it.
  - high_risk / unsupported points are downweighted: awarded_score=0, status
    never ``full``, mastery_eligible=False. They are never counted as correct.
  - ``review_action == "override"`` -> teacher_hit / teacher_score replace AI's;
    a teacher override is the higher authority and may upgrade an AI high_risk
    point to mastery.
  - Default ``dry_run=True``: pure conversion, returns the payload + write_plan,
    never calls the DB. ``learner_state_service=None`` is always safe.
"""
from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)
from deeptutor.services.construction_grading.schema import (
    CaseGradingResult,
    CaseRubricItemResult,
    GradingErrorEvent,
)

_HIT = "hit"
_PARTIAL = "partial"
_MISS = "miss"
_VALID_HITS = (_HIT, _PARTIAL, _MISS)


def build_teacher_review_writeback(
    review_json: dict[str, Any],
    *,
    dry_run: bool = True,
    learner_state_service: Any | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Convert a teacher-review JSON into the existing learning_evidence payload.

    Returns a dict with ``dry_run``, ``learning_evidence_payload`` and
    ``write_plan`` (one row per scoring point). When ``dry_run`` is False AND a
    ``learner_state_service`` is supplied, the payload is also persisted through
    the existing ``write_grading_error_events`` authority (test-env only).
    """
    case_id = _text(review_json.get("case_id"))
    student_id = _text(review_json.get("student_id"))
    engine = _text(review_json.get("engine"))
    point_reviews = [pr for pr in list(review_json.get("point_reviews") or []) if isinstance(pr, dict)]

    write_plan = [_disposition(pr) for pr in point_reviews]
    point_events = [_point_event(row) for row in write_plan]
    rubric_items = [_rubric_item(row) for row in write_plan]
    error_events = [event for event in (_error_event(row) for row in write_plan) if event is not None]

    score_awarded = round(sum(item.awarded_score for item in rubric_items), 3)
    max_score = round(sum(item.max_score for item in rubric_items), 3)
    review_audit = _review_audit(review_json)
    trusted_adjudication = _trusted_adjudication(review_json, review_audit)
    trusted_reviewed = bool(trusted_adjudication.get("eligible"))
    teacher_reviewed = bool(review_json.get("teacher_reviewed") is True)
    final_adjudication_result = {
        "case_id": case_id,
        "student_id": student_id,
        "teacher_reviewed": teacher_reviewed,
        "trusted_adjudication": trusted_adjudication,
        "teacher_review_audit": review_audit,
        "score_awarded": score_awarded,
        "max_score": max_score,
        "points": point_events,
    }

    grading_result = CaseGradingResult(
        question_id=case_id,
        grading_mode="curated_rubric",
        score_awarded=score_awarded,
        max_score=max_score,
        rubric_items=rubric_items,
        error_events=error_events,
        next_training_signal={
            "grading_source": "teacher_review",
            "adjudication_source": "trusted_adjudication",
            "engine": engine or "best_quality_4model",
            "concept": _training_concept(write_plan),
            "focus": _training_concept(write_plan),
            "case_id": case_id,
            "student_id": student_id,
            "teacher_reviewed": teacher_reviewed,
            "trusted_adjudication": trusted_adjudication,
            "teacher_review_audit": review_audit,
            "teacher_review_points": point_events,
            "final_adjudication_result": final_adjudication_result,
            # Compatibility: old Learning Brain readers still look for this key.
            "teacher_final_grading_result": final_adjudication_result,
        },
    )

    payload = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=_turn_id(case_id, student_id),
        session_id=student_id,
    )
    if trusted_reviewed:
        _mark_teacher_reviewed_quality(payload, trusted_adjudication)

    result: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "case_id": case_id,
        "student_id": student_id,
        "engine": engine or "best_quality_4model",
        "learning_evidence_payload": payload,
        "write_plan": write_plan,
        "mastery_point_ids": [row["point_id"] for row in write_plan if row["mastery_eligible"]],
    }

    if dry_run:
        return result

    if not trusted_reviewed:
        result["writeback_count"] = 0
        result["writeback_skipped_reason"] = "trusted_adjudication_required"
        return result

    write_user_id = _text(user_id) or student_id
    if not _is_safe_qa_user_id(write_user_id):
        result["writeback_count"] = 0
        result["writeback_skipped_reason"] = "qa_user_id_required"
        return result

    if learner_state_service is None:
        result["writeback_count"] = 0
        result["writeback_skipped_reason"] = "no_learner_state_service"
        return result

    from deeptutor.services.construction_grading.writeback import write_grading_error_events

    count = write_grading_error_events(
        learner_state_service=learner_state_service,
        user_id=write_user_id,
        grading_result=grading_result,
        source_id=_turn_id(case_id, student_id),
        source_bot_id="construction-exam",
        include_success_events=True,
    )
    result["writeback_count"] = int(count)
    return result


def _disposition(point_review: dict[str, Any]) -> dict[str, Any]:
    """Resolve final hit/score + mastery eligibility for one reviewed point."""
    point_id = _text(point_review.get("point_id"))
    label = _text(point_review.get("label"))
    policy_type = _text(point_review.get("policy_type"))
    max_score = _to_float(point_review.get("max_score"))
    action = _text(point_review.get("review_action")).lower()

    ai_hit = _norm_hit(point_review.get("ai_hit"))
    ai_score = _to_float(point_review.get("ai_score"))
    auto_certified = bool(point_review.get("auto_certified"))
    high_risk = bool(point_review.get("high_risk_review") or point_review.get("high_risk"))
    unsupported = bool(point_review.get("unsupported"))

    teacher_hit = _norm_hit(point_review.get("teacher_hit"))
    teacher_score = point_review.get("teacher_score")
    teacher_note = _text(point_review.get("teacher_note"))
    evidence_span = _text(point_review.get("evidence_span"))
    source = _text(point_review.get("source")) or "teacher_final"

    is_override = action == "override"

    if is_override:
        authority = "teacher_override"
        final_hit = teacher_hit or ai_hit
        final_score = _to_float(teacher_score) if teacher_score is not None else ai_score
    elif action == "reject":
        # Teacher rejected the AI hit: drop to miss, never mastery.
        authority = "teacher_reject"
        final_hit = teacher_hit or _MISS
        final_score = _to_float(teacher_score) if teacher_score is not None else 0.0
    else:  # confirm (or unknown) -> AI draft stands
        authority = "teacher_confirm" if action == "confirm" else "ai_draft"
        final_hit = ai_hit
        final_score = ai_score

    mastery_eligible, disposition = _mastery(
        final_hit=final_hit,
        is_override=is_override,
        action=action,
        auto_certified=auto_certified,
        high_risk=high_risk,
        unsupported=unsupported,
    )

    # Confident mastery -> award the teacher/AI score; otherwise downweight to 0.
    awarded_score = round(min(final_score, max_score), 3) if mastery_eligible else 0.0

    return {
        "point_id": point_id,
        "label": label,
        "policy_type": policy_type,
        "max_score": max_score,
        "authority": authority,
        "ai_hit": ai_hit,
        "ai_score": ai_score,
        "teacher_hit": teacher_hit,
        "teacher_score": _to_float(teacher_score) if teacher_score is not None else None,
        "teacher_note": teacher_note,
        "evidence_span": evidence_span,
        "source": source,
        "review_action": action,
        "high_risk_review": high_risk,
        "unsupported": unsupported,
        "final_hit": final_hit,
        "final_score": round(final_score, 3),
        "awarded_score": awarded_score,
        "mastery_eligible": mastery_eligible,
        "disposition": disposition,
    }


def _mastery(
    *,
    final_hit: str,
    is_override: bool,
    action: str,
    auto_certified: bool,
    high_risk: bool,
    unsupported: bool,
) -> tuple[bool, str]:
    """Decide if a reviewed point may count as confident mastery evidence."""
    if final_hit != _HIT:
        return False, "not_a_full_hit"

    # Teacher override is the higher authority: it can upgrade an AI-flagged
    # high_risk / unsupported point to mastery once a human confirms the hit.
    if is_override:
        return True, "teacher_override_hit"

    # Non-override: a high_risk / unsupported point is downweighted and routed to
    # review — never confident mastery (guard parity with ai_draft_shadow).
    if high_risk:
        return False, "downweighted_pending_review"
    if unsupported:
        return False, "downweighted_unsupported"

    if action == "confirm" or auto_certified:
        return True, "auto_certified_hit"

    return False, "uncertified"


def _rubric_item(row: dict[str, Any]) -> CaseRubricItemResult:
    final_hit = row["final_hit"]
    if final_hit == _HIT and row["mastery_eligible"]:
        status = "full"
    elif final_hit == _PARTIAL and row["mastery_eligible"]:
        status = "partial"
    else:
        # high_risk / unsupported / miss / uncertified -> never a full credit.
        status = "miss"
    return CaseRubricItemResult(
        criterion=row["point_id"],
        max_score=row["max_score"],
        awarded_score=row["awarded_score"],
        status=status,
        keywords=[],
        evidence_text=row["evidence_span"] or row["teacher_note"],
        source_fields=["teacher_review"],
    )


def _error_event(row: dict[str, Any]) -> GradingErrorEvent | None:
    """Emit a learning-gap error event for any point that is NOT confident mastery.

    A confident full-credit mastery point carries no error signal. Everything
    else — miss, reject, high_risk/unsupported downweight, uncertified — is a
    gap the learner should revisit, so it becomes writeback-eligible evidence.
    """
    if row["mastery_eligible"] and row["final_hit"] == _HIT:
        return None
    diagnosis = row["teacher_note"] or _gap_diagnosis(row)
    return GradingErrorEvent(
        error_code=_error_code(row),
        severity=1.0 if row["final_hit"] == _MISS else 0.5,
        concept_tag=row["label"] or row["point_id"],
        evidence=row["teacher_note"],
        diagnosis=diagnosis,
    )


def _gap_diagnosis(row: dict[str, Any]) -> str:
    if row["unsupported"]:
        return "证据不支持（span 未逐字出现），降权待复核"
    if row["high_risk_review"]:
        return "高风险点，降权待复核，不计入确定 mastery"
    if row["final_hit"] == _MISS:
        return "未命中采分点"
    return "未达确定认证，待复核"


def _point_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "point_id": row["point_id"],
        "policy_type": row["policy_type"],
        "source": row["source"],
        "evidence_span": row["evidence_span"],
        "authority": row["authority"],
        "final_hit": row["final_hit"],
        "final_score": row["final_score"],
        "awarded_score": row["awarded_score"],
        "mastery_eligible": row["mastery_eligible"],
        "diagnosis": row["teacher_note"] or _gap_diagnosis(row),
    }


def _training_concept(write_plan: list[dict[str, Any]]) -> str:
    for row in write_plan:
        if row.get("mastery_eligible"):
            return _text(row.get("label") or row.get("point_id"))
    for row in write_plan:
        text = _text(row.get("label") or row.get("point_id"))
        if text:
            return text
    return ""


def review_has_trusted_adjudication(review_json: dict[str, Any]) -> bool:
    return bool(_trusted_adjudication(review_json, _review_audit(review_json)).get("eligible"))


def _mark_teacher_reviewed_quality(payload: dict[str, Any], trusted_adjudication: dict[str, Any]) -> None:
    quality = dict(payload.get("quality") or {})
    cap_reasons = [
        reason
        for reason in list(quality.get("evidence_cap_reasons") or [])
        if _text(reason) != "missing_rag_evidence"
    ]
    quality["evidence_cap_reasons"] = cap_reasons
    quality["teacher_reviewed"] = True
    quality["teacher_review_authority"] = "trusted_adjudication"
    quality["trusted_adjudication"] = {
        key: value
        for key, value in dict(trusted_adjudication or {}).items()
        if key != "eligible"
    }
    payload["quality"] = quality


def _review_audit(review_json: dict[str, Any]) -> dict[str, Any]:
    audit = {
        "review_source": _text(review_json.get("review_source")),
        "authority_label": _text(review_json.get("authority_label")),
        "reviewer_id": _text(review_json.get("reviewer_id")),
        "reviewed_at": _text(review_json.get("reviewed_at")),
        "review_duration_seconds": _to_float(review_json.get("review_duration_seconds")),
        "review_ui_version": _text(review_json.get("review_ui_version")),
    }
    # LLM-jury teacher-review substitute: carry the jury provenance into the
    # learning_evidence payload so it is never mistaken for a human teacher.
    reviewer_type = _text(review_json.get("reviewer_type"))
    if reviewer_type:
        audit["reviewer_type"] = reviewer_type
        audit["jury_models"] = list(review_json.get("jury_models") or [])
        audit["adjudication_protocol"] = _text(review_json.get("adjudication_protocol"))
        audit["confidence"] = _to_float(_first_present(review_json.get("confidence"), review_json.get("adjudication_confidence")))
        audit["conflict_status"] = _text(review_json.get("conflict_status") or "resolved")
    return audit


def _trusted_adjudication(review_json: dict[str, Any], review_audit: dict[str, Any]) -> dict[str, Any]:
    teacher_reviewed = bool(review_json.get("teacher_reviewed") is True)
    reviewer_type = _text(review_audit.get("reviewer_type")).lower()
    authority_label = _text(review_audit.get("authority_label")).lower()
    review_source = _text(review_audit.get("review_source")).lower()

    if teacher_reviewed and not reviewer_type:
        return {
            "eligible": True,
            "source": "teacher_final",
            "authority_label": authority_label or "teacher_final",
            "confidence": 1.0,
            "conflict_status": "resolved",
            "requires_human": False,
        }

    source = reviewer_type or review_source or authority_label
    confidence = _to_float(_first_present(review_audit.get("confidence"), review_json.get("confidence"), 1.0))
    conflict_status = _text(review_audit.get("conflict_status") or review_json.get("conflict_status") or "resolved").lower()
    requires_human = bool(review_json.get("requires_human"))
    if source in {"llm_jury", "ai_jury", "model_jury_teacher_review", "model_jury_teacher_final"}:
        eligible = confidence >= 0.85 and conflict_status in {"resolved", "none", "no_conflict", "not_applicable"} and not requires_human
        return {
            "eligible": eligible,
            "source": "llm_jury" if source == "model_jury_teacher_review" else source,
            "authority_label": authority_label or "model_jury_final",
            "confidence": confidence,
            "conflict_status": conflict_status,
            "requires_human": requires_human,
        }
    if source in {"operator", "operator_smoke", "operator_soak", "human_qa_teacher", "manual_qa_teacher", "teacher_final"}:
        return {
            "eligible": True,
            "source": source,
            "authority_label": authority_label or source,
            "confidence": confidence,
            "conflict_status": conflict_status or "resolved",
            "requires_human": False,
        }
    return {
        "eligible": False,
        "source": source,
        "authority_label": authority_label,
        "confidence": confidence,
        "conflict_status": conflict_status or "unresolved",
        "requires_human": True,
    }


def _error_code(row: dict[str, Any]) -> str:
    policy_type = _text(row.get("policy_type")).lower()
    if policy_type == "calculation":
        return "E09"
    if policy_type == "direction_check":
        return "E05"
    if policy_type == "list_rule":
        return "E02"
    if policy_type == "penalty_rule":
        return "E12"
    return "E03"


def _is_safe_qa_user_id(value: str) -> bool:
    user_id = _text(value).lower()
    return user_id.startswith(("qa_", "test_"))


def _norm_hit(value: Any) -> str:
    text = _text(value).lower()
    return text if text in _VALID_HITS else _MISS if text else ""


def _turn_id(case_id: str, student_id: str) -> str:
    parts = [p for p in (case_id, student_id) if p]
    return "teacher_review:" + ":".join(parts) if parts else "teacher_review"


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()
