"""鲁班站点卡 lesson viewmodel 路由（认证）——双轮 §7 投影门的 runtime 入口。

与 ``luban_preview``（匿名、单卡沙盒）的分界：本路由走 ``secure_router`` 默认
鉴权，只投影 manifest 绿灯包；未签发/不存在一律 404 同形（fail-closed）。
本路由**零写入**——学习证据归 learner_signal（档位①②）、判分链路（档位③）
与 lesson_progress（学-evidence lesson_viewed，融合计划 §2.1）。
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_antidote,
    build_antidote_library,
    build_cloze,
    build_cloze_library,
    build_concept_card_library,
    build_concept_cards,
    build_lesson_viewmodel,
    build_retest_items,
    build_seethrough,
    build_seethrough_library,
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
    mode: str = "review",
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    """变体题面抽取（同一 builder / 同一签发池，两种取题模式）：
    - ``mode=review``（默认，复习轮换皮复测）；
    - ``mode=forward``（学习轮 2 分钟轻练：对刚学完的 pack 广度优先取一组，
      覆盖不同 rule_group）。仅选序不同，均本地判分、证据非 promoting。

    未识别的 mode 归一为 review（thin 归一，不新增第二 builder/第二端点）。
    """
    from datetime import datetime, timedelta, timezone

    # §9-D2: "天"按服务端 UTC+8 日历日折算, 客户端不自算
    now = datetime.now(timezone(timedelta(hours=8)))
    day_index = now.year * 1000 + now.timetuple().tm_yday
    mode = "forward" if str(mode or "").strip().lower() == "forward" else "review"
    try:
        items = build_retest_items(
            pack_id,
            user_id=current_user.user_id,
            day_index=day_index,
            limit=limit,
            mode=mode,
        )
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="lesson not found")
    return {"pack_id": pack_id.upper(), "items": items, "day_index": day_index, "mode": mode}


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


@router.get(
    "/seethrough",
    dependencies=[
        Depends(route_rate_limit("luban_seethrough_library", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def seethrough_library(_: AuthContext = Depends(get_current_user)) -> dict:
    """看穿库总览(F16 5 天留存内容入口天数真值)——只数 signed+sha 双闸通过的看穿池。
    旗标关 = 空投影(total=0, enabled=false),路由形状稳定(同 concept-cards 惯例)。"""
    if not _review_module_enabled():
        return {"total": 0, "packs": [], "enabled": False}
    library = build_seethrough_library()
    library["enabled"] = True
    return library


@router.get(
    "/seethrough/{pack_id}",
    dependencies=[
        Depends(route_rate_limit("luban_seethrough_deck", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def seethrough_deck(pack_id: str, _: AuthContext = Depends(get_current_user)) -> dict:
    """单站看穿 5 天内容(表皮试探 4 选 1 + 透视揭底 4 段 + 暖纠正 + 定位证据带延伸标注)。
    旗标关 / 非绿灯 / 未签发 / sha 漂移一律 404 同形(fail-closed,不泄漏未签发存在性)。
    本路由零写入——看穿内容全部编译期签发,前端只投影、一字不新造。"""
    if not _review_module_enabled():
        raise HTTPException(status_code=404, detail="seethrough not found")
    try:
        return build_seethrough(pack_id)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="seethrough not found")


@router.get(
    "/antidotes",
    dependencies=[
        Depends(route_rate_limit("luban_antidote_library", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def antidote_library(_: AuthContext = Depends(get_current_user)) -> dict:
    """R8 解药库总览（错因银行资产入口「解药覆盖」张数真值）——只数 signed+sha
    双闸通过的解药池。旗标关 = 空投影（total=0, enabled=false），路由形状稳定
    （同 concept-cards / review-due 惯例）；错因银行据此保持「解药整理中」诚实占位。"""
    if not _review_module_enabled():
        return {"total": 0, "packs": [], "enabled": False}
    library = build_antidote_library()
    library["enabled"] = True
    return library


@router.get(
    "/antidotes/{pack_id}/{error_code}",
    dependencies=[
        Depends(route_rate_limit("luban_antidote_detail", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def antidote_detail(
    pack_id: str, error_code: str, _: AuthContext = Depends(get_current_user)
) -> dict:
    """单条解药（错因银行 detail「解药位」）——按 {pack_id, error_code} 投影
    signed 解药，返回 errorbank vm head-note 钉死的 {mental_model, textbook_ref}。
    旗标关 / 非绿灯 / 未签发 / sha 漂移 / 该码无解药一律 404 同形（fail-closed，
    详情页据此保持「解药整理中」占位，绝不自造讲解）。本路由零写入。"""
    if not _review_module_enabled():
        raise HTTPException(status_code=404, detail="antidote not found")
    try:
        return build_antidote(pack_id, error_code)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="antidote not found")


@router.get(
    "/cloze",
    dependencies=[
        Depends(route_rate_limit("luban_cloze_library", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def cloze_library(_: AuthContext = Depends(get_current_user)) -> dict:
    """R6 精确挖空库总览——只数 signed+sha 双闸通过的挖空池。旗标关 = 空投影
    （total=0, enabled=false），路由形状稳定；实务闯关据此保持自由默写降级。"""
    if not _review_module_enabled():
        return {"total": 0, "packs": [], "enabled": False}
    library = build_cloze_library()
    library["enabled"] = True
    return library


@router.get(
    "/cloze/{pack_id}",
    dependencies=[
        Depends(route_rate_limit("luban_cloze_deck", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def cloze_deck(pack_id: str, _: AuthContext = Depends(get_current_user)) -> dict:
    """单站精确挖空（实务闯关半写数据：recall_prompt + skeleton_sentences）。
    旗标关 / 非绿灯 / 未签发 / sha 漂移一律 404 同形（fail-closed，闯关据此保持
    自由默写降级，不伪装挖空）。本路由零写入。"""
    if not _review_module_enabled():
        raise HTTPException(status_code=404, detail="cloze not found")
    try:
        return build_cloze(pack_id)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="cloze not found")


class FullAnswerRequest(BaseModel):
    """档位③全量作答提交体。变体池题面权威 = 已签发 variant bank，答案 = 自由默写文本。"""

    variant_id: str = Field(..., min_length=1, max_length=128)
    answer_text: str = Field(..., min_length=1, max_length=8000)


@router.post(
    "/lessons/{pack_id}/full-answer",
    dependencies=[
        Depends(route_rate_limit("luban_full_answer", default_max_requests=20, default_window_seconds=60.0))
    ],
)
async def full_answer(
    pack_id: str,
    payload: FullAnswerRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    """实务闯关「全量作答」档（档位③）——自由默写文本接既有判分内核链路。

    与档位①②（关键词填空/默写走 ``learner_signal``，非 promoting）的分界：本档
    走判分内核 + ``write_grading_error_events``（``source_feature=construction_grading``，
    判分级 promoting 白名单）→ auto-synthesize weak_points / 复测密度 / 错因银行。

    thin：本路由自身零判分、零写入真值——只把鉴权上下文的 user_id 接到既有
    ``grade_full_answer`` 编排（resolve→内核→唯一 sink）。旗标关一律 404 同形
    （fail-closed，路由形状稳定，不泄漏未签发存在性）。现有 node 型变体包无签发
    采分点供给 → 内核 open_skill 兜底 → 证据 L0 封顶（如实，非 bug）。
    """
    if not _review_module_enabled():
        raise HTTPException(status_code=404, detail="full answer grading not found")
    from deeptutor.services.learner_state.service import get_learner_state_service
    from deeptutor.services.luban_lesson.full_answer_grading import (
        FullAnswerNotAvailable,
        grade_full_answer,
    )

    try:
        return grade_full_answer(
            pack_id=pack_id,
            variant_id=payload.variant_id,
            answer_text=payload.answer_text,
            user_id=current_user.user_id,
            learner_state_service=get_learner_state_service(),
        )
    except (LessonNotAvailable, FullAnswerNotAvailable):
        raise HTTPException(status_code=404, detail="full answer grading not found")
