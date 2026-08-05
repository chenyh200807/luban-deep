"""复习到期投影——到期语义收权 revalidation_queue（双轮 §3 C4 / §6.1）。

此前 review 页用「有变体池=到期」的前端探测（假语义, 六站天天全到期）；本投影
只把 ``pack_lifecycle_projection`` 的 terminal-only review facts 桥接为 candidates，
再委托 ``revalidation_queue`` 决定到期。``exam_date_iso`` 仍只是地平线透传口；
本模块不保存 due、不维护间隔常量，也不解释 item/本机状态。

本投影是「到期复习」候选的**唯一**读侧真值：复习页（GET /review-due）、report
``pack_review`` 与首页 next_step 的 review_due 臂都必须从这里派生——首页不得
用弱点节点另铸第二套 due 候选（2026-07-20 双权威病收权）。
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from deeptutor.services.learner_state.pack_lifecycle_projection import (
    LIFECYCLE_UNLEARNED,
    project_pack_lifecycle,
)
from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    build_review_horizon_projection,
)
from deeptutor.services.luban_lesson.read_model import (
    LessonNotAvailable,
    build_lesson_viewmodel,
    list_green_lessons,
)

_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"


def review_module_enabled() -> bool:
    """复习面总旗标读点（与 /review-due 路由同一 os.getenv 口径）。

    首页 review_due 臂必须与复习页同门：旗标关时复习页 due 恒空，首页发
    review_due CTA 只会是兑付不了的死卡。
    """
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


class ReviewHorizonUnavailable(RuntimeError):
    """Canonical member-profile horizon could not be read."""


def resolve_review_exam_date(
    user_id: str,
    *,
    member_service: Any | None = None,
) -> str:
    """Read the review horizon from its sole authority without inventing a fallback."""
    if member_service is None:
        from deeptutor.services.member_console import get_member_console_service

        member_service = get_member_console_service()
    try:
        profile = member_service.get_profile(user_id)
    except Exception as exc:
        raise ReviewHorizonUnavailable("member_profile_unavailable") from exc
    if not isinstance(profile, dict):
        raise ReviewHorizonUnavailable("member_profile_unavailable")
    return str(profile.get("exam_date") or "").strip()


def build_review_due_projection(
    *,
    user_id: str,
    events: Iterable[Any] | None,
    now_iso: str = "",
    exam_date_iso: str = "",
    pack_lifecycle: dict[str, Any] | None = None,
    declined_probe_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    events = list(events or [])
    green = {row["pack_id"]: row for row in list_green_lessons()}
    packs = _lifecycle_packs(events=events, pack_lifecycle=pack_lifecycle)
    candidates = _pack_review_candidates(packs=packs, green=green)
    state_by_pack = {
        str(candidate["node_id"]).strip().upper(): str(candidate.get("state") or "")
        for candidate in candidates
    }
    # declined = 学员当日 defer 意志(计划 §3.3, revalidation_queue 既有机制,
    # 不另记状态)。caller 从含 learner_signal 行的事件流派生
    # (revalidation_queue.declined_probe_ids_from_events)后注入; 不注入 = 现行为。
    queue = build_revalidation_queue_projection(
        user_id=user_id,
        candidates=candidates,
        now_iso=now_iso,
        exam_date_iso=exam_date_iso,
        declined_probe_ids=declined_probe_ids,
    )
    due_items: list[dict[str, Any]] = []
    for item in list(queue.get("items") or []):
        intent = item.get("intent") or {}
        pack_id = str(intent.get("concept_id") or "").strip().upper()
        if pack_id not in green:
            continue
        try:
            vm = build_lesson_viewmodel(pack_id)
        except LessonNotAvailable:
            continue
        due_items.append(
            {
                "pack_id": pack_id,
                "title": green[pack_id]["title"],
                "probe_id": str(item.get("probe_id") or ""),
                "due_at": str(item.get("due_at") or ""),
                # 档位状态透传（不新建调度语义）：fresh=D+1 首验(归 anchor MCQ)、
                # weak/stable=D+3/D+7 抽查(变体探针候选)；调度真值仍归 revalidation_queue。
                "state": state_by_pack.get(pack_id, ""),
                "review_status": str((packs.get(pack_id) or {}).get("last_review_status") or ""),
                "successful_review_streak": int((packs.get(pack_id) or {}).get("successful_review_streak") or 0),
                "cycle_anchor": str((packs.get(pack_id) or {}).get("review_cycle_anchor") or ""),
                # False = 该站变体池未产(现状仅 2 池)——客户端必须 fail-closed
                # 隐藏"换皮"承诺句(禁对无池站承诺换皮复测)。
                "retest_available": bool(vm["variant_retest"]["available"]),
                # declined 机制透传(deferred=学员今日 defer): 展示层可见后果,
                # 兑付资格(resolve_due_review_probe)不受影响——defer 后当日回头
                # 补做仍可兑付,禁 fail-closed 藏卡。
                "probe_status": str(item.get("status") or ""),
                "next_available_at": str(item.get("next_available_at") or ""),
            }
        )
    return {
        "due": due_items,
        # 已学口径直接复用 pack_lifecycle；讲懂仅 exposed，canonical terminal 才
        # 产生 fresh/stable/weak 调度事实。
        "learned_count": sum(
            1
            for pack_id, entry in packs.items()
            if pack_id in green and str(entry.get("lifecycle_state") or "") != LIFECYCLE_UNLEARNED
        ),
        # 诚实旗标: 结论完整(读到了全部事件), 区别于旧探测的降级语义
        "authority": "revalidation_queue",
    }


def _lifecycle_packs(
    *,
    events: list[Any],
    pack_lifecycle: dict[str, Any] | None,
) -> dict[str, Any]:
    lifecycle = (
        pack_lifecycle
        if isinstance(pack_lifecycle, dict)
        else project_pack_lifecycle(events=events, claims=[])
    )
    packs = lifecycle.get("packs")
    return packs if isinstance(packs, dict) else {}


def _pack_review_candidates(
    *,
    packs: dict[str, Any],
    green: dict[str, Any],
) -> list[dict[str, Any]]:
    """pack 级复习候选桥接的唯一实现（当日投影与 7 天预报共用，禁复制第二份）。"""
    return [
        {
            "node_id": pack_id,
            "label": green[pack_id]["title"],
            "state": (
                "stable"
                if str(entry.get("last_review_status") or "") == "verified"
                else "weak"
                if str(entry.get("last_review_status") or "") == "not_verified"
                else "fresh"
            ),
            "ability_dimension": "code_application",
            "last_observed_at": str(entry.get("last_review_at") or entry.get("last_completion_at") or ""),
            "successful_review_streak": int(entry.get("successful_review_streak") or 0),
            "cycle_anchor": str(entry.get("review_cycle_anchor") or ""),
            "evidence_refs": list(entry.get("terminal_evidence_refs") or []),
        }
        for pack_id, entry in sorted(packs.items())
        if pack_id in green and str(entry.get("last_completion_at") or "")
    ]


def build_review_horizon(
    *,
    user_id: str,
    events: Iterable[Any] | None,
    now_iso: str = "",
    exam_date_iso: str = "",
    pack_lifecycle: dict[str, Any] | None = None,
    declined_probe_ids: Iterable[str] | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """pack 级 7 天到期预报——同一候选桥接（``_pack_review_candidates``），调度
    真值仍唯一归 ``revalidation_queue.build_review_horizon_projection``（计划体系
    §3.1 权威点 2：到期推算不许住在本模块）。本读面是预报（display），不做
    viewmodel/供给兑付过滤——CTA 兑付资格仍只归当日投影 + resolve 口径。"""
    events = list(events or [])
    green = {row["pack_id"]: row for row in list_green_lessons()}
    packs = _lifecycle_packs(events=events, pack_lifecycle=pack_lifecycle)
    return build_review_horizon_projection(
        user_id=user_id,
        candidates=_pack_review_candidates(packs=packs, green=green),
        now_iso=now_iso,
        exam_date_iso=exam_date_iso,
        declined_probe_ids=declined_probe_ids,
        days=days,
    )


def resolve_due_review_probe(
    projection: dict[str, Any],
    *,
    pack_id: str,
    probe_id: str,
) -> dict[str, Any] | None:
    """Resolve one exact, currently eligible probe from the due projection.

    This is deliberately a projection reader, not another scheduler: due state and
    cycle identity remain owned by ``revalidation_queue``.  Both selection issuance
    and completion verification use this same exact-match rule.
    """
    normalized_pack = str(pack_id or "").strip().upper()
    normalized_probe = str(probe_id or "").strip()
    if not normalized_pack or not normalized_probe:
        return None
    for item in list(projection.get("due") or []):
        if not isinstance(item, dict):
            continue
        if (
            str(item.get("pack_id") or "").strip().upper() == normalized_pack
            and str(item.get("probe_id") or "").strip() == normalized_probe
            and item.get("retest_available") is True
            and str(item.get("cycle_anchor") or "").strip()
        ):
            return dict(item)
    return None


def list_redeemable_due_items(projection: dict[str, Any]) -> list[dict[str, Any]]:
    """Due items that selection/completion would actually redeem, in due order.

    资格判据只存在 ``resolve_due_review_probe`` 一份（exact-match:
    pack_id+probe_id+retest_available+cycle_anchor）——本函数逐条委托它过滤，
    不复制口径。首页 next_step 的 review_due 臂只许消费本列表：发出的每个
    probe 必然能被复习入口原样兑付（禁发死 CTA）。

    附加一条**展示侧**过滤（非兑付资格）：``probe_status == "deferred"``
    （学员今日 defer 意志，declined 机制）不进首页/计划 CTA——意志被尊重，
    不再当天顶回学员脸上；复习入口兑付不受影响（defer 后回头补做仍可完成）。
    """
    redeemable: list[dict[str, Any]] = []
    for item in list(projection.get("due") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("probe_status") or "") == "deferred":
            continue
        resolved = resolve_due_review_probe(
            projection,
            pack_id=str(item.get("pack_id") or ""),
            probe_id=str(item.get("probe_id") or ""),
        )
        if resolved is not None:
            redeemable.append(resolved)
    return redeemable


__all__ = [
    "ReviewHorizonUnavailable",
    "build_review_due_projection",
    "build_review_horizon",
    "list_redeemable_due_items",
    "resolve_due_review_probe",
    "resolve_review_exam_date",
    "review_module_enabled",
]
