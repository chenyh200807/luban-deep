"""学-evidence（lesson_viewed）上报端点（融合计划 §2.1）。

照 ``learner_signal.py`` 路由范式：``secure_router`` 默认鉴权、owner-scope
（``user_id`` 只取鉴权上下文，不接受客户端传）、薄转发到
``lesson_evidence.record_lesson_view_evidence``（唯一 writer，走
``append_memory_event`` 唯一 sink）。本路由不做任何语义判断。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.learner_state.lesson_evidence import record_lesson_view_evidence
from deeptutor.services.learner_state.service import get_learner_state_service
from deeptutor.services.luban_lesson import list_all_pack_ids

router = secure_router(tags=["lesson_progress"])


class LessonProgressRequest(BaseModel):
    # 输入边界(病E):长度上限 schema 级拒绝;pack 存在性在 handler 对
    # manifest 全集(list_all_pack_ids,唯一 pack 枚举权威)校验。
    pack_id: str = Field(min_length=1, max_length=64)
    # schema 级长度上限(Codex P3):非法值仍由 writer 白名单拒 400,
    # 此处只防超长串进 handler 被原样拼进 error detail。
    watched_stage: str = Field(min_length=1, max_length=32)  # "lesson"（讲懂幕）| "practice"（闯关幕）
    card_sha: str = Field(default="", max_length=128)


@router.post(
    "/progress",
    dependencies=[
        Depends(route_rate_limit("lesson_progress_post", default_max_requests=60, default_window_seconds=60.0))
    ],
)
def post_lesson_progress(
    body: LessonProgressRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    # 同步 def(非 async):端点内是同步账本 I/O(JSONL append + outbox
    # sqlite),FastAPI 自动放线程池执行,不阻塞事件循环(病B-1)。
    if body.pack_id not in list_all_pack_ids():
        # 未知 pack 绝不落 append-only 账本(垃圾证据无法收回)。
        raise HTTPException(status_code=400, detail=f"unknown pack_id: {body.pack_id}")
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
