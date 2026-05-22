"""Phase -1.D: synthesis event-window flag.

learning_synthesis.synthesize_learning_truth currently iterates all events
unbounded. With 2000+ events per long-lived learner the p95 budget (200ms)
is at risk. This module adds an opt-in ``event_limit`` keyword that windows
to the most-recent N events and surfaces ``window_truncated`` so the read
model can tell the UI that the projection covers only the recent window.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: int) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def _evidence_event(
    *,
    event_id: str,
    days_ago: int,
    concept: str = "1A412010",
    error_code: str = "M01",
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_window",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json={
            "event_type": "learning_evidence",
            "question_id": f"q_{event_id}",
            "question_stem": "测试题",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": error_code, "concept_tag": concept, "diagnosis": "test"}],
            "next_training_signal": {"concept": concept, "focus": "test", "mode": "practice"},
        },
    )


def test_synthesize_learning_truth_window_truncated_false_when_no_limit() -> None:
    """Backward compat: callers that don't pass event_limit see the existing
    behavior; ``window_truncated`` is explicitly False so consumers can
    check the flag without KeyError."""
    events = [_evidence_event(event_id=f"e{i}", days_ago=i) for i in range(5)]
    projection = synthesize_learning_truth(events)
    assert projection["window_truncated"] is False


def test_synthesize_learning_truth_window_truncated_false_when_under_limit() -> None:
    """When event_limit is set but len(events) <= event_limit, no truncation."""
    events = [_evidence_event(event_id=f"e{i}", days_ago=i) for i in range(5)]
    projection = synthesize_learning_truth(events, event_limit=10)
    assert projection["window_truncated"] is False


def test_synthesize_learning_truth_window_truncates_to_recent_n_events() -> None:
    """When len(events) > event_limit, only the most recent event_limit
    events are processed and ``window_truncated`` is True. Recency is by
    created_at."""
    # 12 events spanning 12 days; days_ago=0 is the newest.
    events = [_evidence_event(event_id=f"e{i:02d}", days_ago=i) for i in range(12)]

    projection = synthesize_learning_truth(events, event_limit=5)

    assert projection["window_truncated"] is True
    # The synthesis_run summary should reflect the windowed count.
    assert projection["synthesis_run"]["input_event_count"] == 5


def test_synthesize_learning_truth_window_zero_or_negative_is_ignored() -> None:
    """A zero or negative event_limit is interpreted as "no window" so a
    caller that accidentally passes 0 does not silently lose all events."""
    events = [_evidence_event(event_id=f"e{i}", days_ago=i) for i in range(3)]

    projection_zero = synthesize_learning_truth(events, event_limit=0)
    assert projection_zero["window_truncated"] is False
    assert projection_zero["synthesis_run"]["input_event_count"] == 3

    projection_negative = synthesize_learning_truth(events, event_limit=-1)
    assert projection_negative["window_truncated"] is False
    assert projection_negative["synthesis_run"]["input_event_count"] == 3
