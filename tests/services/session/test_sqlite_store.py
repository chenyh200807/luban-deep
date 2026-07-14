from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
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


def test_sqlite_store_falls_back_to_legacy_db_when_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

        monkeypatch.setattr("deeptutor.services.session.sqlite_store.os.replace", lambda _src, _dst: (_ for _ in ()).throw(OSError("move denied")))

        store = SQLiteSessionStore()

        assert store.db_path == legacy_db
        with sqlite3.connect(store.db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "legacy" in tables
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_sqlite_store_persists_message_metadata(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = asyncio.run(store.create_session(title="Demo", session_id="session-demo"))

    asyncio.run(
        store.add_message(
            session_id=session["id"],
            role="user",
            content="请分析这道题",
            capability="chat",
            metadata={
                "request_snapshot": {
                    "content": "请分析这道题",
                    "enabledTools": ["rag"],
                    "knowledgeBases": ["construction-exam"],
                }
            },
        )
    )

    detail = asyncio.run(store.get_session_with_messages(session["id"]))

    assert detail is not None
    assert detail["messages"][0]["metadata"] == {
        "request_snapshot": {
            "content": "请分析这道题",
            "enabledTools": ["rag"],
            "knowledgeBases": ["construction-exam"],
        }
    }


def test_luban_webview_capabilities_are_scoped_hashed_and_expire(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "webview-capability.db")

    entry_ticket = asyncio.run(
        store.issue_luban_card_entry_ticket(user_id="student_real", pack_id="f16")
    )
    entry_access = asyncio.run(store.resolve_luban_card_entry_ticket(entry_ticket, pack_id="F16"))
    assert entry_access is not None
    assert entry_access["user_id"] == "student_real"
    assert entry_access["pack_id"] == "F16"
    assert entry_access["turn_id"] == ""
    assert entry_access["expires_at"] > time.time()
    assert asyncio.run(store.resolve_luban_card_entry_ticket(entry_ticket, pack_id="D11")) is None

    stream_ticket = asyncio.run(
        store.issue_luban_turn_stream_ticket(
            user_id="student_real", pack_id="F16", turn_id="turn-real"
        )
    )
    stream_access = asyncio.run(store.resolve_luban_turn_stream_ticket(stream_ticket))
    assert stream_access is not None
    assert stream_access["user_id"] == "student_real"
    assert stream_access["pack_id"] == "F16"
    assert stream_access["turn_id"] == "turn-real"

    with store._connect() as conn:
        raw_rows = conn.execute("SELECT ticket_digest FROM webview_access_tickets").fetchall()
        assert all(entry_ticket not in str(row["ticket_digest"]) for row in raw_rows)
        conn.execute("UPDATE webview_access_tickets SET expires_at = 0 WHERE ticket_digest = ?", (store._webview_ticket_digest(stream_ticket),))
        conn.commit()
    assert asyncio.run(store.resolve_luban_turn_stream_ticket(stream_ticket)) is None


def test_sqlite_store_migrates_legacy_messages_metadata_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-messages.db"
    now = time.time()
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
                source TEXT DEFAULT '',
                archived INTEGER DEFAULT 0,
                owner_key TEXT DEFAULT '',
                conversation_id TEXT DEFAULT ''
            );

            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                capability TEXT DEFAULT '',
                events_json TEXT DEFAULT '',
                attachments_json TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at)
            VALUES ('legacy-session', 'Legacy', ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO messages (
                session_id, role, content, capability, events_json, attachments_json, created_at
            ) VALUES ('legacy-session', 'user', 'legacy message', 'chat', '[]', '[]', ?)
            """,
            (now,),
        )
        conn.commit()

    store = SQLiteSessionStore(db_path)
    detail = asyncio.run(store.get_session_with_messages("legacy-session"))

    assert detail is not None
    assert detail["messages"][0]["metadata"] == {}

    asyncio.run(
        store.add_message(
            session_id="legacy-session",
            role="user",
            content="new message",
            metadata={"request_snapshot": {"content": "new message"}},
        )
    )
    updated = asyncio.run(store.get_session_with_messages("legacy-session"))
    assert updated is not None
    assert updated["messages"][1]["metadata"] == {
        "request_snapshot": {"content": "new message"}
    }


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


def test_sqlite_store_migrates_legacy_category_uniqueness_to_owner_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-category-unique.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE notebook_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                owner_key TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO notebook_categories (name, owner_key, created_at)
            VALUES (?, ?, ?)
            """,
            ("错题", "user:u1", 1.0),
        )
        conn.commit()

    store = SQLiteSessionStore(db_path=db_path)

    existing = asyncio.run(store.list_categories(owner_key="user:u1"))
    created = asyncio.run(store.create_category("错题", owner_key="user:u2"))

    assert [item["name"] for item in existing] == ["错题"]
    assert created["owner_key"] == "user:u2"


def test_sqlite_store_prunes_cross_owner_category_links_during_owner_scope_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-category-cross-owner.db"
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

            CREATE TABLE notebook_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                owner_key TEXT DEFAULT '',
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
                owner_key TEXT DEFAULT '',
                created_at REAL NOT NULL
            );

            CREATE TABLE notebook_entry_categories (
                entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES notebook_categories(id) ON DELETE CASCADE,
                PRIMARY KEY (entry_id, category_id)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, owner_key)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """,
            (
                "s1",
                "u1",
                1.0,
                1.0,
                "user:u1",
                "s2",
                "u2",
                1.0,
                1.0,
                "user:u2",
            ),
        )
        conn.execute(
            """
            INSERT INTO notebook_entries (
                id, session_id, owner_key, question_id, question, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "s1",
                "user:u1",
                "q1",
                "Q1",
                1.0,
                1.0,
                2,
                "s2",
                "user:u2",
                "q2",
                "Q2",
                1.0,
                1.0,
            ),
        )
        conn.execute(
            """
            INSERT INTO notebook_categories (id, name, owner_key, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (1, "错题", "", 1.0),
        )
        conn.execute(
            """
            INSERT INTO notebook_entry_categories (entry_id, category_id)
            VALUES (?, ?), (?, ?)
            """,
            (1, 1, 2, 1),
        )
        conn.commit()

    store = SQLiteSessionStore(db_path=db_path)

    u1_categories = asyncio.run(store.get_entry_categories(1, owner_key="user:u1"))
    u2_categories = asyncio.run(store.get_entry_categories(2, owner_key="user:u2"))
    u1_list = asyncio.run(store.list_categories(owner_key="user:u1"))
    u2_list = asyncio.run(store.list_categories(owner_key="user:u2"))

    assert [item["name"] for item in u1_categories] == ["错题"]
    assert u2_categories == []
    assert [(item["name"], item["entry_count"]) for item in u1_list] == [("错题", 1)]
    assert u2_list == []


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
            "SELECT owner_key, source, archived, conversation_id FROM sessions WHERE id = ?",
            ("session_mobile",),
        ).fetchone()

    assert "source" in columns
    assert "archived" in columns
    assert "conversation_id" in columns
    assert row is not None
    assert row["owner_key"] == build_user_owner_key("student_demo")
    assert row["source"] == "wx_miniprogram"
    assert row["archived"] == 1
    assert row["conversation_id"] == "session_mobile"


def test_sqlite_store_rewrite_owner_keys_merges_duplicate_categories_and_preferences(tmp_path: Path) -> None:
    db_path = tmp_path / "owner-key-rewrite.db"
    store = SQLiteSessionStore(db_path=db_path)
    old_owner_key = build_user_owner_key("user_2008")
    new_owner_key = build_user_owner_key("2d9eac15-5d26-4e93-941b-9ec6345ce6d9")

    asyncio.run(store.create_session(title="旧会话", session_id="legacy_session", owner_key=old_owner_key))
    asyncio.run(
        store.update_session_preferences(
            "legacy_session",
            {
                "user_id": "user_2008",
                "owner_key": old_owner_key,
                "source": "wx",
            },
        )
    )
    asyncio.run(
        store.upsert_notebook_entries(
            "legacy_session",
            [
                {
                    "question_id": "q_1",
                    "question": "地基承载力怎么判断？",
                    "question_type": "single_choice",
                }
            ],
        )
    )
    old_category = asyncio.run(store.create_category("错题", owner_key=old_owner_key))
    new_category = asyncio.run(store.create_category("错题", owner_key=new_owner_key))
    legacy_entry = asyncio.run(store.find_notebook_entry("legacy_session", "q_1", owner_key=old_owner_key))
    assert legacy_entry is not None
    asyncio.run(store.add_entry_to_category(int(legacy_entry["id"]), int(old_category["id"]), owner_key=old_owner_key))

    summary = asyncio.run(
        store.rewrite_owner_keys(
            {
                "user_2008": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            }
        )
    )

    assert summary["sessions_updated"] == 1
    assert summary["entries_updated"] == 1
    assert summary["categories_updated"] == 0
    assert summary["category_links_repointed"] == 1
    assert summary["categories_merged"] == 1

    sessions = asyncio.run(store.list_sessions_by_owner(new_owner_key, limit=10))
    assert [item["session_id"] for item in sessions] == ["legacy_session"]
    session = asyncio.run(store.get_session("legacy_session"))
    assert session is not None
    assert session["preferences"]["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert session["preferences"]["owner_key"] == new_owner_key

    categories = asyncio.run(store.list_categories(owner_key=new_owner_key))
    assert [item["id"] for item in categories] == [new_category["id"]]
    linked_categories = asyncio.run(store.get_entry_categories(int(legacy_entry["id"]), owner_key=new_owner_key))
    assert [item["id"] for item in linked_categories] == [new_category["id"]]


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


def test_session_payloads_do_not_expose_internal_runtime_state(
    store: SQLiteSessionStore,
) -> None:
    session = asyncio.run(store.create_session(session_id="runtime_hidden"))
    asyncio.run(
        store.update_session_preferences(
            session["id"],
            {
                "source": "web",
                "runtime_state": {
                    "active_object": {"object_type": "open_chat_topic", "id": "topic-1"}
                },
            },
        )
    )

    detail = asyncio.run(store.get_session(session["id"]))
    sessions = asyncio.run(store.list_sessions())

    assert detail is not None
    assert "runtime_state" not in detail["preferences"]
    assert sessions[0]["id"] == session["id"]
    assert "runtime_state" not in sessions[0]["preferences"]


def test_list_sessions_by_owner_and_conversation_uses_canonical_id(
    store: SQLiteSessionStore,
) -> None:
    owner_key = build_user_owner_key("student_demo")

    asyncio.run(store.create_session(session_id="tb_123", owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            "tb_123",
            {
                "source": "wx_miniprogram",
                "conversation_id": "tb_123",
                "user_id": "student_demo",
            },
        )
    )

    mirror_id = "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123"
    asyncio.run(store.create_session(session_id=mirror_id, owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            mirror_id,
            {
                "source": "wx_miniprogram",
                "conversation_id": "tb_123",
                "user_id": "student_demo",
                "bot_id": "construction-exam-coach",
            },
        )
    )

    matches = asyncio.run(
        store.list_sessions_by_owner_and_conversation(
            owner_key,
            "tb_123",
            source="wx_miniprogram",
        )
    )

    assert {item["id"] for item in matches} == {"tb_123", mirror_id}


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


def test_category_name_is_unique_per_owner_only(store: SQLiteSessionStore) -> None:
    own = asyncio.run(store.create_category("错题", owner_key=build_user_owner_key("student_demo")))
    other = asyncio.run(store.create_category("错题", owner_key=build_user_owner_key("student_other")))

    assert own["owner_key"] == build_user_owner_key("student_demo")
    assert other["owner_key"] == build_user_owner_key("student_other")

    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(store.create_category("错题", owner_key=build_user_owner_key("student_demo")))


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


@pytest.mark.asyncio
async def test_recover_all_orphaned_turns_sweeps_running_across_sessions(
    tmp_path: Path,
) -> None:
    """Startup sweep fails every ``running`` turn regardless of session or age.

    After a crash the process holds no in-memory turn tasks, so a ``running``
    row in SQLite is provably orphaned even if ``updated_at`` is recent — the
    _run_turn finally never executed. The sweep is therefore intentionally
    unconditional (no per-session, no age cutoff). Terminal rows and a fresh
    ``running`` row from a *different* session are both checked.
    """
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session_a = await store.create_session(title="A", session_id="session-a")
    session_b = await store.create_session(title="B", session_id="session-b")

    # A terminal turn that must NOT be touched. Complete it first so the
    # session can then hold a fresh running turn (one active turn per session).
    completed = await store.create_turn(session_a["id"], capability="chat")
    await store.update_turn_status(completed["id"], "completed")

    # Orphan A: old running turn (simulates a long-lived crashed turn).
    orphan_old = await store.create_turn(session_a["id"], capability="chat")
    # Orphan B: a fresh running turn in another session (updated_at ~ now).
    orphan_fresh = await store.create_turn(session_b["id"], capability="deep_solve")

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE turns SET updated_at = ? WHERE id = ?",
            (time.time() - 999, orphan_old["id"]),
        )
        conn.commit()

    recovered = await store.recover_all_orphaned_turns("orphaned_on_restart")
    assert recovered == 2

    old_detail = await store.get_turn(orphan_old["id"])
    fresh_detail = await store.get_turn(orphan_fresh["id"])
    completed_detail = await store.get_turn(completed["id"])

    assert old_detail is not None
    assert old_detail["status"] == "failed"
    assert old_detail["error"] == "orphaned_on_restart"
    assert old_detail["finished_at"] is not None

    assert fresh_detail is not None
    assert fresh_detail["status"] == "failed"
    assert fresh_detail["error"] == "orphaned_on_restart"
    assert fresh_detail["finished_at"] is not None

    # Terminal turn is preserved verbatim.
    assert completed_detail is not None
    assert completed_detail["status"] == "completed"


@pytest.mark.asyncio
async def test_update_turn_status_terminal_state_absorbs(tmp_path: Path) -> None:
    """Turn FSM (律4): terminal states absorb — running is the ONLY writable
    pre-state. A cross-worker cancel must never be resurrected to ``completed``
    by a late terminal commit (production example C: cancel flipped the DB row,
    the execution worker unconditionally wrote completed 39s later)."""
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="FSM", session_id="session-fsm")
    turn = await store.create_turn(session["id"], capability="chat")

    # running -> cancelled: allowed, reports True.
    assert await store.update_turn_status(turn["id"], "cancelled", "superseded") is True

    # cancelled -> completed: rejected, reports False, row unchanged.
    assert await store.update_turn_status(turn["id"], "completed") is False
    detail = await store.get_turn(turn["id"])
    assert detail is not None
    assert detail["status"] == "cancelled"
    assert detail["error"] == "superseded"

    # cancelled -> failed is equally absorbed (no terminal-to-terminal hops).
    assert await store.update_turn_status(turn["id"], "failed", "late failure") is False
    detail = await store.get_turn(turn["id"])
    assert detail["status"] == "cancelled"


@pytest.mark.asyncio
async def test_update_turn_status_running_to_terminal_still_works(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="FSM2", session_id="session-fsm2")
    turn = await store.create_turn(session["id"], capability="chat")

    assert await store.update_turn_status(turn["id"], "completed") is True
    detail = await store.get_turn(turn["id"])
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["finished_at"] is not None


@pytest.mark.asyncio
async def test_list_all_running_turns_returns_orphan_candidates(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session_a = await store.create_session(title="A", session_id="session-run-a")
    session_b = await store.create_session(title="B", session_id="session-run-b")
    done = await store.create_turn(session_a["id"], capability="chat")
    await store.update_turn_status(done["id"], "completed")
    running_a = await store.create_turn(session_a["id"], capability="chat")
    running_b = await store.create_turn(session_b["id"], capability="chat")

    running = await store.list_all_running_turns()
    listed = {(item["id"], item["session_id"]) for item in running}
    assert listed == {
        (running_a["id"], session_a["id"]),
        (running_b["id"], session_b["id"]),
    }


@pytest.mark.asyncio
async def test_recover_all_orphaned_turns_is_idempotent(tmp_path: Path) -> None:
    """A second sweep finds no ``running`` rows and reports 0."""
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    session = await store.create_session(title="Idem", session_id="session-idem")
    await store.create_turn(session["id"], capability="chat")

    first = await store.recover_all_orphaned_turns("orphaned_on_restart")
    assert first == 1

    second = await store.recover_all_orphaned_turns("orphaned_on_restart")
    assert second == 0


def test_connect_uses_wal_and_synchronous_normal(tmp_path: Path) -> None:
    """Runtime per-op connections must inherit WAL + synchronous=NORMAL(1).

    Without an explicit ``PRAGMA synchronous = NORMAL`` on every ``_connect``,
    each new connection falls back to the default FULL, which fsyncs on every
    commit and is the largest single-point write amplification for writes.
    """
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    with store._connect() as conn:
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert synchronous == 1  # NORMAL
    assert journal_mode.lower() == "wal"


def test_runtime_connections_pin_wal_and_synchronous_normal(store: SQLiteSessionStore) -> None:
    """Battle1 W2-T1: every runtime connection must run under the WAL +
    synchronous=NORMAL durability contract, regardless of the SQLite
    compile-time default (stock builds default to FULL per connection)."""
    conn = store._connect()
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    finally:
        conn.close()
    assert str(journal_mode).lower() == "wal"
    assert int(synchronous) == 1  # 1 == NORMAL


# --- Battle1 W2-T2: single-writer thread + lock-free reads ---


def test_concurrent_turn_event_writes_and_reads_stay_consistent(store: SQLiteSessionStore) -> None:
    """8 turns x 50 events written concurrently while readers poll: every turn
    must end with seq 1..50 contiguous (single-writer FIFO keeps ordering)."""

    async def _run() -> None:
        turn_ids: list[str] = []
        for i in range(8):
            session = await store.create_session(title=f"并发写读{i}")
            turn = await store.create_turn(session_id=session["id"])
            turn_ids.append(turn["id"])

        async def _write(turn_id: str) -> None:
            for seq in range(1, 51):
                await store.append_turn_event(
                    turn_id,
                    {"type": "content", "source": "test", "stage": "", "content": f"c{seq}", "metadata": {}},
                )

        async def _poll(turn_id: str) -> None:
            for _ in range(10):
                await store.get_turn_events(turn_id, 0)

        await asyncio.gather(*[_write(t) for t in turn_ids], *[_poll(t) for t in turn_ids])

        for turn_id in turn_ids:
            events = await store.get_turn_events(turn_id, 0)
            seqs = [int(e["seq"]) for e in events]
            assert seqs == list(range(1, 51)), f"{turn_id}: {seqs[:5]}...{seqs[-5:]}"

    asyncio.run(_run())


def test_write_exception_rolls_back_persistent_connection(store: SQLiteSessionStore) -> None:
    """A failing write on the persistent writer connection must not leave an
    open transaction behind (next write succeeds, half-write invisible)."""

    def _bad_write() -> None:
        with store._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("s-rollback", "半写", time.time(), time.time()),
            )
            raise RuntimeError("boom")

    async def _run() -> None:
        with pytest.raises(RuntimeError):
            await store._run(_bad_write)
        # half-write must have been rolled back
        assert await store.get_session("s-rollback") is None
        # writer connection still healthy
        created = await store.create_session(title="正常写", session_id="s-after-rollback")
        assert created["id"] == "s-after-rollback"

    asyncio.run(_run())


def test_reads_do_not_wait_for_writer_thread(store: SQLiteSessionStore) -> None:
    """While the writer thread is deliberately blocked, reads must still
    complete (lock-free read path over WAL)."""

    async def _run() -> None:
        session = await store.create_session(title="读不等写")
        gate = threading.Event()

        def _block_writer() -> None:
            gate.wait(timeout=10)

        blocker = asyncio.get_running_loop().run_in_executor(
            store._write_executor, _block_writer
        )
        try:
            result = await asyncio.wait_for(store.get_session(session["id"]), timeout=2)
            assert result is not None and result["id"] == session["id"]
        finally:
            gate.set()
            await blocker

    asyncio.run(_run())


def test_turn_event_replay_preserves_visibility_field(store: SQLiteSessionStore) -> None:
    """Battle1 latent-bug fix: the replay view (get_turn_events) must be
    field-equivalent to the live fan-out payload — visibility included.
    Legacy rows (written before the column existed) omit the key, matching
    the historical missing-field shape."""

    async def _run() -> None:
        session = await store.create_session(title="回放字段等价")
        turn = await store.create_turn(session_id=session["id"])
        await store.append_turn_event(
            turn["id"],
            {"type": "progress", "source": "turn_runtime", "stage": "understanding",
             "content": "…", "metadata": {"phase": "understanding"}, "visibility": "public"},
        )
        await store.append_turn_event(
            turn["id"],
            {"type": "thinking", "source": "cap", "stage": "", "content": "内部",
             "metadata": {}, "visibility": "internal"},
        )
        # legacy row without visibility
        await store.append_turn_event(
            turn["id"],
            {"type": "content", "source": "cap", "stage": "", "content": "hi", "metadata": {}},
        )
        events = await store.get_turn_events(turn["id"], 0)
        assert events[0]["visibility"] == "public"
        assert events[1]["visibility"] == "internal"
        assert "visibility" not in events[2]

    asyncio.run(_run())
