from __future__ import annotations

from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from tests.fixtures.learning_state_scenarios import learning_event


def test_repeated_same_cluster_dedupes_into_one_recurrence_card() -> None:
    projection = project_three_layer_learning_state(
        events=[
            learning_event("evt_cluster_1", days_ago=5),
            learning_event("evt_cluster_2", days_ago=1),
        ]
    )

    recurrence = [
        item for item in projection["behavior_state"] if item["dimension"] == "recurrence"
    ]
    assert len(recurrence) == 1
    assert recurrence[0]["state"] == "recurring"
    assert sorted(recurrence[0]["evidence_refs"]) == ["evt_cluster_1", "evt_cluster_2"]


def test_different_error_code_does_not_merge_recurrence_clusters() -> None:
    projection = project_three_layer_learning_state(
        events=[
            learning_event("evt_e02", error_code="E02"),
            learning_event("evt_e04", error_code="E04"),
        ]
    )

    assert [
        item for item in projection["behavior_state"] if item["dimension"] == "recurrence"
    ] == []
