"""
Unified WebSocket Endpoint
==========================

Single ``/api/v1/ws`` endpoint for turn-based execution and replayable streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from deeptutor.api.runtime_metrics import get_turn_runtime_metrics
from deeptutor.api.dependencies import AuthContext, enforce_websocket_rate_limit, resolve_auth_context
from deeptutor.contracts.unified_turn import (
    UnifiedTurnCancelMessage,
    UnifiedTurnResumeMessage,
    UnifiedTurnStartMessage,
    UnifiedTurnSubscribeMessage,
    UnifiedTurnSubscribeSessionMessage,
    UnifiedTurnUnsubscribeMessage,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_error_event(
    *,
    content: str,
    session_id: str = "",
    turn_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "error",
        "source": "unified_ws",
        "stage": "",
        "content": content,
        "metadata": {"turn_terminal": True, "status": "rejected"},
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": 0,
    }


def _public_ws_failure_message(action: str) -> str:
    return f"Unable to {action}. Please try again later."


def _public_validation_message(message_type: str) -> str:
    return f"Invalid {message_type} payload."


async def _authorize_session_access(
    session_id: str,
    current_user: AuthContext | None,
) -> None:
    from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store

    store = get_sqlite_session_store()
    owner_key = await store.get_session_owner_key(session_id)
    if not owner_key:
        if current_user and current_user.is_admin:
            return
        raise PermissionError("Session not found")
    if current_user and (
        current_user.is_admin or owner_key == build_user_owner_key(current_user.user_id)
    ):
        return
    raise PermissionError("Session not found")


async def _authorize_turn_access(
    turn_id: str,
    current_user: AuthContext | None,
) -> str:
    from deeptutor.services.session import get_sqlite_session_store

    store = get_sqlite_session_store()
    turn = await store.get_turn(turn_id)
    if turn is None:
        raise LookupError("Turn not found")
    session_id = str(turn.get("session_id") or "").strip()
    await _authorize_session_access(session_id, current_user)
    return session_id


async def _get_active_turn_id_for_session(session_id: str) -> str:
    from deeptutor.services.session import get_sqlite_session_store

    store = get_sqlite_session_store()
    active_turn = await store.get_active_turn(session_id)
    if active_turn is None:
        raise LookupError("Turn not found")
    return str(active_turn.get("id") or "").strip()


def _bind_authenticated_user(
    payload: dict[str, Any],
    current_user: AuthContext | None,
) -> dict[str, Any]:
    if current_user is None:
        return payload

    config = dict(payload.get("config", {}) or {})
    billing_context = config.get("billing_context")
    if not isinstance(billing_context, dict):
        billing_context = {}

    requested_user_id = str(billing_context.get("user_id") or "").strip()
    if requested_user_id and requested_user_id != current_user.user_id and not current_user.is_admin:
        raise PermissionError("Forbidden billing_context user_id")

    config["billing_context"] = {
        **billing_context,
        "source": str(billing_context.get("source") or "authenticated_ws").strip() or "authenticated_ws",
        "user_id": requested_user_id or current_user.user_id,
    }
    return {**payload, "config": config}


@router.websocket("/ws")
async def unified_websocket(ws: WebSocket) -> None:
    if not await enforce_websocket_rate_limit(
        ws,
        "unified_ws_connect",
        default_max_requests=60,
        default_window_seconds=60.0,
    ):
        return
    await ws.accept()
    get_turn_runtime_metrics().record_ws_open()
    closed = False
    subscription_tasks: dict[str, asyncio.Task[None]] = {}
    current_user = resolve_auth_context(ws.headers.get("authorization"))

    async def safe_send(data: dict[str, Any]) -> None:
        nonlocal closed
        if closed:
            return
        try:
            await ws.send_json(data)
        except Exception:
            closed = True

    async def stop_subscription(key: str) -> None:
        task = subscription_tasks.pop(key, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def subscribe_turn(turn_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_turn(turn_id, after_seq=after_seq):
                await safe_send(event)

        await stop_subscription(turn_id)
        subscription_tasks[turn_id] = asyncio.create_task(_forward())

    async def subscribe_session(session_id: str, after_seq: int = 0) -> None:
        from deeptutor.services.session import get_turn_runtime_manager

        async def _forward() -> None:
            runtime = get_turn_runtime_manager()
            async for event in runtime.subscribe_session(session_id, after_seq=after_seq):
                await safe_send(event)

        key = f"session:{session_id}"
        await stop_subscription(key)
        subscription_tasks[key] = asyncio.create_task(_forward())

    try:
        while not closed:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await safe_send({"type": "error", "content": "Invalid JSON."})
                continue

            msg_type = msg.get("type")

            if msg_type in {"message", "start_turn"}:
                from deeptutor.services.session import get_turn_runtime_manager

                runtime = get_turn_runtime_manager()
                try:
                    start_message = UnifiedTurnStartMessage.model_validate(msg)
                    payload = start_message.model_dump(exclude_none=True)
                    session_id = str(payload.get("session_id") or "").strip()
                    if session_id:
                        await _authorize_session_access(session_id, current_user)
                    payload = _bind_authenticated_user(payload, current_user)
                    _, turn = await runtime.start_turn(payload)
                except PermissionError:
                    await safe_send(
                        _build_error_event(
                            content="Unauthorized request.",
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                except RuntimeError:
                    logger.exception("Unified WS start_turn failed")
                    await safe_send(
                        _build_error_event(
                            content=_public_ws_failure_message("start turn"),
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("start_turn")})
                    continue
                await subscribe_turn(turn["id"], after_seq=0)
                continue

            if not msg_type:
                legacy_session_id = str(msg.get("chat_id") or "").strip()
                legacy_content = str(msg.get("content") or "").strip()
                if legacy_session_id and legacy_content:
                    try:
                        await _authorize_session_access(legacy_session_id, current_user)
                        active_turn_id = await _get_active_turn_id_for_session(legacy_session_id)
                    except LookupError:
                        await safe_send(
                            _build_error_event(
                                content="Turn not found",
                                session_id=legacy_session_id,
                            )
                        )
                        continue
                    except PermissionError:
                        await safe_send(
                            _build_error_event(
                                content="Session not found",
                                session_id=legacy_session_id,
                            )
                        )
                        continue
                    await subscribe_turn(active_turn_id, after_seq=0)
                    continue

            if msg_type == "subscribe_turn":
                try:
                    sub_message = UnifiedTurnSubscribeMessage.model_validate(msg)
                    await _authorize_turn_access(sub_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("subscribe_turn")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                await subscribe_turn(sub_message.turn_id, after_seq=sub_message.after_seq)
                continue

            if msg_type == "subscribe_session":
                try:
                    sub_session_message = UnifiedTurnSubscribeSessionMessage.model_validate(msg)
                    await _authorize_session_access(sub_session_message.session_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("subscribe_session")})
                    continue
                except PermissionError:
                    await safe_send(
                        _build_error_event(
                            content="Session not found",
                            session_id=str(msg.get("session_id") or ""),
                        )
                    )
                    continue
                await subscribe_session(
                    sub_session_message.session_id,
                    after_seq=sub_session_message.after_seq,
                )
                continue

            if msg_type == "resume_from":
                try:
                    resume_message = UnifiedTurnResumeMessage.model_validate(msg)
                    await _authorize_turn_access(resume_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("resume_from")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                await subscribe_turn(resume_message.turn_id, after_seq=resume_message.seq)
                continue

            if msg_type == "unsubscribe":
                try:
                    unsubscribe_message = UnifiedTurnUnsubscribeMessage.model_validate(msg)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("unsubscribe")})
                    continue
                if unsubscribe_message.turn_id:
                    await stop_subscription(unsubscribe_message.turn_id)
                if unsubscribe_message.session_id:
                    await stop_subscription(f"session:{unsubscribe_message.session_id}")
                continue

            if msg_type == "cancel_turn":
                try:
                    cancel_message = UnifiedTurnCancelMessage.model_validate(msg)
                    await _authorize_turn_access(cancel_message.turn_id, current_user)
                except ValidationError:
                    await safe_send({"type": "error", "content": _public_validation_message("cancel_turn")})
                    continue
                except LookupError:
                    await safe_send(
                        _build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or ""))
                    )
                    continue
                except PermissionError:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=str(msg.get("turn_id") or "")))
                    continue
                from deeptutor.services.session import get_turn_runtime_manager

                runtime = get_turn_runtime_manager()
                cancelled = await runtime.cancel_turn(cancel_message.turn_id)
                if not cancelled:
                    await safe_send(_build_error_event(content="Turn not found", turn_id=cancel_message.turn_id))
                continue

            await safe_send({"type": "error", "content": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws")
    except Exception:
        logger.exception("Unified WS error")
        await safe_send(
            _build_error_event(content=_public_ws_failure_message("process the websocket request"))
        )
    finally:
        closed = True
        for key in list(subscription_tasks.keys()):
            await stop_subscription(key)
        get_turn_runtime_metrics().record_ws_close()
