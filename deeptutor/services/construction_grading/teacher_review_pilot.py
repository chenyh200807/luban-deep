"""Stream B — teacher-review pilot over 3-5 quasi-real student answers.

End-to-end closed loop, ALL via REUSED capabilities (no second logic, no new table,
no production runtime, no RAG-in-grading):

    Best-Quality 4-model draft (best_quality_ai_draft.best_quality_for_golden)
      -> teacher review JSON (quasi-real QA reviewer decisions, clearly labelled)
      -> writeback preview (teacher_review_writeback.build_teacher_review_writeback, dry_run)
      -> Learning-Brain read-back (learning_brain_synthesis.synthesize_learner_profile)

Hard constraints honored here (mirrors the upstream modules, does NOT re-derive):
  - dry_run=True always: NO real user / production DB is touched.
  - teacher-final is the write authority: every point in the review JSON carries an
    explicit ``review_action`` (confirm / reject / override) — the teacher decision
    overrides the AI draft.
  - high_risk (and unsupported) points that are NOT teacher-confirmed never become
    mastery — enforced upstream by ``teacher_review_writeback._mastery``; we only
    feed the review and read the result back.
  - "quasi-real": answers come from the golden fixture eval_samples (real exam-style
    student answers curated for the benchmark); teacher decisions are authored by us
    as a stand-in QA reviewer and are explicitly flagged ``reviewer_is_synthetic``.
    We do NOT impersonate a named human.

This module owns NO grading authority: adjudication lives in best_quality_ai_draft,
mastery/writeback lives in teacher_review_writeback, synthesis lives in
learning_brain_synthesis. This file only orchestrates them and shapes the
quasi-real review JSON.
"""
from __future__ import annotations

from typing import Any, Callable

from deeptutor.services.construction_grading.best_quality_ai_draft import (
    best_quality_for_golden,
)
from deeptutor.services.construction_grading.learning_brain_synthesis import (
    synthesize_learner_profile,
)
from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)

# review_action vocabulary (mirrors teacher_review_writeback._disposition).
CONFIRM = "confirm"
REJECT = "reject"
OVERRIDE = "override"

# Each pilot subject names the golden case, the eval sample, and a teacher-decision
# policy. The teacher policy is a deterministic function of the AI draft's point
# result, so the pilot is reproducible without hand-coding per-point reviews.
PilotTeacherPolicy = Callable[[dict[str, Any]], dict[str, Any]]


def confirm_ai(point: dict[str, Any]) -> dict[str, Any]:
    """Teacher agrees with the AI draft as-is (the common case for a clear hit/miss).

    A high_risk / unsupported point that is merely *confirmed* still does NOT earn
    mastery upstream — confirm only ratifies the AI label, it is not an override.
    """
    return {"review_action": CONFIRM}


def reject_overcredit(point: dict[str, Any]) -> dict[str, Any]:
    """Teacher catches an AI '放水' (over-credit): downgrade the point to miss.

    Used on a high_risk / partial point the AI leaned generous on. Result: not a full
    hit -> never mastery, and an error_event is emitted for the learner.
    """
    return {
        "review_action": REJECT,
        "teacher_hit": "miss",
        "teacher_score": 0,
        "teacher_note": "复核：AI 放水，近义/不完整不给分，按教材原文踩字判 miss",
    }


def override_upgrade(point: dict[str, Any]) -> dict[str, Any]:
    """Teacher manually upgrades a point to a full hit (higher authority).

    Override is the only path that can lift an AI high_risk point into mastery.
    """
    return {
        "review_action": OVERRIDE,
        "teacher_hit": "hit",
        "teacher_score": point.get("max_score"),
        "teacher_note": "复核：教师确认本点已达采分标准，覆盖 AI 判定为满分命中",
    }


def _point_review(point: dict[str, Any], policy: PilotTeacherPolicy) -> dict[str, Any]:
    """Shape one AI draft point + teacher decision into a review_json point row.

    The AI fields are copied verbatim from the Best-Quality draft (single source);
    the teacher fields come from the chosen policy.
    """
    base = {
        "point_id": point.get("point_id"),
        "label": point.get("expected_point_label") or point.get("label"),
        "policy_type": point.get("policy_type"),
        "max_score": point.get("max_score"),
        "ai_hit": point.get("hit"),
        "ai_score": point.get("score"),
        "auto_certified": bool(point.get("auto_certified")),
        "high_risk_review": bool(point.get("high_risk_review")),
        "unsupported": bool(point.get("unsupported")),
    }
    decision = policy(point)
    base.update(decision)
    return base


def build_review_json(
    draft: dict[str, Any],
    *,
    policy_by_point: dict[str, PilotTeacherPolicy] | None = None,
    default_policy: PilotTeacherPolicy = confirm_ai,
) -> dict[str, Any]:
    """Turn a Best-Quality draft + per-point teacher policies into a review JSON.

    ``policy_by_point`` overrides the teacher decision for specific point_ids; every
    other point uses ``default_policy`` (confirm). Always teacher_reviewed=True so the
    writeback treats this as teacher-final authority. ``reviewer_is_synthetic`` marks
    the QA reviewer as a stand-in (we never impersonate a named human).
    """
    policy_by_point = policy_by_point or {}
    point_reviews = [
        _point_review(point, policy_by_point.get(point.get("point_id"), default_policy))
        for point in draft.get("point_results", [])
    ]
    return {
        "case_id": draft.get("question_id"),
        "student_id": draft.get("student_id"),
        "engine": draft.get("engine") or "best_quality_4model",
        "teacher_reviewed": True,
        "reviewer_is_synthetic": True,
        "reviewer_note": "quasi-real pilot: 学生作答取自 golden eval_samples，教师判定由 QA 占位审核者作出（非真人）",
        "point_reviews": point_reviews,
    }


def run_pilot_subject(
    golden_case: dict[str, Any],
    student_id: str,
    *,
    policy_by_point: dict[str, PilotTeacherPolicy] | None = None,
    default_policy: PilotTeacherPolicy = confirm_ai,
) -> dict[str, Any]:
    """Run one subject through the full closed loop. dry_run is forced True.

    Returns the draft, review_json, and writeback result for this subject. No real
    user / DB is touched (dry_run=True, learner_state_service=None).
    """
    draft = best_quality_for_golden(golden_case, student_id)
    review_json = build_review_json(
        draft, policy_by_point=policy_by_point, default_policy=default_policy
    )
    writeback = build_teacher_review_writeback(review_json, dry_run=True)
    return {
        "case_id": golden_case.get("case_id"),
        "student_id": student_id,
        "draft": draft,
        "review_json": review_json,
        "writeback": writeback,
    }


def run_pilot(subjects: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the whole pilot and synthesize a Learning-Brain read-back.

    *subjects* is a list of ``{"golden_case", "student_id", "policy_by_point"?,
    "default_policy"?}``. Returns ``{"subjects": [...], "synthesis": {...}}`` where
    synthesis is produced by the REUSED ``synthesize_learner_profile`` from the
    teacher-final learning_evidence payloads.
    """
    results = [
        run_pilot_subject(
            s["golden_case"],
            s["student_id"],
            policy_by_point=s.get("policy_by_point"),
            default_policy=s.get("default_policy", confirm_ai),
        )
        for s in subjects
    ]
    payloads = [r["writeback"]["learning_evidence_payload"] for r in results]
    synthesis = synthesize_learner_profile(payloads)
    return {"subjects": results, "synthesis": synthesis}


__all__ = [
    "build_review_json",
    "confirm_ai",
    "reject_overcredit",
    "override_upgrade",
    "run_pilot",
    "run_pilot_subject",
]
