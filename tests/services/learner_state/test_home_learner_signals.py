from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.learner_state.home_learner_signals import (
    build_home_learner_signals,
)


def _dispute_event(event_id: str, concept_id: str, ability: str = "code_application") -> SimpleNamespace:
    return SimpleNamespace(
        event_id=event_id,
        memory_kind="learning_evidence",
        source_feature="conversation_synthesis",
        payload_json={
            "learning_signal_type": "user_dispute",
            "concept_id": concept_id,
            "concept_label": concept_id,
            "ability_dimension": ability,
            "user_says": "not_mastered",
        },
    )


def test_review_empty_when_no_due_probe() -> None:
    signals = build_home_learner_signals(user_id="u1", memory_events=[], mastery_items=[])
    assert signals["review"] == {"overdue": 0, "due_today": 0}


def test_review_due_today_from_single_canonical_probe() -> None:
    signals = build_home_learner_signals(
        user_id="u1",
        memory_events=[_dispute_event("e1", "防水工程")],
        mastery_items=[],
    )
    # v0 capacity 1: one probe emitted → due_today 1, nothing suppressed → overdue 0.
    assert signals["review"] == {"overdue": 0, "due_today": 1}


def test_review_overdue_from_suppressed_due_probes() -> None:
    signals = build_home_learner_signals(
        user_id="u1",
        memory_events=[
            _dispute_event("e1", "防水工程", "code_application"),
            _dispute_event("e2", "屋面工程", "concept_recall"),
        ],
        mastery_items=[],
    )
    # Two due probes, capacity 1 → 1 emitted (due_today), 1 suppressed (overdue).
    assert signals["review"] == {"overdue": 1, "due_today": 1}


def test_weak_nodes_filtered_and_sorted_from_mastery_items() -> None:
    signals = build_home_learner_signals(
        user_id="u1",
        memory_events=[],
        mastery_items=[
            {"name": "A", "mastery": 80},  # >= 60, excluded
            {"name": "B", "mastery": 30},
            {"name": "C", "mastery": 59},
            {"name": "", "mastery": 10},  # no name, excluded
        ],
    )
    assert signals["weak_nodes"] == [
        {"name": "B", "mastery": 30},
        {"name": "C", "mastery": 59},
    ]


def test_source_status_marks_weak_nodes_not_collapsed() -> None:
    signals = build_home_learner_signals(user_id="u1", memory_events=[], mastery_items=[])
    weak_status = signals["source_status"]["weak_nodes"]
    # Honest annotation: mastery numbers have no lower canonical source yet.
    assert weak_status["collapsed"] is False
    assert weak_status["mastery_source"] == "member_chapter_mastery"
