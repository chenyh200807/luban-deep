from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.mcq import grade_mcq_submission

_CHOICE_TYPES = {
    "choice",
    "single_choice",
    "single",
    "multi_choice",
    "multiple_choice",
    "multiple",
    "judge",
    "judgment",
    "true_false",
}

_CASE_TYPES = {
    "written",
    "case",
    "case_study",
    "short_answer",
    "open_ended",
    "essay",
}


def build_deep_question_grading_result(
    question_context: dict[str, Any],
    *,
    user_answer: str,
) -> dict[str, Any] | None:
    """Build the single authoritative grading result for deep_question submissions."""

    if not isinstance(question_context, dict):
        return None
    answer = str(user_answer or "").strip()
    if not answer:
        return None

    row = _question_row_from_context(question_context)
    question_type = str(row.get("question_type") or "").strip().lower()
    if _is_choice_context(row):
        result = grade_mcq_submission(row, answer).to_dict()
        result["type"] = "mcq"
        result["authority"] = "construction_grading"
        return result
    if question_type in _CASE_TYPES:
        result = CaseGradingSkillKernel().grade(
            question_row=row,
            user_answer=answer,
            evidence_rows=[],
        ).to_dict()
        result["type"] = "case"
        result["authority"] = "construction_grading"
        result["question_type"] = question_type or "case"
        result["user_answer"] = answer
        return result
    return None


def attach_deep_question_grading_result(
    question_context: dict[str, Any],
) -> dict[str, Any]:
    """Attach construction grading result without changing deep_question's ownership."""

    context = dict(question_context or {})
    items = context.get("items") or []
    if isinstance(items, list) and items:
        graded_items: list[dict[str, Any]] = []
        result_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                graded_items.append(item)
                continue
            graded_item = dict(item)
            item_result = build_deep_question_grading_result(
                graded_item,
                user_answer=str(graded_item.get("user_answer") or "").strip(),
            )
            if item_result:
                graded_item["construction_grading_result"] = item_result
                graded_item["is_correct"] = _result_is_full_score(item_result)
                graded_item["score"] = _result_percentage_score(item_result)
                result_items.append(item_result)
            graded_items.append(graded_item)
        if result_items:
            context["items"] = graded_items
            score_awarded = sum(float(item.get("score_awarded") or 0) for item in result_items)
            max_score = sum(float(item.get("max_score") or 0) for item in result_items)
            context["construction_grading_result"] = {
                "type": "batch",
                "authority": "construction_grading",
                "score_awarded": score_awarded,
                "max_score": max_score,
                "items": result_items,
            }
            context["is_correct"] = max_score > 0 and score_awarded >= max_score
            context["score"] = _percentage(score_awarded, max_score)
            context["diagnosis"] = (
                "CORRECT"
                if context["is_correct"]
                else "PARTIAL"
                if score_awarded > 0
                else "CONFUSION"
            )
        return context

    result = build_deep_question_grading_result(
        context,
        user_answer=str(context.get("user_answer") or "").strip(),
    )
    if not result:
        return context
    context["construction_grading_result"] = result
    context["is_correct"] = _result_is_full_score(result)
    context["score"] = _result_percentage_score(result)
    if context["is_correct"]:
        context["diagnosis"] = "CORRECT"
    elif result.get("type") == "case" and float(result.get("score_awarded") or 0) > 0:
        context["diagnosis"] = "PARTIAL"
    elif result.get("type") == "case":
        context["diagnosis"] = "采分点遗漏"
    elif not str(context.get("diagnosis") or "").strip():
        context["diagnosis"] = "CONFUSION"
    return context


def _question_row_from_context(question_context: dict[str, Any]) -> dict[str, Any]:
    row = dict(question_context)
    question = str(
        row.get("question_stem")
        or row.get("stem")
        or row.get("question")
        or row.get("question_text")
        or ""
    ).strip()
    row.setdefault("question_stem", question)
    row.setdefault("stem", question)
    row.setdefault("question_text", question)
    row.setdefault("testing_focus", row.get("concentration") or row.get("testing_focus") or "")
    if not row.get("id"):
        row["id"] = row.get("question_id") or row.get("original_id") or ""
    return row


def _is_choice_context(row: dict[str, Any]) -> bool:
    question_type = str(row.get("question_type") or "").strip().lower()
    if question_type in _CHOICE_TYPES:
        return True
    options = row.get("options")
    correct = str(row.get("correct_answer") or "").strip()
    return isinstance(options, dict) and bool(options) and bool(correct)


def _result_is_full_score(result: dict[str, Any]) -> bool:
    max_score = float(result.get("max_score") or 0)
    score_awarded = float(result.get("score_awarded") or 0)
    return max_score > 0 and score_awarded >= max_score


def _result_percentage_score(result: dict[str, Any]) -> int:
    return _percentage(float(result.get("score_awarded") or 0), float(result.get("max_score") or 0))


def _percentage(score_awarded: float, max_score: float) -> int:
    if max_score <= 0:
        return 0
    return int(round((score_awarded / max_score) * 100))
