from __future__ import annotations

import inspect

from deeptutor.services.assessment.pass_readiness_scoring import (
    BAND_POLICY_VERSION,
    BAND_WIDTH_LADDER,
    EVIDENCE_INSUFFICIENT_COPY,
    PASS_LINE,
    AbilityEvidence,
    DimensionEvidence,
    PrepContext,
    build_pass_readiness_result,
    derive_ability_readiness,
    derive_score_band,
)


NOW = "2026-08-05T12:00:00Z"


def _default_evidence(
    *,
    expression: DimensionEvidence | None = None,
    self_reported_score: int | None = None,
) -> AbilityEvidence:
    return AbilityEvidence(
        core_knowledge=DimensionEvidence(correct=3, observations=4),
        construction_logic=DimensionEvidence(correct=2, observations=3),
        case_scoring_point_recognition=DimensionEvidence(correct=2, observations=4),
        answer_expression=expression,
        self_reported_score=self_reported_score,
    )


def _result(evidence: AbilityEvidence, prep: PrepContext, *, scored: int = 12, answered: int = 12) -> dict:
    return build_pass_readiness_result(
        evidence,
        prep,
        scored_task_count=scored,
        answered_count=answered,
        form_version="pass_readiness_form_1",
        item_pool_version="pool_v1",
        now_iso=NOW,
    )


def test_same_input_produces_same_band_and_payload() -> None:
    evidence = _default_evidence()
    prep = PrepContext(weekly_hours_band="10_20", remaining_weeks=12)

    first = _result(evidence, prep)
    second = _result(evidence, prep)

    assert first == second
    assert first["band_status"] == "ok"
    assert first["generated_at"] == NOW


def test_band_width_meets_ladder_minimum_and_endpoints_are_multiples_of_five() -> None:
    cases = [
        (_default_evidence(), 12, 12, "v1_default"),
        (_default_evidence(), 6, 6, "coarse_checkpoint"),
        (
            _default_evidence(
                expression=DimensionEvidence(correct=2, observations=3),
                self_reported_score=88,
            ),
            12,
            12,
            "full_evidence",
        ),
    ]
    for evidence, scored, answered, expected_tier in cases:
        band = derive_score_band(evidence, scored_task_count=scored, answered_count=answered)
        assert band["status"] == "ok"
        assert band["tier"] == expected_tier
        assert band["width"] >= BAND_WIDTH_LADDER[expected_tier]
        assert band["lower"] % 5 == 0
        assert band["upper"] % 5 == 0
        assert band["upper"] > band["lower"]  # never a single point


def test_coarse_checkpoint_is_extra_wide_low_coverage_and_suppresses_interval() -> None:
    result = _result(_default_evidence(), PrepContext(), scored=6, answered=6)

    assert result["band_tier"] == "coarse_checkpoint"
    assert result["band_width"] >= 30
    assert result["evidence_coverage"] == "low"
    assert result["reference_pass_interval"] == ""


def test_expression_unmeasured_never_reaches_the_narrow_tier() -> None:
    # Even with self-reported history and zero skips, no expression evidence
    # keeps the band on the wide ladder step (>=20).
    evidence = _default_evidence(expression=None, self_reported_score=88)

    band = derive_score_band(evidence, scored_task_count=12, answered_count=12)

    assert band["tier"] == "v1_default"
    assert band["width"] >= BAND_WIDTH_LADDER["v1_default"]


def test_feasibility_change_cannot_move_the_band() -> None:
    evidence = _default_evidence()
    tight = _result(evidence, PrepContext(weekly_hours_band="lt_5", remaining_weeks=4))
    ample = _result(evidence, PrepContext(weekly_hours_band="gt_20", remaining_weeks=30))

    assert tight["estimated_score_band"] == ample["estimated_score_band"]
    assert tight["band_lower"] == ample["band_lower"]
    assert tight["band_upper"] == ample["band_upper"]
    assert tight["ability_readiness"] == ample["ability_readiness"]
    assert tight["prep_feasibility"] != ample["prep_feasibility"]


def test_band_function_signature_structurally_excludes_flow_variables() -> None:
    params = set(inspect.signature(derive_score_band).parameters)
    assert params == {"evidence", "scored_task_count", "answered_count"}
    field_names = set(AbilityEvidence.__dataclass_fields__)
    forbidden_fragments = ("hour", "time", "week", "feasib", "prep")
    for name in field_names:
        assert not any(fragment in name.lower() for fragment in forbidden_fragments), name


def test_low_completion_returns_evidence_insufficient_not_a_band() -> None:
    result = _result(_default_evidence(), PrepContext(), scored=12, answered=5)

    assert result["band_status"] == "evidence_insufficient"
    assert result["estimated_score_band"] is None
    assert result["band_copy"] == EVIDENCE_INSUFFICIENT_COPY
    assert result["risk_band"] == "证据不足"
    assert result["reference_pass_interval"] == ""


def test_thin_dimension_gets_signal_sentence_not_numeric_score_and_widens_band() -> None:
    evidence = AbilityEvidence(
        core_knowledge=DimensionEvidence(correct=3, observations=4),
        construction_logic=DimensionEvidence(correct=1, observations=2),  # < 3 obs
        case_scoring_point_recognition=DimensionEvidence(correct=2, observations=4),
        answer_expression=DimensionEvidence(correct=1, observations=1),
    )

    readiness = derive_ability_readiness(evidence)
    assert readiness["dimensions"]["construction_logic"]["score_pct"] is None
    assert readiness["dimensions"]["construction_logic"]["observed_signal"]
    assert readiness["dimensions"]["answer_expression"]["annotation"] == "单次观察"

    band = derive_score_band(evidence, scored_task_count=12, answered_count=12)
    assert band["width"] > BAND_WIDTH_LADDER["v1_default"]


def test_unmeasured_dimension_reports_evidence_insufficient_not_average() -> None:
    readiness = derive_ability_readiness(_default_evidence(expression=None))

    report = readiness["dimensions"]["answer_expression"]
    assert report["measured"] is False
    assert report["score_pct"] is None
    assert report["observed_signal"] == "证据不足"
    assert "answer_expression" in readiness["unmeasured_dimensions"]


def test_output_carries_all_section_7_2_fields_and_versions() -> None:
    result = _result(_default_evidence(), PrepContext(weekly_hours_band="10_20", remaining_weeks=12))

    for field in (
        "estimated_score_band",
        "pass_line",
        "ability_readiness",
        "prep_feasibility",
        "risk_band",
        "evidence_coverage",
        "band_policy_version",
        "reference_pass_interval",
        "model_version",
        "form_version",
        "item_pool_version",
        "generated_at",
    ):
        assert field in result, field
    assert result["pass_line"] == PASS_LINE == 96
    assert result["band_policy_version"] == BAND_POLICY_VERSION == "band-v1"
    assert result["form_version"] == "pass_readiness_form_1"
    assert result["item_pool_version"] == "pool_v1"
    assert result["risk_band"] in {"过线风险高", "临界不稳", "过线优势明显"}
    assert result["estimated_score_band"].endswith(" 分")


def test_self_reported_history_is_labeled_unverified() -> None:
    with_history = _result(_default_evidence(self_reported_score=88), PrepContext())
    without_history = _result(_default_evidence(), PrepContext())

    assert with_history["self_reported_score_label"] == "自报未核验"
    assert without_history["self_reported_score_label"] == ""
