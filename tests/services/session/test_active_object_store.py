from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.services.session.sqlite_store import (
    SQLiteSessionStore,
    build_active_object_from_learning_plan_view,
    build_active_object_from_question_context,
    build_active_object_from_session,
)


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_active_object_and_question_adapter(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Quiz", session_id="session-active-object")

    active_object = build_active_object_from_question_context(
        {
            "question_id": "q_1",
            "question": "判断：流水步距反映相邻专业队投入间隔。",
            "question_type": "choice",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "A",
        },
        source_turn_id="turn-store",
    )

    await store.set_active_object(session["id"], active_object)

    loaded_active_object = await store.get_active_object(session["id"])
    question_context = await store.get_active_question_context(session["id"])

    assert loaded_active_object is not None
    assert loaded_active_object["object_type"] == "single_question"
    assert loaded_active_object["object_id"] == "q_1"
    assert question_context is not None
    assert question_context["question_id"] == "q_1"
    assert question_context["correct_answer"] == "A"


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_guide_page_active_object(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Plan", session_id="session-guide-active-object")

    active_object = build_active_object_from_learning_plan_view(
        {
            "session_id": "plan_demo",
            "user_id": "student_1",
            "status": "in_progress",
            "summary": "当前正在学习网络计划。",
            "progress": 40,
            "page_count": 3,
            "ready_count": 1,
            "current_index": 1,
            "notebook_id": "nb_1",
            "notebook_name": "施工组织",
            "pages": [
                {
                    "page_index": 1,
                    "knowledge_title": "网络计划关键线路",
                    "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
                    "page_status": "ready",
                }
            ],
        },
        source_turn_id="turn-guide-store",
    )

    await store.set_active_object(session["id"], active_object)

    loaded_active_object = await store.get_active_object(session["id"])
    question_context = await store.get_active_question_context(session["id"])

    assert loaded_active_object is not None
    assert loaded_active_object["object_type"] == "guide_page"
    assert loaded_active_object["object_id"] == "plan_demo:page:1"
    assert loaded_active_object["state_snapshot"]["plan_id"] == "plan_demo"
    assert loaded_active_object["state_snapshot"]["current_page"]["knowledge_title"] == "网络计划关键线路"
    assert question_context is None


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_open_chat_active_object(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(
        title="施工组织总设计",
        session_id="session-open-chat-active-object",
        source="wx",
    )
    await store.update_summary(
        session["id"],
        summary="用户正在讨论施工组织总设计与网络计划的关系。",
        up_to_msg_id=0,
    )
    session_view = await store.get_session(session["id"])

    active_object = build_active_object_from_session(
        session_view,
        source_turn_id="turn-open-chat-store",
    )

    await store.set_active_object(session["id"], active_object)

    loaded_active_object = await store.get_active_object(session["id"])
    question_context = await store.get_active_question_context(session["id"])

    assert loaded_active_object is not None
    assert loaded_active_object["object_type"] == "open_chat_topic"
    assert loaded_active_object["object_id"] == session["id"]
    assert loaded_active_object["state_snapshot"]["title"] == "施工组织总设计"
    assert "网络计划" in loaded_active_object["state_snapshot"]["compressed_summary"]
    assert question_context is None
