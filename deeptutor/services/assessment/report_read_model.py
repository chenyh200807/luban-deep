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
