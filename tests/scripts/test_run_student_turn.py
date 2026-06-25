from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_student_turn",
    REPO / "scripts" / "run_student_turn.py",
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def test_db_reconcile_extracts_turn_events_and_message_truth(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_history.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                preferences_json TEXT DEFAULT '{}',
                source TEXT DEFAULT '',
                archived INTEGER DEFAULT 0,
                owner_key TEXT DEFAULT '',
                conversation_id TEXT DEFAULT ''
            );
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                capability TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                error TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                finished_at REAL
            );
            CREATE TABLE turn_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                source TEXT DEFAULT '',
                stage TEXT DEFAULT '',
                content TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                capability TEXT DEFAULT '',
                events_json TEXT DEFAULT '',
                attachments_json TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, conversation_id)
            VALUES ('session-a', 'A', 1, 1, 'conv-1')
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, conversation_id)
            VALUES ('mirror-session', 'Mirror', 1, 1, 'conv-1')
            """
        )
        conn.execute(
            """
            INSERT INTO turns (id, session_id, capability, status, created_at, updated_at, finished_at)
            VALUES ('turn-1', 'session-a', 'chat', 'completed', 1, 2, 2)
            """
        )
        conn.execute(
            """
            INSERT INTO turn_events (
                turn_id, seq, type, source, stage, content, metadata_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "turn-1",
                1,
                "result",
                "turn_runtime",
                "",
                "",
                json.dumps({"response": "DB terminal answer"}, ensure_ascii=False),
                2,
                2,
            ),
        )
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, metadata_json, created_at)
            VALUES ('session-a', 'assistant', 'Assistant canonical content', ?, 2)
            """,
            (
                json.dumps(
                    {
                        "turn_id": "turn-1",
                        "engine_turn_id": "turn-1",
                        "client_turn_id": "client-1",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, metadata_json, created_at)
            VALUES ('mirror-session', 'user', 'LLM prompt envelope mirror', '{}', 2)
            """
        )
        conn.commit()

    reconciled = mod._reconcile_db_truth(
        db_path=db_path,
        turn_id="turn-1",
        conversation_id="conv-1",
        client_turn_id="client-1",
    )

    assert reconciled["checked"] is True
    assert reconciled["matched"] is True
    assert reconciled["turn"]["status"] == "completed"
    assert reconciled["terminal_event"]["response"] == "DB terminal answer"
    assert reconciled["assistant_message"]["content"] == "Assistant canonical content"
    assert {session["id"] for session in reconciled["conversation_sessions"]} == {
        "session-a",
        "mirror-session",
    }


def test_turn_surfaces_ws_exception_without_dropping_turn_identity(monkeypatch) -> None:
    async def fake_request_json(_client, _method, path, *, headers=None, json_body=None):
        assert path == "/api/v1/chat/start-turn"
        assert json_body["client_turn_id"].startswith("studentarmy_")
        return (
            200,
            {
                "conversation": {"id": "conv-1"},
                "turn": {"id": "turn-1"},
                "stream": {
                    "subscribe": {
                        "type": "subscribe_turn",
                        "turn_id": "turn-1",
                        "after_seq": 0,
                    }
                },
            },
        )

    class BrokenWebSocket:
        async def __aenter__(self):
            raise ConnectionError("network closed")

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(mod, "_request_json", fake_request_json)
    monkeypatch.setattr(mod.websockets, "connect", lambda *_args, **_kwargs: BrokenWebSocket())

    result = asyncio.run(
        mod._turn(
            "https://example.test",
            "token",
            "conv-1",
            "请出一道题",
            timeout=0.01,
        )
    )

    assert result["conversation_id"] == "conv-1"
    assert result["turn_id"] == "turn-1"
    assert result["client_turn_id"].startswith("studentarmy_")
    assert result["status"] == "ws_exception"
    assert result["ws_error"].startswith("ws_exception:ConnectionError:")
    assert result["db_reconciled"] == {"checked": False, "status": "not_requested"}
    assert "latency" in result


def test_append_jsonl_writes_incremental_record(tmp_path: Path) -> None:
    out_path = tmp_path / "turns.jsonl"
    mod._append_jsonl(out_path, {"turn_id": "turn-1", "status": "ws_exception"})
    mod._append_jsonl(out_path, {"turn_id": "turn-2", "status": "completed"})

    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]

    assert rows == [
        {"turn_id": "turn-1", "status": "ws_exception"},
        {"turn_id": "turn-2", "status": "completed"},
    ]
