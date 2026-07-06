#!/usr/bin/env python3
"""Power estimate for Stage-1 A/B on the J01 governed gold.

Stage-1 question (from the reconciled milestone plan §阶段1):
    Does 通道① 编译 rubric agree with the HUMAN gold significantly MORE often than
    open-world 现编 does, on the SAME student answers?

This is a PAIRED binary comparison at the scoring-point level: for each (student answer ×
scoring point), arm A (compiled) and arm B (open-world) each agree-or-not with the human
gold hit/miss. The right test is McNemar on the discordant pairs (points where the two arms
differ relative to gold). This script gives an honest power probe BEFORE any billable run —
the plan requires power-first so ~150 rows are not spent on an under-powered false-negative.

Baseline anchor: the one prior human-validation red-light measured compiled-vs-human
point-hit agreement = 0.5267 (MAE 4.6091). That is roughly coin-flip agreement, so there is
plenty of headroom for a better arm to separate — IF the sample is not swamped by clustering.

Design-effect caveat: the J01 slice is WIDE on personas (10) but NARROW on sub-questions
(~4). Points nested in the same sub-question share one official answer and correlated persona
behaviour, so effective independent N << raw N. This script reports both raw and
design-effect-adjusted power.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


# standard normal helpers (no scipy dependency)
def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _z_two_sided(alpha: float) -> float:
    # inverse normal via bisection for the (1 - alpha/2) quantile
    target = 1.0 - alpha / 2.0
    lo, hi = 0.0, 8.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _phi(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def mcnemar_power(n_points: int, discordance: float, psi: float, alpha: float = 0.05) -> float:
    """Approx power of McNemar's test.

    n_points   : number of paired point-level observations.
    discordance: fraction of points where arm A and arm B disagree relative to gold.
    psi        : among discordant pairs, expected fraction where arm A (compiled) is the
                 one that matches gold (0.5 = null; >0.5 = compiled better).
    """
    n_disc = n_points * discordance
    if n_disc < 1:
        return 0.0
    z_a = _z_two_sided(alpha)
    # test statistic ~ (b - n_disc/2) / sqrt(n_disc/4) under H0; power under H1 (b ~ Bin(n_disc, psi))
    sd0 = math.sqrt(n_disc * 0.25)
    sd1 = math.sqrt(n_disc * psi * (1.0 - psi))
    mean_shift = n_disc * (psi - 0.5)
    if sd1 <= 0:
        return 0.0
    z = (abs(mean_shift) - z_a * sd0) / sd1
    return round(_phi(z), 3)


def design_effect(cluster_size: float, icc: float) -> float:
    return 1.0 + (cluster_size - 1.0) * icc


def build_report(*, raw_n: int, core_n: int, clusters: int, alpha: float = 0.05) -> dict:
    baseline_agreement = 0.5267  # compiled-vs-human point-hit (prior red-light)
    cluster_size = raw_n / clusters if clusters else raw_n

    grid = []
    for label, n in (("full_slice", raw_n), ("core_only", core_n)):
        for disc in (0.20, 0.30, 0.40):
            for psi in (0.65, 0.70, 0.75):
                grid.append({
                    "sample": label,
                    "n_points": n,
                    "discordance": disc,
                    "psi_compiled_better": psi,
                    "power_raw": mcnemar_power(n, disc, psi, alpha),
                })

    # design-effect adjusted power for a representative "meaningful effect" cell
    deff_rows = []
    for icc in (0.05, 0.15, 0.30):
        deff = design_effect(cluster_size, icc)
        n_eff = raw_n / deff
        deff_rows.append({
            "icc": icc,
            "cluster_size": round(cluster_size, 1),
            "design_effect": round(deff, 2),
            "effective_n": round(n_eff, 1),
            "power_disc0.30_psi0.70": mcnemar_power(int(n_eff), 0.30, 0.70, alpha),
        })

    # what N is needed for ~80% power at a modest effect (disc 0.30, psi 0.70)?
    needed = None
    for n in range(50, 2001, 10):
        if mcnemar_power(n, 0.30, 0.70, alpha) >= 0.80:
            needed = n
            break

    return {
        "test": "McNemar (paired, point-level, compiled vs open-world against human gold)",
        "baseline_compiled_vs_human_point_hit": baseline_agreement,
        "alpha": alpha,
        "raw_n_points": raw_n,
        "core_n_points": core_n,
        "distinct_sub_question_clusters": clusters,
        "approx_cluster_size": round(cluster_size, 1),
        "power_grid": grid,
        "design_effect_adjusted": deff_rows,
        "n_for_80pct_power_at_disc0.30_psi0.70": needed,
        "verdict": _verdict(raw_n, core_n, clusters, needed),
    }


def _verdict(raw_n: int, core_n: int, clusters: int, needed: int | None) -> dict:
    return {
        "headline": (
            f"~{raw_n} raw point-obs (core≈{core_n}) across only {clusters} sub-question clusters is "
            "BORDERLINE: adequate to detect a LARGE arm separation (compiled clearly better on "
            "≥30-40% of points), UNDER-POWERED for small/moderate effects once clustering is accounted for."
        ),
        "clustering_risk": (
            "Points are nested in ~4 sub-questions × 10 personas. Within-cluster correlation inflates "
            "variance (design effect), so effective independent N is materially below raw N — the "
            "power_grid raw numbers are optimistic upper bounds."
        ),
        "recommendation": (
            f"Treat this J01 slice as a Stage-0 PILOT / directional power probe, not a conclusive A/B. "
            f"For a conclusive Stage-1 verdict target ≥{needed or 200}+ point-obs spread over ≥8-10 DISTINCT "
            "sub-questions (add J01 canonical 专家论证 items from 2015-2019 exams, and/or sibling 危大 母题) "
            "to break the design effect. Do NOT declare '编译 rubric wins' off this slice alone."
        ),
        "falsifiability_precommit": (
            "Pre-register before the A/B run: '编译 rubric wins' iff McNemar p<0.05 AND compiled point-hit "
            "agreement exceeds open-world by a pre-set margin on core-tier points AND all §3 hard gates pass. "
            "Anything else = no-difference / open-world-not-worse. Define the win BEFORE seeing numbers."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Power estimate for J01 governed-gold Stage-1 A/B.")
    parser.add_argument("--raw-n", type=int, default=150, help="raw point-level observations (rows)")
    parser.add_argument("--core-n", type=int, default=90, help="core-tier (危大方案) point observations")
    parser.add_argument("--clusters", type=int, default=4, help="distinct sub-question clusters")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_report(raw_n=args.raw_n, core_n=args.core_n, clusters=args.clusters)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
