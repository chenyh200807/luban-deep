"""Phase -1.A.3: LLM grounding discipline.

When the LLM grader proposes a hit on a scoring point that is not in the
curated rubric, the curated rubric MUST win. The dissent is logged as a
``grader_disagreement`` audit row so we can measure the rate over time and
gate Batch A promotion at ≤ 5%.

Hard constraint from the plan: "No silent LLM rubric invention — if
grading_key.scoring_points and grading_rubric are absent, the system must
not let LLM fabricate scoring points; the scoring-point map must show the
honest empty state instead."
"""
from __future__ import annotations

from deeptutor.services.construction_grading.audit import reconcile_grader_output


def test_llm_scored_hit_outside_curated_rubric_is_flagged_and_overridden() -> None:
    """LLM may only score points that exist in the rubric_specs. Inventions
    are dropped from accepted_hits and recorded under disagreement."""
    audit = reconcile_grader_output(
        rubric_specs=[{"point_id": "fire_rating", "source": "curated_rubric"}],
        llm_output={"scoring_point_hits": [
            {"point_id": "fire_rating", "hit": True},
            {"point_id": "invented_extra_point", "hit": True},
        ]},
    )

    assert audit["accepted_hits"] == [{"point_id": "fire_rating", "hit": True}]
    assert audit["disagreement"] == [
        {"point_id": "invented_extra_point", "reason": "not_in_rubric"}
    ]


def test_grader_output_aligned_with_rubric_has_no_disagreement() -> None:
    """When every LLM hit corresponds to a rubric spec, disagreement is empty."""
    audit = reconcile_grader_output(
        rubric_specs=[
            {"point_id": "fire_rating", "source": "curated_rubric"},
            {"point_id": "closing_sequence", "source": "curated_rubric"},
        ],
        llm_output={"scoring_point_hits": [
            {"point_id": "fire_rating", "hit": True},
            {"point_id": "closing_sequence", "hit": False},
        ]},
    )

    assert audit["accepted_hits"] == [
        {"point_id": "fire_rating", "hit": True},
        {"point_id": "closing_sequence", "hit": False},
    ]
    assert audit["disagreement"] == []


def test_grader_output_without_rubric_specs_drops_all_llm_hits() -> None:
    """When no rubric is available, the LLM cannot fabricate hits. Every
    proposed hit becomes disagreement; accepted_hits is empty. UI then
    surfaces the honest rubric_pending empty state."""
    audit = reconcile_grader_output(
        rubric_specs=[],
        llm_output={"scoring_point_hits": [
            {"point_id": "made_up_a", "hit": True},
            {"point_id": "made_up_b", "hit": False},
        ]},
    )

    assert audit["accepted_hits"] == []
    assert audit["disagreement"] == [
        {"point_id": "made_up_a", "reason": "not_in_rubric"},
        {"point_id": "made_up_b", "reason": "not_in_rubric"},
    ]


def test_grader_output_missing_hits_array_is_safe() -> None:
    """Defensive: missing or malformed llm_output should not crash."""
    audit = reconcile_grader_output(
        rubric_specs=[{"point_id": "fire_rating", "source": "curated_rubric"}],
        llm_output={},
    )

    assert audit["accepted_hits"] == []
    assert audit["disagreement"] == []


def test_grader_output_dedupes_by_point_id_keeping_first_hit() -> None:
    """If the LLM emits two hits for the same point_id, the first wins (it
    is the explicit grader decision; subsequent duplicates are silently
    de-duplicated to keep the accepted_hits stream stable)."""
    audit = reconcile_grader_output(
        rubric_specs=[{"point_id": "fire_rating", "source": "curated_rubric"}],
        llm_output={"scoring_point_hits": [
            {"point_id": "fire_rating", "hit": True},
            {"point_id": "fire_rating", "hit": False},
        ]},
    )

    assert audit["accepted_hits"] == [{"point_id": "fire_rating", "hit": True}]
    assert audit["disagreement"] == []
