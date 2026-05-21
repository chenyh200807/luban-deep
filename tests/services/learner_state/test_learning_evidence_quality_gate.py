"""
Task 0: Learning Evidence Quality Gate

Tests covering the quality contract for learning_evidence events entering the
Learning Report. Gate lives at the service/read-model layer, NOT in front-end JS.

Quality contract shape:
  quality = {
      # ── existing fields (never removed) ──────────────────────────────────
      "evidence_level":         str,   # "L0_observed" | "L1_repeated" | ...
      "writeback_eligible":     bool,
      "stable_truth_eligible":  bool,
      "evidence_cap_reasons":   list[str],
      # ── new quality-gate fields ───────────────────────────────────────────
      "detail_ready":           bool,  # question + answer/rubric + explanation present
      "progress_countable":     bool,  # enough to count as an attempt
      "truth_eligible":         bool,  # concept label + result + evidence for classification
      "missing_fields":         list[str],
      "degraded_reason":        str,   # learner-friendly; "" when healthy
  }

Path assertions use the ACTUAL read-model structure:
  report["learner_facing"]["recent_attempts"][0]["quality"]
NOT the plan's draft assertion report["learning_brain"]["attempts"][0].
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.learning_report_read_model import (
    build_learning_report_read_model,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def learning_evidence_event(
    *,
    question_stem: str = "关于主体结构验收条件的说法，正确的是？",
    question_type: str = "mcq",
    user_answer: str = "A",
    correct_answer: str = "B",
    explanation: dict | str | None = None,
    explanation_missing_reason: str = "",
    concept_label: str = "主体结构",
    error_label: str = "M06",
    score_awarded: float = 0.0,
    max_score: float = 1.0,
    question_id: str = "test_q_001",
    turn_id: str = "test_turn_001",
    days_ago: int = 0,
) -> LearnerStateEvent:
    """Construct a LearnerStateEvent wrapping a build_learning_evidence_payload dict.

    This is a test-only helper; it does NOT modify build_learning_evidence_payload's
    signature (fat skill stays untouched).
    """
    errors = [] if (score_awarded >= max_score and max_score > 0) else [
        {
            "error_code": error_label,
            "concept_tag": concept_label,
            "rubric_item_id": "r1",
            "diagnosis": f"作答错误，涉及{concept_label}知识点。",
        }
    ]
    grading_result: dict = {
        "type": question_type,
        "question_id": question_id,
        "question_stem": question_stem,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "score_awarded": score_awarded,
        "max_score": max_score,
        "error_events": errors,
        "next_training_signal": {
            "concept": concept_label,
            "focus": question_stem[:20],
            "mode": "practice",
        },
    }
    if explanation is not None:
        grading_result["explanation"] = explanation
    if explanation_missing_reason:
        grading_result["explanation_missing_reason"] = explanation_missing_reason

    payload = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=turn_id,
    )
    return LearnerStateEvent(
        event_id=f"qgate_{question_id}_{turn_id}",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{turn_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=f"qgate_{question_id}_{turn_id}",
        created_at=_iso(days_ago),
        payload_json=payload,
    )


class FakeMemberService:
    def get_today_progress(self, user_id: str) -> dict:
        return {"today_done": 0, "daily_target": 30, "streak_days": 0}

    def get_home_dashboard(self, user_id: str) -> dict:
        return {
            "review": {"due_today": 0},
            "mastery": {"weak_nodes": []},
            "today": {"hint": ""},
            "study_plan": {},
            "progress_feedback": {"cards": []},
        }

    def get_assessment_profile(self, user_id: str) -> dict:
        return {
            "level": "beginner",
            "chapter_mastery": {},
            "diagnostic_feedback": {"learner_profile": {"study_tip": ""}},
        }

    def get_mastery_dashboard(self, user_id: str) -> dict:
        return {
            "overall_mastery": 0,
            "groups": [],
            "hotspots": [],
            "review_summary": {"total_due": 0, "overdue_count": 0},
        }


class FakeLearnerStateService:
    def __init__(self, events: list[LearnerStateEvent]) -> None:
        self.events = list(events)

    def list_memory_events(self, user_id: str, limit: int | None = 100) -> list[LearnerStateEvent]:
        return self.events[-limit:] if limit else self.events

    def read_compiled_learning_truth(self, user_id: str) -> dict:
        return {}

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool, event_limit: int | None = None) -> dict:
        from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
        assert dry_run is True
        return {"projection": synthesize_learning_truth(self.list_memory_events(user_id, limit=event_limit))}


def _build_report(events: list[LearnerStateEvent]) -> dict:
    return build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(events),
        event_limit=50,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. build_learning_evidence_payload quality gate (unit level)
# ─────────────────────────────────────────────────────────────────────────────


def test_complete_mcq_evidence_is_detail_ready_and_truth_eligible() -> None:
    """A complete MCQ event with stem + answers + explanation is detail_ready and truth_eligible."""
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "mcq",
            "question_id": "mcq_001",
            "question_stem": "关于主体结构验收条件的说法，正确的是？",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {"summary": "正确选项是 B", "why_user_wrong": "A 漏掉并列条件"},
            "error_events": [
                {
                    "error_code": "M06",
                    "concept_tag": "主体结构",
                    "diagnosis": "漏选了一个关键选项。",
                }
            ],
            "next_training_signal": {
                "concept": "主体结构",
                "focus": "并列条件判断",
                "mode": "practice",
            },
        },
        turn_id="turn_complete_mcq",
    )

    quality = payload["quality"]
    assert quality["detail_ready"] is True, "complete MCQ with explanation must be detail_ready"
    assert quality["truth_eligible"] is True, "complete MCQ with concept + result must be truth_eligible"
    assert quality["progress_countable"] is True
    assert quality["missing_fields"] == []
    assert quality["degraded_reason"] == ""


def test_missing_explanation_progress_countable_but_not_detail_ready() -> None:
    """An event without explanation counts as progress but is NOT detail_ready."""
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "mcq",
            "question_id": "mcq_002",
            "question_stem": "关于防火分区的说法，正确的是？",
            "user_answer": "C",
            "correct_answer": "D",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": None,
            "explanation_missing_reason": "grading_output_missing_explanation",
            "error_events": [
                {
                    "error_code": "M01",
                    "concept_tag": "防火分区",
                    "diagnosis": "基础知识不扎实。",
                }
            ],
            "next_training_signal": {
                "concept": "防火分区",
                "focus": "分区面积",
                "mode": "practice",
            },
        },
        turn_id="turn_no_explanation",
    )

    quality = payload["quality"]
    assert quality["progress_countable"] is True, "event with question+answer+concept is progress_countable"
    assert quality["detail_ready"] is False, "missing explanation must make detail_ready=False"
    assert "explanation" in quality["missing_fields"]


def test_missing_concept_label_not_truth_eligible() -> None:
    """An event without concept_tag is NOT truth_eligible (cannot be classified as weak/strong)."""
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "mcq",
            "question_id": "mcq_003",
            "question_stem": "关于消防疏散通道的说法，正确的是？",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": "正确选项是 B，因为疏散宽度要求不同。",
            "error_events": [
                {
                    # No concept_tag — concept label is missing
                    "error_code": "M05",
                    "diagnosis": "审题方向错误。",
                }
            ],
            "next_training_signal": {
                # No concept
                "focus": "通道宽度",
                "mode": "practice",
            },
        },
        turn_id="turn_no_concept",
    )

    quality = payload["quality"]
    assert quality["truth_eligible"] is False, "missing concept label must make truth_eligible=False"
    assert "concept_label" in quality["missing_fields"]


def test_progress_countable_true_even_when_detail_not_ready() -> None:
    """progress_countable=True can coexist with detail_ready=False."""
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "mcq",
            "question_id": "mcq_004",
            "question_stem": "关于施工总承包的说法？",
            "user_answer": "B",
            "correct_answer": "C",
            "score_awarded": 0,
            "max_score": 1,
            # No explanation at all
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "施工总承包",
                    "diagnosis": "漏掉关键采分点。",
                }
            ],
            "next_training_signal": {
                "concept": "施工总承包",
                "focus": "分包管理",
                "mode": "practice",
            },
        },
        turn_id="turn_progress_only",
    )

    quality = payload["quality"]
    assert quality["progress_countable"] is True
    assert quality["detail_ready"] is False
    # Both can be reported simultaneously
    assert "explanation" in quality["missing_fields"]


def test_existing_quality_fields_are_preserved() -> None:
    """Backward compat: evidence_level, writeback_eligible, stable_truth_eligible,
    evidence_cap_reasons must still be present alongside new fields."""
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case_005",
            "question_stem": "某项目需要组织专家论证，正确做法是什么？",
            "user_answer": "应加强管理。",
            "correct_answer": "应组织专家论证。",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": "基坑工程超深时必须组织专家论证，这是刚性规范要求。",
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "1A432000",
                    "diagnosis": "漏写专家论证要求。",
                }
            ],
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "专家论证程序",
                "mode": "case_repair",
            },
        },
        turn_id="turn_compat",
    )

    quality = payload["quality"]
    # Old fields must not be removed
    assert "evidence_level" in quality
    assert "writeback_eligible" in quality
    assert "stable_truth_eligible" in quality
    assert "evidence_cap_reasons" in quality
    # New fields must exist
    assert "detail_ready" in quality
    assert "progress_countable" in quality
    assert "truth_eligible" in quality
    assert "missing_fields" in quality
    assert "degraded_reason" in quality


# ─────────────────────────────────────────────────────────────────────────────
# 2. Read model surface: recent_attempts[*].quality (integration level)
# ─────────────────────────────────────────────────────────────────────────────


def test_recent_attempts_expose_quality_field() -> None:
    """Read model recent_attempts cards must include the quality dict."""
    event = learning_evidence_event(
        explanation={"summary": "正确选项是 B", "why_user_wrong": "选项 A 不满足并列条件"},
        concept_label="主体结构",
    )
    report = _build_report([event])
    attempts = report["learner_facing"]["recent_attempts"]
    assert len(attempts) >= 1
    assert "quality" in attempts[0], "recent_attempts card must expose quality field"


def test_detail_ready_true_when_explanation_present_in_report() -> None:
    """report surface: detail_ready=True when explanation is provided."""
    event = learning_evidence_event(
        question_stem="关于主体结构验收条件的说法，正确的是？",
        user_answer="A",
        correct_answer="B",
        explanation={"summary": "正确选项是 B", "why_user_wrong": "A 漏掉并列条件"},
        concept_label="主体结构",
        error_label="M06",
    )
    report = _build_report([event])
    item = report["learner_facing"]["recent_attempts"][0]
    assert item["quality"]["detail_ready"] is True
    assert item["quality"]["truth_eligible"] is True
    assert item["quality"]["progress_countable"] is True


def test_detail_ready_false_when_explanation_missing_in_report() -> None:
    """report surface: detail_ready=False and missing_fields has 'explanation' when no explanation given."""
    event = learning_evidence_event(
        question_stem="关于防火分区的说法，正确的是？",
        user_answer="C",
        correct_answer="D",
        explanation=None,
        explanation_missing_reason="grading_output_missing_explanation",
        concept_label="防火分区",
    )
    report = _build_report([event])
    item = report["learner_facing"]["recent_attempts"][0]
    assert item["quality"]["progress_countable"] is True
    assert item["quality"]["detail_ready"] is False
    assert "explanation" in item["quality"]["missing_fields"]


def test_truth_eligible_false_when_concept_missing_in_report() -> None:
    """report surface: truth_eligible=False when no concept label present."""
    # Build a raw event with no concept_tag
    grading_result = {
        "type": "mcq",
        "question_id": "no_concept_q",
        "question_stem": "某施工现场安全要求正确的是？",
        "user_answer": "A",
        "correct_answer": "B",
        "score_awarded": 0,
        "max_score": 1,
        "explanation": "正确答案是 B。",
        "error_events": [
            # No concept_tag
            {"error_code": "M01", "diagnosis": "知识不扎实。"}
        ],
        "next_training_signal": {
            # No concept
            "focus": "安全管理",
            "mode": "practice",
        },
    }
    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="no_concept_turn")
    event = LearnerStateEvent(
        event_id="qgate_no_concept",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:no_concept_turn",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="qgate_no_concept",
        created_at=_iso(0),
        payload_json=payload,
    )
    report = _build_report([event])
    item = report["learner_facing"]["recent_attempts"][0]
    assert item["quality"]["truth_eligible"] is False
    assert "concept_label" in item["quality"]["missing_fields"]
