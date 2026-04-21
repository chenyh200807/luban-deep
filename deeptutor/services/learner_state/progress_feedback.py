from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

_TZ = timezone(timedelta(hours=8))


def _date_key(days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=max(0, int(days_ago)))).strftime("%Y-%m-%d")


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_names(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    items: list[str] = []
    for value in list(values or []):
        name = str(value or "").strip()
        if not name or name in items:
            continue
        items.append(name)
    return items


def _recent_total(daily_counts: dict[str, Any], *, start_days_ago: int, span: int) -> int:
    total = 0
    for index in range(max(0, int(span))):
        total += _safe_int(daily_counts.get(_date_key(start_days_ago + index)))
    return total


def _with_today_count(daily_counts: dict[str, Any], today_done: int) -> dict[str, int]:
    normalized = {str(key): _safe_int(value) for key, value in dict(daily_counts or {}).items()}
    normalized[_date_key()] = max(_safe_int(normalized.get(_date_key())), _safe_int(today_done))
    return normalized


def _normalize_chapter_stats(chapter_stats: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in dict(chapter_stats or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        stats = dict(value or {})
        normalized[name] = {
            "done": _safe_int(stats.get("done")),
            "correct": _safe_int(stats.get("correct")),
            "last_activity_at": str(stats.get("last_activity_at") or "").strip(),
        }
    return normalized


def _pick_focus_stat(
    *,
    focus_topic: str = "",
    weak_points: list[Any] | tuple[Any, ...] | None = None,
    chapter_stats: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    stats_map = dict(chapter_stats or {})
    topic = str(focus_topic or "").strip()
    weak_names = _normalize_names(weak_points)
    candidates = [topic] + weak_names

    for candidate in candidates:
        if not candidate:
            continue
        if candidate in stats_map:
            return candidate, stats_map[candidate]
        for chapter_name, stats in stats_map.items():
            if candidate in chapter_name or chapter_name in candidate:
                return chapter_name, stats

    if stats_map:
        return max(
            stats_map.items(),
            key=lambda item: (_safe_int(item[1].get("done")), str(item[1].get("last_activity_at") or "")),
        )
    return topic or (weak_names[0] if weak_names else ""), {}


def _build_delta_detail(current: int, previous: int) -> str:
    if current <= 0 and previous <= 0:
        return "最近还没有形成连续输出"
    if previous <= 0:
        return "刚开始形成连续输出"
    delta = current - previous
    if delta > 0:
        return "比前 3 天多 " + str(delta) + " 题"
    if delta < 0:
        return "比前 3 天少 " + str(abs(delta)) + " 题"
    return "和前 3 天基本持平"


def _truncate(text: str, max_chars: int = 34) -> str:
    content = str(text or "").strip().replace("\n", " ")
    if len(content) <= max_chars:
        return content
    return content[: max(0, max_chars - 1)] + "…"


def _guide_event_titles(event: Any) -> list[str]:
    payload = dict(getattr(event, "payload_json", {}) or {})
    inner = dict(payload.get("payload_json") or payload)
    return [
        str(point.get("knowledge_title") or "").strip()
        for point in list(inner.get("knowledge_points") or [])
        if isinstance(point, dict) and str(point.get("knowledge_title") or "").strip()
    ]


def _build_event_milestone(
    memory_events: list[Any] | tuple[Any, ...] | None,
    *,
    guided_learning_history: list[dict[str, Any]] | None = None,
) -> dict[str, str] | None:
    guide_event = None
    for event in list(memory_events or []):
        if str(getattr(event, "memory_kind", "") or "").strip() == "guide_completion":
            guide_event = event
            break

    if guide_event is not None:
        titles = _guide_event_titles(guide_event)
        payload = dict(getattr(guide_event, "payload_json", {}) or {})
        inner = dict(payload.get("payload_json") or payload)
        summary = str(inner.get("summary") or "").strip()
        if titles:
            return {
                "title": "刚完成一次专题梳理",
                "detail": "最近完成了 " + "、".join(titles[:2]) + " 的梳理",
                "tone_class": "tone-good",
            }
        if summary:
            return {
                "title": "刚完成一次专题梳理",
                "detail": _truncate(summary),
                "tone_class": "tone-good",
            }

    history = list(guided_learning_history or [])
    if history and isinstance(history[0], dict):
        titles = [
            str(title or "").strip()
            for title in list(history[0].get("completed_titles") or [])
            if str(title or "").strip()
        ]
        if titles:
            return {
                "title": "最近完成一次知识梳理",
                "detail": "刚处理了 " + "、".join(titles[:2]) + " 等知识点",
                "tone_class": "tone-good",
            }
    return None


def build_progress_feedback(
    *,
    focus_topic: str = "",
    weak_points: list[Any] | tuple[Any, ...] | None = None,
    today_done: int | float = 0,
    daily_target: int | float = 0,
    streak_days: int | float = 0,
    review_due: int | float = 0,
    daily_counts: dict[str, Any] | None = None,
    chapter_stats: dict[str, Any] | None = None,
    memory_events: list[Any] | tuple[Any, ...] | None = None,
    guided_learning_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    done = _safe_int(today_done)
    target = _safe_int(daily_target)
    streak = _safe_int(streak_days)
    review_due_count = _safe_int(review_due)
    weak_names = _normalize_names(weak_points)
    normalized_daily_counts = _with_today_count(dict(daily_counts or {}), done)
    normalized_chapter_stats = _normalize_chapter_stats(chapter_stats)
    focus_name, focus_stats = _pick_focus_stat(
        focus_topic=focus_topic,
        weak_points=weak_names,
        chapter_stats=normalized_chapter_stats,
    )
    focus_done = _safe_int((focus_stats or {}).get("done"))

    recent_three = _recent_total(normalized_daily_counts, start_days_ago=0, span=3)
    previous_three = _recent_total(normalized_daily_counts, start_days_ago=3, span=3)
    delta_detail = _build_delta_detail(recent_three, previous_three)

    if recent_three > 0 and previous_three > 0:
        delta = recent_three - previous_three
        change_text = (
            "多 " + str(delta) + " 题"
            if delta > 0
            else "少 " + str(abs(delta)) + " 题"
            if delta < 0
            else "和前 3 天持平"
        )
        summary = "近 3 天累计完成 " + str(recent_three) + " 题，" + change_text + "，进步轨迹开始变得清晰"
    elif recent_three > 0:
        summary = "近 3 天已累计完成 " + str(recent_three) + " 题，节奏刚刚建立起来，继续推进就会看到更稳的变化"
    elif streak > 0:
        summary = "已连续学习 " + str(streak) + " 天，今天再完成一轮练习，系统就能给出更明确的变化反馈"
    else:
        summary = "先完成今天的第一轮练习，系统会开始记录你的节奏变化和薄弱点推进"

    if focus_name and focus_done > 0:
        insight = "这段时间你主要在推进“" + focus_name + "”，累计已完成 " + str(focus_done) + " 题"
    elif focus_name:
        insight = "系统已经把“" + focus_name + "”锁定为当前主攻，接下来几轮练习后这里会最先出现变化"
    elif review_due_count > 0:
        insight = "当前还有 " + str(review_due_count) + " 个待复习点，先清理它们，进步反馈会更快变实"
    elif weak_names:
        insight = "当前最值得观察的变化点在“" + weak_names[0] + "”，继续练习后这里最容易先出现抬升"
    else:
        insight = "先保持今天的学习动作，系统会开始把你的节奏和章节推进沉淀成可见变化"

    cards = [
        {
            "label": "近 3 天完成",
            "value": str(recent_three) + "题",
            "detail": delta_detail,
            "tone_class": "tone-good" if recent_three > previous_three else "tone-accent" if recent_three > 0 else "tone-warn",
        },
        {
            "label": "连续学习",
            "value": str(streak) + "天",
            "detail": "学习节奏正在形成" if streak >= 3 else "还在建立连续性" if streak > 0 else "今天开始建立节奏",
            "tone_class": "tone-good" if streak >= 3 else "tone-accent",
        },
        {
            "label": "主攻推进",
            "value": str(focus_done) + "题" if focus_done > 0 else "待启动",
            "detail": "最近在推“" + focus_name + "”" if focus_name else "主攻章节会在练习后自动锁定",
            "tone_class": "tone-good" if focus_done >= 6 else "tone-accent" if focus_name else "tone-warn",
        },
        {
            "label": "复习压力",
            "value": str(review_due_count) + "项",
            "detail": "建议今天先清掉待复习" if review_due_count > 0 else "当前复习压力可控",
            "tone_class": "tone-warn" if review_due_count > 0 else "tone-good",
        },
    ]

    milestones: list[dict[str, str]] = []
    if recent_three > 0:
        if previous_three > 0 and recent_three > previous_three:
            milestones.append(
                {
                    "title": "最近 3 天明显提速",
                    "detail": "相比前 3 天，多完成了 " + str(recent_three - previous_three) + " 题",
                    "tone_class": "tone-good",
                }
            )
        else:
            milestones.append(
                {
                    "title": "最近 3 天保持输出",
                    "detail": "累计已完成 " + str(recent_three) + " 题，节奏没有断开",
                    "tone_class": "tone-accent",
                }
            )
    if focus_name and focus_done > 0:
        milestones.append(
            {
                "title": "主攻章节开始沉淀",
                "detail": "“" + focus_name + "”累计已完成 " + str(focus_done) + " 题，已经有持续推进的迹象",
                "tone_class": "tone-good" if focus_done >= 6 else "tone-accent",
            }
        )
    event_milestone = _build_event_milestone(
        memory_events,
        guided_learning_history=guided_learning_history,
    )
    if event_milestone:
        milestones.append(event_milestone)
    if streak >= 3:
        milestones.append(
            {
                "title": "连续学习节奏已形成",
                "detail": "已经连续学习 " + str(streak) + " 天，继续保持更容易看到掌握度抬升",
                "tone_class": "tone-good",
            }
        )
    elif target > 0 and done > 0:
        milestones.append(
            {
                "title": "今日学习已经启动",
                "detail": "今天已完成 " + str(done) + "/" + str(target) + "，把当天目标打满会更容易看到正向反馈",
                "tone_class": "tone-accent",
            }
        )
    if review_due_count > 0:
        milestones.append(
            {
                "title": "复习压力需要处理",
                "detail": "当前还有 " + str(review_due_count) + " 个待复习点，先清理它们再加练更划算",
                "tone_class": "tone-warn",
            }
        )

    deduped: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for item in milestones:
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if not title or not detail or title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(
            {
                "title": title,
                "detail": detail,
                "tone_class": str(item.get("tone_class") or "tone-accent"),
            }
        )

    return {
        "summary": summary,
        "insight": insight,
        "cards": cards,
        "milestones": deduped[:3],
    }


def build_progress_feedback_from_learner_snapshot(
    snapshot: Any,
    *,
    daily_counts: dict[str, Any] | None = None,
    chapter_stats: dict[str, Any] | None = None,
    streak_days: int | float = 0,
    review_due: int | float = 0,
    focus_topic: str = "",
) -> dict[str, Any]:
    if snapshot is None:
        return {}
    profile = dict(getattr(snapshot, "profile", {}) or {})
    progress = dict(getattr(snapshot, "progress", {}) or {})
    today = dict(progress.get("today") or {})
    knowledge_map = dict(progress.get("knowledge_map") or {})
    memory_events = list(getattr(snapshot, "memory_events", []) or [])
    return build_progress_feedback(
        focus_topic=str(profile.get("focus_topic") or focus_topic or "").strip(),
        weak_points=list(knowledge_map.get("weak_points") or []),
        today_done=today.get("today_done") or 0,
        daily_target=today.get("daily_target") or 0,
        streak_days=streak_days,
        review_due=review_due,
        daily_counts=daily_counts,
        chapter_stats=chapter_stats,
        memory_events=memory_events,
        guided_learning_history=list(knowledge_map.get("guided_learning_history") or []),
    )
