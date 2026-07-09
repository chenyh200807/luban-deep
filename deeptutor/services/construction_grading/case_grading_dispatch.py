"""案例题轻练判分分发器 —— 按题型把学员作答路由到对的确定性判分引擎。

**只路由,不判分**:采分点真值仍在各引擎(CPM/DAG+ECF/合取门/集合/排序),本模块不造
第二判分权威、不改写任何采分点;只做"哪种题型用哪个引擎"的调度 + 归一成统一结果。
`official_score_allowed` 恒 False(诊断/候选证据,金标 kappa 转正前不铸官方分,§4 红线)。

这是把 7 个孤立判分引擎拼成"一道题→对的判分"的胶水层。Deterministic: no LLM。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from deeptutor.services.construction_grading.case_calc_dag import grade_calc_dag
from deeptutor.services.construction_grading.case_cpm_solver import (
    CpmResult,
    matches_critical_path,
)
from deeptutor.services.construction_grading.case_flaw_correction import (
    FlawCorrectionPair,
    judge_flaw_correction,
)
from deeptutor.services.construction_grading.case_load_combination import grade_set_membership
from deeptutor.services.construction_grading.case_process_ordering import (
    OrderingSpec,
    grade_ordering,
)


class DispatchError(ValueError):
    """Unknown grading kind or malformed payload for the routed engine."""


class PracticeGradingKind(str, Enum):
    CALC_DAG = "calc_dag"                # 造价链式 / 挣值(DAG+ECF)
    SET_MEMBERSHIP = "set_membership"    # 荷载组合(集合精确匹配)
    ORDERING = "ordering"                # 工序排序(拓扑序)
    CONJUNCTION = "conjunction"          # 判断改正(合取门)
    CPM_CRITICAL_PATH = "cpm_critical_path"  # 网络计划关键线路点选


@dataclass(frozen=True)
class DispatchResult:
    kind: PracticeGradingKind
    awarded: float
    max_score: float
    official_score_allowed: bool  # 恒 False
    detail: Any  # 底层引擎的原始结果(证据/逐项)


def dispatch_grade(
    kind: PracticeGradingKind,
    *,
    spec: Any,
    student: Any,
    points: float | None = None,
) -> DispatchResult:
    """把学员作答按 ``kind`` 路由到对应判分引擎,归一成 DispatchResult。

    payload 约定(spec / student):
      - CALC_DAG:        spec=(steps, given_inputs)        student=student_values(dict)
      - SET_MEMBERSHIP:  spec=[SetMembershipPoint,…]       student=selections(dict bin→chips)
      - ORDERING:        spec=OrderingSpec                 student=学员排列(序列);需 points
      - CONJUNCTION:     spec=FlawCorrectionPair           student=(flaw_hit, correction_hit)
      - CPM_CRITICAL_PATH: spec=CpmResult                  student=学员选的线路(序列);需 points
    """
    if kind is PracticeGradingKind.CALC_DAG:
        try:
            steps, given = spec
        except (TypeError, ValueError) as e:
            raise DispatchError(f"CALC_DAG spec must be (steps, given_inputs): {e}") from e
        r = grade_calc_dag(steps, given, student)
        return DispatchResult(kind, r.total_awarded, sum(s.points for s in steps), False, r)

    if kind is PracticeGradingKind.SET_MEMBERSHIP:
        r = grade_set_membership(spec, student)
        return DispatchResult(kind, r.total_awarded, sum(p.points for p in spec), False, r)

    if kind is PracticeGradingKind.ORDERING:
        if not isinstance(spec, OrderingSpec):
            raise DispatchError("ORDERING spec must be an OrderingSpec")
        if points is None:
            raise DispatchError("ORDERING requires `points`")
        r = grade_ordering(spec, student)
        return DispatchResult(kind, points if r.correct else 0.0, float(points), False, r)

    if kind is PracticeGradingKind.CONJUNCTION:
        if not isinstance(spec, FlawCorrectionPair):
            raise DispatchError("CONJUNCTION spec must be a FlawCorrectionPair")
        try:
            flaw_hit, correction_hit = student
        except (TypeError, ValueError) as e:
            raise DispatchError(f"CONJUNCTION student must be (flaw_hit, correction_hit): {e}") from e
        r = judge_flaw_correction(spec, flaw_hit=bool(flaw_hit), correction_hit=bool(correction_hit))
        return DispatchResult(kind, r.awarded_score, spec.combined_max_score, False, r)

    if kind is PracticeGradingKind.CPM_CRITICAL_PATH:
        if not isinstance(spec, CpmResult):
            raise DispatchError("CPM_CRITICAL_PATH spec must be a CpmResult")
        if points is None:
            raise DispatchError("CPM_CRITICAL_PATH requires `points`")
        correct = matches_critical_path(spec, student)
        return DispatchResult(kind, points if correct else 0.0, float(points), False, {"correct": correct})

    raise DispatchError(f"unknown grading kind: {kind!r}")


__all__ = ["DispatchError", "PracticeGradingKind", "DispatchResult", "dispatch_grade"]
