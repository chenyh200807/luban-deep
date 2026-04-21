from __future__ import annotations

from typing import Any


def _normalize_names(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    items: list[str] = []
    for value in list(values or []):
        name = str(value or "").strip()
        if not name or name in items:
            continue
        items.append(name)
    return items


def _pick_focus_topic(
    *,
    focus_topic: str = "",
    weak_points: list[Any] | tuple[Any, ...] | None = None,
    hotspots: list[Any] | tuple[Any, ...] | None = None,
) -> str:
    topic = str(focus_topic or "").strip()
    if topic:
        return topic
    weak_names = _normalize_names(weak_points)
    if weak_names:
        return weak_names[0]
    hotspot_names = _normalize_names(hotspots)
    if hotspot_names:
        return hotspot_names[0]
    return ""


def build_study_plan(
    *,
    focus_topic: str = "",
    focus_hint: str = "",
    weak_points: list[Any] | tuple[Any, ...] | None = None,
    hotspots: list[Any] | tuple[Any, ...] | None = None,
    today_done: int | float = 0,
    daily_target: int | float = 0,
    due_today_count: int | float = 0,
    total_due: int | float = 0,
    overdue_count: int | float = 0,
) -> dict[str, str]:
    topic = _pick_focus_topic(
        focus_topic=focus_topic,
        weak_points=weak_points,
        hotspots=hotspots,
    )
    weak_names = _normalize_names(weak_points)
    hint = str(focus_hint or "").strip()
    total_due_count = max(0, int(total_due or 0))
    overdue = max(0, int(overdue_count or 0))
    due_today = max(0, int(due_today_count or 0))
    done = max(0, int(today_done or 0))
    target = max(0, int(daily_target or 0))
    remaining_target = max(target - done, 0)
    question_count = max(min(remaining_target or 5, 5), 3)

    if total_due_count > 0 and topic:
        priority_task = (
            "先清理 "
            + str(min(total_due_count, 3))
            + " 个待复习点，再围绕“"
            + topic
            + "”做 "
            + str(question_count)
            + " 题巩固"
        )
    elif topic:
        priority_task = "先围绕“" + topic + "”速练 " + str(question_count) + " 题，尽快把薄弱点拉回主线"
    elif remaining_target > 0:
        priority_task = "先完成今天剩余的 " + str(remaining_target) + " 题目标，保持学习节奏"
    else:
        priority_task = "先完成一轮短练习，系统会继续更新你的薄弱点判断"

    if topic:
        study_method = "先看“" + topic + "”考点梳理，再做真题强化，最后回看错题"
    elif due_today > 0:
        study_method = "先复习再练题，把今天待回看的内容优先清掉"
    else:
        study_method = "先做短练，再按错题回看考点，保持诊断持续更新"

    if total_due_count > 0 or overdue > 0:
        time_budget = "约 15 分钟，优先清理复习任务"
    elif remaining_target > 0:
        time_budget = "约 12 分钟，完成今日目标后再加练一轮"
    else:
        time_budget = "约 10 分钟，保持今天的学习节奏"

    if hint:
        coach_note = hint
    elif topic:
        coach_note = "当前最值得优先补强的章节是“" + topic + "”"
    elif weak_names:
        coach_note = "当前最需要优先处理的薄弱点是“" + weak_names[0] + "”"
    else:
        coach_note = "先保持练习频率，系统会继续为你收敛更准确的作战建议"

    return {
        "focus_topic": topic or "今天先稳住基础节奏",
        "priority_task": priority_task,
        "study_method": study_method,
        "time_budget": time_budget,
        "coach_note": coach_note,
    }


def build_study_plan_from_learner_snapshot(
    snapshot: Any,
    *,
    focus_hint: str = "",
    hotspots: list[Any] | tuple[Any, ...] | None = None,
    due_today_count: int | float = 0,
    total_due: int | float = 0,
    overdue_count: int | float = 0,
) -> dict[str, str]:
    if snapshot is None:
        return {}
    profile = dict(getattr(snapshot, "profile", {}) or {})
    progress = dict(getattr(snapshot, "progress", {}) or {})
    today = dict(progress.get("today") or {})
    knowledge_map = dict(progress.get("knowledge_map") or {})
    weak_points = list(knowledge_map.get("weak_points") or [])
    return build_study_plan(
        focus_topic=str(profile.get("focus_topic") or "").strip(),
        focus_hint=focus_hint,
        weak_points=weak_points,
        hotspots=hotspots,
        today_done=today.get("today_done") or 0,
        daily_target=today.get("daily_target") or 0,
        due_today_count=due_today_count,
        total_due=total_due,
        overdue_count=overdue_count,
    )


def format_study_plan_for_prompt(study_plan: dict[str, Any] | None) -> str:
    plan = dict(study_plan or {})
    if not plan:
        return ""

    lines: list[str] = []
    focus_topic = str(plan.get("focus_topic") or "").strip()
    priority_task = str(plan.get("priority_task") or "").strip()
    study_method = str(plan.get("study_method") or "").strip()
    time_budget = str(plan.get("time_budget") or "").strip()
    coach_note = str(plan.get("coach_note") or "").strip()

    if focus_topic:
        lines.append("今日主攻：" + focus_topic)
    if priority_task:
        lines.append("优先任务：" + priority_task)
    if study_method:
        lines.append("学习顺序：" + study_method)
    if time_budget:
        lines.append("建议投入：" + time_budget)
    if coach_note:
        lines.append("补充说明：" + coach_note)

    if not lines:
        return ""
    return "\n当前作战方案：\n- " + "\n- ".join(lines)
