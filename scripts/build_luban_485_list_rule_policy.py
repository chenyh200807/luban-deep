#!/usr/bin/env python3
"""list_rule-only shadow policy v1 for the 485 WEAK-GO convergence round.

Classifies the after-fallback list_rule residuals and applies two candidate
shadow policies, then computes the gate metrics for an A/B. Everything is
offline, shadow-only, deterministic, and grounded ONLY in DeepSeek's own
prediction + the packet's official list_spec (NEVER the gold — no leakage).

Policies (list_rule points only; exact_required/calc/penalty/figure untouched):
  - recompute (v1):   k = official list items found in DeepSeek's OWN evidence_span;
                      score = round(k/n * max, 3); hit = full if k>=n else partial if k>0 else miss.
                      (Grounded in DeepSeek's extraction; cannot invent semantic credit.)
  - fail_closed (v1): list_rule point routed to high_risk_review when DeepSeek's verdict
                      looks structurally unsafe (miss with an enumerated span = suspected
                      under-credit; or hit while recompute k<n = suspected over-credit).
                      Does NOT change score — only quarantines from auto-certification.

NOT runtime, NOT kernel, NOT RAG, does NOT touch consensus gold or force frontier into gold.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
F = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"

PACKET = F / "unified_typed_policy_packet_485.json"
PREDS = F / "unified_predictions_485_span_guarded.json"
GOLD = F / "loo_gold_485_flat.json"
DS_ARM = "deepseek_v4_flash_typed_policy_primary"
ENUM = "；;、,，①②③④⑤⑥⑦⑧⑨"


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _as_text(s) -> str:
    if isinstance(s, list):
        return " ".join(_as_text(x) for x in s)
    return s if isinstance(s, str) else ("" if s is None else str(s))


def _norm(s) -> str:
    return re.sub(r"[（）()\s、,.，。/；;:：]", "", _as_text(s))


def _k_in_span(terms, span) -> int:
    """count official list items present (verbatim or >=2-char core) in DeepSeek's span."""
    sc = _norm(span)
    k = 0
    for t in terms or []:
        tc = _norm(t)
        if not tc:
            continue
        if tc in sc or (len(tc) >= 2 and tc in sc):
            k += 1
    return k


def _enum_count(span) -> int:
    span = _as_text(span)
    if not span:
        return 0
    seps = sum(span.count(c) for c in ENUM)
    return seps + (1 if span.strip() else 0)


def _ds_index(preds):
    for s in preds["prediction_sets"]:
        if s["arm"] == DS_ARM:
            return {(p["case_id"], p["student_id"], p["point_id"]): p for p in s["predictions"]}
    return {}


def _packet_index(packet):
    idx = {}
    for t in packet["tasks"]:
        for sp in t["scoring_points"]:
            tp = sp.get("typed_policy") or {}
            idx[(t["case_id"], t["student_id"], sp["point_id"])] = {
                "policy_type": tp.get("policy_type"),
                "list_spec": tp.get("list_spec") or {},
                "max": sp.get("max_score"),
            }
    return idx


# ---------- residual classification (Task A/B) ----------

def classify_list_rule_residual(pt, pred, gold) -> str:
    ls = pt["list_spec"]
    terms, n = ls.get("terms") or [], ls.get("denominator")
    span = _as_text(pred.get("evidence_span"))
    dh, gh = str(pred.get("hit")), str(gold.get("gold_hit"))
    k = _k_in_span(terms, span)
    if dh == "miss" and gh in ("partial", "hit"):
        if not span.strip():
            return "evidence_span_insufficient"
        if k == 0 and _enum_count(span) >= 2:
            return "generic_label_over_credit"  # jury credited paraphrase, deepseek (verbatim) saw nothing
        if k >= 1:
            return "label_vs_score_mismatch"  # deepseek saw items but scored miss
        return "true_frontier"
    if dh == "hit" and gh == "partial":
        return "denominator_mismatch" if (n and k < n) else "rounding_policy_mismatch"
    if dh == "partial" and gh in ("hit", "miss"):
        return "label_vs_score_mismatch"
    return "true_frontier"


# ---------- policy application ----------

def apply_recompute(ds, pidx):
    """return new ds-index with list_rule scores recomputed from span-grounded k/n."""
    out = {}
    for k, p in ds.items():
        info = pidx.get(k, {})
        np = dict(p)
        if info.get("policy_type") == "list_rule":
            ls = info["list_spec"]
            terms, n, mx = ls.get("terms") or [], ls.get("denominator"), info.get("max") or 0
            if n:
                kk = min(_k_in_span(terms, p.get("evidence_span") or ""), n)
                np["score"] = round(kk / n * mx, 3)
                np["hit"] = "hit" if kk >= n else ("partial" if kk > 0 else "miss")
                np["_recomputed_k_over_n"] = f"{kk}/{n}"
        out[k] = np
    return out


def apply_fail_closed(ds, pidx):
    """flag structurally-unsafe list_rule verdicts to high_risk_review (no score change)."""
    out = {}
    for k, p in ds.items():
        info = pidx.get(k, {})
        np = dict(p)
        if info.get("policy_type") == "list_rule":
            ls = info["list_spec"]
            terms, n = ls.get("terms") or [], ls.get("denominator")
            span = _as_text(p.get("evidence_span"))
            kk = _k_in_span(terms, span)
            hit = str(p.get("hit"))
            suspect = (hit == "miss" and _enum_count(span) >= 2) or (hit == "hit" and n and kk < n)
            if suspect:
                np["high_risk_review"] = True
                np["review_reason"] = "list_rule_fail_closed: suspected under/over-credit vs official list"
        out[k] = np
    return out


# ---------- gate metrics ----------

def _supported(p):
    if p.get("unsupported") is True:
        return False
    if str(p.get("hit")) in ("hit", "partial"):
        return bool((p.get("evidence_span") or "").strip())
    return True


def _exact_fallback_triggered(p):
    from scripts.build_luban_deepseek_exact_required_fallback_eval import fallback_fires
    return p


def gate_metrics(ds, pidx, gold):
    from scripts.build_luban_deepseek_exact_required_fallback_eval import fallback_fires, _gate
    auto, review = [], []
    keys = [k for k in gold if k in ds]
    for k in keys:
        p, info = ds[k], pidx.get(k, {})
        fires, _ = fallback_fires({"policy_type": info.get("policy_type"), "required_terms": (info.get("list_spec") or {}).get("terms", [])}, p)
        if fires or p.get("high_risk_review") is True:
            review.append(k)
        else:
            auto.append(k)
    n = len(auto) or 1
    hit_agree = sum(1 for k in auto if str(ds[k].get("hit")) == str(gold[k]["gold_hit"])) / n
    sdelta = sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) for k in auto) / n
    exact_major = sum(1 for k in auto if pidx.get(k, {}).get("policy_type") == "exact_required" and str(gold[k]["gold_hit"]) == "miss" and str(ds[k].get("hit")) in ("hit", "partial"))
    penalty_major = sum(1 for k in auto if pidx.get(k, {}).get("policy_type") == "penalty_rule" and str(gold[k]["gold_hit"]) == "miss" and str(ds[k].get("hit")) in ("hit", "partial"))
    unsupported = sum(1 for k in auto if str(ds[k].get("hit")) in ("hit", "partial") and not _as_text(ds[k].get("evidence_span")).strip())
    lr_dis = sum(1 for k in auto if pidx.get(k, {}).get("policy_type") == "list_rule" and str(ds[k].get("hit")) != str(gold[k]["gold_hit"]))
    calc_dis = sum(1 for k in auto if pidx.get(k, {}).get("policy_type") == "calculation" and str(ds[k].get("hit")) != str(gold[k]["gold_hit"]))
    total = len(keys)
    after = {"exact_required_major_violation": exact_major, "penalty_rule_major_violation": penalty_major,
             "unsupported_positive": unsupported, "point_hit_agreement": round(hit_agree, 4), "mean_abs_score_delta": round(sdelta, 4)}
    hrr = round(len(review) / total, 4) if total else 0
    cov = round(len(auto) / total, 4) if total else 0
    verdict, reasons = _gate(after, hrr, cov)
    return {"auto_coverage": cov, "auto_hit": round(hit_agree, 4), "score_delta": round(sdelta, 4),
            "exact_major": exact_major, "penalty_major": penalty_major, "unsupported": unsupported,
            "high_risk_review": hrr, "high_risk_review_points": len(review),
            "list_rule_disagreements": lr_dis, "calculation_disagreements": calc_dis,
            "gate_verdict": verdict, "gate_reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(F))
    args = ap.parse_args()
    out = Path(args.out_dir)

    packet, preds, gold_list = _read(PACKET), _read(PREDS), _read(GOLD)
    pidx = _packet_index(packet)
    ds = _ds_index(preds)
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold_list}

    # Task A/B: classify list_rule residuals (after exact_required fallback)
    from scripts.build_luban_deepseek_exact_required_fallback_eval import fallback_fires
    rows = []
    for k, g in gold.items():
        p, info = ds.get(k), pidx.get(k, {})
        if not p or info.get("policy_type") != "list_rule":
            continue
        fires, _ = fallback_fires({"policy_type": "exact_required", "required_terms": []}, p)  # never for list_rule
        if str(p.get("hit")) == str(g["gold_hit"]):
            continue
        cls = classify_list_rule_residual(info, p, g)
        ls = info["list_spec"]
        rows.append({"case_id": k[0], "student_id": k[1], "point_id": k[2],
                     "gold_hit": g["gold_hit"], "gold_score": g["gold_score"],
                     "deepseek_hit": p.get("hit"), "deepseek_score": p.get("score"),
                     "score_delta": round(abs(float(p.get("score") or 0) - float(g["gold_score"] or 0)), 3),
                     "denominator": ls.get("denominator"), "k_in_span": _k_in_span(ls.get("terms") or [], p.get("evidence_span") or ""),
                     "root_cause": cls, "student_span": _as_text(p.get("evidence_span"))[:80]})
    with (out / "list_rule_residual_classification_485.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    cls_counts = Counter(r["root_cause"] for r in rows)
    print(f"list_rule residuals: {len(rows)} | by root cause: {dict(cls_counts)}")

    # Task D: A/B three arms
    arms = {
        "baseline_after_fallback": ds,
        "list_rule_policy_v1_recompute": apply_recompute(ds, pidx),
        "list_rule_policy_v1_fail_closed": apply_fail_closed(ds, pidx),
    }
    results = {name: gate_metrics(arm, pidx, gold) for name, arm in arms.items()}
    (out / "list_rule_policy_ab_485.json").write_text(json.dumps({"residual_classification": dict(cls_counts), "arms": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nARM | cov | hit | sdelta | exact_major | unsup | hrr | lr_dis | gate")
    for name, r in results.items():
        print(f"{name}: {r['auto_coverage']} | {r['auto_hit']} | {r['score_delta']} | {r['exact_major']} | {r['unsupported']} | {r['high_risk_review']} | {r['list_rule_disagreements']} | {r['gate_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
