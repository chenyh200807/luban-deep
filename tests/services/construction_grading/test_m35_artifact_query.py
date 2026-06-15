import json

from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
from deeptutor.services.construction_grading.m35_artifact_query import (
    M35ArtifactQuery,
    retrieve_rubric,
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


def test_query_reads_legacy_source_refs_verified_rate_as_validity():
    artifact = {
        "artifact_version": "qga_v0_20260604",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "scoring_points": [
            {"point_id": "P1", "criterion": "指出需要专家论证", "source_refs": ["s1"]}
        ],
        "quality_gates": {"source_refs_verified_rate": 1.0},
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
    assert result["confidence"]["source_validity"] == 1.0


def test_retrieve_rubric_reads_hash_pinned_pgo_runtime_supply():
    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="2015::EXAM_XW2015_CASE_1::E0",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        )
    )

    assert result["found"] is True
    assert result["artifact_version"] == "case_rubric_scored_pgo"
    assert result["shape"] == "rubric_table"
    assert result["ground"]["source_ref_count"] > 0
    assert result["confidence"]["verdict_ceiling"] == "release_candidate_review_only"
    assert result["budget"] == {"tier": "low", "runtime": "deterministic_pgo_supply"}
    assert result["scoring_points"]
    assert all(point["official_score_allowed"] is False for point in result["scoring_points"])
    assert all(point["canonical_write_allowed"] is False for point in result["scoring_points"])
    assert all(point["authority_source"] == "official_answer_verbatim" for point in result["scoring_points"])
    assert all(point["span_hash"] for point in result["scoring_points"])
    assert "raw_chunks" not in result


def test_retrieve_rubric_explanation_projection_hides_teacher_only_fields():
    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="2015::EXAM_XW2015_CASE_1::E0",
            purpose="explanation",
            shape="review_action",
            citation_required=True,
            budget_tier="low",
        )
    )

    assert result["found"] is True
    assert result["purpose"] == "explanation"
    assert result["shape"] == "review_action"
    assert result["scoring_points"]
    hidden_blob = str(result["scoring_points"])
    assert "official_slice" not in hidden_blob
    assert "official_total_score" not in hidden_blob
    assert "answer_key_authority" not in hidden_blob
    assert "score_authority" not in hidden_blob


def test_retrieve_rubric_fail_opens_when_pgo_supply_question_missing():
    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="missing-qid",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        )
    )

    assert result == {
        "found": False,
        "question_id": "missing-qid",
        "fail_open": True,
        "reason": "artifact_missing",
    }


def _write_runtime_supply(tmp_path, *, manifest_overrides=None, records=None):
    records = list(records or [])
    content_hash = _sha256_hex(records)
    manifest = {
        "namespace": "case_rubric_scored_pgo",
        "content_hash": content_hash,
        "published": False,
        "production_default": "off",
        "source_schemas": ["luban_per_question_grading_object.v1"],
    }
    if manifest_overrides:
        for key, value in manifest_overrides.items():
            if value is None:
                manifest.pop(key, None)
            else:
                manifest[key] = value
    (tmp_path / "case_rubric_scored_pgo.json").write_text(
        json.dumps({"manifest": manifest, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "canonical_pointer.json").write_text(
        json.dumps({"expected_content_hash": content_hash}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def test_retrieve_rubric_blocks_supply_records_that_allow_official_or_canonical_write(tmp_path):
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[
            {
                "qid": "Q-WRITE",
                "point_id": "p1",
                "text": "unsafe point",
                "official_slice": "hidden answer",
                "official_score_allowed": True,
                "canonical_write_allowed": True,
            }
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-WRITE",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is False
    assert result["fail_open"] is True
    assert result["reason"] == "runtime_supply_unavailable"
    assert "official_score_allowed_record_present" in result["blockers"]


def test_retrieve_rubric_blocks_supply_records_without_score_ground(tmp_path):
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[
            {
                "qid": "Q-NOGROUND",
                "point_id": "p1",
                "text": "unsafe point",
                "official_slice": "hidden answer",
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            }
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-NOGROUND",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is False
    assert result["fail_open"] is True
    assert result["reason"] == "runtime_supply_unavailable"
    assert "record_missing_authority_source:Q-NOGROUND:p1" in result["blockers"]
    assert "record_missing_span_hash:Q-NOGROUND:p1" in result["blockers"]


def test_retrieve_rubric_fail_opens_when_runtime_supply_manifest_missing_namespace(tmp_path):
    supply_dir = _write_runtime_supply(
        tmp_path,
        manifest_overrides={"namespace": None},
        records=[
            {
                "qid": "Q-MANIFEST",
                "point_id": "p1",
                "text": "safe point",
                "official_slice": "hidden answer",
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            }
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-MANIFEST",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is False
    assert result["fail_open"] is True
    assert result["reason"] == "runtime_supply_unavailable"
    assert "namespace_missing" in result["blockers"]
