"""复习到期投影——到期语义收权 revalidation_queue（双轮 §3 C4 / §6.1）。

此前 review 页用「有变体池=到期」的前端探测（假语义, 六站天天全到期）；本投影
只把 ``pack_lifecycle_projection`` 的 terminal-only review facts 桥接为 candidates，
再委托 ``revalidation_queue`` 决定到期。``exam_date_iso`` 仍只是地平线透传口；
本模块不保存 due、不维护间隔常量，也不解释 item/本机状态。
"""
from __future__ import annotations

from typing import Any, Iterable

from deeptutor.services.learner_state.pack_lifecycle_projection import (
    LIFECYCLE_UNLEARNED,
    project_pack_lifecycle,
)
from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
)
from deeptutor.services.luban_lesson.read_model import (
    LessonNotAvailable,
    build_lesson_viewmodel,
    list_green_lessons,
)


def build_review_due_projection(
    *,
    user_id: str,
    events: Iterable[Any] | None,
    now_iso: str = "",
    exam_date_iso: str = "",
) -> dict[str, Any]:
    events = list(events or [])
    green = {row["pack_id"]: row for row in list_green_lessons()}
    lifecycle = project_pack_lifecycle(events=events, claims=[])
    packs = lifecycle.get("packs") if isinstance(lifecycle.get("packs"), dict) else {}
    candidates = [
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
    state_by_pack = {
        str(candidate["node_id"]).strip().upper(): str(candidate.get("state") or "")
        for candidate in candidates
    }
    queue = build_revalidation_queue_projection(
        user_id=user_id, candidates=candidates, now_iso=now_iso, exam_date_iso=exam_date_iso
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


__all__ = ["build_review_due_projection", "resolve_due_review_probe"]
