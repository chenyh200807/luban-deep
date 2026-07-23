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
import hashlib
import logging
import time
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.api.routers.mobile import MobileStartTurnRequest, build_mobile_turn_payload
from deeptutor.services.luban_lesson import list_green_lessons
from deeptutor.services.luban_lesson.playback import (
    PlaybackFactInvalid,
    normalize_playback_fact,
)
from deeptutor.services.observability import get_surface_event_store
from deeptutor.services.observability.release_lineage import get_release_lineage
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


class LubanPreviewPlaybackEventRequest(BaseModel):
    contextId: str = Field(max_length=80)
    entryTicket: str = Field(default="", max_length=256)
    eventId: str = Field(min_length=8, max_length=128)
    action: str = Field(min_length=1, max_length=32)
    objectId: str = Field(min_length=1, max_length=128)
    section: str = Field(min_length=1, max_length=64)
    occurredAt: int = Field(default=0, ge=0)
    playbackSessionId: str = Field(min_length=8, max_length=128)
    sequence: int = Field(ge=1, le=1_000_000)
    contentRevision: str = Field(min_length=8, max_length=128)
    positionMs: int = Field(default=0)
    fromPositionMs: int = Field(default=0)
    toPositionMs: int = Field(default=0)
    watchedDeltaMs: int = Field(default=0)
    reason: str = Field(default="", max_length=32)


class LubanPracticeSubmitAnswer(BaseModel):
    variant_id: str = Field(min_length=1, max_length=128)
    selected_option_id: str = Field(min_length=1, max_length=160)


class LubanPracticeSubmitRequest(BaseModel):
    """公开练习页交卷体——只描述「学员看到了哪套题、选了哪些选项」。

    页面不携带、也不上报任何对错判断；判分与逐项解析由服务端
    ``RetestWritebackService.complete()`` 唯一签发。
    """

    contextId: str = Field(max_length=80)
    entryTicket: str = Field(default="", max_length=256)
    practiceSurface: str = Field(default="practice.html", max_length=40)
    projectionReceipt: str = Field(min_length=1, max_length=4096)
    completionId: str = Field(min_length=8, max_length=80)
    answers: list[LubanPracticeSubmitAnswer] = Field(min_length=5, max_length=5)


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


def _conversation_session_id(*, ticket: str, pack_id: str) -> str:
    """Derive one opaque TutorBot session for one validated card entry.

    The entry capability is already the server-validated authority for learner
    and pack.  Its digest keeps follow-up turns in that same canonical session
    without exposing the bearer value or adding client-owned session state.
    """
    normalized_pack = str(pack_id or "").strip().upper()
    digest = hashlib.sha256(str(ticket or "").encode("utf-8")).hexdigest()[:32]
    return f"luban-preview:{normalized_pack}:{digest}"


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


async def _resolve_entry_access(
    *,
    ticket: str,
    card: PublishedCardContext,
) -> dict[str, object]:
    access = await get_sqlite_session_store().resolve_luban_card_entry_ticket(
        ticket,
        pack_id=card.pack_id,
    )
    if not str((access or {}).get("user_id") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学习身份已过期，请返回小程序重新打开这一站。",
        )
    return dict(access or {})


async def _start_tutorbot_turn(
    payload: LubanPreviewAskRequest,
    card: PublishedCardContext,
    *,
    user_id: str,
    session_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    turn_runtime = get_turn_runtime_manager()
    request = _build_luban_turn_request(payload)
    tutorbot_payload = build_mobile_turn_payload(
        body=request,
        authenticated_user_id=user_id,
        wallet_user_id=user_id,
        query=request.query,
        luban_teaching_card_context=_build_luban_turn_context_metadata(payload, card),
    )
    tutorbot_payload["session_id"] = session_id
    # Keep the canonical session lineage authored by the shared Mini Program
    # bootstrap.  The history read model scopes on ``wx_miniprogram``; replacing
    # that value with the product surface made a real SessionStore conversation
    # invisible.  Card identity already travels through interaction_hints and
    # luban_teaching_card_context, so it must not compete for session authority.
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
        session, turn = await _start_tutorbot_turn(
            payload,
            card,
            user_id=user_id,
            session_id=_conversation_session_id(
                ticket=payload.entryTicket,
                pack_id=card.pack_id,
            ),
        )
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


def _practice_submit_day_index() -> int:
    """§9-D2 同一口径：'天'按服务端 UTC+8 日历日折算，客户端不自算。"""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    return now.year * 1000 + now.timetuple().tm_yday


def _grade_practice_submission(
    payload: LubanPracticeSubmitRequest, card: PublishedCardContext, *, user_id: str
) -> dict[str, object]:
    """薄适配器同步内核：归一化 → 收据解析 → 服务端自签 selection → 唯一判分 seam。

    本函数零判分、零证据语义：题集身份由 ``resolve_projection_receipt``（经
    ``build_retest_items``）裁决，答案键只存在于编译 authority sidecar，判分与
    学习证据仅由 ``RetestWritebackService.complete()`` 提交。selection 在同一
    请求内签发并立即被 seam 校验，客户端拿不到、也伪造不了第二种判分入口。
    """
    from deeptutor.services.learner_state.service import get_learner_state_service
    from deeptutor.services.luban_lesson import (
        build_retest_items,
        retest_supply_identity,
    )
    from deeptutor.services.luban_lesson.practice_html import PracticeHtmlInvalid
    from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
    from deeptutor.services.luban_lesson.retest_writeback import (
        RetestCompletionInProgress,
        RetestIdempotencyConflict,
        RetestWritebackService,
    )

    surface_id = str(payload.practiceSurface or "").strip() or "practice.html"
    day_index = _practice_submit_day_index()
    try:
        items = build_retest_items(
            card.pack_id,
            user_id=user_id,
            day_index=day_index,
            mode="forward",
            practice_surface=surface_id,
            projection_receipt=str(payload.projectionReceipt or "").strip(),
        )
    except PracticeHtmlInvalid as exc:
        code = str(exc)
        if code in ("content_updated_retake", "practice_not_released"):
            raise HTTPException(status_code=409, detail={"error": code}) from exc
        raise HTTPException(status_code=404, detail="practice not found") from exc
    variant_ids = [str(item.get("variant_id") or "") for item in items]
    if not items or sorted(variant_ids) != sorted(
        answer.variant_id for answer in payload.answers
    ):
        raise HTTPException(
            status_code=400, detail="practice_submit_answer_set_mismatch"
        )
    supply = retest_supply_identity(card.pack_id, mode="forward")
    if not supply.get("kind") or not supply.get("digest"):
        raise HTTPException(status_code=404, detail="practice not found")
    selection_id = issue_retest_selection(
        user_id=user_id,
        pack_id=card.pack_id,
        day_index=day_index,
        mode="forward",
        variant_ids=variant_ids,
        supply_kind=supply["kind"],
        supply_digest=supply["digest"],
    )
    try:
        return RetestWritebackService(
            learner_state_service=get_learner_state_service(),
        ).complete(
            user_id=user_id,
            completion_id=f"h5:{payload.completionId.strip()}",
            selection_id=selection_id,
            pack_id=card.pack_id,
            mode="forward",
            day_index=day_index,
            answers=[
                {
                    "variant_id": answer.variant_id,
                    "selected_option_id": answer.selected_option_id,
                }
                for answer in payload.answers
            ],
        )
    except RetestIdempotencyConflict as exc:
        raise HTTPException(
            status_code=409, detail="practice completion conflict"
        ) from exc
    except RetestCompletionInProgress as exc:
        raise HTTPException(
            status_code=409, detail="practice completion in progress"
        ) from exc
    except ValueError as exc:
        code = str(exc)
        if code in ("luban_review_module_disabled", "luban_light_practice_disabled"):
            # 灰度未开 = 练习记录暂未开放（诚实终态），不是用户数据问题。
            raise HTTPException(
                status_code=409, detail={"error": "practice_not_released"}
            ) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post(
    "/practice-submit",
    dependencies=[
        Depends(
            route_rate_limit(
                "luban_preview_practice_submit",
                default_max_requests=10,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def submit_luban_preview_practice(
    payload: LubanPracticeSubmitRequest,
) -> dict[str, object]:
    """公开练习页唯一交卷入口——鉴权/归一化/转发，判分不在此处发生。

    entryTicket 是小程序站点签发的短时 capability（同 ai-ask / lesson-viewed），
    绑定 learner + pack；无票 / 过期一律 401 fail-closed，公开页拿不到答案键，
    也没有本地判分可退化。
    """
    card = await asyncio.to_thread(_resolve_published_card, payload.contextId)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前教学卡暂未开放练习判分。",
        )
    user_id = await _resolve_entry_user(ticket=payload.entryTicket, card=card)
    return await asyncio.to_thread(
        _grade_practice_submission, payload, card, user_id=user_id
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


@router.post(
    "/playback-event",
    dependencies=[
        Depends(
            route_rate_limit(
                "luban_preview_playback_event",
                default_max_requests=90,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def record_luban_preview_playback_event(
    payload: LubanPreviewPlaybackEventRequest,
) -> dict[str, object]:
    """Validate an H5 player transition and append it to the behavior authority.

    The browser cannot choose user, release, episode, content revision, or
    section bounds.  This public route is only a scoped ticket adapter over the
    existing ``SurfaceEventStore -> product_behavior_events`` writer.
    """
    card = await asyncio.to_thread(_resolve_published_card, payload.contextId)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前教学卡暂未开放播放记录。",
        )
    access = await _resolve_entry_access(
        ticket=payload.entryTicket,
        card=card,
    )
    user_id = str(access.get("user_id") or "").strip()
    object_id = str(access.get("resource_id") or "").strip()
    if not object_id:
        # Pack-only tickets predate episode binding and cannot prove which
        # lesson page emitted the event.  Reopen the station to mint a scoped
        # capability; never guess episode 1.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="播放身份版本过旧，请返回小程序重新打开这一集。",
        )
    try:
        fact = await asyncio.to_thread(
            normalize_playback_fact,
            {
                "event_id": payload.eventId,
                "action": payload.action,
                "object_id": payload.objectId,
                "section": payload.section,
                "playback_session_id": payload.playbackSessionId,
                "sequence": payload.sequence,
                "content_revision": payload.contentRevision,
                "position_ms": payload.positionMs,
                "from_position_ms": payload.fromPositionMs,
                "to_position_ms": payload.toPositionMs,
                "watched_delta_ms": payload.watchedDeltaMs,
                "reason": payload.reason,
            },
            pack_id=card.pack_id,
            object_id=object_id,
        )
    except PlaybackFactInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Server-derived semantic idempotency: the same player session sequence is
    # one fact even if browser retry code produces a fresh random event id.
    canonical_event_id = "luban_playback_" + hashlib.sha256(
        f"{user_id}|{fact['playback_session_id']}|{fact['sequence']}".encode()
    ).hexdigest()[:32]
    now_ms = int(time.time() * 1000)
    release_id = get_release_lineage().release_id
    metadata = {
        "event_version": 1,
        "visit_id": fact["playback_session_id"],
        "module": "learning",
        "section": fact["section"],
        "action": fact["action"],
        "object_type": "microlesson",
        "object_id": fact["object_id"],
        "entry_source": "luban_station",
        # duration_ms here is actual active playback since the last emitted
        # transition/checkpoint; page visibility dwell stays a separate fact.
        "duration_ms": fact["watched_delta_ms"],
        "visible_ms": 0,
        "result": (
            "completed"
            if fact["action"] == "complete"
            else str(fact["progress_pct"])
            if fact["action"] == "checkpoint"
            else ""
        ),
        "release_id": release_id,
        # app_version is the Mini Program binary version. The H5 card cannot
        # author that fact; content_revision already carries the exact lesson
        # asset SHA and must not be folded into a fake app-version coverage.
        "app_version": "",
        "platform": "wechat_webview",
        "client_event_id": fact["event_id"],
        "playback_session_id": fact["playback_session_id"],
        "sequence": fact["sequence"],
        "content_revision": fact["content_revision"],
        "lesson_file": fact["lesson_file"],
        "position_ms": fact["position_ms"],
        "from_position_ms": fact["from_position_ms"],
        "to_position_ms": fact["to_position_ms"],
        "watched_delta_ms": fact["watched_delta_ms"],
        "content_duration_ms": fact["duration_ms"],
        "progress_pct": fact["progress_pct"],
        "section_index": fact["section_index"],
        "section_label": fact["section_label"],
        "section_group": fact["section_group"],
        "section_start_ms": fact["section_start_ms"],
        "section_end_ms": fact["section_end_ms"],
        "section_progress_pct": fact["section_progress_pct"],
        "reason": fact["reason"],
        # Retain client clock only as bounded diagnostics.  SurfaceEventStore
        # writes business occurred_at from the server receipt clock.
        "client_occurred_at_ms": payload.occurredAt,
    }
    try:
        result = get_surface_event_store().ingest(
            {
                "event_id": canonical_event_id,
                "surface": "wechat_yousenwebview",
                "event_name": "microlesson_playback",
                # playback_session_id is already bounded and names this player
                # session.  Do not add a transport prefix that can exceed the
                # canonical 128-char session boundary.
                "session_id": fact["playback_session_id"],
                "user_id": user_id,
                "collected_at_ms": now_ms,
                "sent_at_ms": now_ms,
                "metadata": metadata,
            },
            validated_event_names=frozenset({"microlesson_playback"}),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"ok": True, **result}
