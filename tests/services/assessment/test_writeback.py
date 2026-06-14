from __future__ import annotations

import os

import pytest

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
from deeptutor.services.assessment.writeback import AssessmentWritebackService
from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref
from deeptutor.services.learner_state.mistake_book import InMemoryMistakeBookStore, MistakeBookService


class _LearnerState:
    def __init__(self) -> None:
        self.events = []
        self.progress_patches = []

    def append_memory_event(self, user_id, **kwargs):
        dedupe_key = kwargs.get("dedupe_key")
        for event in self.events:
            if event.dedupe_key == dedupe_key:
                return event
        event = type(
            "Event",
            (),
            {
                "event_id": f"evt_{len(self.events) + 1}",
                "user_id": user_id,
                "dedupe_key": dedupe_key,
                **kwargs,
            },
        )()
        self.events.append(event)
        return event

    def merge_progress(self, user_id, patch):
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch


def _scored_result() -> dict:
    return {
        "score_summary": {"score_pct": 50, "correct_count": 1, "scored_count": 2},
        "measurement_confidence": {"level": "medium", "reasons": []},
        "items": [
            {
                "question_id": "q1",
                "source_question_id": "src_1",
                "learner_answer": "A",
                "correct_answer": "A",
                "is_correct": True,
                "knowledge_points": ["防水工程"],
                "simple_explanation": "卷材搭接方向正确。",
                "error_codes": [],
                "measurement_confidence": "medium",
            },
            {
                "question_id": "q2",
                "source_question_id": "src_2",
                "learner_answer": "B",
                "correct_answer": "A",
                "is_correct": False,
                "knowledge_points": ["防水工程"],
                "simple_explanation": "防水节点应按规范处理。",
                "error_codes": ["M01"],
                "measurement_confidence": "medium",
            },
        ],
    }


def _service(monkeypatch: pytest.MonkeyPatch) -> tuple[AssessmentWritebackService, _LearnerState, MistakeBookService]:
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", "1")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", "1")
    learner = _LearnerState()
    mistake_book = MistakeBookService(store=InMemoryMistakeBookStore())
    return AssessmentWritebackService(learner_state_service=learner, mistake_book_service=mistake_book), learner, mistake_book


def test_submit_writes_one_learning_evidence_event_per_scored_item(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert len([event for event in learner.events if event.memory_kind == "learning_evidence"]) == 2
    assert refs["learning_event_refs"][0]["event_id"] == "evt_1"
    assert learner.events[0].source_feature == "assessment_testset"
    assert learner.events[0].payload_json["event_type"] == "learning_evidence"


def test_assessment_writeback_updates_home_personalization_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam_1",
        scored_result=_scored_result(),
    )

    assert len(learner.progress_patches) == 1
    projection = learner.progress_patches[0]["patch"]["home_personalization"]
    # resolved taxonomy node is not overridden by the textbook-section alias (branch behavior,
    # merge resolution per owner decision)
    assert projection["today_focus"]["title"] == "今日焦点：防水工程"
    assert projection["today_focus"]["prompt"] == "用 3 道题训练防水工程"
    assert projection["recommended_prompts"][0]["prompt_type"] == "practice_prompt"
    assert projection["recommended_prompts"][0]["intent"]["evidence_refs"] == [
        "evt_2",
        refs["learning_event_refs"][1]["attempt_ref"],
    ]
    assert projection["source_status"]["learning_report"] == "projection"


def test_assessment_writeback_uses_question_taxonomy_code_for_home_projection_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, learner, _mistake_book = _service(monkeypatch)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.home_personalization.infer_learning_topic_with_llm",
        lambda _payload, _candidates: "",
    )
    scored = _scored_result()
    scored["items"][1]["node_code"] = "1A413050"

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam_1",
        scored_result=scored,
    )

    projection = learner.progress_patches[0]["patch"]["home_personalization"]
    assert projection["today_focus"]["title"] == "今日焦点：屋面与防水工程施工"
    assert projection["today_focus"]["intent"]["taxonomy_code"] == "1A413050"
    assert projection["recommended_prompts"][0]["text"] == "用 3 道题训练屋面与防水工程施工"


def test_submit_duplicate_does_not_duplicate_learning_events(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )
    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert len(learner.events) == 2


def test_attempt_ref_is_signed_after_event_id_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    wrong_ref = refs["learning_event_refs"][1]["attempt_ref"]
    verified = verify_attempt_ref(wrong_ref, user_id="student_demo")
    assert verified["event_id"] == "evt_2"
    assert verified["question_id"] == "q2"


def test_wrong_item_is_saved_to_mistake_book_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    items = mistake_book.list_items(user_id="student_demo", subject_id="construction_exam")["items"]
    assert len(items) == 1
    assert items[0]["question_id"] == "q2"
    assert items[0]["concept_label"] == "防水工程"


def test_error_codes_must_exist_in_error_code_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, _mistake_book = _service(monkeypatch)
    result = _scored_result()
    result["items"][1]["error_codes"] = ["NOT_REGISTERED"]

    with pytest.raises(Exception, match="unregistered_error_code"):
        service.writeback(
            user_id="student_demo",
            quiz_id="quiz_1",
            form_id="form_1",
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            scored_result=result,
        )


def test_assessment_submit_does_not_mutate_training_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert all(event.memory_kind != "training_intent" for event in learner.events)
    assert "M01" in ERROR_CODE_REGISTRY


def test_assessment_wrong_item_writes_actionable_learning_graph_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    wrong_payload = learner.events[1].payload_json
    edges = wrong_payload["typed_edges"]

    assert any(edge["edge_type"] == "question_tests_concept" for edge in edges)
    assert any(edge["edge_type"] == "submission_triggered_error" for edge in edges)
    action_edge = next(edge for edge in edges if edge["edge_type"] == "error_points_to_training")
    assert action_edge["from"] == {"type": "error", "id": "防水工程:M01"}
    assert action_edge["to"]["type"] == "next_training"
    assert action_edge["source_feature"] == "assessment_testset"


def test_assessment_graph_edges_prefer_canonical_concept_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)
    result = _scored_result()
    result["items"][1]["section_id"] = "1A432000"

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=result,
    )

    wrong_payload = learner.events[1].payload_json
    action_edge = next(edge for edge in wrong_payload["typed_edges"] if edge["edge_type"] == "error_points_to_training")

    assert wrong_payload["concept_id"] == "1A432000"
    assert wrong_payload["error_events"][0]["concept_tag"] == "1A432000"
    assert action_edge["from"] == {"type": "error", "id": "1A432000:M01"}
