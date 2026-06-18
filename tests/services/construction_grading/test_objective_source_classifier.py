"""M25-G: source classifier + conflict detector — no laundering, no averaging."""
from __future__ import annotations

from deeptutor.services.construction_grading.objective_source_classifier import (
    classify_source,
    detect_conflicts,
)


def test_governed_registry_is_release_authority():
    v = classify_source({"kind": "db_table", "has_answer_key": True, "has_provenance": True,
                         "governed_registry": True})
    assert v["verdict"] == "release_authority_candidate" and v["release_authority"] is True


def test_eval_fixture_is_real_source_candidate_not_release():
    v = classify_source({"kind": "fixture", "has_answer_key": True, "has_provenance": True,
                        "is_eval_fixture": True})
    assert v["verdict"] == "real_source_candidate" and v["release_authority"] is False


def test_rag_chunk_rejected_as_authority():
    v = classify_source({"kind": "rag_chunk", "has_answer_key": True, "has_provenance": True})
    assert v["verdict"] == "rejected" and v["release_authority"] is False


def test_model_and_council_vote_rejected():
    for kind in ("model_vote", "council_vote", "runtime_output", "llm_inferred"):
        v = classify_source({"kind": kind, "has_answer_key": True, "has_provenance": True})
        assert v["release_authority"] is False and v["verdict"] == "rejected"


def test_official_answer_only_is_seed_only():
    v = classify_source({"kind": "raw", "has_answer_key": True, "official_answer_only": True})
    assert v["verdict"] == "seed_only" and v["release_authority"] is False


def test_conflict_detector_same_key_corroborates():
    r = detect_conflicts({
        "prod": [{"question_id": "q1", "answer_key": "C"}],
        "fixture": [{"question_id": "q1", "answer_key": "C"}],
    })
    assert r["corroborated_count"] == 1 and r["conflict_count"] == 0


def test_conflict_detector_different_key_conflicts_not_averaged():
    r = detect_conflicts({
        "prod": [{"question_id": "q1", "answer_key": "C"}],
        "fixture": [{"question_id": "q1", "answer_key": "D"}],
    })
    assert r["conflict_count"] == 1 and r["corroborated_count"] == 0
    assert r["averaged_any_key"] is False  # never averages a contested key
    assert r["conflicts"][0]["keys_by_source"] == {"prod": "C", "fixture": "D"}


def test_multi_select_order_independent_corroboration():
    r = detect_conflicts({
        "prod": [{"question_id": "q2", "answer_key": "ABD"}],
        "fixture": [{"question_id": "q2", "answer_key": "DBA"}],
    })
    assert r["corroborated_count"] == 1 and r["conflict_count"] == 0
