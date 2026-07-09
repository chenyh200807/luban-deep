"""认→写阶梯:铁律(点选永不写掌握)+ 延时窗口 + 升档门 + 成人分层(§1 限制④)。"""
from __future__ import annotations

from deeptutor.services.construction_grading.case_recognition_to_writing import (
    LadderTier,
    can_advance_tier,
    can_write_mastery,
    is_production_tier,
    target_tier,
)


def test_iron_law_point_select_never_writes_mastery():
    # 铁律:档1 竞争性点选,无论"通过"、无论延时,都不写掌握。
    assert can_write_mastery(
        production_tier=LadderTier.COMPETITIVE_SELECT,
        production_passed=True, delayed_retest_passed=True, retest_gap_days=5,
    ) is False


def test_mastery_requires_production_and_delayed_retest_both_pass():
    kw = dict(production_tier=LadderTier.HALF_WRITE, retest_gap_days=5)
    assert can_write_mastery(production_passed=True, delayed_retest_passed=True, **kw) is True
    assert can_write_mastery(production_passed=True, delayed_retest_passed=False, **kw) is False
    assert can_write_mastery(production_passed=False, delayed_retest_passed=True, **kw) is False


def test_delayed_retest_must_be_within_3_to_7_days():
    kw = dict(production_tier=LadderTier.FULL_WRITE, production_passed=True, delayed_retest_passed=True)
    assert can_write_mastery(retest_gap_days=2, **kw) is False   # 太早=即时复述,虚假信心
    assert can_write_mastery(retest_gap_days=3, **kw) is True
    assert can_write_mastery(retest_gap_days=7, **kw) is True
    assert can_write_mastery(retest_gap_days=8, **kw) is False   # 太晚,超窗


def test_is_production_tier():
    assert is_production_tier(LadderTier.COMPETITIVE_SELECT) is False
    assert is_production_tier(LadderTier.HALF_WRITE) is True
    assert is_production_tier(LadderTier.FULL_WRITE) is True


def test_advance_requires_delayed_production_not_point_select():
    # 升档只由当前档隔 3-7 天延时空手产出通过兑现。
    assert can_advance_tier(LadderTier.COMPETITIVE_SELECT, delayed_production_passed=True, gap_days=5) is True
    assert can_advance_tier(LadderTier.COMPETITIVE_SELECT, delayed_production_passed=False, gap_days=5) is False
    assert can_advance_tier(LadderTier.HALF_WRITE, delayed_production_passed=True, gap_days=1) is False  # 窗外
    assert can_advance_tier(LadderTier.FULL_WRITE, delayed_production_passed=True, gap_days=5) is False  # 已顶档


def test_adult_layering_target_tier():
    # A 高频大分×gap 大 → 档4
    assert target_tier(exam_frequency_high=True, score_weight_high=True, recognition_write_gap_large=True) == LadderTier.FULL_WRITE
    # C gap 小 → 档1 脸熟够
    assert target_tier(exam_frequency_high=True, score_weight_high=True, recognition_write_gap_large=False) == LadderTier.COMPETITIVE_SELECT
    # B/默认 → 档2
    assert target_tier(exam_frequency_high=False, score_weight_high=True, recognition_write_gap_large=True) == LadderTier.HALF_WRITE
    assert target_tier(exam_frequency_high=False, score_weight_high=False, recognition_write_gap_large=True) == LadderTier.HALF_WRITE
