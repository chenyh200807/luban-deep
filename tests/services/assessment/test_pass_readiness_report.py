from __future__ import annotations

from deeptutor.services.assessment.blueprint import ability_dimensions_by_section
from deeptutor.services.assessment.report_read_model import (
    build_pass_readiness_report,
    build_result_report,
)


NOW = "2026-08-05T12:00:00Z"

_SECTION_PLAN = [
    ("pr_objective_single", 2),
    ("pr_objective_multi", 2),
    ("pr_case_safety", 2),
    ("pr_case_schedule", 2),
    ("pr_case_quality", 2),
    ("pr_answer_discrimination", 1),
    ("pr_scoring_point_recognition", 1),
]


def _scored_result(*, wrong_question_ids: set[str] | None = None) -> dict:
    wrong = wrong_question_ids or set()
    items = []
    index = 0
    for section_id, count in _SECTION_PLAN:
        for _ in range(count):
            index += 1
            question_id = f"q{index:02d}"
            is_correct = question_id not in wrong
            items.append(
                {
                    "question_id": question_id,
                    "source_question_id": f"src_{question_id}",
                    "question_stem": f"题干 {question_id}",
                    "question_type": "single_choice",
                    "section_id": section_id,
                    "section_label": section_id,
                    "learner_answer": "A",
                    "correct_answer": "A" if is_correct else "B",
                    "is_correct": is_correct,
                    "is_blank": False,
                    "flags": [],
                    "knowledge_points": [f"考点 {question_id}"],
                    "simple_explanation": "解析",
                    "error_codes": [] if is_correct else ["M01"],
                    "measurement_confidence": "medium",
                }
            )
    correct_count = sum(1 for item in items if item["is_correct"])
    return {
        "score_summary": {
            "score_pct": round(correct_count / len(items) * 100),
            "correct_count": correct_count,
            "answered_count": len(items),
            "scored_count": len(items),
            "blank_count": 0,
        },
        "measurement_confidence": {"level": "high", "completion_rate": 1.0, "seconds_per_item": 30, "reasons": []},
        "items": items,
    }


def _probe_questions() -> list[dict]:
    return [
        {
            "question_id": "probe_attempt",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "attempt_history",
            "option_values": {"A": "first_attempt", "B": "retaker_passed_public_last_year"},
        },
        {
            "question_id": "probe_score",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "recent_score_band",
            "option_values": {"A": "no_prior_score", "D": "score_80_95"},
        },
        {
            "question_id": "probe_hours",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "weekly_study_hours",
            "option_values": {"A": "lt_5", "C": "10_20"},
        },
    ]


def _build(*, answers: dict[str, str], wrong: set[str] | None = None) -> dict:
    return build_pass_readiness_report(
        quiz_id="quiz_pr_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_architecture_v1_form_1",
        scored_result=_scored_result(wrong_question_ids=wrong),
        session_questions=_probe_questions(),
        answers=answers,
        writeback_refs={"writeback_status": {"status": "pending"}},
        now_iso=NOW,
    )


def test_envelope_is_pass_readiness_v1_with_full_7_2_block() -> None:
    report = _build(answers={"probe_score": "D", "probe_hours": "C", "probe_attempt": "A"})

    assert report["schema_version"] == "pass-readiness-v1"
    block = report["pass_readiness"]
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
        assert field in block, field
    assert block["pass_line"] == 96
    assert block["band_policy_version"] == "band-v1"
    assert block["form_version"] == "pass_readiness_architecture_v1_form_1"
    assert block["item_pool_version"] == "pass_readiness_architecture_v1"
    assert block["generated_at"] == NOW
    assert block["band_lower"] % 5 == 0 and block["band_upper"] % 5 == 0
    assert block["self_reported_score_label"] == "自报未核验"
    # Base p0a fields are retained for the existing rendering chain.
    assert report["score_summary"]["scored_count"] == 12
    assert len(report["items"]) == 12


def test_item_dimension_binding_yields_4_4_4_observations() -> None:
    binding = ability_dimensions_by_section("pass_readiness_architecture_v1")
    assert len(binding) == 7

    report = _build(answers={})
    dims = report["pass_readiness"]["ability_readiness_detail"]["dimensions"]

    assert dims["core_knowledge"]["observations"] == 4
    assert dims["construction_logic"]["observations"] == 4
    assert dims["case_scoring_point_recognition"]["observations"] == 4
    assert dims["answer_expression"]["measured"] is False
    assert "answer_expression" in report["pass_readiness"]["unmeasured_dimensions"]


def test_same_submission_reproduces_identical_report_with_fixed_now() -> None:
    answers = {"probe_score": "D", "probe_hours": "C", "probe_attempt": "B"}
    wrong = {"q01", "q05", "q09"}

    first = _build(answers=answers, wrong=wrong)
    second = _build(answers=answers, wrong=wrong)

    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_probe_feasibility_answers_never_move_the_band() -> None:
    tight = _build(answers={"probe_hours": "A"})
    ample = _build(answers={"probe_hours": "C"})

    assert tight["pass_readiness"]["estimated_score_band"] == ample["pass_readiness"]["estimated_score_band"]
    assert tight["pass_readiness"]["prep_feasibility"] != ample["pass_readiness"]["prep_feasibility"]


def test_p0a_builder_behavior_is_unchanged() -> None:
    report = build_result_report(
        quiz_id="quiz_topic_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        topic_label="防水专题测评",
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        scored_result=_scored_result(),
    )

    assert report["schema_version"] == "p0a-v1"
    assert "pass_readiness" not in report
