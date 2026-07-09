"""判断改正合取门测试:找错∧改正都对才给分(§4 红线),否则 0 + 诊断状态。"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_flaw_correction import (
    FlawCorrectionError,
    FlawCorrectionPair,
    FlawCorrectionStatus,
    judge_flaw_correction,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
)

_REF = SourceRef("exam_reference_answer", "判断改正真题")


def _member(pid, statement, *, group="g1", score=0.5, ptype=PointType.CONJUNCTION_MEMBER,
            qid="q::sub1", sub_no="1"):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no=sub_no, qid=qid, sub_qid=qid,
        statement=statement, authority_source="official_answer", point_type=ptype,
        required_terms=(), acceptable_variants=(AcceptableVariant("v", _REF),),
        max_score=score, textbook_source_refs=(_REF,), answer_key_authority="official_answer",
        conjunction_group=group,
    )


def _pair():
    return FlawCorrectionPair(
        flaw=_member("flaw", "指出:模板拆除时间不对", score=0.5),
        correction=_member("fix", "改正:应达到规范规定强度后再拆", score=0.5),
    )


def test_both_hit_full_score():
    v = judge_flaw_correction(_pair(), flaw_hit=True, correction_hit=True)
    assert v.status == FlawCorrectionStatus.FULL
    assert v.awarded_score == 1.0
    assert v.conjunction_group == "g1"


def test_flaw_only_gets_zero():
    # 找到错但没改正/改正错 → 合取门不给分(§4 红线)
    v = judge_flaw_correction(_pair(), flaw_hit=True, correction_hit=False)
    assert v.status == FlawCorrectionStatus.FLAW_ONLY
    assert v.awarded_score == 0.0


def test_correction_only_gets_zero():
    v = judge_flaw_correction(_pair(), flaw_hit=False, correction_hit=True)
    assert v.status == FlawCorrectionStatus.CORRECTION_ONLY
    assert v.awarded_score == 0.0


def test_miss_gets_zero():
    v = judge_flaw_correction(_pair(), flaw_hit=False, correction_hit=False)
    assert v.status == FlawCorrectionStatus.MISS
    assert v.awarded_score == 0.0


def test_combined_max_score():
    assert _pair().combined_max_score == 1.0


def test_cross_question_pair_rejected():
    # 2026-07-09 Codex 对抗核证伪:Q1 的找错子 + Q2 的改正子(同名组)不成一对。
    with pytest.raises(FlawCorrectionError):
        FlawCorrectionPair(
            flaw=_member("q1_flaw", "s", group="same", qid="Q1::s1"),
            correction=_member("q2_fix", "s", group="same", qid="Q2::s1"),
        )


def test_non_positive_score_pair_rejected():
    # 合取对必须带正分(0/负分半会让 status=full 但 awarded 非正)。
    with pytest.raises(FlawCorrectionError):
        FlawCorrectionPair(
            flaw=_member("a", "s", score=0.0),
            correction=_member("b", "s", score=0.5),
        )


def test_malformed_pairs_raise():
    with pytest.raises(FlawCorrectionError):  # same point
        p = _member("x", "s")
        FlawCorrectionPair(flaw=p, correction=p)
    with pytest.raises(FlawCorrectionError):  # different groups
        FlawCorrectionPair(flaw=_member("a", "s", group="g1"), correction=_member("b", "s", group="g2"))
    with pytest.raises(FlawCorrectionError):  # None group
        FlawCorrectionPair(flaw=_member("a", "s", group=None), correction=_member("b", "s", group=None))
    with pytest.raises(FlawCorrectionError):  # not CONJUNCTION_MEMBER
        FlawCorrectionPair(
            flaw=_member("a", "s", ptype=PointType.PROCEDURE),
            correction=_member("b", "s"),
        )
