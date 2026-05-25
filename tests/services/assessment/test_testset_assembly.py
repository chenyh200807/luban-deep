from __future__ import annotations

import pytest

from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
)
from deeptutor.services.assessment.blueprint import real_exam_source_policy


def _candidate(index: int, *, stem: str | None = None, source_id: str | None = None) -> QuestionCandidate:
    return QuestionCandidate(
        source_question_id=source_id or f"waterproof_{index}",
        question_stem=stem or f"防水工程第 {index} 题，关于卷材搭接和节点处理的正确做法是？",
        question_type="single_choice" if index % 3 else "multi_choice",
        chapter="防水工程",
        options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
        answer="A" if index % 3 else "AB",
        difficulty="medium",
        source_type="REAL_EXAM",
        node_code="1A414010",
        source_meta={"topic": "防水", "semantic_signature": f"waterproof_sig_{index}"},
    )


def test_p0a_blueprint_delivers_exact_signed_off_count() -> None:
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(80)]),
    )

    payload = service.create_session(
        user_id="student_demo",
        count=12,
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=("waterproof",),
    )

    assert payload["assessment_type"] == "topic_diagnostic"
    assert payload["subject_id"] == "construction_exam"
    assert payload["topic_ids"] == ["waterproof"]
    assert payload["blueprint_version"] == "topic_waterproof_v1"
    assert payload["requested_count"] == 12
    assert payload["delivered_count"] == 12
    assert payload["scored_count"] == 12
    assert payload["profile_count"] == 0
    assert all(question["scored"] for question in payload["questions"])
    assert "answer" not in payload["questions"][0]
    assert "answer" in payload["session_questions"][0]


def test_p0a_form_bank_rotates_unique_scored_items_across_five_forms() -> None:
    blueprint = get_assessment_blueprint("topic_waterproof_v1")
    service = AssessmentBlueprintService(
        blueprint=blueprint,
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(80)]),
    )

    form_bank = service._get_or_build_form_bank()

    scored_source_ids = [
        unit.item.source_question_id
        for form in form_bank.forms
        for unit in form.units
        if unit.scored
    ]
    assert len(form_bank.forms) == 5
    assert len(scored_source_ids) == blueprint.scored_count * 5
    assert len(scored_source_ids) == len(set(scored_source_ids))


def test_p0a_form_bank_can_ship_three_form_minimum_when_five_form_target_is_short() -> None:
    blueprint = get_assessment_blueprint("topic_waterproof_v1")
    service = AssessmentBlueprintService(
        blueprint=blueprint,
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(36)]),
    )

    form_bank = service._get_or_build_form_bank()

    scored_source_ids = [
        unit.item.source_question_id
        for form in form_bank.forms
        for unit in form.units
        if unit.scored
    ]
    assert len(form_bank.forms) == 3
    assert len(scored_source_ids) == blueprint.scored_count * 3
    assert len(scored_source_ids) == len(set(scored_source_ids))


def test_p0a_blueprint_fails_closed_when_topic_candidates_short() -> None:
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(6)]),
    )

    with pytest.raises(AssessmentBlueprintUnavailable):
        service.create_session(
            user_id="student_demo",
            count=12,
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            topic_ids=("waterproof",),
        )


def test_p0a_does_not_silently_use_generic_topic_candidates() -> None:
    generic = [
        QuestionCandidate(
            source_question_id=f"generic_{index}",
            question_stem=f"主体结构第 {index} 题，关于混凝土浇筑的正确做法是？",
            question_type="single_choice",
            chapter="主体结构",
            options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
            answer="A",
            difficulty="medium",
            source_type="REAL_EXAM",
            node_code="1A413000",
            source_meta={"topic": "主体结构"},
        )
        for index in range(30)
    ]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider(generic),
    )

    with pytest.raises(AssessmentBlueprintUnavailable):
        service.create_session(
            user_id="student_demo",
            count=12,
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            topic_ids=("waterproof",),
        )


def test_p0a_dedupes_semantic_signature_when_available() -> None:
    candidates = [_candidate(index, source_id=f"same_semantic_{index}") for index in range(80)]
    candidates[1] = _candidate(1, source_id="same_semantic_duplicate")
    candidates[1].source_meta["semantic_signature"] = candidates[0].source_meta["semantic_signature"]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider(candidates),
    )

    payload = service.create_session(
        user_id="student_demo",
        count=12,
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=("waterproof",),
    )

    signatures = [
        question["provenance"]["source_meta"].get("semantic_signature")
        for question in payload["session_questions"]
    ]
    assert len(signatures) == len(set(signatures))


class SparseStrictTopicSupabaseProvider(SupabaseAssessmentQuestionProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def _supabase_config(self) -> tuple[str, str]:
        return "https://example.supabase.co", "test-key"

    def _get_candidates_for_types(self, *args, **kwargs) -> list[QuestionCandidate]:
        self.call_count += 1
        limit = int(kwargs["limit"])
        if self.call_count == 1:
            return [
                QuestionCandidate(
                    source_question_id=f"generic_{index}",
                    question_stem=f"主体结构第 {index} 题，关于混凝土浇筑的正确做法是？",
                    question_type="single_choice",
                    chapter="主体结构",
                    options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
                    answer="A",
                    difficulty="medium",
                    source_type="REAL_EXAM",
                    node_code="1A413000",
                    source_meta={"topic": "主体结构"},
                )
                for index in range(limit)
            ]
        return [
            QuestionCandidate(
                source_question_id=f"waterproof_extra_{index}",
                question_stem=f"防水施工第 {index} 题，关于施工缝和节点处理的正确做法是？",
                question_type="single_choice",
                chapter="防水施工",
                options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
                answer="A",
                difficulty="medium",
                source_type="REAL_EXAM",
                node_code="1A414010",
                source_meta={"topic": "防水"},
            )
            for index in range(limit)
        ]


def test_supabase_provider_fetches_more_when_strict_topic_window_is_sparse() -> None:
    section = next(
        section
        for section in get_assessment_blueprint("topic_waterproof_v1").sections
        if section.id == "waterproof_construction"
    )
    provider = SparseStrictTopicSupabaseProvider()

    candidates = provider.get_candidates(
        section,
        limit=4,
        exclude_source_ids=set(),
        selection_seed="strict-topic-window",
    )

    assert len(candidates) == 4
    assert all("防水" in candidate.question_stem for candidate in candidates)
    assert provider.call_count >= 2


def test_real_exam_simulation_mini_assembles_20_items_without_official_claim() -> None:
    candidates = [
        QuestionCandidate(
            source_question_id=f"real_exam_{index}",
            question_stem=f"真题样式第 {index} 题，考查建筑实务综合能力。",
            question_type="single_choice" if index % 4 else "multi_choice",
            chapter="建筑实务",
            options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
            answer="A" if index % 4 else "AB",
            difficulty="medium",
            source_type="REAL_EXAM",
            source_meta={"semantic_signature": f"real_exam_sig_{index}"},
        )
        for index in range(120)
    ]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("real_exam_simulation_mini_v1"),
        provider=StaticAssessmentQuestionProvider(candidates),
    )

    payload = service.create_session(
        user_id="student_demo",
        count=20,
        assessment_type="real_exam_simulation",
        subject_id="construction_exam",
    )

    assert payload["assessment_type"] == "real_exam_simulation"
    assert payload["blueprint_version"] == "real_exam_simulation_mini_v1"
    assert payload["requested_count"] == 20
    assert payload["delivered_count"] == 20
    assert all(question["scored"] for question in payload["questions"])
    assert "answer" not in payload["questions"][0]


def test_real_exam_copy_policy_never_claims_official_without_signoff() -> None:
    reviewed = real_exam_source_policy(
        real_exam_share=1.0,
        provenance_ok=True,
        teaching_signoff=False,
    )
    low_share = real_exam_source_policy(
        real_exam_share=0.2,
        provenance_ok=True,
        teaching_signoff=True,
    )

    assert "官方真题" not in reviewed["user_copy"]
    assert reviewed["source_policy_label"] == "真题样式测评"
    assert low_share["source_policy_label"] == "综合模拟测评"
    assert "真题样式" not in low_share["user_copy"]
