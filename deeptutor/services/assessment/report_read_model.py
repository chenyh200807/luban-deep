from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


REPORT_SCHEMA_VERSION = "p0a-v1"
PASS_READINESS_REPORT_SCHEMA_VERSION = "pass-readiness-v1"
# Persisted report schema versions admitted by the DB CHECK constraint
# (supabase/migrations/20260805000100_assessment_report_schema_pass_readiness.sql).
SUPPORTED_REPORT_SCHEMA_VERSIONS = (REPORT_SCHEMA_VERSION, PASS_READINESS_REPORT_SCHEMA_VERSION)


class AssessmentReportError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_result_report(
    *,
    quiz_id: str,
    assessment_type: str,
    subject_id: str,
    topic_ids: list[str],
    topic_label: str,
    blueprint_version: str,
    form_id: str,
    scored_result: dict[str, Any],
    writeback_refs: dict[str, Any] | None = None,
    degraded_reason: str | None = None,
) -> dict[str, Any]:
    items = [dict(item) for item in list(scored_result.get("items") or [])]
    score_summary = dict(scored_result.get("score_summary") or {})
    confidence = dict(scored_result.get("measurement_confidence") or {})
    wrong_items = [item for item in items if not item.get("is_correct")]
    knowledge_map = _knowledge_map(items)
    next_action = _session_local_next_action(wrong_items, knowledge_map)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "quiz_id": quiz_id,
        "assessment_type": assessment_type,
        "subject_id": subject_id,
        "topic_ids": list(topic_ids or []),
        "topic_label": topic_label,
        "blueprint_version": blueprint_version,
        "form_id": form_id,
        "score_title": "本次专题测评得分",
        "score_summary": score_summary,
        "measurement_confidence": confidence,
        "knowledge_map": knowledge_map,
        "wrong_items": [
            {
                "question_id": item.get("question_id"),
                "source_question_id": item.get("source_question_id"),
                "question_stem": item.get("question_stem"),
                "learner_answer": item.get("learner_answer"),
                "correct_answer": item.get("correct_answer"),
                "simple_explanation": item.get("simple_explanation"),
                "knowledge_points": list(item.get("knowledge_points") or []),
                "error_codes": list(item.get("error_codes") or []),
            }
            for item in wrong_items
        ],
        "items": [
            {
                "question_id": item.get("question_id"),
                "source_question_id": item.get("source_question_id"),
                "learner_answer": item.get("learner_answer"),
                "correct_answer": item.get("correct_answer"),
                "is_correct": bool(item.get("is_correct")),
                "simple_explanation": item.get("simple_explanation"),
                "knowledge_points": list(item.get("knowledge_points") or []),
                "error_codes": list(item.get("error_codes") or []),
            }
            for item in items
        ],
        "attempt_refs": list((writeback_refs or {}).get("learning_event_refs") or []),
        "session_local_next_action": next_action,
        "writeback_status": dict((writeback_refs or {}).get("writeback_status") or {}),
        "deep_explanation": {
            "available": False,
            "copy": "详细解析下个版本上线",
        },
        "degraded_reason": degraded_reason,
    }


_SELF_REPORTED_SCORE_BY_TAG: dict[str, int | None] = {
    # Representative mid-band values for the recent_score_band probe (自报未核验).
    "no_prior_score": None,
    "below_60": 50,
    "score_60_79": 70,
    "score_80_95": 88,
    "score_96_plus": 100,
}


def _probe_tags(
    session_questions: list[dict[str, Any]],
    answers: dict[str, Any],
) -> dict[str, str]:
    """Map profile-probe topics to the tag of the tapped option."""

    tags: dict[str, str] = {}
    for question in session_questions:
        if question.get("scored", True):
            continue
        topic = str(question.get("profile_topic") or "").strip()
        if not topic:
            continue
        letter = str(answers.get(str(question.get("question_id") or "")) or "").strip().upper()
        option_values = dict(question.get("option_values") or {})
        tag = str(option_values.get(letter) or "").strip()
        if tag:
            tags[topic] = tag
    return tags


def build_pass_readiness_report(
    *,
    quiz_id: str,
    assessment_type: str,
    subject_id: str,
    topic_label: str,
    blueprint_version: str,
    form_id: str,
    scored_result: dict[str, Any],
    session_questions: list[dict[str, Any]],
    answers: dict[str, Any],
    writeback_refs: dict[str, Any] | None = None,
    degraded_reason: str | None = None,
    now_iso: str = "",
) -> dict[str, Any]:
    """Assemble the pass-readiness-v1 report envelope (§7.2).

    Keeps the base p0a report fields (items/wrong_items/score_summary/…) so the
    existing client rendering chain still works, overrides the persisted
    ``schema_version`` to ``pass-readiness-v1``, and adds the deterministic
    ``pass_readiness`` §7.2 block. The p0a-v1 builder is untouched.
    """

    from deeptutor.services.assessment.blueprint import ability_dimensions_by_section
    from deeptutor.services.assessment.pass_readiness_scoring import (
        AbilityEvidence,
        DimensionEvidence,
        PrepContext,
        build_pass_readiness_result,
    )

    base = build_result_report(
        quiz_id=quiz_id,
        assessment_type=assessment_type,
        subject_id=subject_id,
        topic_ids=[],
        topic_label=topic_label,
        blueprint_version=blueprint_version,
        form_id=form_id,
        scored_result=scored_result,
        writeback_refs=writeback_refs,
        degraded_reason=degraded_reason,
    )
    dimension_by_section = ability_dimensions_by_section(blueprint_version)
    counts: dict[str, dict[str, float]] = {}
    items = [dict(item) for item in list(scored_result.get("items") or [])]
    answered_count = 0
    for item in items:
        answered = bool(str(item.get("learner_answer") or "").strip())
        if answered:
            answered_count += 1
        dimension = dimension_by_section.get(str(item.get("section_id") or ""), "")
        if not dimension or not answered:
            continue
        bucket = counts.setdefault(dimension, {"correct": 0.0, "observations": 0})
        bucket["observations"] += 1
        if item.get("is_correct"):
            bucket["correct"] += 1

    def _evidence(dimension: str) -> DimensionEvidence:
        bucket = counts.get(dimension) or {"correct": 0.0, "observations": 0}
        return DimensionEvidence(correct=bucket["correct"], observations=int(bucket["observations"]))

    tags = _probe_tags(session_questions, dict(answers or {}))
    expression = counts.get("answer_expression")
    evidence = AbilityEvidence(
        core_knowledge=_evidence("core_knowledge"),
        construction_logic=_evidence("construction_logic"),
        case_scoring_point_recognition=_evidence("case_scoring_point_recognition"),
        answer_expression=(
            DimensionEvidence(correct=expression["correct"], observations=int(expression["observations"]))
            if expression
            else None
        ),
        self_reported_score=_SELF_REPORTED_SCORE_BY_TAG.get(tags.get("recent_score_band", ""), None),
    )
    prep_context = PrepContext(
        weekly_hours_band=tags.get("weekly_study_hours", ""),
        remaining_weeks=None,
        attempt_history=tags.get("attempt_history", ""),
    )
    pass_readiness = build_pass_readiness_result(
        evidence,
        prep_context,
        scored_task_count=len(items),
        answered_count=answered_count,
        form_version=form_id,
        item_pool_version=blueprint_version,
        now_iso=str(now_iso or base["generated_at"]),
    )
    base["schema_version"] = PASS_READINESS_REPORT_SCHEMA_VERSION
    base["score_title"] = "一建过线体检结果"
    base["pass_readiness"] = pass_readiness
    return base


def assert_supported_report(report: dict[str, Any]) -> None:
    version = str(dict(report or {}).get("schema_version") or "").strip()
    if version not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
        raise AssessmentReportError(f"unsupported_assessment_report_schema_version:{version or 'missing'}")


def _knowledge_map(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"attempted": 0, "correct": 0})
    for item in items:
        points = list(item.get("knowledge_points") or []) or ["综合能力"]
        for point in points:
            label = str(point or "").strip()
            if not label:
                continue
            totals[label]["attempted"] += 1
            totals[label]["correct"] += 1 if item.get("is_correct") else 0
    result: list[dict[str, Any]] = []
    for label, stats in sorted(totals.items()):
        attempted = max(stats["attempted"], 1)
        result.append(
            {
                "knowledge_point": label,
                "attempted": stats["attempted"],
                "correct": stats["correct"],
                "score_pct": round(stats["correct"] / attempted * 100),
            }
        )
    return result


def _session_local_next_action(wrong_items: list[dict[str, Any]], knowledge_map: list[dict[str, Any]]) -> dict[str, Any]:
    weak = sorted(knowledge_map, key=lambda item: (int(item.get("score_pct") or 0), -int(item.get("attempted") or 0)))
    if wrong_items and weak:
        target = weak[0]["knowledge_point"]
        return {
            "authority": "session_local_deterministic",
            "copy": f"建议先复盘{target}相关错题，再做 3 道同类专项练习。",
            "topic": target,
        }
    return {
        "authority": "session_local_deterministic",
        "copy": "建议保持节奏，后续用同专题短练巩固。",
        "topic": "",
    }
