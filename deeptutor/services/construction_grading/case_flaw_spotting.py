"""AI 错答挑错判分 —— 把"泛泛而谈"变负面示例,直击"写一堆不得分"(§1.5B)。

交互:给学员一段"泛泛而谈/漏采分点"的错答(来自采分点的 `common_wrong_expressions`),
问"这段答案**漏了哪些采分点**?" 学员点选;确定性判分 = 学员选的漏点集合 == 该错答
真实漏掉的采分点集合。

**真实漏点是确定性算的,不是 LLM 判**:复用 `diagnose_photo`(把错答当识别文本喂进去)
→ `missed_point_ids` 即该错答未覆盖的采分点。采分点是唯一真值,不造第二套。
official_score_allowed=False(练习/诊断)。Deterministic: no LLM。
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from deeptutor.services.construction_grading.case_light_practice_contract import (
    LubanCaseScoringPoint,
)
from deeptutor.services.construction_grading.case_photo_diagnosis import (
    PhotoExtraction,
    RecognizedSpan,
    diagnose_photo,
)

OFFICIAL_SCORE_ALLOWED = False


def compute_expression_gaps(
    expression: str, points: Sequence[LubanCaseScoringPoint]
) -> frozenset[str]:
    """一段错答**真实漏掉**的采分点 id 集合(确定性:复用 diagnose_photo 的采分点匹配)。
    命中=required_terms/acceptable_variants 出现;漏=没出现 → 就是该错答不得分之处。"""
    extraction = PhotoExtraction((RecognizedSpan(str(expression), (0, 0, 0, 0), 1.0),))
    result = diagnose_photo(extraction, points)
    return frozenset(result.missed_point_ids)


@dataclass(frozen=True)
class FlawSpottingResult:
    correct: bool
    expected_missing: frozenset[str]  # 该错答真实漏掉的采分点
    student_missing: frozenset[str]   # 学员认为漏掉的
    official_score_allowed: bool


def grade_flaw_spotting(
    expression: str,
    points: Sequence[LubanCaseScoringPoint],
    student_identified_missing: Iterable[str],
) -> FlawSpottingResult:
    """判学员"挑错":选出的漏点集合精确等于该错答真实漏掉的采分点集合 → correct。"""
    expected = compute_expression_gaps(expression, points)
    student = frozenset(str(x) for x in student_identified_missing)
    return FlawSpottingResult(
        correct=student == expected,
        expected_missing=expected,
        student_missing=student,
        official_score_allowed=OFFICIAL_SCORE_ALLOWED,
    )


__all__ = [
    "OFFICIAL_SCORE_ALLOWED",
    "FlawSpottingResult",
    "compute_expression_gaps",
    "grade_flaw_spotting",
]
