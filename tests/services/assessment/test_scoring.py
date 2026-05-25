from __future__ import annotations

import pytest

from deeptutor.services.assessment.scoring import AssessmentScoringError, score_assessment


def _question(question_id: str, answer: str, *, source_id: str | None = None, qtype: str = "single_choice") -> dict:
    return {
        "question_id": question_id,
        "source_question_id": source_id or question_id,
        "question_type": qtype,
        "question_stem": f"{question_id} 防水题",
        "chapter": "防水工程",
        "section_id": "waterproof_quality",
        "section_label": "防水质量",
        "answer": answer,
        "scored": True,
        "provenance": {"node_code": "1A414010", "source_type": "REAL_EXAM"},
        "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}, {"key": "C", "text": "C"}],
    }


def test_scores_single_and_multi_answer_items() -> None:
    result = score_assessment(
        [_question("q1", "A"), _question("q2", "AB", qtype="multi_choice")],
        {"q1": "a", "q2": "BA"},
        time_spent_seconds=120,
    )

    assert result["score_summary"]["correct_count"] == 2
    assert result["score_summary"]["score_pct"] == 100
    assert [item["is_correct"] for item in result["items"]] == [True, True]
    assert result["items"][1]["correct_answer"] == "AB"


def test_blank_attempt_is_reported_without_mastery_penalty_flag() -> None:
    result = score_assessment([_question("q1", "A")], {}, time_spent_seconds=30)

    assert result["items"][0]["learner_answer"] == ""
    assert result["items"][0]["is_blank"] is True
    assert result["items"][0]["is_correct"] is False
    assert "blank_attempt" in result["items"][0]["flags"]


def test_completion_rate_affects_measurement_confidence() -> None:
    questions = [_question(f"q{i}", "A") for i in range(1, 6)]
    result = score_assessment(questions, {"q1": "A"}, time_spent_seconds=240)

    assert result["measurement_confidence"]["level"] == "low"
    assert "low_completion" in result["measurement_confidence"]["reasons"]


def test_time_pattern_marks_low_confidence_without_overriding_score() -> None:
    questions = [_question(f"q{i}", "A") for i in range(1, 6)]
    result = score_assessment(questions, {f"q{i}": "A" for i in range(1, 6)}, time_spent_seconds=8)

    assert result["score_summary"]["score_pct"] == 100
    assert result["measurement_confidence"]["level"] == "low"
    assert "too_fast" in result["measurement_confidence"]["reasons"]


def test_duplicate_source_question_ids_are_rejected() -> None:
    with pytest.raises(AssessmentScoringError):
        score_assessment(
            [_question("q1", "A", source_id="same"), _question("q2", "B", source_id="same")],
            {"q1": "A", "q2": "B"},
            time_spent_seconds=60,
        )
