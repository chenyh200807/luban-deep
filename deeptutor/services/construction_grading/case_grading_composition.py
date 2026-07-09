"""案例题轻练判分**组合适配器 on-ramp** —— 从教研验收的采分点集推导小问级判分 kind。

这是"接线进生产判官"的**组合层第一步**,且**不碰任何生产判分模块**(deep_question /
rubric_grader)——它只读采分点结构、输出该小问该走哪个确定性引擎。生产调用点(在
`_grade_one_case_v1` 里按 owner 拍的落点/灰度调用组合层)仍是 §3 red line + owner 门,
不在本模块。

**kind 派生(单一权威,不造第二套)**:优先教研在 review.json 标的 `practice_grading_kind`
(CALC_DAG/SET_MEMBERSHIP/CPM_CRITICAL_PATH);未标则从采分点已有结构字段派生
——`conjunction_group`→CONJUNCTION、`ordering_group`→ORDERING;都没有 → None(默认
采分点点选/漏点补全走 coverage,不进 dispatch 引擎)。这落实了 Q3 数据结论:policy 不判 kind,
结构字段 + 最小 tag 才判。

**spec 来源的诚实边界(为什么组合层还不能整条自动跑)**:dispatch 各 kind 需的 spec 来源不同——
ORDERING/CONJUNCTION 的 spec 可从采分点+review 结构建;但 CALC_DAG(公式 DAG)/
CPM_CRITICAL_PATH(活动网络)/SET_MEMBERSHIP(集合矩阵)的结构化 spec **不在采分点 rubric、
也不在 review.json**,需一个尚未建立的**结构化命题作者产物**(见接线提案 §依赖)。所以本模块
只做能确定性做的 kind 派生;spec 装配待作者来源就绪 + owner 拍落点。Deterministic: no LLM.
"""
from __future__ import annotations

from collections.abc import Sequence

from deeptutor.services.construction_grading.case_light_practice_contract import (
    LubanCaseScoringPoint,
    PracticeGradingKind,
)


class CompositionError(ValueError):
    """采分点集自相矛盾,无法确定单一判分 kind(如同一小问标了两种显式 kind)。"""


def derive_grading_kind(
    points: Sequence[LubanCaseScoringPoint],
) -> PracticeGradingKind | None:
    """推导**一个小问**(同 sub_no 的采分点集)该走哪个确定性判分 kind。

    - 教研显式标的 `practice_grading_kind` 优先(同小问必须一致,冲突 → CompositionError);
    - 未标则从结构字段派生:有 `conjunction_group` → CONJUNCTION;有 `ordering_group` → ORDERING;
    - 都没有 → None(采分点点选/漏点补全默认走 coverage,不进 dispatch 引擎)。

    纯函数,不判分、不改采分点、不碰生产判官。
    """
    explicit = {p.practice_grading_kind for p in points if p.practice_grading_kind is not None}
    if len(explicit) > 1:
        raise CompositionError(
            f"同一小问采分点标了多个 practice_grading_kind: {sorted(k.value for k in explicit)}"
        )
    if explicit:
        return next(iter(explicit))

    if any(p.conjunction_group for p in points):
        return PracticeGradingKind.CONJUNCTION
    if any(p.ordering_group for p in points):
        return PracticeGradingKind.ORDERING
    return None


# 各 kind 的 dispatch spec 能否从"采分点 + review.json 结构"确定性装配(无需新作者产物)。
# True=组合层可自动建 spec;False=需结构化命题作者产物(公式 DAG / 活动网络 / 集合矩阵),尚无来源。
SPEC_BUILDABLE_FROM_REVIEW: dict[PracticeGradingKind, bool] = {
    PracticeGradingKind.CONJUNCTION: True,   # FlawCorrectionPair ← conjunction_group 两成员
    PracticeGradingKind.ORDERING: True,      # OrderingSpec ← ordering_group + review 次序
    PracticeGradingKind.SET_MEMBERSHIP: False,  # 需集合矩阵(每 bin 的合法集合)——作者产物
    PracticeGradingKind.CALC_DAG: False,        # 需公式 DAG(steps+formula+depends_on)——作者产物
    PracticeGradingKind.CPM_CRITICAL_PATH: False,  # 需活动网络(工期+紧前)——作者产物
}


__all__ = ["CompositionError", "derive_grading_kind", "SPEC_BUILDABLE_FROM_REVIEW"]
