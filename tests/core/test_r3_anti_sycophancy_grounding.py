"""R3 质疑轮 sycophancy 附和编造叙事 —— 单一 GROUNDING_CLAUSE 反附和约束。

g5 T10:学生编"罚款2%~8%",bot 附和并自创"2020年修订把4%调到8%"叙事自圆其说。
根因:GROUNDING_CLAUSE 原本约束"事实主张来源",但没显式禁止"附和学生未核断言"。
修法(单点,不在 directive 再加):在单一 GROUNDING_CLAUSE 加"学生口头断言不属三来源,
不得附和/背书/为圆学生数字编造支撑叙事"。
"""
from __future__ import annotations

from deeptutor.core import grounding


def test_grounding_clause_forbids_sycophantic_endorsement() -> None:
    c = grounding.GROUNDING_CLAUSE
    # 学生断言不算来源 + 不附和 + 不为圆数字编叙事
    assert "学生" in c and "断言" in c
    assert "附和" in c
    assert "不属于上述三个来源" in c
    # 既有反编造约束仍在(防漂移)
    assert "不得编造或伪造具体的规范编号" in c
    assert "题面" in c and "证据" in c


def test_grounding_clause_single_source_unchanged_pointer() -> None:
    """仍是单一权威,prepend_grounding 引用同一常量(防各处抄)。"""
    assert grounding.prepend_grounding("X").startswith(grounding.GROUNDING_CLAUSE)
