from __future__ import annotations

import pytest

from deeptutor.services.learner_state.evidence_story_read_model import (
    build_evidence_story_read_model,
)
from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from deeptutor.services.learner_state.prescription_outcome_read_model import (
    build_prescription_outcomes_read_projection,
)
from tests.fixtures.learning_state_scenarios import SCENARIOS


@pytest.mark.parametrize("scenario_name", sorted(SCENARIOS))
def test_learning_state_scenarios_are_projection_safe(scenario_name: str) -> None:
    events = SCENARIOS[scenario_name]()

    projection = project_three_layer_learning_state(events=events)
    outcomes = build_prescription_outcomes_read_projection(events=events)
    story = build_evidence_story_read_model(
        user_id="student_demo",
        evidence_events=events,
        learning_state=projection,
        prescription_outcomes=outcomes,
    )

    assert projection["source_status"]["authority"] == "learner_memory_events.learning_evidence"
    assert story["privacy"]["learner_handle"] == "learner_a"
    assert story["privacy"]["raw_chat_included"] is False


def test_abandonment_scenario_requires_prescription_followup() -> None:
    events = SCENARIOS["abandonment"]()

    outcomes = build_prescription_outcomes_read_projection(events=events)

    assert outcomes[0]["training_intent_id"] == "intent_abandoned"
    assert outcomes[0]["status"] == "needs_followup"
    assert outcomes[0]["next_required_action"] == "resume_prescription"
    assert outcomes[0]["evidence_refs"] == ["evt_abandoned"]


def test_low_quality_chat_does_not_create_learning_state_claims() -> None:
    events = SCENARIOS["low_quality_chat"]()

    projection = project_three_layer_learning_state(events=events)

    assert projection["knowledge_state"] == []
    assert projection["ability_state"] == []
    assert projection["behavior_state"] == []
    assert projection["source_status"]["legacy_count"] == 1


def test_contradiction_scenario_projects_improving_state() -> None:
    events = SCENARIOS["contradiction"]()

    projection = project_three_layer_learning_state(events=events)

    assert projection["knowledge_state"][0]["state"] == "improving"
    assert projection["ability_state"][0]["state"] == "improving"
    assert projection["knowledge_state"][0]["evidence_refs"] == [
        "evt_contra_miss",
        "evt_contra_hit",
    ]


def test_backfill_scenario_tolerates_legacy_payload_without_story_claim() -> None:
    events = SCENARIOS["backfill"]()
    projection = project_three_layer_learning_state(events=events)
    outcomes = build_prescription_outcomes_read_projection(events=events)

    story = build_evidence_story_read_model(
        user_id="student_demo",
        evidence_events=events,
        learning_state=projection,
        prescription_outcomes=outcomes,
    )

    assert projection["knowledge_state"][0]["state"] == "observed"
    assert projection["knowledge_state"][0]["granularity"] == ""
    assert story["evidence_chain"] == []


def test_revalidation_scenario_links_initial_pattern_to_verified_improvement() -> None:
    events = SCENARIOS["revalidation"]()
    projection = project_three_layer_learning_state(events=events)
    outcomes = build_prescription_outcomes_read_projection(events=events)

    story = build_evidence_story_read_model(
        user_id="student_demo",
        evidence_events=events,
        learning_state=projection,
        prescription_outcomes=outcomes,
    )

    assert outcomes[0]["status"] == "verified"
    assert outcomes[0]["score_ratio"] == 1.0
    assert [item["type"] for item in story["evidence_chain"]] == [
        "initial_pattern",
        "prescription_assigned",
        "verified_improvement",
    ]
    assert story["evidence_chain"][-1]["evidence_refs"] == ["evt_reval_hit"]


def test_scenario_matrix_names_required_release_cases() -> None:
    assert set(SCENARIOS) == {
        "cold_start",
        "abandonment",
        "multi_prescription",
        "multi_device",
        "free_tier",
        "low_quality_chat",
        "contradiction",
        "backfill",
        "revalidation",
    }
