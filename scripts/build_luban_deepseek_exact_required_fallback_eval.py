#!/usr/bin/env python3
"""Offline simulator: DeepSeek-V4-flash single model + a NARROW exact_required high_risk fallback.

The held-out distillation round left exactly ONE hard blocker: an exact_required
踩字 leniency (Q10/S2/P4 — DeepSeek gave partial 0.5 for a near/half term where the
3-model jury said miss). This script simulates a minimal fallback that, for
exact_required points only, moves a suspected near/half-term positive OUT of the
auto-graded set into high_risk_review — WITHOUT re-scoring it to miss (no hiding
the model error). It then measures before/after coverage and hard-violation counts.

STRICT scope (red lines):
  - fallback fires ONLY for policy_type == exact_required
  - NEVER for list_rule / calculation / penalty_rule / figure_label
  - it removes a point from auto-grade; it does NOT change the score
  - offline only; NOT runtime; does NOT touch the kernel, RAG, or consensus gold

directional/shadow — NOT a production accuracy claim.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Signals where the model ITSELF admits, in its rationale, that the official
# exact_required term is not fully met while still awarding a positive — the
# precise tell of an exact_required 踩字 leniency. (The literal span-term check
# was measured and rejected: 20/21 false positives, coverage 100%->87%, because
# official required_terms forms do not byte-match legitimate correct spans.)
_NEAR_SYNONYM_SIGNALS = [
    "类似", "相当于", "近义", "部分表达", "泛称", "不完全一致", "不完全相同",
    "只写了一半", "一半", "意思相近", "近似", "约等于", "可视为",
    "缺少", "未写全", "未完全", "不够规范", "大白话", "口语", "非规范",
]


def load_points(packet: dict) -> dict[tuple, dict]:
    """key -> {policy_type, required_terms, max_score, label}"""
    idx = {}
    for t in packet["tasks"]:
        for sp in t["scoring_points"]:
            tp = sp.get("typed_policy") or {}
            terms = list(tp.get("required_terms") or [])
            ls = tp.get("list_spec") or {}
            if ls.get("terms"):
                terms = terms or list(ls["terms"])
            idx[(t["case_id"], t["student_id"], sp["point_id"])] = {
                "policy_type": tp.get("policy_type"),
                "required_terms": terms,
                "max_score": sp.get("max_score"),
                "label": sp.get("label", ""),
            }
    return idx


def load_predictions(unified: dict, arm: str) -> dict[tuple, dict]:
    idx = {}
    for s in unified["prediction_sets"]:
        if s["arm"] != arm:
            continue
        for p in s["predictions"]:
            idx[(p["case_id"], p["student_id"], p["point_id"])] = p
    return idx


def load_gold(gold: list[dict]) -> dict[tuple, dict]:
    return {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold}


def _span_has_required_term(span: str, terms: list[str]) -> bool:
    """True if the evidence span literally contains at least one required core term
    (loose: also matches when a term's >=4-char core substring appears, to avoid
    over-triggering on punctuation/bracket-form differences)."""
    if not terms:
        return False
    s = span or ""
    for term in terms:
        term = (term or "").strip()
        if not term:
            continue
        if term in s:
            return True
        # tolerate punctuation/bracket form: strip non-CJK/alnum and compare cores
        core = re.sub(r"[（）()\s、,.，。/]", "", term)
        s_core = re.sub(r"[（）()\s、,.，。/]", "", s)
        if len(core) >= 4 and core in s_core:
            return True
    return False


def _rationale_has_near_synonym(rationale: str) -> bool:
    r = rationale or ""
    return any(sig in r for sig in _NEAR_SYNONYM_SIGNALS)


def fallback_fires(point: dict, pred: dict) -> tuple[bool, str]:
    """Return (fires, reason). NARROW: exact_required + positive(hit/partial) where the
    model's own rationale admits the official term is only near/half/missing.

    The literal span-term check is computed for corroboration/reporting only — it is
    NOT a standalone trigger because official term forms do not byte-match legitimate
    correct spans (measured: 20/21 false positives). A `partial` verdict on an
    exact_required point is itself suspect, so a partial with span-missing also fires.
    """
    if point.get("policy_type") != "exact_required":
        return False, ""
    hit = str(pred.get("hit") or "miss")
    if hit not in ("hit", "partial"):
        return False, ""
    span = pred.get("evidence_span") or ""
    rationale = pred.get("rationale") or ""
    span_ok = _span_has_required_term(span, point.get("required_terms") or [])
    near = _rationale_has_near_synonym(rationale)
    if near and not span_ok:
        return True, "near_synonym_rationale+span_lacks_core_term"
    if near:
        return True, "near_synonym_rationale"
    # a partial verdict on an exact_required point whose span lacks the core term
    # is the structural 踩字-leniency shape (half credit for a non-matching term).
    if hit == "partial" and not span_ok:
        return True, "exact_required_partial+span_lacks_core_term"
    return False, ""


def _is_unsupported(pred: dict) -> bool:
    """unsupported_positive = a POSITIVE (hit/partial) with no valid student-answer span.
    A `miss` is never an unsupported positive, even if the span-guard flagged it."""
    hit = str(pred.get("hit") or "miss")
    if hit not in ("hit", "partial"):
        return False
    span = (pred.get("evidence_span") or "").strip()
    if not span:
        return True
    return pred.get("unsupported") is True


def evaluate(points: dict, preds: dict, gold: dict) -> dict:
    """Compute before/after metrics over the gold-covered points."""
    keys = [k for k in gold if k in preds]  # evaluate where we have gold AND a prediction
    triggered = []
    auto_before, auto_after = [], []
    for k in keys:
        pt, pr, g = points.get(k, {}), preds[k], gold[k]
        fires, reason = fallback_fires(pt, pr)
        auto_before.append(k)
        if fires:
            triggered.append({"key": k, "reason": reason, "policy_type": pt.get("policy_type"),
                              "pred_hit": pr.get("hit"), "pred_score": pr.get("score"),
                              "gold_hit": g.get("gold_hit"), "gold_score": g.get("gold_score"),
                              "evidence_span": (pr.get("evidence_span") or "")[:80],
                              "rationale": (pr.get("rationale") or "")[:120]})
        else:
            auto_after.append(k)

    def _metrics(subset):
        n = len(subset)
        if not n:
            return {"points": 0}
        hit_agree = sum(1 for k in subset if str(preds[k].get("hit")) == str(gold[k].get("gold_hit"))) / n
        score_delta = sum(abs(float(preds[k].get("score") or 0) - float(gold[k].get("gold_score") or 0)) for k in subset) / n
        # hard violation: exact_required, gold miss, pred hit/partial (踩字 leniency)
        exact_major = sum(1 for k in subset if points.get(k, {}).get("policy_type") == "exact_required"
                          and str(gold[k].get("gold_hit")) == "miss"
                          and str(preds[k].get("hit")) in ("hit", "partial"))
        unsupported = sum(1 for k in subset if _is_unsupported(preds[k]))
        # regression guards on other types
        list_rule_dis = sum(1 for k in subset if points.get(k, {}).get("policy_type") == "list_rule"
                            and (str(preds[k].get("hit")) != str(gold[k].get("gold_hit"))
                                 or abs(float(preds[k].get("score") or 0) - float(gold[k].get("gold_score") or 0)) > 0.25))
        return {
            "points": n,
            "point_hit_agreement": round(hit_agree, 4),
            "mean_abs_score_delta": round(score_delta, 4),
            "exact_required_major_violation": exact_major,
            "unsupported_positive": unsupported,
            "list_rule_disagreements": list_rule_dis,
        }

    total = len(keys)
    before = _metrics(auto_before)
    after = _metrics(auto_after)
    return {
        "total_evaluated_points": total,
        "before": before | {"auto_graded_points": len(auto_before),
                             "high_risk_review_points": 0,
                             "auto_coverage": round(len(auto_before) / total, 4) if total else 0},
        "after": after | {"auto_graded_points": len(auto_after),
                          "high_risk_review_points": len(triggered),
                          "auto_coverage": round(len(auto_after) / total, 4) if total else 0,
                          "high_risk_review_ratio": round(len(triggered) / total, 4) if total else 0},
        "triggered": triggered,
    }


def _gate(after: dict, hrr_ratio: float, coverage: float) -> tuple[str, list[str]]:
    no_go = []
    if after.get("exact_required_major_violation", 0) > 0:
        no_go.append("exact_required_major_violation still >0")
    if after.get("unsupported_positive", 0) > 0:
        no_go.append("unsupported_positive >0")
    if no_go:
        return "NO-GO", no_go
    if (coverage >= 0.90 and after.get("point_hit_agreement", 0) >= 0.94
            and after.get("mean_abs_score_delta", 1) <= 0.05 and hrr_ratio <= 0.10):
        return "STRONG-GO", ["coverage>=90%, hit>=0.94, score_delta<=0.05, hrr<=10%, hard violation 0"]
    if coverage >= 0.85 and after.get("point_hit_agreement", 0) >= 0.90 and hrr_ratio <= 0.15:
        return "WEAK-GO", ["coverage>=85%, hit>=0.90, hrr<=15%, hard violation 0"]
    return "NO-GO", ["coverage or hit or hrr outside gate"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json"))
    ap.add_argument("--predictions", default=str(REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_predictions_span_guarded.json"))
    ap.add_argument("--arm", default="deepseek_v4_flash_typed_policy_primary")
    ap.add_argument("--gold", default=str(REPO / "artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/consensus_gold_v1.json"))
    ap.add_argument("--out-dir", default=str(REPO / "artifacts/luban_consensus_gold/deepseek_exact_required_fallback_20260603"))
    ap.add_argument("--label", default="heldout_175")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    unified = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    gold_raw = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    # support both top-level list and {"gold": [...]} wrapper (dev slice format)
    gold = gold_raw["gold"] if isinstance(gold_raw, dict) and "gold" in gold_raw else gold_raw

    points = load_points(packet)
    preds = load_predictions(unified, args.arm)
    gold_idx = load_gold(gold)

    result = evaluate(points, preds, gold_idx)
    verdict, reasons = _gate(result["after"], result["after"]["high_risk_review_ratio"], result["after"]["auto_coverage"])
    result["gate_verdict"] = verdict
    result["gate_reasons"] = reasons
    result["label"] = args.label

    (out / f"fallback_before_after_metrics_{args.label}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # triggered points CSV
    with (out / f"fallback_triggered_points_{args.label}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "student_id", "point_id", "reason", "policy_type", "pred_hit", "pred_score", "gold_hit", "gold_score", "evidence_span", "rationale"])
        for t in result["triggered"]:
            k = t["key"]
            w.writerow([k[0], k[1], k[2], t["reason"], t["policy_type"], t["pred_hit"], t["pred_score"], t["gold_hit"], t["gold_score"], t["evidence_span"], t["rationale"]])
    # high_risk_review queue (same set, queue framing)
    with (out / f"high_risk_review_queue_{args.label}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "student_id", "point_id", "policy_type", "trigger_reason", "deepseek_hit", "deepseek_score", "action"])
        for t in result["triggered"]:
            k = t["key"]
            w.writerow([k[0], k[1], k[2], t["policy_type"], t["reason"], t["pred_hit"], t["pred_score"], "route_to_human_or_jury_review"])

    print(f"[{args.label}] total={result['total_evaluated_points']}")
    print(f"  before: coverage={result['before']['auto_coverage']} exact_major={result['before']['exact_required_major_violation']} hit={result['before'].get('point_hit_agreement')}")
    print(f"  after:  coverage={result['after']['auto_coverage']} exact_major={result['after']['exact_required_major_violation']} hit={result['after'].get('point_hit_agreement')} hrr={result['after']['high_risk_review_ratio']}")
    print(f"  triggered: {len(result['triggered'])} -> {[ (t['key'][0],t['key'][1],t['key'][2]) for t in result['triggered'] ]}")
    print(f"  GATE: {verdict} {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
