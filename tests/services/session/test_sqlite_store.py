from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

from deeptutor.services.path_service import PathService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key


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


def test_sqlite_store_migrates_legacy_notebook_owner_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-notebook.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                compressed_summary TEXT DEFAULT '',
                summary_up_to_msg_id INTEGER DEFAULT 0,
                preferences_json TEXT DEFAULT '{}'
            );

            CREATE TABLE notebook_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                question_id TEXT NOT NULL,
                question TEXT NOT NULL,
                question_type TEXT DEFAULT '',
                options_json TEXT DEFAULT '{}',
                correct_answer TEXT DEFAULT '',
                explanation TEXT DEFAULT '',
                difficulty TEXT DEFAULT '',
                user_answer TEXT DEFAULT '',
                is_correct INTEGER DEFAULT 0,
                bookmarked INTEGER DEFAULT 0,
                followup_session_id TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(session_id, question_id)
            );

            CREATE TABLE notebook_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL
            );

            CREATE TABLE notebook_entry_categories (
                entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES notebook_categories(id) ON DELETE CASCADE,
                PRIMARY KEY (entry_id, category_id)
            );
            """
        )
        conn.commit()

    store = SQLiteSessionStore(db_path=db_path)

    with sqlite3.connect(store.db_path) as conn:
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        entry_columns = {row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)").fetchall()}
        category_columns = {row[1] for row in conn.execute("PRAGMA table_info(notebook_categories)").fetchall()}

    assert "owner_key" in session_columns
    assert "owner_key" in entry_columns
    assert "owner_key" in category_columns


def test_sqlite_store_backfills_session_source_archived_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-session-metadata.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                compressed_summary TEXT DEFAULT '',
                summary_up_to_msg_id INTEGER DEFAULT 0,
                preferences_json TEXT DEFAULT '{}',
                owner_key TEXT DEFAULT ''
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (
                id, title, created_at, updated_at, preferences_json, owner_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "session_mobile",
                "Mobile",
                1.0,
                1.0,
                '{"source":"wx_miniprogram","archived":true,"user_id":"student_demo"}',
                "",
            ),
        )
        conn.commit()

    store = SQLiteSessionStore(db_path=db_path)

    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        row = conn.execute(
            "SELECT owner_key, source, archived FROM sessions WHERE id = ?",
            ("session_mobile",),
        ).fetchone()

    assert "source" in columns
    assert "archived" in columns
    assert row is not None
    assert row["owner_key"] == build_user_owner_key("student_demo")
    assert row["source"] == "wx_miniprogram"
    assert row["archived"] == 1


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(db_path=tmp_path / "test.db")


def _make_items(*specs):
    items = []
    for qid, question, is_correct in specs:
        items.append(
            {
                "question_id": qid,
                "question": question,
                "question_type": "choice",
                "options": {"A": "opt_a", "B": "opt_b"},
                "user_answer": "A",
                "correct_answer": "B",
                "explanation": "expl",
                "difficulty": "medium",
                "is_correct": is_correct,
            }
        )
    return items


def test_upsert_notebook_entries_persists_all(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session(title="Test"))
    items = _make_items(("q1", "2+2?", False), ("q2", "3+3?", True), ("q3", "5+5?", False))
    upserted = asyncio.run(store.upsert_notebook_entries(session["id"], items))
    assert upserted == 3
    result = asyncio.run(store.list_notebook_entries())
    assert result["total"] == 3
    assert all(entry["session_title"] == "Test" for entry in result["items"])


def test_add_message_updates_mobile_placeholder_title(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session(title="新对话", source="wx_miniprogram"))
    asyncio.run(store.add_message(session["id"], "user", "建筑构造是什么？"))
    updated = asyncio.run(store.get_session(session["id"]))
    assert updated is not None
    assert updated["title"] == "建筑构造是什么？"


def test_upsert_notebook_entries_updates_on_conflict(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    sid = session["id"]
    asyncio.run(store.upsert_notebook_entries(sid, _make_items(("q1", "Q?", False))))
    result = asyncio.run(store.list_notebook_entries())
    assert result["items"][0]["is_correct"] is False

    asyncio.run(
        store.upsert_notebook_entries(
            sid,
            [
                {
                    "question_id": "q1",
                    "question": "Q?",
                    "user_answer": "B",
                    "correct_answer": "B",
                    "is_correct": True,
                }
            ],
        )
    )
    result = asyncio.run(store.list_notebook_entries())
    assert result["total"] == 1
    assert result["items"][0]["is_correct"] is True
    assert result["items"][0]["user_answer"] == "B"


def test_upsert_skips_blank_questions(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    items = [
        {"question_id": "q1", "question": "", "is_correct": False},
        {"question_id": "", "question": "Valid?", "is_correct": False},
        {"question_id": "q3", "question": "OK?", "is_correct": False},
    ]
    upserted = asyncio.run(store.upsert_notebook_entries(session["id"], items))
    assert upserted == 1


def test_upsert_unknown_session_raises(store: SQLiteSessionStore) -> None:
    with pytest.raises(ValueError, match="Session not found"):
        asyncio.run(store.upsert_notebook_entries("nope", _make_items(("q1", "Q?", False))))


def test_list_entries_filters_bookmarked(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q1?", False), ("q2", "Q2?", True))))
    entries = asyncio.run(store.list_notebook_entries())["items"]
    asyncio.run(store.update_notebook_entry(entries[0]["id"], {"bookmarked": True}))
    bookmarked = asyncio.run(store.list_notebook_entries(bookmarked=True))
    assert bookmarked["total"] == 1
    assert bookmarked["items"][0]["bookmarked"] is True


def test_list_entries_filters_is_correct(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q1?", False), ("q2", "Q2?", True))))
    wrong = asyncio.run(store.list_notebook_entries(is_correct=False))
    assert wrong["total"] == 1
    assert wrong["items"][0]["question_id"] == "q1"


def test_list_sessions_by_owner_filters_source_and_archived(store: SQLiteSessionStore) -> None:
    owner_key = build_user_owner_key("student_demo")
    other_owner_key = build_user_owner_key("student_other")

    asyncio.run(store.create_session(session_id="wx_live", owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            "wx_live",
            {
                "source": "wx_miniprogram",
                "archived": False,
            },
        )
    )

    asyncio.run(store.create_session(session_id="wx_archived", owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            "wx_archived",
            {
                "source": "wx_miniprogram",
                "archived": True,
            },
        )
    )

    asyncio.run(store.create_session(session_id="web_live", owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            "web_live",
            {
                "source": "web",
                "archived": False,
            },
        )
    )

    asyncio.run(store.create_session(session_id="other_owner", owner_key=other_owner_key))
    asyncio.run(
        store.update_session_preferences(
            "other_owner",
            {
                "source": "wx_miniprogram",
                "archived": False,
            },
        )
    )

    active = asyncio.run(
        store.list_sessions_by_owner(
            owner_key,
            source="wx_miniprogram",
            archived=False,
        )
    )
    archived = asyncio.run(
        store.list_sessions_by_owner(
            owner_key,
            source="wx_miniprogram",
            archived=True,
        )
    )

    assert [item["id"] for item in active] == ["wx_live"]
    assert [item["id"] for item in archived] == ["wx_archived"]
    assert active[0]["preferences"]["source"] == "wx_miniprogram"
    assert active[0]["preferences"]["archived"] is False


def test_list_sessions_supports_keyset_cursor(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="session-a", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_session(session_id="session-b", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_session(session_id="session-c", owner_key=build_user_owner_key("student_demo")))

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (300.0, "session-a"))
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (200.0, "session-b"))
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (100.0, "session-c"))
        conn.commit()

    first_page = asyncio.run(store.list_sessions(limit=2))
    assert [item["session_id"] for item in first_page] == ["session-a", "session-b"]

    second_page = asyncio.run(
        store.list_sessions(limit=2, before_updated_at=200.0, before_session_id="session-b")
    )
    assert [item["session_id"] for item in second_page] == ["session-c"]


def test_update_notebook_entry_bookmark_roundtrip(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    entry_id = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    assert asyncio.run(store.update_notebook_entry(entry_id, {"bookmarked": True})) is True
    assert asyncio.run(store.get_notebook_entry(entry_id))["bookmarked"] is True
    assert asyncio.run(store.update_notebook_entry(entry_id, {"bookmarked": False})) is True
    assert asyncio.run(store.get_notebook_entry(entry_id))["bookmarked"] is False
    assert asyncio.run(store.update_notebook_entry(99999, {"bookmarked": True})) is False


def test_update_followup_session_id(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    entry_id = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    asyncio.run(store.update_notebook_entry(entry_id, {"followup_session_id": "sess_fu"}))
    entry = asyncio.run(store.get_notebook_entry(entry_id))
    assert entry["followup_session_id"] == "sess_fu"


def test_list_notebook_entries_supports_keyset_cursor(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session(session_id="notebook-cursor"))
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q1", False), ("q2", "Q2", False), ("q3", "Q3", False))))

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE notebook_entries SET created_at = ?, updated_at = ? WHERE question_id = ?", (300.0, 300.0, "q1"))
        conn.execute("UPDATE notebook_entries SET created_at = ?, updated_at = ? WHERE question_id = ?", (200.0, 200.0, "q2"))
        conn.execute("UPDATE notebook_entries SET created_at = ?, updated_at = ? WHERE question_id = ?", (100.0, 100.0, "q3"))
        conn.commit()

    first_page = asyncio.run(store.list_notebook_entries(limit=2))
    assert [item["question_id"] for item in first_page["items"]] == ["q1", "q2"]

    second_page = asyncio.run(
        store.list_notebook_entries(
            limit=2,
            before_created_at=200.0,
            before_entry_id=first_page["items"][-1]["id"],
        )
    )
    assert [item["question_id"] for item in second_page["items"]] == ["q3"]


def test_find_notebook_entry(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    found = asyncio.run(store.find_notebook_entry(session["id"], "q1"))
    assert found is not None
    assert found["question_id"] == "q1"
    assert asyncio.run(store.find_notebook_entry(session["id"], "nope")) is None


def test_delete_notebook_entry(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q1?", False), ("q2", "Q2?", False))))
    entry_id = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    assert asyncio.run(store.delete_notebook_entry(entry_id)) is True
    assert asyncio.run(store.list_notebook_entries())["total"] == 1
    assert asyncio.run(store.delete_notebook_entry(99999)) is False


def test_entries_cascade_on_session_delete(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    assert asyncio.run(store.list_notebook_entries())["total"] == 1
    asyncio.run(store.delete_session(session["id"]))
    assert asyncio.run(store.list_notebook_entries())["total"] == 0


def test_category_crud(store: SQLiteSessionStore) -> None:
    category = asyncio.run(store.create_category("Math"))
    assert category["name"] == "Math"
    categories = asyncio.run(store.list_categories())
    assert len(categories) == 1
    assert categories[0]["entry_count"] == 0

    asyncio.run(store.rename_category(category["id"], "Algebra"))
    categories = asyncio.run(store.list_categories())
    assert categories[0]["name"] == "Algebra"

    asyncio.run(store.delete_category(category["id"]))
    assert asyncio.run(store.list_categories()) == []


def test_entry_category_association(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    entry_id = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    category = asyncio.run(store.create_category("Physics"))

    assert asyncio.run(store.add_entry_to_category(entry_id, category["id"])) is True
    entry = asyncio.run(store.get_notebook_entry(entry_id))
    assert len(entry["categories"]) == 1
    assert entry["categories"][0]["name"] == "Physics"

    by_category = asyncio.run(store.list_notebook_entries(category_id=category["id"]))
    assert by_category["total"] == 1

    asyncio.run(store.remove_entry_from_category(entry_id, category["id"]))
    assert asyncio.run(store.get_entry_categories(entry_id)) == []


def test_category_cascade_on_entry_delete(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    entry_id = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    category = asyncio.run(store.create_category("History"))
    asyncio.run(store.add_entry_to_category(entry_id, category["id"]))
    asyncio.run(store.delete_notebook_entry(entry_id))
    categories = asyncio.run(store.list_categories())
    assert categories[0]["entry_count"] == 0


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
async def test_sqlite_store_projects_and_backfills_presentation_from_legacy_summary(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Quiz", session_id="session-legacy-presentation")

    await store.add_message(
        session["id"],
        "assistant",
        "### Question 1\n某防水工程题目",
        capability="deep_question",
        events=[
            {
                "type": "result",
                "metadata": {
                    "summary": {
                        "results": [
                            {
                                "qa_pair": {
                                    "question_id": "q_1",
                                    "question": "某防水工程题目",
                                    "question_type": "choice",
                                    "options": {"A": "方案A", "B": "方案B"},
                                    "correct_answer": "B",
                                    "explanation": "B 更符合规范。",
                                }
                            }
                        ]
                    }
                },
            }
        ],
    )

    messages = await store.get_messages(session["id"])
    metadata = messages[0]["events"][0]["metadata"]
    assert isinstance(metadata["summary"], dict)
    assert "presentation" not in metadata

    stats = await store.backfill_message_presentations(session["id"])
    assert stats == {"scanned": 1, "updated": 1}

    messages = await store.get_messages(session["id"])
    metadata = messages[0]["events"][0]["metadata"]
    assert "summary" not in metadata
    assert metadata["presentation"]["blocks"][0]["questions"][0]["question_id"] == "q_1"

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT events_json FROM messages WHERE session_id = ?",
            (session["id"],),
        ).fetchone()
    persisted_events = json.loads(row[0])
    persisted_metadata = persisted_events[0]["metadata"]
    assert "summary" not in persisted_metadata
    assert persisted_metadata["presentation"]["blocks"][0]["questions"][0]["question_id"] == "q_1"


@pytest.mark.asyncio
async def test_sqlite_store_archives_unrenderable_summary_as_plain_text(
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Written", session_id="session-legacy-written")

    await store.add_message(
        session["id"],
        "assistant",
        "### Question 1\n请说明流水施工的基本特点。",
        capability="deep_question",
        events=[
            {
                "type": "result",
                "metadata": {
                    "summary": {
                        "results": [
                            {
                                "qa_pair": {
                                    "question_id": "q_1",
                                    "question": "请说明流水施工的基本特点。",
                                    "question_type": "written",
                                    "correct_answer": "略",
                                    "explanation": "略",
                                }
                            }
                        ]
                    }
                },
            }
        ],
    )

    before = await store.get_messages(session["id"])
    before_metadata = before[0]["events"][0]["metadata"]
    assert isinstance(before_metadata["summary"], dict)
    assert "presentation" not in before_metadata

    stats = await store.backfill_message_presentations(session["id"])
    assert stats == {"scanned": 1, "updated": 1}

    after = await store.get_messages(session["id"])
    after_metadata = after[0]["events"][0]["metadata"]
    assert "summary" not in after_metadata
    assert "presentation" not in after_metadata


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
