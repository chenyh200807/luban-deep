"""认→写阶梯 —— 铁律 + 升档/掌握写入门 + 成人分层(§1 限制④)。

**铁律**:"会写"只能由**产出**兑现,永远不能由**点选正确率**判定(点选=再认,迁移只到
再认;点选流畅=虚假信心)。本模块把这条铁律焊成确定性门:

  - 4 档阶梯:档1 竞争性点选(认·底座,**非产出**)/ 档2 半写关键词 / 档3 句式积木 /
    档4 成段书写(档2-4 = 空手产出)。
  - **掌握态写入门**:掌握态只由「**空手产出(档≥2)通过 × 隔 3-7 天延时复测通过**」双通过
    才写入(机制⑥)。点选(档1)正确率**永不**写掌握。
  - **升档门**:升下一档只由「当前档隔 3-7 天延时空手产出通过」兑现,不由点选分(机制③)。
  - **成人分层**:A(高频大分 × 认-写 gap 大)→逼到档4;C(gap 小)→停档1 脸熟够;
    其余/默认 → 档2 术语默写(省成人时间)。

Deterministic: no LLM, no network, no DB. 纯规则,判分/掌握写入的红线在此收口。
"""
from __future__ import annotations

from enum import IntEnum

# 延时复测窗口(机制③⑥):隔 3-7 天空手产出才算"跨过虚假信心"。
DELAY_MIN_DAYS = 3
DELAY_MAX_DAYS = 7


class LadderTier(IntEnum):
    COMPETITIVE_SELECT = 1  # 竞争性点选(认·底座,零打字)—— 非产出
    HALF_WRITE = 2          # 半写关键词(cued recall,认→写跨越点)
    SENTENCE_BLOCK = 3      # 句式积木拼句
    FULL_WRITE = 4          # 成段书写(唯一同构考场)


_PRODUCTION_FLOOR = LadderTier.HALF_WRITE  # 档≥2 才是"空手产出";档1 只是再认


class LadderError(TypeError):
    """Raised when a tier argument is not a LadderTier (裸 int/bool 会绕过铁律门)。"""


def _require_tier(tier: object, name: str) -> LadderTier:
    """Fail-closed:非 LadderTier(裸 int 5 / bool / None …)一律拒绝。
    2026-07-09 Codex 对抗核证伪:``is_production_tier(5)`` 曾用 IntEnum 比较绕过铁律,
    让非法档位写进掌握态。铁律门的入参必须是真档位枚举。"""
    if not isinstance(tier, LadderTier):
        raise LadderError(f"{name} must be a LadderTier, got {tier!r} ({type(tier).__name__})")
    return tier


def is_production_tier(tier: LadderTier) -> bool:
    """该档是否"空手产出"(档≥2);档1 竞争性点选是再认,不是产出。"""
    return _require_tier(tier, "tier") >= _PRODUCTION_FLOOR


def _delay_ok(gap_days: int) -> bool:
    return DELAY_MIN_DAYS <= gap_days <= DELAY_MAX_DAYS


def can_write_mastery(
    *,
    production_tier: LadderTier,
    production_passed: bool,
    delayed_retest_passed: bool,
    retest_gap_days: int,
) -> bool:
    """掌握态是否可写入。**铁律**:必须是空手产出(档≥2)通过 × 隔 3-7 天延时复测通过 双通过。
    点选(档1)无论正确率多高都**不写**掌握(返回 False)。"""
    if not is_production_tier(production_tier):
        return False  # 铁律:点选是再认,永不写掌握
    return production_passed and delayed_retest_passed and _delay_ok(retest_gap_days)


def can_advance_tier(
    current: LadderTier,
    *,
    delayed_production_passed: bool,
    gap_days: int,
) -> bool:
    """能否升下一档。升档只由「当前档隔 3-7 天延时**空手产出**通过」兑现,不由点选分。
    档1→档2 也要求一次延时产出(把再认掺进提取后,用产出兑现跨越)。已在档4 不再升。"""
    if _require_tier(current, "current") >= LadderTier.FULL_WRITE:
        return False
    return delayed_production_passed and _delay_ok(gap_days)


def next_tier(current: LadderTier) -> LadderTier | None:
    """当前档的**下一档**(只升一档,杜绝跳档);已在档4 返回 None。
    调用方升档必须用它推进,不得自行跳到任意档(2026-07-09 Codex 对抗核:模块需能表达
    '只加一档',否则调用方可从档1 直接跳档4)。"""
    _require_tier(current, "current")
    if current >= LadderTier.FULL_WRITE:
        return None
    return LadderTier(int(current) + 1)


def target_tier(
    *,
    exam_frequency_high: bool,
    score_weight_high: bool,
    recognition_write_gap_large: bool,
) -> LadderTier:
    """成人分层(考频×分值×认-写 gap):A 高频大分×gap 大 → 档4;gap 小(脸熟够)→ 档1;
    其余/默认 → 档2 术语默写(省成人时间,默认每考点到档2)。"""
    if exam_frequency_high and score_weight_high and recognition_write_gap_large:
        return LadderTier.FULL_WRITE  # A 类:付档4 成本
    if not recognition_write_gap_large:
        return LadderTier.COMPETITIVE_SELECT  # C 类:gap 小,停档1 脸熟
    return LadderTier.HALF_WRITE  # B/默认:停档2 术语默写


__all__ = [
    "DELAY_MIN_DAYS",
    "DELAY_MAX_DAYS",
    "LadderTier",
    "LadderError",
    "is_production_tier",
    "can_write_mastery",
    "can_advance_tier",
    "next_tier",
    "target_tier",
]
