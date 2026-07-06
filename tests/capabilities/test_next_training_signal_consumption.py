"""
plan §Batch E.1 Gap 6 — lightweight 出题入口主动消费 latest next_training_signal.

测试 _extract_latest_next_training_signal 能从 active_object.state_snapshot 中
取出最新错题的 concept / focus，供 coordinator anchor 命中 weak point。
"""

from __future__ import annotations

from deeptutor.capabilities.deep_question import DeepQuestionCapability


def test_extract_signal_from_top_level_grading_result() -> None:
    active_object = {
        "object_type": "question_set",
        "state_snapshot": {
            "question_id": "qs",
            "construction_grading_result": {
                "authority": "construction_grading",
                "next_training_signal": {
                    "concept": "1A432000",
                    "focus": "专家论证程序",
                    "mode": "case_repair",
                },
            },
        },
    }
    concept, focus = DeepQuestionCapability._extract_latest_next_training_signal(active_object)
    assert concept == "1A432000"
    assert focus == "专家论证程序"


def test_extract_signal_from_item_when_top_level_absent() -> None:
    active_object = {
        "object_type": "question_set",
        "state_snapshot": {
            "items": [
                {
                    "question_id": "q1",
                    "construction_grading_result": {
                        "next_training_signal": {"concept": "1A431000", "focus": "防水"}
                    },
                }
            ]
        },
    }
    concept, focus = DeepQuestionCapability._extract_latest_next_training_signal(active_object)
    assert concept == "1A431000"
    assert focus == "防水"


def test_extract_signal_returns_empty_when_no_grading_result() -> None:
    active_object = {"object_type": "open_chat_topic", "state_snapshot": {"title": "随便聊"}}
    assert DeepQuestionCapability._extract_latest_next_training_signal(active_object) == ("", "")


def test_extract_signal_returns_empty_when_active_object_missing() -> None:
    assert DeepQuestionCapability._extract_latest_next_training_signal(None) == ("", "")
    assert DeepQuestionCapability._extract_latest_next_training_signal({}) == ("", "")


def test_learning_training_intent_updates_topic_and_active_object_state() -> None:
    intent = {
        "source": "learning_report",
        "training_intent_id": "lti_123",
        "concept_id": "1A432000",
        "concept_label": "主体结构",
        "error_code": "M06",
        "error_label": "多选漏选",
        "training_mode": "case_repair",
        "question_count": 3,
    }

    normalized = DeepQuestionCapability._normalize_learning_training_intent(intent)
    topic = DeepQuestionCapability._apply_learning_training_intent_to_topic("生成专项训练", normalized)
    active_object = DeepQuestionCapability._attach_learning_training_intent_to_active_object(
        {"object_type": "question_set", "state_snapshot": {"question_id": "qs"}},
        normalized,
    )

    assert normalized["training_intent_id"] == "lti_123"
    assert "主体结构" in topic
    assert "多选漏选" in topic
    assert "case_repair" in topic
    assert active_object["state_snapshot"]["training_intent_id"] == "lti_123"
    assert active_object["state_snapshot"]["learning_training_intent"]["concept_label"] == "主体结构"


def test_explicit_user_question_count_overrides_training_intent_count() -> None:
    intent = DeepQuestionCapability._normalize_learning_training_intent(
        {
            "source": "debug",
            "training_intent_id": "intent-count-4",
            "concept_label": "水泥",
            "question_count": 4,
        }
    )

    assert (
        DeepQuestionCapability._resolve_generation_question_count(
            overrides={"num_questions": 4},
            learning_training_intent=intent,
            raw_user_message="用 3 道题训练水泥",
        )
        == 3
    )


def test_existing_generation_question_count_overrides_training_intent_count() -> None:
    intent = DeepQuestionCapability._normalize_learning_training_intent(
        {
            "source": "debug",
            "training_intent_id": "intent-count-4",
            "concept_label": "水泥",
            "question_count": 4,
        }
    )

    assert (
        DeepQuestionCapability._resolve_generation_question_count(
            overrides={"num_questions": 3},
            learning_training_intent=intent,
            raw_user_message="训练水泥",
        )
        == 3
    )


def test_training_intent_question_count_applies_when_user_count_is_not_explicit() -> None:
    intent = DeepQuestionCapability._normalize_learning_training_intent(
        {
            "source": "debug",
            "training_intent_id": "intent-count-4",
            "concept_label": "水泥",
            "question_count": 4,
        }
    )

    assert (
        DeepQuestionCapability._resolve_generation_question_count(
            overrides={"num_questions": 1},
            learning_training_intent=intent,
            raw_user_message="训练水泥",
        )
        == 4
    )
