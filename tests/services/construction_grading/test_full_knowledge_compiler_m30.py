from __future__ import annotations

import json

from deeptutor.services.construction_grading import full_knowledge_compiler as fkc


def test_objective_full_sign_and_conflict_not_silent() -> None:
    rows = [
        {"question_id": "Q1", "question_type": "single_choice",
         "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}],
         "official_answer": "C", "content_hash": "h1", "based_on_version": 3, "source_meta": {"y": 2023}},
        {"question_id": "Q2", "question_type": "multi_choice",
         "options": [{"key": "A", "value": "a"}, {"key": "B", "value": "b"}, {"key": "C", "value": "c"}],
         "official_answer": "ABC", "content_hash": "h2", "based_on_version": 3, "source_meta": {}},
        {"question_id": "Q3", "question_type": "single_choice",
         "options": [{"key": "A", "value": "a"}], "official_answer": "Z", "content_hash": "h3"},  # bad
    ]
    out = fkc.compile_full_objective_release_candidate(rows)
    m = out["manifest"]
    assert m["status"] == "release_candidate"
    assert m["published"] is False
    assert m["count"] == 2
    assert m["official_answer_as_source"] == 0
    assert m["answer_key_override"] == 0
    keys = {r["question_id"]: r["answer_key"] for r in out["records"]}
    assert keys["Q1"] == "C"
    assert keys["Q2"] == "ABC"
    for r in out["records"]:
        assert r["official_answer_role"] == "seed_corroboration_only_not_authority"
        assert r["based_on_version"] is not None or r["based_on_version"] is None
    assert fkc.verify_lane_bundle(out, "objective_answer_key_full") is True


def test_objective_tamper_fails_closed() -> None:
    rows = [{"question_id": "Q1", "question_type": "single_choice",
             "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}], "official_answer": "C"}]
    out = fkc.compile_full_objective_release_candidate(rows)
    assert fkc.verify_lane_bundle(out, "objective_answer_key_full") is True
    out["records"][0]["answer_key"] = "A"  # tamper
    assert fkc.verify_lane_bundle(out, "objective_answer_key_full") is False


def test_objective_conflict_queued_not_fixed() -> None:
    rows = [
        {"question_id": "Q1", "question_type": "single_choice", "stem": "same stem",
         "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}], "official_answer": "C"},
        {"question_id": "Q2", "question_type": "single_choice", "stem": "same stem",
         "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}], "official_answer": "A"},
    ]
    out = fkc.compile_full_objective_release_candidate(rows)
    assert out["manifest"]["conflict_count"] == 1
    assert out["conflicts"][0]["reason"] == "duplicate_stem_different_key"


def test_source_context_never_answer_key() -> None:
    chunks = [
        {"chunk_id": "CET_1A_P1", "doc_id": "d1", "doc_type": "textbook",
         "loc": {"page": 2, "chapter": "建筑构造", "section": "建筑物构成"}, "content": "结构体系..."},
    ]
    out = fkc.compile_source_context_release_candidate(chunks)
    assert out["manifest"]["status"] == "release_candidate"
    assert out["manifest"]["rag_chunk_as_answer_key"] == 0
    ref = out["records"][0]
    assert ref["is_answer_key"] is False
    assert ref["source_table"] == "kb_v5.chunks"
    assert ref["role"] == "retrieval_context_only"


def test_case_rubric_partition_external_to_work_order_calc_validator() -> None:
    points = [
        {"point_id": "p1", "authority_kind": "textbook", "text": "教材点", "required_terms": ["a"]},
        {"point_id": "p2", "authority_kind": "external", "text": "外部规范"},
        {"point_id": "p3", "authority_kind": "review_only", "text": "判断句"},
        {"point_id": "p4", "authority_kind": "calc", "text": "计算点"},  # no spec -> validator fail
        {"point_id": "p5", "authority_kind": "calc", "text": "计算点", "machine_spec": {"formula": "x"}},
        {"point_id": "p6", "authority_kind": "list_full", "text": "列举", "list_items": ["a", "b"]},
        {"point_id": "p7", "authority_kind": "drop", "text": "丢弃"},
    ]
    out = fkc.compile_case_rubric_release_candidate(points)
    m = out["manifest"]
    signed_ids = {r["point_id"] for r in out["records"]}
    wo_ids = {w["point_id"] for w in out["work_order"]}
    assert "p1" in signed_ids and "p5" in signed_ids and "p6" in signed_ids
    assert "p2" in wo_ids and "p3" in wo_ids  # external/review_only -> work_order
    assert "p4" in wo_ids  # calc validator failed -> work_order
    assert m["external_or_reviewonly_auto_signed"] == 0
    assert m["list_partial_auto"] == 0
    assert m["dropped_count"] == 1
    for r in out["records"]:
        assert r["list_partial_auto"] is False


def test_m20_absorb_laundering_to_work_order() -> None:
    deltas = [
        {"delta_id": "d1", "kind": "rubric_delta", "origin": "textbook", "source_backed": True},
        {"delta_id": "d2", "kind": "answer_key_candidate", "origin": "model_vote"},  # laundering
        {"delta_id": "d3", "kind": "validator_rule_review", "origin": "review"},
        {"delta_id": "d4", "kind": "machine_spec_fix", "origin": "external", "machine_checkable": True},
    ]
    out = fkc.absorb_m20_deltas(deltas)
    assert out["status"] == "release_candidate"
    assert out["candidate_used_as_release_truth"] == 0
    rc_ids = {e["delta_id"] for e in out["release_candidate"]}
    wo_ids = {e["delta_id"] for e in out["work_order"]}
    assert "d1" in rc_ids
    assert "d2" in wo_ids  # model_vote not source-backed -> work_order
    assert "d3" in wo_ids
    assert all(e["promote_to_release"] is False for e in out["release_candidate"])


def test_unified_manifest_release_candidate_not_published() -> None:
    obj = fkc.compile_full_objective_release_candidate(
        [{"question_id": "Q1", "question_type": "single_choice",
          "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}], "official_answer": "C"}])
    src = fkc.compile_source_context_release_candidate(
        [{"chunk_id": "c1", "doc_type": "textbook", "loc": {}, "content": "x"}])
    case = fkc.compile_case_rubric_release_candidate(
        [{"point_id": "p1", "authority_kind": "textbook", "text": "t"}])
    m20 = fkc.absorb_m20_deltas([{"delta_id": "d1", "kind": "rubric_delta", "origin": "textbook", "source_backed": True}])
    manifest = fkc.build_compiled_knowledge_registry_manifest(
        objective=obj, source=src, case_rubric=case, m20=m20)
    assert manifest["status"] == "release_candidate"
    assert manifest["published"] is False
    assert manifest["production_default_connected"] is False
    assert manifest["canonical_truth_written"] is False
    assert manifest["rollback_pointer"]
    assert "question_context" in manifest["blocks_for_runtime_packet"]
    json.dumps(manifest, ensure_ascii=False)
