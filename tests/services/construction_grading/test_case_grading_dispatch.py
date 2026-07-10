"""判分分发器:按题型路由到对的引擎 + official_score_allowed 恒 False + 拒绝未知/畸形。"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_calc_dag import CalcRole, CalcStep
from deeptutor.services.construction_grading.case_cpm_solver import Activity, solve_cpm
from deeptutor.services.construction_grading.case_flaw_correction import FlawCorrectionPair
from deeptutor.services.construction_grading.case_grading_dispatch import (
    DispatchError,
    DispatchResult,
    PracticeGradingKind,
    dispatch_grade,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
)
from deeptutor.services.construction_grading.case_load_combination import SetMembershipPoint
from deeptutor.services.construction_grading.case_process_ordering import OrderingSpec

_REF = SourceRef("exam_reference_answer", "dispatch")


def _member(pid):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no="1", qid="q::s1", sub_qid="q::s1", statement=f"s-{pid}",
        authority_source="official_answer", point_type=PointType.CONJUNCTION_MEMBER,
        required_terms=(), acceptable_variants=(AcceptableVariant("v", _REF),),
        max_score=0.5, textbook_source_refs=(_REF,), answer_key_authority="official_answer",
        conjunction_group="g1",
    )


def test_dispatch_calc_dag():
    steps = [
        CalcStep("A", "48000", (), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("B", "A * 0.15", ("A",), 0.01, 2, 1.0, CalcRole.RESULT),
    ]
    r = dispatch_grade(PracticeGradingKind.CALC_DAG, spec=(steps, {}), student={"A": 48000.0, "B": 7200.0})
    assert r.awarded == 2.0 and r.max_score == 2.0 and r.official_score_allowed is False


def test_dispatch_set_membership():
    pts = [SetMembershipPoint("底面模板", frozenset({"G1", "Q1"}), 1.0)]
    r = dispatch_grade(PracticeGradingKind.SET_MEMBERSHIP, spec=pts, student={"底面模板": ["G1", "Q1"]})
    assert r.awarded == 1.0 and r.official_score_allowed is False


def test_dispatch_ordering():
    spec = OrderingSpec.from_sequence(["清理", "支模", "浇筑"])
    ok = dispatch_grade(PracticeGradingKind.ORDERING, spec=spec, student=["清理", "支模", "浇筑"], points=2.0)
    assert ok.awarded == 2.0
    bad = dispatch_grade(PracticeGradingKind.ORDERING, spec=spec, student=["支模", "清理", "浇筑"], points=2.0)
    assert bad.awarded == 0.0


def test_dispatch_conjunction():
    pair = FlawCorrectionPair(flaw=_member("flaw"), correction=_member("fix"))
    full = dispatch_grade(PracticeGradingKind.CONJUNCTION, spec=pair, student=(True, True))
    assert full.awarded == 1.0
    half = dispatch_grade(PracticeGradingKind.CONJUNCTION, spec=pair, student=(True, False))
    assert half.awarded == 0.0  # 找错不改正不得分


def test_dispatch_cpm_critical_path():
    net = [Activity("S", 0, ()), Activity("A", 3, ("S",)), Activity("B", 2, ("S",)),
           Activity("E", 3, ("A", "B")), Activity("T", 0, ("E",))]
    result = solve_cpm(net)
    r = dispatch_grade(PracticeGradingKind.CPM_CRITICAL_PATH, spec=result,
                       student=list(result.critical_paths[0]), points=3.0)
    assert r.awarded == 3.0 and r.official_score_allowed is False


def test_all_kinds_never_official_score():
    # 结构不变量:任何路由都 official_score_allowed=False。
    steps = [CalcStep("A", "1", (), 0.0, None, 1.0, CalcRole.RESULT)]
    r = dispatch_grade(PracticeGradingKind.CALC_DAG, spec=(steps, {}), student={"A": 1.0})
    assert isinstance(r, DispatchResult) and r.official_score_allowed is False


def test_unknown_kind_and_malformed_payload_raise():
    with pytest.raises(DispatchError):
        dispatch_grade(PracticeGradingKind.CALC_DAG, spec="not-a-tuple", student={})
    with pytest.raises(DispatchError):
        dispatch_grade(PracticeGradingKind.ORDERING, spec="not-a-spec", student=[], points=1.0)
    with pytest.raises(DispatchError):  # ORDERING 缺 points
        dispatch_grade(PracticeGradingKind.ORDERING, spec=OrderingSpec.from_sequence(["A"]), student=["A"])
