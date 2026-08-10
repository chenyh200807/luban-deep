"""表单 v2 blueprint（§6.2-v2）：39 交互结构、两级检查点、多选真题过滤。"""

from __future__ import annotations

from typing import Any

from deeptutor.services.assessment import compiled_practice_provider as cpp
from deeptutor.services.assessment.blueprint import (
    COMPILED_PRACTICE_QUESTION_SOURCE,
    AssessmentBlueprint,
    AssessmentSection,
    ability_dimensions_by_section,
    get_assessment_blueprint,
)
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    _real_exam_marked,
    _select_diagnostic_candidates,
)
from tests.services.assessment.test_compiled_practice_provider import (
    _item,
    _provider,
)


def test_v2_is_39_interactions_30_objective_6_case_3_probes() -> None:
    blueprint = get_assessment_blueprint("pass_readiness_architecture_v2")

    assert blueprint.version == "pass_readiness_architecture_v2"
    assert blueprint.assessment_type == "pass_readiness"
    assert blueprint.requested_count == 39
    assert blueprint.scored_count == 36
    assert blueprint.profile_count == 3

    singles = [s for s in blueprint.sections if s.question_source == COMPILED_PRACTICE_QUESTION_SOURCE]
    # 五族配额=选编定稿 family_matrix(主体5/安全4/进度3/质量4/防水4,案例段补齐
    # 族平衡),合计 20 单选。
    assert len(singles) == 5 and sum(s.count for s in singles) == 20
    assert {s.id: s.count for s in singles} == {
        "pr2_single_main_structure": 5,
        "pr2_single_safety": 4,
        "pr2_single_schedule": 3,
        "pr2_single_quality": 4,
        "pr2_single_waterproof": 4,
    }
    assert all(s.question_types == ("single_choice",) for s in singles)
    assert all(s.compiled_packs for s in singles)

    multi = next(s for s in blueprint.sections if s.id == "pr2_objective_multi")
    assert multi.count == 10
    assert multi.question_types == ("multi_choice",)
    # 真题原题双闸：source_types 排除 REAL_EXAM + based_on/source 标记过滤。
    assert "REAL_EXAM" not in multi.source_types
    assert multi.exclude_real_exam_marked is True

    cases = [s for s in blueprint.sections if s.id.startswith("pr2_case_")]
    assert len(cases) == 3 and all(s.count == 2 for s in cases)

    prep = next(s for s in blueprint.sections if not s.scored)
    assert prep.id == "pr_prep_context" and prep.count == 3  # 复用 v1 probe 注册


def test_v1_blueprint_is_untouched_rollback_anchor() -> None:
    v1 = get_assessment_blueprint("pass_readiness_architecture_v1")

    assert v1.requested_count == 15
    assert v1.scored_count == 12
    assert all(
        s.question_source == "questions_bank" and not s.exclude_real_exam_marked
        for s in v1.sections
    )


def test_v2_dimension_matrix_core20_logic10_case6() -> None:
    blueprint = get_assessment_blueprint("pass_readiness_architecture_v2")
    by_dimension: dict[str, int] = {}
    for section in blueprint.sections:
        if section.scored:
            assert section.ability_dimension, section.id
            by_dimension[section.ability_dimension] = (
                by_dimension.get(section.ability_dimension, 0) + section.count
            )
    assert by_dimension == {
        "core_knowledge": 20,
        "construction_logic": 10,
        "case_scoring_point_recognition": 6,
    }
    assert ability_dimensions_by_section("pass_readiness_architecture_v2")[
        "pr2_single_main_structure"
    ] == "core_knowledge"


def test_v2_is_pure_tap_only() -> None:
    blueprint = get_assessment_blueprint("pass_readiness_architecture_v2")
    allowed = {"single_choice", "multi_choice"}
    for section in blueprint.sections:
        if not section.scored:
            assert section.question_types == ("profile_probe",)
            continue
        assert set(section.question_types) <= allowed, section.id
        assert set(section.fallback_question_types) <= allowed, section.id


def _bank_candidate(
    source_id: str,
    *,
    question_type: str = "multi_choice",
    source_type: str = "textbook_exercise",
    source_meta: dict[str, Any] | None = None,
    chapter: str = "质量验收",
) -> QuestionCandidate:
    return QuestionCandidate(
        source_question_id=source_id,
        question_stem=f"多选题干 {source_id} 质量验收",
        question_type=question_type,
        chapter=chapter,
        options=(("A", "甲"), ("B", "乙"), ("C", "丙"), ("D", "丁")),
        answer="AB",
        source_type=source_type,
        source_meta=source_meta or {},
    )


def test_multi_section_filters_real_exam_marked_rows() -> None:
    blueprint = get_assessment_blueprint("pass_readiness_architecture_v2")
    multi = next(s for s in blueprint.sections if s.id == "pr2_objective_multi")
    candidates = [
        _bank_candidate("clean-1"),
        _bank_candidate("real-exam-row", source_type="REAL_EXAM"),
        _bank_candidate("based-on-marked", source_meta={"based_on": "2021年真题第8题"}),
        _bank_candidate("exam-year-marked", source_meta={"exam_year": 2019}),
        _bank_candidate("text-marked", source_meta={"note": "改编自真题"}),
        _bank_candidate("clean-2", chapter="安全"),
    ]
    selected = _select_diagnostic_candidates(
        candidates, section=multi, limit=10, selection_seed="s", avoid_chapters=set()
    )
    assert {c.source_question_id for c in selected} == {"clean-1", "clean-2"}
    assert _real_exam_marked(_bank_candidate("x", source_meta={"based_on": "y"}))
    assert not _real_exam_marked(_bank_candidate("x"))


def test_v1_sections_do_not_filter_marked_rows() -> None:
    # 回滚锚保护：无 exclude_real_exam_marked 声明的 section 行为不变。
    v1 = get_assessment_blueprint("pass_readiness_architecture_v1")
    section = next(s for s in v1.sections if s.id == "pr_objective_multi")
    candidates = [_bank_candidate("based-on-marked", source_meta={"based_on": "真题"})]
    selected = _select_diagnostic_candidates(
        candidates, section=section, limit=2, selection_seed="s", avoid_chapters=set()
    )
    assert [c.source_question_id for c in selected] == ["based-on-marked"]


def _tiny_single_section_blueprint() -> AssessmentBlueprint:
    return AssessmentBlueprint(
        version="single_section_probe_test",
        requested_count=4,
        sections=(
            AssessmentSection(
                id="s1",
                label="s1",
                count=4,
                scored=True,
                question_types=("single_choice",),
                minimum_multiplier=1,
            ),
        ),
    )


def test_create_payload_delivers_requested_count() -> None:
    candidates = [
        QuestionCandidate(
            source_question_id=f"q{i}",
            question_stem=f"题干{i}",
            question_type="single_choice",
            chapter=f"章节{i}",
            options=(("A", "甲"), ("B", "乙")),
            answer="A",
            source_type="TEXTBOOK",
        )
        for i in range(12)
    ]
    service = AssessmentBlueprintService(
        blueprint=_tiny_single_section_blueprint(),
        provider=StaticAssessmentQuestionProvider(candidates),
    )
    payload = service.create_session(user_id="u1", count=4)
    assert payload["delivered_count"] == 4
    # 中场检查点已按 owner 2026-08-07 拍板全链下线:create payload 不再导出该族字段。
    assert "checkpoint_after" not in payload and "checkpoints" not in payload


def test_v2_form_assembles_39_units_with_routed_sources() -> None:
    """端到端组卷：五族编译读源 + 练习册多选/案例静态源 → 39 交互成卷。"""
    blueprint = get_assessment_blueprint("pass_readiness_architecture_v2")
    authorities: dict[str, Any] = {}
    for section in blueprint.sections:
        if section.question_source != COMPILED_PRACTICE_QUESTION_SOURCE:
            continue
        for pack in section.compiled_packs:
            authorities[pack] = {
                "items": [
                    _item(f"{pack}-v{i}", fact_id=f"{pack}-fact-{i}")
                    for i in range(3)
                ]
            }
    bank_candidates: list[QuestionCandidate] = []
    for i in range(40):
        bank_candidates.append(
            _bank_candidate(f"multi-{i}", chapter=f"多选章节{i}")
        )
    for i in range(40):
        bank_candidates.append(
            _bank_candidate(
                f"case-{i}",
                question_type="single_choice",
                source_type="TEXTBOOK_ASSESSMENT",
                chapter=f"案例章节{i}",
            )
        )
    routed = cpp.SourceRoutedAssessmentQuestionProvider(
        default_provider=StaticAssessmentQuestionProvider(bank_candidates),
        compiled_provider=_provider(authorities),
    )
    service = AssessmentBlueprintService(blueprint=blueprint, provider=routed)
    payload = service.create_session(user_id="u1", count=39)

    assert payload["delivered_count"] == 39
    assert payload["scored_count"] == 36
    assert payload["profile_count"] == 3
    compiled_questions = [
        q
        for q in payload["session_questions"]
        if q.get("provenance", {}).get("source_table") == "luban_compiled_practice_authority"
    ]
    assert len(compiled_questions) == 20  # 20 单选全部来自编译轻练权威
    multi_questions = [
        q for q in payload["session_questions"] if q["section_id"] == "pr2_objective_multi"
    ]
    assert len(multi_questions) == 10
    assert all(
        q["provenance"]["source_type"] in {"TEXTBOOK", "textbook_exercise"}
        for q in multi_questions
    )
