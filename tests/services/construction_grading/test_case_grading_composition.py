"""组合适配器 on-ramp:小问级判分 kind 派生(tag 优先 → 结构派生 → None 默认)。"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_grading_composition import (
    SPEC_BUILDABLE_FROM_REVIEW,
    CompositionError,
    derive_grading_kind,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    PracticeGradingKind,
    SourceRef,
)

_REF = SourceRef("exam_reference_answer", "q")


def _p(pid, *, kind=None, conj=None, order=None):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no="1", qid="Q::E0", sub_qid="Q::E0::sub1",
        statement=f"s-{pid}", authority_source="official_answer", point_type=PointType.PROCEDURE,
        required_terms=(), acceptable_variants=(AcceptableVariant("_", _REF),), max_score=0.5,
        textbook_source_refs=(_REF,), answer_key_authority="official_answer",
        conjunction_group=conj, ordering_group=order, practice_grading_kind=kind,
    )


def test_explicit_tag_wins():
    pts = [_p("a", kind=PracticeGradingKind.CALC_DAG), _p("b", kind=PracticeGradingKind.CALC_DAG)]
    assert derive_grading_kind(pts) is PracticeGradingKind.CALC_DAG


def test_conflicting_explicit_tags_raise():
    pts = [_p("a", kind=PracticeGradingKind.CALC_DAG), _p("b", kind=PracticeGradingKind.CPM_CRITICAL_PATH)]
    with pytest.raises(CompositionError):
        derive_grading_kind(pts)


def test_conjunction_derived_from_structure():
    pts = [_p("a", conj="g1"), _p("b", conj="g1")]
    assert derive_grading_kind(pts) is PracticeGradingKind.CONJUNCTION


def test_ordering_derived_from_structure():
    assert derive_grading_kind([_p("a", order="o1"), _p("b", order="o1")]) is PracticeGradingKind.ORDERING


def test_explicit_tag_beats_structure():
    # 教研显式标 SET_MEMBERSHIP 优先于顺带的 ordering_group(tag 是权威)。
    pts = [_p("a", kind=PracticeGradingKind.SET_MEMBERSHIP, order="o1")]
    assert derive_grading_kind(pts) is PracticeGradingKind.SET_MEMBERSHIP


def test_plain_points_yield_none_default_coverage():
    # 无 tag 无结构 → None(采分点点选/漏点补全走 coverage,不进 dispatch 引擎)。
    assert derive_grading_kind([_p("a"), _p("b")]) is None


def test_spec_buildability_map_matches_dispatch_kinds():
    # 组合层 spec 可建性映射覆盖全部 5 个 dispatch kind;ORDERING/CONJUNCTION 可从 review 建,
    # CALC/CPM/SET 需作者产物(记录依赖边界,防"以为整条能自动跑")。
    assert set(SPEC_BUILDABLE_FROM_REVIEW) == set(PracticeGradingKind)
    assert SPEC_BUILDABLE_FROM_REVIEW[PracticeGradingKind.CONJUNCTION] is True
    assert SPEC_BUILDABLE_FROM_REVIEW[PracticeGradingKind.ORDERING] is True
    assert SPEC_BUILDABLE_FROM_REVIEW[PracticeGradingKind.CALC_DAG] is False
    assert SPEC_BUILDABLE_FROM_REVIEW[PracticeGradingKind.CPM_CRITICAL_PATH] is False
    assert SPEC_BUILDABLE_FROM_REVIEW[PracticeGradingKind.SET_MEMBERSHIP] is False
