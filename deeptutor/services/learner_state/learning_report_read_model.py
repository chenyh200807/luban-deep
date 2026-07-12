from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import time
from typing import Any, Callable

from deeptutor.services.construction_grading.learning_evidence import compute_quality_signals
from deeptutor.services.experiments.cohort import current_stage, is_enabled
from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
from deeptutor.services.learner_state.evidence_lifecycle import (
    committed_retest_completion_ids,
    event_promotion_allowed,
    evidence_attempt_id,
)
from deeptutor.services.learner_state.home_personalization import (
    is_canonical_home_personalization_projection,
)
from deeptutor.services.learner_state.learning_brain_read_model import (
    build_learning_brain_read_model,
)
from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from deeptutor.services.learner_state.mastery_estimator import estimate_mastery
from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.personalization_context import (
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.prescription_outcome_read_model import (
    build_prescription_outcomes_read_projection,
)
from deeptutor.services.learner_state.progress_feedback import build_progress_feedback
from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    dispute_candidates_from_events,
)
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)
from deeptutor.services.learner_state.training_intent import (
    PRESCRIPTION_AUTHORITY,
    build_learning_training_intent,
)
from deeptutor.services.taxonomy.construction_taxonomy import (
    is_non_topic_label,
    normalize_taxonomy_code,
    student_facing_label,
    taxonomy_index,
    taxonomy_tree_stats,
    textbook_directory,
    textbook_topic_meta,
)
from deeptutor.services.taxonomy.learning_topic_resolver import canonical_learning_topic_label


def _build_scoring_point_map_from(*, events: list[Any], user_id: str) -> dict[str, Any]:
    """Batch C Task 7: thin composer — never grows beyond delegation."""
    return build_scoring_point_map_read_projection(events=events, user_id=user_id)


def _build_learning_state_from(*, events: list[Any]) -> dict[str, Any]:
    """Batch C Task 8: thin composer — exposes Task 4's three-layer
    projection at the top of the report so the view-model can read it
    without spelunking into learning_brain."""
    return project_three_layer_learning_state(events=events)


def _build_prescription_outcomes_from(*, events: list[Any]) -> list[dict[str, Any]]:
    """Batch D Task 9: thin composer over the sibling read projection."""
    return build_prescription_outcomes_read_projection(events=events)


def aggregate_attempts_by_label(events: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """§6-2 首页 mastery 收口的公开 seam：同一份 learning-evidence 过滤 +
    聚合逻辑喂 estimate_mastery（唯一 mastery 算子）。member_console 的
    首页/雷达/章节盘必须复用这里，不得自建第二套 attempts 聚合。"""
    return _aggregate_learning_evidence(_learning_evidence_events(list(events or [])))["attempts_by_label"]


def _build_pack_lifecycle_from(*, events: list[Any], weak_points: list[dict[str, Any]]) -> dict[str, Any]:
    """融合计划 §1：per-pack 生命周期投影（蓝环/掌握双轨）——thin composer。
    投影数据文件缺失时降级为空投影，不拖垮整份 report。"""
    try:
        from deeptutor.services.learner_state.pack_lifecycle_projection import (
            project_pack_lifecycle,
        )

        return project_pack_lifecycle(events=events, claims=weak_points)
    except Exception:
        return {
            "authority": "pack_lifecycle_projection.read_model",
            "packs": {},
            "unassigned_practice": [],
            "degraded": True,
        }


_TZ = timezone(timedelta(hours=8))
# Canonical schema id for register-before-use (schema-governance P2: this read model is
# this module's single schema authority — contracts/learning-report.md). The wire payload
# keeps the integer ``schema_version`` (1 default / 2 opt-in) for client compatibility; this
# string id makes the schema VISIBLE to the schema-registry closure so a competing
# learning-report schema can never appear unregistered. Registered as T2 runtime-canonical
# in contracts/schema_registry.yaml.
SCHEMA_ID = "learning_report_read_model.v2"
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
_DEICTIC_TOPIC_LABELS = {
    "这题",
    "那题",
    "本题",
    "该题",
    "此题",
    "题目",
    "当前题",
    "当前题目",
    "这个题",
    "那个题",
    "这道题",
    "那道题",
    "这一题",
    "那一题",
    "这道题目",
    "那道题目",
    "当前考点",
    "当前知识点",
}
_SOURCE_NAMES = (
    "today_progress",
    "home_dashboard",
    "assessment_profile",
    "mastery_dashboard",
    "learner_events",
    "note_assets",
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
_LSI_FLAG = "LEARNING_STATE_INFERENCE_V2"
_PROMPT_TOPIC_MARKERS = (
    "我想练习",
    "请严格围绕",
    "当前学习锚点",
    "出题",
    "training_mode",
    "mixed_rev",
    "那出",
)
_GENERIC_TRAINING_TOPICS = {"综合练习", "薄弱点", "错因", "待归因", "专项题"}


def build_learning_report_read_model(
    *,
    user_id: str,
    member_service: Any,
    learner_state_service: Any,
    mistake_book_service: Any | None = None,
    notebook_card_service: Any | None = None,
    event_limit: int = 100,
    schema_version: int = 1,
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
    assessment_profile = _sanitize_assessment_profile_topics(assessment_profile)
    mastery_dashboard = _sanitize_mastery_dashboard_topics(mastery_dashboard)
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
    bookmarked_event_ids = _bookmarked_event_ids(
        user_id=normalized_user,
        mistake_book_service=mistake_book_service,
    )
    mistake_book_projection = _mistake_book_projection(
        user_id=normalized_user,
        mistake_book_service=mistake_book_service,
    )
    note_assets = _note_assets_projection(
        user_id=normalized_user,
        notebook_card_service=notebook_card_service,
        source_status=source_status,
    )
    learner_facing = _learner_facing_payload(
        events=events,
        evidence_stats=evidence_stats,
        weak_points=weak_points,
        next_training=next_training,
        bookmarked_event_ids=bookmarked_event_ids,
    )
    training_prescription = _training_prescription_payload(
        learner_facing=learner_facing,
    )
    personalization_context = build_personalization_context_pack(
        user_id=normalized_user,
        learning_brain=learning_brain,
        active_training_intent=_safe_dict(_safe_dict(learner_facing.get("next_action")).get("intent")),
        recent_events=events,
    )
    learning_brain_degraded = learning_brain_source == "dry_run_learning_evidence"
    next_best_actions = _safe_list(personalization_context.get("next_best_action_candidates"))
    if learning_brain_degraded:
        next_best_actions = [_degraded_dry_run_action(action) for action in next_best_actions] or [
            _degraded_dry_run_action({})
        ]
        personalization_context = dict(personalization_context)
        personalization_context["next_best_action_candidates"] = next_best_actions
    truth_sections = _truth_sections(events)
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
        "overall_mastery": _overall_mastery_score(mastery),
    }

    window_truncated = evidence_stats["event_count"] >= limit
    degraded_sources = sorted(
        name for name, status in source_status.items() if status.get("ok") is False
    )
    degraded = bool(degraded_sources)
    flag_state = _learning_state_inference_flag_state(normalized_user)
    scoring_point_map = (
        _build_scoring_point_map_from(events=events, user_id=normalized_user)
        if flag_state["action_loop"]
        else _empty_scoring_point_map("feature_flag_off")
    )
    prescription_outcomes = _build_prescription_outcomes_from(events=events)
    learning_state = (
        _build_learning_state_from(events=events)
        if flag_state["state_projection"]
        else _empty_learning_state("feature_flag_off")
    )
    revalidation_queue = (
        build_revalidation_queue_projection(
            user_id=normalized_user,
            events=events,
            scoring_point_map=scoring_point_map,
            dispute_candidates=dispute_candidates_from_events(events),
            prescription_outcomes=prescription_outcomes,
        )
        if flag_state["verification"]
        else _empty_revalidation_queue("feature_flag_off")
    )

    report = {
        "ok": True,
        "user_id": normalized_user,
        "schema_version": _SCHEMA_VERSION,
        "authority": {
            "read_model": "learning-report-read-model",
            "progress_source": "learner_memory_events.learning_evidence",
            "learning_brain_source": learning_brain_source,
            "learning_brain_degraded": learning_brain_degraded,
            "personalization_context_source": "PersonalizationContextPack",
            "next_best_action_source": "training_intent",
            "note_assets_source": "learner_notebook_cards",
            "today_tasks_source": "learning-report-read-model.note_assets",
            "deprecated_page_sources": list(_DEPRECATED_PAGE_SOURCES),
        },
        "degraded": degraded,
        "degraded_sources": degraded_sources,
        "source_status": source_status,
        "feature_flags": flag_state,
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
        "study_plan": _study_plan_payload(
            home_dashboard=home_dashboard,
            learner_facing=learner_facing,
            next_training=next_training,
            training_prescription=training_prescription,
        ),
        "learning_brain": learning_brain,
        "learner_facing": learner_facing,
        "truth_sections": truth_sections,
        "personalization_context": personalization_context,
        "next_best_actions": next_best_actions,
        "next_training": next_training,
        "training_prescription": training_prescription,
        "note_assets": note_assets,
        "today_tasks": _today_tasks_from_note_assets(note_assets),
        # Batch C Task 7: scoring point map projection (read-only sibling).
        "scoring_point_map": scoring_point_map,
        "prescription_outcomes": prescription_outcomes,
        "revalidation_queue": revalidation_queue,
        # Batch C Task 8: three-layer learning state (Task 4 projection)
        # exposed at top level so the student page view-model can render
        # state -> reason -> action -> evidence without traversing into
        # learning_brain internals.
        "learning_state": learning_state,
        # 融合计划 §1：per-pack 生命周期（未学/已学·待验证/练过/真懂/休眠）——
        # 蓝环（接触轨）与红黄绿（掌握轨）拆开，供前端第 11 轮增量稿消费。
        "pack_lifecycle": _build_pack_lifecycle_from(events=events, weak_points=weak_points),
        # D-class: student-visible long-term analytics (recurrent errors + trend).
        # Pure read projection — derived from learning_brain.weak_points.occurrence_timeline.
        "long_term_analytics": _build_long_term_analytics(learning_brain),
        "legacy_compat": {
            "today_progress": legacy_today,
            "home_dashboard": home_dashboard,
            "assessment_profile": assessment_profile,
            "mastery_dashboard": mastery_dashboard,
        },
    }
    report["grading_to_brain_loop"] = _build_grading_to_brain_loop(report)
    if int(schema_version or 1) == 2:
        return _learning_report_v2(
            report,
            mistake_book_projection=mistake_book_projection,
            evidence_stats=evidence_stats,
        )
    return report


def _build_grading_to_brain_loop(report: dict[str, Any]) -> dict[str, Any]:
    """Student/product-facing Grading-to-Brain loop projection.

    This is deliberately a read-only composer over existing authorities:
    grading evidence -> Learning Brain -> PersonalizationContextPack ->
    training_intent/revalidation -> prescription outcome.
    """
    freshness = _safe_dict(report.get("freshness"))
    learning_brain = _safe_dict(report.get("learning_brain"))
    personalization = _safe_dict(report.get("personalization_context"))
    next_best_actions = _safe_list(report.get("next_best_actions"))
    prescription_outcomes = _safe_list(report.get("prescription_outcomes"))
    revalidation_queue = _safe_dict(report.get("revalidation_queue"))
    learner_facing = _safe_dict(report.get("learner_facing"))

    primary_outcome = _safe_dict(prescription_outcomes[0] if prescription_outcomes else {})
    next_action = _safe_dict(next_best_actions[0] if next_best_actions else {})
    top_claims = _safe_list(personalization.get("top_claims"))
    weak_points = _safe_list(learning_brain.get("weak_points"))
    observed = _safe_list(learning_brain.get("observed_candidates"))
    stale_claims = _safe_list(learning_brain.get("stale_claims"))
    improvements = _safe_list(learning_brain.get("improvement_signals"))
    compiled_objects = learning_brain.get("compiled_objects")
    if isinstance(compiled_objects, dict):
        compiled_count = len(compiled_objects)
    else:
        compiled_count = len(_safe_list(compiled_objects))

    evidence_refs = _dedupe_strings(
        _safe_list(primary_outcome.get("evidence_refs"))
        or _safe_list(next_action.get("evidence_refs"))
        or _evidence_refs_from_learner_facing(learner_facing)
    )
    event_count = _safe_int(freshness.get("event_count"))
    claim_count = len(top_claims) or len(weak_points) or len(observed) or len(stale_claims) or compiled_count
    has_personalization = bool(
        personalization.get("source") == "PersonalizationContextPack"
        or personalization.get("authority")
        or top_claims
        or personalization.get("feedback_guidance")
    )
    has_next_action = bool(next_action or _safe_dict(learner_facing.get("next_action")).get("title"))
    queue_items = _safe_list(revalidation_queue.get("items"))

    outcome_status = str(primary_outcome.get("status") or "").strip()
    if improvements or outcome_status == "verified":
        status = "improved"
    elif queue_items:
        status = "needs_retest"
    elif has_next_action:
        status = "action_ready"
    elif claim_count:
        status = "claim_ready"
    elif event_count:
        status = "evidence_ready"
    else:
        status = "needs_first_grading"

    next_required_action = str(primary_outcome.get("next_required_action") or "").strip()
    if not next_required_action:
        if queue_items:
            next_required_action = "complete_revalidation_probe"
        elif has_next_action:
            next_required_action = "start_next_action"
        elif event_count:
            next_required_action = "wait_for_learning_brain_projection"
        else:
            next_required_action = "submit_first_case_answer"

    stages = [
        {
            "key": "grading_result",
            "label": "本次批改",
            "status": "ready" if event_count else "missing",
            "evidence_count": event_count,
            "authority": "learner_memory_events.learning_evidence",
        },
        {
            "key": "learning_evidence",
            "label": "学习证据",
            "status": "ready" if event_count else "missing",
            "evidence_refs": evidence_refs[:5],
            "authority": "learner_memory_events.learning_evidence",
        },
        {
            "key": "learner_claim",
            "label": "长期画像",
            "status": "ready" if claim_count else "pending",
            "claim_count": claim_count,
            "authority": "LearningBrainReadModel",
        },
        {
            "key": "personalization_context",
            "label": "个性化上下文",
            "status": "ready" if has_personalization else "pending",
            "authority": "PersonalizationContextPack",
        },
        {
            "key": "next_action",
            "label": "下一步动作",
            "status": "ready" if has_next_action else "pending",
            "action_type": str(next_action.get("action_type") or ""),
            "authority": "training_intent",
        },
        {
            "key": "retest",
            "label": "复测结果",
            "status": "verified" if outcome_status == "verified" else ("due" if queue_items else "pending"),
            "next_required_action": next_required_action,
            "authority": "prescription_outcomes",
        },
    ]

    return {
        "status": status,
        "next_required_action": next_required_action,
        "evidence_refs": evidence_refs[:8],
        "current_action": {
            "title": str(next_action.get("title") or _safe_dict(learner_facing.get("next_action")).get("title") or "").strip(),
            "action_type": str(next_action.get("action_type") or "").strip(),
            "prescription_authority": str(next_action.get("prescription_authority") or PRESCRIPTION_AUTHORITY),
        },
        "latest_outcome": {
            "training_intent_id": str(primary_outcome.get("training_intent_id") or "").strip(),
            "status": outcome_status,
            "score_ratio": primary_outcome.get("score_ratio"),
            "verified_at": str(primary_outcome.get("verified_at") or "").strip(),
        },
        "stages": stages,
        "authority": {
            "grading_evidence": "learner_memory_events.learning_evidence",
            "learner_model": "LearningBrainReadModel",
            "personalization": "PersonalizationContextPack",
            "action": "training_intent",
            "retest": "prescription_outcomes",
        },
        "source_status": {
            "degraded": bool(report.get("degraded")),
            "learning_brain_degraded": bool(_safe_dict(report.get("authority")).get("learning_brain_degraded")),
        },
    }


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _evidence_refs_from_learner_facing(learner_facing: dict[str, Any]) -> list[str]:
    refs: list[Any] = []
    for attempt in _safe_list(learner_facing.get("recent_attempts")):
        item = _safe_dict(attempt)
        refs.append(item.get("key"))
    for evidence in _safe_list(learner_facing.get("evidence_timeline")):
        item = _safe_dict(evidence)
        refs.append(item.get("key"))
    return _dedupe_strings(refs)


def _build_long_term_analytics(learning_brain: dict[str, Any]) -> dict[str, Any]:
    """D-class: project student-visible long-term analytics from learning_brain.weak_points.

    Purely read — derives from occurrence_timeline already on each weak_point.
    No new DB reads, no new authority, append-only section on the report.
    """
    weak_points = list((learning_brain or {}).get("weak_points") or [])

    recurrent_errors: list[dict[str, Any]] = []
    for wp in weak_points:
        timeline = list(wp.get("occurrence_timeline") or [])
        if len(timeline) < 2:
            continue
        dates = sorted(str(e.get("observed_at") or "") for e in timeline)
        recurrent_errors.append({
            "concept_id": str(wp.get("concept_id") or ""),
            "error_code": str(wp.get("error_code") or ""),
            "occurrence_count": len(timeline),
            "first_seen_at": dates[0],
            "last_seen_at": dates[-1],
        })
    recurrent_errors.sort(key=lambda x: (-x["occurrence_count"], x["last_seen_at"]))

    active_weak_count = len(weak_points)
    recurrent_count = len(recurrent_errors)
    if recurrent_count == 0:
        trend = "improving"
    elif recurrent_count > max(1, active_weak_count // 2):
        trend = "declining"
    else:
        trend = "stable"

    return {
        "recurrent_errors": recurrent_errors,
        "progression_summary": {
            "trend_direction": trend,
            "active_weak_count": active_weak_count,
            "recurrent_error_count": recurrent_count,
        },
    }


def _learning_state_inference_flag_state(user_id: str) -> dict[str, Any]:
    enabled = is_enabled(_LSI_FLAG, user_id=user_id)
    return {
        "flag": _LSI_FLAG,
        "stage": current_stage(_LSI_FLAG),
        "enabled": enabled,
        "evidence": enabled and is_enabled(f"{_LSI_FLAG}.evidence", user_id=user_id),
        "state_projection": enabled and is_enabled(f"{_LSI_FLAG}.state_projection", user_id=user_id),
        "action_loop": enabled and is_enabled(f"{_LSI_FLAG}.action_loop", user_id=user_id),
        "verification": enabled and is_enabled(f"{_LSI_FLAG}.verification", user_id=user_id),
    }


def _overall_mastery_score(mastery: dict[str, Any]) -> int:
    overall = _safe_dict(mastery.get("overall_mastery"))
    if overall:
        return _safe_int(overall.get("score"))
    return _safe_int(mastery.get("overall_mastery"))


def _empty_scoring_point_map(reason: str) -> dict[str, Any]:
    return {
        "items": [],
        "empty_state": "rubric_pending",
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "model": "rule_based_v1",
            "degraded": True,
            "blocked_reason": reason,
        },
    }


def _empty_learning_state(reason: str) -> dict[str, Any]:
    return {
        "knowledge_state": [],
        "ability_state": [],
        "behavior_state": [],
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "model": "rule_based_v1",
            "degraded": True,
            "blocked_reason": reason,
        },
    }


def _empty_revalidation_queue(reason: str) -> dict[str, Any]:
    return {
        "items": [],
        "source_status": {
            "authority": "learner_memory_events.learning_evidence -> mastery_estimator -> training_intent",
            "model": "rule_based_arrs_v1",
            "daily_capacity": 1,
            "candidate_count": 0,
            "due_count": 0,
            "blocked_reasons": [reason],
        },
    }


def _note_assets_projection(
    *,
    user_id: str,
    notebook_card_service: Any | None,
    source_status: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if notebook_card_service is None:
        source_status["note_assets"] = _idle_status()
        return {
            "items": [],
            "count": 0,
            "source_status": {
                "ok": None,
                "authority": "learner_notebook_cards",
                "reason": "notebook_card_service_not_configured",
            },
        }
    lister = getattr(notebook_card_service, "list_cards", None)
    if not callable(lister):
        source_status["note_assets"] = {"ok": False, "latency_ms": 0, "error": "list_cards_unavailable"}
        return {
            "items": [],
            "count": 0,
            "source_status": {
                "ok": False,
                "authority": "learner_notebook_cards",
                "reason": "list_cards_unavailable",
            },
        }
    try:
        cards = list(lister(user_id) or [])
    except Exception as exc:
        source_status["note_assets"] = {"ok": False, "latency_ms": 0, "error": type(exc).__name__}
        return {
            "items": [],
            "count": 0,
            "source_status": {
                "ok": False,
                "authority": "learner_notebook_cards",
                "reason": type(exc).__name__,
            },
        }
    items = [_note_asset_item(card, index) for index, card in enumerate(cards[:20])]
    source_status["note_assets"] = {"ok": True, "latency_ms": 0, "error": None, "count": len(items)}
    return {
        "items": items,
        "count": len(items),
        "source_status": {
            "ok": True,
            "authority": "learner_notebook_cards",
            "generated_at": datetime.now(_TZ).isoformat(),
        },
    }


def _note_asset_item(card: dict[str, Any], index: int) -> dict[str, Any]:
    source_ref = _safe_dict(card.get("source_ref"))
    card_type = str(card.get("card_type") or "manual_note").strip() or "manual_note"
    summary = str(_safe_dict(card.get("ai_enhanced_content")).get("summary") or "").strip()
    has_source_ref = bool(
        str(source_ref.get("event_id") or source_ref.get("attempt_ref") or source_ref.get("turn_id") or "").strip()
    )
    action = _note_asset_action(card_type=card_type, source_ref=source_ref)
    return {
        "key": str(card.get("note_id") or f"note-{index}").strip(),
        "note_id": str(card.get("note_id") or "").strip(),
        "card_type": card_type,
        "title": str(card.get("title") or "学习卡片").strip()[:80],
        "summary": summary[:180],
        "subject_id": str(card.get("subject_id") or "").strip(),
        "source_type": str(card.get("source_type") or "").strip(),
        "source_linked": has_source_ref,
        "source_label": "来自一次批改/答疑" if has_source_ref else "",
        "evidence_label": "可追溯到原始学习证据" if has_source_ref else "",
        "action": action,
        "updated_at": str(card.get("updated_at") or "").strip(),
        "version": _safe_int(card.get("version")) or 1,
    }


def _note_asset_action(*, card_type: str, source_ref: dict[str, Any]) -> dict[str, Any]:
    attempt_ref = str(source_ref.get("attempt_ref") or "").strip()
    turn_id = str(source_ref.get("turn_id") or "").strip()
    if card_type in {"scoring_card", "error_pattern_note"}:
        return {
            "label": "重新作答" if attempt_ref else "练同类题",
            "type": "reanswer" if attempt_ref else "probe",
            "attempt_ref": attempt_ref,
            "entry_source": "note_asset",
        }
    return {
        "label": "测一下",
        "type": "probe",
        "turn_id": turn_id,
        "entry_source": "note_asset",
    }


def _today_tasks_from_note_assets(note_assets: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for asset in _safe_list(note_assets.get("items")):
        item = _safe_dict(asset)
        action = _safe_dict(item.get("action"))
        note_id = str(item.get("note_id") or "").strip()
        if not note_id or not action:
            continue
        tasks.append(
            {
                "task_id": f"note:{note_id}",
                "title": str(item.get("title") or "复习学习卡片").strip()[:80],
                "subtitle": str(item.get("summary") or item.get("source_label") or "").strip()[:120],
                "source": "note_assets",
                "note_id": note_id,
                "action": action,
            }
        )
        if len(tasks) >= 3:
            break
    return tasks


def _learning_report_v2(
    report: dict[str, Any],
    *,
    mistake_book_projection: dict[str, Any],
    evidence_stats: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(report)
    learner_facing = _safe_dict(payload.get("learner_facing"))
    attempts = _safe_list(learner_facing.get("recent_attempts"))
    timeline = _safe_list(learner_facing.get("evidence_timeline"))
    loops = _safe_list(learner_facing.get("training_loops"))
    next_action = _safe_dict(learner_facing.get("next_action"))
    overview = _safe_dict(payload.get("overview"))
    mastery = _safe_dict(payload.get("mastery"))
    home_dashboard = _safe_dict(_safe_dict(payload.get("legacy_compat")).get("home_dashboard"))
    home_projection = _safe_dict(home_dashboard.get("home_projection") or home_dashboard.get("projection"))
    if is_canonical_home_personalization_projection(home_projection):
        home_source_status = _safe_dict(home_projection.get("source_status"))
        home_prompts = _safe_list(home_projection.get("recommended_prompts"))
    else:
        home_source_status = {}
        home_prompts = []
    summary = _safe_dict(learner_facing.get("summary"))
    primary_focus = (
        str(next_action.get("concept") or "").strip()
        or str(summary.get("primary_focus") or "").strip()
        or str(overview.get("focus_hint") or "").strip()
    )
    hero_title = primary_focus or "完成一次练习后生成重点"
    payload["schema_version"] = 2
    payload["authority"] = {
        **_safe_dict(payload.get("authority")),
        "conversation_source": "learner_memory_events.learning_evidence[evidence_source=conversation_synthesis]",
        "attempt_detail_source": "attempt-detail-read-model",
        "mistake_book_source": "learner_mistake_book_items",
        "training_intent_source": "learning-report-read-model",
        "home_context_source": "home_dashboard.today_focus/recommended_prompts",
    }
    payload["recent_attempts"] = attempts
    payload["timeline"] = timeline
    payload["training_loop_cards"] = loops
    payload["attempts"] = [_attempt_v2(item) for item in attempts]
    payload["hero"] = {
        "stage_label": str(overview.get("learner_level") or "学习阶段").strip() or "学习阶段",
        "headline": f"当前最该补：{hero_title}",
        "subline": str(summary.get("headline") or "").strip(),
        "primary_cta": {
            "label": str(next_action.get("cta") or "开始训练"),
            "intent": _safe_dict(next_action.get("intent")) or build_learning_training_intent(
                user_id=str(payload.get("user_id") or ""),
                concept_label=primary_focus,
                source="learning_report",
                reason="v2_hero",
            ),
        },
    }
    payload["home_personalization"] = {
        "focus_ref": "home_dashboard.today_focus",
        "recommended_prompt_count": len(home_prompts),
        "latest_conversation_signal": "",
        "source_status": home_source_status,
    }
    payload["today_prescription"] = _today_prescription_v2(
        training_prescription=_safe_dict(payload.get("training_prescription")),
        next_best_actions=_safe_list(payload.get("next_best_actions")),
    )
    payload["mistake_book"] = mistake_book_projection
    payload["next_training"] = _next_training_v2(next_action=next_action, existing=_safe_list(payload.get("next_training")))
    payload["mastery"] = _mastery_v2(mastery, overview=overview, evidence_stats=evidence_stats)
    payload["learning_brain"] = _compact_learning_brain_v2(_safe_dict(payload.get("learning_brain")))
    payload["i18n_keys"] = {
        "locale": "zh-CN",
        "hero.headline": "learning_report.hero.headline",
        "attempt.result": "learning_report.attempt.result",
        "next_training.title": "learning_report.next_training.title",
    }
    return payload


def _compact_learning_brain_v2(learning_brain: dict[str, Any]) -> dict[str, Any]:
    """Keep v2 mobile payload learner-facing and bounded.

    v1 still exposes the full Learning Brain projection. v2 clients consume
    normalized report surfaces, so carrying compiled_objects and full evidence
    chains only inflates setData/network cost without adding learner value.
    """

    sections = _safe_dict(learning_brain.get("visible_sections"))
    graph_chain = _safe_dict(learning_brain.get("graph_chain"))
    synthesis_run = _safe_dict(learning_brain.get("synthesis_run"))
    output_projection_hash = str(
        learning_brain.get("output_projection_hash") or synthesis_run.get("output_projection_hash") or ""
    ).strip()
    return {
        "ok": bool(learning_brain.get("ok", True)),
        "projection_subject": str(learning_brain.get("projection_subject") or "").strip(),
        "schema_version": _safe_int(learning_brain.get("schema_version")) or 2,
        "output_projection_hash": output_projection_hash,
        "synthesis_run": {
            "output_projection_hash": output_projection_hash,
            "status": str(synthesis_run.get("status") or "").strip(),
            "input_event_count": _safe_int(synthesis_run.get("input_event_count")),
        },
        "weak_points": [
            _compact_weak_point(item)
            for item in _safe_list(learning_brain.get("weak_points"))[:5]
            if isinstance(item, dict)
        ],
        "visible_sections": {
            "current_truth": [
                _compact_visible_truth(item, index=index)
                for index, item in enumerate(_safe_list(sections.get("current_truth"))[:6])
                if isinstance(item, dict)
            ],
            "evidence_flow": [
                _compact_visible_evidence(item, index=index)
                for index, item in enumerate(_safe_list(sections.get("evidence_flow"))[:6])
                if isinstance(item, dict)
            ],
            "next_training": [
                _compact_next_training(item, index=index)
                for index, item in enumerate(_safe_list(sections.get("next_training"))[:5])
                if isinstance(item, dict)
            ],
        },
        "graph_chain": {
            "has_training_uses_question": bool(graph_chain.get("has_training_uses_question")),
            "has_training_improved_error": bool(graph_chain.get("has_training_improved_error")),
            "has_training_not_improved_error": bool(graph_chain.get("has_training_not_improved_error")),
            "training_uses_question": [
                _compact_graph_edge(item, index=index)
                for index, item in enumerate(_safe_list(graph_chain.get("training_uses_question"))[:4])
                if isinstance(item, dict)
            ],
            "training_improved_error": [
                _compact_graph_edge(item, index=index)
                for index, item in enumerate(_safe_list(graph_chain.get("training_improved_error"))[:4])
                if isinstance(item, dict)
            ],
            "training_not_improved_error": [
                _compact_graph_edge(item, index=index)
                for index, item in enumerate(_safe_list(graph_chain.get("training_not_improved_error"))[:4])
                if isinstance(item, dict)
            ],
        },
        "event_count": _safe_int(learning_brain.get("event_count")),
        "created_claim_count": _safe_int(learning_brain.get("created_claim_count")),
        "typed_graph_edge_count": _safe_int(learning_brain.get("typed_graph_edge_count")),
    }


def _today_prescription_v2(
    *,
    training_prescription: dict[str, Any],
    next_best_actions: list[Any],
) -> dict[str, Any]:
    top_action = _safe_dict(next_best_actions[0] if next_best_actions else {})
    intent_id = str(training_prescription.get("training_intent_id") or top_action.get("training_intent_id") or "").strip()
    source = str(
        top_action.get("source")
        if top_action.get("degraded") or top_action.get("source") == "dry_run_fallback"
        else training_prescription.get("source") or top_action.get("source") or "training_intent"
    ).strip()
    evidence_refs = _safe_list(training_prescription.get("evidence_refs")) or _safe_list(top_action.get("evidence_refs"))
    action_type = "starter_action" if not evidence_refs else "retest_training"
    if source == "dry_run_fallback":
        action_type = "starter_action"
    return {
        "title": str(training_prescription.get("title") or top_action.get("title") or "先补一条可诊断证据").strip(),
        "why_this_now": str(
            top_action.get("why_this_now")
            or training_prescription.get("why_this")
            or training_prescription.get("subtitle")
            or ""
        ).strip(),
        "evidence_refs": evidence_refs[:5],
        "source": source,
        "prescription_authority": PRESCRIPTION_AUTHORITY,
        "degraded": bool(source == "dry_run_fallback" or training_prescription.get("degraded") or top_action.get("degraded")),
        "primary_action": {
            "type": action_type,
            "intent_id": intent_id,
            "prescription_authority": PRESCRIPTION_AUTHORITY,
        },
    }


def _compact_weak_point(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept_id": str(item.get("concept_id") or "").strip(),
        "label": str(item.get("label") or item.get("display_title") or "").strip(),
        "evidence_level": str(item.get("evidence_level") or "").strip(),
        "memory_lifecycle_stage": str(item.get("memory_lifecycle_stage") or "").strip(),
        "memory_lifecycle_label": str(item.get("memory_lifecycle_label") or "").strip(),
        "confidence": item.get("confidence"),
        "recommended_training": _safe_dict(item.get("recommended_training")),
    }


def _compact_visible_truth(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "key": str(item.get("key") or f"truth-{index}"),
        "current_truth": str(item.get("current_truth") or "").strip(),
        "evidence_level": str(item.get("evidence_level") or "").strip(),
        "evidence_level_label": str(item.get("evidence_level_label") or "").strip(),
        "memory_lifecycle_stage": str(item.get("memory_lifecycle_stage") or "").strip(),
        "memory_lifecycle_label": str(item.get("memory_lifecycle_label") or "").strip(),
        "confidence": item.get("confidence"),
        "display_title": str(item.get("display_title") or item.get("current_truth") or "").strip(),
        "display_meta": str(item.get("display_meta") or "").strip(),
        "supporting_event_labels": _safe_list(item.get("supporting_event_labels"))[:3],
    }


def _compact_visible_evidence(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "key": str(item.get("key") or f"evidence-{index}"),
        "display_label": str(item.get("display_label") or item.get("display_title") or "").strip(),
        "display_title": str(item.get("display_title") or "").strip(),
        "display_path": str(item.get("display_path") or "").strip(),
        "tone": str(item.get("tone") or "").strip(),
    }


def _compact_next_training(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "key": str(item.get("key") or f"training-{index}"),
        "display_title": str(item.get("display_title") or item.get("title") or "").strip(),
        "display_meta": str(item.get("display_meta") or item.get("reason") or "").strip(),
        "intent": _safe_dict(item.get("intent")),
    }


def _compact_graph_edge(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "key": str(item.get("key") or f"edge-{index}"),
        "edge_type": str(item.get("edge_type") or "").strip(),
        "display_path": str(item.get("display_path") or "").strip(),
        "display_meta": str(item.get("display_meta") or "").strip(),
    }


def _attempt_v2(item: Any) -> dict[str, Any]:
    attempt = _safe_dict(item)
    return {
        "attempt_key": str(attempt.get("key") or "").strip(),
        "attempt_ref": str(attempt.get("attempt_ref") or "").strip(),
        "subject_id": str(attempt.get("subject_id") or "").strip(),
        "bot_id": str(attempt.get("bot_id") or "").strip(),
        "time_label": str(attempt.get("time_label") or "").strip(),
        "question_title": str(attempt.get("title") or "").strip(),
        "question_preview": str(attempt.get("question_text") or attempt.get("title") or "").strip(),
        "result_label": str(attempt.get("result_label") or "").strip(),
        "answer_line": str(attempt.get("answer_line") or "").strip(),
        "diagnosis": str(attempt.get("diagnosis") or "").strip(),
        "why_it_matters": str(attempt.get("diagnosis_detail") or attempt.get("explanation") or "").strip(),
        "is_bookmarked": bool(attempt.get("is_bookmarked")),
        "actions": {
            "detail": bool(attempt.get("attempt_ref")),
            "bookmark": bool(attempt.get("collectable")),
            "retry": True,
        },
    }


def _next_training_v2(*, next_action: dict[str, Any], existing: list[Any]) -> list[dict[str, Any]]:
    if next_action.get("title"):
        return [
            {
                "title": str(next_action.get("title") or "").strip(),
                "reason": str(next_action.get("subtitle") or "").strip(),
                "estimated_minutes": _safe_int(next_action.get("estimated_minutes")),
                "intent": _safe_dict(next_action.get("intent")),
            }
        ]
    items = []
    for index, item in enumerate(existing[:5]):
        source = _safe_dict(item)
        title = str(source.get("display_title") or source.get("title") or source.get("claim") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "reason": str(source.get("display_meta") or source.get("reason") or "").strip(),
                "estimated_minutes": _safe_int(source.get("estimated_minutes")) or 8,
                "intent": _safe_dict(source.get("intent")),
                "key": str(source.get("key") or f"training-{index}"),
            }
        )
    return items


def _mastery_v2(
    mastery: dict[str, Any],
    *,
    overview: dict[str, Any],
    evidence_stats: dict[str, Any],
) -> dict[str, Any]:
    groups = _safe_list(mastery.get("groups"))
    hotspots = _safe_list(mastery.get("hotspots"))
    attempts_by_label = _safe_dict(evidence_stats.get("attempts_by_label"))
    dimensions = []
    for group in groups:
        for chapter in _safe_list(_safe_dict(group).get("chapters")):
            item = _safe_dict(chapter)
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            estimate = estimate_mastery(
                attempts=_safe_list(attempts_by_label.get(name)),
                legacy_score=item.get("mastery"),
            )
            dimensions.append(
                {
                    "name": name,
                    **estimate,
                }
            )
    if not dimensions:
        for item in hotspots:
            hotspot = _safe_dict(item)
            name = str(hotspot.get("name") or "").strip()
            if not name:
                continue
            estimate = estimate_mastery(
                attempts=_safe_list(attempts_by_label.get(name)),
                legacy_score=hotspot.get("mastery"),
            )
            dimensions.append(
                {
                    "name": name,
                    **estimate,
                }
            )
    overall_score = _safe_int(mastery.get("overall_mastery") if not isinstance(mastery.get("overall_mastery"), dict) else mastery.get("overall_mastery", {}).get("score"))
    if not overall_score:
        overall_score = _safe_int(overview.get("overall_mastery"))
    overall_estimate = estimate_mastery(
        attempts=_safe_list(evidence_stats.get("attempts")),
        legacy_score=overall_score,
    )
    return {
        **mastery,
        "overall_mastery": overall_estimate,
        "dimensions": dimensions,
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
    return _dedupe_learning_evidence_events([
        event
        for event in list(events or [])
        if str(getattr(event, "memory_kind", "") or "") == "learning_evidence"
        and _is_learning_evidence_payload(event)
    ])


def _dedupe_learning_evidence_events(events: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for event in events:
        key = _learning_evidence_identity(event)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _learning_evidence_identity(event: Any) -> str:
    dedupe_key = str(getattr(event, "dedupe_key", "") or "").strip()
    if dedupe_key:
        return f"dedupe:{dedupe_key}"
    payload = _safe_dict(getattr(event, "payload_json", {}))
    raw = {
        "source_id": str(getattr(event, "source_id", "") or ""),
        "turn_id": payload.get("turn_id"),
        "session_id": payload.get("session_id"),
        "question_id": payload.get("question_id"),
        "question_type": payload.get("question_type"),
        "user_answer": payload.get("user_answer"),
        "score_awarded": payload.get("score_awarded"),
        "max_score": payload.get("max_score"),
        "error_events": payload.get("error_events") or payload.get("errors") or [],
    }
    digest = hashlib.sha1(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"fingerprint:{digest}"


def _is_learning_evidence_payload(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return (
        str(payload.get("event_type") or "") == "learning_evidence"
        or str(getattr(event, "source_feature", "") or "") == "construction_grading"
    )


def _is_progress_countable_event(event: Any) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if str(payload.get("evidence_source") or "").strip() == "conversation_synthesis":
        return False
    quality = _safe_dict(payload.get("quality"))
    if quality.get("progress_countable") is False:
        return False
    return True


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
    attempts: list[dict[str, Any]] = []
    attempts_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        event_count += 1
        if not _is_progress_countable_event(event):
            continue
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
        attempt_payload = _mastery_attempt_payload(event=event, payload=payload)
        attempts.append(attempt_payload)
        if label:
            stats = chapter_stats.setdefault(label, {"done": 0, "correct": 0, "last_activity_at": ""})
            stats["done"] += 1
            if _is_correct(payload):
                stats["correct"] += 1
            if created_at and created_at > str(stats.get("last_activity_at") or ""):
                stats["last_activity_at"] = created_at
            attempts_by_label[label].append(attempt_payload)

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
        "attempts": attempts,
        "attempts_by_label": {key: list(value) for key, value in attempts_by_label.items()},
    }


def _mastery_attempt_payload(*, event: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": str(getattr(event, "event_id", "") or payload.get("turn_id") or ""),
        "question_id": str(payload.get("question_id") or getattr(event, "source_id", "") or ""),
        "created_at": str(getattr(event, "created_at", "") or ""),
        "score_awarded": payload.get("score_awarded"),
        "max_score": payload.get("max_score"),
        "difficulty": payload.get("difficulty")
        or payload.get("question_difficulty")
        or payload.get("difficulty_level")
        or "medium",
        "quality": _safe_dict(payload.get("quality")),
        "evidence_source": str(payload.get("evidence_source") or getattr(event, "source_feature", "") or ""),
    }


def _event_concept(payload: dict[str, Any]) -> str:
    canonical_topic = _safe_dict(payload.get("canonical_topic"))
    canonical = str(
        canonical_topic.get("label")
        or canonical_topic.get("taxonomy_code")
        or canonical_topic.get("taxonomy_id")
        or ""
    ).strip()
    if canonical:
        return canonical
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


def _study_plan_payload(
    *,
    home_dashboard: dict[str, Any],
    learner_facing: dict[str, Any],
    next_training: list[dict[str, Any]],
    training_prescription: dict[str, Any],
) -> dict[str, Any]:
    plan = _safe_dict(home_dashboard.get("study_plan"))
    plan = _canonicalized_study_plan(plan)
    prescription_plan = _study_plan_from_prescription(training_prescription)
    if any(
        str(plan.get(key) or "").strip()
        for key in ("focus_topic", "priority_task", "study_method", "time_budget", "coach_note")
    ):
        if _is_student_safe_study_plan(plan):
            return plan
        if prescription_plan:
            return prescription_plan

    if prescription_plan:
        return prescription_plan

    next_action = _safe_dict(learner_facing.get("next_action"))
    summary = _safe_dict(learner_facing.get("summary"))
    focus_topic = (
        str(next_action.get("concept") or "").strip()
        or str(summary.get("primary_focus") or "").strip()
        or str(_safe_dict(home_dashboard.get("today_focus")).get("title") or "").strip()
    )
    focus_topic = canonical_learning_topic_label(focus_topic)
    priority_task = str(next_action.get("title") or "").strip()
    coach_note = str(next_action.get("subtitle") or "").strip()
    estimated_minutes = _safe_int(next_action.get("estimated_minutes"))

    if not focus_topic and next_training:
        item = _safe_dict(next_training[0])
        focus_topic = _clean_learning_text(
            item.get("display_title") or item.get("claim") or ""
        )
        coach_note = coach_note or _clean_learning_text(
            item.get("display_meta") or item.get("display_label") or ""
        )

    if not (focus_topic or priority_task or coach_note):
        return {}

    return {
        "focus_topic": focus_topic or "今天先完成一轮诊断练习",
        "priority_task": priority_task or "先完成一组专项训练",
        "study_method": "先按错因做专项题，再回看当时解析，最后用一题复测确认",
        "time_budget": f"约 {estimated_minutes} 分钟" if estimated_minutes > 0 else "约 10 分钟",
        "coach_note": coach_note or "完成后系统会继续更新你的学情判断",
        "source": "learning_report_next_training",
    }


def _training_prescription_payload(*, learner_facing: dict[str, Any]) -> dict[str, Any]:
    next_action = _safe_dict(learner_facing.get("next_action"))
    intent = _safe_dict(next_action.get("intent"))
    topic = _student_safe_topic(
        intent.get("concept_label") or next_action.get("concept") or ""
    )
    error_label = _clean_learning_text(
        intent.get("error_label") or next_action.get("error") or ""
    ) or "错因"
    evidence_refs = _safe_list(intent.get("evidence_refs") or intent.get("attempt_refs"))
    evidence_count = len([item for item in evidence_refs if str(item or "").strip()])
    status = str(intent.get("status") or "").strip() or "degraded"
    if not topic or evidence_count <= 0:
        status = "degraded"
    if status == "degraded":
        has_existing_evidence = evidence_count > 0
        return {
            "status": "degraded",
            "source": "training_intent",
            "title": "补一题可诊断练习" if has_existing_evidence else "先补一条可诊断证据",
            "subtitle": (
                f"已有 {evidence_count} 条学习证据，但还缺少稳定的题目主题"
                if has_existing_evidence
                else "完成 1 题后，系统会把题目、作答和错因合成可训练主题"
            ),
            "display_topic": "",
            "error_label": "",
            "why_this": (
                f"系统已看到 {evidence_count} 条作答记录，但题目主题或错因链还不够稳定，不能硬编专项训练。先补 1 题可诊断练习，再生成更具体的训练处方。"
                if has_existing_evidence
                else "当前证据还不足以生成可靠专项训练，先用一题建立学情基线。"
            ),
            "evidence_count": evidence_count,
            "evidence_refs": [],
            "estimated_minutes": 3,
            "question_plan": [
                {
                    "phase": "discovery_probe",
                    "phase_label": "补证据" if has_existing_evidence else "起步测评",
                    "label": "补 1 题确认具体薄弱点" if has_existing_evidence else "先用 1 题确认薄弱点",
                    "question_count": 1,
                }
            ],
            "success_criteria": _safe_dict(intent.get("success_criteria")),
            "training_intent_id": str(intent.get("training_intent_id") or "").strip(),
        }

    question_plan = _prescription_question_plan(
        steps=_safe_list(intent.get("prescription_steps")),
        topic=topic,
        error_label=error_label,
    )
    total_questions = sum(_safe_int(item.get("question_count")) for item in question_plan)
    total_questions = total_questions or _safe_int(intent.get("question_count")) or 1
    return {
        "status": "active",
        "source": "training_intent",
        "title": f"围绕“{topic}”完成闭环训练",
        "priority_task": str(next_action.get("title") or "").strip()
        or f"先做 {total_questions} 道“{topic}”辨析题",
        "subtitle": f"先修“{error_label}”，再用新题验证",
        "display_topic": topic,
        "error_label": error_label,
        "why_this": f"最近 {evidence_count} 次作答暴露“{error_label}”，先围绕“{topic}”修正判断抓手。",
        "evidence_count": evidence_count,
        "evidence_refs": evidence_refs[:5],
        "estimated_minutes": max(3, total_questions * 2),
        "question_plan": question_plan,
        "success_criteria": _safe_dict(intent.get("success_criteria")),
        "training_intent_id": str(intent.get("training_intent_id") or "").strip(),
    }


def _degraded_dry_run_action(action: dict[str, Any]) -> dict[str, Any]:
    payload = dict(action or {})
    payload.update({
        "status": "degraded",
        "degraded": True,
        "source": "dry_run_fallback",
        "prescription_authority": "training_intent",
        "title": "先补一题可诊断练习",
        "why_this_now": "当前稳定学习事实缺失，只能用最近窗口做低风险提示。",
        "evidence_refs": [],
    })
    return payload


def _prescription_question_plan(
    *,
    steps: list[Any],
    topic: str,
    error_label: str,
) -> list[dict[str, Any]]:
    if not steps:
        steps = [{"phase": "repair_root", "question_count": 1}]
    labels = {
        "repair_root": f"先辨清{topic}的条件边界",
        "expression_drill": f"说清{topic}的判断抓手",
        "transfer_case": f"换一个场景判断{topic}",
        "verification_probe": f"用 1 题验证不再{error_label}",
    }
    phase_labels = {
        "repair_root": "补根因",
        "expression_drill": "表达训练",
        "transfer_case": "迁移练习",
        "verification_probe": "验证题",
        "discovery_probe": "起步测评",
    }
    plan = []
    for index, raw in enumerate(steps):
        step = _safe_dict(raw)
        phase = str(step.get("phase") or f"phase-{index}").strip()
        count = _safe_int(step.get("question_count")) or 1
        plan.append(
            {
                "phase": phase,
                "phase_label": phase_labels.get(phase, "训练"),
                "label": labels.get(phase, f"围绕{topic}完成训练"),
                "question_count": count,
            }
        )
    return plan


def _study_plan_from_prescription(prescription: dict[str, Any]) -> dict[str, Any]:
    item = _safe_dict(prescription)
    if not item:
        return {}
    status = str(item.get("status") or "").strip()
    topic = canonical_learning_topic_label(item.get("display_topic")) or _student_safe_topic(item.get("display_topic"))
    estimated = _safe_int(item.get("estimated_minutes"))
    if status == "active" and topic:
        return {
            "focus_topic": topic,
            "priority_task": str(item.get("priority_task") or item.get("title") or "").strip(),
            "study_method": "先辨清条件边界，再说出判断抓手，换场景练一次，最后用验证题闭环",
            "time_budget": f"约 {estimated} 分钟" if estimated > 0 else "约 8 分钟",
            "coach_note": str(item.get("why_this") or item.get("subtitle") or "").strip(),
            "source": "training_prescription",
        }
    if status == "degraded":
        evidence_count = _safe_int(item.get("evidence_count"))
        return {
            "focus_topic": "今天先完成一轮诊断练习",
            "priority_task": "补 1 题可诊断练习，确认具体薄弱点" if evidence_count > 0 else "先做 1 题摸底，补齐可诊断证据",
            "study_method": (
                "先补一题高质量作答，系统再把题目主题、选项和错因合成专项训练"
                if evidence_count > 0
                else "先完成一题真实作答，系统再按题目、选项和错因生成专项训练"
            ),
            "time_budget": f"约 {estimated} 分钟" if estimated > 0 else "约 3 分钟",
            "coach_note": str(item.get("why_this") or "先用真实作答建立学情基线").strip(),
            "source": "training_prescription",
        }
    return {}


def _is_student_safe_study_plan(plan: dict[str, Any]) -> bool:
    texts = [
        str(plan.get(key) or "").strip()
        for key in ("focus_topic", "priority_task", "study_method", "coach_note")
    ]
    if any(_looks_like_prompt_topic(text) for text in texts if text):
        return False
    focus = str(plan.get("focus_topic") or plan.get("focusTopic") or "").strip()
    return not focus or bool(_student_safe_topic(focus))


def _canonicalized_study_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan:
        return {}
    payload = dict(plan)
    raw_focus = payload.get("focus_topic") or payload.get("focusTopic")
    focus = canonical_learning_topic_label(raw_focus)
    if focus:
        payload["focus_topic"] = focus
    elif raw_focus:
        return {}
    return payload


def _learner_facing_payload(
    *,
    events: list[Any],
    evidence_stats: dict[str, Any],
    weak_points: list[dict[str, Any]],
    next_training: list[dict[str, Any]],
    bookmarked_event_ids: set[str] | None = None,
) -> dict[str, Any]:
    attempts = _recent_attempt_cards(events, bookmarked_event_ids=bookmarked_event_ids or set())
    diagnoses = _diagnosis_cards(events=events, weak_points=weak_points)
    timeline = _evidence_timeline(attempts)
    loops = _training_loop_cards(attempts=attempts, diagnoses=diagnoses)
    next_action = _next_action_card(diagnoses=diagnoses, next_training=next_training, events=events)
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


def _recent_attempt_cards(events: list[Any], *, bookmarked_event_ids: set[str] | None = None) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    bookmark_ids = set(bookmarked_event_ids or set())
    ordered = sorted(
        [event for event in list(events or []) if _is_progress_countable_event(event)],
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
        is_bookmarked = str(getattr(event, "event_id", "") or "") in bookmark_ids
        cards.append({
            "key": _attempt_card_key(event=event, payload=payload, index=index),
            "attempt_ref": _attempt_ref(event=event, payload=payload),
            "subject_id": _attempt_subject_id(event=event, payload=payload),
            "bot_id": str(getattr(event, "source_bot_id", "") or "").strip(),
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
            "is_bookmarked": is_bookmarked,
            "bookmark_label": "已加入错题" if is_bookmarked else "",
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


def _attempt_subject_id(*, event: Any, payload: dict[str, Any]) -> str:
    subject_id = str(payload.get("subject_id") or "").strip()
    if subject_id:
        return subject_id
    bot_id = str(getattr(event, "source_bot_id", "") or "").strip()
    if bot_id == "construction-exam":
        return "construction_exam_1"
    return bot_id


def _bookmarked_event_ids(*, user_id: str, mistake_book_service: Any | None) -> set[str]:
    if mistake_book_service is None:
        return set()
    getter = getattr(mistake_book_service, "bookmark_event_ids", None)
    if not callable(getter):
        return set()
    try:
        return set(getter(user_id=user_id, include_mastered=True) or set())
    except Exception:
        return set()


def _mistake_book_projection(*, user_id: str, mistake_book_service: Any | None) -> dict[str, Any]:
    if mistake_book_service is None:
        return {"count": 0, "recent_items": [], "source_status": {"ok": None, "reason": "not_configured"}}
    lister = getattr(mistake_book_service, "list_items", None)
    if not callable(lister):
        return {"count": 0, "recent_items": [], "source_status": {"ok": None, "reason": "unsupported_service"}}
    try:
        result = _safe_dict(lister(user_id=user_id, include_mastered=True))
    except Exception as exc:
        reason = str(exc).strip() or exc.__class__.__name__
        return {
            "count": 0,
            "recent_items": [],
            "source_status": {"ok": False, "reason": reason},
        }
    return {
        "count": _safe_int(result.get("count")),
        "recent_items": _safe_list(result.get("items"))[:3],
        "etag": str(result.get("etag") or "").strip(),
        "generated_at": str(result.get("generated_at") or "").strip(),
        "source_status": {"ok": True},
    }


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
        if not _is_progress_countable_event(event):
            continue
        payload = _safe_dict(getattr(event, "payload_json", {}))
        created_at = str(getattr(event, "created_at", "") or "")
        question_topic = _topic_from_question_payload(payload=payload, event=event)
        evidence_ref = _evidence_ref(event=event, payload=payload)
        for error in _safe_list(payload.get("error_events") or payload.get("errors")):
            if not isinstance(error, dict):
                continue
            concept = (
                _student_safe_topic(
                    _concept_label(str(error.get("concept_tag") or _event_concept(payload) or ""))
                )
                or question_topic
            )
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
                    "evidence_refs": [],
                    "topic_candidates": [],
                },
            )
            item["count"] += 1
            if evidence_ref and evidence_ref not in item["evidence_refs"]:
                item["evidence_refs"].append(evidence_ref)
            if question_topic and question_topic not in item["topic_candidates"]:
                item["topic_candidates"].append(question_topic)
            if created_at > str(item.get("latest_at") or ""):
                item["latest_at"] = created_at
                item["detail"] = _clean_learning_text(error.get("diagnosis") or "")

    for weak in weak_points:
        concept = _student_safe_topic(_concept_label(str(weak.get("concept_id") or "")))
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
                "evidence_refs": [],
                "topic_candidates": [],
            },
        )
        item["count"] = max(_safe_int(item.get("count")), len(_safe_list(weak.get("supporting_event_ids"))))
        for raw_ref in _safe_list(weak.get("supporting_event_ids")):
            ref = _opaque_ref(raw_ref)
            if ref and ref not in item["evidence_refs"]:
                item["evidence_refs"].append(ref)
        if not item.get("detail"):
            item["detail"] = _clean_learning_text(weak.get("display_title") or weak.get("claim") or "")

    cards = []
    for item in grouped.values():
        count = _safe_int(item.get("count"))
        concept = _student_safe_topic(item.get("concept")) or str(
            (_safe_list(item.get("topic_candidates")) or ["综合练习"])[0]
        )
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
            "evidence_refs": _safe_list(item.get("evidence_refs"))[:5],
            "topic_candidates": _safe_list(item.get("topic_candidates"))[:3],
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


def _latest_training_completed_action(events: list[Any]) -> dict[str, Any] | None:
    ordered = sorted(
        list(events or []),
        key=lambda event: str(getattr(event, "created_at", "") or ""),
        reverse=True,
    )
    for event in ordered:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if str(payload.get("learning_signal_type") or "").strip() != "training_completed":
            continue
        concept = _student_safe_topic(
            _concept_label(_event_concept(payload))
            or _safe_dict(payload.get("concept")).get("label")
            or payload.get("concept_label")
            or ""
        )
        if not concept:
            continue
        attempt_ref = str(payload.get("attempt_ref") or "").strip()
        evidence_refs = _safe_list(payload.get("evidence_refs"))
        return {
            "title": f"再测一次{concept}",
            "subtitle": "刚完成同类训练，用一套新题确认是否真正回到主线",
            "concept": concept,
            "error": str(
                _safe_dict(payload.get("error")).get("label")
                or payload.get("error_label")
                or ""
            ).strip(),
            "intent": {
                "source": "learning_report",
                "learning_signal_type": "assessment",
                "concept_label": concept,
                "attempt_ref": attempt_ref,
                "evidence_refs": evidence_refs or ([attempt_ref] if attempt_ref else []),
                "reason": "training_completion_retest",
            },
            "cta": "去测评",
            "estimated_minutes": 8,
        }
    return None


def _next_action_card(
    *,
    diagnoses: list[dict[str, Any]],
    next_training: list[dict[str, Any]],
    events: list[Any],
) -> dict[str, Any]:
    training_completed = _latest_training_completed_action(events)
    if training_completed:
        return training_completed
    if diagnoses:
        top = diagnoses[0]
        candidates = [
            top.get("concept"),
            *(_safe_list(top.get("topic_candidates")) or []),
        ]
        concept = next((_student_safe_topic(item) for item in candidates if _student_safe_topic(item)), "")
        error = str(top.get("error") or "错因")
        evidence_refs = _safe_list(top.get("evidence_refs"))
        if not concept:
            intent = build_learning_training_intent(
                user_id="",
                error_label=error,
                question_count=3,
                training_mode="mixed_review",
                reason=str(top.get("meta") or ""),
            )
            return _with_next_best_action_view({
                "title": "先补一条可诊断证据",
                "subtitle": "完成 1 题后，系统会生成可靠训练主题",
                "concept": "",
                "error": error,
                "intent": intent,
                "cta": "去练习",
                "estimated_minutes": 3,
            }, intent=intent)
        intent = build_learning_training_intent(
            user_id="",
            concept_label=concept,
            error_label=error,
            evidence_refs=evidence_refs,
            question_count=3,
            training_mode="mixed_review",
            reason=str(top.get("meta") or ""),
        )
        return _with_next_best_action_view({
            "title": f"先做 3 道“{concept}”专项题",
            "subtitle": f"目标：把“{error}”这一类错误拉回主线",
            "concept": concept,
            "error": error,
            "intent": intent,
            "cta": "开始训练",
            "estimated_minutes": 8,
        }, intent=intent)
    if next_training:
        item = _safe_dict(next_training[0])
        title = _clean_learning_text(item.get("display_title") or item.get("claim") or "下一步训练")
        meta = _clean_learning_text(item.get("display_meta") or item.get("display_label") or "")
        intent = build_learning_training_intent(user_id="", reason=meta, question_count=3)
        return _with_next_best_action_view({
            "title": title or "先完成一组专项训练",
            "subtitle": meta or "完成后系统会继续更新你的学情判断",
            "concept": "",
            "intent": intent,
            "cta": "开始训练",
            "estimated_minutes": 8,
        }, intent=intent)
    intent = build_learning_training_intent(user_id="", reason="starter", question_count=3)
    return _with_next_best_action_view({
        "title": "先完成一组练习",
        "subtitle": "完成批改后，系统会生成你的错因和下一步训练",
        "concept": "",
        "intent": intent,
        "cta": "去练习",
        "estimated_minutes": 10,
    }, intent=intent)


def _with_next_best_action_view(card: dict[str, Any], *, intent: dict[str, Any]) -> dict[str, Any]:
    actions = build_next_best_actions(user_id="", training_intents=[intent], max_actions=1)
    action = _safe_dict(actions[0] if actions else {})
    enriched = dict(card)
    enriched.update({
        "action_id": action.get("action_id") or "",
        "training_intent_id": action.get("training_intent_id") or str(intent.get("training_intent_id") or ""),
        "source": action.get("source") or "training_intent",
        "prescription_authority": action.get("prescription_authority") or "training_intent",
        "why_this_now": action.get("why_this_now") or "",
        "evidence_refs": _safe_list(action.get("evidence_refs")),
        "intent": _safe_dict(action.get("intent")) or dict(intent),
    })
    return enriched


def _truth_sections(events: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    needs_confirmation: list[dict[str, Any]] = []
    committed_retest_ids = committed_retest_completion_ids(events)
    for event in events:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        quality = _attempt_quality(payload)
        concept = _concept_label(_event_concept(payload)) or _safe_dict(payload.get("concept")).get("label") or ""
        errors = [item for item in _safe_list(payload.get("error_events") or payload.get("errors")) if isinstance(item, dict)]
        error = _primary_error_label(errors) or str(_safe_dict(payload.get("error")).get("label") or "").strip()
        signal_type = str(payload.get("learning_signal_type") or "").strip()
        label = concept or error or "待确认学习事实"
        if quality.get("detail_ready") and not concept:
            needs_confirmation.append({"label": label, "reason": "concept_missing", "level_label": "待确认"})
            continue
        key = (concept or "综合练习", error or signal_type or "观察")
        item = grouped.setdefault(
            key,
            {
                "label": f"{key[0]}：{key[1]}",
                "concept": key[0],
                "error": key[1],
                "count": 0,
                "stable_count": 0,
                "stable_attempt_ids": [],
                "latest_at": "",
                "conversation_only": True,
            },
        )
        item["count"] += 1
        if _is_progress_countable_event(event) and event_promotion_allowed(
            event,
            committed_retest_ids=committed_retest_ids,
        ):
            attempt_id = evidence_attempt_id(event, payload)
            if attempt_id and attempt_id not in item["stable_attempt_ids"]:
                item["stable_attempt_ids"].append(attempt_id)
            item["stable_count"] = len(item["stable_attempt_ids"])
            item["conversation_only"] = False
        created_at = str(getattr(event, "created_at", "") or "")
        if created_at > str(item.get("latest_at") or ""):
            item["latest_at"] = created_at
    stable: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    for item in grouped.values():
        item.pop("stable_attempt_ids", None)
        count = _safe_int(item.get("count"))
        stable_count = _safe_int(item.get("stable_count"))
        if stable_count >= 2:
            stable.append({**item, "level_label": "重复出现"})
        else:
            recent.append({**item, "level_label": "刚发现" if not item.get("conversation_only") else "已讲解"})
    return {
        "stable_truths": stable,
        "recent_observations": recent,
        "needs_confirmation": needs_confirmation,
    }


def _mastery_payload(
    mastery_dashboard: dict[str, Any],
    *,
    radar_dimensions: list[dict[str, Any]],
    evidence_stats: dict[str, Any],
) -> dict[str, Any]:
    chapter_stats = _safe_dict(evidence_stats.get("chapter_stats"))
    evidence_chapters = _evidence_mastery_chapters(chapter_stats)
    groups = []
    for group in _safe_list(mastery_dashboard.get("groups")):
        group_payload = _safe_dict(group)
        chapters = []
        for chapter in _safe_list(group_payload.get("chapters")):
            chapter_payload = _safe_dict(chapter)
            raw_name = chapter_payload.get("name")
            name = _display_dimension_label(raw_name)
            taxonomy_meta = _taxonomy_display_meta(raw_name, name)
            if not name or not taxonomy_meta:
                continue
            mastery = _calibrated_mastery(
                _safe_int(chapter_payload.get("mastery")),
                _safe_dict(chapter_stats.get(name)),
            )
            status = _score_status(mastery)
            chapters.append({
                **chapter_payload,
                **taxonomy_meta,
                "name": name,
                "mastery": mastery,
                "status": status,
                "color": _status_color(status),
            })
        if not chapters:
            continue
        avg_mastery = round(
            sum(_safe_int(item.get("mastery")) for item in chapters) / max(len(chapters), 1)
        )
        avg_status = _score_status(avg_mastery)
        groups.append({
            **group_payload,
            "avg_mastery": avg_mastery,
            "avg_status": avg_status,
            "avg_class": _avg_class(avg_status),
            "chapters": chapters,
        })
    if not groups and evidence_chapters:
        avg_mastery = round(
            sum(_safe_int(item.get("mastery")) for item in evidence_chapters)
            / max(len(evidence_chapters), 1)
        )
        avg_status = _score_status(avg_mastery)
        groups.append({
            "name": "练习证据",
            "avg_mastery": avg_mastery,
            "avg_status": avg_status,
            "avg_class": _avg_class(avg_status),
            "chapters": evidence_chapters,
        })

    hotspots = []
    for item in _safe_list(mastery_dashboard.get("hotspots")):
        hotspot = _safe_dict(item)
        raw_name = hotspot.get("name")
        name = _display_dimension_label(raw_name)
        taxonomy_meta = _taxonomy_display_meta(raw_name, name)
        if not name or not taxonomy_meta:
            continue
        mastery = _calibrated_mastery(
            _safe_int(hotspot.get("mastery")),
            _safe_dict(chapter_stats.get(name)),
        )
        status = _score_status(mastery)
        hotspots.append({
            **hotspot,
            **taxonomy_meta,
            "name": name,
            "mastery": mastery,
            "status": status,
            "color": _status_color(status),
        })
    if not hotspots and evidence_chapters:
        hotspots = sorted(
            [dict(item) for item in evidence_chapters if _safe_int(item.get("done")) > 0],
            key=lambda item: (_safe_int(item.get("mastery")), -_safe_int(item.get("done"))),
        )[:5]
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
    knowledge_summary = _knowledge_map_summary(groups=groups, hotspots=hotspots)
    return {
        "overall_mastery": {
            "score": overall,
            "status": _score_status(overall),
            "class_name": _score_class(_score_status(overall)),
        },
        "groups": groups,
        "hotspots": hotspots,
        "knowledge_summary": knowledge_summary,
        "review_summary": review or {"total_due": 0, "overdue_count": 0},
    }


def _taxonomy_counts() -> dict[str, int]:
    stats = taxonomy_tree_stats()
    return {
        "total_nodes": _safe_int(stats.get("total_nodes")),
        "coded_nodes": _safe_int(stats.get("coded_nodes")),
        "leaf_nodes": _safe_int(stats.get("leaf_nodes")),
        "unique_codes": _safe_int(stats.get("unique_codes")),
        "duplicate_code_rows": _safe_int(stats.get("duplicate_code_rows")),
    }


def _knowledge_map_summary(
    *,
    groups: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = _taxonomy_counts()
    parent_refs = {
        str(_safe_dict(node).get("parent_code") or "").strip()
        for node in _safe_dict(taxonomy_index().get("nodes_by_id")).values()
        if str(_safe_dict(node).get("parent_code") or "").strip()
    }
    chapter_rows: dict[int, dict[str, Any]] = {}
    for chapter in textbook_directory():
        no = _safe_int(_safe_dict(chapter).get("no"))
        if no <= 0:
            continue
        chapter_rows[no] = {
            "chapter_no": no,
            "chapter_name": "第" + str(no) + "章 " + str(_safe_dict(chapter).get("name") or "").strip(),
            "section_count": len(_safe_list(_safe_dict(chapter).get("sections"))),
            "evaluated_topics": 0,
            "mastered_topics": 0,
            "developing_topics": 0,
            "weak_topics": 0,
            "top_topics": [],
            "status": "unseen",
        }

    observed: dict[str, dict[str, Any]] = {}
    for item in [
        chapter
        for group in groups
        for chapter in _safe_list(_safe_dict(group).get("chapters"))
    ] + [hotspot for hotspot in hotspots]:
        topic = _safe_dict(item)
        key = str(topic.get("taxonomy_code") or topic.get("name") or "").strip()
        name = str(topic.get("name") or "").strip()
        if not key or not name:
            continue
        observed[key] = {
            "name": name,
            "status": str(topic.get("status") or _score_status(_safe_int(topic.get("mastery")))),
            "mastery": _safe_int(topic.get("mastery")),
            "taxonomy_code": str(topic.get("taxonomy_code") or "").strip(),
            "textbook_chapter_no": _safe_int(topic.get("textbook_chapter_no")),
        }

    status_counts = {"strong": 0, "normal": 0, "weak": 0, "observed": 0}
    leaf_evaluated = 0
    for item in observed.values():
        status = str(item.get("status") or "observed")
        status_counts[status if status in status_counts else "observed"] += 1
        chapter_no = _safe_int(item.get("textbook_chapter_no"))
        chapter = chapter_rows.get(chapter_no)
        if chapter is not None:
            chapter["evaluated_topics"] += 1
            if status == "strong":
                chapter["mastered_topics"] += 1
            elif status == "weak":
                chapter["weak_topics"] += 1
            else:
                chapter["developing_topics"] += 1
            if len(chapter["top_topics"]) < 3:
                chapter["top_topics"].append(str(item.get("name") or "").strip())
        code = str(item.get("taxonomy_code") or "").strip()
        if code and code not in parent_refs:
            leaf_evaluated += 1
    for chapter in chapter_rows.values():
        if _safe_int(chapter.get("weak_topics")) > 0:
            chapter["status"] = "weak"
        elif _safe_int(chapter.get("mastered_topics")) > 0 and _safe_int(chapter.get("developing_topics")) <= 0:
            chapter["status"] = "strong"
        elif _safe_int(chapter.get("evaluated_topics")) > 0:
            chapter["status"] = "developing"

    return {
        **counts,
        "total_textbook_chapters": len(chapter_rows),
        "evaluated_topics": len(observed),
        "evaluated_leaf_points": leaf_evaluated,
        "mastered_topics": status_counts["strong"],
        "developing_topics": status_counts["normal"] + status_counts["observed"],
        "weak_topics": status_counts["weak"],
        "unmeasured_leaf_points": max(0, counts["leaf_nodes"] - leaf_evaluated),
        "textbook_chapters": list(chapter_rows.values()),
    }


def _score_class(status: str) -> str:
    return {
        "strong": "score-good",
        "normal": "score-mid",
        "weak": "score-low",
        "observed": "score-low",
    }.get(status, "score-low")


def _avg_class(status: str) -> str:
    return {
        "strong": "avg-good",
        "normal": "avg-mid",
        "weak": "avg-low",
        "observed": "avg-low",
    }.get(status, "avg-low")


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
        taxonomy_meta = _taxonomy_display_meta(item.get("name") or key, name)
        if name and taxonomy_meta:
            calibrated = _calibrated_mastery(
                score,
                _safe_dict(chapter_stats.get(name)),
            )
            _append_dimension(dimensions, name=name, score=calibrated, extra=taxonomy_meta)
    if dimensions:
        return dimensions
    for group in _safe_list(mastery_dashboard.get("groups")):
        for chapter in _safe_list(_safe_dict(group).get("chapters")):
            item = _safe_dict(chapter)
            name = _display_dimension_label(item.get("name"))
            taxonomy_meta = _taxonomy_display_meta(item.get("name"), name)
            if name and taxonomy_meta:
                calibrated = _calibrated_mastery(
                    _safe_int(item.get("mastery")),
                    _safe_dict(chapter_stats.get(name)),
                )
                _append_dimension(dimensions, name=name, score=calibrated, extra=taxonomy_meta)
    if dimensions:
        return dimensions
    for item in _evidence_mastery_chapters(chapter_stats):
        if item.get("textbook_chapter_name"):
            _append_dimension(
                dimensions,
                name=str(item.get("name") or ""),
                score=_safe_int(item.get("mastery")),
                extra={
                    key: item[key]
                    for key in ("taxonomy_code", "taxonomy_path", "parent_name", "textbook_chapter_no", "textbook_chapter_name", "textbook_section_name")
                    if key in item
                },
            )
    return dimensions


def _evidence_mastery_chapters(chapter_stats: dict[str, Any]) -> list[dict[str, Any]]:
    chapters = []
    for name, raw_stats in sorted(
        _safe_dict(chapter_stats).items(),
        key=lambda item: (
            -_safe_int(_safe_dict(item[1]).get("done")),
            str(item[0] or ""),
        ),
    ):
        label = _display_dimension_label(name)
        stats = _safe_dict(raw_stats)
        if not label or _safe_int(stats.get("done")) <= 0:
            continue
        mastery = _calibrated_mastery(0, stats)
        status = _score_status(mastery)
        taxonomy_meta = _taxonomy_display_meta(name, label)
        chapters.append({
            **taxonomy_meta,
            "name": label,
            "mastery": mastery,
            "status": status,
            "color": _status_color(status),
            "done": _safe_int(stats.get("done")),
            "correct": _safe_int(stats.get("correct")),
            "last_activity_at": str(stats.get("last_activity_at") or ""),
            "source": "learning_evidence",
        })
    return chapters


def _append_dimension(
    dimensions: list[dict[str, Any]],
    *,
    name: str,
    score: int,
    extra: dict[str, Any] | None = None,
) -> None:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return
    normalized_score = max(0, min(int(score or 0), 100))
    value = round(normalized_score / 100, 2)
    status = _score_status(normalized_score)
    payload = {
        "name": normalized_name,
        "value": value,
        "score": normalized_score,
        "rate_text": f"{normalized_score}%",
        "status": status,
        "level": status,
        "color": _status_color(status),
        **_safe_dict(extra),
    }
    for item in dimensions:
        if item.get("name") == normalized_name:
            if value > float(item.get("value") or 0):
                item.update(payload)
            return
    dimensions.append(payload)


def _score_status(score: int) -> str:
    if score >= 70:
        return "strong"
    if score >= 40:
        return "normal"
    if score > 0:
        return "weak"
    return "observed"


def _status_color(status: str) -> str:
    return {
        "strong": "#34d399",
        "normal": "#fbbf24",
        "weak": "#f87171",
        "observed": "#94a3b8",
    }.get(status, "#94a3b8")


def _display_dimension_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _is_deictic_topic_label(text):
        return ""
    # student-facing: a code resolves to Chinese (or '' on miss, never the code); human text passes through
    label = student_facing_label(text)
    normalized = str(label or "").strip()
    if _is_deictic_topic_label(normalized):
        return ""
    return normalized


def _sanitize_assessment_profile_topics(profile: dict[str, Any]) -> dict[str, Any]:
    payload = dict(_safe_dict(profile))
    chapter_mastery = {}
    for key, value in _safe_dict(payload.get("chapter_mastery")).items():
        item = _safe_dict(value)
        name = item.get("name") if item else key
        display_name = _display_dimension_label(name or key)
        if not display_name or not _taxonomy_display_meta(name or key, display_name):
            continue
        chapter_mastery[key] = value
    payload["chapter_mastery"] = chapter_mastery
    return payload


def _sanitize_mastery_dashboard_topics(dashboard: dict[str, Any]) -> dict[str, Any]:
    payload = dict(_safe_dict(dashboard))
    groups = []
    for group in _safe_list(payload.get("groups")):
        group_payload = dict(_safe_dict(group))
        chapters = [
            chapter
            for chapter in _safe_list(group_payload.get("chapters"))
            if _is_textbook_topic_payload(_safe_dict(chapter).get("name"))
        ]
        if not chapters:
            continue
        group_payload["chapters"] = chapters
        groups.append(group_payload)
    payload["groups"] = groups
    payload["hotspots"] = [
        hotspot
        for hotspot in _safe_list(payload.get("hotspots"))
        if _is_textbook_topic_payload(_safe_dict(hotspot).get("name"))
    ]
    return payload


def _is_textbook_topic_payload(value: Any) -> bool:
    label = _display_dimension_label(value)
    return bool(label and _taxonomy_display_meta(value, label))


def _taxonomy_display_meta(raw_value: Any, label: str) -> dict[str, Any]:
    code = normalize_taxonomy_code(raw_value)
    node = taxonomy_index()["nodes_by_code"].get(code) if code else None
    path = [
        str(name or "").strip()
        for name in _safe_list(_safe_dict(node).get("path_names"))
        if str(name or "").strip()
    ] if node else []
    if not path:
        path = [str(label or "").strip()] if str(label or "").strip() else []
    textbook_meta = textbook_topic_meta(
        raw_value=raw_value,
        label=label,
        path_names=path,
    )
    if not textbook_meta:
        return {}
    meta = {**textbook_meta}
    if code and node:
        meta["taxonomy_code"] = code
    if path:
        meta["taxonomy_path"] = path
        meta["parent_name"] = path[0]
    return meta


def _is_deictic_topic_label(value: Any) -> bool:
    compact = re.sub(r"[\s　，,。.!！?？:：;；“”\"'‘’（）()【】\[\]<>《》]+", "", str(value or ""))
    return compact in _DEICTIC_TOPIC_LABELS or is_non_topic_label(value)


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
    for weak_name in weak_names:
        topic = canonical_learning_topic_label(weak_name)
        if topic:
            return topic
    focus = _safe_dict(home_dashboard.get("today_focus"))
    return canonical_learning_topic_label(
        str(focus.get("title") or _safe_dict(home_dashboard.get("today")).get("hint") or "").strip()
    )


def _concept_label(concept_id: str) -> str:
    # SINGLE AUTHORITY, student-facing: a code -> canonical Chinese (or '' on miss, NEVER the code);
    # already-Chinese text (callers sometimes pass a label) passes through unchanged.
    return student_facing_label(concept_id)


def _student_safe_topic(value: Any) -> str:
    text = _clean_learning_text(value)
    if not text or _looks_like_prompt_topic(text):
        return ""
    text = text.strip("「」\"'“”")
    text = text.replace("相关的题目", "").replace("相关题目", "").strip()
    text = re.sub(r"\s+", "", text)
    if not text or _looks_like_prompt_topic(text):
        return ""
    if text in _GENERIC_TRAINING_TOPICS:
        return ""
    if len(text) > 24:
        return ""
    return text


def _looks_like_prompt_topic(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _PROMPT_TOPIC_MARKERS):
        return True
    if re.search(r"(先做|做|出)\s*\d+\s*道?题", text):
        return True
    if "题目" in text and ("练习" in text or "相关" in text):
        return True
    return False


def _topic_from_question_payload(*, payload: dict[str, Any], event: Any) -> str:
    text = _question_text(payload=payload, event=event, index=0)
    if not text or _looks_like_prompt_topic(text):
        return ""
    if "防火门" in text:
        return "防火门构造要求"
    if "投标保证金" in text:
        return "投标保证金法定上限"
    if "验槽" in text:
        return "验槽方法辨析"
    candidate = text
    for sep in ("，", ",", "？", "?", "。"):
        if sep in candidate:
            candidate = candidate.split(sep)[0]
            break
    candidate = candidate.removeprefix("关于").strip()
    candidate = candidate.replace("的说法", "").replace("的做法", "").strip()
    candidate = candidate.replace("下列哪项", "").replace("正确的是", "").strip()
    candidate = candidate.replace("的构造要求", "构造要求")
    return _student_safe_topic(candidate)


def _evidence_ref(*, event: Any, payload: dict[str, Any]) -> str:
    raw = "|".join(
        str(value or "").strip()
        for value in [
            getattr(event, "event_id", ""),
            getattr(event, "source_id", ""),
            payload.get("question_id"),
            getattr(event, "created_at", ""),
        ]
    )
    return _opaque_ref(raw)


def _opaque_ref(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"evidence-{digest}"


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
    raw_text = str(value or "").strip()
    if not raw_text:
        return ""
    option_map = _option_map(options)
    text = raw_text.upper()
    if option_map:
        compact = re.sub(r"[\s,，、;；|/]+", "", text)
        if compact and all(char in option_map for char in compact):
            return "、".join(
                f"{letter}（{_truncate(option_map.get(letter), 18)}）"
                for letter in compact
            )
    if not re.fullmatch(r"[A-Z]+", text):
        return _truncate(_clean_learning_text(raw_text), 28)
    letters = [char for char in text if char.isalpha()]
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
    start = datetime.now(_TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=8)
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
