#!/usr/bin/env python3
"""Reusable N-turn same-conversation driver for Battle2 paired baseline.

Registers a fresh eval-runner user, opens one conversation, then sends a list of
messages SERIALLY in that same conversation (waiting for each turn's terminal
`done`/`error` before the next). Every start-turn request carries the eval
billing-bypass header (X-Eval-Bypass) so turns never bill / never create real
member activity.

Records per-turn local wall-clock start/end (UTC), passed flag, conversation id,
turn id, turn index. Never deletes the conversation.

Run from within the release worktree so imports resolve, e.g.:
  cd <worktree> && PYTHONPATH=. python3 <scratch>/session_driver.py ...
This file is imported by run_arm.py; it is not committed to the repo.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from scripts.run_mobile_login_smoke import (
    _build_ws_url,
    _register_or_login,
    _request_json,
    _run_ws_turn,
)
from scripts.run_student_turn import _eval_bypass_headers


def _utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def _start_turn_with_bypass(
    client: httpx.AsyncClient,
    *,
    auth_headers: dict[str, str],
    conversation_id: str,
    message: str,
) -> tuple[str, str, dict[str, Any]]:
    headers = {**auth_headers, **_eval_bypass_headers()}
    status_code, payload = await _request_json(
        client,
        "POST",
        "/api/v1/chat/start-turn",
        headers=headers,
        json_body={
            "query": message,
            "conversation_id": conversation_id,
            "mode": "AUTO",
            "language": "zh",
            "interaction_profile": "tutorbot",
        },
    )
    if status_code != 200:
        raise RuntimeError(f"start_turn_failed:{status_code}:{payload}")
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    stream = payload.get("stream") if isinstance(payload.get("stream"), dict) else {}
    subscribe = stream.get("subscribe") if isinstance(stream.get("subscribe"), dict) else {}
    started_cid = str(conversation.get("id") or conversation_id).strip() or conversation_id
    turn_id = str((payload.get("turn") or {}).get("id") or subscribe.get("turn_id") or "").strip()
    if not turn_id:
        raise RuntimeError(f"start_turn_missing_turn_id:{payload}")
    subscribe_payload = dict(subscribe) if subscribe else {
        "type": "subscribe_turn",
        "turn_id": turn_id,
        "after_seq": 0,
    }
    return started_cid, turn_id, subscribe_payload


async def _run_one_turn(
    client: httpx.AsyncClient,
    *,
    ws_url: str,
    token: str,
    auth_headers: dict[str, str],
    conversation_id: str,
    message: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """One start-turn + WS turn, with a single retry on failure."""
    last_error = ""
    for attempt in (1, 2):
        start_wall = time.time()
        try:
            cid, turn_id, subscribe_payload = await _start_turn_with_bypass(
                client,
                auth_headers=auth_headers,
                conversation_id=conversation_id,
                message=message,
            )
            result = await _run_ws_turn(
                ws_url=ws_url,
                token=token,
                session_id=cid,
                turn_id=turn_id,
                subscribe_payload=subscribe_payload,
                timeout_seconds=timeout_seconds,
            )
            end_wall = time.time()
            return {
                "attempt": attempt,
                "conversation_id": cid,
                "turn_id": result.turn_id,
                "message": message,
                "start_utc": _utc_iso(start_wall),
                "end_utc": _utc_iso(end_wall),
                "wall_ms": round((end_wall - start_wall) * 1000.0, 1),
                "done": result.done,
                "done_status": result.done_status,
                "passed": bool(result.done),
                "response_len": len(result.assistant_response or ""),
                "response_head": (result.assistant_response or "")[:120],
                "event_types": result.event_types,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - record and retry/continue
            end_wall = time.time()
            last_error = f"{type(exc).__name__}:{exc}"[:400]
            if attempt == 2:
                return {
                    "attempt": attempt,
                    "conversation_id": conversation_id,
                    "turn_id": "",
                    "message": message,
                    "start_utc": _utc_iso(start_wall),
                    "end_utc": _utc_iso(end_wall),
                    "wall_ms": round((end_wall - start_wall) * 1000.0, 1),
                    "done": False,
                    "done_status": "failed",
                    "passed": False,
                    "response_len": 0,
                    "response_head": "",
                    "event_types": [],
                    "error": last_error,
                }
            # brief pause before retry
            await asyncio.sleep(2.0)
    # unreachable
    return {"passed": False, "error": last_error}


async def register_user_with_backoff(
    *,
    api_base_url: str,
    username: str,
    password: str,
    phone: str,
    timeout_seconds: float = 60.0,
    max_attempts: int = 6,
) -> bool:
    """Register a fresh eval user, backing off on HTTP 429 (register limit=3/60s)."""
    base = api_base_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=timeout_seconds, trust_env=False) as client:
        delay = 22.0
        for attempt in range(1, max_attempts + 1):
            try:
                _, created = await _register_or_login(
                    client, username=username, password=password, phone=phone, register=True
                )
                return created
            except RuntimeError as exc:
                if "register_failed:429" in str(exc) and attempt < max_attempts:
                    await asyncio.sleep(delay)
                    delay = min(delay * 1.5, 65.0)
                    continue
                raise


async def run_session(
    *,
    api_base_url: str,
    username: str,
    password: str,
    phone: str,
    messages: list[str],
    label: str,
    register: bool = False,
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    base = api_base_url.rstrip("/")
    ws_url = _build_ws_url(base)
    session_start = time.time()
    turns: list[dict[str, Any]] = []
    conversation_id = ""
    created_user = False
    error = ""

    async with httpx.AsyncClient(base_url=base, timeout=timeout_seconds, trust_env=False) as client:
        # login with a small retry on transient 429 (login limit=10/60s)
        auth_payload = None
        for login_attempt in range(1, 5):
            try:
                auth_payload, created_user = await _register_or_login(
                    client,
                    username=username,
                    password=password,
                    phone=phone,
                    register=register,
                )
                break
            except RuntimeError as exc:
                if ("429" in str(exc)) and login_attempt < 4:
                    await asyncio.sleep(15.0)
                    continue
                raise
        token = str(auth_payload.get("token") or "").strip()
        if not token:
            raise RuntimeError(f"auth_missing_token:{auth_payload}")
        auth_headers = {"Authorization": f"Bearer {token}"}

        status_code, conversation_payload = await _request_json(
            client, "POST", "/api/v1/conversations", headers=auth_headers
        )
        if status_code != 200:
            raise RuntimeError(f"create_conversation_failed:{status_code}:{conversation_payload}")
        conversation_id = str((conversation_payload.get("conversation") or {}).get("id") or "").strip()
        if not conversation_id:
            raise RuntimeError(f"conversation_missing_id:{conversation_payload}")

        for idx, message in enumerate(messages, start=1):
            turn = await _run_one_turn(
                client,
                ws_url=ws_url,
                token=token,
                auth_headers=auth_headers,
                conversation_id=conversation_id,
                message=message,
                timeout_seconds=timeout_seconds,
            )
            turn["turn_index"] = idx
            turn["session_label"] = label
            conversation_id = turn.get("conversation_id") or conversation_id
            turns.append(turn)

    session_end = time.time()
    passed_turns = sum(1 for t in turns if t.get("passed"))
    return {
        "label": label,
        "username": username,
        "created_user": created_user,
        "conversation_id": conversation_id,
        "session_start_utc": _utc_iso(session_start),
        "session_end_utc": _utc_iso(session_end),
        "session_wall_ms": round((session_end - session_start) * 1000.0, 1),
        "turn_count": len(turns),
        "passed_turns": passed_turns,
        "turns": turns,
        "error": error,
    }
