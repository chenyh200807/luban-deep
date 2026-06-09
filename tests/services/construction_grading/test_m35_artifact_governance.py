from deeptutor.services.construction_grading.m35_artifact_governance import (
    evaluate_m35_artifact_governance,
)


def test_release_candidate_requires_owner_and_review_authority():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "lifecycle_status": "release_candidate",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is False
    assert report["blocking_reasons"] == [
        "missing_owner_role",
        "missing_review_authority",
        "missing_supersede_policy",
        "missing_rollback_policy",
    ]


def test_shadow_candidate_with_owner_and_review_path_is_consumable_for_shadow_only():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "shadow_candidate",
        "lifecycle_status": "shadow_candidate",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "po_directional_single_reviewer",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is True
    assert report["official_score_allowed"] is False
    assert report["blocking_reasons"] == []


def test_controlled_default_lifecycle_is_valid_but_does_not_grant_official_score():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "lifecycle_status": "controlled_default",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "teacher_validated",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is True
    assert report["official_score_allowed"] is False
    assert "invalid_lifecycle_status" not in report["blocking_reasons"]


def test_runtime_consumable_requires_artifact_version_source_refs_and_quality_gates():
    artifact = {
        "question_id": "Q1-NA",
        "status": "shadow_candidate",
        "lifecycle_status": "shadow_candidate",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "teacher_validated",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [],
        "quality_gates": {},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is False
    assert "missing_artifact_version" in report["blocking_reasons"]
    assert "missing_source_refs" in report["blocking_reasons"]
    assert "score_sum_not_verified" in report["blocking_reasons"]
    assert "source_validity_below_gate" in report["blocking_reasons"]


def test_blocked_artifact_is_not_runtime_consumable_even_when_governed():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "blocked",
        "lifecycle_status": "blocked",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "teacher_validated",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is False
    assert report["official_score_allowed"] is False
    assert report["blocking_reasons"] == []
