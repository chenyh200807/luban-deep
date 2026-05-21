from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any, Callable

from deeptutor.services.construction_grading.learning_evidence import compute_quality_signals
from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
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
_ERROR_LABELS = {
    "E01": "知识点缺失",
    "E02": "采分点遗漏",
    "E03": "关键词缺失",
    "E04": "口号化表达",
    "E05": "审题错误",
    "E06": "程序顺序错误",
    "E07": "概念混淆",
    "E08": "背景信息提取失败",
    "E09": "计算错误",
    "E10": "规范适用错误",
    "E11": "迁移失败",
    "E12": "表达冗余",
    "M01": "知识点不熟",
    "M02": "关键词误读",
    "M03": "概念混淆",
    "M04": "选项陷阱",
    "M05": "审题方向错误",
    "M06": "多选漏选",
    "M07": "多选错选",
    "M08": "规范数字混淆",
    "M09": "题干条件提取不完整",
    "M10": "用常识替代规范判断",
}


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
    radar_dimensions = _radar_dimensions(
        assessment_profile,
        mastery_dashboard,
        evidence_stats=evidence_stats,
    )
    mastery = _mastery_payload(
        mastery_dashboard,
        radar_dimensions=radar_dimensions,
        evidence_stats=evidence_stats,
    )
    next_training = _next_training_items(learning_brain, home_dashboard)
    learner_facing = _learner_facing_payload(
        events=events,
        evidence_stats=evidence_stats,
        weak_points=weak_points,
        next_training=next_training,
    )
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
        "learner_facing": learner_facing,
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


def _learner_facing_payload(
    *,
    events: list[Any],
    evidence_stats: dict[str, Any],
    weak_points: list[dict[str, Any]],
    next_training: list[dict[str, Any]],
) -> dict[str, Any]:
    attempts = _recent_attempt_cards(events)
    diagnoses = _diagnosis_cards(events=events, weak_points=weak_points)
    timeline = _evidence_timeline(attempts)
    loops = _training_loop_cards(attempts=attempts, diagnoses=diagnoses)
    next_action = _next_action_card(diagnoses=diagnoses, next_training=next_training)
    primary_focus = str(next_action.get("concept") or "").strip()
    if not primary_focus and diagnoses:
        primary_focus = str(diagnoses[0].get("concept") or "").strip()
    if not primary_focus and attempts:
        primary_focus = str(attempts[0].get("concept") or "").strip()
    today_done = _safe_int(evidence_stats.get("today_done"))
    recent_done = _safe_int(evidence_stats.get("recent_three_done"))
    weak_count = len(diagnoses)
    if attempts:
        headline = f"最近 {recent_done} 次练习里，重点关注 {primary_focus or '薄弱题型'}。"
    else:
        headline = "完成一次练习后，这里会按真实作答生成复盘。"
    return {
        "summary": {
            "title": "今日学习复盘" if attempts else "学习复盘待生成",
            "headline": headline,
            "today_done": today_done,
            "recent_three_done": recent_done,
            "primary_focus": primary_focus,
            "weak_count": weak_count,
        },
        "recent_attempts": attempts[:5],
        "diagnoses": diagnoses[:4],
        "evidence_timeline": timeline[:6],
        "training_loops": loops[:3],
        "next_action": next_action,
    }


def _recent_attempt_cards(events: list[Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    ordered = sorted(
        list(events or []),
        key=lambda event: str(getattr(event, "created_at", "") or ""),
        reverse=True,
    )
    for index, event in enumerate(ordered[:12]):
        payload = _safe_dict(getattr(event, "payload_json", {}))
        concept = _concept_label(_event_concept(payload)) or "综合练习"
        errors = [error for error in _safe_list(payload.get("error_events") or payload.get("errors")) if isinstance(error, dict)]
        is_correct = _is_correct(payload)
        error_label = _primary_error_label(errors)
        diagnosis = _primary_diagnosis(errors)
        user_answer = _format_answer(payload.get("user_answer"), payload.get("options"))
        correct_answer = _format_answer(payload.get("correct_answer"), payload.get("options"))
        missed = _format_letters(payload.get("missed_options"))
        extra = _format_letters(payload.get("extra_options"))
        result_label = "答对" if is_correct else "答错"
        question_text = _question_text(payload=payload, event=event, index=index)
        title = _truncate(question_text, 34)
        answer_parts = []
        if user_answer:
            answer_parts.append(f"你选：{user_answer}")
        if correct_answer:
            answer_parts.append(f"正确：{correct_answer}")
        if missed:
            answer_parts.append(f"漏选：{missed}")
        if extra:
            answer_parts.append(f"多选：{extra}")
        if not answer_parts and payload.get("score_awarded") is not None and payload.get("max_score") is not None:
            answer_parts.append(f"得分：{payload.get('score_awarded')}/{payload.get('max_score')}")
        if not diagnosis:
            diagnosis = "这次作答形成了一条改善信号。" if is_correct else "本次批改记录到一个薄弱点。"
        explanation = _pick_attempt_explanation(payload, diagnosis=diagnosis, is_correct=is_correct)
        quality = _attempt_quality(payload)
        cards.append({
            "key": _attempt_card_key(event=event, payload=payload, index=index),
            "attempt_ref": _attempt_ref(event=event, payload=payload),
            "time_label": _time_label(str(getattr(event, "created_at", "") or "")),
            "title": title,
            "question_text": question_text,
            "options": _option_items(payload.get("options")),
            "concept": concept,
            "result_label": result_label,
            "tone": "correct" if is_correct else "wrong",
            "answer_line": "；".join(answer_parts),
            "diagnosis": error_label or ("稳定答对" if is_correct else "待归因"),
            "diagnosis_detail": _clean_learning_text(diagnosis),
            "explanation": explanation,
            "evidence_label": _attempt_evidence_label(index),
            "collectable": not is_correct,
            "detail_lines": [
                line for line in [
                    "；".join(answer_parts),
                    _clean_learning_text(diagnosis),
                    explanation,
                ] if line
            ],
            "quality": quality,
        })
    return cards


def _attempt_ref(*, event: Any, payload: dict[str, Any]) -> str:
    try:
        return sign_attempt_ref(
            user_id=str(getattr(event, "user_id", "") or ""),
            event_id=str(getattr(event, "event_id", "") or ""),
            question_id=str(payload.get("question_id") or ""),
        )
    except ValueError:
        return ""


def _diagnosis_cards(*, events: list[Any], weak_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        created_at = str(getattr(event, "created_at", "") or "")
        for error in _safe_list(payload.get("error_events") or payload.get("errors")):
            if not isinstance(error, dict):
                continue
            concept = _concept_label(str(error.get("concept_tag") or _event_concept(payload) or ""))
            error_code = str(error.get("error_code") or "").strip().upper()
            error_label = _error_label(error_code)
            if not concept and not error_label:
                continue
            key = (concept or "综合练习", error_label or "待归因")
            item = grouped.setdefault(
                key,
                {
                    "key": f"{key[0]}::{key[1]}",
                    "concept": key[0],
                    "error": key[1],
                    "count": 0,
                    "latest_at": "",
                    "detail": "",
                },
            )
            item["count"] += 1
            if created_at > str(item.get("latest_at") or ""):
                item["latest_at"] = created_at
                item["detail"] = _clean_learning_text(error.get("diagnosis") or "")

    for weak in weak_points:
        concept = _concept_label(str(weak.get("concept_id") or ""))
        error = _error_label(weak.get("error_code"))
        if not concept and not error:
            continue
        key = (concept or "综合练习", error or "待归因")
        item = grouped.setdefault(
            key,
            {
                "key": f"{key[0]}::{key[1]}",
                "concept": key[0],
                "error": key[1],
                "count": 0,
                "latest_at": "",
                "detail": _clean_learning_text(weak.get("claim") or ""),
            },
        )
        item["count"] = max(_safe_int(item.get("count")), len(_safe_list(weak.get("supporting_event_ids"))))
        if not item.get("detail"):
            item["detail"] = _clean_learning_text(weak.get("display_title") or weak.get("claim") or "")

    cards = []
    for item in grouped.values():
        count = _safe_int(item.get("count"))
        concept = str(item.get("concept") or "综合练习")
        error = str(item.get("error") or "待归因")
        level_label = "需要重点补" if count >= 2 else "刚发现"
        cards.append({
            "key": str(item.get("key") or f"{concept}::{error}"),
            "level_label": level_label,
            "title": f"{concept}：{error}",
            "concept": concept,
            "error": error,
            "meta": f"最近出现 {max(count, 1)} 次",
            "detail": item.get("detail") or f"这类题先按“{error}”处理，后续练习会继续校准。",
            "action": f"先做 3 道{concept}相关辨析题",
            "count": max(count, 1),
        })
    return sorted(cards, key=lambda item: (_safe_int(item.get("count")), str(item.get("key") or "")), reverse=True)


def _evidence_timeline(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for index, item in enumerate(attempts):
        result = str(item.get("result_label") or "")
        answer = str(item.get("answer_line") or "").strip()
        line = "；".join(part for part in (result, answer, str(item.get("diagnosis") or "")) if part)
        timeline.append({
            "key": f"timeline-{index}",
            "time_label": item.get("time_label") or "",
            "title": item.get("title") or "一次练习",
            "line": line,
            "tone": item.get("tone") or "",
        })
    return timeline


def _training_loop_cards(*, attempts: list[dict[str, Any]], diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards = []
    for index, diagnosis in enumerate(diagnoses[:4]):
        concept = str(diagnosis.get("concept") or "薄弱点")
        error = str(diagnosis.get("error") or "待归因")
        related = [item for item in attempts if item.get("concept") == concept]
        latest_tone = str(related[0].get("tone") or "") if related else ""
        improved = latest_tone == "correct"
        cards.append({
            "key": f"loop-{index}",
            "title": error,
            "from": f"错因：{concept} / {error}",
            "training": f"训练：{diagnosis.get('action') or ('围绕 ' + concept + ' 做变式训练')}",
            "outcome": "变化：最近已有答对记录，继续巩固" if improved else "变化：仍需通过下一轮训练验证",
            "tone": "improved" if improved else "not-improved",
        })
    return cards


def _next_action_card(*, diagnoses: list[dict[str, Any]], next_training: list[dict[str, Any]]) -> dict[str, Any]:
    if diagnoses:
        top = diagnoses[0]
        concept = str(top.get("concept") or "薄弱点")
        error = str(top.get("error") or "错因")
        return {
            "title": f"先做 3 道“{concept}”专项题",
            "subtitle": f"目标：把“{error}”这一类错误拉回主线",
            "concept": concept,
            "cta": "开始训练",
            "estimated_minutes": 8,
        }
    if next_training:
        item = _safe_dict(next_training[0])
        title = _clean_learning_text(item.get("display_title") or item.get("claim") or "下一步训练")
        meta = _clean_learning_text(item.get("display_meta") or item.get("display_label") or "")
        return {
            "title": title or "先完成一组专项训练",
            "subtitle": meta or "完成后系统会继续更新你的学情判断",
            "concept": "",
            "cta": "开始训练",
            "estimated_minutes": 8,
        }
    return {
        "title": "先完成一组练习",
        "subtitle": "完成批改后，系统会生成你的错因和下一步训练",
        "concept": "",
        "cta": "去练习",
        "estimated_minutes": 10,
    }


def _mastery_payload(
    mastery_dashboard: dict[str, Any],
    *,
    radar_dimensions: list[dict[str, Any]],
    evidence_stats: dict[str, Any],
) -> dict[str, Any]:
    chapter_stats = _safe_dict(evidence_stats.get("chapter_stats"))
    groups = []
    for group in _safe_list(mastery_dashboard.get("groups")):
        group_payload = _safe_dict(group)
        chapters = []
        for chapter in _safe_list(group_payload.get("chapters")):
            chapter_payload = _safe_dict(chapter)
            name = _display_dimension_label(chapter_payload.get("name"))
            if not name:
                continue
            mastery = _calibrated_mastery(
                _safe_int(chapter_payload.get("mastery")),
                _safe_dict(chapter_stats.get(name)),
            )
            chapters.append({**chapter_payload, "name": name, "mastery": mastery})
        if not chapters:
            continue
        avg_mastery = round(
            sum(_safe_int(item.get("mastery")) for item in chapters) / max(len(chapters), 1)
        )
        groups.append({**group_payload, "avg_mastery": avg_mastery, "chapters": chapters})

    hotspots = []
    for item in _safe_list(mastery_dashboard.get("hotspots")):
        hotspot = _safe_dict(item)
        name = _display_dimension_label(hotspot.get("name"))
        if not name:
            continue
        mastery = _calibrated_mastery(
            _safe_int(hotspot.get("mastery")),
            _safe_dict(chapter_stats.get(name)),
        )
        hotspots.append({**hotspot, "name": name, "mastery": mastery})
    review = _safe_dict(mastery_dashboard.get("review_summary"))
    chapter_scores = [
        _safe_int(chapter.get("mastery"))
        for group in groups
        for chapter in _safe_list(_safe_dict(group).get("chapters"))
    ]
    if chapter_scores:
        overall = round(sum(chapter_scores) / max(len(chapter_scores), 1))
    else:
        scores = [round(float(item.get("value") or 0) * 100) for item in radar_dimensions]
        overall = round(sum(scores) / max(len(scores), 1)) if scores else 0
    return {
        "overall_mastery": overall,
        "groups": groups,
        "hotspots": hotspots,
        "review_summary": review or {"total_due": 0, "overdue_count": 0},
    }


def _radar_dimensions(
    assessment_profile: dict[str, Any],
    mastery_dashboard: dict[str, Any],
    *,
    evidence_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    chapter_stats = _safe_dict(evidence_stats.get("chapter_stats"))
    mastery = _safe_dict(assessment_profile.get("chapter_mastery"))
    dimensions: list[dict[str, Any]] = []
    for key, value in mastery.items():
        item = _safe_dict(value)
        score = _safe_int(item.get("mastery") if item else value)
        name = _display_dimension_label(item.get("name") or key)
        if name:
            calibrated = _calibrated_mastery(
                score,
                _safe_dict(chapter_stats.get(name)),
            )
            _append_dimension(dimensions, name=name, score=calibrated)
    if dimensions:
        return dimensions
    for group in _safe_list(mastery_dashboard.get("groups")):
        for chapter in _safe_list(_safe_dict(group).get("chapters")):
            item = _safe_dict(chapter)
            name = _display_dimension_label(item.get("name"))
            if name:
                calibrated = _calibrated_mastery(
                    _safe_int(item.get("mastery")),
                    _safe_dict(chapter_stats.get(name)),
                )
                _append_dimension(dimensions, name=name, score=calibrated)
    return dimensions


def _append_dimension(dimensions: list[dict[str, Any]], *, name: str, score: int) -> None:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return
    value = round(max(0, min(int(score or 0), 100)) / 100, 2)
    for item in dimensions:
        if item.get("name") == normalized_name:
            item["value"] = max(float(item.get("value") or 0), value)
            return
    dimensions.append({"name": normalized_name, "value": value})


def _display_dimension_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    label = display_taxonomy_label(text, fallback=text)
    return str(label or text).strip()


def _calibrated_mastery(raw_score: int, stats: dict[str, Any]) -> int:
    """Apply evidence coverage caps so sparse signals cannot display as mastery."""

    raw = max(0, min(int(raw_score or 0), 100))
    attempts = _safe_int(stats.get("done"))
    correct = min(_safe_int(stats.get("correct")), attempts)
    if attempts <= 0:
        return min(raw, 60) if raw >= 90 else raw

    accuracy = correct / max(attempts, 1)
    if attempts == 1:
        cap = 60
    elif attempts == 2:
        cap = 72
    elif attempts <= 4:
        cap = 84
    elif attempts <= 7:
        cap = 92
    else:
        cap = 100 if accuracy >= 0.85 else 92

    if accuracy < 0.5:
        cap = min(cap, 40)
    elif accuracy < 0.7:
        cap = min(cap, 60)

    bayesian_estimate = round(((correct + 1) / (attempts + 2)) * 100)
    candidate = max(raw, bayesian_estimate) if raw else bayesian_estimate
    return max(0, min(candidate, cap))


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


def _question_text(*, payload: dict[str, Any], event: Any, index: int) -> str:
    text = str(
        payload.get("question_stem")
        or payload.get("stem")
        or payload.get("question_text")
        or payload.get("question")
        or ""
    ).strip()
    if text:
        return _clean_learning_text(text)
    focus = str(_safe_dict(payload.get("next_training_signal")).get("focus") or "").strip()
    if focus and not focus.isascii():
        return _clean_learning_text(focus)
    concept = _concept_label(_event_concept(payload))
    if concept:
        return f"{concept}练习题"
    question_id = str(payload.get("question_id") or getattr(event, "source_id", "") or "").strip()
    if question_id:
        return f"第 {index + 1} 次练习"
    return "一次练习"


def _question_title(*, payload: dict[str, Any], event: Any, index: int) -> str:
    return _truncate(_question_text(payload=payload, event=event, index=index), 34)


def _attempt_card_key(*, event: Any, payload: dict[str, Any], index: int) -> str:
    raw = "|".join(
        str(value or "").strip()
        for value in [
            getattr(event, "event_id", ""),
            getattr(event, "source_id", ""),
            payload.get("question_id"),
            getattr(event, "created_at", ""),
        ]
    )
    if not raw.strip("|"):
        raw = f"fallback-{index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"attempt-{digest}"


def _pick_attempt_explanation(payload: dict[str, Any], *, diagnosis: str, is_correct: bool) -> str:
    candidates = [
        payload.get("explanation"),
        payload.get("analysis"),
        payload.get("solution"),
        payload.get("answer_analysis"),
        payload.get("system_explanation"),
        payload.get("grading_explanation"),
        payload.get("feedback"),
        payload.get("summary"),
    ]
    for value in candidates:
        text = _clean_learning_text(_attempt_text_value(value))
        if text:
            return _truncate(text, 160)
    if is_correct:
        return "这题答对了，后续可以用同类变式题确认是否稳定掌握。"
    if diagnosis:
        return _truncate(f"先回看本题条件和选项边界：{diagnosis}", 160)
    return "这题已经进入错题证据，建议回看题干关键词、正确选项依据和易错干扰项。"


def _attempt_text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "explanation", "analysis", "summary", "message"):
            nested = _attempt_text_value(value.get(key))
            if nested:
                return nested
        return ""
    if isinstance(value, list):
        parts = [_attempt_text_value(item) for item in value]
        return " ".join(part for part in parts if part)
    return ""


def _option_items(options: Any) -> list[dict[str, str]]:
    mapped = _option_map(options)
    if not mapped:
        return []
    return [{"key": key, "text": _truncate(value, 36)} for key, value in sorted(mapped.items())]


def _primary_error_label(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        label = _error_label(error.get("error_code"))
        if label:
            return label
    return ""


def _primary_diagnosis(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        text = str(error.get("diagnosis") or error.get("evidence") or "").strip()
        if text:
            return text
    return ""


def _error_label(error_code: Any) -> str:
    code = str(error_code or "").strip().upper()
    if not code:
        return ""
    return _ERROR_LABELS.get(code) or "错因"


def _format_answer(value: Any, options: Any = None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return _truncate(_clean_learning_text(text), 28)
    option_map = _option_map(options)
    parts = []
    for letter in letters:
        option_text = option_map.get(letter)
        if option_text:
            parts.append(f"{letter}（{_truncate(option_text, 18)}）")
        else:
            parts.append(letter)
    return "、".join(parts)


def _format_letters(value: Any) -> str:
    if isinstance(value, list):
        letters = [str(item or "").strip().upper() for item in value if str(item or "").strip()]
        return "、".join(letters)
    return _format_answer(value)


def _option_map(options: Any) -> dict[str, str]:
    if isinstance(options, dict):
        return {str(key).strip().upper(): _clean_learning_text(value) for key, value in options.items() if str(key).strip()}
    if isinstance(options, list):
        mapped: dict[str, str] = {}
        for item in options:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or item.get("option") or "").strip().upper()
                value = item.get("text") or item.get("content") or item.get("value") or ""
                if key:
                    mapped[key] = _clean_learning_text(value)
        return mapped
    return {}


def _time_label(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "最近"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return "最近"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    local = parsed.astimezone(_TZ)
    today = datetime.now(_TZ).date()
    if local.date() == today:
        return f"今天 {local.strftime('%H:%M')}"
    if local.date() == today - timedelta(days=1):
        return f"昨天 {local.strftime('%H:%M')}"
    return local.strftime("%m月%d日 %H:%M")


def _attempt_evidence_label(index: int) -> str:
    if index == 0:
        return "最近一次批改"
    if index == 1:
        return "上一次批改"
    return f"第 {index + 1} 次批改"


def _clean_learning_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("practice /", "")
    text = text.replace("->", "→")
    for code, label in _ERROR_LABELS.items():
        text = text.replace(code, label)
    text = " ".join(text.split())
    return text


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


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


def _attempt_quality(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the quality dict from an event payload.

    For events produced before the quality-gate feature (schema_version < 1 or
    missing quality key), we derive a best-effort quality dict from the payload
    fields we can inspect.  This ensures backward compat while exposing the
    quality contract on all attempt cards.
    """
    stored = _safe_dict(payload.get("quality"))
    # If the stored quality already has the new fields, pass it through unchanged.
    if "detail_ready" in stored:
        return stored

    # --- Legacy path: derive quality from payload fields via single producer ---
    return compute_quality_signals(payload)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
