from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager
from deeptutor.tutorbot.teaching_modes import normalize_teaching_mode

router = APIRouter()
member_service = get_member_console_service()
session_store = get_sqlite_session_store()
turn_runtime = get_turn_runtime_manager()


def _ts_to_iso(timestamp: float | int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp)).isoformat()


def _resolve_user_id(authorization: str | None, user_id: str | None = None) -> str:
    resolved = member_service.resolve_user_id(authorization, user_id=user_id)
    if not str(resolved or "").strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return resolved


def _session_visible_to_user(session: dict[str, Any] | None, resolved_user_id: str) -> bool:
    if not session:
        return False
    prefs = session.get("preferences") or {}
    owner_id = str(prefs.get("user_id") or "").strip()
    return not owner_id or owner_id == resolved_user_id


def _build_turn_start_response(session: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation": {
            "id": session["id"],
            "title": session["title"],
            "created_at": _ts_to_iso(session.get("created_at")),
        },
        "turn": {
            "id": turn["id"],
            "capability": turn.get("capability") or "",
            "status": turn.get("status") or "running",
        },
        "stream": {
            "transport": "websocket",
            "url": "/api/v1/ws",
            "subscribe": {
                "type": "subscribe_turn",
                "turn_id": turn["id"],
                "after_seq": 0,
            },
            "resume": {
                "type": "resume_from",
                "turn_id": turn["id"],
                "seq": 0,
            },
        },
    }


def _build_message_interactive_payload(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    events = message.get("events")
    if not isinstance(events, list):
        return None

    for event in reversed(events):
        if not isinstance(event, dict) or str(event.get("type") or "").strip() != "result":
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        summary = metadata.get("summary")
        if not isinstance(summary, dict):
            continue

        raw_results = summary.get("results")
        if not isinstance(raw_results, list):
            continue

        questions: list[dict[str, Any]] = []
        hidden_contexts: list[dict[str, Any]] = []
        has_multi_choice = False

        for result in raw_results:
            if not isinstance(result, dict):
                continue
            qa_pair = result.get("qa_pair")
            if not isinstance(qa_pair, dict):
                continue

            question_type = str(qa_pair.get("question_type") or "").strip().lower()
            raw_options = qa_pair.get("options")
            if question_type != "choice" or not isinstance(raw_options, dict):
                continue

            option_keys = sorted(str(key or "").strip().upper() for key in raw_options.keys())
            option_map: dict[str, str] = {}
            options: list[dict[str, str]] = []
            for key in option_keys:
                if not key:
                    continue
                value = str(raw_options.get(key) or "").strip()
                if not value:
                    continue
                options.append({"key": key, "text": value})
                option_map[key] = value
            if not options:
                continue

            correct_answer = str(qa_pair.get("correct_answer") or "").strip()
            card_question_type = "multi_choice" if len(correct_answer) > 1 else "single_choice"
            if card_question_type == "multi_choice":
                has_multi_choice = True

            question_index = len(questions) + 1
            questions.append(
                {
                    "index": question_index,
                    "stem": str(qa_pair.get("question") or "").strip(),
                    "question_type": card_question_type,
                    "options": options,
                    "question_id": str(qa_pair.get("question_id") or f"q_{question_index}").strip(),
                }
            )
            hidden_contexts.append(
                {
                    "question_id": str(qa_pair.get("question_id") or f"q_{question_index}").strip(),
                    "question": str(qa_pair.get("question") or "").strip(),
                    "question_type": "choice",
                    "options": option_map,
                    "correct_answer": correct_answer,
                    "explanation": str(qa_pair.get("explanation") or "").strip(),
                    "difficulty": str(qa_pair.get("difficulty") or "").strip(),
                    "concentration": str(
                        qa_pair.get("concentration")
                        or qa_pair.get("knowledge_point")
                        or qa_pair.get("topic")
                        or ""
                    ).strip(),
                    "knowledge_context": str(
                        qa_pair.get("knowledge_context") or qa_pair.get("explanation") or ""
                    ).strip(),
                }
            )

        if not questions:
            continue

        return {
            "type": "mcq_interactive",
            "questions": questions,
            "hidden_contexts": hidden_contexts,
            "submit_hint": (
                "多题作答，先分别点选，再提交答案。"
                if len(questions) > 1
                else "多选题，先点选，再提交答案。"
                if has_multi_choice
                else "请选择后提交答案"
            ),
            "receipt": "",
        }

    return None


def _build_mini_tutor_interaction_hints(
    *,
    mode: str,
    profile: str,
    hints: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(hints or {})
    normalized_mode = normalize_teaching_mode(mode)
    normalized_profile = str(profile or "mini_tutor").strip() or "mini_tutor"

    merged["profile"] = normalized_profile
    merged["product_surface"] = "wechat_miniprogram"
    merged["entry_role"] = "tutorbot"
    merged["subject_domain"] = "construction_exam"
    merged["teaching_mode"] = normalized_mode
    merged["pedagogy_contract"] = "construction_exam_tutor_v1"
    merged["response_contract"] = (
        "fast_scoring_points"
        if normalized_mode == "fast"
        else "deep_four_elements"
        if normalized_mode == "deep"
        else "default_agentic_chat"
    )
    merged["teaching_focus"] = [
        "踩分点",
        "易错点",
        "记忆口诀",
        "心得",
    ]
    return merged


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
    resolved_user_id = _resolve_user_id(authorization)
    session = await session_store.create_session()
    await session_store.update_session_preferences(
        session["id"],
        {
            "archived": False,
            "source": "wx_miniprogram",
            "user_id": resolved_user_id,
        },
    )
    return {"conversation": {"id": session["id"], "title": session["title"], "created_at": _ts_to_iso(session["created_at"])}}


@router.get("/conversations")
async def list_conversations(
    archived: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    sessions = await session_store.list_sessions(limit=200, offset=0)
    items = []
    for session in sessions:
        if not _session_visible_to_user(session, resolved_user_id):
            continue
        prefs = session.get("preferences") or {}
        if bool(prefs.get("archived", False)) != archived:
            continue
        items.append(
            {
                "id": session["id"],
                "title": session["title"],
                "last_message": session.get("last_message", ""),
                "message_count": int(session.get("message_count") or 0),
                "status": str(session.get("status") or "idle"),
                "capability": str(session.get("capability") or ""),
                "cost_summary": session.get("cost_summary"),
                "source": str(prefs.get("source") or ""),
                "created_at": _ts_to_iso(session.get("created_at")),
                "updated_at": _ts_to_iso(session.get("updated_at")),
                "archived": bool(prefs.get("archived", False)),
            }
        )
    return {"conversations": items}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    session = await session_store.get_session_with_messages(conversation_id)
    if session is None or not _session_visible_to_user(session, resolved_user_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = [
        {
            "id": item["id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": _ts_to_iso(item.get("created_at")),
            "interactive": _build_message_interactive_payload(item),
        }
        for item in session.get("messages", [])
    ]
    return {"messages": messages}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    session = await session_store.get_session_with_messages(conversation_id)
    if session is None or not _session_visible_to_user(session, resolved_user_id):
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
        session = await session_store.get_session_with_messages(conversation_id)
        if session is None or not _session_visible_to_user(session, resolved_user_id):
            continue
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


@router.post("/chat/start-turn")
async def mobile_chat_start_turn(
    body: MobileStartTurnRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    query = str(body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    resolved_user_id = _resolve_user_id(authorization)
    session_id = str(body.conversation_id or "").strip()
    capability = str(body.capability or "").strip() or None
    mode = str(body.mode or "AUTO").strip().upper()
    normalized_mode = normalize_teaching_mode(mode)
    config: dict[str, Any] = {}
    if mode == "DEEP":
        config["chat_mode"] = "deep"
        config["chat_mode_explicit"] = True
    elif mode == "FAST":
        config["chat_mode"] = "fast"
        config["chat_mode_explicit"] = True
    interaction_profile = str(body.interaction_profile or "").strip() or "mini_tutor"
    interaction_hints = _build_mini_tutor_interaction_hints(
        mode=normalized_mode,
        profile=interaction_profile,
        hints=body.interaction_hints,
    )
    config["billing_context"] = {
        "source": "wx_miniprogram",
        "user_id": resolved_user_id,
    }
    if interaction_profile:
        config["interaction_profile"] = interaction_profile
    if interaction_hints:
        config["interaction_hints"] = interaction_hints
    if body.followup_question_context:
        config["followup_question_context"] = body.followup_question_context

    try:
        session, turn = await turn_runtime.start_turn(
            {
                "type": "start_turn",
                "content": query,
                "session_id": session_id or None,
                "capability": capability,
                "tools": list(body.tools or []),
                "knowledge_bases": list(body.knowledge_bases or []),
                "attachments": list(body.attachments or []),
                "language": str(body.language or "zh"),
                "config": config,
            }
        )
    except RuntimeError as exc:
        if "active turn" in str(exc).lower() and session_id:
            session = await session_store.get_session(session_id)
            active_turn = await session_store.get_active_turn(session_id)
            if (
                session is not None
                and active_turn is not None
                and _session_visible_to_user(session, resolved_user_id)
            ):
                return _build_turn_start_response(session, active_turn)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session_store.update_session_preferences(
        session["id"],
        {
            "source": "wx_miniprogram",
            "user_id": resolved_user_id,
        },
    )

    return _build_turn_start_response(session, turn)
