"""score_assigner 单测:验证踩点给分逻辑(R1-R7)与封顶判分。"""
from __future__ import annotations

from deeptutor.services.source_compiler.score_assigner import (
    AUTHORITY,
    assign_scores,
    default_sub_q_total,
    judge,
)


def test_non_list_units_each_one_point():
    # R3:非列举单元各 1.0(3 个判断,小题满分 5;踩点池 3 可 < 满分)
    out = assign_scores(
        [{"type": "判断"}, {"type": "判断"}, {"type": "判断"}], sub_q_total=5.0
    )
    assert out["scores"] == [1.0, 1.0, 1.0]
    assert out["authority"] == AUTHORITY


def test_list_absorbs_remainder():
    # R4②:1 判断(1.0)+ 1 列举,小题满分 5 → 列举吸收余额 4.0
    out = assign_scores(
        [{"type": "判断"}, {"type": "列举"}], sub_q_total=5.0
    )
    assert out["scores"] == [1.0, 4.0]


def test_multi_list_split_remainder():
    # 无非列举、3 个列举、小题满分 6 → 各吸收 6/3 = 2.0
    out = assign_scores(
        [{"type": "列举"}, {"type": "列举"}, {"type": "列举"}], sub_q_total=6.0
    )
    assert out["scores"] == [2.0, 2.0, 2.0]


def test_more_units_than_total_halves():
    # R5:8 个单元 > 小题满分 5.5 → 每单元 0.5
    pts = [{"type": "列举"}] * 8
    out = assign_scores(pts, sub_q_total=5.5)
    assert out["scores"] == [0.5] * 8


def test_judge_caps_at_sub_q_total():
    # R7 封顶:[1.0, 4.0],命中全部,满分 5 → 5.0;只命中列举 → 4.0
    scores = [1.0, 4.0]
    assert judge(scores, [True, True], 5.0) == 5.0
    assert judge(scores, [False, True], 5.0) == 4.0
    assert judge(scores, [False, False], 5.0) == 0.0


def test_judge_caps_when_pool_exceeds_total():
    # 给分池 > 满分(踩点制),全命中仍封顶到满分
    scores = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]  # 6 点池
    assert judge(scores, [True] * 6, 5.0) == 5.0


def test_default_total_buckets():
    assert default_sub_q_total(2) == 3.0
    assert default_sub_q_total(4) == 5.0
    assert default_sub_q_total(6) == 6.0
    assert default_sub_q_total(8) == 7.0


def test_empty_points():
    out = assign_scores([], sub_q_total=5.0)
    assert out["scores"] == []
    assert out["authority"] == AUTHORITY
