"""Narrow H5 adapters for hosted Luban teaching cards.

The HTML card owns only its in-place presentation.  A card-entry capability is
issued by the authenticated Mini Program station, then this module starts the
existing TutorBot turn under that same learner and returns a one-turn
subscription capability for the *existing* ``/api/v1/ws`` stream.  It never
creates an anonymous preview learner, a second chat protocol, or a second
mastery writer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.api.routers.mobile import MobileStartTurnRequest, build_mobile_turn_payload
from deeptutor.services.luban_lesson import list_green_lessons
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager


router = public_router(reason="hosted Luban card bridge requires scoped station capability and rate-limit")

_LEGACY_C02_CONTEXT_ID = "C02_progress_payment"
_STREAM_PROTOCOL = "luban-preview-v1"
_STREAM_URL = "/api/v1/ws"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedCardContext:
    """Server-resolved card identity; browser-provided title is never authority."""

    pack_id: str
    title: str
    content_sha256: str = ""


class LubanPreviewScene(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    label: str | None = Field(default=None, max_length=80)
    focus: str | None = Field(default=None, max_length=80)
    keycard: str | None = Field(default=None, max_length=160)
    coach: str | None = Field(default=None, max_length=320)


class LubanPreviewCaption(BaseModel):
    speaker: str | None = Field(default=None, max_length=8)
    text: str | None = Field(default=None, max_length=260)
    start: float | None = None
    end: float | None = None


class LubanPreviewAskRequest(BaseModel):
    contextId: str = Field(max_length=80)
    cardId: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=120)
    question: str | None = Field(default=None, max_length=360)
    currentScene: LubanPreviewScene | None = None
    currentCaption: LubanPreviewCaption | None = None
    time: float | None = None
    # This is an opaque, short-lived capability issued by the authenticated
    # station.  It is not a Mini Program bearer token and cannot call any
    # general account API.
    entryTicket: str = Field(default="", max_length=256)


class LubanPreviewLessonViewedRequest(BaseModel):
    contextId: str = Field(max_length=80)
    cardId: str | None = Field(default=None, max_length=80)
    entryTicket: str = Field(default="", max_length=256)


class LubanPreviewTurnStream(BaseModel):
    transport: str = "websocket"
    url: str = _STREAM_URL
    protocol: str = _STREAM_PROTOCOL
    ticket: str
    turn_id: str
    after_seq: int = 0


class LubanPreviewAskResponse(BaseModel):
    source: str
    context_id: str
    suggested_questions: list[str]
    session_id: str
    turn_id: str
    stream: LubanPreviewTurnStream


def _suggested_questions() -> list[str]:
    return [
        "这一步为什么不能直接套公式？",
        "当期和累计到底怎么区分？",
        "答题纸上怎样写才更像采分句？",
    ]


def _resolve_published_card(context_id: str) -> PublishedCardContext | None:
    """Resolve only current, card-hosted manifest rows (fail closed)."""
    requested = str(context_id or "").strip().upper()
    if requested == _LEGACY_C02_CONTEXT_ID.upper():
        requested = "C02"
    if not requested:
        return None
    for row in list_green_lessons():
        if str(row.get("pack_id") or "").strip().upper() != requested:
            continue
        if row.get("card_hosted") is not True:
            return None
        title = str(row.get("title") or "").strip()
        return PublishedCardContext(
            pack_id=requested,
            title=title or requested,
            content_sha256=str(row.get("content_sha256") or "").strip(),
        )
    return None


def _build_luban_teaching_card_context(
    payload: LubanPreviewAskRequest, card: PublishedCardContext
) -> dict[str, object]:
    """Keep browser playback data as a low-authority anchor, never a question key."""
    scene = payload.currentScene or LubanPreviewScene()
    return (
        {
            "pack_id": card.pack_id,
            "title": card.title,
            "content_sha256": card.content_sha256,
            "current_scene": scene.model_dump(exclude_none=True),
            "current_caption": (
                payload.currentCaption.model_dump(exclude_none=True)
                if payload.currentCaption
                else {}
            ),
            "time": payload.time,
        }
    )


def _build_luban_turn_request(payload: LubanPreviewAskRequest) -> MobileStartTurnRequest:
    """Use the conversation page's request shape; do not author a card prompt."""
    question = (payload.question or "").strip() or "请解释我当前画面容易卡住的点。"
    return MobileStartTurnRequest(
        query=question,
        client_turn_id=f"luban-preview-{uuid4().hex}",
        mode="AUTO",
        language="zh",
        interaction_profile="tutorbot",
        interaction_hints={
            "product_surface": "luban_teaching_card",
            "entry_role": "tutorbot",
            "subject_domain": "construction_exam",
            "ui_surface": "inline_popup",
        },
        knowledge_bases=["construction-exam"],
        # This explicitly enables the existing compiled teaching-context lane
        # for both TutorBot and deep_question.  It remains non-grading input.
        general_knowledge_context=True,
    )


def _build_luban_turn_context_metadata(
    payload: LubanPreviewAskRequest, card: PublishedCardContext
) -> dict[str, object]:
    return {
        "source": "luban_teaching_card",
        "card": _build_luban_teaching_card_context(payload, card),
    }


async def _resolve_entry_user(*, ticket: str, card: PublishedCardContext) -> str:
    access = await get_sqlite_session_store().resolve_luban_card_entry_ticket(
        ticket,
        pack_id=card.pack_id,
    )
    user_id = str((access or {}).get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学习身份已过期，请返回小程序重新打开这一站。",
        )
    return user_id


async def _start_tutorbot_turn(
    payload: LubanPreviewAskRequest,
    card: PublishedCardContext,
    *,
    user_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    turn_runtime = get_turn_runtime_manager()
    session_id = f"luban-preview:{card.pack_id}:{uuid4().hex}"
    request = _build_luban_turn_request(payload)
    tutorbot_payload = build_mobile_turn_payload(
        body=request,
        authenticated_user_id=user_id,
        wallet_user_id=user_id,
        query=request.query,
        luban_teaching_card_context=_build_luban_turn_context_metadata(payload, card),
    )
    tutorbot_payload["session_id"] = session_id
    tutorbot_payload["config"]["billing_context"]["source"] = "luban_teaching_card"
    session, turn = await turn_runtime.start_turn(tutorbot_payload)
    return dict(session or {}), dict(turn or {})


@router.post(
    "/ai-ask",
    response_model=LubanPreviewAskResponse,
    dependencies=[
        Depends(
            route_rate_limit(
                "luban_preview_ai_ask",
                default_max_requests=12,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def ask_luban_preview(payload: LubanPreviewAskRequest) -> LubanPreviewAskResponse:
    # Manifest/file projections are synchronous by design; keep that bounded
    # read out of the async API loop.
    card = await asyncio.to_thread(_resolve_published_card, payload.contextId)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前教学卡暂未开放答疑。",
        )

    user_id = await _resolve_entry_user(ticket=payload.entryTicket, card=card)
    try:
        session, turn = await _start_tutorbot_turn(payload, card, user_id=user_id)
        session_id = str(session.get("id") or session.get("session_id") or "").strip()
        turn_id = str(turn.get("id") or "").strip()
        if not session_id or not turn_id:
            raise RuntimeError("TutorBot turn start returned no session or turn")
        stream_ticket = await get_sqlite_session_store().issue_luban_turn_stream_ticket(
            user_id=user_id,
            pack_id=card.pack_id,
            turn_id=turn_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("luban teaching-card TutorBot turn start failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TutorBot 答疑暂时不可用，请留在本页稍后重试。",
        )

    return LubanPreviewAskResponse(
        source="tutorbot_turn_runtime",
        context_id=card.pack_id,
        suggested_questions=_suggested_questions(),
        session_id=session_id,
        turn_id=turn_id,
        stream=LubanPreviewTurnStream(ticket=stream_ticket, turn_id=turn_id),
    )


@router.post(
    "/lesson-viewed",
    dependencies=[
        Depends(
            route_rate_limit(
                "luban_preview_lesson_viewed",
                default_max_requests=12,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def mark_luban_preview_lesson_viewed(payload: LubanPreviewLessonViewedRequest) -> dict[str, object]:
    """Delegate to the existing lesson-evidence writer before H5 enters five questions.

    This endpoint is only a web-view identity adapter.  It does not decide
    evidence semantics and does not create a second learner-state writer:
    ``record_lesson_view_evidence`` remains the sole append operation.
    """
    card = await asyncio.to_thread(_resolve_published_card, payload.contextId)
    if card is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前教学卡暂未开放学习记录。")
    user_id = await _resolve_entry_user(ticket=payload.entryTicket, card=card)
    from deeptutor.services.learner_state.lesson_evidence import record_lesson_view_evidence
    from deeptutor.services.learner_state.service import get_learner_state_service

    try:
        event = await asyncio.to_thread(
            record_lesson_view_evidence,
            get_learner_state_service(),
            user_id=user_id,
            pack_id=card.pack_id,
            watched_stage="lesson",
            # Learner evidence must name the server-published pack revision,
            # never a browser-supplied label.  The entry ticket already binds
            # learner + pack; this read-model value is the remaining content
            # authority.
            card_sha=card.content_sha256,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "event_id": str(getattr(event, "event_id", "") or "")}
