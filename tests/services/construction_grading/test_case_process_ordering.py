"""工序排序判分金标测试。

金标 = 真题 EXAM_1A434000_P0010_02::E3 工艺流程(编译库 list 直读的官方序):
  清理表面 → 支设模板 → 洒水湿润 → 涂抹混凝土界面剂
线性唯一序:精确等于官方序才对;任一交换违反紧前约束 → 错。
多合法拓扑序:满足全部紧前约束即对。
"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_process_ordering import (
    OrderingError,
    OrderingSpec,
    grade_ordering,
)

_FLOW = ["清理表面", "支设模板", "洒水湿润", "涂抹混凝土界面剂"]


def test_golden_linear_exact_order_correct():
    spec = OrderingSpec.from_sequence(_FLOW)
    assert grade_ordering(spec, _FLOW).correct is True


def test_linear_swap_is_wrong():
    spec = OrderingSpec.from_sequence(_FLOW)
    swapped = ["支设模板", "清理表面", "洒水湿润", "涂抹混凝土界面剂"]
    r = grade_ordering(spec, swapped)
    assert r.correct is False
    assert "紧前" in r.reason


def test_missing_or_extra_activity_is_wrong():
    spec = OrderingSpec.from_sequence(_FLOW)
    assert grade_ordering(spec, _FLOW[:3]).correct is False           # 漏一步
    assert grade_ordering(spec, _FLOW + ["养护"]).correct is False    # 多一步


def test_duplicate_in_student_order_is_wrong():
    spec = OrderingSpec.from_sequence(_FLOW)
    dup = ["清理表面", "清理表面", "洒水湿润", "涂抹混凝土界面剂"]
    assert grade_ordering(spec, dup).correct is False


def test_multiple_valid_topological_orders():
    # 偏序:A、B 都必须在 C 前,但 A/B 之间无约束 → [A,B,C] 与 [B,A,C] 都合法。
    spec = OrderingSpec(activities=("A", "B", "C"), precedence=frozenset({("A", "C"), ("B", "C")}))
    assert grade_ordering(spec, ["A", "B", "C"]).correct is True
    assert grade_ordering(spec, ["B", "A", "C"]).correct is True
    assert grade_ordering(spec, ["C", "A", "B"]).correct is False  # C 不能在 A/B 前


def test_normalization_whitespace_fullwidth():
    spec = OrderingSpec.from_sequence(_FLOW)
    noisy = [" 清理表面 ", "支设模板", "洒水湿润", "涂抹混凝土界面剂"]
    assert grade_ordering(spec, noisy).correct is True


def test_malformed_spec_raises():
    with pytest.raises(OrderingError):  # 重复工序
        OrderingSpec(activities=("A", "A"), precedence=frozenset())
    with pytest.raises(OrderingError):  # 紧前引用未知工序
        OrderingSpec(activities=("A", "B"), precedence=frozenset({("A", "Z")}))
    with pytest.raises(OrderingError):  # 自环
        OrderingSpec(activities=("A",), precedence=frozenset({("A", "A")}))
    with pytest.raises(OrderingError):  # 空序列
        OrderingSpec.from_sequence([])
