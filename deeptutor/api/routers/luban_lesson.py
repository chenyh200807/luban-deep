"""鲁班站点卡 lesson viewmodel 路由（认证）——双轮 §7 投影门的 runtime 入口。

与 ``luban_preview``（匿名、单卡沙盒）的分界：本路由走 ``secure_router`` 默认
鉴权，只投影 manifest 绿灯包；未签发/不存在一律 404 同形（fail-closed）。
读侧只投影签发内容；复测完成写侧统一委托 RetestWritebackService，由服务端重判后
一次提交 completion terminal 与 station_completed，不接受客户端自报学情结论。
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
    list_all_pack_ids,
    list_lesson_catalog,
    retest_pool_meta,
    retest_supply_identity,
)
from deeptutor.services.luban_lesson.practice_html import (
    PracticeHtmlInvalid,
    compiled_practice_pool_meta,
    is_compiled_practice_pack,
)
from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
from deeptutor.services.luban_lesson.review_due import (
    build_review_due_projection,
    resolve_due_review_probe,
)
from deeptutor.services.session import get_sqlite_session_store

router = secure_router(tags=["luban_lesson"])


class RetestAnswerRequest(BaseModel):
    variant_id: str
    choice_ok: bool | None = None
    selected_option_id: str = ""


class RetestCompletionRequest(BaseModel):
    completion_id: str
    selection_id: str
    mode: str = "review"
    day_index: int
    answers: list[RetestAnswerRequest] = Field(min_length=1, max_length=10)
    training_intent_id: str = ""
    probe_id: str = ""


class CardEntryResponse(BaseModel):
    """A narrow, short-lived H5 capability — never a reusable user bearer token."""

    entry_ticket: str
    expires_in_seconds: int


@router.get(
    "/lessons",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_list", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def lessons(_: AuthContext = Depends(get_current_user)) -> dict:
    light_enabled = _review_module_enabled() and _light_practice_enabled()
    green_lessons, teaching_points = list_lesson_catalog()
    teaching_topic_universe = len(
        {str(point.get("pack_id") or "") for point in teaching_points}
    )
    return {
        # 总站数由 manifest 唯一枚举；客户端不得继续维护 40/41 的镜像常量。
        "pack_universe": len(list_all_pack_ids()),
        # 教学集从已发布 lesson*.html 只读投影；它不是第二套学习/练习生命周期。
        "teaching_point_universe": len(teaching_points),
        "teaching_topic_universe": teaching_topic_universe,
        "teaching_points": teaching_points,
        "lessons": [
            {
                **row,
                "light_practice_available": light_enabled and row.get("retest_available") is True,
            }
            for row in green_lessons
        ]
    }


@router.get(
    "/lessons/{pack_id}",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_detail", default_max_requests=60, default_window_seconds=60.0))
    ],
)
async def lesson_detail(
    pack_id: str,
    episode: int = 1,
    _: AuthContext = Depends(get_current_user),
) -> dict:
    try:
        return build_lesson_viewmodel(pack_id, episode_index=episode)
    except LessonNotAvailable:
        raise HTTPException(status_code=404, detail="lesson not found")


@router.post(
    "/lessons/{pack_id}/card-entry",
    response_model=CardEntryResponse,
    dependencies=[
        Depends(route_rate_limit("luban_lesson_card_entry", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def issue_card_entry(
    pack_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> CardEntryResponse:
    """Bridge one authenticated station into its hosted H5 card.

    The browser card needs a narrowly scoped capability because a WeChat
    ``web-view`` cannot safely receive the Mini Program's bearer credential.
    Availability stays with ``build_lesson_viewmodel``; ticket ownership stays
    with the authenticated user and the session store is its sole persistence.
    """
    try:
        viewmodel = build_lesson_viewmodel(pack_id)
    except LessonNotAvailable as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    if not str(viewmodel.get("card_url") or "").strip():
        raise HTTPException(status_code=404, detail="lesson card not found")
    ticket = await get_sqlite_session_store().issue_luban_card_entry_ticket(
        user_id=current_user.user_id,
        pack_id=str(viewmodel.get("pack_id") or pack_id),
    )
    return CardEntryResponse(entry_ticket=ticket, expires_in_seconds=45 * 60)


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
    practice_surface: str = "",
    probe_id: str = "",
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    """题面投影（同一 endpoint / 同一 completion authority）：
    - ``mode=review``（默认，复习轮换皮复测）；
    - ``mode=forward``（学习轮课后轻练；已编译 pack 从 finished HTML 私有题池取五题）。
      completion 均由服务端重判；forward 非 promoting。

    未识别的 mode 归一为 review（thin 归一，不新增第二 builder/第二端点）。
    """
    from datetime import datetime, timedelta, timezone

    # §9-D2: "天"按服务端 UTC+8 日历日折算, 客户端不自算
    now = datetime.now(timezone(timedelta(hours=8)))
    day_index = now.year * 1000 + now.timetuple().tm_yday
    mode = "forward" if str(mode or "").strip().lower() == "forward" else "review"
    if not _review_module_enabled() or (mode == "forward" and not _light_practice_enabled()):
        raise HTTPException(status_code=404, detail="retest not available")
    selection_probe = ""
    cycle_anchor = ""
    if mode == "review":
        selection_probe = str(probe_id or "").strip()
        if not selection_probe:
            raise HTTPException(status_code=400, detail="retest_probe_id_required")
        from deeptutor.services.learner_state.service import get_learner_state_service

        learner_state = get_learner_state_service()
        events = learner_state.list_learning_evidence_events(
            current_user.user_id,
            limit=None,
            since=None,
        )
        due_projection = build_review_due_projection(
            user_id=current_user.user_id,
            events=events,
            exam_date_iso=_exam_date_for(current_user.user_id),
        )
        due_probe = resolve_due_review_probe(
            due_projection,
            pack_id=pack_id,
            probe_id=selection_probe,
        )
        if due_probe is None:
            raise HTTPException(status_code=400, detail="retest_probe_not_due")
        cycle_anchor = str(due_probe.get("cycle_anchor") or "").strip()
    try:
        items = build_retest_items(
            pack_id,
            user_id=current_user.user_id,
            day_index=day_index,
            limit=limit,
            mode=mode,
            practice_surface=practice_surface,
        )
    except (LessonNotAvailable, PracticeHtmlInvalid):
        raise HTTPException(status_code=404, detail="lesson not found")
    compiled_registered = mode == "forward" and is_compiled_practice_pack(pack_id)
    if compiled_registered and not items:
        raise HTTPException(status_code=404, detail="compiled practice unavailable")
    compiled_forward = compiled_registered
    compiled_pool = (
        compiled_practice_pool_meta(pack_id, surface_id=practice_surface)
        if compiled_forward
        else None
    )
    supply = retest_supply_identity(pack_id, mode=mode)
    if not supply.get("kind") or not supply.get("digest"):
        raise HTTPException(status_code=404, detail="retest supply unavailable")
    return {
        "pack_id": pack_id.upper(),
        "items": items,
        "day_index": day_index,
        "mode": mode,
        "selection_id": issue_retest_selection(
            user_id=current_user.user_id,
            pack_id=pack_id,
            day_index=day_index,
            mode=mode,
            variant_ids=[str(item.get("variant_id") or "") for item in items],
            supply_kind=supply["kind"],
            supply_digest=supply["digest"],
            probe_id=selection_probe,
            cycle_anchor=cycle_anchor,
        ),
        "pool": compiled_pool
        if compiled_forward
        else retest_pool_meta(pack_id),
        "practice_source": "compiled_html" if compiled_forward else "signed_variant",
    }


@router.post(
    "/lessons/{pack_id}/retest-complete",
    dependencies=[
        Depends(route_rate_limit("luban_lesson_retest_complete", default_max_requests=20, default_window_seconds=60.0))
    ],
)
async def retest_complete(
    pack_id: str,
    body: RetestCompletionRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    from deeptutor.services.learner_state.service import get_learner_state_service
    from deeptutor.services.luban_lesson.retest_writeback import (
        RetestCompletionInProgress,
        RetestIdempotencyConflict,
        RetestProbeClaimUnavailable,
        RetestWritebackService,
    )

    try:
        return RetestWritebackService(
            learner_state_service=get_learner_state_service(),
            review_exam_date_resolver=_exam_date_for,
        ).complete(
            user_id=current_user.user_id,
            completion_id=body.completion_id,
            selection_id=body.selection_id,
            pack_id=pack_id,
            mode=body.mode,
            day_index=body.day_index,
            answers=[item.model_dump() for item in body.answers],
            training_intent_id=body.training_intent_id,
            probe_id=body.probe_id,
        )
    except RetestIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="retest completion conflict") from exc
    except RetestCompletionInProgress as exc:
        raise HTTPException(status_code=409, detail="retest completion in progress") from exc
    except RetestProbeClaimUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="retest probe atomic authority unavailable",
        ) from exc
    except LessonNotAvailable as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# 复习模块灰度旗标（register-before-use: contracts/env_registry.yaml + .env.example）。
# 关 = 空投影（fail-closed 空清单, 页面走诚实空态）, 不 404——路由形状稳定。
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_LIGHT_PRACTICE_FLAG = "LUBAN_LIGHT_PRACTICE_ENABLED"


def _review_module_enabled() -> bool:
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _light_practice_enabled() -> bool:
    return str(os.getenv(_LIGHT_PRACTICE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


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
    events = get_learner_state_service().list_learning_evidence_events(
        current_user.user_id, limit=None, since=None
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
