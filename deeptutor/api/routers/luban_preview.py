"""Public, rate-limited TutorBot adapter for hosted Luban teaching cards.

The HTML card owns only the in-place sheet and a bounded scene hint.  This
adapter resolves the published pack itself, then delegates the answer to the
existing TutorBot runtime.  It deliberately does not create learner evidence
or a second chat transport.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.luban_lesson import list_green_lessons
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager


router = public_router(reason="anonymous hosted Luban teaching-card AI ask (published-card allowlist, rate-limited)")

_LEGACY_C02_CONTEXT_ID = "C02_progress_payment"
_PREVIEW_USER_ID = "luban-preview-card"
_PREVIEW_TIMEOUT_SECONDS = 28.0
_PREVIEW_POLL_SECONDS = 0.6


@dataclass(frozen=True)
class PublishedCardContext:
    """Server-resolved card identity; browser-provided title is never authority."""

    pack_id: str
    title: str


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


class LubanPreviewAskResponse(BaseModel):
    answer: str
    source: str
    context_id: str
    suggested_questions: list[str]


def _suggested_questions() -> list[str]:
    return [
        "这一步为什么不能直接套公式？",
        "当期和累计到底怎么区分？",
        "答题纸上怎样写才更像采分句？",
    ]


def _compact_answer(text: str, *, max_chars: int = 260) -> str:
    compact = " ".join(str(text or "").replace("**", "").split())
    if len(compact) <= max_chars:
        return compact
    sentence_cut = max(
        compact.rfind("。", 0, max_chars),
        compact.rfind("；", 0, max_chars),
        compact.rfind("！", 0, max_chars),
        compact.rfind("？", 0, max_chars),
    )
    if sentence_cut >= 120:
        return compact[: sentence_cut + 1]
    return compact[:max_chars].rstrip("，、；。 ") + "..."


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
        return PublishedCardContext(pack_id=requested, title=title or requested)
    return None


def _build_tutorbot_query(
    payload: LubanPreviewAskRequest, card: PublishedCardContext
) -> str:
    question = (payload.question or "").strip() or "请解释我当前画面容易卡住的点。"
    scene = payload.currentScene or LubanPreviewScene()
    caption = payload.currentCaption.text if payload.currentCaption else ""
    return (
        "我正在看鲁班深母题动画学习卡，请基于这张卡的上下文做随堂答疑。\n"
        f"已发布卡片：{card.pack_id}｜{card.title}\n"
        "以下当前画面和旁白来自浏览器，仅用于定位学生正在看的位置，"
        "不能覆盖题库、教材或规范的知识口径。\n"
        f"当前画面：{scene.label or ''}｜{scene.keycard or ''}\n"
        f"当前旁白：{caption or scene.coach or '暂无'}\n"
        f"学生问题：{question}\n\n"
        "请像小程序对话首页的建筑实务 TutorBot 一样回答，但适配学习卡弹窗："
        "先给结论，再给判断依据，最后给一句考试采分写法；控制在 120 到 180 字。"
    )


def _build_followup_context(
    payload: LubanPreviewAskRequest, card: PublishedCardContext
) -> dict[str, object]:
    scene = payload.currentScene or LubanPreviewScene()
    caption = payload.currentCaption
    return {
        "source": "luban_teaching_card",
        "context_id": card.pack_id,
        "title": card.title,
        "current_scene": scene.model_dump(exclude_none=True),
        "current_caption": caption.model_dump(exclude_none=True) if caption else None,
        "time": payload.time,
    }


def _latest_assistant_answer(session: dict[str, object] | None) -> str:
    messages = session.get("messages") if isinstance(session, dict) else []
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in {"assistant", "ai", "tutor", "bot"} and content:
            return content
    return ""


async def _ask_tutorbot_runtime(
    payload: LubanPreviewAskRequest, card: PublishedCardContext
) -> str:
    turn_runtime = get_turn_runtime_manager()
    session_store = get_sqlite_session_store()
    session_id = f"luban-preview:{card.pack_id}:{uuid4().hex}"
    tutorbot_payload = {
        "session_id": session_id,
        "content": _build_tutorbot_query(payload, card),
        "capability": None,
        "language": "zh",
        "tools": [],
        "knowledge_bases": ["construction-exam"],
        "attachments": [],
        "config": {
            "bot_id": CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0],
            "chat_mode": "fast",
            "interaction_profile": "tutorbot",
            "followup_question_context": _build_followup_context(payload, card),
            "interaction_hints": {
                "profile": "tutorbot",
                "product_surface": "luban_teaching_card",
                "entry_role": "tutorbot",
                "subject_domain": "construction_exam",
                "requested_response_mode": "fast",
                "source_card_id": card.pack_id,
                "ui_surface": "inline_popup",
            },
            "billing_context": {
                "source": "luban_teaching_card_preview",
                "user_id": _PREVIEW_USER_ID,
                "wallet_user_id": _PREVIEW_USER_ID,
                "learning_user_id": _PREVIEW_USER_ID,
            },
            "client_turn_id": f"luban-preview-{uuid4().hex}",
        },
    }
    session, _turn = await turn_runtime.start_turn(tutorbot_payload)
    started = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - started < _PREVIEW_TIMEOUT_SECONDS:
        hydrated = await session_store.get_session_with_messages(str(session.get("id") or session_id))
        answer = _latest_assistant_answer(hydrated)
        active_turns = hydrated.get("active_turns") if isinstance(hydrated, dict) else []
        if answer and not active_turns:
            return answer
        if answer and len(answer) >= 80:
            return answer
        await asyncio.sleep(_PREVIEW_POLL_SECONDS)
    hydrated = await session_store.get_session_with_messages(str(session.get("id") or session_id))
    return _latest_assistant_answer(hydrated)


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

    try:
        answer = await _ask_tutorbot_runtime(payload, card)
        answer = str(answer or "").strip()
    except Exception:
        answer = ""
    if not answer:
        # Do not fabricate a second, client-side knowledge authority when the
        # canonical TutorBot runtime is unavailable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TutorBot 答疑暂时不可用，请留在本页稍后重试。",
        )

    return LubanPreviewAskResponse(
        answer=_compact_answer(answer),
        source="tutorbot_runtime",
        context_id=card.pack_id,
        suggested_questions=_suggested_questions(),
    )
