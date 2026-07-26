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
    assert len(questions) == 337
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


def test_real_fixture_uses_docs_2026_full_exam_years() -> None:
    questions = load_exam_quality_bank()
    assert {q.year for q in questions} == set(range(2015, 2026))


def test_real_fixture_keeps_docs_2026_source_pointers() -> None:
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[3]
        / "deeptutor/services/benchmark/fixtures/exam_quality_bank.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["source_docs_2026_root"] == "FastAPI20251222/docs/2026/题库"
    assert payload["years_blocked"] == []
    assert payload["by_year"]["2024"]["single_choice"] == 21
    assert payload["by_year"]["2024"]["multiple_choice"] == 10
    assert len(payload["type_normalizations"]) == 4
    assert all((item.get("source") or {}).get("docs_2026_path") for item in payload["questions"])


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
