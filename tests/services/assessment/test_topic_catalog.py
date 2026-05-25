from __future__ import annotations

import pytest

from deeptutor.services.assessment.blueprint import MIN_FORM_ROTATION_COUNT, TARGET_FORM_ROTATION_COUNT
from deeptutor.services.assessment.topic_catalog import (
    REQUIRED_TOPIC_TESTSET_IDS,
    TopicTestSetUnavailable,
    build_topic_assessment_blueprint,
    classify_topic_form_count,
    get_topic_testset_catalog,
    recommend_assessment_entry,
    resolve_topic_testset_spec,
)


def test_catalog_contains_required_p0a_plus_topics() -> None:
    catalog = get_topic_testset_catalog()

    assert [item.topic_id for item in catalog] == list(REQUIRED_TOPIC_TESTSET_IDS)
    assert "waterproof" in REQUIRED_TOPIC_TESTSET_IDS
    assert "decoration" in REQUIRED_TOPIC_TESTSET_IDS
    assert "mep" in REQUIRED_TOPIC_TESTSET_IDS
    assert "foundation" in REQUIRED_TOPIC_TESTSET_IDS
    assert "main_structure" in REQUIRED_TOPIC_TESTSET_IDS
    assert "formwork_scaffold" in REQUIRED_TOPIC_TESTSET_IDS
    assert "safety" in REQUIRED_TOPIC_TESTSET_IDS
    assert "schedule" in REQUIRED_TOPIC_TESTSET_IDS
    assert "contract_claim" in REQUIRED_TOPIC_TESTSET_IDS
    assert "quality_acceptance" in REQUIRED_TOPIC_TESTSET_IDS


def test_catalog_blueprints_share_form_gate_shape() -> None:
    for spec in get_topic_testset_catalog():
        blueprint = build_topic_assessment_blueprint(spec.topic_id)

        assert blueprint.version == spec.blueprint_version
        assert blueprint.requested_count == 12
        assert blueprint.scored_count == 12
        assert len(blueprint.sections) == 3
        assert all(section.count == 4 for section in blueprint.sections)
        assert all(section.strict_topics for section in blueprint.sections)
        assert all(section.minimum_multiplier == MIN_FORM_ROTATION_COUNT for section in blueprint.sections)


def test_form_count_classification_is_fail_closed() -> None:
    assert classify_topic_form_count(0) == "authoring_needed"
    assert classify_topic_form_count(MIN_FORM_ROTATION_COUNT - 1) == "authoring_needed"
    assert classify_topic_form_count(MIN_FORM_ROTATION_COUNT) == "pilot"
    assert classify_topic_form_count(TARGET_FORM_ROTATION_COUNT - 1) == "pilot"
    assert classify_topic_form_count(TARGET_FORM_ROTATION_COUNT) == "stable"


def test_unknown_topic_is_not_mapped_to_waterproof() -> None:
    with pytest.raises(TopicTestSetUnavailable):
        resolve_topic_testset_spec(["unknown_topic"])


def test_recommendation_defaults_to_diagnostic_when_learning_signal_is_insufficient() -> None:
    recommendation = recommend_assessment_entry(
        [{"topic_id": "main_structure", "status": "stable", "enabled": True, "label": "主体结构"}],
        weak_nodes=[],
        has_assessment_history=False,
    )

    assert recommendation["recommended_mode"] == "diagnostic"
    assert recommendation["recommended_count"] == 20
    assert recommendation["source"] == "insufficient_learning_signal"


def test_recommendation_selects_enabled_topic_from_weak_node() -> None:
    recommendation = recommend_assessment_entry(
        [
            {"topic_id": "waterproof", "status": "stable", "enabled": True, "label": "防水工程"},
            {"topic_id": "main_structure", "status": "stable", "enabled": True, "label": "主体结构"},
        ],
        weak_nodes=[{"name": "主体结构施工缝", "mastery": 25}],
        has_assessment_history=True,
    )

    assert recommendation["recommended_mode"] == "topic"
    assert recommendation["recommended_topic_id"] == "main_structure"
    assert recommendation["recommended_count"] == 12
    assert recommendation["source"] == "learner_state_weak_node"
