from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
)
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage


def test_diagnostic_v1_has_20_units_with_16_scored_and_4_profile() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")

    assert blueprint.version == "diagnostic_v1"
    assert blueprint.requested_count == 20
    assert blueprint.scored_count == 16
    assert blueprint.profile_count == 4
    assert sum(section.count for section in blueprint.sections) == 20
    assert sum(section.count for section in blueprint.sections if section.scored) == 16
    assert sum(section.count for section in blueprint.sections if not section.scored) == 4


def test_calculation_is_optional_and_structured_judgment_is_fallback() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    comprehensive = next(section for section in blueprint.sections if section.id == "comprehensive_application")

    assert comprehensive.count == 2
    assert "case_study" in comprehensive.question_types
    assert "calculation" in comprehensive.question_types
    assert "structured_judgment" in comprehensive.fallback_question_types
    assert comprehensive.hard_require_calculation is False


def test_coverage_passes_when_every_section_has_three_x_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "pass"
    assert report["requested_count"] == 20
    assert report["issues"] == []


def test_coverage_fails_closed_when_a_section_is_missing_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
        if section.id != "planning_schedule"
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "fail"
    assert any(issue["section_id"] == "planning_schedule" for issue in report["issues"])
    assert any(issue["code"] == "insufficient_candidates" for issue in report["issues"])


def test_question_bank_id_is_required_but_source_chunk_id_is_only_warning() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": 0 if section.id == "main_structure" else section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "fail"
    assert any(issue["code"] == "missing_question_id_provenance" for issue in report["issues"])
    assert any(issue["code"] == "weak_source_chunk_trace" for issue in report["issues"])


def test_sparse_calculation_uses_structured_judgment_warning_not_blocker() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "pass"
    assert any(issue["code"] == "calculation_fallback_used" for issue in report["issues"])


def _candidate(
    index: int,
    *,
    question_type: str = "single_choice",
    chapter: str = "建筑实务",
    difficulty: str = "medium",
) -> QuestionCandidate:
    return QuestionCandidate(
        source_question_id=f"q_{index}",
        question_stem=f"题干 {index}",
        question_type=question_type,
        chapter=chapter,
        options=(("A", "选项 A"), ("B", "选项 B"), ("C", "选项 C"), ("D", "选项 D")),
        answer="A",
        difficulty=difficulty,
        source_type="REAL_EXAM",
    )


def test_blueprint_service_creates_20_units_with_profile_probes() -> None:
    candidates = [_candidate(index) for index in range(1, 40)] + [
        _candidate(100 + index, question_type="case_study") for index in range(1, 10)
    ]
    service = AssessmentBlueprintService(
        provider=StaticAssessmentQuestionProvider(candidates),
        allow_dev_fallback=False,
    )

    payload = service.create_session(user_id="student_demo", count=20)

    assert payload["blueprint_version"] == "diagnostic_v1"
    assert payload["requested_count"] == 20
    assert payload["delivered_count"] == 20
    assert payload["scored_count"] == 16
    assert payload["profile_count"] == 4
    assert payload["shortfall_count"] == 0
    assert sum(1 for item in payload["session_questions"] if item["scored"]) == 16
    assert sum(1 for item in payload["session_questions"] if not item["scored"]) == 4
    assert all(item["provenance"]["question_id"] for item in payload["session_questions"])
    assert payload["sections"][0]["section_id"] == "foundation_deep_foundation"


def test_blueprint_service_spreads_scored_questions_across_chapters_and_difficulties() -> None:
    difficulties = ("easy", "medium", "hard")
    candidates = [
        _candidate(
            index,
            question_type="case_study",
            chapter=f"诊断章节 {index}",
            difficulty=difficulties[index % len(difficulties)],
        )
        for index in range(1, 50)
    ]
    service = AssessmentBlueprintService(
        provider=StaticAssessmentQuestionProvider(candidates),
        allow_dev_fallback=False,
    )

    payload = service.create_session(user_id="student_demo", count=20)
    scored = [item for item in payload["session_questions"] if item["scored"]]

    assert len(scored) == 16
    assert len({item["chapter"] for item in scored}) == 16
    assert {item["difficulty"] for item in scored} == {"easy", "medium", "hard"}


def test_static_provider_prefers_section_topics_when_available() -> None:
    section = get_assessment_blueprint("diagnostic_v1").sections[0]
    candidates = [
        _candidate(1, question_type="case_study", chapter="主体结构"),
        _candidate(2, question_type="case_study", chapter="地基基础"),
        _candidate(3, question_type="case_study", chapter="深基坑支护"),
        _candidate(4, question_type="case_study", chapter="施工组织"),
    ]
    provider = StaticAssessmentQuestionProvider(candidates)

    selected = provider.get_candidates(section, limit=2, exclude_source_ids=set(), selection_seed="topic-test")

    assert {item.chapter for item in selected} == {"地基基础", "深基坑支护"}


def test_supabase_candidate_rows_use_chinese_chapter_labels_for_node_codes() -> None:
    section = get_assessment_blueprint("diagnostic_v1").sections[1]

    tagged_candidate = SupabaseAssessmentQuestionProvider._candidate_from_row(
        {
            "id": "122",
            "question_stem": "题干",
            "question_type": "multi_choice",
            "source_type": "REAL_EXAM",
            "node_code": "1A411002",
            "tags": {"node_name": "建筑构造设计要求"},
            "difficulty": "0.3",
            "options": {"A": "选项 A", "B": "选项 B"},
            "correct_answer": "A",
        },
        section,
    )
    candidate = SupabaseAssessmentQuestionProvider._candidate_from_row(
        {
            "id": "123",
            "question_stem": "题干",
            "question_type": "single_choice",
            "source_type": "REAL_EXAM",
            "node_code": "1A412030",
            "difficulty": "16.2",
            "options": {"A": "选项 A", "B": "选项 B"},
            "correct_answer": "A",
        },
        section,
    )

    assert tagged_candidate is not None
    assert tagged_candidate.chapter == "建筑构造设计要求"
    assert tagged_candidate.difficulty == "medium"
    assert candidate is not None
    assert candidate.chapter == "结构设计与建筑材料"
    assert candidate.difficulty == "hard"


def test_blueprint_service_fails_closed_when_scored_candidates_are_short() -> None:
    service = AssessmentBlueprintService(
        provider=StaticAssessmentQuestionProvider([_candidate(1), _candidate(2)]),
        allow_dev_fallback=False,
    )

    try:
        service.create_session(user_id="student_demo", count=20)
    except AssessmentBlueprintUnavailable as exc:
        assert "requires" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected blueprint service to fail closed")
