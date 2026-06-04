"""Tests for the题目级 QuestionGradingArtifact 发布层 (runtime-readable, non-recompile).

Deterministic: reads only the golden fixture + cached typed-policy packets. No
live provider key, no DB, no RAG authority.
"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading import question_grading_artifacts as qga

VERSION_ID = "qga_v0_20260604"


def test_list_case_ids_covers_twenty_golden_cases():
    case_ids = qga.list_case_ids()
    assert len(case_ids) == 20
    assert "Q1-NA" in case_ids
    assert len(set(case_ids)) == len(case_ids)  # no duplicates


def test_list_question_grading_artifacts_alias():
    # alias must return the same set of readable case ids
    assert qga.list_question_grading_artifacts() == qga.list_case_ids()


def test_build_known_case_returns_artifact_shape():
    art = qga.build_question_grading_artifact("Q1-NA")
    assert art["question_id"] == "Q1-NA"
    assert art["version_id"] == VERSION_ID
    assert art["stem"]  # non-empty stem
    assert art["official_answer"]  # non-empty official answer
    assert isinstance(art["scoring_points"], list)
    assert art["scoring_points"], "Q1-NA must have at least one scoring point"
    # never auto-certify on an artifact-missing path
    assert "artifact_missing" not in art


def test_unknown_case_id_returns_artifact_missing():
    art = qga.build_question_grading_artifact("DOES-NOT-EXIST")
    assert art == {"artifact_missing": True, "case_id": "DOES-NOT-EXIST"}


def test_all_twenty_cases_build_without_error():
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        assert "artifact_missing" not in art, f"{cid} should be readable"
        assert art["question_id"] == cid
        assert art["scoring_points"], f"{cid} has no scoring points"


def test_every_scoring_point_has_policy_type_and_max_score():
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            assert sp.get("policy_type"), f"{cid}/{sp.get('point_id')} missing policy_type"
            assert sp.get("max_score") is not None, f"{cid}/{sp.get('point_id')} missing max_score"
            assert "point_id" in sp


def test_source_refs_come_from_real_fields_only():
    # Q1-NA P1 has a textbook evidence chunk + textbook_quote -> real source_ref
    art = qga.build_question_grading_artifact("Q1-NA")
    p1 = next(sp for sp in art["scoring_points"] if sp["point_id"] == "P1")
    assert p1["source_status"] == "ok"
    assert p1["auto_certifiable"] is True
    assert p1["source_refs"], "Q1-NA P1 should have at least one source_ref"
    # every source_ref must carry a real quote / chunk, never a fabricated anchor
    for ref in p1["source_refs"]:
        assert ref["source_type"]
        assert ref.get("quote") or ref.get("chunk_id")


def test_missing_or_weak_source_is_not_auto_certifiable():
    # Q17-1A433000 P1 is a high_risk_review point with empty evidence -> weak source
    art = qga.build_question_grading_artifact("Q17-1A433000")
    p1 = next(sp for sp in art["scoring_points"] if sp["point_id"] == "P1")
    assert p1["source_status"] == "missing_or_weak"
    assert p1["auto_certifiable"] is False
    # weak source must not fabricate a textbook anchor
    for ref in p1["source_refs"]:
        assert ref["source_type"] != "textbook"


def test_policy_type_fallback_never_fabricates_textbook():
    # If a point lacked a typed policy, fallback marks semantic_allowed and weak source,
    # but never invents a textbook chunk. Verify the invariant across all points.
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            if sp["source_status"] == "missing_or_weak":
                assert sp["auto_certifiable"] is False
                for ref in sp["source_refs"]:
                    assert ref["source_type"] != "textbook"


def test_calculation_point_carries_calculation_spec():
    # Q20-1A413000 P1 is a calculation point with a numeric_spec
    art = qga.build_question_grading_artifact("Q20-1A413000")
    p1 = next(sp for sp in art["scoring_points"] if sp["point_id"] == "P1")
    assert p1["policy_type"] == "calculation"
    assert p1["calculation_spec"] is not None
