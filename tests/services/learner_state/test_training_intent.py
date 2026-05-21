from __future__ import annotations

from deeptutor.services.learner_state.training_intent import build_learning_training_intent


def test_training_intent_contains_concept_error_attempt_and_question_count() -> None:
    intent = build_learning_training_intent(
        user_id="u1",
        concept_id="1A432000",
        concept_label="主体结构",
        error_code="M06",
        error_label="多选漏选",
        attempt_refs=["ref1"],
        question_count=9,
        training_mode="mcq_discrimination",
    )

    assert intent["source"] == "learning_report"
    assert intent["concept_label"] == "主体结构"
    assert intent["error_label"] == "多选漏选"
    assert intent["attempt_refs"] == ["ref1"]
    assert intent["question_count"] == 5
    assert intent["training_mode"] == "mcq_discrimination"
    assert intent["training_intent_id"].startswith("lti_")
