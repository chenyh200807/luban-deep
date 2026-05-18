from __future__ import annotations

from deeptutor.services.learner_state.learning_synthesis import (
    find_concept_evidence,
    find_question_graph_context,
    trace_training_recommendation,
    synthesize_learning_truth,
)
from tests.services.learner_state.test_learning_synthesis import _learning_event


def test_graph_context_can_query_question_to_training_chain() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002"),
    ])

    context = find_question_graph_context(projection, question_id="case_001")

    assert context["question_id"] == "case_001"
    assert context["rubric_item_ids"] == ["case_001:r1"]
    assert context["error_ids"] == ["1A432000:E02"]
    assert context["training_target_ids"] == ["1A432000:E02:case_repair"]
    assert context["evidence_event_ids"] == ["evt1"]


def test_graph_context_can_query_concept_evidence() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002"),
    ])

    evidence = find_concept_evidence(projection, concept_id="1A432000")

    assert evidence["evidence_level"] == "L1_repeated"
    assert evidence["supporting_event_ids"] == ["evt1", "evt2"]
    assert evidence["timeline_refs"][0]["event_id"] == "evt1"


def test_graph_context_can_trace_training_recommendation_reason() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002"),
    ])

    trace = trace_training_recommendation(
        projection,
        training_id="1A432000:E02:case_repair",
    )

    assert trace["error_ids"] == ["1A432000:E02"]
    assert trace["reason_event_ids"] == ["evt1", "evt2"]


def test_graph_projection_reports_missing_concept_readiness_gap() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1", concept_id=""),
    ])

    gaps = projection["typed_graph"]["readiness_gaps"]

    assert gaps[0]["code"] == "missing_concept_edge"
    assert gaps[0]["question_id"] == "case_001"
