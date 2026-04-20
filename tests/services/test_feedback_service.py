from __future__ import annotations

from deeptutor.services.feedback_service import (
    build_mobile_feedback_row,
    normalize_feedback_record,
)


def test_build_mobile_feedback_row_moves_non_uuid_ids_into_metadata() -> None:
    row = build_mobile_feedback_row(
        user_id="student_demo",
        session_id="session_feedback_1",
        message_id="42",
        rating=-9,
        reason_tags=["事实错误", "逻辑不通", "事实错误"],
        comment="这里不对",
        answer_mode="fast",
    )

    assert row["user_id"] is None
    assert row["conversation_id"] is None
    assert row["message_id"] is None
    assert row["rating"] == -1
    assert row["reason_tags"] == ["事实错误", "逻辑不通"]
    assert row["metadata"]["deeptutor_user_id"] == "student_demo"
    assert row["metadata"]["deeptutor_session_id"] == "session_feedback_1"
    assert row["metadata"]["deeptutor_message_id"] == "42"
    assert row["metadata"]["answer_mode"] == "FAST"


def test_build_mobile_feedback_row_keeps_answer_mode_and_response_mode_metadata() -> None:
    row = build_mobile_feedback_row(
        user_id="student_demo",
        answer_mode="smart",
        requested_response_mode="deep",
        effective_response_mode="fast",
        response_mode_degrade_reason="token_budget",
        actual_tool_rounds=2,
    )

    assert row["metadata"]["answer_mode"] == "SMART"
    assert row["metadata"]["requested_response_mode"] == "DEEP"
    assert row["metadata"]["effective_response_mode"] == "FAST"
    assert row["metadata"]["response_mode_degrade_reason"] == "token_budget"
    assert row["metadata"]["actual_tool_rounds"] == 2


def test_normalize_feedback_record_prefers_top_level_ids_then_metadata_fallback() -> None:
    record = normalize_feedback_record(
        {
            "id": "feedback_1",
            "created_at": "2026-04-17T10:00:00+08:00",
            "user_id": "",
            "conversation_id": "",
            "message_id": "",
            "rating": 7,
            "reason_tags": ["逻辑不通", "逻辑不通", ""],
            "comment": "需要重讲",
            "metadata": {
                "deeptutor_user_id": "u1",
                "deeptutor_session_id": "session_1",
                "deeptutor_message_id": "101",
                "answer_mode": "FAST",
                "feedback_source": "wx_miniprogram_message_actions",
                "surface": "wx_miniprogram",
                "platform": "wechat_miniprogram",
                "source": "wx_miniprogram",
            },
        }
    )

    assert record["user_id"] == "u1"
    assert record["session_id"] == "session_1"
    assert record["message_id"] == "101"
    assert record["rating"] == 1
    assert record["reason_tags"] == ["逻辑不通"]
    assert record["feedback_source"] == "wx_miniprogram_message_actions"


def test_normalize_feedback_record_reads_response_mode_fields_from_metadata() -> None:
    record = normalize_feedback_record(
        {
            "id": "feedback_2",
            "created_at": "2026-04-17T10:00:00+08:00",
            "user_id": "u2",
            "conversation_id": "session_2",
            "message_id": "102",
            "rating": 1,
            "reason_tags": [],
            "comment": "",
            "metadata": {
                "answer_mode": "FAST",
                "requested_response_mode": "DEEP",
                "effective_response_mode": "FAST",
                "response_mode_degrade_reason": "tool_budget",
                "actual_tool_rounds": 3,
            },
        }
    )

    assert record["answer_mode"] == "FAST"
    assert record["requested_response_mode"] == "DEEP"
    assert record["effective_response_mode"] == "FAST"
    assert record["response_mode_degrade_reason"] == "tool_budget"
    assert record["actual_tool_rounds"] == 3
