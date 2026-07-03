"""§2.1 学-evidence（lesson_viewed）契约与逐消费者断言。

契约钉死：event_type 硬要求 / progress_countable=false / evidence_level=exposed /
source_feature=luban_lesson 留在 synthesis 白名单外 / dedupe_key 含 watched_stage。
消费者矩阵：synthesis 不吃、report 不刷 attempt/streak、mastery attempts 跳过、
today_focus 不被顶、learning_state_projection 显式分类、supabase outbox 白名单在列。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deeptutor.services.learner_state.lesson_evidence import (
    LESSON_VIEWED_SIGNAL,
    SOURCE_FEATURE,
    is_lesson_view_event,
    record_lesson_view_evidence,
)
from deeptutor.services.learner_state.service import LearnerStateEvent


class _RecordingLearnerState:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def append_memory_event(self, user_id, **kwargs):
        self.calls.append({"user_id": user_id, **kwargs})
        return type("Event", (), {"event_id": f"evt_{len(self.calls)}", **kwargs})()


def _lesson_event(event_id: str = "lesson_evt_1", *, stage: str = "lesson") -> LearnerStateEvent:
    recorder = _RecordingLearnerState()
    record_lesson_view_evidence(
        recorder,
        user_id="student_demo",
        pack_id="N01",
        watched_stage=stage,
        card_sha="sha256:card",
        now=datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
    )
    call = recorder.calls[0]
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature=call["source_feature"],
        source_id=call["source_id"],
        source_bot_id=None,
        memory_kind=call["memory_kind"],
        dedupe_key=call["dedupe_key"],
        created_at="2026-07-03T18:00:00+08:00",
        payload_json=call["payload_json"],
    )


def test_lesson_evidence_payload_honors_contract_and_plan() -> None:
    recorder = _RecordingLearnerState()
    record_lesson_view_evidence(
        recorder,
        user_id="student_demo",
        pack_id="N01",
        watched_stage="practice",
        card_sha="sha256:card",
        now=datetime(2026, 7, 3, 2, 0, tzinfo=timezone.utc),  # 北京 10:00
    )
    call = recorder.calls[0]
    payload = call["payload_json"]
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_feature"] == SOURCE_FEATURE == "luban_lesson"
    assert payload["event_type"] == "learning_evidence"  # contract:397-404 硬要求
    assert payload["learning_signal_type"] == LESSON_VIEWED_SIGNAL
    assert payload["evidence_level"] == "exposed"
    assert payload["quality"] == {"progress_countable": False}
    assert payload["pack_id"] == "N01"
    assert payload["watched_stage"] == "practice"
    # dedupe 按（用户, pack, 幕, 业务日）细分：同日重看折叠，跨幕各自成条。
    assert call["dedupe_key"] == "lesson_viewed:student_demo:N01:practice:2026-07-03"


def test_lesson_evidence_rejects_unknown_stage_and_blank_ids() -> None:
    recorder = _RecordingLearnerState()
    with pytest.raises(ValueError):
        record_lesson_view_evidence(recorder, user_id="u", pack_id="N01", watched_stage="binge")
    with pytest.raises(ValueError):
        record_lesson_view_evidence(recorder, user_id="", pack_id="N01", watched_stage="lesson")
    with pytest.raises(ValueError):
        record_lesson_view_evidence(recorder, user_id="u", pack_id="", watched_stage="lesson")
    assert recorder.calls == []


def test_synthesis_never_eats_lesson_evidence() -> None:
    from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth

    projection = synthesize_learning_truth([_lesson_event()])
    assert projection["weak_points"] == []
    assert projection["observed_candidates"] == []
    assert projection["compiled_objects"] == {}


def test_report_aggregation_does_not_count_lesson_views_as_attempts() -> None:
    from deeptutor.services.learner_state.learning_report_read_model import (
        _aggregate_learning_evidence,
        _learning_evidence_events,
    )

    events = _learning_evidence_events([_lesson_event()])
    stats = _aggregate_learning_evidence(events)
    assert stats["attempt_count"] == 0
    assert stats["today_done"] == 0
    assert stats["streak_days"] == 0
    assert stats["attempts_by_label"] == {}


def test_mastery_estimator_skips_lesson_views() -> None:
    from deeptutor.services.learner_state.mastery_estimator import estimate_mastery

    estimate = estimate_mastery(attempts=[_lesson_event()], legacy_score=0)
    assert estimate["sample_count"] == 0
    assert estimate["status"] == "insufficient_evidence"


def test_today_focus_is_not_hijacked_by_lesson_view() -> None:
    from deeptutor.services.learner_state.home_personalization import (
        _projection_from_recent_learning_events,
    )

    projection = _projection_from_recent_learning_events(
        [_lesson_event()],
        generated_at=datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
    )
    assert projection is None


def test_learning_state_projection_classifies_lesson_views_explicitly() -> None:
    from deeptutor.services.learner_state.learning_state_projection import (
        project_three_layer_learning_state,
    )

    projection = project_three_layer_learning_state(events=[_lesson_event()])
    status = projection["source_status"]
    assert status["lesson_view_count"] == 1
    assert status["legacy_count"] == 0
    assert status["grading_fact_count"] == 0


def test_supabase_outbox_whitelist_accepts_learning_evidence() -> None:
    from deeptutor.services.learner_state.supabase_writer import LearnerStateSupabaseWriter

    assert LearnerStateSupabaseWriter._supports_event_type("learning_evidence") is True


def test_revalidation_queue_ignores_exposed_lesson_state() -> None:
    # 学-evidence 只到「已学·待验证」；exposed 不在 revalidation 白名单态,
    # 绝不给未验证的接触发复测 probe（M0）。
    from deeptutor.services.learner_state.lesson_evidence import is_lesson_view_event as check

    event = _lesson_event()
    assert check(event) is True
    assert event.payload_json["evidence_level"] == "exposed"
    from deeptutor.services.learner_state.memory_lifecycle import evidence_level_rank

    assert evidence_level_rank("exposed") == -1  # 不参与掌握排序


def test_is_lesson_view_event_rejects_other_sources() -> None:
    grading = LearnerStateEvent(
        event_id="g1",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:g1",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key="g1",
        created_at="2026-07-03T18:00:00+08:00",
        payload_json={"event_type": "learning_evidence", "learning_signal_type": "lesson_viewed"},
    )
    assert is_lesson_view_event(grading) is False
