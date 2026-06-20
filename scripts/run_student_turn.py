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
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_mobile_login_smoke import (  # noqa: E402
    _build_ws_url,
    _register_or_login,
    _request_json,
)
from deeptutor.services.internal_qa import (  # noqa: E402
    EVAL_BILLING_BYPASS_HEADER,
    make_eval_billing_bypass_token,
)

DEFAULT_BASE_URL = os.getenv("DEEPTUTOR_QA_BASE_URL", "https://test2.yousenjiaoyu.com")


def _eval_bypass_headers() -> dict[str, str]:
    """Add the eval-mode billing-bypass header iff a local key is configured.

    The key never travels: only a fresh HMAC over the current timestamp is sent.
    With no key set this is a no-op and turns are charged normally.
    """

    secret = os.getenv("DEEPTUTOR_EVAL_BYPASS_KEY", "").strip()
    if len(secret) < 32:
        return {}
    token = make_eval_billing_bypass_token(secret, ts=int(time.time()))
    return {EVAL_BILLING_BYPASS_HEADER: token}


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
    base_url: str, token: str, conversation_id: str, query: str, timeout: float
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", **_eval_bypass_headers()}
    ws_url = _build_ws_url(base_url)
    start_wall = time.monotonic()
    started = error = ""
    turn_id = ""
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
            "client_turn_id": f"studentarmy_{int(time.time() * 1000)}",
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
            return {
                "ok": False,
                "error": f"start_turn_failed:{http_status}",
                "http_status": http_status,
                "detail": response,
                "conversation_id": conversation_id,
            }
        conversation = response.get("conversation") if isinstance(response.get("conversation"), dict) else {}
        stream = response.get("stream") if isinstance(response.get("stream"), dict) else {}
        subscribe = stream.get("subscribe") if isinstance(stream.get("subscribe"), dict) else {}
        started = str(conversation.get("id") or conversation_id).strip() or conversation_id
        turn_id = str((response.get("turn") or {}).get("id") or subscribe.get("turn_id") or "").strip()
        if not turn_id:
            return {"ok": False, "error": "missing_turn_id", "detail": response, "conversation_id": started}
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
                    fallback = str(md.get("response") or (md.get("metadata") or {}).get("response") or fallback)
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
    return {
        "ok": bool(visible) and not error,
        "conversation_id": started or conversation_id,
        "turn_id": turn_id,
        "visible_response": visible,
        "done_status": done_status,
        "event_types": event_types,
        "event_count": len(event_types),
        "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
        "latency_ms": round(latency_ms, 1),
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-turn student-army TutorBot primitive")
    parser.add_argument("mode", choices=["login", "new", "turn"])
    parser.add_argument("--api-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default="")
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args(argv)

    base_url = str(args.api_base_url).rstrip("/")
    if args.mode == "login":
        out = asyncio.run(_login(base_url, args.timeout_seconds))
    elif args.mode == "new":
        if not args.token:
            raise SystemExit("--token required for new")
        out = asyncio.run(_new_conversation(base_url, args.token, args.timeout_seconds))
    else:
        if not args.token or not args.conversation_id or not args.query:
            raise SystemExit("--token, --conversation-id, --query required for turn")
        out = asyncio.run(
            _turn(base_url, args.token, args.conversation_id, args.query, args.timeout_seconds)
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
