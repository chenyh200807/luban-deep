"""deep_question 练题路径的 Grading-to-Brain writeback 契约。

约束（与 TutorBot loop 的 _record_v1_grading_to_brain 同一 seam）：
- 复用 write_case_grading_event_learning_evidence，不存在第二写入器；
- 只为 event_type == case_grading_completed 的 V1 事件写 learning_evidence；
- fail-closed：写入失败绝不影响可见批改结果；
- 测试边界为 integration-style：故意不 mock writer 本身，让断言穿过真实的
  write_case_grading_event_learning_evidence + to_learning_evidence 投影，
  以钉住「同一 seam 同一 payload 形状」；只在 learner_state_service 处打桩；
- 成功后在 result_payload 上暴露 grading_to_brain_loop / learning_evidence_event_id，
  authority 恒为 learner_memory_events.learning_evidence。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import _record_v1_grading_to_brain_for_question


class _FakeEvent:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def append_memory_event(self, user_id: str, **kwargs: Any) -> Any:
        self.calls.append({"user_id": user_id, **kwargs})
        return _FakeEvent(f"evt-{len(self.calls)}")


class _ExplodingLearnerStateService:
    def append_memory_event(self, user_id: str, **kwargs: Any) -> Any:
        raise RuntimeError("supabase down")


def _context(user_id: str = "stu_1") -> SimpleNamespace:
    return SimpleNamespace(
        metadata={"user_id": user_id, "bot_id": "construction-exam-coach"},
        config_overrides={},
        session_id="sess-1",
    )


def _v1_event() -> dict[str, Any]:
    return {
        "event_type": "case_grading_completed",
        "question_id": "Q10",
        "awarded_score": 1,
        "max_score": 2,
        "high_risk_review": False,
        "rubric_provenance": "compiled_rubric",
        "scoring_points": [
            {
                "point_id": "P1",
                "knowledge_point": "钢筋调直工艺",
                "hit": "miss",
                "score": 0,
                "max_score": 1,
                "mistake_type": "near_synonym_not_accepted",
                "evidence_span": "普通钢筋调直机",
                "policy_type": "exact_required",
            },
            {
                "point_id": "P2",
                "knowledge_point": "数控设备选型",
                "hit": "hit",
                "score": 1,
                "max_score": 1,
            },
        ],
    }


def _graded_context() -> dict[str, Any]:
    return {
        "question_id": "Q10",
        "user_answer": "应使用普通钢筋调直机。",
        "question_stem": "简述钢筋调直应选用的机械。",
        "node_code": "1A415000",
    }


def test_v1_case_event_writes_learning_evidence_and_marks_result_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeLearnerStateService()
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: service,
    )
    result_payload: dict[str, Any] = {}

    _record_v1_grading_to_brain_for_question(
        context=_context(),
        v1_event=_v1_event(),
        graded_context=_graded_context(),
        result_payload=result_payload,
        turn_id="turn-1",
    )

    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["user_id"] == "stu_1"
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_bot_id"] == "construction-exam-coach"
    assert call["source_id"] == "turn-1:Q10"
    assert call["dedupe_key"]
    payload = call["payload_json"]
    assert payload["legacy_event_type"] == "case_grading_completed"
    assert payload["session_id"] == "sess-1"
    assert payload["canonical_truth_written"] is False
    assert payload["claim_promotion_allowed"] is False

    loop_meta = result_payload["grading_to_brain_loop"]
    assert loop_meta["writeback_count"] == 1
    assert loop_meta["memory_kind"] == "learning_evidence"
    assert loop_meta["authority"] == "learner_memory_events.learning_evidence"
    assert result_payload["learning_evidence_event_id"] == loop_meta["event_id"] == "evt-1"


def test_non_case_event_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakeLearnerStateService()
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: service,
    )
    result_payload: dict[str, Any] = {}

    _record_v1_grading_to_brain_for_question(
        context=_context(),
        v1_event={"status": "unavailable"},
        graded_context=_graded_context(),
        result_payload=result_payload,
        turn_id="turn-1",
    )
    _record_v1_grading_to_brain_for_question(
        context=_context(),
        v1_event=None,
        graded_context=_graded_context(),
        result_payload=result_payload,
        turn_id="turn-1",
    )

    assert service.calls == []
    assert result_payload == {}


def test_missing_user_id_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakeLearnerStateService()
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: service,
    )
    result_payload: dict[str, Any] = {}

    _record_v1_grading_to_brain_for_question(
        context=_context(user_id=""),
        v1_event=_v1_event(),
        graded_context=_graded_context(),
        result_payload=result_payload,
        turn_id="turn-1",
    )

    assert service.calls == []
    assert result_payload == {}


def test_writer_failure_is_fail_closed_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: _ExplodingLearnerStateService(),
    )
    result_payload: dict[str, Any] = {"response": "可见批改结果"}

    _record_v1_grading_to_brain_for_question(
        context=_context(),
        v1_event=_v1_event(),
        graded_context=_graded_context(),
        result_payload=result_payload,
        turn_id="turn-1",
    )

    assert result_payload == {"response": "可见批改结果"}
