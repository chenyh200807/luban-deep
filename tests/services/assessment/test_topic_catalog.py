from __future__ import annotations

import pytest

from deeptutor.services.assessment.blueprint import MIN_FORM_ROTATION_COUNT, TARGET_FORM_ROTATION_COUNT
from deeptutor.services.assessment.topic_catalog import (
    REQUIRED_TOPIC_TESTSET_IDS,
    TopicTestSetUnavailable,
    build_topic_assessment_blueprint,
    classify_topic_form_count,
    get_topic_testset_catalog,
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
