from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager

router = APIRouter()
member_service = get_member_console_service()
session_store = get_sqlite_session_store()
turn_runtime = get_turn_runtime_manager()


def _ts_to_iso(timestamp: float | int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp)).isoformat()


def _sse_payload(data: str) -> bytes:
    return f"data: {data}\n\n".encode("utf-8")


def _resolve_user_id(authorization: str | None, user_id: str | None = None) -> str:
    return member_service.resolve_user_id(authorization, user_id=user_id)


class LoginRequest(BaseModel):
    username: str
    password: str


class PhoneRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


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
    return member_service.verify_phone_code(body.phone)


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
async def wechat_login() -> dict[str, Any]:
    return member_service.verify_phone_code("13800000001")


@router.post("/wechat/mp/bind-phone")
async def wechat_bind_phone(body: dict[str, Any]) -> dict[str, Any]:
    return {"bound": True, "phone_code": body.get("phone_code", "")}


@router.get("/practice/today-progress")
async def practice_today_progress(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return member_service.get_today_progress(_resolve_user_id(authorization))


@router.get("/practice/chapter-progress")
async def practice_chapter_progress(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    return member_service.get_chapter_progress(_resolve_user_id(authorization))


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
async def create_conversation() -> dict[str, Any]:
    session = await session_store.create_session()
    await session_store.update_session_preferences(session["id"], {"archived": False, "source": "wx_miniprogram"})
    return {"conversation": {"id": session["id"], "title": session["title"], "created_at": _ts_to_iso(session["created_at"])}}


@router.get("/conversations")
async def list_conversations(archived: bool = False) -> dict[str, Any]:
    sessions = await session_store.list_sessions(limit=200, offset=0)
    items = []
    for session in sessions:
        prefs = session.get("preferences") or {}
        if bool(prefs.get("archived", False)) != archived:
            continue
        items.append(
            {
                "id": session["id"],
                "title": session["title"],
                "last_message": session.get("last_message", ""),
                "created_at": _ts_to_iso(session.get("created_at")),
                "updated_at": _ts_to_iso(session.get("updated_at")),
                "archived": bool(prefs.get("archived", False)),
            }
        )
    return {"conversations": items}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str) -> dict[str, Any]:
    session = await session_store.get_session_with_messages(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = [
        {
            "id": item["id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": _ts_to_iso(item.get("created_at")),
        }
        for item in session.get("messages", [])
    ]
    return {"messages": messages}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, Any]:
    deleted = await session_store.delete_session(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post("/conversations/batch")
async def batch_conversations(body: BatchConversationRequest) -> dict[str, Any]:
    updated = 0
    for conversation_id in body.conversation_ids:
        if body.action == "delete":
            updated += 1 if await session_store.delete_session(conversation_id) else 0
            continue
        prefs = {"archived": body.action == "archive"}
        updated += 1 if await session_store.update_session_preferences(conversation_id, prefs) else 0
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


@router.post("/stream/chat/sse")
async def stream_chat_sse(request: Request) -> StreamingResponse:
    payload = await request.json()
    session_id = str(payload.get("session_id") or payload.get("conversation_id") or "").strip()
    query = str(payload.get("query") or "").strip()
    user_id = str(payload.get("user_id") or "student_demo")
    mode = str(payload.get("mode") or "AUTO").upper()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not session_id:
        session = await session_store.create_session()
        session_id = session["id"]
    chat_mode = "deep" if mode == "DEEP" else "fast"

    async def event_stream():
        try:
            _, turn = await turn_runtime.start_turn(
                {
                    "content": query,
                    "session_id": session_id,
                    "capability": "chat",
                    "language": "zh",
                    "config": {"chat_mode": chat_mode},
                    "metadata": {"mobile_user_id": user_id},
                }
            )
        except RuntimeError as exc:
            yield _sse_payload(json.dumps({"type": "error", "data": str(exc)}, ensure_ascii=False))
            yield _sse_payload("[DONE]")
            return

        title_sent = False
        yield _sse_payload(json.dumps({"type": "status", "data": "thinking"}, ensure_ascii=False))
        async for event in turn_runtime.subscribe_turn(turn["id"]):
            event_type = event.get("type")
            if not title_sent and event_type not in {"session", "done"}:
                session = await session_store.get_session(session_id)
                if session and session.get("title"):
                    yield _sse_payload(
                        json.dumps({"updated_title": session["title"]}, ensure_ascii=False)
                    )
                    title_sent = True
            if event_type == "content":
                yield _sse_payload(
                    json.dumps({"type": "token", "data": event.get("content", "")}, ensure_ascii=False)
                )
            elif event_type in {"stage_start", "thinking", "progress", "observation", "tool_call", "tool_result"}:
                content = event.get("content") or event.get("stage") or event_type
                yield _sse_payload(json.dumps({"type": "status", "data": content}, ensure_ascii=False))
            elif event_type == "sources":
                citations = event.get("metadata", {}).get("sources") or event.get("metadata") or {}
                yield _sse_payload(
                    json.dumps(
                        {
                            "type": "final",
                            "engine": "deeptutor",
                            "engine_session_id": session_id,
                            "engine_turn_id": turn["id"],
                            "citations": citations,
                        },
                        ensure_ascii=False,
                    )
                )
            elif event_type == "result":
                yield _sse_payload(
                    json.dumps(
                        {
                            "type": "final",
                            "engine": "deeptutor",
                            "engine_session_id": session_id,
                            "engine_turn_id": turn["id"],
                        },
                        ensure_ascii=False,
                    )
                )
            elif event_type == "error":
                yield _sse_payload(
                    json.dumps({"type": "error", "data": event.get("content", "服务异常")}, ensure_ascii=False)
                )
            elif event_type == "done":
                yield _sse_payload(json.dumps({"type": "status_end", "data": "done"}, ensure_ascii=False))
                yield _sse_payload("[DONE]")
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
