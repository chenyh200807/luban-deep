"""判断改正题的合取门判分(找错 ∧ 改正)+ 诊断状态。

§3 指出:生产判官把 `flaw_correction` 降级成 `qualitative`,转 runtime 时丢掉
pairing/flaw_span/correction_span,最后按 coverage 给分 —— **合取约束丢失**
(找错不改正也能拿分)。本模块**在 light-practice 判分域内**恢复合取门:

  一个判断改正采分点 = **一对**共享同一 `conjunction_group` 的原子采分点:
    · 找错子(flaw sub-point)—— 学员是否识别出"哪里错"
    · 改正子(correction sub-point)—— 学员是否给出"正确做法"
  **两半都命中才给该对满分;缺任一 → 0 分**(§4 红线:只找错不改正不得满分)。

不造第二套判分权威:采分点真值仍是 `LubanCaseScoringPoint`;合取评分复用已测的
`score_conjunction_group`;本模块只加(1)pair 结构与校验、(2)**诊断状态**
(flaw_only / correction_only / miss / full)—— 后者驱动"诊断挂采分点/误解"。
不改生产 `per_question_grading_judge`(review-only 边界)。official_score_allowed=false。

Deterministic: no LLM. 采分点"命中与否"由上游判定(确定性 required_terms 或 LLM
batch_judge);本门只做"两半命中 → 合取给分 + 诊断"的确定性组合。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from deeptutor.services.construction_grading.case_light_practice_contract import (
    LubanCaseScoringPoint,
    PointType,
    score_conjunction_group,
)


class FlawCorrectionStatus(str, Enum):
    FULL = "full"  # 找错 ∧ 改正 都对 → 满分
    FLAW_ONLY = "flaw_only"  # 找到错但改正不对 → 0(合取门)
    CORRECTION_ONLY = "correction_only"  # 给了正确做法但没指出错在哪 → 0
    MISS = "miss"  # 都没命中 → 0


class FlawCorrectionError(ValueError):
    """Raised when a flaw/correction pair is malformed."""


@dataclass(frozen=True)
class FlawCorrectionPair:
    """判断改正采分点对:找错子 + 改正子,共享一个 conjunction_group。"""

    flaw: LubanCaseScoringPoint
    correction: LubanCaseScoringPoint

    def __post_init__(self) -> None:
        f, c = self.flaw, self.correction
        if f.point_id == c.point_id:
            raise FlawCorrectionError("flaw and correction must be distinct points")
        # A pair must be two halves of ONE (sub)question — a flaw from Q1 paired with a
        # correction from Q2 is not a judgment-correction point (2026-07-09 Codex 对抗核证伪).
        if (f.qid, f.sub_qid, f.sub_no) != (c.qid, c.sub_qid, c.sub_no):
            raise FlawCorrectionError(
                f"flaw/correction must belong to the same (qid, sub_qid, sub_no): "
                f"flaw=({f.qid},{f.sub_qid},{f.sub_no}) correction=({c.qid},{c.sub_qid},{c.sub_no})"
            )
        if f.conjunction_group is None or f.conjunction_group != c.conjunction_group:
            raise FlawCorrectionError(
                f"flaw/correction must share a non-null conjunction_group "
                f"(flaw={f.conjunction_group!r} correction={c.conjunction_group!r})"
            )
        if f.point_type is not PointType.CONJUNCTION_MEMBER or c.point_type is not PointType.CONJUNCTION_MEMBER:
            raise FlawCorrectionError("both flaw and correction must be point_type=合取子")
        if f.max_score <= 0 or c.max_score <= 0:
            raise FlawCorrectionError(
                f"flaw/correction must carry positive max_score (flaw={f.max_score}, correction={c.max_score})"
            )

    @property
    def combined_max_score(self) -> float:
        return self.flaw.max_score + self.correction.max_score


@dataclass(frozen=True)
class FlawCorrectionVerdict:
    status: FlawCorrectionStatus
    awarded_score: float
    conjunction_group: str


def judge_flaw_correction(
    pair: FlawCorrectionPair, *, flaw_hit: bool, correction_hit: bool
) -> FlawCorrectionVerdict:
    """合取门:两半都命中 → 满分;否则 0。诊断状态标出缺了哪半(驱动误解反馈)。"""
    # 合取评分委托给已测的 score_conjunction_group(单一来源,不重复合取逻辑):
    # flaw 与 correction 在同一 conjunction_group,两半都命中才给该组满分,否则 0。
    hits = set()
    if flaw_hit:
        hits.add(pair.flaw.point_id)
    if correction_hit:
        hits.add(pair.correction.point_id)
    awarded = score_conjunction_group([pair.flaw, pair.correction], hits)

    if flaw_hit and correction_hit:
        status = FlawCorrectionStatus.FULL
    elif flaw_hit:
        status = FlawCorrectionStatus.FLAW_ONLY
    elif correction_hit:
        status = FlawCorrectionStatus.CORRECTION_ONLY
    else:
        status = FlawCorrectionStatus.MISS
    return FlawCorrectionVerdict(
        status=status,
        awarded_score=awarded,
        conjunction_group=pair.flaw.conjunction_group or "",
    )


__all__ = [
    "FlawCorrectionStatus",
    "FlawCorrectionError",
    "FlawCorrectionPair",
    "FlawCorrectionVerdict",
    "judge_flaw_correction",
]
