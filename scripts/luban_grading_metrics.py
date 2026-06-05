#!/usr/bin/env python3
"""Ordinal grading-agreement metrics (QWK + exact/adjacent agreement + normalized delta).

Local deterministic implementation — NO sklearn / numpy dependency. These are
DIAGNOSTIC metrics for the grading shadow eval. They DO NOT replace the
zero-tolerance hard gates (exact_required_major_violation==0, unsupported_positive==0,
penalty_major==0, evidence_span traceable). directional/shadow.
"""
from __future__ import annotations

HIT_ORD = {"miss": 0, "partial": 1, "hit": 2}


def _ord(hit) -> int:
    return HIT_ORD.get(str(hit), 0)


def quadratic_weighted_kappa(a: list[int], b: list[int], n_cat: int = 3) -> float:
    """QWK for two equal-length ordinal label lists over categories 0..n_cat-1.

    QWK = 1 - sum(W*O) / sum(W*E), W_ij = (i-j)^2/(n_cat-1)^2.
    Returns 1.0 for perfect agreement; 0.0 when no pairs (degenerate).
    """
    if not a or len(a) != len(b):
        return 0.0
    n = len(a)
    denom_w = (n_cat - 1) ** 2 or 1
    O = [[0] * n_cat for _ in range(n_cat)]
    for x, y in zip(a, b):
        O[x][y] += 1
    row = [sum(O[i]) for i in range(n_cat)]
    col = [sum(O[i][j] for i in range(n_cat)) for j in range(n_cat)]
    num = den = 0.0
    for i in range(n_cat):
        for j in range(n_cat):
            w = (i - j) ** 2 / denom_w
            e = row[i] * col[j] / n
            num += w * O[i][j]
            den += w * e
    if den == 0:
        # no expected disagreement (one rater constant) -> perfect iff observed agree
        return 1.0 if all(O[i][j] == 0 for i in range(n_cat) for j in range(n_cat) if i != j) else 0.0
    return round(1 - num / den, 4)


def exact_agreement(a: list[int], b: list[int]) -> float:
    if not a:
        return 0.0
    return round(sum(1 for x, y in zip(a, b) if x == y) / len(a), 4)


def adjacent_agreement(a: list[int], b: list[int]) -> float:
    """fraction within 1 ordinal level (|x-y|<=1)."""
    if not a:
        return 0.0
    return round(sum(1 for x, y in zip(a, b) if abs(x - y) <= 1) / len(a), 4)


def qwk_for_pairs(pred_hits: list, gold_hits: list, n_cat: int = 3) -> float:
    return quadratic_weighted_kappa([_ord(h) for h in pred_hits], [_ord(h) for h in gold_hits], n_cat)


def agreement_block(pred_hits: list, gold_hits: list) -> dict:
    a = [_ord(h) for h in pred_hits]
    b = [_ord(h) for h in gold_hits]
    return {
        "points": len(a),
        "qwk": quadratic_weighted_kappa(a, b),
        "exact_agreement": exact_agreement(a, b),
        "adjacent_agreement": adjacent_agreement(a, b),
    }
