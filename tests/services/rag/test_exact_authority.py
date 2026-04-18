from __future__ import annotations

from deeptutor.services.rag.exact_authority import (
    extract_exact_question_authority_from_metadata,
    resolve_exact_authority_response_from_authority,
    should_force_exact_authority,
)


def test_extract_exact_question_authority_normalizes_case_bundle() -> None:
    authority = extract_exact_question_authority_from_metadata(
        {
            "exact_question": {
                "answer_kind": "case_study",
                "case_bundle": {
                    "covered_subquestions": [
                        {
                            "display_index": "1",
                            "prompt": "Q1",
                            "authoritative_answer": "A1",
                        }
                    ],
                    "missing_subquestions": [],
                    "coverage_ratio": 1.0,
                    "coverage_state": "multi_subquestion_exact",
                },
            }
        }
    )

    assert authority is not None
    assert authority["authority_kind"] == "case_study"
    assert authority["covered_subquestions"][0]["authoritative_answer"] == "A1"
    assert authority["coverage_state"] == "multi_subquestion_exact"


def test_should_force_exact_authority_requires_full_case_coverage() -> None:
    assert should_force_exact_authority(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
            "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}],
            "coverage_ratio": 0.5,
            "coverage_state": "single_subquestion_only",
        }
    ) is False
    assert should_force_exact_authority(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
            "missing_subquestions": [],
            "coverage_ratio": 1.0,
            "coverage_state": "multi_subquestion_exact",
        }
    ) is True


def test_resolve_exact_authority_response_returns_full_case_only() -> None:
    assert (
        resolve_exact_authority_response_from_authority(
            {
                "authority_kind": "case_study",
                "covered_subquestions": [
                    {"display_index": "1", "authoritative_answer": "A1"},
                    {"display_index": "2", "authoritative_answer": "A2"},
                ],
                "missing_subquestions": [],
                "coverage_ratio": 1.0,
            }
        )
        == "1. A1\n\n2. A2"
    )
    assert (
        resolve_exact_authority_response_from_authority(
            {
                "authority_kind": "case_study",
                "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
                "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}],
                "coverage_ratio": 0.5,
            }
        )
        is None
    )
