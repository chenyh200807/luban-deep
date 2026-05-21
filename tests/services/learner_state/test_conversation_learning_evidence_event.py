from __future__ import annotations

from deeptutor.services.learner_state.conversation_learning_evidence import (
    build_learning_evidence_from_conversation_turn,
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
    )

    assert event is not None
    payload = event["payload_json"]
    assert event["memory_kind"] == "learning_evidence"
    assert payload["event_type"] == "learning_evidence"
    assert payload["evidence_source"] == "conversation_synthesis"
    assert payload["learning_signal_type"] == "answer_explanation"
    assert payload["concept"]["label"] == "主体结构"
    assert payload["evidence_level"] == "exposed"
    assert payload["confidence"] < 0.6
    assert payload["conversation_turn_ref"] == "turn_123"


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


def test_non_learning_conversation_is_not_written() -> None:
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_125",
        user_question="你好",
        assistant_answer={"summary": "你好，有什么可以帮你？"},
    )

    assert event is None
