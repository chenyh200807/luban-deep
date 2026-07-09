"""拍照纸笔诊断骨架 —— 读图↔判分**解耦** + 证据回显(§1.5D)。

红线:**读图与评分解耦**(识别错只修前链,不漂评分);**诊断非评分**,
`official_score_allowed=False`;信任靠"识别哪几个词/漏哪几点",不靠长解释黑箱。

解耦即构造:本模块只做 OCR **之后**的确定性环节 —— 关键实体标准化 → 采分点确定性
匹配 → 证据回显。`diagnose_photo` **只吃抽取文本(`PhotoExtraction`),绝不吃图**。
OCR/VLM 抽取(PaddleOCR/腾讯云/百度手写)是**上游注入边界**,不在本模块(生产
photo_answer 做 OCR;本骨架不碰它 —— review-only)。

判分 = f(识别文本)。识别错 → 学员纠正识别文本(修前链)→ 重跑 diagnose 即正确,
评分逻辑一字未变。这就是解耦:文本可独立纠错,评分只是文本的确定性函数。

采分点是唯一真值:匹配用采分点的 required_terms / acceptable_variants 确定性判命中,
不让 LLM 越权当 ground truth。Deterministic: no LLM, no network, no image bytes here.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from deeptutor.services.construction_grading.case_light_practice_contract import (
    LubanCaseScoringPoint,
)
from deeptutor.services.construction_grading.case_light_practice_rtg import normalize

OFFICIAL_SCORE_ALLOWED = False  # 诊断非评分(结构性常量)


@dataclass(frozen=True)
class RecognizedSpan:
    """OCR 识别出的一段文本 + 它在原图的区域 + 置信度(证据回显用)。"""

    text: str
    region: tuple[int, int, int, int]  # 原图 bbox (x, y, w, h) — 供回显定位/纠错
    confidence: float  # 0..1

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence {self.confidence} out of [0,1]")


@dataclass(frozen=True)
class PhotoExtraction:
    """OCR 抽取结果(解耦边界)。评分只消费它,不消费图像字节。"""

    spans: tuple[RecognizedSpan, ...]

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.spans)


@dataclass(frozen=True)
class PointDiagnosis:
    point_id: str
    matched: bool
    matched_term: str | None  # 命中了采分点的哪个词/变体
    evidence_span: RecognizedSpan | None  # 命中出现在哪段识别文本 + 原图区域(回显纠错)
    confidence: float  # = 命中所在 span 的置信度(未命中为 0)


@dataclass(frozen=True)
class PhotoDiagnosisResult:
    diagnoses: tuple[PointDiagnosis, ...]
    official_score_allowed: bool  # 恒 False —— 拍照诊断永不铸官方分

    @property
    def matched_point_ids(self) -> list[str]:
        return [d.point_id for d in self.diagnoses if d.matched]

    @property
    def missed_point_ids(self) -> list[str]:
        return [d.point_id for d in self.diagnoses if not d.matched]


def _terms_for(point: LubanCaseScoringPoint) -> list[str]:
    """采分点的可接受命中词:required_terms + acceptable_variants 术语。"""
    terms = list(point.required_terms)
    terms.extend(v.term for v in point.acceptable_variants)
    return [t for t in terms if t]


def diagnose_photo(
    extraction: PhotoExtraction,
    points: Sequence[LubanCaseScoringPoint],
    *,
    normalize_fn: Callable[[str], str] = normalize,
) -> PhotoDiagnosisResult:
    """对每个采分点,在识别文本里确定性找 required_terms/acceptable_variants;命中则记
    证据 span(原图区域 + 置信度)供回显纠错。**只吃文本,不吃图** —— 解耦即构造。"""
    diagnoses: list[PointDiagnosis] = []
    for p in points:
        terms = _terms_for(p)
        matched_term: str | None = None
        evidence: RecognizedSpan | None = None
        # 找第一个命中的词及其所在 span(确定性,子串归一化匹配)
        for term in terms:
            nt = normalize_fn(term)
            if not nt:
                continue
            span = next((s for s in extraction.spans if nt in normalize_fn(s.text)), None)
            if span is not None:
                matched_term, evidence = term, span
                break
        matched = evidence is not None
        diagnoses.append(
            PointDiagnosis(
                point_id=p.point_id,
                matched=matched,
                matched_term=matched_term,
                evidence_span=evidence,
                confidence=(evidence.confidence if evidence else 0.0),
            )
        )
    return PhotoDiagnosisResult(diagnoses=tuple(diagnoses), official_score_allowed=OFFICIAL_SCORE_ALLOWED)


__all__ = [
    "OFFICIAL_SCORE_ALLOWED",
    "RecognizedSpan",
    "PhotoExtraction",
    "PointDiagnosis",
    "PhotoDiagnosisResult",
    "diagnose_photo",
]
