"""P-1 conjunction-group scorer + RTG5 binding (§2.5③ / §4 找错∧改正 red line).

找错不改正不得满分:两名成员(找错子 / 改正子)在同一 conjunction_group,必须
全部命中才给该组分;缺任一 → 该组 0 分。判断改正题的合取约束不能丢。
"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    ScoringPointError,
    SourceBindingError,
    SourceRef,
    score_conjunction_group,
    validate_source_scoring_point_id,
)

_REF = SourceRef("exam_reference_answer", "2019-一建建筑-案例三")


def _point(point_id, *, score=1.0, conjunction_group=None, point_type=PointType.PROCEDURE,
           qid="q::sub1", sub_no="1"):
    return LubanCaseScoringPoint(
        point_id=point_id,
        sub_no=sub_no,
        qid=qid,
        sub_qid=qid,
        statement=f"statement-{point_id}",
        authority_source="official_answer",
        point_type=point_type,
        required_terms=(),
        acceptable_variants=(AcceptableVariant("v", _REF),),
        max_score=score,
        textbook_source_refs=(_REF,),
        answer_key_authority="official_answer",
        conjunction_group=conjunction_group,
    )


def test_flaw_correction_needs_both_members_for_full_score():
    find = _point("flaw", score=1.0, conjunction_group="g1", point_type=PointType.CONJUNCTION_MEMBER)
    fix = _point("fix", score=1.0, conjunction_group="g1", point_type=PointType.CONJUNCTION_MEMBER)
    points = [find, fix]

    # 找错不改正 → 该合取组 0 分(不是 1 分)。
    assert score_conjunction_group(points, {"flaw"}) == 0.0
    assert score_conjunction_group(points, {"fix"}) == 0.0
    # 找错∧改正 → 满分 2.0。
    assert score_conjunction_group(points, {"flaw", "fix"}) == 2.0


def test_cross_question_same_group_name_not_merged():
    # 2026-07-09 Codex 对抗核证伪:两道题各有一对同名 group "g",全局合并会把
    # Q1 已挣的分拖成 0。作用域按 (qid,sub_qid,group) 后,命中 Q1 两半 → Q1 满分。
    q1a = _point("q1a", score=0.5, conjunction_group="g", qid="Q1::s1")
    q1b = _point("q1b", score=0.5, conjunction_group="g", qid="Q1::s1")
    q2a = _point("q2a", score=0.5, conjunction_group="g", qid="Q2::s1")
    q2b = _point("q2b", score=0.5, conjunction_group="g", qid="Q2::s1")
    pts = [q1a, q1b, q2a, q2b]
    assert score_conjunction_group(pts, {"q1a", "q1b"}) == 1.0  # Q1 full, Q2 zero
    assert score_conjunction_group(pts, {"q1a", "q1b", "q2a", "q2b"}) == 2.0


def test_duplicate_point_id_fails_closed():
    # 2026-07-09 Codex 对抗核证伪:重复 point_id 会让一次命中满足两个成员。
    with pytest.raises(ScoringPointError):
        score_conjunction_group([_point("DUP"), _point("DUP")], {"DUP"})


def test_non_conjunction_points_score_independently():
    a = _point("a", score=1.0)
    b = _point("b", score=2.0)
    assert score_conjunction_group([a, b], {"a"}) == 1.0
    assert score_conjunction_group([a, b], {"a", "b"}) == 3.0
    assert score_conjunction_group([a, b], set()) == 0.0


def test_mixed_flat_and_conjunction():
    flat = _point("flat", score=1.0)
    g_find = _point("gf", score=1.0, conjunction_group="g")
    g_fix = _point("gx", score=1.0, conjunction_group="g")
    points = [flat, g_find, g_fix]
    # flat hit but conjunction incomplete → only flat's 1.0
    assert score_conjunction_group(points, {"flat", "gf"}) == 1.0
    # everything hit → 3.0
    assert score_conjunction_group(points, {"flat", "gf", "gx"}) == 3.0


# ── RTG5: generated option → real scoring-point binding ────────────────────────


def test_correct_option_must_bind_a_real_scoring_point():
    points = [_point("sp_1"), _point("sp_2")]
    good = {
        "correct_options": [{"source_scoring_point_id": "sp_1"}],
        "distractors": [{"error_code": "E_OMIT"}],
    }
    validate_source_scoring_point_id(good, points)  # does not raise


def test_correct_option_binding_nonexistent_point_is_rejected():
    points = [_point("sp_1")]
    bad = {
        "correct_options": [{"source_scoring_point_id": "sp_FAKE"}],
        "distractors": [{"error_code": "E_OMIT"}],
    }
    with pytest.raises(SourceBindingError):
        validate_source_scoring_point_id(bad, points)


def test_distractor_must_not_bind_scoring_point_and_must_have_error_code():
    points = [_point("sp_1")]
    with pytest.raises(SourceBindingError):
        validate_source_scoring_point_id(
            {
                "correct_options": [{"source_scoring_point_id": "sp_1"}],
                "distractors": [{"source_scoring_point_id": "sp_1"}],
            },
            points,
        )
    with pytest.raises(SourceBindingError):
        validate_source_scoring_point_id(
            {
                "correct_options": [{"source_scoring_point_id": "sp_1"}],
                "distractors": [{"text": "no error code"}],
            },
            points,
        )
