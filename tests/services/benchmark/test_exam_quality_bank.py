"""Tests for the historical-exam ground-truth bank loader.

Validates loading against the real fixture (no network, no LLM) so the
ground-truth asset that backs closed-book quality scoring stays well-formed.
"""

from __future__ import annotations

import json

from deeptutor.services.benchmark.exam_quality_bank import (
    ExamQuestion,
    load_exam_quality_bank,
)


def test_loads_real_fixture_with_valid_mcq_records() -> None:
    questions = load_exam_quality_bank()
    assert questions, "bank fixture must contain questions"
    assert all(isinstance(q, ExamQuestion) for q in questions)
    for q in questions:
        eq = q.exact_question
        assert eq.get("answer_kind") == "mcq"
        correct = str(eq.get("correct_answer") or "")
        options = eq.get("options") or {}
        # ground-truth integrity: every answer letter must be a real option
        assert correct, f"{q.question_id} missing correct_answer"
        assert all(letter in options for letter in correct), q.question_id
        assert str(eq.get("stem") or "").strip(), f"{q.question_id} missing stem"


def test_single_choice_has_one_letter_multiple_has_more() -> None:
    questions = load_exam_quality_bank()
    for q in questions:
        n = len(q.exact_question["correct_answer"])
        if q.type == "single_choice":
            assert n == 1, f"{q.question_id} single_choice not one letter"
        elif q.type == "multiple_choice":
            assert n >= 2, f"{q.question_id} multiple_choice not multi-letter"


def test_custom_path_and_empty_bank(tmp_path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"questions": []}), encoding="utf-8")
    assert load_exam_quality_bank(empty) == []
