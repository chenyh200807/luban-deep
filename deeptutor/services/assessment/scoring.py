from __future__ import annotations

from collections import Counter
from typing import Any


class AssessmentScoringError(ValueError):
    pass


def _normalize_answer(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    letters = [ch for ch in raw if ch.isalnum()]
    return "".join(sorted(set(letters)))


def _knowledge_points(question: dict[str, Any]) -> list[str]:
    points: list[str] = []
    for value in (
        question.get("chapter"),
        dict(question.get("provenance") or {}).get("node_code"),
        question.get("section_label"),
    ):
        text = str(value or "").strip()
        if text and text not in points:
            points.append(text)
    return points or ["综合能力"]


def _simple_explanation(question: dict[str, Any], *, is_correct: bool) -> str:
    source_meta = dict(dict(question.get("provenance") or {}).get("source_meta") or {})
    for key in ("simple_explanation", "analysis", "explanation", "rationale"):
        text = str(source_meta.get(key) or "").strip()
        if text:
            return text
    if is_correct:
        return "本题作答正确，继续保持对关键条件和规范表述的核对。"
    return "本题需要回到题干关键词、相关规范条文和防水构造要求逐项核对。"


def _error_codes(question: dict[str, Any], *, learner_answer: str, correct_answer: str) -> list[str]:
    if not learner_answer:
        return ["M05"]
    qtype = str(question.get("question_type") or "").strip()
    if qtype == "multi_choice":
        learner_set = set(learner_answer)
        correct_set = set(correct_answer)
        if learner_set < correct_set:
            return ["M06"]
        if learner_set - correct_set:
            return ["M07"]
    return ["M01"]


def _confidence(scored_count: int, answered_count: int, time_spent_seconds: int) -> dict[str, Any]:
    completion_rate = answered_count / max(scored_count, 1)
    seconds_per_item = float(time_spent_seconds or 0) / max(scored_count, 1)
    reasons: list[str] = []
    if completion_rate < 0.6:
        reasons.append("low_completion")
    if seconds_per_item < 3:
        reasons.append("too_fast")
    if seconds_per_item > 600:
        reasons.append("too_slow")
    if not reasons:
        level = "high" if completion_rate >= 0.9 else "medium"
    elif "low_completion" in reasons or "too_fast" in reasons:
        level = "low"
    else:
        level = "medium"
    return {
        "level": level,
        "completion_rate": round(completion_rate, 4),
        "seconds_per_item": round(seconds_per_item, 2),
        "reasons": reasons,
    }


def score_assessment(
    session_questions_private: list[dict[str, Any]],
    answers: dict[str, Any],
    *,
    time_spent_seconds: int = 0,
) -> dict[str, Any]:
    scored_questions = [dict(question) for question in session_questions_private if question.get("scored", True)]
    source_counts = Counter(str(question.get("source_question_id") or "") for question in scored_questions)
    duplicates = [source_id for source_id, count in source_counts.items() if source_id and count > 1]
    if duplicates:
        raise AssessmentScoringError(f"duplicate_source_question_id: {duplicates[0]}")

    items: list[dict[str, Any]] = []
    correct_count = 0
    answered_count = 0
    for question in scored_questions:
        question_id = str(question.get("question_id") or "").strip()
        learner_answer = _normalize_answer(answers.get(question_id))
        correct_answer = _normalize_answer(question.get("answer"))
        is_blank = not learner_answer
        is_correct = bool(learner_answer and learner_answer == correct_answer)
        if learner_answer:
            answered_count += 1
        if is_correct:
            correct_count += 1
        item_confidence = "medium" if not is_blank else "low"
        items.append(
            {
                "question_id": question_id,
                "source_question_id": str(question.get("source_question_id") or "").strip(),
                "question_stem": str(question.get("question_stem") or "").strip(),
                "question_type": str(question.get("question_type") or "").strip(),
                "section_id": str(question.get("section_id") or "").strip(),
                "section_label": str(question.get("section_label") or "").strip(),
                "learner_answer": learner_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "is_blank": is_blank,
                "flags": ["blank_attempt"] if is_blank else [],
                "knowledge_points": _knowledge_points(question),
                "simple_explanation": _simple_explanation(question, is_correct=is_correct),
                "error_codes": [] if is_correct else _error_codes(question, learner_answer=learner_answer, correct_answer=correct_answer),
                "measurement_confidence": item_confidence,
            }
        )

    confidence = _confidence(len(scored_questions), answered_count, int(time_spent_seconds or 0))
    return {
        "score_summary": {
            "score_pct": round(correct_count / max(len(scored_questions), 1) * 100),
            "correct_count": correct_count,
            "answered_count": answered_count,
            "scored_count": len(scored_questions),
            "blank_count": max(len(scored_questions) - answered_count, 0),
        },
        "measurement_confidence": confidence,
        "items": items,
    }
