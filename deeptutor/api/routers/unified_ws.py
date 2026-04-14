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


@router.websocket("/ws")
async def unified_websocket(ws: WebSocket) -> None:
    await ws.accept()
    closed = False
    subscription_tasks: dict[str, asyncio.Task[None]] = {}

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
                    _, turn = await runtime.start_turn(start_message.model_dump(exclude_none=True))
                except RuntimeError as exc:
                    await safe_send(
                        {
                            "type": "error",
                            "source": "unified_ws",
                            "stage": "",
                            "content": str(exc),
                            "metadata": {"turn_terminal": True, "status": "rejected"},
                            "session_id": str(msg.get("session_id") or ""),
                            "turn_id": "",
                            "seq": 0,
                        }
                    )
                    continue
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid start_turn payload: {exc.errors()}"})
                    continue
                await subscribe_turn(turn["id"], after_seq=0)
                continue

            if msg_type == "subscribe_turn":
                try:
                    sub_message = UnifiedTurnSubscribeMessage.model_validate(msg)
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid subscribe_turn payload: {exc.errors()}"})
                    continue
                await subscribe_turn(sub_message.turn_id, after_seq=sub_message.after_seq)
                continue

            if msg_type == "subscribe_session":
                try:
                    sub_session_message = UnifiedTurnSubscribeSessionMessage.model_validate(msg)
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid subscribe_session payload: {exc.errors()}"})
                    continue
                await subscribe_session(
                    sub_session_message.session_id,
                    after_seq=sub_session_message.after_seq,
                )
                continue

            if msg_type == "resume_from":
                try:
                    resume_message = UnifiedTurnResumeMessage.model_validate(msg)
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid resume_from payload: {exc.errors()}"})
                    continue
                await subscribe_turn(resume_message.turn_id, after_seq=resume_message.seq)
                continue

            if msg_type == "unsubscribe":
                try:
                    unsubscribe_message = UnifiedTurnUnsubscribeMessage.model_validate(msg)
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid unsubscribe payload: {exc.errors()}"})
                    continue
                if unsubscribe_message.turn_id:
                    await stop_subscription(unsubscribe_message.turn_id)
                if unsubscribe_message.session_id:
                    await stop_subscription(f"session:{unsubscribe_message.session_id}")
                continue

            if msg_type == "cancel_turn":
                try:
                    cancel_message = UnifiedTurnCancelMessage.model_validate(msg)
                except ValidationError as exc:
                    await safe_send({"type": "error", "content": f"Invalid cancel_turn payload: {exc.errors()}"})
                    continue
                from deeptutor.services.session import get_turn_runtime_manager

                runtime = get_turn_runtime_manager()
                cancelled = await runtime.cancel_turn(cancel_message.turn_id)
                if not cancelled:
                    await safe_send({"type": "error", "content": f"Turn not found: {cancel_message.turn_id}"})
                continue

            await safe_send({"type": "error", "content": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws")
    except Exception as exc:
        logger.error("Unified WS error: %s", exc, exc_info=True)
        await safe_send({"type": "error", "content": str(exc)})
    finally:
        closed = True
        for key in list(subscription_tasks.keys()):
            await stop_subscription(key)
