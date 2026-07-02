"""鲁班站点卡 lesson viewmodel 路由（认证）——双轮 §7 投影门的 runtime 入口。

与 ``luban_preview``（匿名、单卡沙盒）的分界：本路由走 ``secure_router`` 默认
鉴权，只投影 manifest 绿灯包；未签发/不存在一律 404 同形（fail-closed）。
本路由**零写入**——学习证据归 learner_signal（档位①②）与判分链路（档位③）。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_lesson_viewmodel,
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
