from __future__ import annotations

from datetime import datetime, timezone

from deeptutor.services.learner_state.service import LearnerStateEvent


def _event(event_id: str = "evt_detail_1", *, user_id: str = "student_demo") -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id=user_id,
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        payload_json={
            "event_type": "learning_evidence",
            "question_id": "q1",
            "question_stem": "关于主体结构验收条件的说法，正确的是？",
            "options": {"A": "错误做法", "B": "正确做法"},
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {
                "summary": "正确选项是 B。",
                "why_user_wrong": "A 忽略了验收前置条件。",
            },
            "error_events": [
                {
                    "error_code": "M06",
                    "concept_tag": "1A432000",
                    "diagnosis": "多选漏选。",
                }
            ],
            "next_training_signal": {"concept": "1A432000", "focus": "验收条件", "mode": "case_repair"},
        },
    )


class FakeLearnerStateService:
    def __init__(self, events: list[LearnerStateEvent]) -> None:
        self.events = {event.event_id: event for event in events}
        self.read_calls: list[tuple[str, str]] = []

    def read_learning_evidence_event(self, user_id: str, event_id: str, *, max_age_seconds=None):
        self.read_calls.append((user_id, event_id))
        event = self.events.get(event_id)
        if event is None or event.user_id != user_id:
            return None
        return event


def test_attempt_detail_contains_question_answer_explanation_and_sources() -> None:
    from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    event = _event()
    service = FakeLearnerStateService([event])
    detail = build_attempt_detail_read_model(
        user_id="student_demo",
        learner_state_service=service,
        attempt_ref=sign_attempt_ref(user_id="student_demo", event_id=event.event_id, question_id="q1"),
    )

    assert service.read_calls == [("student_demo", "evt_detail_1")]
    assert detail["ok"] is True
    assert detail["question"]["stem"] == "关于主体结构验收条件的说法，正确的是？"
    assert detail["answer"]["user_answer"] == "A"
    assert detail["answer"]["correct_answer"] == "B"
    assert detail["explanation"]["summary"] == "正确选项是 B。"
    assert detail["explanation"]["why_user_wrong"] == "A 忽略了验收前置条件。"
    assert detail["evidence_sources"][0]["label"] in {"当时作答", "本次批改"}
    assert "evt_detail_1" not in str(detail)


def test_attempt_detail_rejects_cross_user_ref() -> None:
    from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    event = _event()
    service = FakeLearnerStateService([event])

    detail = build_attempt_detail_read_model(
        user_id="other_user",
        learner_state_service=service,
        attempt_ref=sign_attempt_ref(user_id="student_demo", event_id=event.event_id, question_id="q1"),
    )

    assert detail["ok"] is False
    assert detail["error"] == "invalid_attempt_ref"
    assert service.read_calls == []


def test_attempt_detail_maps_string_explanation_to_summary() -> None:
    from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    event = _event()
    event.payload_json["explanation"] = "这题要先判断验收条件。"

    detail = build_attempt_detail_read_model(
        user_id="student_demo",
        learner_state_service=FakeLearnerStateService([event]),
        attempt_ref=sign_attempt_ref(user_id="student_demo", event_id=event.event_id, question_id="q1"),
    )

    assert detail["explanation"]["summary"] == "这题要先判断验收条件。"
    assert detail["explanation"]["why_user_wrong"] == ""


def test_attempt_detail_surfaces_explanation_through_full_evidence_pipeline() -> None:
    """End-to-end recovery test: grading_result → build_learning_evidence_payload →
    LearnerStateEvent → build_attempt_detail_read_model.

    The detail surface and conversation turns must carry the real grader explanation,
    not a generic 'A 选项不符合标准答案' fallback. This locks the regression that the
    accident on 2026-05-22 exposed.
    """
    from deeptutor.services.construction_grading.learning_evidence import build_learning_evidence_payload
    from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    payload_json = build_learning_evidence_payload(
        grading_result={
            "type": "mcq",
            "question_id": "fire_q_001",
            "question_stem": "关于消防疏散通道的说法，正确的是？",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {
                "summary": "正确选项是 B，疏散宽度需按人数计算。",
                "why_user_wrong": "A 错把固定宽度当成通用要求。",
            },
            "error_events": [
                {"error_code": "M08", "concept_tag": "消防疏散", "diagnosis": "规范数字混淆。"}
            ],
            "next_training_signal": {"concept": "消防疏散", "focus": "宽度计算", "mode": "practice"},
        },
        turn_id="turn_fire_001",
    )

    event_id = "evt_fire_001"
    event = LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:turn_fire_001",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        payload_json=payload_json,
    )

    detail = build_attempt_detail_read_model(
        user_id="student_demo",
        learner_state_service=FakeLearnerStateService([event]),
        attempt_ref=sign_attempt_ref(
            user_id="student_demo", event_id=event_id, question_id="fire_q_001"
        ),
    )

    assert detail["ok"] is True, detail
    assert detail["explanation"]["summary"] == "正确选项是 B，疏散宽度需按人数计算。"
    assert detail["explanation"]["why_user_wrong"] == "A 错把固定宽度当成通用要求。"

    # next_training must surface from the payload so the UI can render the follow-up step.
    assert detail["next_training"].get("focus") == "宽度计算"
    assert detail["next_training"].get("concept") == "消防疏散"

    # The conversation turn marked '系统解析' must contain the real explanation text,
    # not a degraded fallback ('A 选项不符合标准答案' or similar generic prose).
    system_turns = [turn for turn in detail["conversation"]["turns"] if turn["role"] == "system"]
    assert any("疏散宽度" in str(turn.get("content") or "") for turn in system_turns), (
        f"system turn must include real explanation, got {system_turns}"
    )
