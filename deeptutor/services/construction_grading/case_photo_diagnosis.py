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

# 否定前缀:命中词紧前窗口内出现这些字 → 视为否定语境,不算命中(2026-07-09 Codex
# 对抗核:"没有分层剥开"曾误命中"分层剥开")。启发式;诊断非评分,宁保守不送分。
_NEGATIONS = frozenset("不没未无非")
_NEG_WINDOW = 4


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


def _negated(norm_text: str, idx: int) -> bool:
    """命中位置 ``idx`` 紧前 ``_NEG_WINDOW`` 字内是否有否定字(否定语境不算命中)。"""
    return any(c in _NEGATIONS for c in norm_text[max(0, idx - _NEG_WINDOW):idx])


def _best_span(term: str, extraction: PhotoExtraction, normalize_fn: Callable[[str], str]) -> RecognizedSpan | None:
    """含 ``term`` 的**最高置信** span(否定语境跳过);无则 None。多 span 命中不再取第一个。"""
    nt = normalize_fn(term)
    if not nt:
        return None
    best: RecognizedSpan | None = None
    for s in extraction.spans:
        ns = normalize_fn(s.text)
        idx = ns.find(nt)
        if idx == -1 or _negated(ns, idx):
            continue
        if best is None or s.confidence > best.confidence:
            best = s
    return best


def diagnose_photo(
    extraction: PhotoExtraction,
    points: Sequence[LubanCaseScoringPoint],
    *,
    normalize_fn: Callable[[str], str] = normalize,
) -> PhotoDiagnosisResult:
    """对每个采分点确定性判命中(2026-07-09 Codex 对抗核加固):

      - **required_terms 全需**(都出现才算命中,避免"只写部分要素"假阳送分);
        **acceptable_variants 任一**(替代全句表达,任一出现即命中)。
      - **否定守卫**:命中词紧前窗口有否定字(不/没/未/无/非)→ 不算命中。
      - **最高置信 span**:多 span 含命中词时取置信度最高的(而非第一个)作证据,
        避免题干复述/低质量 span 抢占证据回显。

    只吃 ``PhotoExtraction``(文本+span),绝不吃图 —— 解耦即构造。诊断非评分。"""
    diagnoses: list[PointDiagnosis] = []
    for p in points:
        matched_term: str | None = None
        evidence: RecognizedSpan | None = None

        required = [t for t in p.required_terms if t]
        variants = [v.term for v in p.acceptable_variants if v.term]

        # ① required_terms 全需:每个都要有(否定守卫的)最高置信 span
        if required:
            spans = {t: _best_span(t, extraction, normalize_fn) for t in required}
            if all(spans.values()):
                # 证据取全体命中里置信度最高的那段;matched_term 记该词
                matched_term, evidence = max(
                    ((t, s) for t, s in spans.items()), key=lambda ts: ts[1].confidence
                )
        # ② 未凭 required 命中 → acceptable_variants 任一命中即可
        if evidence is None:
            for term in variants:
                s = _best_span(term, extraction, normalize_fn)
                if s is not None:
                    matched_term, evidence = term, s
                    break

        diagnoses.append(
            PointDiagnosis(
                point_id=p.point_id,
                matched=evidence is not None,
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
