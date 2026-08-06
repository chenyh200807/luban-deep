"""带宽阶梯 v2 / pass-readiness-model-v2（§6.2-v2 + §7.1/§7.2）。

覆盖:三档查表(10 粗带≥30 / 30 客观带≥20 / 全量精带≥15)、band-v2 与
model-v2 版本位、v1 常量与行为零漂移、结构性 feasibility 隔离、报告选路。
"""

from __future__ import annotations

import inspect

from deeptutor.services.assessment.pass_readiness_scoring import (
    BAND_POLICY_VERSION,
    BAND_POLICY_VERSION_V2,
    BAND_WIDTH_LADDER,
    BAND_WIDTH_LADDER_V2,
    COARSE_CHECKPOINT_TASK_COUNT_V2,
    EVIDENCE_INSUFFICIENT_COPY,
    OBJECTIVE_BAND_TASK_COUNT_V2,
    PASS_READINESS_MODEL_VERSION,
    PASS_READINESS_MODEL_VERSION_V2,
    AbilityEvidence,
    DimensionEvidence,
    PrepContext,
    build_pass_readiness_result,
    build_pass_readiness_result_v2,
    derive_ability_readiness_v2,
    derive_score_band,
    derive_score_band_v2,
)


NOW = "2026-08-06T12:00:00Z"


def _v2_evidence(
    *,
    self_reported_score: int | None = None,
) -> AbilityEvidence:
    # v2 维度矩阵满卷形态：core≈20 / logic≈10 / case≈6，expression 未测。
    return AbilityEvidence(
        core_knowledge=DimensionEvidence(correct=14, observations=20),
        construction_logic=DimensionEvidence(correct=6, observations=10),
        case_scoring_point_recognition=DimensionEvidence(correct=3, observations=6),
        answer_expression=None,
        self_reported_score=self_reported_score,
    )


def test_v2_ladder_is_a_three_step_table_lookup() -> None:
    assert BAND_WIDTH_LADDER_V2 == {
        "coarse_checkpoint": 30,
        "objective_band": 20,
        "v2_default": 15,
    }
    assert COARSE_CHECKPOINT_TASK_COUNT_V2 == 10
    assert OBJECTIVE_BAND_TASK_COUNT_V2 == 30


def test_v2_tiers_by_checkpoint_progress() -> None:
    coarse_evidence = AbilityEvidence(
        core_knowledge=DimensionEvidence(correct=7, observations=10),
        construction_logic=DimensionEvidence(correct=0, observations=0),
        case_scoring_point_recognition=DimensionEvidence(correct=0, observations=0),
    )
    objective_evidence = AbilityEvidence(
        core_knowledge=DimensionEvidence(correct=14, observations=20),
        construction_logic=DimensionEvidence(correct=6, observations=10),
        case_scoring_point_recognition=DimensionEvidence(correct=0, observations=0),
    )
    cases = [
        (coarse_evidence, 10, "coarse_checkpoint", "low"),
        (objective_evidence, 30, "objective_band", "medium"),
        (_v2_evidence(), 36, "v2_default", "high"),
    ]
    for evidence, scored, expected_tier, expected_coverage in cases:
        band = derive_score_band_v2(
            evidence, scored_task_count=scored, answered_count=scored
        )
        assert band["status"] == "ok"
        assert band["tier"] == expected_tier
        assert band["width"] >= BAND_WIDTH_LADDER_V2[expected_tier]
        assert band["evidence_coverage"] == expected_coverage
        assert band["band_policy_version"] == "band-v2"
        assert band["lower"] % 5 == 0 and band["upper"] % 5 == 0
        assert band["upper"] > band["lower"]


def test_v2_full_form_default_width_is_narrower_than_v1_default() -> None:
    band = derive_score_band_v2(_v2_evidence(), scored_task_count=36, answered_count=36)
    assert BAND_WIDTH_LADDER_V2["v2_default"] == 15 < BAND_WIDTH_LADDER["v1_default"]
    assert band["width"] >= 15


def test_v2_skips_and_thin_dimensions_still_widen() -> None:
    full = derive_score_band_v2(_v2_evidence(), scored_task_count=36, answered_count=36)
    skipped = derive_score_band_v2(_v2_evidence(), scored_task_count=36, answered_count=30)
    assert skipped["width"] >= full["width"] + 5


def test_v2_low_completion_yields_evidence_insufficient() -> None:
    band = derive_score_band_v2(_v2_evidence(), scored_task_count=36, answered_count=10)
    assert band["status"] == "evidence_insufficient"
    assert band["copy"] == EVIDENCE_INSUFFICIENT_COPY
    assert band["band_policy_version"] == "band-v2"


def test_v2_model_and_policy_versions_are_bumped_and_v1_untouched() -> None:
    assert PASS_READINESS_MODEL_VERSION_V2 == "pass-readiness-model-v2"
    assert BAND_POLICY_VERSION_V2 == "band-v2"
    # v1 回滚锚零漂移。
    assert PASS_READINESS_MODEL_VERSION == "pass-readiness-model-v1"
    assert BAND_POLICY_VERSION == "band-v1"
    assert BAND_WIDTH_LADDER == {"coarse_checkpoint": 30, "v1_default": 20, "full_evidence": 12}
    v1_band = derive_score_band(
        AbilityEvidence(
            core_knowledge=DimensionEvidence(correct=3, observations=4),
            construction_logic=DimensionEvidence(correct=2, observations=3),
            case_scoring_point_recognition=DimensionEvidence(correct=2, observations=4),
        ),
        scored_task_count=12,
        answered_count=12,
    )
    assert v1_band["band_policy_version"] == "band-v1"
    assert v1_band["readiness"]["model_version"] == "pass-readiness-model-v1"

    readiness_v2 = derive_ability_readiness_v2(_v2_evidence())
    assert readiness_v2["model_version"] == "pass-readiness-model-v2"


def test_v2_band_signature_structurally_excludes_flow_variables() -> None:
    params = set(inspect.signature(derive_score_band_v2).parameters)
    assert params == {"evidence", "scored_task_count", "answered_count"}


def test_v2_feasibility_cannot_move_the_band() -> None:
    evidence = _v2_evidence()
    kwargs = dict(
        scored_task_count=36,
        answered_count=36,
        form_version="pass_readiness_v2_form_1",
        item_pool_version="pass_readiness_architecture_v2",
        now_iso=NOW,
    )
    tight = build_pass_readiness_result_v2(
        evidence, PrepContext(weekly_hours_band="lt_5", remaining_weeks=4), **kwargs
    )
    ample = build_pass_readiness_result_v2(
        evidence, PrepContext(weekly_hours_band="gt_20", remaining_weeks=30), **kwargs
    )
    assert tight["estimated_score_band"] == ample["estimated_score_band"]
    assert tight["band_policy_version"] == "band-v2"
    assert tight["model_version"] == "pass-readiness-model-v2"
    assert tight["prep_feasibility"] != ample["prep_feasibility"]


def test_v1_result_envelope_versions_unchanged() -> None:
    result = build_pass_readiness_result(
        AbilityEvidence(
            core_knowledge=DimensionEvidence(correct=3, observations=4),
            construction_logic=DimensionEvidence(correct=2, observations=3),
            case_scoring_point_recognition=DimensionEvidence(correct=2, observations=4),
        ),
        PrepContext(weekly_hours_band="10_20"),
        scored_task_count=12,
        answered_count=12,
        form_version="f1",
        item_pool_version="pool_v1",
        now_iso=NOW,
    )
    assert result["band_policy_version"] == "band-v1"
    assert result["model_version"] == "pass-readiness-model-v1"


def test_report_builder_routes_v2_blueprint_to_band_v2() -> None:
    from deeptutor.services.assessment.report_read_model import build_pass_readiness_report

    items = []
    section_plan = [
        ("pr2_single_main_structure", 4),
        ("pr2_single_safety", 4),
        ("pr2_single_schedule", 4),
        ("pr2_single_quality", 4),
        ("pr2_single_waterproof", 4),
        ("pr2_objective_multi", 10),
        ("pr2_case_safety", 2),
        ("pr2_case_schedule", 2),
        ("pr2_case_quality", 2),
    ]
    index = 0
    for section_id, count in section_plan:
        for _ in range(count):
            index += 1
            items.append(
                {
                    "question_id": f"q{index:02d}",
                    "source_question_id": f"src{index:02d}",
                    "question_stem": f"题干{index}",
                    "section_id": section_id,
                    "learner_answer": "A",
                    "correct_answer": "A",
                    "is_correct": True,
                    "knowledge_points": [],
                    "error_codes": [],
                    "simple_explanation": "",
                }
            )
    scored_result = {
        "items": items,
        "score_summary": {"score_pct": 100, "correct_count": 36, "answered_count": 36},
        "measurement_confidence": {"level": "high"},
    }
    report = build_pass_readiness_report(
        quiz_id="quiz_v2",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v2",
        form_id="pass_readiness_architecture_v2_form_1",
        scored_result=scored_result,
        session_questions=[],
        answers={},
        now_iso=NOW,
    )
    block = report["pass_readiness"]
    assert block["band_policy_version"] == "band-v2"
    assert block["model_version"] == "pass-readiness-model-v2"
    # 维度观察数落到 v2 矩阵（20/10/6）。
    detail = block["ability_readiness_detail"]["dimensions"]
    assert detail["core_knowledge"]["observations"] == 20
    assert detail["construction_logic"]["observations"] == 10
    assert detail["case_scoring_point_recognition"]["observations"] == 6
    # 持久化信封 schema 仍是 DB CHECK 白名单里的 pass-readiness-v1。
    assert report["schema_version"] == "pass-readiness-v1"
