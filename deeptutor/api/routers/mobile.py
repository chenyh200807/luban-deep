from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, require_self_or_admin, route_rate_limit
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.contracts.unified_turn import UnifiedTurnStartResponse, build_turn_stream_bootstrap
from deeptutor.services.learner_state import LearnerStateService
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.query_intent import (
    build_grounding_decision,
)
from deeptutor.services.feedback_service import (
    SupabaseFeedbackStore,
    build_mobile_feedback_row,
)
from deeptutor.services.session import (
    build_user_owner_key,
    get_sqlite_session_store,
    get_turn_runtime_manager,
)

router = APIRouter()
logger = logging.getLogger(__name__)
member_service = get_member_console_service()
learner_state_service = LearnerStateService()
turn_runtime = get_turn_runtime_manager()
session_store = get_sqlite_session_store()

_MOBILE_TUTORBOT_ID = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
_MOBILE_TUTORBOT_NAME = "Construction Exam Coach"
_MOBILE_TUTORBOT_DESCRIPTION = "微信小程序主聊天默认建筑实务 TutorBot"
_MOBILE_PLACEHOLDER_TITLES = {"", "new conversation", "新对话"}
_MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE = 500
MobileFeedbackSupabaseClient = SupabaseFeedbackStore


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
    if owner_key == build_user_owner_key(user_id):
        return
    variants = await _load_mobile_conversation_variants(resolved_conversation_id, user_id)
    if variants:
        return
    raise HTTPException(status_code=404, detail="Conversation not found")


def _new_mobile_conversation_id() -> str:
    return f"tb_{uuid4().hex[:24]}"


def _infer_mobile_conversation_title(text: str) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return "新对话"
    return normalized[:32] + ("..." if len(normalized) > 32 else "")


def _normalize_mobile_conversation_id(session: dict[str, Any]) -> str:
    session_id = str(session.get("id") or session.get("session_id") or "").strip()
    preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
    conversation_id = str(preferences.get("conversation_id") or "").strip()
    if session_id.startswith("tutorbot:") and conversation_id:
        return conversation_id
    return session_id


def _is_placeholder_mobile_title(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in _MOBILE_PLACEHOLDER_TITLES


def _merge_mobile_conversation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        canonical_id = _normalize_mobile_conversation_id(row)
        if not canonical_id:
            continue
        current = merged.get(canonical_id)
        if current is None:
            current = dict(row)
            current["id"] = canonical_id
            current["session_id"] = canonical_id
            merged[canonical_id] = current
            order.append(canonical_id)
        else:
            current_updated = float(current.get("updated_at") or 0.0)
            row_updated = float(row.get("updated_at") or 0.0)
            if row_updated > current_updated:
                for key in ("updated_at", "created_at", "status", "active_turn_id", "capability", "cost_summary"):
                    if key in row:
                        current[key] = row.get(key)
            current["message_count"] = max(
                int(current.get("message_count") or 0),
                int(row.get("message_count") or 0),
            )
            if _is_placeholder_mobile_title(current.get("title")) and not _is_placeholder_mobile_title(row.get("title")):
                current["title"] = row.get("title")
            if not str(current.get("last_message") or "").strip() and str(row.get("last_message") or "").strip():
                current["last_message"] = row.get("last_message")
            current_prefs = current.get("preferences") if isinstance(current.get("preferences"), dict) else {}
            row_prefs = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
            if not current_prefs.get("conversation_id") and row_prefs.get("conversation_id"):
                current["preferences"] = dict(row_prefs)

    result = [merged[item_id] for item_id in order]
    result.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return result


def _matches_mobile_conversation_id(session: dict[str, Any], conversation_id: str) -> bool:
    normalized_conversation_id = str(conversation_id or "").strip()
    if not normalized_conversation_id:
        return False
    session_id = str(session.get("id") or session.get("session_id") or "").strip()
    return (
        session_id == normalized_conversation_id
        or _normalize_mobile_conversation_id(session) == normalized_conversation_id
    )


async def _load_mobile_conversation_variants(
    conversation_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    normalized_conversation_id = str(conversation_id or "").strip()
    if not normalized_conversation_id:
        return []
    owner_key = build_user_owner_key(user_id)
    matches: list[dict[str, Any]] = []
    offset = 0
    while True:
        rows = await session_store.list_sessions_by_owner(
            owner_key,
            source="wx_miniprogram",
            archived=None,
            limit=_MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE,
            offset=offset,
        )
        batch = list(rows or [])
        if not batch:
            break
        matches.extend(
            row
            for row in batch
            if isinstance(row, dict) and _matches_mobile_conversation_id(row, normalized_conversation_id)
        )
        if len(batch) < _MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE:
            break
        offset += _MOBILE_CONVERSATION_LOOKUP_PAGE_SIZE
    return matches


def _merge_mobile_message_rows(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        [item for item in messages if isinstance(item, dict)],
        key=lambda item: (
            float(item.get("created_at") or 0.0),
            int(item.get("id") or 0),
        ),
    )
    merged: list[dict[str, Any]] = []
    for item in ordered:
        presentation = _build_presentation_payload(item)
        signature = (
            str(item.get("role") or ""),
            str(item.get("content") or ""),
            json.dumps(presentation, ensure_ascii=False, sort_keys=True) if presentation else "",
        )
        created_at = float(item.get("created_at") or 0.0)
        if merged:
            previous = merged[-1]
            previous_presentation = _build_presentation_payload(previous)
            previous_signature = (
                str(previous.get("role") or ""),
                str(previous.get("content") or ""),
                json.dumps(previous_presentation, ensure_ascii=False, sort_keys=True)
                if previous_presentation
                else "",
            )
            previous_created_at = float(previous.get("created_at") or 0.0)
            if signature == previous_signature and abs(created_at - previous_created_at) <= 2.0:
                continue
        merged.append(item)
    return merged


async def _persist_mobile_feedback(
    *,
    body: "ChatFeedbackRequest",
    authorization: str | None,
    session_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    user_id = _resolve_user_id(authorization)
    normalized_session_id = str(session_id or body.conversation_id or "").strip()
    normalized_message_id = str(message_id or body.message_id or "").strip()
    if normalized_session_id:
        await _assert_mobile_conversation_access(normalized_session_id, user_id)

    writer = MobileFeedbackSupabaseClient()
    if not writer.is_configured:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable")

    row = build_mobile_feedback_row(
        user_id=user_id,
        session_id=normalized_session_id,
        message_id=normalized_message_id,
        rating=body.rating,
        reason_tags=body.reason_tags,
        comment=body.comment,
        answer_mode=body.answer_mode,
    )
    try:
        await writer.insert_feedback(row)
    except httpx.HTTPStatusError as exc:
        logger.warning("Mobile feedback write failed: status=%s body=%s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Failed to persist feedback") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected mobile feedback write failure")
        raise HTTPException(status_code=500, detail="Failed to persist feedback") from exc
    finally:
        await writer.aclose()

    return {"ok": True}


def _normalize_tutorbot_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "auto":
        return "smart"
    if normalized in {"fast", "deep"}:
        return normalized
    return "smart"


def _extract_goal_patches(patch: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(patch, dict):
        return []
    raw_goals = patch.get("goals")
    if isinstance(raw_goals, list):
        return [dict(item) for item in raw_goals if isinstance(item, dict)]
    raw_goal = patch.get("goal")
    if isinstance(raw_goal, dict):
        return [dict(raw_goal)]
    goal_fields = {
        "id",
        "goal_type",
        "title",
        "target_node_codes",
        "target_question_count",
        "progress",
        "deadline",
        "completed_at",
    }
    if goal_fields.intersection(patch.keys()):
        return [{key: value for key, value in patch.items() if key in goal_fields}]
    return []


def _build_learner_profile_payload(profile: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile or {})
    passthrough_fields = {
        "timezone",
        "source",
        "plan",
        "exam_target",
        "knowledge_level",
        "communication_style",
    }
    passthrough_objects = {
        "learning_preferences",
        "support_preferences",
        "heartbeat_preferences",
        "consent",
    }
    for key in passthrough_fields:
        if key in patch:
            merged[key] = patch[key]
    for key in passthrough_objects:
        if isinstance(patch.get(key), dict):
            merged[key] = dict(patch[key])
    return merged


def _build_member_profile_rollback_patch(profile: dict[str, Any]) -> dict[str, Any]:
    rollback_fields = (
        "display_name",
        "exam_date",
        "daily_target",
        "difficulty_preference",
        "explanation_style",
        "review_reminder",
        "avatar_url",
    )
    return {
        key: profile[key]
        for key in rollback_fields
        if isinstance(profile, dict) and key in profile
    }


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
    merged.setdefault("suppress_answer_reveal_on_generate", True)
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
    grounding_decision = build_grounding_decision(
        query=query,
        knowledge_bases=body.knowledge_bases,
        rag_enabled=True,
        tutorbot_context=True,
    )
    current_info_required = grounding_decision.current_info_required or grounding_decision.textbook_delta_query
    if current_info_required and "web_search" not in requested_tools:
        requested_tools.append("web_search")

    interaction_profile = str(body.interaction_profile or "tutorbot").strip() or "tutorbot"
    interaction_hints = _merge_interaction_hints(
        interaction_profile,
        body.interaction_hints,
        current_info_required=current_info_required,
    )
    if grounding_decision.reasons:
        interaction_hints["grounding_reasons"] = list(grounding_decision.reasons)
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


def _build_presentation_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    events = message.get("events") if isinstance(message.get("events"), list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        presentation = metadata.get("presentation")
        if isinstance(presentation, dict):
            return presentation
    return None


def _serialize_mobile_message(message: dict[str, Any]) -> dict[str, Any]:
    presentation = _build_presentation_payload(message)
    return {
        "role": str(message.get("role") or ""),
        "content": str(message.get("content") or ""),
        "created_at": _ts_to_iso(message.get("created_at")),
        "presentation": presentation,
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
        result = member_service.register_with_external_auth(body.username, body.password, body.phone)
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        user_id = str(
            result.get("user_id")
            or result.get("id")
            or user.get("user_id")
            or user.get("id")
            or ""
        ).strip()
        if user_id:
            try:
                learner_state_service.read_snapshot(user_id)
            except Exception:
                pass
        return result
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    user_id = _resolve_user_id(authorization)
    previous_profile = member_service.get_profile(user_id)
    previous_learner_profile = learner_state_service.read_profile(user_id)
    goal_patches = _extract_goal_patches(patch)
    previous_goals = learner_state_service.read_goals(user_id) if goal_patches else []
    profile = member_service.update_profile(user_id, patch)
    learner_profile = _build_learner_profile_payload(profile, patch)
    try:
        learner_state_service.write_profile_strict(user_id, learner_profile)
        if goal_patches:
            learner_state_service.sync_goals_strict(user_id, goal_patches)
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            member_service.update_profile(user_id, _build_member_profile_rollback_patch(previous_profile))
        except Exception as rollback_exc:
            rollback_errors.append(f"member profile rollback failed: {rollback_exc}")
        try:
            learner_state_service.write_profile_strict(user_id, previous_learner_profile)
        except Exception as rollback_exc:
            rollback_errors.append(f"learner profile rollback failed: {rollback_exc}")
        if goal_patches:
            try:
                learner_state_service.sync_goals_strict(user_id, previous_goals)
            except Exception as rollback_exc:
                rollback_errors.append(f"learner goals rollback failed: {rollback_exc}")
        detail = f"Failed to sync learner state: {exc}"
        if rollback_errors:
            detail = f"{detail}; rollback failed: {'; '.join(rollback_errors)}"
        raise HTTPException(status_code=503, detail=detail) from exc
    return profile


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
    return {"conversations": _merge_mobile_conversation_rows(list(sessions or []))}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="Conversation not found")
    merged_messages: list[dict[str, Any]] = []
    for session_row in sessions:
        session = await session_store.get_session_with_messages(str(session_row.get("id") or ""))
        if session is None:
            continue
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        if preferences.get("source") != "wx_miniprogram":
            continue
        merged_messages.extend(list(session.get("messages") or []))
    if not merged_messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "messages": [
            _serialize_mobile_message(item)
            for item in _merge_mobile_message_rows(merged_messages)
        ]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved_user_id = _resolve_user_id(authorization)
    sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="Conversation not found")
    deleted = False
    for session in sessions:
        session_id = str(session.get("id") or "").strip()
        if not session_id:
            continue
        deleted = await session_store.delete_session(session_id) or deleted
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
        sessions = await _load_mobile_conversation_variants(conversation_id, resolved_user_id)
        if not sessions:
            continue
        if body.action == "delete":
            for session in sessions:
                updated += 1 if await session_store.delete_session(str(session.get("id") or "")) else 0
            continue
        for session in sessions:
            updated += 1 if await session_store.update_session_preferences(
                str(session.get("id") or ""),
                {"archived": body.action == "archive"},
            ) else 0
    return {"updated": updated, "action": body.action}


@router.post("/sessions/{session_id}/messages/{message_id}/feedback")
async def submit_message_feedback(
    session_id: str,
    message_id: str,
    body: ChatFeedbackRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _persist_mobile_feedback(
        body=body,
        authorization=authorization,
        session_id=session_id,
        message_id=message_id,
    )


@router.post("/chat/feedback")
async def chat_feedback(body: ChatFeedbackRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    # Backward-compatible alias for older mini program builds.
    return await _persist_mobile_feedback(
        body=body,
        authorization=authorization,
    )


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
