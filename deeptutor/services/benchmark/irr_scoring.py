"""Small, dependency-free agreement scoring for Luban golden labels.

This module intentionally reports process reproducibility, not human IRR.
"""

from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any


LabelKey = tuple[str, str, str]


def _key(row: dict[str, Any]) -> LabelKey:
    return (str(row.get("case_id")), str(row.get("sample_id")), str(row.get("point_id")))


def _label_map(rows: list[dict[str, Any]]) -> dict[LabelKey, dict[str, Any]]:
    return {_key(row): row for row in rows}


def _avg(values: list[float]) -> float:
    return round(float(mean(values)), 4) if values else 0.0


def _score(row: dict[str, Any]) -> float:
    return float(row.get("score") or row.get("human_score") or row.get("gold_score") or 0)


def _hit(row: dict[str, Any]) -> str:
    return str(row.get("hit") or row.get("human_hit") or row.get("ledger_hit") or "").strip()


def _cluster_bootstrap_hit_ci(pairs: list[tuple[LabelKey, dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for (case_id, sample_id, _point_id), left, right in pairs:
        clusters[f"{case_id}::{sample_id}"].append(1.0 if _hit(left) == _hit(right) else 0.0)
    cluster_values = [_avg(values) for values in clusters.values()]
    if not cluster_values:
        return {"metric": "hit_agreement", "low": 0.0, "high": 0.0, "samples": 0}
    rng = random.Random(20260601)
    boot: list[float] = []
    for _ in range(200):
        sample = [cluster_values[rng.randrange(len(cluster_values))] for _ in cluster_values]
        boot.append(float(mean(sample)))
    boot.sort()
    return {
        "metric": "hit_agreement",
        "low": round(boot[int(len(boot) * 0.025)], 4),
        "high": round(boot[min(len(boot) - 1, int(len(boot) * 0.975))], 4),
        "samples": len(boot),
    }


def score_point_label_agreement(labels_a: list[dict[str, Any]], labels_b: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare two pre-adjudication point-label sets.

    The function is deliberately plain: exact hit agreement, exact score agreement,
    mean absolute score delta, and a cluster bootstrap CI over sample clusters.
    """

    left = _label_map(labels_a)
    right = _label_map(labels_b)
    keys = sorted(set(left) & set(right))
    pairs = [(key, left[key], right[key]) for key in keys]
    hit_matches: list[float] = []
    score_matches: list[float] = []
    score_deltas: list[float] = []
    disagreements: list[dict[str, Any]] = []
    for case_id, sample_id, point_id in keys:
        a = left[(case_id, sample_id, point_id)]
        b = right[(case_id, sample_id, point_id)]
        hit_match = _hit(a) == _hit(b)
        score_delta = abs(_score(a) - _score(b))
        score_match = score_delta <= 1e-9
        hit_matches.append(1.0 if hit_match else 0.0)
        score_matches.append(1.0 if score_match else 0.0)
        score_deltas.append(score_delta)
        if not hit_match or not score_match:
            disagreements.append(
                {
                    "case_id": case_id,
                    "sample_id": sample_id,
                    "point_id": point_id,
                    "a_hit": _hit(a),
                    "b_hit": _hit(b),
                    "a_score": round(_score(a), 4),
                    "b_score": round(_score(b), 4),
                    "score_delta": round(score_delta, 4),
                }
            )
    return {
        "point_count": len(keys),
        "missing_from_a": len(set(right) - set(left)),
        "missing_from_b": len(set(left) - set(right)),
        "hit_agreement": _avg(hit_matches),
        "score_exact_agreement": _avg(score_matches),
        "mean_abs_score_delta": _avg(score_deltas),
        "pre_adjudication_disagreement_count": len(disagreements),
        "pre_adjudication_disagreements": disagreements,
        "cluster_bootstrap_ci": _cluster_bootstrap_hit_ci(pairs),
    }
