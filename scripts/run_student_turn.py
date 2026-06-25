#!/usr/bin/env python3
"""Single-turn WeChat-shaped TutorBot primitive for adaptive student-army QA.

This is a thin CLI around the same mobile start-turn + unified WS contract the
WeChat mini-program uses (`/api/v1/chat/start-turn` + `/api/v1/ws`). It exists so
an adaptive "student" agent can: log in once, open a conversation, then send one
message at a time, read the bot's reply, and decide the next message in-character.

It records nothing to the repo and invents no answer authority; it only relays the
runtime's visible response plus objective stability/latency signals.

Credentials come from env (never the CLI args, so they never land in a prompt or
process list): DEEPTUTOR_QA_USERNAME / DEEPTUTOR_QA_PASSWORD. Base URL defaults to
test2 and can be overridden with DEEPTUTOR_QA_BASE_URL or --api-base-url.

Modes:
  login            -> prints {"token": ..., "user_id": ...}
  new              -> needs --token; prints {"conversation_id": ...}
  turn             -> needs --token --conversation-id --query;
                      prints one JSON object with the visible reply + signals
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

import httpx
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.internal_qa import (  # noqa: E402
    EVAL_BILLING_BYPASS_HEADER,
    make_eval_billing_bypass_token,
)
from scripts.run_mobile_login_smoke import (  # noqa: E402
    _build_ws_url,
    _register_or_login,
    _request_json,
)

DEFAULT_BASE_URL = os.getenv("DEEPTUTOR_QA_BASE_URL", "https://test2.yousenjiaoyu.com")
TERMINAL_TURN_STATUSES = {"completed", "failed", "cancelled"}


def _eval_bypass_headers() -> dict[str, str]:
    """Add the eval-mode billing-bypass header iff a local key is configured.

    The key never travels: only a fresh HMAC over the current timestamp is sent.
    With no key set this is a no-op and turns are charged normally.
    """

    secret = os.getenv("DEEPTUTOR_EVAL_BYPASS_KEY", "").strip()
    if not secret:
        # Local-file fallback so an eval driver (and Workflow student agents) can
        # sign turns without ever handling the key in env/args/prompts.
        key_file = os.getenv(
            "DEEPTUTOR_EVAL_KEY_FILE", os.path.expanduser("~/.deeptutor_eval_key")
        )
        try:
            with open(key_file, encoding="utf-8") as handle:
                secret = handle.read().strip()
        except OSError:
            secret = ""
    if len(secret) < 32:
        return {}
    token = make_eval_billing_bypass_token(secret, ts=int(time.time()))
    return {EVAL_BILLING_BYPASS_HEADER: token}


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _extract_response(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in ("response", "assistant_content", "content"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        nested_response = _extract_response(nested)
        if nested_response:
            return nested_response
    return ""


def _append_jsonl(path: str | os.PathLike[str], payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _db_not_requested() -> dict[str, Any]:
    return {"checked": False, "status": "not_requested"}


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _message_matches_turn(
    message: dict[str, Any],
    *,
    turn_id: str,
    client_turn_id: str,
) -> bool:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    ids = {
        str(metadata.get("turn_id") or "").strip(),
        str(metadata.get("engine_turn_id") or "").strip(),
    }
    if turn_id and turn_id in ids:
        return True
    return bool(client_turn_id and str(metadata.get("client_turn_id") or "").strip() == client_turn_id)


def _reconcile_db_truth(
    *,
    db_path: str | os.PathLike[str],
    turn_id: str = "",
    conversation_id: str = "",
    client_turn_id: str = "",
) -> dict[str, Any]:
    """Read local SQLite turn truth without mutating runtime state.

    This intentionally mirrors the contract shape instead of importing runtime
    managers: the harness is an evidence reader, not a second turn authority.
    """

    resolved_path = Path(db_path).expanduser()
    result: dict[str, Any] = {
        "checked": True,
        "matched": False,
        "status": "not_found",
        "db_path": str(resolved_path),
        "turn": None,
        "terminal_event": None,
        "assistant_message": None,
        "conversation_sessions": [],
        "messages": [],
    }
    if not resolved_path.exists():
        result["status"] = "db_missing"
        return result

    uri = f"file:{resolved_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row

        turn: dict[str, Any] | None = None
        if turn_id:
            turn = _row_dict(
                conn.execute(
                    """
                    SELECT id, session_id, capability, status, error, created_at, updated_at, finished_at
                    FROM turns
                    WHERE id = ?
                    """,
                    (turn_id,),
                ).fetchone()
            )
        if turn is None and conversation_id:
            turn = _row_dict(
                conn.execute(
                    """
                    SELECT t.id, t.session_id, t.capability, t.status, t.error,
                           t.created_at, t.updated_at, t.finished_at
                    FROM turns t
                    INNER JOIN sessions s ON s.id = t.session_id
                    WHERE s.id = ? OR s.conversation_id = ?
                    ORDER BY t.updated_at DESC
                    LIMIT 1
                    """,
                    (conversation_id, conversation_id),
                ).fetchone()
            )
        if turn is not None and not turn_id:
            turn_id = str(turn.get("id") or "").strip()

        session_rows: list[sqlite3.Row] = []
        seen_session_ids: set[str] = set()
        if conversation_id:
            session_rows.extend(
                conn.execute(
                    """
                    SELECT id, title, source, conversation_id, created_at, updated_at
                    FROM sessions
                    WHERE id = ? OR conversation_id = ?
                    ORDER BY updated_at DESC, id DESC
                    """,
                    (conversation_id, conversation_id),
                ).fetchall()
            )
        turn_session_id = str((turn or {}).get("session_id") or "").strip()
        if turn_session_id:
            session_rows.extend(
                conn.execute(
                    """
                    SELECT id, title, source, conversation_id, created_at, updated_at
                    FROM sessions
                    WHERE id = ?
                    """,
                    (turn_session_id,),
                ).fetchall()
            )

        sessions: list[dict[str, Any]] = []
        for row in session_rows:
            session = _row_dict(row) or {}
            session_id = str(session.get("id") or "").strip()
            if not session_id or session_id in seen_session_ids:
                continue
            seen_session_ids.add(session_id)
            sessions.append(session)
        result["conversation_sessions"] = sessions

        events: list[dict[str, Any]] = []
        if turn_id:
            event_rows = conn.execute(
                """
                SELECT seq, type, source, stage, content, metadata_json, timestamp, created_at
                FROM turn_events
                WHERE turn_id = ?
                ORDER BY seq ASC
                """,
                (turn_id,),
            ).fetchall()
            for row in event_rows:
                metadata = _json_loads(row["metadata_json"], {})
                events.append(
                    {
                        "seq": row["seq"],
                        "type": row["type"] or "",
                        "source": row["source"] or "",
                        "stage": row["stage"] or "",
                        "content": row["content"] or "",
                        "metadata": metadata,
                        "response": _extract_response(metadata),
                        "timestamp": row["timestamp"],
                    }
                )
        result["turn_events"] = events
        terminal_event = next(
            (event for event in reversed(events) if event.get("type") == "result"),
            None,
        ) or next(
            (
                event
                for event in reversed(events)
                if str(event.get("type") or "") in {"error", "done"}
            ),
            None,
        )
        result["terminal_event"] = terminal_event

        session_ids = [str(session.get("id") or "") for session in sessions]
        messages: list[dict[str, Any]] = []
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            message_rows = conn.execute(
                f"""
                SELECT id, session_id, role, content, capability, metadata_json, created_at
                FROM messages
                WHERE session_id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                tuple(session_ids),
            ).fetchall()
            for row in message_rows:
                message = _row_dict(row) or {}
                message["metadata"] = _json_loads(str(message.pop("metadata_json") or ""), {})
                messages.append(message)
        result["messages"] = messages

    assistant_message = next(
        (
            message
            for message in reversed(messages)
            if str(message.get("role") or "") == "assistant"
            and _message_matches_turn(message, turn_id=turn_id, client_turn_id=client_turn_id)
        ),
        None,
    ) or next(
        (
            message
            for message in reversed(messages)
            if str(message.get("role") or "") == "assistant"
            and str(message.get("session_id") or "") == str((turn or {}).get("session_id") or "")
        ),
        None,
    )
    result["assistant_message"] = assistant_message
    result["turn"] = turn
    if turn is None:
        result["status"] = "turn_not_found"
        return result
    result["matched"] = True
    result["status"] = str(turn.get("status") or "unknown")
    return result


def _status_from_ws(done_status: str, ws_error: str, visible: str) -> str:
    if ws_error == "ws_timeout":
        return "ws_timeout"
    if ws_error.startswith("ws_exception:"):
        return "ws_exception"
    if done_status:
        return done_status
    if visible:
        return "completed"
    return "unknown"


def _finalize_turn_output(
    *,
    conversation_id: str,
    turn_id: str,
    client_turn_id: str,
    visible_response: str,
    done_status: str,
    event_types: list[str],
    ttft_ms: float | None,
    latency_ms: float,
    ws_error: str,
    http_status: int,
    detail: Any = None,
    db_reconciled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_reconciled = db_reconciled or _db_not_requested()
    db_turn = db_reconciled.get("turn") if isinstance(db_reconciled.get("turn"), dict) else {}
    db_terminal = (
        db_reconciled.get("terminal_event")
        if isinstance(db_reconciled.get("terminal_event"), dict)
        else {}
    )
    db_message = (
        db_reconciled.get("assistant_message")
        if isinstance(db_reconciled.get("assistant_message"), dict)
        else {}
    )
    db_status = str(db_turn.get("status") or "").strip()
    if db_status in TERMINAL_TURN_STATUSES:
        status = db_status
    else:
        status = _status_from_ws(done_status, ws_error, visible_response)

    db_visible = str(db_terminal.get("response") or db_message.get("content") or "").strip()
    visible = visible_response.strip() or db_visible
    ok = status == "completed" and bool(visible)
    output = {
        "ok": ok,
        "status": status,
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "client_turn_id": client_turn_id,
        "visible_response": visible,
        "done_status": done_status,
        "event_types": event_types,
        "event_count": len(event_types),
        "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
        "latency_ms": round(latency_ms, 1),
        "latency": {
            "total_ms": round(latency_ms, 1),
            "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
        },
        "http_status": http_status,
        "ws_error": ws_error,
        "error": ws_error,
        "db_reconciled": db_reconciled,
    }
    if detail is not None:
        output["detail"] = detail
    return output


async def _login(base_url: str, timeout: float) -> dict[str, Any]:
    username = os.getenv("DEEPTUTOR_QA_USERNAME", "").strip()
    password = os.getenv("DEEPTUTOR_QA_PASSWORD", "").strip()
    if not username or not password:
        raise SystemExit("DEEPTUTOR_QA_USERNAME / DEEPTUTOR_QA_PASSWORD must be set")
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
        auth_payload, _ = await _register_or_login(
            client, username=username, password=password, phone="", register=False
        )
        token = str(auth_payload.get("token") or "").strip()
        if not token:
            raise SystemExit(f"auth_missing_token:{auth_payload}")
        return {"token": token, "user_id": str(auth_payload.get("user_id") or "")}


async def _new_conversation(base_url: str, token: str, timeout: float) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
        status, payload = await _request_json(
            client, "POST", "/api/v1/conversations", headers=headers
        )
        if status != 200:
            raise SystemExit(f"create_conversation_failed:{status}:{payload}")
        conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
        conversation_id = str(conversation.get("id") or "").strip()
        if not conversation_id:
            raise SystemExit(f"conversation_missing_id:{payload}")
        return {"conversation_id": conversation_id}


async def _turn(
    base_url: str,
    token: str,
    conversation_id: str,
    query: str,
    timeout: float,
    *,
    client_turn_id: str = "",
    db_path: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", **_eval_bypass_headers()}
    ws_url = _build_ws_url(base_url)
    start_wall = time.monotonic()
    started = error = ""
    turn_id = ""
    client_turn_id = client_turn_id.strip() or f"studentarmy_{int(time.time() * 1000)}"
    fragments: list[str] = []
    fallback = ""
    event_types: list[str] = []
    done_status = ""
    ttft_ms: float | None = None
    http_status = 0

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
        payload = {
            "query": query,
            "conversation_id": conversation_id,
            "mode": "AUTO",
            "language": "zh",
            "client_turn_id": client_turn_id,
            "config": {"bot_id": "construction-exam-coach"},
            "interaction_profile": "tutorbot",
            "interaction_hints": {
                "product_surface": "wechat_miniprogram",
                "entry_role": "tutorbot",
                "subject_domain": "construction_exam",
                "requested_response_mode": "smart",
            },
        }
        http_status, response = await _request_json(
            client, "POST", "/api/v1/chat/start-turn", headers=headers, json_body=payload
        )
        if http_status != 200:
            latency_ms = (time.monotonic() - start_wall) * 1000.0
            return _finalize_turn_output(
                conversation_id=conversation_id,
                turn_id="",
                client_turn_id=client_turn_id,
                visible_response="",
                done_status="start_turn_failed",
                event_types=[],
                ttft_ms=None,
                latency_ms=latency_ms,
                ws_error=f"start_turn_failed:{http_status}",
                http_status=http_status,
                detail=response,
            )
        conversation = response.get("conversation") if isinstance(response.get("conversation"), dict) else {}
        stream = response.get("stream") if isinstance(response.get("stream"), dict) else {}
        subscribe = stream.get("subscribe") if isinstance(stream.get("subscribe"), dict) else {}
        started = str(conversation.get("id") or conversation_id).strip() or conversation_id
        turn_id = str((response.get("turn") or {}).get("id") or subscribe.get("turn_id") or "").strip()
        if not turn_id:
            latency_ms = (time.monotonic() - start_wall) * 1000.0
            return _finalize_turn_output(
                conversation_id=started,
                turn_id="",
                client_turn_id=client_turn_id,
                visible_response="",
                done_status="missing_turn_id",
                event_types=[],
                ttft_ms=None,
                latency_ms=latency_ms,
                ws_error="missing_turn_id",
                http_status=http_status,
                detail=response,
            )
        subscribe_payload = dict(subscribe) if subscribe else {
            "type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0
        }

    ws_headers = {"Authorization": f"Bearer {token}"}
    try:
        async with websockets.connect(ws_url, additional_headers=ws_headers) as ws:
            await ws.send(json.dumps(subscribe_payload, ensure_ascii=False))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                event = json.loads(raw)
                etype = str(event.get("type") or "")
                event_types.append(etype)
                if etype == "content" and event.get("content"):
                    if ttft_ms is None:
                        ttft_ms = (time.monotonic() - start_wall) * 1000.0
                    fragments.append(str(event["content"]))
                elif etype == "result":
                    md = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                    fallback = _extract_response(md) or fallback
                elif etype == "error":
                    error = str(event.get("content") or "ws_turn_failed")
                    done_status = "error"
                    break
                elif etype == "done":
                    done_status = str((event.get("metadata") or {}).get("status") or "")
                    break
    except asyncio.TimeoutError:
        error = "ws_timeout"
        done_status = "timeout"
    except Exception as exc:  # noqa: BLE001 - surface any transport error as a signal
        error = f"ws_exception:{type(exc).__name__}:{exc}"
        done_status = "ws_exception"

    latency_ms = (time.monotonic() - start_wall) * 1000.0
    visible = "".join(fragments).strip() or fallback.strip()
    db_reconciled = _db_not_requested()
    if db_path:
        db_reconciled = _reconcile_db_truth(
            db_path=db_path,
            turn_id=turn_id,
            conversation_id=started or conversation_id,
            client_turn_id=client_turn_id,
        )
    return _finalize_turn_output(
        conversation_id=started or conversation_id,
        turn_id=turn_id,
        client_turn_id=client_turn_id,
        visible_response=visible,
        done_status=done_status,
        event_types=event_types,
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        ws_error=error,
        http_status=http_status,
        db_reconciled=db_reconciled,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-turn student-army TutorBot primitive")
    parser.add_argument("mode", choices=["login", "new", "turn", "db-reconcile"])
    parser.add_argument("--api-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default="")
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--turn-id", default="")
    parser.add_argument("--client-turn-id", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--query-file", default="", help="read query text from a file (avoids shell quoting)")
    parser.add_argument("--db-path", default="", help="read-only SQLite chat_history.db path for DB truth reconciliation")
    parser.add_argument("--output-jsonl", default="", help="append the emitted JSON object to this JSONL file")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args(argv)

    base_url = str(args.api_base_url).rstrip("/")
    if args.query_file:
        with open(args.query_file, encoding="utf-8") as handle:
            args.query = handle.read().strip()
    if args.mode == "login":
        out = asyncio.run(_login(base_url, args.timeout_seconds))
    elif args.mode == "new":
        if not args.token:
            raise SystemExit("--token required for new")
        out = asyncio.run(_new_conversation(base_url, args.token, args.timeout_seconds))
    elif args.mode == "db-reconcile":
        if not args.db_path:
            raise SystemExit("--db-path required for db-reconcile")
        if not args.turn_id and not args.conversation_id:
            raise SystemExit("--turn-id or --conversation-id required for db-reconcile")
        out = _reconcile_db_truth(
            db_path=args.db_path,
            turn_id=args.turn_id,
            conversation_id=args.conversation_id,
            client_turn_id=args.client_turn_id,
        )
    else:
        if not args.token or not args.conversation_id or not args.query:
            raise SystemExit("--token, --conversation-id, --query required for turn")
        out = asyncio.run(
            _turn(
                base_url,
                args.token,
                args.conversation_id,
                args.query,
                args.timeout_seconds,
                client_turn_id=args.client_turn_id,
                db_path=args.db_path,
            )
        )
    if args.output_jsonl:
        _append_jsonl(args.output_jsonl, out)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
