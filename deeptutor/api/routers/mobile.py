from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, require_self_or_admin, route_rate_limit
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.contracts.unified_turn import UnifiedTurnStartResponse, build_turn_stream_bootstrap
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.session import (
    build_user_owner_key,
    get_sqlite_session_store,
    get_turn_runtime_manager,
)

router = APIRouter()
member_service = get_member_console_service()
turn_runtime = get_turn_runtime_manager()
session_store = get_sqlite_session_store()

_MOBILE_TUTORBOT_ID = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
_MOBILE_TUTORBOT_NAME = "Construction Exam Coach"
_MOBILE_TUTORBOT_DESCRIPTION = "微信小程序主聊天默认建筑实务 TutorBot"


def _ts_to_iso(timestamp: float | int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp)).isoformat()


def _resolve_user_id(authorization: str | None, user_id: str | None = None) -> str:
    resolved = member_service.resolve_user_id(authorization, user_id=user_id)
    if not str(resolved or "").strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return resolved


async def _assert_mobile_conversation_access(conversation_id: str, user_id: str) -> None:
    resolved_conversation_id = str(conversation_id or "").strip()
    if not resolved_conversation_id:
        return
    owner_key = await session_store.get_session_owner_key(resolved_conversation_id)
    if not owner_key:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if owner_key != build_user_owner_key(user_id):
        raise HTTPException(status_code=404, detail="Conversation not found")


def _new_mobile_conversation_id() -> str:
    return f"tb_{uuid4().hex[:24]}"


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


def _query_requires_current_info(query: str) -> bool:
    text = str(query or "").strip().lower()
    keywords = (
        "最新",
        "现行",
        "当前",
        "今年",
        "最近",
        "政策",
        "通知",
        "公告",
        "新规",
        "发文",
        "变化",
    )
    return any(keyword in text for keyword in keywords)


def _merge_interaction_hints(
    profile: str,
    hints: dict[str, Any] | None,
    *,
    current_info_required: bool,
) -> dict[str, Any]:
    merged = dict(hints or {})
    normalized_profile = str(profile or "").strip().lower()
    if normalized_profile == "":
        normalized_profile = "tutorbot"
    merged["profile"] = normalized_profile
    merged.setdefault("product_surface", "wechat_miniprogram")
    merged.setdefault("entry_role", "tutorbot")
    merged.setdefault("subject_domain", "construction_exam")
    if current_info_required:
        merged["current_info_required"] = True
    return merged


def _build_mobile_turn_payload(
    *,
    body: MobileStartTurnRequest,
    user_id: str,
    query: str,
) -> dict[str, Any]:
    requested_tools = [str(item).strip() for item in (body.tools or []) if str(item).strip()]
    current_info_required = _query_requires_current_info(query)
    if current_info_required and "web_search" not in requested_tools:
        requested_tools.append("web_search")

    interaction_profile = str(body.interaction_profile or "tutorbot").strip() or "tutorbot"
    interaction_hints = _merge_interaction_hints(
        interaction_profile,
        body.interaction_hints,
        current_info_required=current_info_required,
    )
    config: dict[str, Any] = {
        "chat_mode": _normalize_tutorbot_mode(body.mode),
        "interaction_hints": interaction_hints,
        "billing_context": {
            "source": "wx_miniprogram",
            "user_id": user_id,
        },
        "interaction_profile": interaction_profile,
    }
    if body.followup_question_context:
        config["followup_question_context"] = dict(body.followup_question_context)

    capability = str(body.capability or "").strip() or None
    if capability == "tutorbot":
        capability = None
    config["bot_id"] = _MOBILE_TUTORBOT_ID
    return {
        "session_id": str(body.conversation_id or "").strip() or None,
        "content": query,
        "capability": capability,
        "language": str(body.language or "zh").strip() or "zh",
        "tools": requested_tools,
        "knowledge_bases": list(body.knowledge_bases or []),
        "attachments": list(body.attachments or []),
        "config": config,
    }


def _build_interactive_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    events = message.get("events") if isinstance(message.get("events"), list) else []
    questions: list[dict[str, Any]] = []
    hidden_contexts: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
        results = summary.get("results") if isinstance(summary.get("results"), list) else []
        for result in results:
            qa_pair = result.get("qa_pair") if isinstance(result, dict) else None
            if not isinstance(qa_pair, dict):
                continue
            question = {
                "question_id": str(qa_pair.get("question_id") or "").strip(),
                "question": str(qa_pair.get("question") or "").strip(),
                "question_type": str(qa_pair.get("question_type") or "").strip(),
                "options": qa_pair.get("options") or {},
                "difficulty": qa_pair.get("difficulty"),
                "concentration": qa_pair.get("concentration"),
            }
            if question["question_id"] and question["question"]:
                questions.append(question)
                hidden_contexts.append(
                    {
                        "question_id": question["question_id"],
                        "correct_answer": qa_pair.get("correct_answer"),
                        "explanation": qa_pair.get("explanation"),
                    }
                )
    if not questions:
        return None
    return {
        "type": "mcq_interactive",
        "questions": questions,
        "hidden_contexts": hidden_contexts,
    }


def _serialize_mobile_message(message: dict[str, Any]) -> dict[str, Any]:
    interactive = _build_interactive_payload(message)
    return {
        "role": str(message.get("role") or ""),
        "content": str(message.get("content") or ""),
        "created_at": _ts_to_iso(message.get("created_at")),
        "interactive": interactive,
    }


def _build_tutorbot_start_response(
    *,
    conversation_id: str,
    query: str,
    turn_id: str,
    capability: str,
) -> dict[str, Any]:
    response = UnifiedTurnStartResponse(
        conversation={
            "id": conversation_id,
            "title": _infer_mobile_conversation_title(query),
            "created_at": datetime.now().isoformat(),
        },
        turn={
            "id": turn_id,
            "capability": capability,
            "status": "running",
        },
        bot={
            "id": _MOBILE_TUTORBOT_ID,
            "name": _MOBILE_TUTORBOT_NAME,
        },
        stream=build_turn_stream_bootstrap(session_id=conversation_id, turn_id=turn_id),
    )
    return response.model_dump(exclude_none=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class PhoneRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    phone: str


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
    interaction_profile: str = "tutorbot"
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


@router.post(
    "/auth/login",
    dependencies=[Depends(route_rate_limit("mobile_auth_login", default_max_requests=10, default_window_seconds=60.0))],
)
async def auth_login(body: LoginRequest) -> dict[str, Any]:
    try:
        return member_service.login_with_password(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post(
    "/auth/register",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_register", default_max_requests=3, default_window_seconds=60.0))
    ],
)
async def auth_register(body: RegisterRequest) -> dict[str, Any]:
    try:
        return member_service.register_with_external_auth(body.username, body.password, body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/auth/send-code",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_send_code", default_max_requests=3, default_window_seconds=60.0))
    ],
)
async def auth_send_code(body: PhoneRequest) -> dict[str, Any]:
    try:
        return member_service.send_phone_code(body.phone)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/auth/verify-code",
    dependencies=[
        Depends(route_rate_limit("mobile_auth_verify_code", default_max_requests=6, default_window_seconds=60.0))
    ],
)
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


@router.post(
    "/wechat/mp/login",
    dependencies=[
        Depends(route_rate_limit("mobile_wechat_login", default_max_requests=10, default_window_seconds=60.0))
    ],
)
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
async def bi_radar(
    user_id: str,
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    resolved = current_user.user_id if not current_user.is_admin else user_id
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
    resolved_user_id = _resolve_user_id(authorization)
    session = await session_store.ensure_session(
        _new_mobile_conversation_id(),
        owner_key=build_user_owner_key(resolved_user_id),
    )
    await session_store.update_session_title(session["id"], "新对话")
    await session_store.update_session_preferences(
        session["id"],
        {
            "source": "wx_miniprogram",
            "user_id": resolved_user_id,
            "archived": False,
            "bot_id": _MOBILE_TUTORBOT_ID,
        },
    )
    return {
        "conversation": {
            "id": session["id"],
            "title": "新对话",
            "created_at": _ts_to_iso(session.get("created_at")),
        }
    }


@router.get("/conversations")
async def list_conversations(
    archived: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    sessions = await session_store.list_sessions_by_owner(
        build_user_owner_key(resolved_user_id),
        source="wx_miniprogram",
        archived=archived,
        limit=200,
        offset=0,
    )
    return {"conversations": sessions}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    owner_key = await session_store.get_session_owner_key(conversation_id)
    if owner_key != build_user_owner_key(resolved_user_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    session = await session_store.get_session_with_messages(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
    if preferences.get("source") != "wx_miniprogram":
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "messages": [_serialize_mobile_message(item) for item in list(session.get("messages") or [])]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    owner_key = await session_store.get_session_owner_key(conversation_id)
    if owner_key != build_user_owner_key(resolved_user_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    session = await session_store.get_session(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
    if preferences.get("source") != "wx_miniprogram":
        raise HTTPException(status_code=404, detail="Conversation not found")
    deleted = await session_store.delete_session(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post("/conversations/batch")
async def batch_conversations(
    body: BatchConversationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    updated = 0
    for conversation_id in body.conversation_ids:
        owner_key = await session_store.get_session_owner_key(conversation_id)
        if owner_key != build_user_owner_key(resolved_user_id):
            continue
        session = await session_store.get_session(conversation_id)
        if session is None:
            continue
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        if preferences.get("source") != "wx_miniprogram":
            continue
        if body.action == "delete":
            updated += 1 if await session_store.delete_session(conversation_id) else 0
            continue
        updated += 1 if await session_store.update_session_preferences(
            conversation_id,
            {"archived": body.action == "archive"},
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

    resolved_user_id = _resolve_user_id(authorization)
    await _assert_mobile_conversation_access(body.conversation_id, resolved_user_id)
    payload = _build_mobile_turn_payload(
        body=body,
        user_id=resolved_user_id,
        query=query,
    )
    session, turn = await turn_runtime.start_turn(payload)
    return _build_tutorbot_start_response(
        conversation_id=str(session.get("id") or ""),
        query=query,
        turn_id=str(turn.get("id") or ""),
        capability=str(turn.get("capability") or "chat") or "chat",
    )
