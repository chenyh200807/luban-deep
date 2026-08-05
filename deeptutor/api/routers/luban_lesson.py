"""鲁班站点卡 lesson viewmodel 路由（认证）——双轮 §7 投影门的 runtime 入口。

与 ``luban_preview``（匿名、单卡沙盒）的分界：本路由走 ``secure_router`` 默认
鉴权，只投影 manifest 绿灯包；未签发/不存在一律 404 同形（fail-closed）。
读侧只投影签发内容；复测完成写侧统一委托 RetestWritebackService，由服务端重判后
一次提交 completion terminal 与 station_completed，不接受客户端自报学情结论。
"""
from __future__ import annotations

import asyncio
import os

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.learner_state.evidence_lifecycle import (
    validate_immediate_confirm_parent,
)
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
    decode_projection_receipt,
    is_compiled_practice_pack,
)
from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
from deeptutor.services.luban_lesson.review_due import (
    ReviewHorizonUnavailable,
    build_review_due_projection,
    resolve_due_review_probe,
    resolve_review_exam_date,
)
from deeptutor.services.luban_lesson.variant_eligibility import (
    build_variant_probe_items,
    variant_probe_fact_ids,
    variant_probe_supply_identity,
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


class CardEntryRequest(BaseModel):
    episode: int = Field(default=1, ge=1, le=100)


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
    payload: CardEntryRequest | None = None,
    current_user: AuthContext = Depends(get_current_user),
) -> CardEntryResponse:
    """Bridge one authenticated station into its hosted H5 card.

    The browser card needs a narrowly scoped capability because a WeChat
    ``web-view`` cannot safely receive the Mini Program's bearer credential.
    Availability stays with ``build_lesson_viewmodel``; ticket ownership stays
    with the authenticated user and the session store is its sole persistence.
    """
    try:
        viewmodel = build_lesson_viewmodel(
            pack_id,
            episode_index=(payload or CardEntryRequest()).episode,
        )
    except LessonNotAvailable as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    if not str(viewmodel.get("card_url") or "").strip():
        raise HTTPException(status_code=404, detail="lesson card not found")
    ticket = await get_sqlite_session_store().issue_luban_card_entry_ticket(
        user_id=current_user.user_id,
        pack_id=str(viewmodel.get("pack_id") or pack_id),
        resource_id=str(viewmodel.get("teaching_point_id") or ""),
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
    projection_receipt: str = "",
    probe_id: str = "",
    confirm_facts: str = "",
    confirm_anchor: str = "",
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    """题面投影（同一 endpoint / 同一 completion authority）：
    - ``mode=review``（默认，复习轮换皮复测）；
    - ``mode=forward``（学习轮课后轻练；已编译 pack 从 finished HTML 私有题池取五题）。
      completion 均由服务端重判；forward 非 promoting。
    - ``projection_receipt``（H5 receipt bridge，仅 compiled forward）：选题严格
      解析到客户所见题集并原样回显；与当前供给漂移（重签/撤销/篡改）→
      409 ``content_updated_retake`` 要求整卷重取，绝不按 index 重映射。

    未识别的 mode 归一为 review（thin 归一，不新增第二 builder/第二端点）。
    """
    # 同款「同步阻塞全家桶」：整段 body 无 await，却做 list_learning_evidence_events /
    # build_review_due_projection / build_variant_probe_items / build_retest_items 等
    # 多次同步 Supabase 往返。半修 retest_complete 而放任此 load 路径，事件循环仍被
    # 阻塞。按同一惯例把纯同步内核丢线程池，参数显式传入（避免闭包内 `mode` 重赋值
    # 触发 UnboundLocalError），行为逐字节不变。
    return await asyncio.to_thread(
        _retest_items_sync,
        pack_id,
        limit,
        mode,
        practice_surface,
        projection_receipt,
        probe_id,
        confirm_facts,
        confirm_anchor,
        current_user,
    )


def _retest_items_sync(
    pack_id: str,
    limit: int,
    mode: str,
    practice_surface: str,
    projection_receipt: str,
    probe_id: str,
    confirm_facts: str,
    confirm_anchor: str,
    current_user: AuthContext,
) -> dict:
    """题面投影同步内核——由 ``retest_items`` 经 ``asyncio.to_thread`` 调度执行。

    抽出的全部是原 ``retest_items`` body（逐字节不变）；HTTPException 在线程内抛出
    经 ``to_thread`` 原样传回路由并出栈。拆成模块级具名函数（非闭包）以便所有依赖仍
    以裸名从模块全局解析——既有 monkeypatch 测试不受影响。"""
    from datetime import datetime, timedelta, timezone

    # §9-D2: "天"按服务端 UTC+8 日历日折算, 客户端不自算
    now = datetime.now(timezone(timedelta(hours=8)))
    day_index = now.year * 1000 + now.timetuple().tm_yday
    mode = "forward" if str(mode or "").strip().lower() == "forward" else "review"
    if not _review_module_enabled() or (mode == "forward" and not _light_practice_enabled()):
        raise HTTPException(status_code=404, detail="retest not available")
    selection_probe = ""
    cycle_anchor = ""
    review_state = ""
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
        try:
            due_projection = build_review_due_projection(
                user_id=current_user.user_id,
                events=events,
                exam_date_iso=_exam_date_for(current_user.user_id),
            )
        except ReviewHorizonUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="review horizon member profile unavailable",
            ) from exc
        due_probe = resolve_due_review_probe(
            due_projection,
            pack_id=pack_id,
            probe_id=selection_probe,
        )
        if due_probe is None:
            raise HTTPException(status_code=400, detail="retest_probe_not_due")
        cycle_anchor = str(due_probe.get("cycle_anchor") or "").strip()
        review_state = str(due_probe.get("state") or "").strip()

    # ---- 变体判断题消费接线（切片三，两点都 gate LUBAN_VARIANT_PROBE_ENABLED）----
    # 供给唯一权威 = build_variant_probe_items → resolve_variant_supply（绿灯签发闸）；
    # selection 以 variant_probe_supply_identity 签发（writeback 按 token 的 supply_kind
    # 分派）。任一环不满足 → forward confirm 404 同形 / review 退 compiled MCQ 不空窗。
    confirm_facts_raw = str(confirm_facts or "").strip()
    # Intent 与 availability 必须分开：confirm URL 一旦携 facts 就只能是
    # immediate-confirm；灰度关闭/供给撤回必须 fail-close，绝不能降级成普通
    # compiled forward 后重开一个 episode。
    confirm_requested = mode == "forward" and bool(confirm_facts_raw)
    variant_items: list[dict] | None = None
    variant_probe_role = ""
    if _variant_probe_enabled():
        if confirm_requested:
            # 消费点1：错后当场确认（immediate_confirm；facts = 客户端传的错题 facts，≤5）。
            facts = [f.strip() for f in confirm_facts_raw.split(",") if f.strip()][:5]
            requested_parent = str(confirm_anchor or "").strip()
            if not requested_parent:
                raise HTTPException(
                    status_code=400, detail="retest_confirm_anchor_required"
                )
            from deeptutor.services.learner_state.service import (
                get_learner_state_service,
            )

            confirm_events = get_learner_state_service().list_learning_evidence_events(
                current_user.user_id,
                limit=None,
                since=None,
            )
            if not validate_immediate_confirm_parent(
                confirm_events,
                pack_id=pack_id,
                parent_terminal_id=requested_parent,
                fact_ids=facts,
            ):
                raise HTTPException(
                    status_code=400, detail="retest_confirm_parent_invalid"
                )
            cycle_anchor = requested_parent
            picked = build_variant_probe_items(
                pack_id,
                user_id=current_user.user_id,
                day_index=day_index,
                probe_role="immediate_confirm",
                fact_ids=facts,
                limit=5,
            )
            if picked:
                variant_items, variant_probe_role = picked, "immediate_confirm"
        elif mode == "review" and review_state in {"weak", "stable"}:
            # 消费点2：D+3/D+7 抽查（d1_probe）；fresh(D+1 首验) 恒走 anchor MCQ。
            picked = build_variant_probe_items(
                pack_id,
                user_id=current_user.user_id,
                day_index=day_index,
                probe_role="d1_probe",
                limit=5,
            )
            if picked:
                variant_items, variant_probe_role = picked, "d1_probe"

    if variant_items is not None:
        variant_supply = variant_probe_supply_identity(pack_id)
        if not variant_supply.get("kind") or not variant_supply.get("digest"):
            variant_items = None  # 供给闸不过 → 退（forward confirm 见下 404）
    if confirm_requested and variant_items is None:
        # confirm 请求了但无法服务（旗标关/供给空/无交集）→ 404 同形（fail-closed）。
        raise HTTPException(status_code=404, detail="retest not available")
    if variant_items is not None:
        return {
            "pack_id": pack_id.upper(),
            "items": variant_items,
            "day_index": day_index,
            "mode": mode,
            "selection_id": issue_retest_selection(
                user_id=current_user.user_id,
                pack_id=pack_id,
                day_index=day_index,
                mode=mode,
                variant_ids=[str(item.get("variant_id") or "") for item in variant_items],
                supply_kind=variant_supply["kind"],
                supply_digest=variant_supply["digest"],
                probe_id=selection_probe,
                cycle_anchor=cycle_anchor,
            ),
            "pool": None,
            "practice_source": "signed_variant",
            "variant_probe_role": variant_probe_role,
        }

    projection_receipt = str(projection_receipt or "").strip()
    try:
        items = build_retest_items(
            pack_id,
            user_id=current_user.user_id,
            day_index=day_index,
            limit=limit,
            mode=mode,
            practice_surface=practice_surface,
            projection_receipt=projection_receipt,
        )
    except PracticeHtmlInvalid as exc:
        code = str(exc)
        if code == "content_updated_retake":
            # receipt 与当前供给漂移（重签/撤销/篡改）——语义错误要求客户端
            # 整卷重取；服务端绝不按 index 重映射或静默换题。
            raise HTTPException(
                status_code=409, detail={"error": "content_updated_retake"}
            ) from exc
        if code == "practice_not_released":
            # 练习供给尚未签发发布（教研节奏问题，非用户侧数据漂移）。用独立
            # 错误码回传，让前端给出"练习还在签发中，先看讲解"暖文案，绝不
            # 冒充 content_updated_retake 误导用户去"重做已更新的题"。
            raise HTTPException(
                status_code=409, detail={"error": "practice_not_released"}
            ) from exc
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except LessonNotAvailable:
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
    response = {
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
    if mode == "forward" and compiled_forward:
        # 前端据此决定错后是否亮「当场确认」入口（旗标关/供给空 → 空列表 = 不亮）。
        response["confirm_facts_ready"] = _confirm_facts_ready(pack_id)
    if projection_receipt:
        # 桥接契约：客户端要求响应 receipt 与桥接值逐字节相等（retest.js）。
        # 只回显、不重签——builder 解析成功即证明该 token 仍锚定当前供给。
        response["projection_receipt"] = projection_receipt
        response["projection_digest"] = decode_projection_receipt(
            projection_receipt
        )["projection_digest"]
    return response


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

    def _run_complete() -> dict:
        # 服务端统一重判 + 写 terminal 学习证据是 8~15 次同步 Supabase 往返的阻塞
        # I/O（三结构病之一「同步阻塞全家桶」）。整段无 await，直接内联会霸占事件
        # 循环线程 → 并发天花板 → 撞前端 15s 死线。按仓库既有惯例把纯同步可调用体
        # 丢到线程池（rate_limit.py:102-107 / luban_preview 同款），事件循环得以并发
        # 服务其它请求；complete() 内部的原子幂等 claim + 确定性 event_id 保证并发正确性。
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

    try:
        return await asyncio.to_thread(_run_complete)
    except RetestIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="retest completion conflict") from exc
    except RetestCompletionInProgress as exc:
        raise HTTPException(status_code=409, detail="retest completion in progress") from exc
    except RetestProbeClaimUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="retest probe atomic authority unavailable",
        ) from exc
    except ReviewHorizonUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="review horizon member profile unavailable",
        ) from exc
    except LessonNotAvailable as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# 复习模块灰度旗标（register-before-use: contracts/env_registry.yaml + .env.example）。
# 关 = 空投影（fail-closed 空清单, 页面走诚实空态）, 不 404——路由形状稳定。
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_LIGHT_PRACTICE_FLAG = "LUBAN_LIGHT_PRACTICE_ENABLED"
# 变体判断题消费接线灰度(register-before-use: contracts/env_registry.yaml + .env.example)。
# 关 = 两消费点全走现行为(confirm 入口不亮 / review 退 compiled MCQ)。
_VARIANT_PROBE_FLAG = "LUBAN_VARIANT_PROBE_ENABLED"


def _review_module_enabled() -> bool:
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _light_practice_enabled() -> bool:
    return str(os.getenv(_LIGHT_PRACTICE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _variant_probe_enabled() -> bool:
    return str(os.getenv(_VARIANT_PROBE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _confirm_facts_ready(pack_id: str) -> list[str]:
    """immediate_confirm 变体供给就绪的 fact 集合（前端据此决定错后是否亮
    「当场确认」入口）。供给唯一权威 = resolve_variant_supply（绿灯签发闸）；
    旗标关 / 供给任一闸不过 → 空列表（fail-closed，入口不亮）。"""
    if not _variant_probe_enabled():
        return []
    return sorted(variant_probe_fact_ids(pack_id, probe_role="immediate_confirm"))


def _exam_date_for(user_id: str) -> str:
    """§6.1 地平线参数: exam_date 唯一读源 = member profile（不复制真值）。
    未设置是已知空值；读取失败由 domain error fail-close。"""
    return resolve_review_exam_date(user_id)


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
    try:
        projection = build_review_due_projection(
            user_id=current_user.user_id,
            events=events,
            exam_date_iso=_exam_date_for(current_user.user_id),
        )
    except ReviewHorizonUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="review horizon member profile unavailable",
        ) from exc
    projection["enabled"] = True
    return projection


@router.get(
    "/exam-prep-plan",
    dependencies=[
        Depends(route_rate_limit("luban_exam_prep_plan", default_max_requests=30, default_window_seconds=60.0))
    ],
)
async def exam_prep_plan(current_user: AuthContext = Depends(get_current_user)) -> dict:
    """备考计划投影（计划页/跑道视图）——薄包装，零业务逻辑进 router。

    组装唯一入口 = MemberConsoleService composition root
    （``_assemble_home_plan_inputs`` → ``build_exam_prep_plan_projection``），
    本端点只做鉴权 + 线程池转发 + 投影原样透传；flag off 返回
    ``{"enabled": false}``（前端隐藏入口，不 404）。
    """
    from fastapi.concurrency import run_in_threadpool

    from deeptutor.services.member_console import get_member_console_service

    return await run_in_threadpool(
        get_member_console_service().get_exam_prep_plan, current_user.user_id
    )


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
