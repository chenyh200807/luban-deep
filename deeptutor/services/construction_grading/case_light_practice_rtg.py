"""Case light-practice Post-generation gates — RTG1–RTG8 (deterministic) + RTG9 seam.

运行时出题门(runtime-generation-gate,`RTG*`)—— 命名一律 `RTG`,**不得**沿用
`compiler_pipeline` 的 artifact 签发门 `G0-G8`(会串线),也不是 `deterministic_prescreen`
(学生答案判分前置)。这套门是 §1限制③ 的 **Post-gen 确定性门**:LLM 生成一道轻练题后,
在给学员看之前,用**不调 LLM 的确定性规则**把不安全的题拒掉。

设计纪律(§1限制③):
  - 先便宜后贵、先硬拒(BLOCK)后软处理(SOFT_FAIL→可疑队列)。
  - 任一 BLOCK → 调用方重生成 ≤2 次 → 仍失败降级/人工队列。
  - RTG9(干扰"其实也对")确定性判不了,是**异源模型**的活 —— 本纯模块只留接口
    (`RTG9_NEEDS_CROSS_SOURCE`),不在此实现,也**只分流不当真值**。
  - 门若因缺输入没跑到,显式标 ``NOT_EXERCISED``,**绝不静默当 PASS**
    (反 [[release-gate-runner-attest-only-what-it-exercises]] 的假绿)。

红线:采分点是唯一真值。RTG5/RTG8 是"生成忠实采分点硬门"——生成错了,确定性判分
只会稳定地按错题判,所以必须在出题这一关拦住。

Deterministic and pure: no LLM, no network, no DB.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
from deeptutor.services.construction_grading.case_light_practice_contract import (
    LubanCaseScoringPoint,
)

# Generator emits this literal when it cannot confidently pick an error code;
# RTG3 routes it to human review instead of blocking (§1限制③ RTG3).
NEEDS_REVIEW = "NEEDS_REVIEW"

# RTG8 faithfulness: token-overlap ratio floor when neither text is a substring
# of the other. Deterministic, char/term based — no embeddings.
_RTG8_OVERLAP_FLOOR = 0.6
# RTG6 shape band: a distractor's length must sit within [0.3x, 3x] of the
# correct option it parallels (rough parity — cheap heuristic, SOFT only).
_RTG6_MIN_RATIO = 0.3
_RTG6_MAX_RATIO = 3.0
# RTG6 near-correct: a distractor whose characters are ≥85% CONTAINED in a correct
# option is a near-synonym paraphrase of the right answer (e.g. 分层剥离 vs 分层剥开 —
# 差一字). Deterministic gates can't judge full semantic equivalence (that is RTG9's
# cross-source job), but this high-containment subset is a cheap deterministic
# pre-filter → 可疑队列. Surfaced by a 2026-07-09 live DeepSeek run.
_RTG6_NEAR_CORRECT_CONTAINMENT = 0.85


class GateStatus(str, Enum):
    PASS = "pass"
    BLOCK = "block"  # hard reject → regenerate / drop
    SOFT_FAIL = "soft_fail"  # → 可疑队列 (suspicious queue)
    NEEDS_HUMAN = "needs_human"  # → 人工队列 (RTG3 NEEDS_REVIEW)
    NOT_EXERCISED = "not_exercised"  # input absent — NEVER silently a pass


class Verdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    SOFT_FAIL = "soft_fail"
    NEEDS_HUMAN = "needs_human"


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    detail: str = ""


@dataclass(frozen=True)
class PostGenReport:
    verdict: Verdict
    results: tuple[GateResult, ...]

    def failures(self) -> list[GateResult]:
        return [r for r in self.results if r.status in (GateStatus.BLOCK, GateStatus.SOFT_FAIL, GateStatus.NEEDS_HUMAN)]


# ── Normalization (RTG1 collision / RTG2 dedup) ────────────────────────────────

_PUNCT_WS_RE = re.compile(r"[\s　\.,,。;;:：、!!??()()\"'“”‘’\-—_/\\]+")
# Symbol-equivalence: fold full/half-width and common construction synonyms of
# equality/units so "≠字面同" cannot slip a collision through.
_SYMBOL_FOLD = {
    "㎡": "m2",
    "m²": "m2",
    "＝": "=",
    "％": "%",
}


def normalize(text: str) -> str:
    """NFKC + strip whitespace/punctuation + symbol fold → collision key."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    for a, b in _SYMBOL_FOLD.items():
        s = s.replace(a, b)
    s = _PUNCT_WS_RE.sub("", s)
    return s.casefold()


def _tokens(text: str) -> set[str]:
    return set(normalize(text)) if text else set()


def _overlap_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _containment_in(inner: str, outer: str) -> float:
    """Fraction of ``inner``'s characters that also appear in ``outer`` (directional).

    Catches a near-synonym of the correct answer whose extra distinguishing chars
    are few — Jaccard misses this when the correct option carries a long tail
    (e.g. a parenthetical); containment normalizes by the shorter (distractor) side.
    """
    ti, to = _tokens(inner), _tokens(outer)
    if not ti:
        return 0.0
    return len(ti & to) / len(ti)


# ── The gates ──────────────────────────────────────────────────────────────────


def run_post_gen_gates(
    item: Mapping[str, object],
    points: Sequence[LubanCaseScoringPoint],
    *,
    error_code_candidates: Iterable[str] | None = None,
    consistent_point_ids: Iterable[str] | None = None,
) -> PostGenReport:
    """Run RTG1–RTG8 on a generated item; return an aggregate verdict.

    ``item`` shape (dict): ``{"stem": str, "correct_options": [{"text", "source_scoring_point_id"}],
    "distractors": [{"text", "error_code"}]}``.
    ``points`` = the atomized scoring points of THIS (sub)question (whitelist-gated).
    ``error_code_candidates`` = the pre-screened code subset for this topic (RTG4; optional).
    ``consistent_point_ids`` = point_ids the Pre-gen 一致性闸 judged同一小问 (RTG7; optional).
    """
    results: list[GateResult] = []
    correct = list(item.get("correct_options") or [])
    distractors = list(item.get("distractors") or [])
    point_by_id = {p.point_id: p for p in points}

    # RTG5 — structure + option→truth binding (HARD). Cheapest structural gate first.
    r5 = _rtg5_structure(correct, distractors, point_by_id)
    results.append(r5)

    # RTG1 — distractor ≠ any correct after normalization (HARD; 撞车根除).
    results.append(_rtg1_collision(correct, distractors))

    # RTG2 — distractors pairwise distinct (HARD).
    results.append(_rtg2_distractor_dedup(distractors))

    # RTG3 — error_code ∈ registry (NEEDS_REVIEW → human) (HARD/HUMAN).
    results.append(_rtg3_error_code_registry(distractors))

    # RTG8 — correct option faithful to its bound scoring point原文 (HARD; 反编造).
    results.append(_rtg8_faithfulness(correct, point_by_id))

    # RTG4 — error_code ∈ this-topic candidate subset (SOFT).
    results.append(_rtg4_candidate_subset(distractors, error_code_candidates))

    # RTG6 — length/shape parity + no substring / cheap negation (SOFT).
    results.append(_rtg6_shape(correct, distractors))

    # RTG7 — all referenced points in the consistency-screened group (HARD when known).
    results.append(_rtg7_consistency(correct, consistent_point_ids))

    return PostGenReport(verdict=_aggregate(results), results=tuple(results))


def _aggregate(results: Sequence[GateResult]) -> Verdict:
    statuses = {r.status for r in results}
    if GateStatus.BLOCK in statuses:
        return Verdict.BLOCK
    if GateStatus.NEEDS_HUMAN in statuses:
        return Verdict.NEEDS_HUMAN
    if GateStatus.SOFT_FAIL in statuses:
        return Verdict.SOFT_FAIL
    return Verdict.PASS


def _rtg5_structure(correct, distractors, point_by_id) -> GateResult:
    if not correct:
        return GateResult("RTG5", GateStatus.BLOCK, "no correct_options")
    if not distractors:
        return GateResult("RTG5", GateStatus.BLOCK, "no distractors (need 1 correct + N distractors)")
    for opt in correct:
        text = (opt or {}).get("text")
        sid = (opt or {}).get("source_scoring_point_id")
        if not text:
            return GateResult("RTG5", GateStatus.BLOCK, "correct option missing text")
        if sid not in point_by_id:
            return GateResult("RTG5", GateStatus.BLOCK, f"source_scoring_point_id {sid!r} not a real point of this question")
    for dis in distractors:
        if not (dis or {}).get("text"):
            return GateResult("RTG5", GateStatus.BLOCK, "distractor missing text")
        if (dis or {}).get("source_scoring_point_id"):
            return GateResult("RTG5", GateStatus.BLOCK, "distractor must not bind a real scoring point")
    return GateResult("RTG5", GateStatus.PASS)


def _rtg1_collision(correct, distractors) -> GateResult:
    correct_keys = {normalize(o.get("text")) for o in correct if o.get("text")}
    for dis in distractors:
        if normalize(dis.get("text")) in correct_keys:
            return GateResult("RTG1", GateStatus.BLOCK, f"distractor equals a correct option after normalization: {dis.get('text')!r}")
    return GateResult("RTG1", GateStatus.PASS)


def _rtg2_distractor_dedup(distractors) -> GateResult:
    seen: set[str] = set()
    for dis in distractors:
        k = normalize(dis.get("text"))
        if k in seen:
            return GateResult("RTG2", GateStatus.BLOCK, f"duplicate distractor after normalization: {dis.get('text')!r}")
        seen.add(k)
    return GateResult("RTG2", GateStatus.PASS)


def _rtg3_error_code_registry(distractors) -> GateResult:
    needs_human = False
    for dis in distractors:
        code = str(dis.get("error_code") or "").strip()
        if code == NEEDS_REVIEW:
            needs_human = True
            continue
        if code not in ERROR_CODE_REGISTRY:
            return GateResult("RTG3", GateStatus.BLOCK, f"error_code {code!r} not in ERROR_CODE_REGISTRY")
    if needs_human:
        return GateResult("RTG3", GateStatus.NEEDS_HUMAN, "distractor error_code=NEEDS_REVIEW → 人工队列")
    return GateResult("RTG3", GateStatus.PASS)


def _rtg8_faithfulness(correct, point_by_id) -> GateResult:
    for opt in correct:
        sid = opt.get("source_scoring_point_id")
        point = point_by_id.get(sid)
        if point is None:
            # RTG5 already blocks this; defensively treat as block here too.
            return GateResult("RTG8", GateStatus.BLOCK, f"correct option binds unknown point {sid!r}")
        ct, st = normalize(opt.get("text")), normalize(point.statement)
        faithful = ct in st or st in ct or _overlap_ratio(opt.get("text"), point.statement) >= _RTG8_OVERLAP_FLOOR
        if not faithful:
            return GateResult(
                "RTG8",
                GateStatus.BLOCK,
                f"correct option not faithful to scoring point原文 (overlap<{_RTG8_OVERLAP_FLOOR}): {opt.get('text')!r} vs {point.statement!r}",
            )
    return GateResult("RTG8", GateStatus.PASS)


def _rtg4_candidate_subset(distractors, error_code_candidates) -> GateResult:
    if error_code_candidates is None:
        return GateResult("RTG4", GateStatus.NOT_EXERCISED, "no pre-screened candidate subset supplied")
    candidates = set(error_code_candidates)
    for dis in distractors:
        code = str(dis.get("error_code") or "").strip()
        if code == NEEDS_REVIEW:
            continue
        if code not in candidates:
            return GateResult("RTG4", GateStatus.SOFT_FAIL, f"error_code {code!r} outside pre-screened candidates → 可疑队列")
    return GateResult("RTG4", GateStatus.PASS)


def _rtg6_shape(correct, distractors) -> GateResult:
    ref_len = max((len(normalize(o.get("text"))) for o in correct if o.get("text")), default=0)
    correct_norm = [normalize(o.get("text")) for o in correct if o.get("text")]
    for dis in distractors:
        dn = normalize(dis.get("text"))
        if not dn:
            continue
        # length parity band
        if ref_len and not (_RTG6_MIN_RATIO * ref_len <= len(dn) <= _RTG6_MAX_RATIO * ref_len):
            return GateResult("RTG6", GateStatus.SOFT_FAIL, f"distractor length {len(dn)} outside [{_RTG6_MIN_RATIO},{_RTG6_MAX_RATIO}]×{ref_len} → 可疑")
        # substring of a correct option (too-close paraphrase)
        for cn in correct_norm:
            if dn and dn in cn:
                return GateResult("RTG6", GateStatus.SOFT_FAIL, "distractor is a substring of a correct option → 可疑")
        # near-correct: distractor chars ≥85% contained in a correct option = 近义改写
        # of the right answer (deterministic subset of RTG9). 2026-07-09 live-surfaced.
        for opt in correct:
            if _containment_in(dis.get("text"), opt.get("text")) >= _RTG6_NEAR_CORRECT_CONTAINMENT:
                return GateResult(
                    "RTG6",
                    GateStatus.SOFT_FAIL,
                    f"distractor ~近义 correct option (containment≥{_RTG6_NEAR_CORRECT_CONTAINMENT}) → 可疑/异源: {dis.get('text')!r}",
                )
        # cheap negation ("不"/"无"/"未" prepended is a lazy flip)
        raw = str(dis.get("text") or "")
        if raw and raw.lstrip()[:1] in ("不", "无", "未", "非"):
            return GateResult("RTG6", GateStatus.SOFT_FAIL, "distractor looks like a cheap negation flip → 可疑")
    return GateResult("RTG6", GateStatus.PASS)


def _rtg7_consistency(correct, consistent_point_ids) -> GateResult:
    if consistent_point_ids is None:
        return GateResult("RTG7", GateStatus.NOT_EXERCISED, "no consistency-screen group supplied (Pre-gen 一致性闸 is P1)")
    consistent = set(consistent_point_ids)
    for opt in correct:
        sid = opt.get("source_scoring_point_id")
        if sid not in consistent:
            return GateResult("RTG7", GateStatus.BLOCK, f"referenced point {sid!r} outside the consistency-screened group (欠切分 tell)")
    return GateResult("RTG7", GateStatus.PASS)


# RTG9 — cross-source seam. Deterministic gates CANNOT decide "其实也对/语义等价";
# only a DIFFERENT-vendor model may triage similarity-over-threshold candidates,
# and it only SORTS (可疑队列), never becomes ground truth. Left unimplemented here.
RTG9_NEEDS_CROSS_SOURCE = "RTG9 requires a cross-source (non-DeepSeek) model — triage only, not ground truth"


__all__ = [
    "NEEDS_REVIEW",
    "GateStatus",
    "Verdict",
    "GateResult",
    "PostGenReport",
    "normalize",
    "run_post_gen_gates",
    "RTG9_NEEDS_CROSS_SOURCE",
]
