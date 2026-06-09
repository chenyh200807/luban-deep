from deeptutor.services.construction_grading.m35_artifact_query import (
    M35ArtifactQuery,
    retrieve_m35_scoring_context,
)


def test_retrieve_rubric_returns_typed_grounded_shape_without_raw_chunks():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "scoring_points": [
            {
                "point_id": "P1",
                "criterion": "指出需要专家论证",
                "source_refs": ["s1"],
            }
        ],
        "quality_gates": {"source_validity": 1.0},
    }

    result = retrieve_m35_scoring_context(
        M35ArtifactQuery(
            question_id="Q1-NA",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        artifact_store={"Q1-NA": artifact},
    )

    assert result["artifact_version"] == "m35_case_scoring_20260609"
    assert result["shape"] == "rubric_table"
    assert result["ground"]["source_ref_count"] == 1
    assert result["confidence"]["source_validity"] == 1.0
    assert result["budget"] == {"tier": "low"}
    assert "raw_chunks" not in result


def test_missing_artifact_fails_open_without_retrieval_loop():
    result = retrieve_m35_scoring_context(
        M35ArtifactQuery(
            question_id="missing",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        artifact_store={},
    )

    assert result == {
        "found": False,
        "question_id": "missing",
        "fail_open": True,
        "reason": "artifact_missing",
    }


def test_citation_required_without_sources_fails_open():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "scoring_points": [{"point_id": "P1", "criterion": "指出需要专家论证"}],
        "quality_gates": {"source_validity": 0.0},
    }

    result = retrieve_m35_scoring_context(
        M35ArtifactQuery(
            question_id="Q1-NA",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        artifact_store={"Q1-NA": artifact},
    )

    assert result["found"] is True
    assert result["fail_open"] is True
    assert result["reason"] == "citation_required_but_missing"


def test_request_never_returns_chunks_even_if_artifact_contains_legacy_chunks():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "raw_chunks": ["must not leak"],
        "scoring_points": [{"point_id": "P1", "criterion": "指出需要专家论证", "source_refs": ["s1"]}],
        "quality_gates": {"source_validity": 1.0},
    }

    result = retrieve_m35_scoring_context(
        M35ArtifactQuery(
            question_id="Q1-NA",
            purpose="explanation",
            shape="review_action",
            citation_required=False,
            budget_tier="medium",
        ),
        artifact_store={"Q1-NA": artifact},
    )

    assert result["found"] is True
    assert "raw_chunks" not in result
    assert result["purpose"] == "explanation"
    assert result["shape"] == "review_action"
