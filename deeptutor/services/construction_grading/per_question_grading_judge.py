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

_PGO_SUB_TYPE_TO_POLICY = {
    "flaw_correction": "qualitative",
    "exceptions": "qualitative",
    "calculation": "calculation",
    "enumeration": "list",
    "free_text_point": "qualitative",
}

_VERDICT_CREDIT = {
    HIT: 1.0,
    PARTIAL: 0.5,
    MISS: 0.0,
    CONTRADICTION: 0.0,
}

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


def _supporting_terms_by_point(contract: dict[str, Any]) -> dict[str, list[str]]:
    terms_by_point: dict[str, list[str]] = {}
    for cite in contract.get("supporting_citations") or []:
        if not isinstance(cite, dict):
            continue
        if cite.get("official_score_allowed") is not False:
            continue
        if cite.get("anchor_verified") is False:
            continue
        if not cite.get("chunk_id"):
            continue
        point_id = str(cite.get("point_id") or "")
        term = str(cite.get("term") or "").strip()
        if not point_id or not term:
            continue
        terms_by_point.setdefault(point_id, [])
        if term not in terms_by_point[point_id]:
            terms_by_point[point_id].append(term)
    return terms_by_point


def runtime_points_from_grading_contract(
    contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Adapt the PGO contract into the runtime point shape without minting scores.

    The official total remains the only numeric score authority. These points are
    adjudication instructions: official slice + coarse policy + verified supporting
    terms. Per-point ``score``/``max_score`` stay null by construction.
    """
    supporting_terms = _supporting_terms_by_point(contract)
    runtime_points: list[dict[str, Any]] = []
    for sp in contract.get("scoring_points") or []:
        point_id = str(sp.get("point_id") or "")
        sub_type = str(sp.get("sub_type") or "free_text_point")
        required_terms = supporting_terms.get(point_id, [])
        policy_type = _PGO_SUB_TYPE_TO_POLICY.get(sub_type, "qualitative")
        if required_terms and policy_type == "qualitative":
            policy_type = "exact_required"
        runtime_points.append(
            {
                "point_id": point_id,
                "official_slice": sp.get("official_slice") or "",
                "knowledge_point": sp.get("official_slice") or "",
                "policy_type": policy_type,
                "sub_type": sub_type,
                "required_terms": list(required_terms),
                "term_authority": (
                    "textbook_cited_supporting_only"
                    if required_terms
                    else "none"
                ),
                "score": None,
                "max_score": None,
            }
        )
    return runtime_points


def verdict_coverage_awarded_score(
    point_verdicts: dict[str, str],
    contract: dict[str, Any],
    *,
    partial_ratio: float = 0.5,
) -> dict[str, Any]:
    """Award ``official_total_score * verdict coverage`` for null-score PGO points.

    This is the Stage 2 single-authority arithmetic: one official numeric total,
    verdict-count coverage for distribution, and no per-point score summation.
    """
    total = contract.get("official_total_score")
    if not isinstance(total, int | float):
        return {
            "awarded_score": 0.0,
            "max_score": 0.0,
            "coverage": 0.0,
            "credited_points": 0.0,
            "total_points": len(contract.get("scoring_points") or []),
            "score_authority": "official_total_x_verdict_coverage",
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "blockers": ["missing_official_total_score"],
        }
    points = contract.get("scoring_points") or []
    if not points:
        return {
            "awarded_score": 0.0,
            "max_score": float(total),
            "coverage": 0.0,
            "credited_points": 0.0,
            "total_points": 0,
            "score_authority": "official_total_x_verdict_coverage",
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "blockers": ["no_scoring_points"],
        }

    credit_weights = dict(_VERDICT_CREDIT)
    credit_weights[PARTIAL] = float(partial_ratio)
    credited = sum(
        credit_weights.get(point_verdicts.get(str(sp.get("point_id"))), 0.0)
        for sp in points
    )
    coverage = credited / len(points)
    awarded = float(total) * coverage
    return {
        "awarded_score": round(awarded, 4),
        "max_score": float(total),
        "coverage": round(coverage, 4),
        "credited_points": round(credited, 4),
        "total_points": len(points),
        "score_authority": "official_total_x_verdict_coverage",
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "blockers": [],
    }


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
    "runtime_points_from_grading_contract",
    "verdict_coverage_awarded_score",
    "detect_over_credit",
]
