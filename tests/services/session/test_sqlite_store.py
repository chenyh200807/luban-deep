from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from deeptutor.services.path_service import PathService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def test_sqlite_store_defaults_to_data_user_chat_history_db(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        store = SQLiteSessionStore()

        assert store.db_path == tmp_path / "data" / "user" / "chat_history.db"
        assert store.db_path.exists()
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_sqlite_store_migrates_legacy_chat_history_db(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        legacy_db = tmp_path / "data" / "chat_history.db"
        legacy_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(legacy_db) as conn:
            conn.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY)")
            conn.commit()

        store = SQLiteSessionStore()

        assert store.db_path.exists()
        assert not legacy_db.exists()
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


@pytest.mark.asyncio
async def test_sqlite_store_aggregates_session_cost_summary(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")

    session = await store.create_session(title="Token Demo", session_id="session-token-demo")

    turn_one = await store.create_turn(session["id"], capability="chat")
    await store.append_turn_event(
        turn_one["id"],
        {
            "type": "result",
            "source": "chat",
            "stage": "responding",
            "content": "",
            "metadata": {
                "metadata": {
                    "cost_summary": {
                        "scope_id": "turn:1",
                        "session_id": session["id"],
                        "total_input_tokens": 120,
                        "total_output_tokens": 30,
                        "total_tokens": 150,
                        "total_calls": 2,
                        "measured_calls": 1,
                        "estimated_calls": 1,
                        "usage_sources": {"provider": 1, "tiktoken": 1},
                        "models": {"deepseek-v3.2": 2},
                        "total_cost_usd": 0.0125,
                    }
                }
            },
            "timestamp": 1.0,
        },
    )
    await store.update_turn_status(turn_one["id"], "completed")

    turn_two = await store.create_turn(session["id"], capability="chat")
    await store.append_turn_event(
        turn_two["id"],
        {
            "type": "result",
            "source": "chat",
            "stage": "responding",
            "content": "",
            "metadata": {
                "metadata": {
                    "cost_summary": {
                        "scope_id": "turn:2",
                        "session_id": session["id"],
                        "total_input_tokens": 80,
                        "total_output_tokens": 20,
                        "total_tokens": 100,
                        "total_calls": 1,
                        "measured_calls": 1,
                        "estimated_calls": 0,
                        "usage_sources": {"provider": 1},
                        "models": {"deepseek-v3.2": 1},
                        "total_cost_usd": 0.004,
                    }
                }
            },
            "timestamp": 2.0,
        },
    )
    await store.update_turn_status(turn_two["id"], "completed")

    sessions = await store.list_sessions()
    assert sessions[0]["cost_summary"] == {
        "scope_id": f"session:{session['id']}",
        "session_id": session["id"],
        "total_input_tokens": 200,
        "total_output_tokens": 50,
        "total_tokens": 250,
        "total_calls": 3,
        "measured_calls": 2,
        "estimated_calls": 1,
        "usage_accuracy": "mixed",
        "usage_sources": {"provider": 2, "tiktoken": 1},
        "models": {"deepseek-v3.2": 3},
        "total_cost_usd": 0.0165,
    }

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["cost_summary"] == sessions[0]["cost_summary"]


@pytest.mark.asyncio
async def test_sqlite_store_persists_active_question_context_in_runtime_state(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Quiz", session_id="session-quiz")

    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_1",
            "question": "判断：流水步距反映相邻专业队投入间隔。",
            "question_type": "choice",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "A",
        },
    )

    context = await store.get_active_question_context(session["id"])

    assert context is not None
    assert context["question_id"] == "q_1"
    assert context["correct_answer"] == "A"


@pytest.mark.asyncio
async def test_sqlite_store_recovers_stale_running_turn_before_creating_new_turn(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Turns", session_id="session-turns")
    stale_turn = await store.create_turn(session["id"], capability="chat")

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE turns SET updated_at = ? WHERE id = ?",
            (time.time() - 400, stale_turn["id"]),
        )
        conn.commit()

    next_turn = await store.create_turn(session["id"], capability="chat")
    stale_detail = await store.get_turn(stale_turn["id"])

    assert stale_detail is not None
    assert stale_detail["status"] == "failed"
    assert next_turn["id"] != stale_turn["id"]
