import pytest

from deeptutor.services.construction_grading.m35_status import (
    m35_runtime_status_from_v0,
    official_score_allowed_for_m35,
)


def test_v0_published_does_not_grant_m35_official_score():
    mapped = m35_runtime_status_from_v0(
        {"status": "published", "version_id": "qga_v0_20260604"}
    )

    assert mapped["legacy_artifact_status"] == "published"
    assert mapped["m35_runtime_status"] == "release_candidate"
    assert mapped["official_score_allowed"] is False
    assert mapped["published_registry_authority"] is False


@pytest.mark.parametrize(
    ("artifact", "legacy_status", "m35_status"),
    [
        ({"status": "published"}, "published", "release_candidate"),
        ({"status": "draft"}, "draft", "shadow_candidate"),
        ({"status": "blocked"}, "blocked", "blocked"),
        ({"status": "unknown"}, "unknown", "blocked"),
        ({}, "", "blocked"),
    ],
)
def test_v0_status_mapping_matrix_never_grants_official_authority(
    artifact, legacy_status, m35_status
):
    mapped = m35_runtime_status_from_v0(artifact)

    assert mapped["legacy_artifact_status"] == legacy_status
    assert mapped["m35_runtime_status"] == m35_status
    assert mapped["official_score_allowed"] is False
    assert mapped["published_registry_authority"] is False


def test_client_supplied_release_status_is_ignored():
    mapped = official_score_allowed_for_m35(
        server_governed_registry_status="",
        client_supplied_status="published",
        artifact_status="release_candidate",
    )

    assert mapped is False


def test_artifact_status_published_is_not_registry_authority():
    mapped = official_score_allowed_for_m35(
        server_governed_registry_status="",
        client_supplied_status="draft",
        artifact_status="published",
    )

    assert mapped is False


def test_only_server_governed_published_registry_can_allow_official_score():
    mapped = official_score_allowed_for_m35(
        server_governed_registry_status="published",
        client_supplied_status="draft",
        artifact_status="release_candidate",
    )

    assert mapped is True
