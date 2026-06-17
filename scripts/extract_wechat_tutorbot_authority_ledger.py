#!/usr/bin/env python3
"""Extract compact WeChat TutorBot authority ledger rows from local session DB.

This is an internal QA adapter. It reads the existing SQLite session/turn store
and summarizes persisted turn-event metadata; it does not create runtime state,
call production APIs, or introduce a second question truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "user" / "chat_history.db"


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _sha256_json(value: Any) -> str:
    if value in (None, "", {}, []):
        return ""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _compact_text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", {}, []):
            return value
    return ""


def _session_runtime_state(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT preferences_json FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return {}
    preferences = _dict(_json_loads(row["preferences_json"], {}))
    return _dict(preferences.get("runtime_state"))


def _turn_row(conn: sqlite3.Connection, turn_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, session_id, capability, status, error, created_at, updated_at, finished_at
        FROM turns
        WHERE id = ?
        """,
        (turn_id,),
    ).fetchone()


def _turn_events(conn: sqlite3.Connection, turn_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT seq, type, source, stage, content, metadata_json, timestamp
        FROM turn_events
        WHERE turn_id = ?
        ORDER BY seq ASC
        """,
        (turn_id,),
    ).fetchall()
    return [
        {
            "seq": int(row["seq"]),
            "type": row["type"] or "",
            "source": row["source"] or "",
            "stage": row["stage"] or "",
            "content": row["content"] or "",
            "metadata": _dict(_json_loads(row["metadata_json"], {})),
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


def _latest_result_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    result_events = [event for event in events if event.get("type") == "result"]
    return result_events[-1] if result_events else {}


def _latest_done_status(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("type") == "done":
            status = str(_dict(event.get("metadata")).get("status") or "").strip()
            if status:
                return status
    return ""


def _question_context(metadata: dict[str, Any], active_object: dict[str, Any]) -> dict[str, Any]:
    explicit = _dict(metadata.get("question_followup_context"))
    if explicit:
        return explicit
    snapshot = _dict(active_object.get("state_snapshot"))
    if snapshot:
        return snapshot
    exact = _dict(metadata.get("exact_question"))
    return exact


def _grading_result(metadata: dict[str, Any], question_context: dict[str, Any]) -> dict[str, Any]:
    explicit = _dict(metadata.get("construction_grading_result"))
    if explicit:
        return explicit
    nested = _dict(question_context.get("construction_grading_result"))
    if nested:
        return nested
    items = _list(question_context.get("items"))
    for item in items:
        result = _dict(_dict(item).get("construction_grading_result"))
        if result:
            return result
    return {}


def _grading_item(grading_result: dict[str, Any]) -> dict[str, Any]:
    items = _list(grading_result.get("items"))
    return _dict(items[0]) if items else grading_result


def _active_object_ref(active_object: dict[str, Any]) -> dict[str, Any]:
    if not active_object:
        return {}
    return {
        "object_type": str(active_object.get("object_type") or "").strip(),
        "object_id": str(active_object.get("object_id") or "").strip(),
        "version": active_object.get("version"),
        "source_turn_id": str(active_object.get("source_turn_id") or "").strip(),
    }


def _session_active_object_ref(runtime_state: dict[str, Any]) -> dict[str, Any]:
    return _active_object_ref(_dict(runtime_state.get("active_object")))


def _string_authority(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _authority_source(metadata: dict[str, Any], grading: dict[str, Any]) -> str:
    lifecycle = _dict(metadata.get("question_lifecycle_decision"))
    if _string_authority(metadata.get("question_authority_source")):
        return _string_authority(metadata.get("question_authority_source"))
    if _string_authority(grading.get("authority")):
        return _string_authority(grading.get("authority"))
    if bool(metadata.get("exact_fast_path_hit")) or _dict(metadata.get("exact_question")):
        return "exact_question"
    if bool(lifecycle.get("needs_clarification")):
        return "lifecycle_clarification"
    if _string_authority(metadata.get("execution_path")):
        return _string_authority(metadata.get("execution_path"))
    return _string_authority(lifecycle.get("decision_source"))


def _correct_answer_present(
    metadata: dict[str, Any],
    question_context: dict[str, Any],
    grading_item: dict[str, Any],
) -> bool:
    if isinstance(metadata.get("correct_answer_present"), bool):
        return bool(metadata["correct_answer_present"])
    return bool(
        str(
            _first_non_empty(
                question_context.get("correct_answer"),
                grading_item.get("correct_answer"),
            )
        ).strip()
    )


def _trace_expectation(row: dict[str, Any]) -> str:
    path = str(row.get("execution_path") or row.get("result_mode") or "").strip()
    mode = str(row.get("result_mode") or "").strip()
    if path.startswith("deep_question_") or mode in {"followup", "grading"}:
        return "active_question_followup_or_grading"
    if path == "tutorbot_lifecycle_clarification":
        return "lifecycle_clarification"
    if path.startswith("tutorbot_exact") or row.get("official_answer"):
        return "exact_question_tutorbot"
    if path.startswith("tutorbot_kb") or path.startswith("tutorbot_open"):
        return "open_world_teaching"
    return "generic_terminal_turn"


def _required_trace_fields(row: dict[str, Any]) -> tuple[str, ...]:
    expectation = _trace_expectation(row)
    if expectation == "active_question_followup_or_grading":
        return (
            "active_object_ref",
            "turn_semantic_decision",
            "result_mode",
            "question_id",
            "answer_authority_source",
        )
    if expectation == "lifecycle_clarification":
        return (
            "active_object_ref",
            "question_lifecycle_decision",
            "result_mode",
            "answer_authority_source",
        )
    if expectation == "exact_question_tutorbot":
        return (
            "active_object_ref",
            "question_lifecycle_decision",
            "result_mode",
            "question_id",
            "answer_authority_source",
        )
    if expectation == "open_world_teaching":
        return (
            "question_lifecycle_decision",
            "result_mode",
            "answer_authority_source",
        )
    return ("result_mode", "answer_authority_source")


def _missing_trace_fields(row: dict[str, Any]) -> list[str]:
    required = _required_trace_fields(row)
    return [key for key in required if not row.get(key)]


def extract_turn_authority_row(
    conn: sqlite3.Connection,
    *,
    turn_id: str,
    round_id: str = "",
    entry_surface: str = "real_wechat_package",
) -> dict[str, Any]:
    turn = _turn_row(conn, turn_id)
    if turn is None:
        raise ValueError(f"turn not found: {turn_id}")
    events = _turn_events(conn, turn_id)
    result_event = _latest_result_event(events)
    metadata = _dict(result_event.get("metadata"))
    active_object = _dict(metadata.get("active_object"))
    question_context = _question_context(metadata, active_object)
    grading = _grading_result(metadata, question_context)
    grading_item = _grading_item(grading)
    runtime_state = _session_runtime_state(conn, turn["session_id"])

    question_id = str(
        _first_non_empty(
            metadata.get("question_id"),
            question_context.get("question_id"),
            grading_item.get("question_id"),
            active_object.get("object_id"),
        )
    ).strip()
    official_answer = str(
        _first_non_empty(
            question_context.get("correct_answer"),
            grading_item.get("correct_answer"),
        )
    ).strip()
    learner_answer = str(
        _first_non_empty(
            metadata.get("user_answer"),
            question_context.get("user_answer"),
            grading_item.get("user_answer"),
        )
    ).strip()

    row = {
        "round_id": round_id or turn_id,
        "entry_surface": entry_surface,
        "conversation_id": turn["session_id"],
        "turn_id": turn_id,
        "turn_status": turn["status"] or "",
        "terminal_status": _latest_done_status(events) or turn["status"] or "",
        "capability": turn["capability"] or "",
        "event_source": result_event.get("source") or "",
        "execution_engine": str(metadata.get("execution_engine") or "").strip(),
        "execution_path": str(metadata.get("execution_path") or "").strip(),
        "result_mode": str(metadata.get("mode") or metadata.get("execution_path") or "").strip(),
        "assistant_content_source": str(metadata.get("assistant_content_source") or "").strip(),
        "answer_authority_source": _authority_source(metadata, grading_item or grading),
        "question_id": question_id,
        "question_hash": _sha256_json(question_context.get("question")),
        "options_hash": _sha256_json(question_context.get("options")),
        "learner_answer": learner_answer,
        "official_answer": official_answer,
        "correct_answer_present": _correct_answer_present(metadata, question_context, grading_item),
        "is_correct": _first_non_empty(
            metadata.get("is_correct"),
            question_context.get("is_correct"),
            grading_item.get("is_correct"),
        ),
        "active_object_ref": _active_object_ref(active_object),
        "session_active_object_ref": _session_active_object_ref(runtime_state),
        "turn_semantic_decision": _dict(metadata.get("turn_semantic_decision")),
        "question_lifecycle_decision": _dict(metadata.get("question_lifecycle_decision")),
        "active_object_question_id": str(
            _dict(active_object.get("state_snapshot")).get("question_id") or ""
        ).strip(),
        "response_excerpt": _compact_text(metadata.get("response")),
        "event_count": len(events),
        "result_seq": result_event.get("seq") or 0,
    }
    row["trace_expectation"] = _trace_expectation(row)
    row["missing_trace_fields"] = _missing_trace_fields(row)
    row["trace_complete"] = not row["missing_trace_fields"]
    return row


def _conversation_turn_ids(conn: sqlite3.Connection, conversation_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT id
        FROM turns
        WHERE session_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def _parse_turn_spec(spec: str) -> tuple[str, str]:
    if "=" in spec:
        round_id, turn_id = spec.split("=", 1)
        return round_id.strip(), turn_id.strip()
    return "", spec.strip()


def extract_authority_rows(
    db_path: Path,
    *,
    turn_specs: list[str],
    conversation_ids: list[str],
    entry_surface: str,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for conversation_id in conversation_ids:
            for turn_id in _conversation_turn_ids(conn, conversation_id):
                rows.append(
                    extract_turn_authority_row(
                        conn,
                        turn_id=turn_id,
                        round_id=turn_id,
                        entry_surface=entry_surface,
                    )
                )
        for spec in turn_specs:
            round_id, turn_id = _parse_turn_spec(spec)
            rows.append(
                extract_turn_authority_row(
                    conn,
                    turn_id=turn_id,
                    round_id=round_id,
                    entry_surface=entry_surface,
                )
            )
    return rows


def _write_jsonl(rows: list[dict[str, Any]], output: Path | None) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    payload = "\n".join(lines) + ("\n" if lines else "")
    if output is None:
        sys.stdout.write(payload)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract compact internal authority ledger rows for WeChat TutorBot QA.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite chat_history.db path.")
    parser.add_argument(
        "--turn",
        action="append",
        default=[],
        help="Turn id, or ROUND_ID=turn_id. Can be repeated.",
    )
    parser.add_argument(
        "--conversation-id",
        action="append",
        default=[],
        help="Conversation/session id. All turns in the conversation are exported.",
    )
    parser.add_argument(
        "--entry-surface",
        default="real_wechat_package",
        help="Ledger entry surface label.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write JSONL to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.turn and not args.conversation_id:
        raise SystemExit("provide at least one --turn or --conversation-id")
    rows = extract_authority_rows(
        args.db,
        turn_specs=list(args.turn),
        conversation_ids=list(args.conversation_id),
        entry_surface=str(args.entry_surface or "real_wechat_package"),
    )
    _write_jsonl(rows, args.output)
    complete = sum(1 for row in rows if row.get("trace_complete"))
    print(
        f"authority ledger rows={len(rows)} trace_complete={complete} output={args.output or 'stdout'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
