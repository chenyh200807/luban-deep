from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "extract_wechat_tutorbot_authority_ledger.py"
    spec = importlib.util.spec_from_file_location("extract_wechat_tutorbot_authority_ledger", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_script()


def _init_db(path: Path) -> None:
    now = time.time()
    with sqlite3.connect(path) as conn:
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
                created_at REAL NOT NULL,
                UNIQUE(turn_id, seq)
            );
            """
        )
        runtime_state = {
            "active_object": {
                "object_type": "single_question",
                "object_id": "historical:q1",
                "version": 2,
                "source_turn_id": "turn_1",
                "state_snapshot": {
                    "question_id": "historical:q1",
                    "correct_answer": "D",
                    "user_answer": "C",
                    "is_correct": False,
                },
            }
        }
        conn.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, preferences_json, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "conv_1",
                "屋面坡度题",
                now,
                now,
                json.dumps({"runtime_state": runtime_state}, ensure_ascii=False),
                "wx_miniprogram",
            ),
        )
        conn.execute(
            """
            INSERT INTO turns (id, session_id, capability, status, created_at, updated_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("turn_1", "conv_1", "deep_question", "completed", now, now, now),
        )
        metadata = {
            "response": "正确答案是 D。",
            "mode": "followup",
            "execution_path": "deep_question_followup",
            "question_id": "historical:q1",
            "question_followup_context": {
                "question_id": "historical:q1",
                "question": "屋面坡度最小值是？",
                "options": {"C": "3%", "D": "5%"},
                "correct_answer": "D",
                "user_answer": "C",
                "is_correct": False,
            },
            "active_object": {
                "object_type": "single_question",
                "object_id": "historical:q1",
                "version": 2,
                "source_turn_id": "turn_1",
                "state_snapshot": {
                    "question_id": "historical:q1",
                    "correct_answer": "D",
                    "user_answer": "C",
                    "is_correct": False,
                },
            },
            "turn_semantic_decision": {
                "relation_to_active_object": "ask_about_active_object",
                "next_action": "route_to_followup_explainer",
            },
            "question_lifecycle_decision": {
                "scene": "mcq_grading",
                "decision_source": "deterministic",
            },
        }
        conn.execute(
            """
            INSERT INTO turn_events (
                turn_id, seq, type, source, stage, content, metadata_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "turn_1",
                1,
                "result",
                "deep_question",
                "",
                "",
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO turn_events (
                turn_id, seq, type, source, stage, content, metadata_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "turn_1",
                2,
                "done",
                "deep_question",
                "",
                "",
                json.dumps({"status": "completed"}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()


def test_extract_turn_authority_row_reads_persisted_internal_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_history.db"
    _init_db(db_path)

    rows = LEDGER.extract_authority_rows(
        db_path,
        turn_specs=["QA30-REAL-X=turn_1"],
        conversation_ids=[],
        entry_surface="real_wechat_package",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["round_id"] == "QA30-REAL-X"
    assert row["conversation_id"] == "conv_1"
    assert row["question_id"] == "historical:q1"
    assert row["official_answer"] == "D"
    assert row["learner_answer"] == "C"
    assert row["active_object_ref"]["object_id"] == "historical:q1"
    assert row["session_active_object_ref"]["object_id"] == "historical:q1"
    assert row["turn_semantic_decision"]["next_action"] == "route_to_followup_explainer"
    assert row["question_lifecycle_decision"]["scene"] == "mcq_grading"
    assert row["trace_expectation"] == "active_question_followup_or_grading"
    assert row["trace_complete"] is True
    assert row["missing_trace_fields"] == []


def test_extract_conversation_exports_all_turns(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_history.db"
    _init_db(db_path)

    rows = LEDGER.extract_authority_rows(
        db_path,
        turn_specs=[],
        conversation_ids=["conv_1"],
        entry_surface="real_wechat_package",
    )

    assert [row["turn_id"] for row in rows] == ["turn_1"]


def test_extract_turn_authority_row_reports_trace_gaps(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_history.db"
    _init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE turn_events SET metadata_json = ? WHERE turn_id = ? AND type = 'result'",
            (json.dumps({"response": "普通回答"}, ensure_ascii=False), "turn_1"),
        )
        conn.commit()

    rows = LEDGER.extract_authority_rows(
        db_path,
        turn_specs=["turn_1"],
        conversation_ids=[],
        entry_surface="real_wechat_package",
    )

    assert rows[0]["trace_complete"] is False
    assert rows[0]["missing_trace_fields"] == ["result_mode", "answer_authority_source"]
