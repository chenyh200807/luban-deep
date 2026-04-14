from __future__ import annotations

import asyncio
from datetime import datetime
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig

router = APIRouter()
member_service = get_member_console_service()

_MOBILE_TUTORBOT_ID = "construction-exam-coach"
_MOBILE_TUTORBOT_NAME = "Construction Exam Coach"
_MOBILE_TUTORBOT_DESCRIPTION = "微信小程序主聊天默认建筑实务 TutorBot"
_PENDING_MOBILE_TURNS: dict[str, dict[str, Any]] = {}


def _ts_to_iso(timestamp: float | int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp)).isoformat()


def _resolve_user_id(authorization: str | None, user_id: str | None = None) -> str:
    resolved = member_service.resolve_user_id(authorization, user_id=user_id)
    if not str(resolved or "").strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return resolved


def _new_mobile_conversation_id() -> str:
    return f"tb_{uuid4().hex[:24]}"


def _new_mobile_turn_id() -> str:
    return f"turn_{uuid4().hex[:24]}"


def _infer_mobile_conversation_title(text: str) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return "新对话"
    return normalized[:32] + ("..." if len(normalized) > 32 else "")


def _normalize_tutorbot_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "auto":
        return "smart"
    if normalized in {"fast", "deep"}:
        return normalized
    return "smart"


async def _ensure_mobile_tutorbot():
    mgr = get_tutorbot_manager()
    instance = mgr.get_bot(_MOBILE_TUTORBOT_ID)
    if instance and instance.running:
        return instance

    config = mgr._load_bot_config(_MOBILE_TUTORBOT_ID)
    if config is None:
        soul = mgr.get_soul("construction-exam-coach") or {}
        config = BotConfig(
            name=_MOBILE_TUTORBOT_NAME,
            description=_MOBILE_TUTORBOT_DESCRIPTION,
            persona=str(soul.get("content") or ""),
        )
    return await mgr.start_bot(_MOBILE_TUTORBOT_ID, config)


def _build_tutorbot_start_response(
    *,
    conversation_id: str,
    query: str,
    turn_id: str,
) -> dict[str, Any]:
    return {
        "conversation": {
            "id": conversation_id,
            "title": _infer_mobile_conversation_title(query),
            "created_at": datetime.now().isoformat(),
        },
        "turn": {
            "id": turn_id,
            "capability": "tutorbot",
            "status": "running",
        },
        "bot": {
            "id": _MOBILE_TUTORBOT_ID,
            "name": _MOBILE_TUTORBOT_NAME,
        },
        "stream": {
            "transport": "websocket",
            "url": f"/api/v1/mobile/tutorbot/ws/{_MOBILE_TUTORBOT_ID}",
            "chat_id": conversation_id,
            "subscribe": {
                "type": "subscribe_turn",
                "turn_id": turn_id,
                "after_seq": 0,
            },
            "resume": {
                "type": "resume_from",
                "turn_id": turn_id,
                "seq": 0,
            },
        },
    }


class LoginRequest(BaseModel):
    username: str
    password: str


class PhoneRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class WechatLoginRequest(BaseModel):
    code: str = ""


class WechatBindPhoneRequest(BaseModel):
    phone_code: str = ""


class MobileStartTurnRequest(BaseModel):
    query: str
    conversation_id: str = ""
    capability: str = ""
    mode: str = "AUTO"
    language: str = "zh"
    interaction_profile: str = "mini_tutor"
    interaction_hints: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    followup_question_context: dict[str, Any] | None = None


class ChatFeedbackRequest(BaseModel):
    message_id: str = ""
    conversation_id: str = ""
    rating: int = 0
    reason_tags: list[str] = Field(default_factory=list)
    comment: str = ""
    answer_mode: str = "AUTO"


class AssessmentCreateRequest(BaseModel):
    assessment_type: str = "diagnostic"
    count: int = Field(default=20, ge=1, le=50)


class AssessmentSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    time_spent_seconds: int = 0


class BatchConversationRequest(BaseModel):
    action: str
    conversation_ids: list[str] = Field(default_factory=list)


@router.post("/auth/login")
async def auth_login(body: LoginRequest) -> dict[str, Any]:
    return member_service.login_with_password(body.username)


@router.post("/auth/send-code")
async def auth_send_code(body: PhoneRequest) -> dict[str, Any]:
    return member_service.send_phone_code(body.phone)


@router.post("/auth/verify-code")
async def auth_verify_code(body: VerifyCodeRequest) -> dict[str, Any]:
    try:
        return member_service.verify_phone_code(body.phone, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auth/profile")
async def auth_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_profile(_resolve_user_id(authorization))


@router.patch("/auth/profile/settings")
async def auth_profile_settings(
    patch: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return member_service.update_profile(_resolve_user_id(authorization), patch)


@router.post("/wechat/mp/login")
async def wechat_login(body: WechatLoginRequest) -> dict[str, Any]:
    try:
        return await member_service.login_with_wechat_code(body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/wechat/mp/bind-phone")
async def wechat_bind_phone(
    body: WechatBindPhoneRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await member_service.bind_phone_for_wechat(
            _resolve_user_id(authorization),
            body.phone_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/practice/today-progress")
async def practice_today_progress(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_today_progress(_resolve_user_id(authorization))


@router.get("/practice/chapter-progress")
async def practice_chapter_progress(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    return member_service.get_chapter_progress(_resolve_user_id(authorization))


@router.get("/practice/daily-question")
async def practice_daily_question(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_daily_question(_resolve_user_id(authorization))


@router.get("/billing/points")
async def billing_points(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    wallet = member_service.get_wallet(_resolve_user_id(authorization))
    return {"points": wallet["balance"]}


@router.get("/billing/wallet")
async def billing_wallet(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_wallet(_resolve_user_id(authorization))


@router.get("/billing/ledger")
async def billing_ledger(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return member_service.get_ledger(_resolve_user_id(authorization), limit=limit, offset=offset)


@router.get("/homepage/dashboard")
async def homepage_dashboard(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_home_dashboard(_resolve_user_id(authorization))


@router.get("/profile/badges")
async def profile_badges(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_badges(_resolve_user_id(authorization))


@router.get("/bi/radar/{user_id}")
async def bi_radar(user_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    resolved = _resolve_user_id(authorization, user_id=user_id)
    return member_service.get_radar_data(resolved)


@router.get("/plan/mastery-dashboard")
async def mastery_dashboard(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_mastery_dashboard(_resolve_user_id(authorization))


@router.get("/assessment/profile")
async def assessment_profile(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_assessment_profile(_resolve_user_id(authorization))


@router.post("/assessment/create")
async def assessment_create(
    body: AssessmentCreateRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return member_service.create_assessment(_resolve_user_id(authorization), count=body.count)


@router.post("/assessment/{quiz_id}/submit")
async def assessment_submit(
    quiz_id: str,
    body: AssessmentSubmitRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return member_service.submit_assessment(
            _resolve_user_id(authorization),
            quiz_id,
            answers=body.answers,
            time_spent_seconds=body.time_spent_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/conversations")
async def create_conversation(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _resolve_user_id(authorization)
    conversation_id = _new_mobile_conversation_id()
    return {
        "conversation": {
            "id": conversation_id,
            "title": "新对话",
            "created_at": datetime.now().isoformat(),
        }
    }


@router.get("/conversations")
async def list_conversations(
    archived: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    mgr = get_tutorbot_manager()
    items = mgr.list_bot_conversations(
        _MOBILE_TUTORBOT_ID,
        user_id=resolved_user_id,
        archived=archived,
        limit=200,
    )
    return {"conversations": items}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    messages = get_tutorbot_manager().get_bot_conversation_messages(
        _MOBILE_TUTORBOT_ID,
        user_id=resolved_user_id,
        conversation_id=conversation_id,
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "messages": [
            {
                "role": item["role"],
                "content": item["content"],
                "created_at": item.get("created_at") or "",
                "interactive": None,
            }
            for item in messages
        ]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    deleted = get_tutorbot_manager().delete_bot_conversation(
        _MOBILE_TUTORBOT_ID,
        user_id=resolved_user_id,
        conversation_id=conversation_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post("/conversations/batch")
async def batch_conversations(
    body: BatchConversationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    mgr = get_tutorbot_manager()
    updated = 0
    for conversation_id in body.conversation_ids:
        if body.action == "delete":
            updated += 1 if mgr.delete_bot_conversation(
                _MOBILE_TUTORBOT_ID,
                user_id=resolved_user_id,
                conversation_id=conversation_id,
            ) else 0
            continue
        updated += 1 if mgr.update_bot_conversation_archive(
            _MOBILE_TUTORBOT_ID,
            user_id=resolved_user_id,
            conversation_id=conversation_id,
            archived=body.action == "archive",
        ) else 0
    return {"updated": updated, "action": body.action}


@router.post("/chat/feedback")
async def chat_feedback(body: ChatFeedbackRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    member_service.add_note(
        user_id,
        content=f"消息反馈 rating={body.rating} tags={','.join(body.reason_tags)} comment={body.comment}".strip(),
        channel="system",
        pinned=False,
    )
    return {"ok": True}


@router.post("/chat/start-turn")
async def mobile_chat_start_turn(
    body: MobileStartTurnRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    query = str(body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    _resolve_user_id(authorization)
    await _ensure_mobile_tutorbot()
    conversation_id = str(body.conversation_id or "").strip() or _new_mobile_conversation_id()
    turn_id = _new_mobile_turn_id()
    _PENDING_MOBILE_TURNS[turn_id] = {
        "user_id": _resolve_user_id(authorization),
        "conversation_id": conversation_id,
        "query": query,
        "mode": _normalize_tutorbot_mode(body.mode),
        "created_at": datetime.now().timestamp(),
    }
    return _build_tutorbot_start_response(
        conversation_id=conversation_id,
        query=query,
        turn_id=turn_id,
    )


@router.websocket("/mobile/tutorbot/ws/{bot_id}")
async def mobile_tutorbot_ws(ws: WebSocket, bot_id: str):
    authorization = ws.headers.get("authorization")
    try:
        resolved_user_id = _resolve_user_id(authorization)
    except HTTPException:
        await ws.close(code=4401, reason="Authentication required")
        return

    mgr = get_tutorbot_manager()
    if bot_id == _MOBILE_TUTORBOT_ID:
        await _ensure_mobile_tutorbot()

    instance = mgr.get_bot(bot_id)
    if not instance or not instance.running:
        await ws.close(code=4004, reason="Bot not found or not running")
        return

    await ws.accept()
    try:
        async def _stream_response(*, content: str, conversation_id: str, mode: str) -> None:
            delta_sent = False

            async def on_progress(text: str) -> None:
                await ws.send_json({"type": "thinking", "content": text})

            async def on_content_delta(text: str) -> None:
                nonlocal delta_sent
                if not text:
                    return
                delta_sent = True
                await ws.send_json({"type": "content", "content": text})

            response = await mgr.send_message(
                bot_id,
                content,
                chat_id=conversation_id,
                on_progress=on_progress,
                on_content_delta=on_content_delta,
                mode=mode,
                session_key=mgr.build_chat_session_key(
                    bot_id,
                    conversation_id,
                    user_id=resolved_user_id,
                ),
                session_metadata={
                    "user_id": resolved_user_id,
                    "conversation_id": conversation_id,
                    "source": "wx_miniprogram",
                    "archived": False,
                },
            )
            if response and not delta_sent:
                await ws.send_json({"type": "content", "content": response})
            await ws.send_json({"type": "done"})

        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            message_type = str(data.get("type") or "").strip()

            try:
                if message_type in {"subscribe_turn", "resume_from"}:
                    turn_id = str(data.get("turn_id") or "").strip()
                    pending = _PENDING_MOBILE_TURNS.pop(turn_id, None)
                    if not pending:
                        await ws.send_json({"type": "error", "content": "Turn not found or expired"})
                        continue
                    if str(pending.get("user_id") or "").strip() != resolved_user_id:
                        await ws.send_json({"type": "error", "content": "Turn user mismatch"})
                        continue
                    await _stream_response(
                        content=str(pending.get("query") or ""),
                        conversation_id=str(pending.get("conversation_id") or ""),
                        mode=str(pending.get("mode") or "smart"),
                    )
                    continue

                content = str(data.get("content") or "").strip()
                conversation_id = str(data.get("chat_id") or "").strip()
                if not content or not conversation_id:
                    await ws.send_json({"type": "error", "content": "content and chat_id are required"})
                    continue

                await _stream_response(
                    content=content,
                    conversation_id=conversation_id,
                    mode=_normalize_tutorbot_mode(data.get("mode")),
                )
            except RuntimeError as exc:
                await ws.send_json({"type": "error", "content": str(exc)})
    except WebSocketDisconnect:
        return
