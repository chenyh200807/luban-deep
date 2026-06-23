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
    assert "canonical_write_allowed_record_present" in result["blockers"]


def test_retrieve_rubric_caches_validated_supply_until_files_change(tmp_path, monkeypatch):
    from deeptutor.services.construction_grading import m35_artifact_query

    record = {
        "qid": "Q-CACHE",
        "point_id": "p1",
        "text": "safe point",
        "official_slice": "hidden answer",
        "official_score_allowed": False,
        "canonical_write_allowed": False,
    }
    supply_dir = _write_runtime_supply(tmp_path, records=[record])

    calls = {"n": 0}
    real_loader = m35_artifact_query._load_pgo_supply

    def counting_loader(slot_dir):
        calls["n"] += 1
        return real_loader(slot_dir)

    monkeypatch.setattr(m35_artifact_query, "_load_pgo_supply", counting_loader)

    query = M35ArtifactQuery(
        question_id="Q-CACHE",
        purpose="grading",
        shape="rubric_table",
        citation_required=True,
        budget_tier="low",
    )

    first = retrieve_rubric(query, runtime_supply_dir=supply_dir)
    second = retrieve_rubric(query, runtime_supply_dir=supply_dir)

    assert first["found"] is True
    assert second["found"] is True
    assert first["scoring_points"] == second["scoring_points"]
    # Second call is served from cache: no re-read / re-hash / re-scan.
    assert calls["n"] == 1

    # Rewriting the bank (content + size change) must invalidate the cache.
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[record, {**record, "qid": "Q-CACHE-2", "point_id": "p2"}],
    )
    third = retrieve_rubric(query, runtime_supply_dir=supply_dir)
    assert third["found"] is True
    assert calls["n"] == 2


def test_retrieve_rubric_scoring_shape_fails_open_when_no_score_bearing_ground(tmp_path):
    # C3 ground gate: a scoring shape (grading/rubric_table) must refuse to grade
    # when no point carries score-bearing ground (official answer slice), even if
    # the caller did not set citation_required. The grade must never fall back to
    # ungrounded points.
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[
            {
                "qid": "Q-UNSOURCED",
                "point_id": "p1",
                "text": "claim without any authority",
                "official_slice": "",
                "term_authority": "none",
                "required_terms": [],
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            }
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-UNSOURCED",
            purpose="grading",
            shape="rubric_table",
            citation_required=False,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is True
    assert result["fail_open"] is True
    assert result["reason"] == "scoring_shape_without_score_bearing_ground"


def test_retrieve_rubric_supporting_only_ground_is_not_score_bearing(tmp_path):
    # Textbook supporting provenance alone is NOT score-bearing ground: a scoring
    # shape with only supporting refs still fails open (supporting refs never enter
    # the correct/incorrect channel — single-authority red line).
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[
            {
                "qid": "Q-SUPPORT",
                "point_id": "p1",
                "text": "textbook-backed only",
                "official_slice": "",
                "term_authority": "textbook:GB50300",
                "required_terms": ["验收"],
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            }
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-SUPPORT",
            purpose="grading",
            shape="rubric_table",
            citation_required=False,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is True
    assert result["fail_open"] is True
    assert result["reason"] == "scoring_shape_without_score_bearing_ground"


def test_retrieve_rubric_classifies_point_ground_and_marks_unscorable(tmp_path):
    # Mixed bag: one score-bearing + one supporting-only + one unsourced. The query
    # passes (there IS score-bearing ground), exposes per-point ground_class +
    # scorable, and reports the layered ground counts so consumers never grade on
    # supporting/unsourced points.
    supply_dir = _write_runtime_supply(
        tmp_path,
        records=[
            {
                "qid": "Q-MIX",
                "point_id": "p_ok",
                "text": "official point",
                "official_slice": "官方答案要点",
                "term_authority": "none",
                "required_terms": [],
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            },
            {
                "qid": "Q-MIX",
                "point_id": "p_support",
                "text": "textbook-backed only",
                "official_slice": "",
                "term_authority": "textbook:GB50300",
                "required_terms": ["验收"],
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            },
            {
                "qid": "Q-MIX",
                "point_id": "p_unsourced",
                "text": "no authority",
                "official_slice": "",
                "term_authority": "none",
                "required_terms": [],
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            },
        ],
    )

    result = retrieve_rubric(
        M35ArtifactQuery(
            question_id="Q-MIX",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        runtime_supply_dir=supply_dir,
    )

    assert result["found"] is True
    assert result.get("fail_open") is not True
    ground = result["ground"]
    assert ground["score_bearing_count"] == 1
    assert ground["supporting_count"] == 1
    assert ground["unsourced_count"] == 1
    assert ground["source_ref_count"] == 1  # back-compat: now means score-bearing

    points = {p["point_id"]: p for p in result["scoring_points"]}
    assert points["p_ok"]["ground_class"] == "score_bearing"
    assert points["p_ok"]["scorable"] is True
    assert points["p_support"]["ground_class"] == "supporting_only"
    assert points["p_support"]["scorable"] is False
    assert points["p_unsourced"]["ground_class"] == "unsourced"
    assert points["p_unsourced"]["scorable"] is False


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
