"""Preview-only Luban learning-card helpers.

This router exists to validate the C02 animation-card experience before the
feature is wired into the authenticated TutorBot runtime. It is deliberately
narrow: one allowed context id, bounded payloads, and route-level rate limiting.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.session import get_sqlite_session_store, get_turn_runtime_manager


router = public_router(reason="anonymous luban preview AI ask (rate-limited)")

_C02_CONTEXT_ID = "C02_progress_payment"
_PREVIEW_USER_ID = "luban-preview-c02"
_PREVIEW_TIMEOUT_SECONDS = 28.0
_PREVIEW_POLL_SECONDS = 0.6
_C02_AUTHORITY_CONTEXT = {
    "title": "进度款题先判四口径",
    "main_exam_action": "把进度款题写成资金链采分句：先判哪笔钱，再锁量价、时点、扣减。",
    "safe_summary": (
        "进度款类题先判四个口径：哪笔钱、量价口径、时点口径、扣减口径。"
        "不要先套公式，要先把当期、累计、税前价、预付款扣回和质保金扣留说清楚。"
    ),
    "key_points": [
        "哪笔钱：预付款、进度款、结算款、质保金先分清。",
        "量价口径：工程量和综合单价是否含税、是否净量。",
        "时点口径：累计完成还是当期完成，会影响起扣和实付。",
        "扣减口径：扣预付款、前期已付、发包人扣款和质保金。",
    ],
}


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


def _fallback_answer(payload: LubanPreviewAskRequest) -> str:
    scene = payload.currentScene or LubanPreviewScene()
    question = (payload.question or "我现在最容易卡在哪里？").strip()
    label = scene.label or "当前画面"
    keycard = scene.keycard or _C02_AUTHORITY_CONTEXT["title"]
    points = "；".join(_C02_AUTHORITY_CONTEXT["key_points"][:3])
    return (
        f"你问的是：{question}\n\n"
        f"先看这幕「{label}」：{keycard}。这张卡真正训练的不是背公式，而是先判资金口径。"
        f"答题时按“四口径”落笔：哪笔钱、量价、时点、扣减。{points}。"
        "最后把话落到当期实付或判断结论，阅卷人才看得到采分动作。"
    )


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


def _build_tutorbot_query(payload: LubanPreviewAskRequest) -> str:
    question = (payload.question or "").strip() or "请解释我当前画面容易卡住的点。"
    scene = payload.currentScene or LubanPreviewScene()
    caption = payload.currentCaption.text if payload.currentCaption else ""
    return (
        "我正在看鲁班深母题动画学习卡，请基于这张卡的上下文做随堂答疑。\n"
        f"卡片：{_C02_AUTHORITY_CONTEXT['title']}\n"
        f"主线：{_C02_AUTHORITY_CONTEXT['main_exam_action']}\n"
        f"母题摘要：{_C02_AUTHORITY_CONTEXT['safe_summary']}\n"
        f"关键点：{'；'.join(_C02_AUTHORITY_CONTEXT['key_points'])}\n"
        f"当前画面：{scene.label or ''}｜{scene.keycard or ''}\n"
        f"当前旁白：{caption or scene.coach or '暂无'}\n"
        f"学生问题：{question}\n\n"
        "请像小程序对话首页的建筑实务 TutorBot 一样回答，但适配学习卡弹窗："
        "先直接解惑，再给一句考试采分写法，控制在 120 到 180 字。"
    )


def _build_followup_context(payload: LubanPreviewAskRequest) -> dict[str, object]:
    scene = payload.currentScene or LubanPreviewScene()
    caption = payload.currentCaption
    return {
        "source": "luban_animation_card",
        "context_id": _C02_CONTEXT_ID,
        "title": _C02_AUTHORITY_CONTEXT["title"],
        "main_exam_action": _C02_AUTHORITY_CONTEXT["main_exam_action"],
        "safe_summary": _C02_AUTHORITY_CONTEXT["safe_summary"],
        "key_points": list(_C02_AUTHORITY_CONTEXT["key_points"]),
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


async def _ask_tutorbot_runtime(payload: LubanPreviewAskRequest) -> str:
    turn_runtime = get_turn_runtime_manager()
    session_store = get_sqlite_session_store()
    session_id = f"luban-preview:{_C02_CONTEXT_ID}:{uuid4().hex}"
    tutorbot_payload = {
        "session_id": session_id,
        "content": _build_tutorbot_query(payload),
        "capability": None,
        "language": "zh",
        "tools": [],
        "knowledge_bases": ["construction-exam"],
        "attachments": [],
        "config": {
            "bot_id": CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0],
            "chat_mode": "fast",
            "interaction_profile": "tutorbot",
            "followup_question_context": _build_followup_context(payload),
            "interaction_hints": {
                "profile": "tutorbot",
                "product_surface": "luban_animation_card",
                "entry_role": "tutorbot",
                "subject_domain": "construction_exam",
                "requested_response_mode": "fast",
                "source_card_id": _C02_CONTEXT_ID,
                "ui_surface": "inline_popup",
            },
            "billing_context": {
                "source": "luban_animation_card_preview",
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
    if payload.contextId != _C02_CONTEXT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前预览答疑只开放 C02_progress_payment。",
        )

    fallback = _fallback_answer(payload)
    try:
        answer = await _ask_tutorbot_runtime(payload)
        answer = str(answer or "").strip()
    except Exception:
        answer = ""

    return LubanPreviewAskResponse(
        answer=_compact_answer(answer or fallback),
        source="tutorbot_runtime" if answer else "fallback",
        context_id=_C02_CONTEXT_ID,
        suggested_questions=_suggested_questions(),
    )
