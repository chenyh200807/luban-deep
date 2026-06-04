"""Tests for Stream C — teacher-review writeback preview (dry-run first).

Authority rules under test:
  - auto_certified points (teacher confirm OR AI auto_certified not overturned by
    an override) may generate confident mastery evidence.
  - high_risk / unsupported points must NOT become confident mastery evidence —
    they are downweighted / marked non-mastery, never counted as correct.
  - teacher override覆盖 AI draft: final hit/score uses teacher_hit/teacher_score.
  - dry_run (default) never touches a DB; learner_state_service=None must not raise.
  - pure-function conversion: no new table, reuses build_learning_evidence_payload.
"""
from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)


def _review(point_reviews: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": "Q1-NA",
        "student_id": "qa_stu_1",
        "engine": "best_quality_4model",
        "teacher_reviewed": True,
        "point_reviews": point_reviews,
    }


class _RecordingLearnerStateService:
    """Captures append_memory_event calls; never persists."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.progress_patches: list[dict[str, Any]] = []

    def append_memory_event(self, user_id: str, **kwargs: Any) -> Any:
        self.calls.append({"user_id": user_id, **kwargs})

        class _Evt:
            event_id = f"evt-{len(self.calls)}"

        return _Evt()

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch


def test_dry_run_emits_learning_evidence_payload_without_db() -> None:
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "auto_certified": True,
            "teacher_hit": "hit",
            "teacher_score": 5,
            "teacher_note": "认证",
            "review_action": "confirm",
        },
    ])

    # learner_state_service=None must be safe in dry_run.
    out = build_teacher_review_writeback(review, dry_run=True, learner_state_service=None)

    assert out["dry_run"] is True
    payload = out["learning_evidence_payload"]
    assert payload["event_type"] == "learning_evidence"
    assert payload["question_id"] == "Q1-NA"
    assert isinstance(out["write_plan"], list)
    # No DB handle, no persistence, no exception.
    assert "writeback_count" not in out


def test_high_risk_point_is_not_confident_mastery_evidence() -> None:
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "high_risk_review": True,
            "review_reason": "selective_abstention_proxy",
            "teacher_hit": "",
            "teacher_score": None,
            "teacher_note": "",
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)
    plan = {row["point_id"]: row for row in out["write_plan"]}

    assert plan["P1"]["mastery_eligible"] is False
    assert plan["P1"]["disposition"] == "downweighted_pending_review"
    # high_risk point must not be scored as awarded mastery in the rubric item.
    item = _rubric_item(out, "P1")
    assert item["status"] != "full"
    assert item["awarded_score"] == 0


def test_unsupported_point_is_not_confident_mastery_evidence() -> None:
    review = _review([
        {
            "point_id": "P2",
            "label": "资源需要量及供应平衡表",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "unsupported": True,
            "teacher_hit": "",
            "teacher_score": None,
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)
    plan = {row["point_id"]: row for row in out["write_plan"]}

    assert plan["P2"]["mastery_eligible"] is False
    item = _rubric_item(out, "P2")
    assert item["awarded_score"] == 0


def test_teacher_override_beats_ai_draft() -> None:
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "auto_certified": True,
            # teacher disagrees: AI over-credited, teacher marks miss.
            "teacher_hit": "miss",
            "teacher_score": 0,
            "teacher_note": "学生未写规范术语",
            "review_action": "override",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)
    plan = {row["point_id"]: row for row in out["write_plan"]}

    # Teacher override wins: final hit/score reflect teacher, not AI.
    assert plan["P1"]["final_hit"] == "miss"
    assert plan["P1"]["final_score"] == 0
    assert plan["P1"]["authority"] == "teacher_override"
    item = _rubric_item(out, "P1")
    assert item["status"] == "miss"
    assert item["awarded_score"] == 0


def test_teacher_override_can_upgrade_ai_high_risk_to_mastery() -> None:
    # AI flagged high_risk, but teacher reviewed and confirms a real hit via override.
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "partial",
            "ai_score": 2,
            "high_risk_review": True,
            "teacher_hit": "hit",
            "teacher_score": 5,
            "teacher_note": "术语原文正确",
            "review_action": "override",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)
    plan = {row["point_id"]: row for row in out["write_plan"]}

    # Teacher override is the higher authority -> may become mastery despite AI high_risk.
    assert plan["P1"]["final_hit"] == "hit"
    assert plan["P1"]["final_score"] == 5
    assert plan["P1"]["mastery_eligible"] is True
    assert plan["P1"]["authority"] == "teacher_override"


def test_reject_action_does_not_produce_mastery() -> None:
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "auto_certified": True,
            "teacher_hit": "miss",
            "teacher_score": 0,
            "review_action": "reject",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)
    plan = {row["point_id"]: row for row in out["write_plan"]}

    assert plan["P1"]["mastery_eligible"] is False
    assert plan["P1"]["final_hit"] == "miss"


def test_dry_run_is_pure_and_makes_no_service_call() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P1",
            "max_score": 5,
            "ai_hit": "hit",
            "ai_score": 5,
            "auto_certified": True,
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(
        review, dry_run=True, learner_state_service=service, user_id="qa_stu_1"
    )

    assert out["dry_run"] is True
    # Pure conversion: no DB write happened even though a service was passed.
    assert service.calls == []


def test_writeback_when_explicitly_enabled_calls_service() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P1",
            "label": "施工总进度计划表(图)",
            "max_score": 5,
            "ai_hit": "miss",
            "ai_score": 0,
            "auto_certified": True,
            "teacher_hit": "miss",
            "teacher_score": 0,
            "teacher_note": "缺少规范术语",
            "review_action": "override",
        },
    ])

    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id="qa_stu_1"
    )

    assert out["dry_run"] is False
    # An error event (miss) is writeback-eligible -> service got called.
    assert out["writeback_count"] == 1
    assert service.calls
    assert service.calls[0]["memory_kind"] == "learning_evidence"
    payload = service.calls[0]["payload_json"]
    assert payload["question_id"] == "Q1-NA"
    point_events = payload["next_training_signal"]["teacher_review_points"]
    assert point_events[0]["point_id"] == "P1"
    assert point_events[0]["authority"] == "teacher_override"
    assert point_events[0]["final_hit"] == "miss"
    assert point_events[0]["final_score"] == 0.0
    assert point_events[0]["awarded_score"] == 0.0
    assert point_events[0]["mastery_eligible"] is False
    assert point_events[0]["diagnosis"] == "缺少规范术语"
    teacher_final = payload["next_training_signal"]["teacher_final_grading_result"]
    assert teacher_final["teacher_reviewed"] is True
    assert teacher_final["points"][0]["point_id"] == "P1"
    assert teacher_final["points"][0]["final_hit"] == "miss"


def test_teacher_final_point_event_preserves_source_and_evidence_span() -> None:
    review = _review([
        {
            "point_id": "P1",
            "label": "官方术语：专项施工方案",
            "policy_type": "exact_required",
            "max_score": 2,
            "ai_hit": "hit",
            "ai_score": 2,
            "auto_certified": True,
            "teacher_hit": "miss",
            "teacher_score": 0,
            "evidence_span": "施工方案",
            "teacher_note": "近义/半术语，未写官方术语",
            "review_action": "override",
            "source": "teacher_final",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=True)

    plan = out["write_plan"][0]
    assert plan["source"] == "teacher_final"
    assert plan["evidence_span"] == "施工方案"
    point = out["learning_evidence_payload"]["next_training_signal"]["teacher_review_points"][0]
    assert point["source"] == "teacher_final"
    assert point["evidence_span"] == "施工方案"


def test_writeback_payload_does_not_mark_high_risk_or_unsupported_as_mastery() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P-risk",
            "label": "高风险采分点",
            "max_score": 2,
            "ai_hit": "hit",
            "ai_score": 2,
            "high_risk_review": True,
            "review_action": "confirm",
        },
        {
            "point_id": "P-unsupported",
            "label": "无证据采分点",
            "max_score": 2,
            "ai_hit": "hit",
            "ai_score": 2,
            "unsupported": True,
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id="qa_stu_1"
    )

    assert out["writeback_count"] == 1
    payload = service.calls[0]["payload_json"]
    point_events = {row["point_id"]: row for row in payload["next_training_signal"]["teacher_review_points"]}
    assert point_events["P-risk"]["mastery_eligible"] is False
    assert point_events["P-risk"]["diagnosis"] == "高风险点，降权待复核，不计入确定 mastery"
    assert point_events["P-unsupported"]["mastery_eligible"] is False
    assert point_events["P-unsupported"]["diagnosis"] == "证据不支持（span 未逐字出现），降权待复核"


def test_teacher_reviewed_full_hit_can_persist_success_learning_evidence() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P-calc",
            "label": "流水节拍计算",
            "max_score": 4,
            "ai_hit": "hit",
            "ai_score": 4,
            "teacher_hit": "hit",
            "teacher_score": 4,
            "teacher_note": "计算过程与结果一致，不归为术语错因",
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id="qa_stu_1"
    )

    assert out["writeback_count"] == 1
    payload = service.calls[0]["payload_json"]
    assert payload["error_events"] == []
    assert payload["next_training_signal"]["concept"] == "流水节拍计算"
    assert payload["next_training_signal"]["teacher_review_points"][0]["mastery_eligible"] is True


def test_teacher_reviewed_false_does_not_write_when_explicitly_enabled() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P1",
            "max_score": 5,
            "ai_hit": "miss",
            "ai_score": 0,
            "review_action": "confirm",
        },
    ])
    review["teacher_reviewed"] = False

    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id="qa_stu_1"
    )

    assert out["writeback_count"] == 0
    assert out["writeback_skipped_reason"] == "teacher_reviewed_required"
    assert service.calls == []


def test_non_qa_user_id_does_not_write_when_explicitly_enabled() -> None:
    service = _RecordingLearnerStateService()
    review = _review([
        {
            "point_id": "P1",
            "max_score": 5,
            "ai_hit": "miss",
            "ai_score": 0,
            "review_action": "confirm",
        },
    ])
    review["student_id"] = "real_student_123"

    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id="real_student_123"
    )

    assert out["writeback_count"] == 0
    assert out["writeback_skipped_reason"] == "qa_user_id_required"
    assert service.calls == []


def test_writeback_disabled_without_service_even_if_not_dry_run() -> None:
    # dry_run=False but no service -> must not raise, must not pretend to write.
    review = _review([
        {
            "point_id": "P1",
            "ai_hit": "miss",
            "ai_score": 0,
            "max_score": 5,
            "review_action": "confirm",
        },
    ])

    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=None)

    assert out["writeback_count"] == 0
    assert out.get("writeback_skipped_reason") == "no_learner_state_service"


def _rubric_item(out: dict[str, Any], point_id: str) -> dict[str, Any]:
    items = out["learning_evidence_payload"]["rubric_items"]
    for item in items:
        if item.get("criterion") == point_id:
            return item
    raise AssertionError(f"rubric item {point_id} not found in payload")
