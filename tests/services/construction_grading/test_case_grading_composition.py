"""组合适配器 on-ramp:小问级判分 kind 派生(tag 优先 → 结构派生 → None 默认)。"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_flaw_correction import judge_flaw_correction
from deeptutor.services.construction_grading.case_grading_composition import (
    SPEC_BUILDABLE_FROM_REVIEW,
    CompositionError,
    assemble_conjunction_pairs,
    assemble_ordering_spec,
    derive_grading_kind,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    ConjunctionRole,
    LubanCaseScoringPoint,
    PointType,
    PracticeGradingKind,
    SourceRef,
)
from deeptutor.services.construction_grading.case_process_ordering import grade_ordering

_REF = SourceRef("exam_reference_answer", "q")


def _p(pid, *, kind=None, conj=None, order=None, rank=None, role=None, ptype=PointType.PROCEDURE):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no="1", qid="Q::E0", sub_qid="Q::E0::sub1",
        statement=f"s-{pid}", authority_source="official_answer", point_type=ptype,
        required_terms=(), acceptable_variants=(AcceptableVariant("_", _REF),), max_score=0.5,
        textbook_source_refs=(_REF,), answer_key_authority="official_answer",
        conjunction_group=conj, ordering_group=order, practice_grading_kind=kind,
        ordering_rank=rank, conjunction_role=role,
    )


def _cm(pid, group, role):
    # 合取子:point_type 必须是合取子(FlawCorrectionPair 校验)。
    return _p(pid, conj=group, role=role, ptype=PointType.CONJUNCTION_MEMBER)


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


# ── 层② spec 装配:ORDERING(真题金标 EXAM_1A434000_P0010_02 工艺流程)──

def test_assemble_ordering_spec_from_rank_and_grades_end_to_end():
    # 真题工艺流程:清理表面→支设模板→洒水湿润→涂抹界面剂(用 point_id 承载,rank=次序)。
    pts = [
        _p("涂抹界面剂", order="o", rank=4), _p("清理表面", order="o", rank=1),
        _p("支设模板", order="o", rank=2), _p("洒水湿润", order="o", rank=3),
    ]  # 故意乱序传入,装配须按 rank 排
    spec = assemble_ordering_spec(pts)
    assert spec.activities == ("清理表面", "支设模板", "洒水湿润", "涂抹界面剂")
    # 端到端:正确序判对,换序判错(装配的 spec 真能喂引擎)
    assert grade_ordering(spec, ["清理表面", "支设模板", "洒水湿润", "涂抹界面剂"]).correct
    assert not grade_ordering(spec, ["支设模板", "清理表面", "洒水湿润", "涂抹界面剂"]).correct


def test_assemble_ordering_fails_closed_on_missing_or_bad_rank():
    with pytest.raises(CompositionError):  # 缺 rank
        assemble_ordering_spec([_p("a", order="o", rank=1), _p("b", order="o")])
    with pytest.raises(CompositionError):  # rank 重复
        assemble_ordering_spec([_p("a", order="o", rank=1), _p("b", order="o", rank=1)])
    with pytest.raises(CompositionError):  # rank 不连续(1,3 缺 2)
        assemble_ordering_spec([_p("a", order="o", rank=1), _p("b", order="o", rank=3)])
    with pytest.raises(CompositionError):  # 无工序点
        assemble_ordering_spec([_p("a")])


# ── 层② spec 装配:CONJUNCTION(判断改正,找错∧改正)──

def test_assemble_conjunction_pairs_and_grades_end_to_end():
    # 两处判断改正 → 两对(g1/g2),每对一 FLAW 一 CORRECTION。
    pts = [
        _cm("g1_fix", "g1", ConjunctionRole.CORRECTION), _cm("g1_flaw", "g1", ConjunctionRole.FLAW),
        _cm("g2_flaw", "g2", ConjunctionRole.FLAW), _cm("g2_fix", "g2", ConjunctionRole.CORRECTION),
    ]
    pairs = assemble_conjunction_pairs(pts)
    assert len(pairs) == 2
    # 角色装配正确:每对 flaw 是 FLAW 那个、correction 是 CORRECTION 那个
    assert pairs[0].flaw.point_id == "g1_flaw" and pairs[0].correction.point_id == "g1_fix"
    # 端到端合取门:找错∧改正都命中给满分,只找错不改正 0(§4 红线)
    both = judge_flaw_correction(pairs[0], flaw_hit=True, correction_hit=True).awarded_score
    only = judge_flaw_correction(pairs[0], flaw_hit=True, correction_hit=False).awarded_score
    assert both > 0 and only == 0.0


def test_assemble_conjunction_fails_closed_on_malformed_group():
    with pytest.raises(CompositionError):  # 组员≠2(只 1 个)
        assemble_conjunction_pairs([_cm("a", "g1", ConjunctionRole.FLAW)])
    with pytest.raises(CompositionError):  # 两个同 role(缺 CORRECTION)
        assemble_conjunction_pairs([
            _cm("a", "g1", ConjunctionRole.FLAW), _cm("b", "g1", ConjunctionRole.FLAW),
        ])
    with pytest.raises(CompositionError):  # 无合取点
        assemble_conjunction_pairs([_p("a")])


def test_ordering_rank_must_be_positive():
    from deeptutor.services.construction_grading.case_light_practice_contract import ScoringPointError
    with pytest.raises(ScoringPointError):
        _p("a", order="o", rank=0)
