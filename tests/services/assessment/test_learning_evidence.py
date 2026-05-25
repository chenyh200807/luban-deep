from __future__ import annotations

from deeptutor.services.assessment.learning_evidence import (
    build_assessment_learning_evidence_batch,
)
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)


def test_build_assessment_learning_evidence_batch_uses_grading_batch_shape() -> None:
    batch = build_assessment_learning_evidence_batch(
        quiz_id="quiz_1",
        blueprint_version="diagnostic_v1",
        questions=[
            {
                "question_id": "q1",
                "source_question_id": "bank_q1",
                "question_stem": "验槽通常主要采用什么方法？",
                "chapter": "地基基础",
                "answer": "A",
                "options": [{"key": "A", "text": "观察法"}, {"key": "B", "text": "钎探法"}],
                "provenance": {"node_code": "1A411010"},
            },
            {
                "question_id": "q2",
                "question_stem": "混凝土强度评定目的是什么？",
                "chapter": "建筑材料",
                "answer": "C",
            },
        ],
        answers={"q1": "B", "q2": "C"},
    )

    assert batch["type"] == "batch"
    assert batch["authority"] == "construction_grading"
    wrong, correct = batch["items"]
    assert wrong["question_id"] == "bank_q1"
    assert wrong["user_answer"] == "B"
    assert wrong["correct_answer"] == "A"
    assert wrong["score_awarded"] == 0.0
    assert wrong["error_events"][0]["concept_tag"] == "1A411010"
    assert wrong["next_training_signal"]["source"] == "assessment"
    assert wrong["evidence_refs"][0] == {"source_type": "assessment", "source_id": "quiz_1"}
    assert correct["score_awarded"] == 1.0
    assert correct["error_events"] == []


def test_assessment_ref_survives_canonical_learning_evidence_normalization() -> None:
    batch = build_assessment_learning_evidence_batch(
        quiz_id="quiz_1",
        blueprint_version="diagnostic_v1",
        questions=[
            {
                "question_id": "q1",
                "question_stem": "验槽通常主要采用什么方法？",
                "chapter": "地基基础",
                "answer": "A",
            },
        ],
        answers={"q1": "B"},
    )

    payload = build_learning_evidence_payload(
        grading_result=batch["items"][0],
        turn_id="quiz_1:q1",
    )

    assert any(
        ref.get("source_type") == "assessment" and ref.get("source_id") == "quiz_1"
        for ref in payload["evidence_refs"]
    )
