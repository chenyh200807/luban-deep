from __future__ import annotations

from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
)
from deeptutor.services.assessment.profile_probes import get_profile_probes


def _candidate(index: int, *, question_type: str) -> QuestionCandidate:
    return QuestionCandidate(
        source_question_id=f"pr_src_{question_type}_{index}",
        question_stem=f"过线体检候选题 {question_type} {index}，关于施工质量与安全管理的正确做法是？",
        question_type=question_type,
        chapter=f"章节 {question_type} {index}",
        options=(("A", "选项 A"), ("B", "选项 B"), ("C", "选项 C"), ("D", "选项 D")),
        answer="A" if question_type == "single_choice" else "AB",
        difficulty=("easy", "medium", "hard")[index % 3],
        source_type="REAL_EXAM",
        source_meta={"semantic_signature": f"pr_sig_{question_type}_{index}"},
    )


def _pass_readiness_service() -> AssessmentBlueprintService:
    candidates = [_candidate(index, question_type="single_choice") for index in range(40)]
    candidates += [_candidate(index, question_type="multi_choice") for index in range(40)]
    return AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("pass_readiness_architecture_v1"),
        provider=StaticAssessmentQuestionProvider(candidates),
        allow_dev_fallback=False,
    )


def test_registry_has_legacy_and_prep_context_probes_with_unique_ids() -> None:
    probes = get_profile_probes()

    assert len(probes) == 7
    assert len({probe.id for probe in probes}) == 7
    prep = [probe for probe in probes if probe.section_id == "pr_prep_context"]
    assert [probe.topic for probe in prep] == [
        "attempt_history",
        "recent_score_band",
        "weekly_study_hours",
    ]
    # Option wire format stays letter-tap: letters only, tags non-empty.
    for probe in prep:
        for letter, text, tag in probe.options:
            assert len(letter) == 1 and letter.isalpha() and letter.isupper()
            assert text
            assert tag


def test_attempt_history_probe_carries_passed_subject_and_expiry_context() -> None:
    probes = {probe.topic: probe for probe in get_profile_probes() if probe.section_id == "pr_prep_context"}

    tags = {tag for _letter, _text, tag in probes["attempt_history"].options}
    assert "first_attempt" in tags
    assert "retaker_passes_expiring_this_year" in tags  # feeds the rolling-expiry CTA
    assert "retaker_only_practical_left" in tags


def test_weekly_hours_probe_tags_match_prep_context_bands() -> None:
    probes = {probe.topic: probe for probe in get_profile_probes() if probe.section_id == "pr_prep_context"}

    tags = [tag for _letter, _text, tag in probes["weekly_study_hours"].options]
    # These tags are the wire values consumed by pass_readiness_scoring.PrepContext.
    assert tags == ["lt_5", "5_10", "10_20", "gt_20"]


def test_pass_readiness_form_fills_prep_context_with_the_new_probes() -> None:
    service = _pass_readiness_service()

    payload = service.create_session(user_id="student_demo", count=15, assessment_type="pass_readiness")

    assert payload["blueprint_version"] == "pass_readiness_architecture_v1"
    assert payload["checkpoint_after"] == 6
    assert payload["delivered_count"] == 15
    assert payload["scored_count"] == 12
    assert payload["profile_count"] == 3
    profile_questions = [item for item in payload["session_questions"] if not item["scored"]]
    assert [item["section_id"] for item in profile_questions] == ["pr_prep_context"] * 3
    probe_ids = [item["provenance"]["question_id"] for item in profile_questions]
    assert probe_ids == [
        "profile_pr_attempt_history_v1",
        "profile_pr_recent_score_band_v1",
        "profile_pr_weekly_study_hours_v1",
    ]
    # Answer wire format unchanged: option-tap questions with letter keys only.
    for item in payload["questions"]:
        assert item["options"]
        assert all(len(option["key"]) <= 2 for option in item["options"])
        assert "answer" not in item


def test_diagnostic_v1_still_uses_its_own_four_probes_in_order() -> None:
    candidates = [
        QuestionCandidate(
            source_question_id=f"diag_{index}",
            question_stem=f"诊断题 {index}",
            question_type="case_study",
            chapter=f"诊断章节 {index}",
            options=(("A", "选项 A"), ("B", "选项 B"), ("C", "选项 C"), ("D", "选项 D")),
            answer="A",
            difficulty=("easy", "medium", "hard")[index % 3],
            source_type="REAL_EXAM",
        )
        for index in range(1, 80)
    ]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("diagnostic_v1"),
        provider=StaticAssessmentQuestionProvider(candidates),
        allow_dev_fallback=False,
    )

    payload = service.create_session(user_id="student_demo", count=20)

    profile_questions = [item for item in payload["session_questions"] if not item["scored"]]
    assert [item["provenance"]["question_id"] for item in profile_questions] == [
        "profile_review_rhythm_v1",
        "profile_planning_style_v1",
        "profile_pressure_recovery_v1",
        "profile_explanation_density_v1",
    ]
