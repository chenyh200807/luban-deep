from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    _AssessmentForm,
    _AssessmentFormBank,
    _AssessmentFormUnit,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
    _form_from_persisted_row,
    _form_to_persisted_row,
)
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage
from deeptutor.services.assessment.profile_probes import get_profile_probes


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


class CountingStaticAssessmentQuestionProvider(StaticAssessmentQuestionProvider):
    def __init__(self, candidates: list[QuestionCandidate]) -> None:
        super().__init__(candidates)
        self.call_count = 0

    def get_candidates(self, *args, **kwargs):
        self.call_count += 1
        return super().get_candidates(*args, **kwargs)


class PersistedOnlyAssessmentProvider:
    def __init__(self, form_bank: _AssessmentFormBank) -> None:
        self.form_bank = form_bank
        self.get_candidate_calls = 0

    def get_candidates(self, *args, **kwargs):
        self.get_candidate_calls += 1
        raise AssertionError("create_session should not generate candidates when persisted forms exist")

    def load_persisted_form_bank(self, blueprint):
        return self.form_bank

    def question_bank_size(self) -> int:
        return self.form_bank.question_bank_size


def _persisted_form_bank_for_blueprint() -> _AssessmentFormBank:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    profile_probes = list(get_profile_probes())
    forms = []
    for form_index in range(1, 6):
        units = []
        candidate_index = form_index * 100
        profile_index = 0
        for section in blueprint.sections:
            for _ in range(section.count):
                if section.scored:
                    candidate_index += 1
                    units.append(
                        _AssessmentFormUnit(
                            section_id=section.id,
                            scored=True,
                            item=_candidate(
                                candidate_index,
                                question_type="case_study",
                                chapter=f"持久化章节 {candidate_index}",
                                difficulty=("easy", "medium", "hard")[candidate_index % 3],
                            ),
                        )
                    )
                else:
                    units.append(
                        _AssessmentFormUnit(
                            section_id=section.id,
                            scored=False,
                            item=profile_probes[profile_index],
                        )
                    )
                    profile_index += 1
        forms.append(
            _AssessmentForm(
                form_id=f"diagnostic_v1_form_{form_index}",
                form_index=form_index,
                units=tuple(units),
                fallback_used=False,
            )
        )
    return _AssessmentFormBank(forms=tuple(forms), question_bank_size=500)


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
    assert payload["form_count"] == 5
    assert 1 <= payload["form_index"] <= 5
    assert payload["form_id"].startswith("diagnostic_v1_form_")
    assert payload["shortfall_count"] == 0
    assert sum(1 for item in payload["session_questions"] if item["scored"]) == 16
    assert sum(1 for item in payload["session_questions"] if not item["scored"]) == 4
    assert all(item["provenance"]["question_id"] for item in payload["session_questions"])
    assert payload["sections"][0]["section_id"] == "foundation_deep_foundation"


def test_blueprint_service_reuses_prebuilt_five_form_bank_between_sessions() -> None:
    candidates = [
        _candidate(
            index,
            question_type="case_study",
            chapter=f"诊断章节 {index}",
            difficulty=("easy", "medium", "hard")[index % 3],
        )
        for index in range(1, 80)
    ]
    provider = CountingStaticAssessmentQuestionProvider(candidates)
    service = AssessmentBlueprintService(
        provider=provider,
        allow_dev_fallback=False,
    )

    first = service.create_session(user_id="student_demo", count=20)
    call_count_after_first = provider.call_count
    second = service.create_session(user_id="student_demo", count=20)

    assert first["form_count"] == 5
    assert second["form_count"] == 5
    assert provider.call_count == call_count_after_first
    assert call_count_after_first == 5 * sum(1 for section in service.blueprint.sections if section.scored)


def test_assessment_form_serializes_for_database_persistence() -> None:
    candidates = [
        _candidate(
            index,
            question_type="case_study",
            chapter=f"诊断章节 {index}",
            difficulty=("easy", "medium", "hard")[index % 3],
        )
        for index in range(1, 80)
    ]
    service = AssessmentBlueprintService(
        provider=StaticAssessmentQuestionProvider(candidates),
        allow_dev_fallback=False,
    )
    form_bank = service._build_form_bank()
    form = form_bank.forms[0]

    row = _form_to_persisted_row(service.blueprint.version, form, question_bank_size=form_bank.question_bank_size)
    restored = _form_from_persisted_row(row, service.blueprint)

    assert row["status"] == "active"
    assert row["form_id"] == "diagnostic_v1_form_1"
    assert row["quality_json"]["scored_count"] == 16
    assert len(row["items_json"]) == 20
    assert restored.form_id == form.form_id
    assert restored.form_index == form.form_index
    assert len(restored.units) == 20


def test_blueprint_service_uses_persisted_forms_without_candidate_generation() -> None:
    provider = PersistedOnlyAssessmentProvider(_persisted_form_bank_for_blueprint())
    service = AssessmentBlueprintService(provider=provider, allow_dev_fallback=False)

    payload = service.create_session(user_id="student_demo", count=20)

    assert provider.get_candidate_calls == 0
    assert payload["form_count"] == 5
    assert payload["question_bank_size"] == 500
    assert payload["fallback_used"] is False
    assert len(payload["questions"]) == 20


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
