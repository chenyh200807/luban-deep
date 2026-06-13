"""Judge-side deterministic logic for the per-question grading contract A/B (review-only).

No LLM, no network, no DB write. This is the deterministic half of the case-question
A/B that tests KnowQL Phase B's thesis: forcing the judge to adjudicate every atomic
official point separately 摁死 the measured ~20% over-credit (a high score while an
official point is missed).

It provides three pure pieces the A/B harness composes:

1. ``make_controlled_student_answers`` — builds student answers with EXACT ground truth
   by keeping/dropping verbatim atomic official slices, so "did the student cover point
   X" is known by construction (no human labelling needed for the over-credit measure).
2. ``oracle_verdicts`` / ``candidate_coverage_score`` — a perfect-judge oracle + a
   review-only candidate coverage score (fraction of atomic official points hit). The
   coverage score is a signal over the official checklist, NOT a minted per-point score.
3. ``detect_over_credit`` — the deployable Phase B gate: a high score with any
   missed/contradicted official point is structurally invalid (the validator the codex
   memory called "score≥95 + any miss → invalid").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HIT = "hit"
PARTIAL = "partial"
MISS = "miss"
CONTRADICTION = "contradiction"

# Only a full HIT credits an atomic official point. partial/miss/contradiction do not.
_CREDITED = frozenset({HIT})
_UNMET = frozenset({MISS, CONTRADICTION})

# A score at/above this fraction is "high" — used to describe the trust-collapse failure
# (near-full marks despite a missed sub-question) in human terms.
OVER_CREDIT_HIGH_THRESHOLD = 0.95

# Over-credit is a score that MATERIALLY exceeds actual coverage — not merely a high score
# with a miss. Covering 23/24 official points and scoring 0.958 is honest proportional
# credit; claiming 1.0 while only 0.8 is covered (a missed sub-question) is over-credit.
# The gap must exceed this margin to count (tolerates rounding / one partial credit).
OVER_CREDIT_GAP_MARGIN = 0.1


@dataclass(frozen=True)
class ControlledAnswer:
    """A student answer with known ground truth (which atomic points it covers)."""

    label: str
    student_answer: str
    covered_point_ids: tuple[str, ...]
    missing_point_ids: tuple[str, ...]


def _iter_points(obj_or_contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Atomic points from either a per-question OBJECT (nested sub_questions) or a
    CONTRACT (flat scoring_points). Returns dicts with at least ``point_id``."""
    if obj_or_contract.get("scoring_points") is not None and not obj_or_contract.get(
        "sub_questions"
    ):
        return list(obj_or_contract["scoring_points"])
    points: list[dict[str, Any]] = []
    for sub in obj_or_contract.get("sub_questions") or []:
        for p in sub.get("scoring_points") or []:
            points.append(p)
    return points


def make_controlled_student_answers(obj: dict[str, Any]) -> list[ControlledAnswer]:
    """Build controlled student answers with exact ground truth from a per-question object.

    Each atomic official slice is verbatim, so an answer that includes a slice should be
    HIT on that point and one that omits it MISS. Three cases per question:
      * ``complete`` — every atomic point present (expect no miss);
      * ``drop_last`` — one atomic point omitted (the classic "missed sub-question");
      * ``keep_first_half`` — only the first half of points present.
    The answer text is the kept atomic slices joined — terse, but exact ground truth.
    """
    points = _iter_points(obj)
    point_ids = [str(p.get("point_id")) for p in points]
    slices = [str(p.get("atomic_official_slice") or "") for p in points]
    n = len(point_ids)

    def _mk(label: str, keep: list[int]) -> ControlledAnswer:
        keep_set = set(keep)
        covered = tuple(point_ids[i] for i in sorted(keep_set))
        missing = tuple(pid for i, pid in enumerate(point_ids) if i not in keep_set)
        answer = "\n".join(slices[i] for i in sorted(keep_set))
        return ControlledAnswer(label, answer, covered, missing)

    cases = [_mk("complete", list(range(n)))]
    if n >= 2:
        cases.append(_mk("drop_last", list(range(n - 1))))
        cases.append(_mk("keep_first_half", list(range((n + 1) // 2))))
    return cases


def oracle_verdicts(contract: dict[str, Any], answer: ControlledAnswer) -> dict[str, str]:
    """Perfect-judge oracle (deterministic): HIT iff the point is in the answer's covered
    set, else MISS. Validates the harness end-to-end without an LLM and is arm-B's upper
    bound."""
    covered = set(answer.covered_point_ids)
    return {
        str(sp.get("point_id")): (HIT if str(sp.get("point_id")) in covered else MISS)
        for sp in contract.get("scoring_points") or []
    }


def candidate_coverage_score(
    point_verdicts: dict[str, str], contract: dict[str, Any]
) -> float:
    """Review-only candidate score = fraction of atomic official points fully HIT.

    NOT a minted per-point authority — a coverage signal over the official checklist
    (per-point scores have no canonical truth; the official key only gives the total).
    """
    points = contract.get("scoring_points") or []
    if not points:
        return 0.0
    credited = sum(
        1 for sp in points if point_verdicts.get(str(sp.get("point_id"))) in _CREDITED
    )
    return credited / len(points)


def detect_over_credit(
    *,
    score_pct: float,
    point_verdicts: dict[str, str],
    contract: dict[str, Any],
    high_threshold: float = OVER_CREDIT_HIGH_THRESHOLD,
    gap_margin: float = OVER_CREDIT_GAP_MARGIN,
) -> dict[str, Any]:
    """Deployable Phase B gate: a score that MATERIALLY exceeds the coverage its OWN
    per-point verdicts justify is self-inconsistent over-credit (invalid → regrade).

    Verdict-based, so it works in production where ground truth is unknown — the judge's
    claimed ``score_pct`` must be consistent with how many official points it actually
    marked HIT. Covering 23/24 and scoring 0.958 is honest (gap ≈ 0); claiming 1.0 while
    its verdicts hit only 0.8 is over-credit (gap 0.2 > margin). ``high_threshold`` is
    retained only to annotate the human-readable "near-full marks despite a miss" case.
    """
    coverage = candidate_coverage_score(point_verdicts, contract)
    missed = [
        str(sp.get("point_id"))
        for sp in contract.get("scoring_points") or []
        if point_verdicts.get(str(sp.get("point_id"))) in _UNMET
    ]
    gap = round(score_pct - coverage, 4)
    over = bool(gap > gap_margin)
    near_full_despite_miss = bool(score_pct >= high_threshold and missed and over)
    return {
        "over_credit": over,
        "invalid": over,
        "score_pct": score_pct,
        "coverage_from_verdicts": round(coverage, 4),
        "score_coverage_gap": gap,
        "miss_count": len(missed),
        "missed_point_ids": missed,
        "near_full_marks_despite_miss": near_full_despite_miss,
        "reason": "score exceeds verdict-justified coverage" if over else "ok",
    }


__all__ = [
    "HIT",
    "PARTIAL",
    "MISS",
    "CONTRADICTION",
    "OVER_CREDIT_HIGH_THRESHOLD",
    "OVER_CREDIT_GAP_MARGIN",
    "ControlledAnswer",
    "make_controlled_student_answers",
    "oracle_verdicts",
    "candidate_coverage_score",
    "detect_over_credit",
]
