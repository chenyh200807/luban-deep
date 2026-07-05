"""鲁班站点卡 lesson viewmodel 路由（认证）——双轮 §7 投影门的 runtime 入口。

与 ``luban_preview``（匿名、单卡沙盒）的分界：本路由走 ``secure_router`` 默认
鉴权，只投影 manifest 绿灯包；未签发/不存在一律 404 同形（fail-closed）。
本路由**零写入**——学习证据归 learner_signal（档位①②）、判分链路（档位③）
与 lesson_progress（学-evidence lesson_viewed，融合计划 §2.1）。
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_concept_card_library,
    build_concept_cards,
    build_lesson_viewmodel,
    build_retest_items,
    list_green_lessons,
)

router = secure_router(tags=["luban_lesson"])


@router.get(
    "/lessons",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_list", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def lessons(_: AuthContext = Depends(get_current_user)) -> dict:
    return {"lessons": list_green_lessons()}


@router.get(
    "/lessons/{pack_id}",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_detail", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def lesson_detail(pack_id: str, _: AuthContext = Depends(get_current_user)) -> dict:
    try:
        return build_lesson_viewmodel(pack_id)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="lesson not found")


@router.get(
    "/lessons/{pack_id}/retest-items",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_retest", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def retest_items(
    pack_id: str,
    limit: int = 5,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    from datetime import datetime, timedelta, timezone

    # §9-D2: "天"按服务端 UTC+8 日历日折算, 客户端不自算
    now = datetime.now(timezone(timedelta(hours=8)))
    day_index = now.year * 1000 + now.timetuple().tm_yday
    try:
        items = build_retest_items(
            pack_id, user_id=current_user.user_id, day_index=day_index, limit=limit
        )
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="lesson not found")
    return {"pack_id": pack_id.upper(), "items": items, "day_index": day_index}


# 复习模块灰度旗标（register-before-use: contracts/env_registry.yaml + .env.example）。
# 关 = 空投影（fail-closed 空清单, 页面走诚实空态）, 不 404——路由形状稳定。
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"


def _review_module_enabled() -> bool:
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _exam_date_for(user_id: str) -> str:
    """§6.1 地平线参数: exam_date 唯一读源 = member profile（不复制真值）。
    读取失败/未设置 → ""（引擎按无地平线运转, 不阻塞到期投影）。"""
    try:
        from deeptutor.services.member_console import get_member_console_service

        return str(get_member_console_service().get_profile(user_id).get("exam_date") or "").strip()
    except Exception:
        return ""


@router.get(
    "/review-due",
    dependencies=[
        Depends(route_rate_limit("luban_review_due", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def review_due(current_user: AuthContext = Depends(get_current_user)) -> dict:
    """复习到期投影——到期语义唯一权威=revalidation_queue(§3 C4), 替代前端 N+1 探测。"""
    if not _review_module_enabled():
        return {"due": [], "learned_count": 0, "authority": "revalidation_queue", "enabled": False}
    from deeptutor.services.learner_state.service import get_learner_state_service
    from deeptutor.services.luban_lesson.review_due import build_review_due_projection

    events = get_learner_state_service().list_memory_events(
        current_user.user_id, limit=200
    )
    projection = build_review_due_projection(
        user_id=current_user.user_id,
        events=events,
        exam_date_iso=_exam_date_for(current_user.user_id),
    )
    projection["enabled"] = True
    return projection


@router.get(
    "/concept-cards",
    dependencies=[
        Depends(route_rate_limit("luban_concept_card_library", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def concept_card_library(_: AuthContext = Depends(get_current_user)) -> dict:
    """考点卡库总览（复习页资产入口张数真值）——只数 signed+sha 双闸通过的卡池。

    旗标关 = 空投影（total=0, enabled=false），路由形状稳定（同 review-due 惯例）；
    复习页据此保持「即将开通」诚实占位，不 404。
    """
    if not _review_module_enabled():
        return {"total": 0, "packs": [], "enabled": False}
    library = build_concept_card_library()
    library["enabled"] = True
    return library


@router.get(
    "/concept-cards/{pack_id}",
    dependencies=[
        Depends(route_rate_limit("luban_concept_card_deck", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def concept_card_deck(pack_id: str, _: AuthContext = Depends(get_current_user)) -> dict:
    """单站考点卡（翻卡页）。旗标关 / 非绿灯 / 未签发 / sha 漂移一律 404 同形
    （fail-closed，不泄漏未签发存在性）。本路由零写入——「记住了/再看一眼」
    是客户端纯本地呈现态，绝不写掌握。"""
    if not _review_module_enabled():
        raise HTTPException(status_code=404, detail="concept cards not found")
    try:
        return build_concept_cards(pack_id)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="concept cards not found")
