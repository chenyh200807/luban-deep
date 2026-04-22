#!/usr/bin/env python3
"""Run a real mobile auth -> conversation -> unified WS continuity smoke."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _generated_credentials(prefix: str = "prelaunchsmoke") -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}_{stamp}"
    password = f"SmokeA{stamp % 1000000:06d}"
    phone = f"139{stamp % 100000000:08d}"
    return username, password, phone


@dataclass(slots=True)
class TurnSmokeResult:
    session_id: str
    turn_id: str
    assistant_response: str
    event_types: list[str]
    done: bool
    done_status: str


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    response = await client.request(
        method,
        path,
        headers=headers,
        json=json_body,
    )
    payload: dict[str, Any]
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": response.text}
    return response.status_code, payload


async def _register_or_login(
    client: httpx.AsyncClient,
    *,
    username: str,
    password: str,
    phone: str,
    register: bool,
) -> tuple[dict[str, Any], bool]:
    if register:
        status_code, payload = await _request_json(
            client,
            "POST",
            "/api/v1/auth/register",
            json_body={"username": username, "password": password, "phone": phone},
        )
        if status_code == 200:
            return payload, True
        if status_code != 400:
            raise RuntimeError(f"register_failed:{status_code}:{payload}")

    status_code, payload = await _request_json(
        client,
        "POST",
        "/api/v1/auth/login",
        json_body={"username": username, "password": password},
    )
    if status_code != 200:
        raise RuntimeError(f"login_failed:{status_code}:{payload}")
    return payload, False


async def _run_ws_turn(
    *,
    ws_url: str,
    token: str,
    session_id: str,
    turn_id: str,
    subscribe_payload: dict[str, Any],
    timeout_seconds: float,
    connector_factory: Callable[..., Any] | None = None,
) -> TurnSmokeResult:
    connect = connector_factory or websockets.connect
    headers = {"Authorization": f"Bearer {token}"}
    fragments: list[str] = []
    fallback_response = ""
    event_types: list[str] = []
    resolved_session_id = session_id
    resolved_turn_id = turn_id
    terminal_type = ""
    terminal_status = ""

    async with connect(ws_url, additional_headers=headers) as websocket:
        await websocket.send(json.dumps(subscribe_payload, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            event_type = str(event.get("type") or "")
            event_types.append(event_type)
            if event_type == "session":
                resolved_session_id = str(event.get("session_id") or resolved_session_id)
                resolved_turn_id = str(event.get("turn_id") or resolved_turn_id)
            elif event_type == "content" and event.get("content"):
                fragments.append(str(event["content"]))
            elif event_type == "result":
                metadata = event.get("metadata") or {}
                resolved_turn_id = str(event.get("turn_id") or resolved_turn_id)
                fallback_response = str(
                    metadata.get("response")
                    or (metadata.get("metadata") or {}).get("response")
                    or fallback_response
                )
            elif event_type == "error":
                terminal_type = event_type
                terminal_status = str((event.get("metadata") or {}).get("status") or "")
                raise RuntimeError(str(event.get("content") or "ws_turn_failed"))
            elif event_type == "done":
                terminal_type = event_type
                terminal_status = str((event.get("metadata") or {}).get("status") or "")
                break

    response = "".join(fragments).strip() or fallback_response.strip()
    return TurnSmokeResult(
        session_id=resolved_session_id,
        turn_id=resolved_turn_id,
        assistant_response=response,
        event_types=event_types,
        done=terminal_type == "done",
        done_status=terminal_status,
    )


async def _start_mobile_turn(
    client: httpx.AsyncClient,
    *,
    auth_headers: dict[str, str],
    conversation_id: str,
    message: str,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    status_code, payload = await _request_json(
        client,
        "POST",
        "/api/v1/chat/start-turn",
        headers=auth_headers,
        json_body={
            "query": message,
            "conversation_id": conversation_id,
            "mode": "AUTO",
            "language": "zh",
            "interaction_profile": "tutorbot",
        },
    )
    if status_code != 200:
        raise RuntimeError(f"mobile_start_turn_failed:{status_code}:{payload}")
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    stream = payload.get("stream") if isinstance(payload.get("stream"), dict) else {}
    subscribe = stream.get("subscribe") if isinstance(stream.get("subscribe"), dict) else {}
    started_conversation_id = str(conversation.get("id") or conversation_id).strip() or conversation_id
    turn_id = str((payload.get("turn") or {}).get("id") or subscribe.get("turn_id") or "").strip()
    if not turn_id:
        raise RuntimeError(f"mobile_start_turn_missing_turn_id:{payload}")
    if str(stream.get("transport") or "").strip() != "websocket":
        raise RuntimeError(f"mobile_start_turn_invalid_transport:{payload}")
    subscribe_payload = dict(subscribe) if subscribe else {"type": "subscribe_turn", "turn_id": turn_id, "after_seq": 0}
    if str(subscribe_payload.get("type") or "").strip() != "subscribe_turn":
        raise RuntimeError(f"mobile_start_turn_invalid_subscribe_payload:{payload}")
    return started_conversation_id, turn_id, subscribe_payload, payload


async def run_mobile_login_smoke(
    *,
    api_base_url: str,
    username: str,
    password: str,
    phone: str,
    register: bool = False,
    first_message: str = "请用两句话介绍流水施工。",
    second_message: str = "继续上一题，用一句话概括你刚才回答的重点。",
    timeout_seconds: float = 60.0,
    cleanup_conversation: bool = True,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
    connector_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    normalized_base_url = api_base_url.rstrip("/")
    ws_url = _build_ws_url(normalized_base_url)
    created_user = False
    conversation_deleted = False
    conversation_id = ""
    auth_user_id = ""
    profile_payload: dict[str, Any] = {}
    first_turn_result: TurnSmokeResult | None = None
    second_turn_result: TurnSmokeResult | None = None
    messages_after_first: list[dict[str, Any]] = []
    messages_after_second: list[dict[str, Any]] = []

    client_builder = client_factory or httpx.AsyncClient
    async with client_builder(base_url=normalized_base_url, timeout=timeout_seconds, trust_env=False) as client:
        auth_payload, created_user = await _register_or_login(
            client,
            username=username,
            password=password,
            phone=phone,
            register=register,
        )
        token = str(auth_payload.get("token") or "").strip()
        if not token:
            raise RuntimeError(f"auth_missing_token:{auth_payload}")
        auth_user_id = str(auth_payload.get("user_id") or "").strip()
        auth_headers = {"Authorization": f"Bearer {token}"}

        status_code, profile_payload = await _request_json(
            client,
            "GET",
            "/api/v1/auth/profile",
            headers=auth_headers,
        )
        if status_code != 200:
            raise RuntimeError(f"profile_failed:{status_code}:{profile_payload}")

        status_code, conversation_payload = await _request_json(
            client,
            "POST",
            "/api/v1/conversations",
            headers=auth_headers,
        )
        if status_code != 200:
            raise RuntimeError(f"create_conversation_failed:{status_code}:{conversation_payload}")
        conversation = conversation_payload.get("conversation") or {}
        conversation_id = str(conversation.get("id") or "").strip()
        if not conversation_id:
            raise RuntimeError(f"conversation_missing_id:{conversation_payload}")

        first_started_conversation_id, first_turn_id, first_subscribe_payload, _ = await _start_mobile_turn(
            client,
            auth_headers=auth_headers,
            conversation_id=conversation_id,
            message=first_message,
        )
        conversation_id = first_started_conversation_id
        first_turn_result = await _run_ws_turn(
            ws_url=ws_url,
            token=token,
            session_id=conversation_id,
            turn_id=first_turn_id,
            subscribe_payload=first_subscribe_payload,
            timeout_seconds=timeout_seconds,
            connector_factory=connector_factory,
        )

        status_code, messages_payload = await _request_json(
            client,
            "GET",
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=auth_headers,
        )
        if status_code != 200:
            raise RuntimeError(f"messages_after_first_failed:{status_code}:{messages_payload}")
        messages_after_first = list(messages_payload.get("messages") or [])

        second_started_conversation_id, second_turn_id, second_subscribe_payload, _ = await _start_mobile_turn(
            client,
            auth_headers=auth_headers,
            conversation_id=conversation_id,
            message=second_message,
        )
        conversation_id = second_started_conversation_id
        second_turn_result = await _run_ws_turn(
            ws_url=ws_url,
            token=token,
            session_id=conversation_id,
            turn_id=second_turn_id,
            subscribe_payload=second_subscribe_payload,
            timeout_seconds=timeout_seconds,
            connector_factory=connector_factory,
        )

        status_code, messages_payload = await _request_json(
            client,
            "GET",
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=auth_headers,
        )
        if status_code != 200:
            raise RuntimeError(f"messages_after_second_failed:{status_code}:{messages_payload}")
        messages_after_second = list(messages_payload.get("messages") or [])

        if cleanup_conversation:
            status_code, delete_payload = await _request_json(
                client,
                "DELETE",
                f"/api/v1/conversations/{conversation_id}",
                headers=auth_headers,
            )
            if status_code != 200:
                raise RuntimeError(f"delete_conversation_failed:{status_code}:{delete_payload}")
            conversation_deleted = bool(delete_payload.get("deleted"))

    first_message_count = len(messages_after_first)
    second_message_count = len(messages_after_second)
    passed = (
        bool(auth_user_id)
        and bool(profile_payload)
        and bool(conversation_id)
        and first_turn_result is not None
        and first_turn_result.done
        and second_turn_result is not None
        and second_turn_result.done
        and first_message_count >= 2
        and second_message_count > first_message_count
    )

    return {
        "run_id": f"mobile-login-smoke-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_base_url": normalized_base_url,
        "ws_url": ws_url,
        "username": username,
        "phone": phone,
        "created_user": created_user,
        "auth_user_id": auth_user_id,
        "profile_user_id": str(profile_payload.get("user_id") or profile_payload.get("id") or "").strip(),
        "conversation_id": conversation_id,
        "messages_after_first_count": first_message_count,
        "messages_after_second_count": second_message_count,
        "cleanup_conversation": cleanup_conversation,
        "conversation_deleted": conversation_deleted,
        "first_turn": {
            "turn_id": first_turn_result.turn_id if first_turn_result else "",
            "assistant_response": first_turn_result.assistant_response if first_turn_result else "",
            "event_types": first_turn_result.event_types if first_turn_result else [],
            "done": first_turn_result.done if first_turn_result else False,
            "done_status": first_turn_result.done_status if first_turn_result else "",
        },
        "second_turn": {
            "turn_id": second_turn_result.turn_id if second_turn_result else "",
            "assistant_response": second_turn_result.assistant_response if second_turn_result else "",
            "event_types": second_turn_result.event_types if second_turn_result else [],
            "done": second_turn_result.done if second_turn_result else False,
            "done_status": second_turn_result.done_status if second_turn_result else "",
        },
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor mobile auth/login continuity smoke")
    parser.add_argument("--api-base-url", default="https://test2.yousenjiaoyu.com")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--register", action="store_true", help="先调用 /api/v1/auth/register；若已存在则回退到登录")
    parser.add_argument("--username-prefix", default="prelaunchsmoke")
    parser.add_argument("--first-message", default="请用两句话介绍流水施工。")
    parser.add_argument("--second-message", default="继续上一题，用一句话概括你刚才回答的重点。")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--keep-conversation", action="store_true", help="默认会清理 smoke 会话；加上此参数则保留")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password.strip()
    phone = args.phone.strip()
    if args.register and (not username or not password or not phone):
        username, password, phone = _generated_credentials(args.username_prefix)
    if not username or not password:
        raise SystemExit("必须提供 --username 和 --password；若要自动生成，请加 --register。")
    if args.register and not phone:
        raise SystemExit("--register 模式下必须提供 --phone，或留空让脚本自动生成。")

    payload = asyncio.run(
        run_mobile_login_smoke(
            api_base_url=args.api_base_url,
            username=username,
            password=password,
            phone=phone,
            register=args.register,
            first_message=args.first_message,
            second_message=args.second_message,
            timeout_seconds=args.timeout_seconds,
            cleanup_conversation=not args.keep_conversation,
        )
    )

    print(f"Mobile login smoke completed: {payload['run_id']}")
    print(f"Passed: {payload['passed']}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
