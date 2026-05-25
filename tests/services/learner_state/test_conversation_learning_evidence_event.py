from __future__ import annotations

from deeptutor.services.learner_state.conversation_learning_evidence import (
    build_learning_evidence_from_conversation_turn,
    write_conversation_learning_evidence_event,
)


def test_answer_explanation_turn_becomes_low_confidence_learning_evidence() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_123",
        user_question="主体结构多选题为什么容易漏选？",
        assistant_answer={
            "summary": "多选题要逐项判断所有必要条件，不能选到一个确定项就停止。",
            "concept_label": "主体结构",
            "error_label": "多选漏选",
            "source_refs": [{"type": "rag_hit", "label": "教材依据"}],
        },
        subject_id="construction_exam_1",
    )

    assert event is not None
    payload = event["payload_json"]
    assert event["memory_kind"] == "learning_evidence"
    assert event["event_type"] == "learning_evidence"
    assert event["evidence_source"] == "conversation_synthesis"
    assert event["learning_signal_type"] == "answer_explanation"
    assert event["subject_id"] == "construction_exam_1"
    assert event["training_intent_id"] is None
    assert payload["event_type"] == "learning_evidence"
    assert payload["evidence_source"] == "conversation_synthesis"
    assert payload["learning_signal_type"] == "answer_explanation"
    assert payload["concept"]["label"] == "主体结构"
    assert payload["evidence_level"] == "exposed"
    assert payload["confidence"] < 0.6
    assert payload["conversation_turn_ref"] == "turn_123"
    assert payload["subject_id"] == "construction_exam_1"
    assert payload["training_intent_id"] is None


def test_conversation_evidence_redacts_pii_before_write() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_124",
        user_question="张三：我的手机号 13812345678，主体结构为什么错？",
        assistant_answer={"summary": "这里错在验收条件。", "concept_label": "主体结构"},
        learning_signal_type="mistake_explain",
    )

    assert event is not None
    payload = event["payload_json"]
    assert "13812345678" not in payload["user_question"]
    assert payload["user_question_redacted"] is True
    assert payload["learning_signal_type"] == "mistake_explain"


def test_home_prompt_click_carries_intent_without_new_event_type() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_home",
        user_question="我手机号 13800001234 想问主体结构怎么背？",
        assistant_answer={"summary": "主体结构多选题要逐项判断。"},
        learning_signal_type="home_prompt_clicked",
        prompt_intent={
            "source": "home_dashboard",
            "concept_label": "主体结构",
            "error_label": "多选漏选",
            "subject_id": "construction_exam_1",
            "training_intent_id": "lti_123",
        },
    )

    assert event is not None
    assert event["event_type"] == "learning_evidence"
    assert event["evidence_source"] == "conversation_synthesis"
    assert event["learning_signal_type"] == "home_prompt_clicked"
    assert event["subject_id"] == "construction_exam_1"
    assert event["training_intent_id"] == "lti_123"
    assert "13800001234" not in event["user_question"]
    assert "[REDACTED_PHONE]" in event["user_question"]


def test_training_completion_carries_assessment_attempt_context() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_training_done",
        user_question="我完成了这 3 道同类题，帮我判断。",
        assistant_answer={"summary": "地下防水同类训练已完成，施工缝节点仍需复盘。"},
        prompt_intent={
            "source": "assessment_result_wrong_item",
            "learning_signal_type": "training_completed",
            "subject_id": "construction_exam",
            "concept_label": "地下防水",
            "error_label": "M01",
            "attempt_ref": "attempt_signed",
            "evidence_refs": ["attempt_signed"],
            "question_count": 3,
        },
    )

    assert event is not None
    payload = event["payload_json"]
    assert payload["learning_signal_type"] == "training_completed"
    assert payload["subject_id"] == "construction_exam"
    assert payload["concept"]["label"] == "地下防水"
    assert payload["error"]["label"] == "M01"
    assert payload["attempt_ref"] == "attempt_signed"
    assert payload["evidence_refs"] == ["attempt_signed"]
    assert payload["training_question_count"] == 3


def test_supabase_writer_does_not_require_conversation_event_type_whitelist() -> None:
    from deeptutor.services.learner_state.supabase_writer import LearnerStateSupabaseWriter

    assert LearnerStateSupabaseWriter._supports_event_type("learning_evidence")
    assert not LearnerStateSupabaseWriter._supports_event_type("conversation_learning_evidence")


def test_non_learning_conversation_is_not_written() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_125",
        user_question="你好",
        assistant_answer={"summary": "你好，有什么可以帮你？"},
    )

    assert event is None


def test_still_confused_turn_is_low_confidence_and_not_truth_eligible() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_confused",
        user_question="主体结构多选题我还是没听懂，为什么会漏选？",
        assistant_answer={
            "summary": "主体结构多选题要逐项核对必要条件，漏选通常是因为只看到一个确定项就停止判断。",
        },
    )

    assert event is not None
    payload = event["payload_json"]
    assert payload["learning_signal_type"] == "still_confused"
    assert payload["confidence"] <= 0.35
    assert payload["quality"]["truth_eligible"] is False
    assert payload["quality"]["stable_truth_eligible"] is False
    assert payload["event_type"] == "learning_evidence"
    assert payload["evidence_source"] == "conversation_synthesis"


def test_conversation_writeback_updates_home_personalization_projection() -> None:
    class _FakeLearnerStateService:
        def __init__(self) -> None:
            self.appended: list[dict[str, object]] = []
            self.progress_patches: list[dict[str, object]] = []

        def append_memory_event(self, user_id: str, **kwargs: object) -> object:
            self.appended.append({"user_id": user_id, **kwargs})
            return {"event_id": "evt_conversation"}

        def merge_progress(self, user_id: str, patch: dict[str, object]) -> dict[str, object]:
            self.progress_patches.append({"user_id": user_id, "patch": patch})
            return patch

    service = _FakeLearnerStateService()

    written = write_conversation_learning_evidence_event(
        learner_state_service=service,
        user_id="u1",
        turn_ref="turn_projection",
        user_question="主体结构多选题我还是没听懂，为什么会漏选？",
        assistant_answer={
            "summary": "主体结构多选题要逐项核对必要条件，漏选通常是因为只看到一个确定项就停止判断。",
        },
        subject_id="construction_exam_1",
    )

    assert written == {"event_id": "evt_conversation"}
    assert service.appended[0]["memory_kind"] == "learning_evidence"
    patch = service.progress_patches[0]["patch"]
    projection = patch["home_personalization"]
    assert projection["today_focus"]["intent"]["concept_label"] == "主体结构"
    assert projection["recommended_prompts"][0]["intent"]["source"] == "home_dashboard"
    assert projection["source_status"]["learning_report"] == "projection"
