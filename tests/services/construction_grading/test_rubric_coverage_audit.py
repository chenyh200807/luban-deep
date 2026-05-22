"""Phase -1.A: rubric coverage classification.

The plan promises a scoring-point map UI, but only items whose case_kernel
rubric authority resolves to ``grading_key`` or ``curated_rubric`` are
map-eligible. Projected / open_skill items must surface as ``rubric_pending``
empty state instead. This test pins the classifier behavior so the Batch C
UI gate has a stable signal to read.

The classifier is read-only: it inspects ``questions_bank`` rows but never
mutates ``grading_rubric`` or any other Supabase column.
"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.audit import classify_rubric_coverage


def test_rubric_coverage_classifies_each_attempt_by_authority_tier() -> None:
    """Three-bucket classification matching case_kernel's 4-tier authority:

    - grading_key      → grading_key.scoring_points populated
    - curated_rubric   → questions_bank.grading_rubric populated
    - projected_or_open → neither populated (legacy keyword/structured_rules
                         projection or open_skill fallback handles them)
    """
    audit = classify_rubric_coverage(rows=[
        {"question_id": "q1", "grading_key": {"scoring_points": [{"point_id": "p1"}]}},
        {"question_id": "q2", "grading_rubric": [{"point_id": "p2"}]},
        {"question_id": "q3"},
    ])

    assert audit["coverage_counts"] == {
        "grading_key": 1,
        "curated_rubric": 1,
        "projected_or_open": 1,
    }
    assert audit["map_eligible_ratio"] == 2 / 3


def test_rubric_coverage_grading_key_wins_over_curated_when_both_present() -> None:
    """When both ``grading_key`` and ``grading_rubric`` exist, the row counts
    under ``grading_key`` (the highest authority tier per case_kernel)."""
    audit = classify_rubric_coverage(rows=[
        {
            "question_id": "q_both",
            "grading_key": {"scoring_points": [{"point_id": "p1"}]},
            "grading_rubric": [{"point_id": "p1"}],
        }
    ])

    assert audit["coverage_counts"]["grading_key"] == 1
    assert audit["coverage_counts"]["curated_rubric"] == 0
    assert audit["coverage_counts"]["projected_or_open"] == 0
    assert audit["map_eligible_ratio"] == 1.0


def test_rubric_coverage_treats_empty_containers_as_projected_or_open() -> None:
    """Empty ``grading_key.scoring_points`` or empty ``grading_rubric``
    arrays are not map-eligible — they degrade to projected_or_open."""
    audit = classify_rubric_coverage(rows=[
        {"question_id": "q1", "grading_key": {"scoring_points": []}},
        {"question_id": "q2", "grading_rubric": []},
        {"question_id": "q3", "grading_key": {}},
        {"question_id": "q4", "grading_rubric": None},
    ])

    assert audit["coverage_counts"] == {
        "grading_key": 0,
        "curated_rubric": 0,
        "projected_or_open": 4,
    }
    assert audit["map_eligible_ratio"] == 0.0


def test_rubric_coverage_empty_rows_returns_zero_ratio_without_zero_division() -> None:
    """Empty input must not raise; ratio defaults to 0.0 with empty counts."""
    audit = classify_rubric_coverage(rows=[])

    assert audit["coverage_counts"] == {
        "grading_key": 0,
        "curated_rubric": 0,
        "projected_or_open": 0,
    }
    assert audit["map_eligible_ratio"] == 0.0


def test_rubric_coverage_classifier_is_read_only() -> None:
    """The classifier MUST NOT mutate the input rows (no write-back into
    ``grading_rubric``). Phase -1.A.1 hard constraint: rubric normalizer is
    read-only.
    """
    original = {"question_id": "q1", "grading_key": {"scoring_points": [{"point_id": "p1"}]}}
    snapshot = {**original, "grading_key": {**original["grading_key"], "scoring_points": list(original["grading_key"]["scoring_points"])}}

    classify_rubric_coverage(rows=[original])

    assert original == snapshot, "classifier must not mutate input rows"
