from __future__ import annotations

from deeptutor.services.construction_grading import (
    objective_governed_registry_extractor as ext,
)


def test_hermetic_fixture_extracts_and_signs_release_candidate() -> None:
    bundle = ext.build_release_candidate_bundle()
    assert ext.verify_bundle(bundle) is True
    m = bundle["manifest"]
    assert m["status"] == "release_candidate"
    assert m["published"] is False
    assert m["namespace"] == "objective_answer_key_governed"
    assert m["separate_from_case_registry"] is True
    assert m["separate_from_candidate_namespace"] is True
    assert m["answer_key_override"] == 0
    assert m["rag_chunk_as_answer_key"] == 0
    assert m["count"] >= 3


def test_answer_keys_are_governed_only() -> None:
    bundle = ext.build_release_candidate_bundle()
    for rec in bundle["records"]:
        assert rec["answer_key_authority"] == "governed_source_official_answer_only"
        assert rec["source_refs"][0]["kind"] == "governed_questions_bank"
    keys = {r["question_id"]: r["answer_key"] for r in bundle["records"]}
    assert keys["QB_2023_1A_001"] == "A"
    assert keys["QB_2023_1A_002"] == "ABD"  # order-independent normalized
    assert keys["QB_2024_1A_010"] == "T"  # true_false normalized


def test_tamper_fails_closed() -> None:
    bundle = ext.build_release_candidate_bundle()
    assert ext.verify_bundle(bundle) is True
    bundle["records"][0]["answer_key"] = "B"  # tamper
    assert ext.verify_bundle(bundle) is False


def test_missing_source_status_records_precise_live_blocker() -> None:
    status = ext.governed_source_status(db_url="")
    assert status["live_available"] is False
    assert "QUESTIONS_BANK_DB_URL" in status["live_blocker"]


def test_live_path_uses_injected_querier_readonly() -> None:
    def _querier(url: str):
        assert url == "postgresql://ro@host/db"
        return [
            {
                "question_id": "QB_LIVE_1",
                "question_type": "single_choice",
                "stem": "x",
                "options": {"A": "a", "B": "b"},
                "official_answer": "B",
            }
        ]

    bundle = ext.build_release_candidate_bundle(db_url="postgresql://ro@host/db", querier=_querier)
    assert ext.verify_bundle(bundle) is True
    assert bundle["manifest"]["source_kind"] == "questions_bank_live_readonly"
    assert bundle["records"][0]["answer_key"] == "B"


def test_invalid_rows_rejected_not_guessed() -> None:
    def _querier(url: str):
        return [
            {"question_id": "BAD1", "question_type": "single_choice",
             "options": {"A": "a", "B": "b"}, "official_answer": "C"},  # valid letter, not in options
            {"question_id": "BAD2", "question_type": "single_choice",
             "options": {"A": "a", "B": "b"}, "official_answer": "AB"},  # single but multi
        ]

    bundle = ext.build_release_candidate_bundle(db_url="postgresql://ro@host/db", querier=_querier)
    assert bundle["manifest"]["count"] == 0
    reasons = {r["reason"] for r in bundle["rejected"]}
    assert "answer_not_in_options" in reasons
    assert "single_choice_multi_answer" in reasons
