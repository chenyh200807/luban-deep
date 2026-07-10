"""荷载组合集合判分金标测试。

金标 = 真题 EXAM_1A434020_P0009_01::E2 模板支撑体系荷载组合(编译库 exact_required 直读):
  底面模板承载力 {G1,G2,G3,Q1} · 支架立杆承载力 {G1,G2,G3,Q4}
  整体稳定组合一 {G1,G2,G3,Q1,Q3} · 整体稳定组合二 {G1,G2,G3,Q1,Q4}
判分 = 每计算项集合精确相等;多选/漏选/换项皆 0。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deeptutor.services.construction_grading.case_load_combination import (
    SCHEMA_ID,
    SetMembershipError,
    SetMembershipPoint,
    grade_set_membership,
)

_REGISTRY = Path(__file__).resolve().parents[3] / "contracts" / "schema_registry.yaml"


def _golden():
    return [
        SetMembershipPoint("底面模板承载力", frozenset({"G1", "G2", "G3", "Q1"}), 1.0),
        SetMembershipPoint("支架立杆承载力", frozenset({"G1", "G2", "G3", "Q4"}), 1.0),
        SetMembershipPoint("整体稳定组合一", frozenset({"G1", "G2", "G3", "Q1", "Q3"}), 1.0),
        SetMembershipPoint("整体稳定组合二", frozenset({"G1", "G2", "G3", "Q1", "Q4"}), 1.0),
    ]


def test_dataclass_fields_match_registry():
    payload = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
    entry = next(e for e in payload["tier2_canonical_contracts"] if e.get("name") == SCHEMA_ID)
    assert list(SetMembershipPoint.__dataclass_fields__.keys()) == list(entry["canonical_fields"])


def test_all_bins_exact_match_full_score():
    student = {
        "底面模板承载力": ["G1", "G2", "G3", "Q1"],
        "支架立杆承载力": ["G1", "G2", "G3", "Q4"],
        "整体稳定组合一": ["G1", "G2", "G3", "Q1", "Q3"],
        "整体稳定组合二": ["G1", "G2", "G3", "Q1", "Q4"],
    }
    r = grade_set_membership(_golden(), student)
    assert r.total_awarded == 4.0
    assert all(v.correct for v in r.verdicts.values())


def test_extra_or_missing_load_is_zero_for_that_bin():
    student = {
        "底面模板承载力": ["G1", "G2", "G3", "Q1", "Q2"],   # 多选 Q2 → 0
        "支架立杆承载力": ["G1", "G2", "G3"],                # 漏 Q4 → 0
        "整体稳定组合一": ["G1", "G2", "G3", "Q1", "Q4"],    # 换项(Q4 应为 Q3)→ 0
        "整体稳定组合二": ["G1", "G2", "G3", "Q1", "Q4"],    # 正确
    }
    r = grade_set_membership(_golden(), student)
    assert r.total_awarded == 1.0
    assert r.verdicts["底面模板承载力"].correct is False
    assert r.verdicts["支架立杆承载力"].correct is False
    assert r.verdicts["整体稳定组合一"].correct is False
    assert r.verdicts["整体稳定组合二"].correct is True


def test_missing_bin_and_order_and_normalization():
    # 未答某 bin → 0;集合无序;全角/大小写/空格归一
    student = {
        "底面模板承载力": ["Ｑ1", " g3 ", "G2", "G1"],  # 全角Q/小写g/空格 → 归一后 == 官方
        # 其余 bin 未答
    }
    r = grade_set_membership(_golden(), student)
    assert r.verdicts["底面模板承载力"].correct is True
    assert r.verdicts["支架立杆承载力"].correct is False  # 未答
    assert r.total_awarded == 1.0


# ── 2026-07-09 Codex 对抗核回归 ──────────────────────────────────────────────


def test_dict_selection_does_not_score_full():
    # dict 只迭代 key、忽略 False 值 → 曾把"全未选"判满分。现 fail-closed 判错。
    student = {"底面模板承载力": {"G1": False, "G2": False, "G3": False, "Q1": False}}
    r = grade_set_membership(_golden(), student)
    assert r.verdicts["底面模板承载力"].correct is False


def test_str_selection_fails_closed():
    # 字符串会被逐字符拆 → 明确 fail-closed 判错(不逐字符匹配)。
    r = grade_set_membership(_golden(), {"底面模板承载力": "G1G2G3Q1"})
    assert r.verdicts["底面模板承载力"].correct is False


def test_non_setmembershippoint_rejected():
    from types import SimpleNamespace
    fake = SimpleNamespace(bin="底面模板承载力", correct_set={"G1"}, points=1.0)  # 绕过 __post_init__
    with pytest.raises(SetMembershipError):
        grade_set_membership([fake], {"底面模板承载力": ["G1"]})


def test_zero_width_chars_normalized():
    # 零宽/BOM 视觉同一 chip 应判等
    student = {"底面模板承载力": ["G1", "G2", "G3", "Q​1"]}  # Q1 带零宽空格
    r = grade_set_membership(_golden(), student)
    assert r.verdicts["底面模板承载力"].correct is True


def test_empty_bin_name_rejected():
    with pytest.raises(SetMembershipError):
        SetMembershipPoint("", frozenset({"G1"}), 1.0)
    with pytest.raises(SetMembershipError):
        SetMembershipPoint("   ", frozenset({"G1"}), 1.0)


def test_malformed_points_raise():
    with pytest.raises(SetMembershipError):  # 空集合
        SetMembershipPoint("x", frozenset(), 1.0)
    with pytest.raises(SetMembershipError):  # 负分
        SetMembershipPoint("x", frozenset({"G1"}), -1.0)
    with pytest.raises(SetMembershipError):  # 重复 bin
        grade_set_membership(
            [SetMembershipPoint("x", frozenset({"G1"}), 1.0),
             SetMembershipPoint("x", frozenset({"G2"}), 1.0)],
            {"x": ["G1"]},
        )
