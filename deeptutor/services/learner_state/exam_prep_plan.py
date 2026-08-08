"""exam_prep_plan_projection——7 天滚动备考计划读投影（AI 学习计划体系计划 §3.1）。

**这不是第二处方、第二调度器、第二学序。** 它是既有学情权威（证据、处方、复习
调度、学序、供给）的展开投影 + 学员意志叠加，零自有存储、零 IO：全部输入由
caller（composition root，见 member_console `_build_home_next_step`）注入，仿照
``home_next_step_projection`` 的纯函数风格。

单一权威接线（计划 §3.1 三个权威点）：

- **今日首任务仲裁不复制**：day 0 的首任务直接消费
  ``build_home_next_step_projection``（四臂仲裁唯一实现）的输出——四臂语义
  （review_due 臂优先占位 > practice_active 承接 > learn_next 学序推进 >
  learn_fallback）在计划内逐字段保留。flag on ∧ 无 plan_preference 时，
  计划首任务与旧四臂输出**逐字段相等**（shadow parity，机器验收）。
- **到期日期只准消费 horizon 读面**：未来天的复习任务来自
  ``revalidation_queue.build_review_horizon_projection`` 的输出（caller 注入），
  本模块绝不拿 due_at 自行外推。
- **学序权威**：``order_packs_with_prerequisites``（registry + 前置边）。

排序政策（计划 §3.2，确定性、版本化 ``PLAN_POLICY_VERSION``）::

    gap 排序 = 预期丢分 × 考频/重要度权重 × 证据置信度 × 短期可补性 ÷ 预期学习时长
    日程分配 = 排序结果 × 每日时间预算 × revalidation_queue 到期约束(复习优先占位)

v1 因子说明（诚实版）：考频/丢分资产尚未接线，各任务族先用文档化常量
（``_GAP_FACTORS``）；因子变更必须 bump ``PLAN_POLICY_VERSION``。

学员意志（plan_preference，§3.3）作用于**排序与日程**，绝不动证据结论：
pin 提前（红线：不静默覆盖，冲突时带后果说明）；defer 后移一天（复习任务的
defer 已在上游 declined 机制生效，不在本层重复处理）；time_budget 重排日程
密度、不缩减单任务完整性。

铁律：禁写 ledger、禁生成/修改 training_intent、禁改 revalidation 状态、
禁排无 published 供给的任务（供给不足进 ``supply_gaps`` 反哺教研，不排假任务）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from deeptutor.services.learner_state.home_next_step_projection import (
    MODE_FALLBACK,
    MODE_LEARN,
    MODE_PRACTICE,
    MODE_REVIEW,
    build_home_next_step_projection,
)
from deeptutor.services.learner_state.pack_lifecycle_projection import (
    LIFECYCLE_UNLEARNED,
)
from deeptutor.services.taxonomy.construction_learning_graph import (
    order_packs_with_prerequisites,
)

_TZ = timezone(timedelta(hours=8))

PLAN_POLICY_VERSION = "exam_prep_plan_policy_v2"

# §3.2 v1 因子常量（占位真值来源见模块 docstring；改动必须 bump 版本号）。
# (expected_loss, frequency_weight, evidence_confidence, recoverability, minutes)
_GAP_FACTORS: dict[str, tuple[float, float, float, float, int]] = {
    "review_probe": (0.8, 1.0, 0.9, 1.0, 5),
    "practice_retest": (0.7, 1.0, 0.7, 0.9, 8),
    "learn_station": (0.5, 1.0, 0.4, 1.0, 12),
}
_DEFAULT_DAILY_BUDGET_MINUTES = 30


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_iso(value: str) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    return parsed.astimezone(_TZ)


def plan_preferences_from_events(
    events: Iterable[Any] | None,
    *,
    now_iso: str = "",
) -> dict[str, Any]:
    """从事件流提取 plan_preference 意志（唯一写器=record_learner_signal）。

    - ``pins``：pin 信号的 concept_id（=pack_id），事件序去重；
    - ``deferred_targets``：**非复习任务**的当日 defer（无 probe_id；带 probe_id
      的复习 defer 由 declined 机制承载，本读面刻意不重复消费——单一落点）；
    - ``time_budget_minutes``：最后一条 time_budget 信号生效（0=未设置）。
    """
    now = _parse_iso(now_iso) or datetime.now(_TZ)
    today = now.astimezone(_TZ).date()
    pins: list[str] = []
    deferred_targets: list[str] = []
    time_budget_minutes = 0
    for ev in list(events or []):
        payload = ev.get("payload_json") if isinstance(ev, dict) else getattr(ev, "payload_json", None)
        if not isinstance(payload, dict):
            payload = ev if isinstance(ev, dict) else {}
        signal = _text(payload.get("learning_signal_type"))
        if signal not in {"pin", "defer", "time_budget"}:
            continue
        if signal == "pin":
            cid = _text(payload.get("concept_id")).upper()
            if cid and cid not in pins:
                pins.append(cid)
            continue
        if signal == "defer":
            if _text(payload.get("probe_id")):
                continue  # 复习 defer → declined 机制，单一落点
            created_raw = ev.get("created_at") if isinstance(ev, dict) else getattr(ev, "created_at", "")
            created = _parse_iso(str(created_raw or ""))
            if created is None or created.astimezone(_TZ).date() != today:
                continue
            cid = _text(payload.get("concept_id")).upper()
            if cid and cid not in deferred_targets:
                deferred_targets.append(cid)
            continue
        try:
            minutes = int(payload.get("time_budget_minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0:
            time_budget_minutes = minutes
    return {
        "pins": pins,
        "deferred_targets": deferred_targets,
        "time_budget_minutes": time_budget_minutes,
    }


def _gap_score(kind: str) -> float:
    loss, freq, confidence, recoverability, minutes = _GAP_FACTORS[kind]
    return (loss * freq * confidence * recoverability) / max(minutes, 1)


def _task(
    *,
    kind: str,
    mode: str,
    source_authority: str,
    source_ref: str,
    target_pack_id: str,
    reason: str,
    why: str,
    evidence_refs: list[str],
    completion_condition: str,
    retest_condition: str,
) -> dict[str, Any]:
    return {
        "task": kind,
        "mode": mode,
        "source_authority": source_authority,
        "source_ref": source_ref,
        "target_pack_id": target_pack_id,
        "reason": reason,
        "why": why,
        "evidence_refs": list(evidence_refs),
        "expected_time": _GAP_FACTORS[kind][4],
        "completion_condition": completion_condition,
        "retest_condition": retest_condition,
    }


def _review_task_from_due_item(item: dict[str, Any]) -> dict[str, Any]:
    pack_id = _text(item.get("pack_id")).upper()
    probe_id = _text(item.get("probe_id"))
    label = _text(item.get("title")) or "薄弱点"
    due_at = _text(item.get("due_at"))
    return _task(
        kind="review_probe",
        mode=MODE_REVIEW,
        source_authority="revalidation_queue",
        source_ref=probe_id,
        target_pack_id=pack_id,
        reason=f"到期复验：{label} 再看一眼就稳了",
        why=f"复习调度到期（{due_at[:10]}）：错过会遗忘回退，复验通过才升稳",
        evidence_refs=[ref for ref in list(item.get("evidence_refs") or []) if _text(ref)],
        completion_condition=f"review_probe_completed:{probe_id}",
        retest_condition="review_terminal_verified",
    )


def _review_task_from_horizon_item(item: dict[str, Any]) -> dict[str, Any] | None:
    intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
    pack_id = _text(intent.get("concept_id")).upper()
    probe_id = _text(item.get("probe_id"))
    if not pack_id or not probe_id:
        return None
    label = _text(intent.get("concept_label")) or pack_id
    due_at = _text(item.get("due_at"))
    task = _task(
        kind="review_probe",
        mode=MODE_REVIEW,
        source_authority="revalidation_queue",
        source_ref=probe_id,
        target_pack_id=pack_id,
        reason=f"到期复验：{label} 再看一眼就稳了",
        why=f"复习调度预报（{due_at[:10]} 到期）：间隔复习到点，复验通过才升稳",
        evidence_refs=[ref for ref in list(item.get("evidence_refs") or []) if _text(ref)],
        completion_condition=f"review_probe_completed:{probe_id}",
        retest_condition="review_terminal_verified",
    )
    if _text(item.get("status")) == "deferred":
        task["status"] = "deferred"
    return task


def _practice_task_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    intent_id = _text(intent.get("training_intent_id"))
    target = _text(intent.get("target_pack_id")).upper()
    label = _text(intent.get("concept_label")) or _text(intent.get("error_label")) or "你漏的采分点"
    return _task(
        kind="practice_retest",
        mode=MODE_PRACTICE,
        source_authority="training_intent",
        source_ref=intent_id,
        target_pack_id=target,
        reason=f"继续练：{label}，换个题面",
        why=f"处方未完成：{label} 的训练意图仍活跃，换皮复测闭环才算修复",
        evidence_refs=[ref for ref in list(intent.get("evidence_refs") or []) if _text(ref)],
        completion_condition=f"retest_completed:{target}",
        retest_condition="forward_terminal_committed",
    )


def _learn_task_from_station(pack_id: str, title: str, *, fallback: bool) -> dict[str, Any]:
    mode = MODE_FALLBACK if fallback else MODE_LEARN
    reason = (
        f"从这里开始：{title}（多数考生的第一站）"
        if fallback
        else f"下一站：{title}"
    )
    why = (
        "冷启动/全学完：registry 静态序起点（群体理由，不伪装个性化）"
        if fallback
        else "学序推进：registry 学序 + 前置边的下一未学站（学完次日进入复习调度）"
    )
    return _task(
        kind="learn_station",
        mode=mode,
        source_authority="pack_manifest.registry_order" if fallback else "pack_lifecycle_projection",
        source_ref=pack_id,
        target_pack_id=pack_id,
        reason=reason,
        why=why,
        evidence_refs=[],
        completion_condition=f"station_completed:{pack_id}",
        retest_condition="next_day_fresh_probe",
    )


def build_exam_prep_plan_projection(
    *,
    now_iso: str = "",
    days: int = 7,
    review_due_items: list[dict[str, Any]] | None,
    review_horizon: dict[str, Any] | None,
    active_training_intents: list[dict[str, Any]] | None,
    pack_lifecycle: dict[str, Any] | None,
    green_lessons: list[dict[str, Any]] | None,
    plan_preferences: dict[str, Any] | None = None,
    daily_target_minutes: int = _DEFAULT_DAILY_BUDGET_MINUTES,
    review_due_unavailable: bool = False,
) -> dict[str, Any]:
    """输出未来 ``days`` 天滚动任务序列（确定性：同输入同 now_iso 同计划）。"""
    now = _parse_iso(now_iso) or datetime.now(_TZ)
    today = now.astimezone(_TZ).date()
    horizon_days = max(1, int(days or 1))
    prefs = plan_preferences if isinstance(plan_preferences, dict) else {}
    pins = [_text(p).upper() for p in list(prefs.get("pins") or []) if _text(p)]
    deferred_targets = {
        _text(p).upper() for p in list(prefs.get("deferred_targets") or []) if _text(p)
    }
    budget_minutes = int(prefs.get("time_budget_minutes") or 0) or max(
        1, int(daily_target_minutes or _DEFAULT_DAILY_BUDGET_MINUTES)
    )

    green = [
        item for item in list(green_lessons or [])
        if isinstance(item, dict) and _text(item.get("pack_id"))
    ]
    green_by_id = {_text(item.get("pack_id")).upper(): item for item in green}

    def _supply_ready(pack_id: str) -> bool:
        row = green_by_id.get(_text(pack_id).upper())
        return bool(row and row.get("retest_available"))

    # ── 今日首任务：四臂仲裁唯一实现，不复制（parity by construction）─────────
    next_step = build_home_next_step_projection(
        review_due_items=review_due_items,
        active_training_intents=active_training_intents,
        pack_lifecycle=pack_lifecycle,
        green_lessons=green_lessons,
        review_due_unavailable=review_due_unavailable,
    )

    # ── 任务池 ────────────────────────────────────────────────────────────────
    supply_gaps: list[dict[str, Any]] = []
    # 证据链富化：due 行不带 evidence_refs，从 horizon 读面同 probe 取（同一权威）。
    horizon_evidence: dict[str, list[str]] = {}
    for day in list((review_horizon or {}).get("days") or []):
        for item in list((day or {}).get("items") or []) if isinstance(day, dict) else []:
            if isinstance(item, dict) and _text(item.get("probe_id")):
                horizon_evidence[_text(item.get("probe_id"))] = [
                    ref for ref in list(item.get("evidence_refs") or []) if _text(ref)
                ]
    review_today = []
    for item in list(review_due_items or []):
        if not isinstance(item, dict) or not _text(item.get("probe_id")):
            continue
        task = _review_task_from_due_item(item)
        if not task["evidence_refs"]:
            task["evidence_refs"] = list(horizon_evidence.get(task["source_ref"], []))
        review_today.append(task)
    practice_pool: list[dict[str, Any]] = []
    for intent in list(active_training_intents or []):
        if not isinstance(intent, dict) or not _text(intent.get("training_intent_id")):
            continue
        target = _text(intent.get("target_pack_id")).upper()
        if not target or not _supply_ready(target):
            supply_gaps.append(
                {
                    "kind": "practice_retest",
                    "source_ref": _text(intent.get("training_intent_id")),
                    "target_pack_id": target,
                    "gap_reason": "practice_supply_unavailable" if target else "intent_without_pack_binding",
                }
            )
            continue
        practice_pool.append(_practice_task_from_intent(intent))
    # caller 注入序 = 处方 read-model 既有优先序（不在此重排：非第二处方）。

    packs = (pack_lifecycle or {}).get("packs") if isinstance(pack_lifecycle, dict) else {}
    packs = packs if isinstance(packs, dict) else {}

    def _state(pack_id: str) -> str:
        entry = packs.get(pack_id) if isinstance(packs.get(pack_id), dict) else {}
        return _text(entry.get("lifecycle_state"))

    ordered_ids = [_text(item.get("pack_id")) for item in green]
    titles = {_text(item.get("pack_id")): _text(item.get("title")) for item in green}
    unlearned = {pid for pid in ordered_ids if _state(pid) in ("", LIFECYCLE_UNLEARNED)}
    ordered_ids = order_packs_with_prerequisites(ordered_ids, unlearned_pack_ids=unlearned)
    unlearned_ordered = [pid for pid in ordered_ids if pid in unlearned]
    # 推荐起点一致性（与四臂同一规则，不造第二处方）：起点=第一个 supply_ready
    # 的未学站，无一 supply_ready 时回退路线第一个未学站；其余保持学序。
    learn_pool_ids: list[str] = []
    if unlearned_ordered:
        learn_pick = next(
            (pid for pid in unlearned_ordered if _supply_ready(pid)),
            unlearned_ordered[0],
        )
        learn_pool_ids = [learn_pick] + [pid for pid in unlearned_ordered if pid != learn_pick]
    learn_pool = [
        _learn_task_from_station(pid, titles.get(pid) or pid, fallback=False)
        for pid in learn_pool_ids
    ]
    if not learn_pool and green:
        # 全学完/冷启动：fallback 臂语义（registry 序第一绿灯站，群体理由）。
        first = next(
            (item for item in green if _supply_ready(_text(item.get("pack_id")))),
            green[0],
        )
        pid = _text(first.get("pack_id"))
        learn_pool = [_learn_task_from_station(pid, _text(first.get("title")) or pid, fallback=True)]

    # ── 未来天复习占位：只准消费 horizon 读面 ────────────────────────────────
    horizon_buckets: dict[int, list[dict[str, Any]]] = {}
    for day in list((review_horizon or {}).get("days") or []):
        if not isinstance(day, dict):
            continue
        offset = int(day.get("day_offset") or 0)
        if offset < 1 or offset >= horizon_days:
            continue
        tasks = []
        for item in list(day.get("items") or []):
            if not isinstance(item, dict):
                continue
            task = _review_task_from_horizon_item(item)
            if task is not None:
                tasks.append(task)
        if tasks:
            horizon_buckets[offset] = tasks

    # ── 日程分配（review 占位 → 意志 → gap 排序填充 × 时间预算）──────────────
    # policy_v2(owner 2026-08-08 拍板「别太线性」):practice/learn 轮转交错,
    # 族内各保权威序(处方序/学序)——打破整天同臂连排;首任务仍由四臂 parity
    # 合并裁决,不受交错影响。§3.2 gap 公式退役为族内参考,不再全池重排。
    backlog: list[dict[str, Any]] = []
    _pp, _lp = list(practice_pool), list(learn_pool)
    while _pp or _lp:
        if _pp:
            backlog.append(_pp.pop(0))
        if _lp:
            backlog.append(_lp.pop(0))

    def _is_deferred_target(task: dict[str, Any]) -> bool:
        return _text(task.get("target_pack_id")).upper() in deferred_targets

    def _is_pinned(task: dict[str, Any]) -> bool:
        return _text(task.get("target_pack_id")).upper() in set(pins)

    day_plans: list[dict[str, Any]] = []
    preference_applied = {"pin": 0, "defer": 0, "time_budget": int(prefs.get("time_budget_minutes") or 0)}
    deferred_backlog: list[dict[str, Any]] = []
    for offset in range(horizon_days):
        tasks: list[dict[str, Any]] = []
        planned = 0
        reviews = review_today if offset == 0 else horizon_buckets.get(offset, [])
        # 复习任务优先占位（调度约束，超预算也不裁——单任务完整性红线）。
        for task in reviews:
            tasks.append(task)
            planned += int(task["expected_time"])
        # 前一日 defer 顺延的任务优先承接。
        carried, deferred_backlog = deferred_backlog, []
        pool = carried + backlog
        remaining: list[dict[str, Any]] = []
        # pin 提前（学员意志红线：不静默覆盖；与到期复习同日时带后果说明）。
        pinned_first = sorted(
            pool,
            key=lambda t: (0 if _is_pinned(t) else 1),
        )
        for task in pinned_first:
            if offset == 0 and _is_deferred_target(task):
                deferred_backlog.append(task)
                preference_applied["defer"] += 1
                continue
            if planned >= budget_minutes and tasks:
                remaining.append(task)
                continue
            if _is_pinned(task):
                task = dict(task)
                task["pinned"] = True
                if offset == 0 and reviews:
                    task["consequence"] = "锁定优先执行：同日到期复验将顺延，遗忘风险上升"
                preference_applied["pin"] += 1
                # pin 的任务插到当日最前（学员意志优先于调度占位，后果已显示）。
                tasks.insert(0, task)
            else:
                tasks.append(task)
            planned += int(task["expected_time"])
        backlog = remaining
        day_plans.append(
            {
                "date": (today + timedelta(days=offset)).isoformat(),
                "day_offset": offset,
                "tasks": tasks,
                "planned_minutes": planned,
            }
        )

    # ── 首任务 parity 合并：day0 首任务逐字段承接四臂输出 ─────────────────────
    if not pins and not deferred_targets:
        day0_tasks = day_plans[0]["tasks"]
        head_ref = _text(next_step.get("source_ref"))
        head_mode = _text(next_step.get("mode"))
        if head_mode in {MODE_REVIEW, MODE_PRACTICE, MODE_LEARN, MODE_FALLBACK}:
            matched_index = next(
                (
                    index
                    for index, task in enumerate(day0_tasks)
                    if task["mode"] == head_mode and task["source_ref"] == head_ref
                ),
                None,
            )
            if matched_index is not None:
                merged = {**day0_tasks[matched_index], **next_step}
                day0_tasks.pop(matched_index)
                day0_tasks.insert(0, merged)

    return {
        "plan_policy_version": PLAN_POLICY_VERSION,
        "horizon_days": horizon_days,
        "days": day_plans,
        "supply_gaps": supply_gaps,
        "next_step_arbitration": next_step,
        "source_status": {
            "authority": "exam_prep_plan_projection",
            "plan_policy_version": PLAN_POLICY_VERSION,
            "daily_budget_minutes": budget_minutes,
            "preference_applied": preference_applied,
            "review_due_unavailable": bool(review_due_unavailable),
            "unscheduled_count": len(backlog) + len(deferred_backlog),
        },
    }


__all__ = [
    "PLAN_POLICY_VERSION",
    "build_exam_prep_plan_projection",
    "plan_preferences_from_events",
]
