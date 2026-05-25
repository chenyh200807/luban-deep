from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any


def build_explanation_cache_key(
    quiz_id: str,
    question_id: str,
    learner_answer_hash: str,
    grading_result_hash: str,
    prompt_version: str,
) -> str:
    raw = "|".join(
        [
            str(quiz_id or ""),
            str(question_id or ""),
            str(learner_answer_hash or ""),
            str(grading_result_hash or ""),
            str(prompt_version or ""),
        ]
    )
    return "assessment_explain_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class DailyExplanationBudget:
    def __init__(self, *, max_misses_per_user_per_day: int = 20) -> None:
        self.max_misses_per_user_per_day = max(0, int(max_misses_per_user_per_day))
        self._misses: dict[str, int] = {}

    def record_cache_miss(self, user_id: str) -> int:
        normalized = str(user_id or "").strip() or "anonymous"
        next_count = int(self._misses.get(normalized) or 0) + 1
        if next_count > self.max_misses_per_user_per_day:
            raise RuntimeError("assessment_deep_explanation_budget_exceeded")
        self._misses[normalized] = next_count
        return next_count


def attach_deep_explanation(
    report: dict[str, Any],
    *,
    question_id: str,
    explanation: dict[str, Any],
) -> dict[str, Any]:
    next_report = deepcopy(report)
    normalized_question_id = str(question_id or "")
    for group_key in ("wrong_items", "items", "questions"):
        for item in next_report.get(group_key) or []:
            if str(item.get("question_id") or item.get("id") or "") == normalized_question_id:
                item["deep_explanation"] = dict(explanation or {})
    return next_report


def build_static_deep_explanation(
    *,
    question: dict[str, Any],
    learner_answer: str,
    correct_answer: str,
) -> dict[str, Any]:
    simple = str(
        question.get("simple_explanation")
        or question.get("explanation")
        or question.get("analysis")
        or "本题需要回到题干条件、规范要求和选项差异逐项判断。"
    ).strip()
    knowledge_points = list(question.get("knowledge_points") or question.get("knowledge_nodes") or [])
    return {
        "summary": simple,
        "learner_answer": str(learner_answer or ""),
        "correct_answer": str(correct_answer or ""),
        "knowledge_points": knowledge_points,
        "score_mutation_allowed": False,
        "source": "assessment_deep_explanation_projection",
    }
