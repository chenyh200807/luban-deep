from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Callable

from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
from deeptutor.services.learner_state.progress_feedback import build_progress_feedback
from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label

_TZ = timezone(timedelta(hours=8))
_SCHEMA_VERSION = 1
_ERROR_MESSAGE_LIMIT = 200
_LEGACY_SOURCE_TIMEOUT_S = 0.5
_CORE_SOURCE_TIMEOUT_S = 2.0
_SOURCE_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(4, int(os.getenv("DEEPTUTOR_LEARNING_REPORT_SOURCE_WORKERS", "8") or 8)),
    thread_name_prefix="learning-report-source",
)
_DEPRECATED_PAGE_SOURCES = [
    "/api/v1/practice/today-progress",
    "/api/v1/homepage/dashboard",
    "/api/v1/assessment/profile",
    "/api/v1/plan/mastery-dashboard",
    "/api/v1/learning-brain/projection",
]
_SOURCE_NAMES = (
    "today_progress",
    "home_dashboard",
    "assessment_profile",
    "mastery_dashboard",
    "learner_events",
    "compiled_truth",
    "dry_run_synthesis",
)


def build_learning_report_read_model(
    *,
    user_id: str,
    member_service: Any,
    learner_state_service: Any,
    event_limit: int = 100,
) -> dict[str, Any]:
    normalized_user = str(user_id or "").strip()
    limit = max(1, min(int(event_limit or 100), 500))

    source_status: dict[str, dict[str, Any]] = {name: _idle_status() for name in _SOURCE_NAMES}

    legacy_sources = _call_sources_parallel(
        source_status,
        {
            "today_progress": lambda: member_service.get_today_progress(normalized_user),
            "home_dashboard": lambda: member_service.get_home_dashboard(normalized_user),
            "assessment_profile": lambda: member_service.get_assessment_profile(normalized_user),
            "mastery_dashboard": lambda: member_service.get_mastery_dashboard(normalized_user),
        },
        timeout_s=_source_timeout_s("legacy", _LEGACY_SOURCE_TIMEOUT_S),
    )
    legacy_today = legacy_sources.get("today_progress")
    home_dashboard = legacy_sources.get("home_dashboard")
    assessment_profile = legacy_sources.get("assessment_profile")
    mastery_dashboard = legacy_sources.get("mastery_dashboard")
    raw_events, _ = _call_source(
        source_status,
        "learner_events",
        lambda: _list_learning_evidence_events(
            learner_state_service,
            normalized_user,
            limit=limit,
            since=_recent_window_since_iso(),
        ),
        default=[],
        timeout_s=_source_timeout_s("core", _CORE_SOURCE_TIMEOUT_S),
    )

    legacy_today = _safe_dict(legacy_today)
    home_dashboard = _safe_dict(home_dashboard)
    assessment_profile = _safe_dict(assessment_profile)
    mastery_dashboard = _safe_dict(mastery_dashboard)
    raw_events = list(raw_events or [])

    events = _learning_evidence_events(raw_events)
    evidence_stats = _aggregate_learning_evidence(events)

    learning_brain, learning_brain_source = _build_learning_brain(
        user_id=normalized_user,
        learner_state_service=learner_state_service,
        event_limit=limit,
        evidence_events=events,
        source_status=source_status,
    )
    weak_points = _learning_brain_weak_points(learning_brain)
    weak_names = [
        _concept_label(str(item.get("concept_id") or ""))
        for item in weak_points
        if str(item.get("concept_id") or "").strip()
    ]
    if not weak_names:
        weak_names = [
            str(item.get("name") or "").strip()
            for item in _safe_list(_safe_dict(home_dashboard.get("mastery")).get("weak_nodes"))
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]

    progress_feedback = build_progress_feedback(
        focus_topic=_pick_focus_topic(weak_names=weak_names, home_dashboard=home_dashboard),
        weak_points=weak_names,
        today_done=evidence_stats["today_done"],
        daily_target=_safe_int(legacy_today.get("daily_target")) or 30,
        streak_days=evidence_stats["streak_days"],
        review_due=_safe_int(_safe_dict(mastery_dashboard.get("review_summary")).get("total_due")),
        daily_counts=evidence_stats["daily_counts"],
        chapter_stats=evidence_stats["chapter_stats"],
        memory_events=events,
    )
    radar_dimensions = _radar_dimensions(assessment_profile, mastery_dashboard)
    mastery = _mastery_payload(mastery_dashboard, radar_dimensions=radar_dimensions)
    next_training = _next_training_items(learning_brain, home_dashboard)
    daily_target = _safe_int(legacy_today.get("daily_target")) or 30
    overview = {
        "today_done": evidence_stats["today_done"],
        "recent_three_done": evidence_stats["recent_three_done"],
        "attempt_count": evidence_stats["attempt_count"],
        "today_unique_questions": evidence_stats["today_unique_questions"],
        "recent_three_unique_questions": evidence_stats["recent_three_unique_questions"],
        "unique_question_count": evidence_stats["unique_question_count"],
        "daily_target": daily_target,
        "streak_days": evidence_stats["streak_days"],
        "weak_node_count": len(weak_points)
        if weak_points
        else len(_safe_list(_safe_dict(home_dashboard.get("mastery")).get("weak_nodes"))),
        "due_today_count": _safe_int(_safe_dict(home_dashboard.get("review")).get("due_today")),
        "focus_hint": _safe_dict(home_dashboard.get("today")).get("hint")
        or _safe_dict(home_dashboard.get("today_focus")).get("title")
        or "",
        "learner_level": str(assessment_profile.get("level") or ""),
        "study_tip": _safe_dict(_safe_dict(assessment_profile.get("diagnostic_feedback")).get("learner_profile")).get(
            "study_tip"
        )
        or "",
        "overall_mastery": _safe_int(mastery.get("overall_mastery")),
    }

    window_truncated = evidence_stats["event_count"] >= limit
    degraded_sources = sorted(
        name for name, status in source_status.items() if status.get("ok") is False
    )
    degraded = bool(degraded_sources)

    return {
        "ok": True,
        "user_id": normalized_user,
        "schema_version": _SCHEMA_VERSION,
        "authority": {
            "read_model": "learning-report-read-model",
            "progress_source": "learner_memory_events.learning_evidence",
            "learning_brain_source": learning_brain_source,
            "deprecated_page_sources": list(_DEPRECATED_PAGE_SOURCES),
        },
        "degraded": degraded,
        "degraded_sources": degraded_sources,
        "source_status": source_status,
        "freshness": {
            "generated_at": datetime.now(_TZ).isoformat(),
            "event_count": evidence_stats["event_count"],
            "latest_event_at": evidence_stats["latest_event_at"],
            "unknown_date_count": evidence_stats["unknown_date_count"],
            "window_truncated": window_truncated,
        },
        "overview": overview,
        "progress_feedback": progress_feedback,
        "mastery": mastery,
        "radar_dimensions": radar_dimensions,
        "learning_brain": learning_brain,
        "next_training": next_training,
        "legacy_compat": {
            "today_progress": legacy_today,
            "home_dashboard": home_dashboard,
            "assessment_profile": assessment_profile,
            "mastery_dashboard": mastery_dashboard,
        },
    }


def _idle_status() -> dict[str, Any]:
    return {"ok": None, "latency_ms": 0, "error": None}


def _call_source(
    source_status: dict[str, dict[str, Any]],
    name: str,
    fn: Callable[[], Any],
    *,
    default: Any = None,
    timeout_s: float | None = None,
) -> tuple[Any, dict[str, Any]]:
    started = time.perf_counter()
    try:
        value = _run_source_with_timeout(fn, timeout_s=timeout_s)
    except TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = f"TimeoutError: source exceeded {float(timeout_s or 0):.2f}s"[:_ERROR_MESSAGE_LIMIT]
        status = {"ok": False, "latency_ms": latency_ms, "error": message}
        source_status[name] = status
        return default, status
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = f"{type(exc).__name__}: {exc!s}"[:_ERROR_MESSAGE_LIMIT]
        status = {"ok": False, "latency_ms": latency_ms, "error": message}
        source_status[name] = status
        return default, status
    latency_ms = int((time.perf_counter() - started) * 1000)
    status = {"ok": True, "latency_ms": latency_ms, "error": None}
    source_status[name] = status
    return value, status


def _call_sources_parallel(
    source_status: dict[str, dict[str, Any]],
    calls: dict[str, Callable[[], Any]],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.perf_counter() + max(float(timeout_s), 0.01)
    futures = {
        name: (time.perf_counter(), _SOURCE_EXECUTOR.submit(fn))
        for name, fn in dict(calls or {}).items()
    }
    results: dict[str, Any] = {}
    for name, (started, future) in futures.items():
        try:
            value = future.result(timeout=max(deadline - time.perf_counter(), 0.01))
        except TimeoutError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            source_status[name] = {
                "ok": False,
                "latency_ms": latency_ms,
                "error": f"TimeoutError: source exceeded {float(timeout_s):.2f}s"[:_ERROR_MESSAGE_LIMIT],
            }
            continue
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            source_status[name] = {
                "ok": False,
                "latency_ms": latency_ms,
                "error": f"{type(exc).__name__}: {exc!s}"[:_ERROR_MESSAGE_LIMIT],
            }
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)
        source_status[name] = {"ok": True, "latency_ms": latency_ms, "error": None}
        results[name] = value
    return results


def _run_source_with_timeout(fn: Callable[[], Any], *, timeout_s: float | None) -> Any:
    if timeout_s is None or timeout_s <= 0:
        return fn()
    future = _SOURCE_EXECUTOR.submit(fn)
    return future.result(timeout=float(timeout_s))


def _source_timeout_s(kind: str, default: float) -> float:
    env_name = f"DEEPTUTOR_LEARNING_REPORT_{str(kind or '').upper()}_SOURCE_TIMEOUT_MS"
    try:
        value = float(os.getenv(env_name, "")) / 1000.0
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else float(default)


def _list_learning_evidence_events(
    learner_state_service: Any,
    user_id: str,
    *,
    limit: int,
    since: str,
) -> list[Any]:
    reader = getattr(learner_state_service, "list_learning_evidence_events", None)
    if callable(reader):
        return list(reader(user_id, limit=limit, since=since) or [])
    events = list(learner_state_service.list_memory_events(user_id, limit=None) or [])
    filtered = [
        event
        for event in _learning_evidence_events(events)
        if _iso_unknown_or_after(str(getattr(event, "created_at", "") or ""), since)
    ]
    return filtered[-max(1, int(limit)) :]


def _build_learning_brain(
    *,
    user_id: str,
    learner_state_service: Any,
    event_limit: int,
    evidence_events: list[Any],
    source_status: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    projection, compiled_status = _call_source(
        source_status,
        "compiled_truth",
        lambda: learner_state_service.read_compiled_learning_truth(user_id),
    )
    projection = _safe_dict(projection)
    source = "compiled_learning_truth"
    if not projection and evidence_events:
        synthesis, _ = _call_source(
            source_status,
            "dry_run_synthesis",
            lambda: learner_state_service.synthesize_learning_truth(
                user_id, dry_run=True, event_limit=event_limit
            ),
        )
        projection = _safe_dict(_safe_dict(synthesis).get("projection"))
        source = "dry_run_learning_evidence"
    elif compiled_status.get("ok") is False:
        source = "dry_run_learning_evidence"
    return (
        build_learning_brain_read_model(user_id=user_id, projection=projection, surface="mobile"),
        source,
    )


def _learning_evidence_events(events: list[Any]) -> list[Any]:
    return [
        event
        for event in list(events or [])
        if str(getattr(event, "source_feature", "") or "") == "construction_grading"
        and str(getattr(event, "memory_kind", "") or "") == "learning_evidence"
    ]


def _aggregate_learning_evidence(events: list[Any]) -> dict[str, Any]:
    daily_attempts: dict[str, int] = defaultdict(int)
    daily_unique_questions: dict[str, set[str]] = defaultdict(set)
    chapter_stats: dict[str, dict[str, Any]] = {}
    latest_event_at = ""
    unknown_date_count = 0
    attempt_count = 0
    today_key = _date_key()
    today_unique: set[str] = set()
    recent_three_unique: set[str] = set()
    recent_three_keys = {_date_key(days_ago=index) for index in range(3)}
    unique_questions: set[str] = set()
    event_count = 0

    for event in events:
        event_count += 1
        payload = _safe_dict(getattr(event, "payload_json", {}))
        created_at = str(getattr(event, "created_at", "") or "").strip()
        day = _date_key_from_iso(created_at)
        if day is None:
            unknown_date_count += 1
            continue
        attempt_count += 1
        daily_attempts[day] += 1
        question_id = str(
            payload.get("question_id")
            or getattr(event, "source_id", "")
            or getattr(event, "event_id", "")
        ).strip()
        if question_id:
            daily_unique_questions[day].add(question_id)
            unique_questions.add(question_id)
            if day == today_key:
                today_unique.add(question_id)
            if day in recent_three_keys:
                recent_three_unique.add(question_id)
        if created_at and (not latest_event_at or created_at > latest_event_at):
            latest_event_at = created_at
        concept = _event_concept(payload)
        label = _concept_label(concept)
        if label:
            stats = chapter_stats.setdefault(label, {"done": 0, "correct": 0, "last_activity_at": ""})
            stats["done"] += 1
            if _is_correct(payload):
                stats["correct"] += 1
            if created_at and created_at > str(stats.get("last_activity_at") or ""):
                stats["last_activity_at"] = created_at

    daily_counts_view = {key: int(value) for key, value in daily_attempts.items()}
    today_done = int(daily_attempts.get(today_key, 0))
    recent_three_done = sum(int(daily_attempts.get(_date_key(days_ago=index), 0)) for index in range(3))
    return {
        "daily_counts": daily_counts_view,
        "daily_unique_questions": {key: sorted(value) for key, value in daily_unique_questions.items()},
        "chapter_stats": chapter_stats,
        "today_done": today_done,
        "recent_three_done": recent_three_done,
        "attempt_count": attempt_count,
        "today_unique_questions": len(today_unique),
        "recent_three_unique_questions": len(recent_three_unique),
        "unique_question_count": len(unique_questions),
        "streak_days": _streak_days(daily_counts_view),
        "latest_event_at": latest_event_at,
        "unknown_date_count": unknown_date_count,
        "event_count": event_count,
    }


def _event_concept(payload: dict[str, Any]) -> str:
    signal = _safe_dict(payload.get("next_training_signal"))
    if str(signal.get("concept") or "").strip():
        return str(signal.get("concept") or "").strip()
    for error in _safe_list(payload.get("error_events") or payload.get("errors")):
        if isinstance(error, dict) and str(error.get("concept_tag") or "").strip():
            return str(error.get("concept_tag") or "").strip()
    for edge in _safe_list(payload.get("typed_edges")):
        if not isinstance(edge, dict):
            continue
        to_node = _safe_dict(edge.get("to"))
        if to_node.get("type") == "concept" and str(to_node.get("id") or "").strip():
            return str(to_node.get("id") or "").strip()
    return ""


def _learning_brain_weak_points(learning_brain: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in _safe_list(learning_brain.get("weak_points")) if isinstance(item, dict)]


def _next_training_items(learning_brain: dict[str, Any], home_dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    visible = _safe_dict(learning_brain.get("visible_sections"))
    items = [dict(item) for item in _safe_list(visible.get("next_training")) if isinstance(item, dict)]
    if items:
        return items[:5]
    focus = _safe_dict(home_dashboard.get("today_focus"))
    if focus:
        return [{"display_title": focus.get("title") or "下一步训练", "display_meta": focus.get("description") or ""}]
    return []


def _mastery_payload(mastery_dashboard: dict[str, Any], *, radar_dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    groups = _safe_list(mastery_dashboard.get("groups"))
    hotspots = _safe_list(mastery_dashboard.get("hotspots"))
    review = _safe_dict(mastery_dashboard.get("review_summary"))
    if mastery_dashboard:
        overall = _safe_int(mastery_dashboard.get("overall_mastery"))
    else:
        scores = [round(float(item.get("value") or 0) * 100) for item in radar_dimensions]
        overall = round(sum(scores) / max(len(scores), 1)) if scores else 0
    return {
        "overall_mastery": overall,
        "groups": groups,
        "hotspots": hotspots,
        "review_summary": review or {"total_due": 0, "overdue_count": 0},
    }


def _radar_dimensions(assessment_profile: dict[str, Any], mastery_dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    mastery = _safe_dict(assessment_profile.get("chapter_mastery"))
    dimensions: list[dict[str, Any]] = []
    for key, value in mastery.items():
        item = _safe_dict(value)
        score = _safe_int(item.get("mastery") if item else value)
        name = str(item.get("name") or key or "").strip()
        if name:
            dimensions.append({"name": name, "value": round(score / 100, 2)})
    if dimensions:
        return dimensions
    for group in _safe_list(mastery_dashboard.get("groups")):
        for chapter in _safe_list(_safe_dict(group).get("chapters")):
            item = _safe_dict(chapter)
            name = str(item.get("name") or "").strip()
            if name:
                dimensions.append({"name": name, "value": round(_safe_int(item.get("mastery")) / 100, 2)})
    return dimensions


def _pick_focus_topic(*, weak_names: list[str], home_dashboard: dict[str, Any]) -> str:
    if weak_names:
        return weak_names[0]
    focus = _safe_dict(home_dashboard.get("today_focus"))
    return str(focus.get("title") or _safe_dict(home_dashboard.get("today")).get("hint") or "").strip()


def _concept_label(concept_id: str) -> str:
    return display_taxonomy_label(concept_id, fallback=concept_id or "")


def _is_correct(payload: dict[str, Any]) -> bool:
    try:
        awarded = float(payload.get("score_awarded") or 0)
        max_score = float(payload.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return max_score > 0 and awarded >= max_score


def _date_key(value: str | None = None, *, days_ago: int = 0) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(_TZ).strftime("%Y-%m-%d")
        except Exception:
            pass
    return (datetime.now(_TZ) - timedelta(days=max(0, int(days_ago)))).strftime("%Y-%m-%d")


def _recent_window_since_iso() -> str:
    start = datetime.now(_TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2)
    return start.isoformat()


def _iso_at_or_after(value: str, floor: str) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        floor_dt = datetime.fromisoformat(str(floor or "").replace("Z", "+00:00"))
    except Exception:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    if floor_dt.tzinfo is None:
        floor_dt = floor_dt.replace(tzinfo=_TZ)
    return parsed >= floor_dt


def _iso_unknown_or_after(value: str, floor: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return True
    return _iso_at_or_after(text, floor)


def _date_key_from_iso(value: str) -> str | None:
    """Parse an ISO timestamp into a YYYY-MM-DD day bucket in +08:00.

    Returns None when the value is missing, malformed, or in the future — those
    events must not be folded into today's attempt count and instead increment
    ``unknown_date_count``.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    now = datetime.now(_TZ)
    if parsed > now + timedelta(minutes=5):
        return None
    return parsed.astimezone(_TZ).strftime("%Y-%m-%d")


def _streak_days(daily_counts: dict[str, int]) -> int:
    streak = 0
    for index in range(365):
        if int(daily_counts.get(_date_key(days_ago=index)) or 0) <= 0:
            break
        streak += 1
    return streak


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
