from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)
from deeptutor.services.learner_state.learning_brain_read_model import (
    build_learning_brain_read_model,
)
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent


QA_STUDENT_ID = "qa_teacher_review_20260604"


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.events: list[LearnerStateEvent] = []
        self.progress_patches: list[dict[str, Any]] = []

    def append_memory_event(self, user_id: str, **kwargs: Any) -> LearnerStateEvent:
        event = LearnerStateEvent(
            event_id=f"evt-{len(self.events) + 1}",
            user_id=user_id,
            source_feature=str(kwargs.get("source_feature") or ""),
            source_id=str(kwargs.get("source_id") or ""),
            source_bot_id=kwargs.get("source_bot_id"),
            memory_kind=str(kwargs.get("memory_kind") or ""),
            payload_json=dict(kwargs.get("payload_json") or {}),
            dedupe_key=str(kwargs.get("dedupe_key") or ""),
            created_at=f"2026-06-04T00:00:{len(self.events) + 1:02d}+00:00",
        )
        self.events.append(event)
        return event

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch

    def list_memory_events(self, user_id: str, limit: int | None = 20) -> list[LearnerStateEvent]:
        events = [event for event in self.events if event.user_id == user_id]
        return events if limit is None else events[-limit:]

    def synthesize_learning_truth(
        self,
        user_id: str,
        *,
        dry_run: bool = True,
        event_limit: int | None = None,
    ) -> dict[str, Any]:
        projection = synthesize_learning_truth(self.list_memory_events(user_id, limit=event_limit))
        return {"projection": projection, "summary_md": "", "outbox_item": None}


def _pilot_reviews() -> list[dict[str, Any]]:
    return [
        {
            "sample_id": "exact_required_override",
            "case_id": "real-golden-exact-001",
            "student_id": QA_STUDENT_ID,
            "engine": "best_quality_4model",
            "teacher_reviewed": True,
            "point_reviews": [
                {
                    "point_id": "P-exact-01",
                    "label": "官方术语：专项施工方案",
                    "policy_type": "exact_required",
                    "max_score": 2,
                    "ai_hit": "partial",
                    "ai_score": 0.5,
                    "high_risk_review": True,
                    "review_action": "override",
                    "teacher_hit": "miss",
                    "teacher_score": 0,
                    "teacher_note": "未写官方术语，近义不给分",
                },
                {
                    "point_id": "P-exact-02",
                    "label": "官方术语：专项施工方案",
                    "policy_type": "exact_required",
                    "max_score": 2,
                    "ai_hit": "partial",
                    "ai_score": 0.5,
                    "review_action": "override",
                    "teacher_hit": "miss",
                    "teacher_score": 0,
                    "teacher_note": "仍缺专项施工方案官方表述",
                }
            ],
        },
        {
            "sample_id": "list_rule_accept_partial",
            "case_id": "real-golden-list-002",
            "student_id": QA_STUDENT_ID,
            "engine": "best_quality_4model",
            "teacher_reviewed": True,
            "point_reviews": [
                {
                    "point_id": "P-list-01",
                    "label": "资源供应平衡要点",
                    "policy_type": "list_rule",
                    "max_score": 3,
                    "ai_hit": "partial",
                    "ai_score": 1.5,
                    "review_action": "confirm",
                    "teacher_hit": "partial",
                    "teacher_score": 1.5,
                    "teacher_note": "列举不全，仍缺关键要点",
                }
            ],
        },
        {
            "sample_id": "calculation_override_to_miss",
            "case_id": "real-golden-calc-003",
            "student_id": QA_STUDENT_ID,
            "engine": "best_quality_4model",
            "teacher_reviewed": True,
            "point_reviews": [
                {
                    "point_id": "P-calc-01",
                    "label": "流水节拍计算",
                    "policy_type": "calculation",
                    "max_score": 4,
                    "ai_hit": "partial",
                    "ai_score": 2,
                    "review_action": "override",
                    "teacher_hit": "miss",
                    "teacher_score": 0,
                    "teacher_note": "公式或数值错误，计算结果不成立",
                }
            ],
        },
        {
            "sample_id": "direction_check_override",
            "case_id": "real-golden-direction-004",
            "student_id": QA_STUDENT_ID,
            "engine": "best_quality_4model",
            "teacher_reviewed": True,
            "point_reviews": [
                {
                    "point_id": "P-direction-01",
                    "label": "官方术语：专项施工方案",
                    "policy_type": "direction_check",
                    "max_score": 2,
                    "ai_hit": "hit",
                    "ai_score": 2,
                    "review_action": "override",
                    "teacher_hit": "miss",
                    "teacher_score": 0,
                    "teacher_note": "方向错，多答不得分",
                }
            ],
        },
        {
            "sample_id": "full_hit_mastery",
            "case_id": "real-golden-mastery-005",
            "student_id": QA_STUDENT_ID,
            "engine": "best_quality_4model",
            "teacher_reviewed": True,
            "point_reviews": [
                {
                    "point_id": "P-mastery-01",
                    "label": "网络计划关键线路",
                    "policy_type": "exact_required",
                    "max_score": 3,
                    "ai_hit": "hit",
                    "ai_score": 3,
                    "auto_certified": True,
                    "review_action": "confirm",
                    "teacher_hit": "hit",
                    "teacher_score": 3,
                    "teacher_note": "命中关键线路，证据充分",
                }
            ],
        },
    ]


def test_fake_integration_writes_teacher_review_events_and_learning_brain_reads_them() -> None:
    service = _FakeLearnerStateService()

    outputs = [
        build_teacher_review_writeback(
            review,
            dry_run=False,
            learner_state_service=service,
            user_id=QA_STUDENT_ID,
        )
        for review in _pilot_reviews()
    ]

    assert [output["writeback_count"] for output in outputs] == [1, 1, 1, 1, 1]
    assert len(service.events) == 5
    assert {event.memory_kind for event in service.events} == {"learning_evidence"}
    assert all(event.user_id == QA_STUDENT_ID for event in service.events)
    assert all(event.payload_json["next_training_signal"]["teacher_final_grading_result"] for event in service.events)

    payloads = {event.payload_json["question_id"]: event.payload_json for event in service.events}
    assert payloads["real-golden-exact-001"]["error_events"][0]["diagnosis"] == "未写官方术语，近义不给分"
    assert payloads["real-golden-list-002"]["error_events"][0]["diagnosis"] == "列举不全，仍缺关键要点"
    assert payloads["real-golden-calc-003"]["error_events"][0]["error_code"] == "E09"
    assert payloads["real-golden-direction-004"]["error_events"][0]["error_code"] == "E05"
    assert payloads["real-golden-mastery-005"]["error_events"] == []
    mastery_point = payloads["real-golden-mastery-005"]["next_training_signal"]["teacher_review_points"][0]
    assert mastery_point["mastery_eligible"] is True

    synthesis = service.synthesize_learning_truth(QA_STUDENT_ID, dry_run=True, event_limit=50)
    projection = synthesis["projection"]
    read_model = build_learning_brain_read_model(
        user_id=QA_STUDENT_ID,
        projection=projection,
        surface="qa",
    )

    assert read_model["event_count"] == 5
    assert any(item["concept_id"] == "官方术语：专项施工方案" for item in read_model["weak_points"])
    assert any(item["concept_id"] == "网络计划关键线路" for item in read_model["improvement_signals"])
    assert all(
        not point["mastery_eligible"]
        for output in outputs
        for point in output["write_plan"]
        if point["point_id"] != "P-mastery-01"
    )
