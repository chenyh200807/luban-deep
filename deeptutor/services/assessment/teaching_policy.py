from __future__ import annotations

from typing import Any


def build_teaching_policy_seed(
    *,
    session: dict[str, Any],
    answers: dict[str, str],
    score_report: dict[str, Any],
    time_spent_seconds: int,
) -> dict[str, Any]:
    questions = list(session.get("questions") or [])
    scored_questions = [item for item in questions if item.get("scored", True)]
    profile_questions = [item for item in questions if not item.get("scored", True)]
    answered_count = sum(1 for item in questions if str(answers.get(item.get("question_id"), "")).strip())
    seconds_per_question = float(time_spent_seconds or 0) / max(len(questions), 1)
    confidence, low_reasons = _measurement_confidence(
        answered_count=answered_count,
        total_count=len(questions),
        seconds_per_question=seconds_per_question,
    )
    profile_values = _profile_values(profile_questions, answers)
    priority_chapters = [
        item.get("name")
        for item in list(score_report.get("priority_chapters") or [])[:5]
        if item.get("name")
    ]
    recommended_action = (
        profile_values.get("pressure_response")
        or ("targeted_micro_drill" if int(score_report.get("score_pct") or 0) < 60 else "worked_example")
    )
    return {
        "version": "assessment_seed_v1",
        "recommended_action": recommended_action,
        "pace": _pace(profile_values, seconds_per_question),
        "scaffold_level": _scaffold_level(score_report, profile_values),
        "review_rhythm": profile_values.get("review_rhythm") or "same_day_review",
        "priority_chapters": priority_chapters,
        "measurement_confidence": confidence,
        "low_confidence_reasons": low_reasons,
        "source_assessment": {
            "quiz_id": session.get("quiz_id"),
            "blueprint_version": session.get("blueprint_version"),
            "scored_count": len(scored_questions),
            "profile_count": len(profile_questions),
            "score_pct": int(score_report.get("score_pct") or 0),
        },
    }


def _profile_values(profile_questions: list[dict[str, Any]], answers: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for question in profile_questions:
        key = str(answers.get(question.get("question_id"), "")).strip().upper()
        option_values = dict(question.get("option_values") or {})
        if key and option_values.get(key):
            values[str(question.get("profile_topic") or question.get("section_id") or "")] = str(option_values[key])
    return values


def _measurement_confidence(
    *,
    answered_count: int,
    total_count: int,
    seconds_per_question: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if answered_count < total_count:
        reasons.append("partial_submission")
    if seconds_per_question and seconds_per_question < 3:
        reasons.append("too_fast")
    if answered_count == 0:
        reasons.append("blank_submission")
    if reasons:
        return "low", reasons
    if seconds_per_question < 8:
        return "medium", ["fast_completion"]
    return "high", []


def _pace(profile_values: dict[str, str], seconds_per_question: float) -> str:
    if profile_values.get("planning_style") == "needs_pace_support":
        return "pace_recovery"
    if seconds_per_question < 8:
        return "slow_down_checkpoints"
    return "steady"


def _scaffold_level(score_report: dict[str, Any], profile_values: dict[str, str]) -> str:
    if profile_values.get("pressure_response") == "minimal_scaffold":
        return "stepwise"
    score = int(score_report.get("score_pct") or 0)
    if score < 50:
        return "high"
    if score < 75:
        return "medium"
    return "light"
