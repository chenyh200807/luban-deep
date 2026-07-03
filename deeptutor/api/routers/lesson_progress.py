"""学-evidence（lesson_viewed）上报端点（融合计划 §2.1）。

照 ``learner_signal.py`` 路由范式：``secure_router`` 默认鉴权、owner-scope
（``user_id`` 只取鉴权上下文，不接受客户端传）、薄转发到
``lesson_evidence.record_lesson_view_evidence``（唯一 writer，走
``append_memory_event`` 唯一 sink）。本路由不做任何语义判断。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.learner_state.lesson_evidence import record_lesson_view_evidence
from deeptutor.services.learner_state.service import get_learner_state_service

router = secure_router(tags=["lesson_progress"])


class LessonProgressRequest(BaseModel):
    pack_id: str
    watched_stage: str  # "lesson"（讲懂幕）| "practice"（闯关幕）
    card_sha: str = ""


@router.post(
    "/progress",
    dependencies=[
        Depends(route_rate_limit("lesson_progress_post", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def post_lesson_progress(
    body: LessonProgressRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    try:
        event = record_lesson_view_evidence(
            get_learner_state_service(),
            user_id=current_user.user_id,
            pack_id=body.pack_id,
            watched_stage=body.watched_stage,
            card_sha=body.card_sha,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "event_id": str(getattr(event, "event_id", "") or "")}
