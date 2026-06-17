#!/usr/bin/env python3
"""Compute the Qwen few-shot vs baseline A/B delta + GO/Weak-GO/NO-GO verdict.

Pure offline comparison of two consensus_gold_shadow metrics files. directional/shadow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compute_ab_delta(baseline: dict, fewshot: dict) -> dict:
    def g(d, k):
        return d.get(k, 0)

    d = {
        "baseline_hit_agreement": g(baseline, "point_hit_agreement"),
        "fewshot_hit_agreement": g(fewshot, "point_hit_agreement"),
        "delta_hit_agreement": round(g(fewshot, "point_hit_agreement") - g(baseline, "point_hit_agreement"), 4),
        "baseline_score_delta": g(baseline, "mean_abs_score_delta"),
        "fewshot_score_delta": g(fewshot, "mean_abs_score_delta"),
        "delta_score_delta": round(g(fewshot, "mean_abs_score_delta") - g(baseline, "mean_abs_score_delta"), 4),
        "baseline_unsupported_positive": g(baseline, "unsupported_positive"),
        "fewshot_unsupported_positive": g(fewshot, "unsupported_positive"),
        "baseline_disagreement_count": g(baseline, "disagreement_count"),
        "fewshot_disagreement_count": g(fewshot, "disagreement_count"),
        "list_rule_disagreement_delta": g(fewshot, "list_rule_disagreements") - g(baseline, "list_rule_disagreements"),
        "exact_required_major_violation_delta": g(fewshot, "exact_required_major_violation") - g(baseline, "exact_required_major_violation"),
        "penalty_rule_major_violation_delta": g(fewshot, "penalty_rule_major_violation") - g(baseline, "penalty_rule_major_violation"),
        "calculation_disagreement_delta": g(fewshot, "calculation_disagreements") - g(baseline, "calculation_disagreements"),
    }
    d["verdict"], d["verdict_reasons"] = _verdict(d)
    return d


def _verdict(d: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    # NO-GO conditions (any)
    if d["fewshot_unsupported_positive"] > 0:
        reasons.append("unsupported_positive>0")
    if d["exact_required_major_violation_delta"] > 0:
        reasons.append("exact_required major regression")
    if d["penalty_rule_major_violation_delta"] > 0:
        reasons.append("penalty_rule major regression")
    if d["calculation_disagreement_delta"] > 0:
        reasons.append("calculation regression")
    if d["delta_hit_agreement"] < -0.01:
        reasons.append("hit_agreement down >0.01")
    if d["delta_score_delta"] > 0.02:
        reasons.append("score_delta worse >0.02")
    if reasons:
        return "NO-GO", reasons
    # Strong GO
    if (d["delta_hit_agreement"] > 0 and d["delta_score_delta"] <= 0 and d["list_rule_disagreement_delta"] < 0):
        return "STRONG-GO", ["hit up, score not worse, list_rule down, no regression"]
    # Weak GO
    if (d["delta_hit_agreement"] >= 0 and d["delta_score_delta"] <= 0.01 and d["list_rule_disagreement_delta"] < 0):
        return "WEAK-GO", ["hit not down, score within +0.01, list_rule down, no major regression"]
    return "NO-GO", ["no list_rule improvement or net non-improvement without regression headroom"]


def compute_list_rule_only_ab(baseline: dict, candidate: dict) -> dict:
    """Stricter verdict for the list_rule-ONLY round.

    GO requires hit not below baseline AND exact_required_disagreements not increased.
    Weak-GO allows hit down <= 0.003. Any 踩字/penalty/calc/unsupported regression, or
    list_rule not improving, is NO-GO. directional/shadow.
    """
    def g(d, k):
        return d.get(k, 0)

    d = {
        "baseline_hit_agreement": g(baseline, "point_hit_agreement"),
        "candidate_hit_agreement": g(candidate, "point_hit_agreement"),
        "delta_hit_agreement": round(g(candidate, "point_hit_agreement") - g(baseline, "point_hit_agreement"), 4),
        "baseline_score_delta": g(baseline, "mean_abs_score_delta"),
        "candidate_score_delta": g(candidate, "mean_abs_score_delta"),
        "delta_score_delta": round(g(candidate, "mean_abs_score_delta") - g(baseline, "mean_abs_score_delta"), 4),
        "candidate_unsupported_positive": g(candidate, "unsupported_positive"),
        "baseline_list_rule_disagreements": g(baseline, "list_rule_disagreements"),
        "candidate_list_rule_disagreements": g(candidate, "list_rule_disagreements"),
        "list_rule_disagreement_delta": g(candidate, "list_rule_disagreements") - g(baseline, "list_rule_disagreements"),
        "baseline_exact_required_disagreements": g(baseline, "exact_required_disagreements"),
        "candidate_exact_required_disagreements": g(candidate, "exact_required_disagreements"),
        "exact_required_disagreement_delta": g(candidate, "exact_required_disagreements") - g(baseline, "exact_required_disagreements"),
        "candidate_exact_required_major_violation": g(candidate, "exact_required_major_violation"),
        "penalty_rule_major_violation_delta": g(candidate, "penalty_rule_major_violation") - g(baseline, "penalty_rule_major_violation"),
        "calculation_disagreement_delta": g(candidate, "calculation_disagreements") - g(baseline, "calculation_disagreements"),
    }
    d["verdict"], d["verdict_reasons"] = _list_rule_only_verdict(d)
    return d


def _list_rule_only_verdict(d: dict) -> tuple[str, list[str]]:
    # NO-GO conditions (any) — hard 踩字/regression gates
    no_go: list[str] = []
    if d["candidate_unsupported_positive"] > 0:
        no_go.append("unsupported_positive>0")
    if d["candidate_exact_required_major_violation"] > 0:
        no_go.append("exact_required_major_violation>0")
    if d["penalty_rule_major_violation_delta"] > 0:
        no_go.append("penalty_rule major regression")
    if d["calculation_disagreement_delta"] > 0:
        no_go.append("calculation regression")
    if d["delta_score_delta"] > 0.01:
        no_go.append("score_delta clearly worse (>+0.01)")
    if d["list_rule_disagreement_delta"] >= 0:
        no_go.append("list_rule no improvement")
    if no_go:
        return "NO-GO", no_go

    # GO: hit not below baseline + exact_required not increased + score within +0.01
    if (
        d["list_rule_disagreement_delta"] < 0
        and d["delta_hit_agreement"] >= 0
        and d["delta_score_delta"] <= 0.01
        and d["exact_required_disagreement_delta"] <= 0
    ):
        return "GO", ["list_rule down, hit not below baseline, exact_required not increased, no regression"]

    # Weak-GO: hit down <= 0.003, score within +0.01
    if (
        d["list_rule_disagreement_delta"] < 0
        and d["delta_hit_agreement"] >= -0.003
        and d["delta_score_delta"] <= 0.01
    ):
        return "WEAK-GO", ["list_rule down, hit down <=0.003, score within +0.01, no major regression"]

    return "NO-GO", ["hit dropped >0.003 below baseline without offsetting gain"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--fewshot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--list-rule-only", action="store_true", help="use stricter list_rule-only verdict")
    args = ap.parse_args()
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    cand = json.loads(Path(args.fewshot).read_text(encoding="utf-8"))
    d = compute_list_rule_only_ab(base, cand) if args.list_rule_only else compute_ab_delta(base, cand)
    Path(args.out).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
