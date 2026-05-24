from __future__ import annotations

from typing import Any


def build_assessment_learning_evidence_batch(
    *,
    quiz_id: str,
    blueprint_version: str,
    questions: list[dict[str, Any]],
    answers: dict[str, str],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for question in questions:
        question_id = str(question.get("question_id") or "").strip()
        user_answer = str(answers.get(question_id, "") or "").strip().upper()
        if not question_id or not user_answer:
            continue
        correct_answer = str(question.get("answer") or "").strip().upper()
        chapter = str(question.get("chapter") or question.get("section_label") or "").strip()
        is_correct = bool(correct_answer and user_answer == correct_answer)
        source_question_id = str(question.get("source_question_id") or "").strip()
        provenance = dict(question.get("provenance") or {})
        node_code = str(provenance.get("node_code") or "").strip()
        concept = node_code or chapter or "assessment"
        explanation = "摸底测评已记录本题作答结果。"
        errors = []
        if not is_correct:
            explanation = f"摸底测评中，{chapter or '本题'}相关题目答错，需要回到原题复盘。"
            errors.append({
                "error_code": "unknown_error",
                "concept_tag": concept,
                "diagnosis": explanation,
            })
        items.append({
            "type": "mcq",
            "question_id": source_question_id or question_id,
            "question_type": "mcq",
            "question_stem": question.get("question_stem") or question.get("question") or "",
            "options": question.get("options") if isinstance(question.get("options"), (dict, list)) else {},
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "score_awarded": 1.0 if is_correct else 0.0,
            "max_score": 1.0,
            "grading_mode": "assessment_blueprint",
            "explanation": {
                "summary": explanation,
                "why_user_wrong": explanation if not is_correct else "",
            },
            "error_events": errors,
            "evidence_refs": [
                {"source_type": "assessment", "source_id": quiz_id},
                {"source_type": "active_question", "source_id": source_question_id or question_id},
            ],
            "next_training_signal": {
                "source": "assessment",
                "concept": concept,
                "focus": chapter or concept,
                "mode": "assessment_review",
                "blueprint_version": blueprint_version,
            },
        })
    return {
        "type": "batch",
        "authority": "construction_grading",
        "items": items,
    }
