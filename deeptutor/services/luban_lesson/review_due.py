"""复习到期投影——到期语义收权 revalidation_queue（双轮 §3 C4 / §6.1）。

此前 review 页用「有变体池=到期」的前端探测（假语义, 六站天天全到期）；本投影
把到期判定收回唯一调度权威：站完成事件（learner_signal ``station_completed``,
concept_id=pack_id）作为 candidates 注入 ``build_revalidation_queue_projection``
（其公开注入口）, 复用其 ``_is_due``/日容量语义——新学相(fresh)首跳次日 =
交接时刻「明天见」的兑现。``exam_date_iso`` 是 §6.1 地平线参数的透传口（压缩/
cap 逻辑仍全在 revalidation_queue, 本模块零调度逻辑, 防第二调度器）, 只做:
① 事件→pack 级 candidate 的粒度桥接; ② 到期结果 join 投影门绿灯+变体池。
"""
from __future__ import annotations

from typing import Any, Iterable

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
)
from deeptutor.services.luban_lesson.read_model import (
    LessonNotAvailable,
    build_lesson_viewmodel,
    list_green_lessons,
)

_SIGNAL_TYPE = "station_completed"


def _station_completions(events: Iterable[Any]) -> dict[str, str]:
    """station_completed 事件 → {pack_id: 最新完成时间 iso}。"""
    latest: dict[str, str] = {}
    for event in list(events or []):
        payload = getattr(event, "payload_json", None) or {}
        if not isinstance(payload, dict):
            continue
        if str(payload.get("learning_signal_type") or "").strip() != _SIGNAL_TYPE:
            continue
        pack_id = str(payload.get("concept_id") or "").strip().upper()
        if not pack_id:
            continue
        observed = str(getattr(event, "created_at", "") or "").strip()
        if observed > latest.get(pack_id, ""):
            latest[pack_id] = observed
    return latest


def build_review_due_projection(
    *,
    user_id: str,
    events: Iterable[Any] | None,
    now_iso: str = "",
    exam_date_iso: str = "",
) -> dict[str, Any]:
    completions = _station_completions(events or [])
    green = {row["pack_id"]: row for row in list_green_lessons()}
    candidates = [
        {
            "node_id": pack_id,
            "label": green[pack_id]["title"],
            "state": "fresh",  # 新学相: 首跳次日(交接时刻"明天见")
            "ability_dimension": "",
            "last_observed_at": observed_at,
        }
        for pack_id, observed_at in sorted(completions.items())
        if pack_id in green  # 投影门: 只有绿灯站可进复测
    ]
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
                # False = 该站变体池未产(现状仅 2 池)——客户端必须 fail-closed
                # 隐藏"换皮"承诺句(禁对无池站承诺换皮复测)。
                "retest_available": bool(vm["variant_retest"]["available"]),
            }
        )
    return {
        "due": due_items,
        "learned_count": len([p for p in completions if p in green]),
        # 诚实旗标: 结论完整(读到了全部事件), 区别于旧探测的降级语义
        "authority": "revalidation_queue",
    }


__all__ = ["build_review_due_projection"]
