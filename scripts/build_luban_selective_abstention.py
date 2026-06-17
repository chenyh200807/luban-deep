#!/usr/bin/env python3
"""Selective-abstention risk-coverage pilot (research initiative #1).

Routes the most uncertain DeepSeek-flash positives into high_risk_review using
OFFLINE jury-derived + model-observable risk signals — WITHOUT changing any score.
Sweeps the abstention threshold and reports the risk-coverage curve under BOTH the
legacy raw-score_delta gate and the metric-v2 (QWK) candidate gate.

HARD constraints enforced on the certified subset: exact_required_major_violation==0,
unsupported_positive==0, penalty_major==0. high_risk_review is NOT correctness — it
is "not auto-certified, route to offline jury / human". directional/shadow, NOT runtime.
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
from scripts.luban_grading_metrics import qwk_for_pairs  # noqa: E402

SRC = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"
BAKE = REPO / "artifacts/luban_consensus_gold/list_rule_semantic_model_bakeoff_20260603"
OUT = REPO / "artifacts/luban_consensus_gold/selective_abstention_qwk_20260604"
ARM2 = BAKE / "predictions_by_arm" / "list_rule_semantic_protocol.json"
HEDGE = ["不确定", "可能", "近义", "泛称", "大白话", "部分覆盖", "不完全", "只写了一半", "一半", "缺少", "存疑"]


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _as_text(s):
    if isinstance(s, list):
        return " ".join(_as_text(x) for x in s)
    return s if isinstance(s, str) else ("" if s is None else str(s))


def _arm2_index():
    base = {(p["case_id"], p["student_id"], p["point_id"]): p
            for s in _read(SRC / "unified_predictions_485_span_guarded.json")["prediction_sets"]
            if s["arm"] == "deepseek_v4_flash_typed_policy_primary" for p in s["predictions"]}
    arm = {(p["case_id"], p["student_id"], p["point_id"]): p
           for s in _read(ARM2)["prediction_sets"] for p in s["predictions"]}
    base.update(arm)
    return base


def _pidx():
    idx = {}
    for t in _read(SRC / "unified_typed_policy_packet_485.json")["tasks"]:
        for sp in t["scoring_points"]:
            tp = sp.get("typed_policy") or {}
            idx[(t["case_id"], t["student_id"], sp["point_id"])] = {"policy_type": tp.get("policy_type"), "list_spec": tp.get("list_spec") or {}}
    return idx


def _votes():
    out = {}
    for r in csv.DictReader((SRC / "model_vote_matrix_485.csv").read_text(encoding="utf-8").splitlines()):
        out[(r["case_id"], r["student_id"], r["point_id"])] = [r.get("gpt_hit"), r.get("opus_hit"), r.get("qwen37_hit")]
    return out


def _exact_fallback(p, info):
    from scripts.build_luban_deepseek_exact_required_fallback_eval import fallback_fires
    return fallback_fires({"policy_type": info.get("policy_type"), "required_terms": (info.get("list_spec") or {}).get("terms", [])}, p)[0]


def risk_score(p, info, jurors) -> float:
    """OFFLINE model-observable risk: jury disagreement (primary) + list_rule-partial + weak span/rationale."""
    hit = str(p.get("hit"))
    if hit not in ("hit", "partial"):
        return -1.0  # miss is not a positive; not an abstention candidate
    jdis = sum(1 for j in jurors if str(j) != hit) if jurors else 0  # 0..3
    r = float(jdis)
    if info.get("policy_type") == "list_rule" and hit == "partial":
        r += 0.6
    span = _as_text(p.get("evidence_span")).strip()
    if not span or len(span) < 4:
        r += 0.4
    if any(h in _as_text(p.get("rationale")) for h in HEDGE):
        r += 0.3
    return round(r, 3)


def metrics_on(subset, ds, pidx, gold):
    n = len(subset) or 1
    hit = sum(1 for k in subset if str(ds[k].get("hit")) == str(gold[k]["gold_hit"])) / n
    raw = sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) for k in subset) / n
    exact_major = sum(1 for k in subset if pidx.get(k, {}).get("policy_type") == "exact_required" and str(gold[k]["gold_hit"]) == "miss" and str(ds[k].get("hit")) in ("hit", "partial"))
    penalty_major = sum(1 for k in subset if pidx.get(k, {}).get("policy_type") == "penalty_rule" and str(gold[k]["gold_hit"]) == "miss" and str(ds[k].get("hit")) in ("hit", "partial"))
    unsup = sum(1 for k in subset if str(ds[k].get("hit")) in ("hit", "partial") and not _as_text(ds[k].get("evidence_span")).strip())
    qwk = qwk_for_pairs([ds[k].get("hit") for k in subset], [gold[k]["gold_hit"] for k in subset])
    return {"points": len(subset), "auto_hit": round(hit, 4), "raw_score_delta": round(raw, 4),
            "qwk": qwk, "exact_major": exact_major, "penalty_major": penalty_major, "unsupported": unsup}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ds = _arm2_index()
    pidx = _pidx()
    votes = _votes()
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in _read(SRC / "loo_gold_485_flat.json")}
    keys = [k for k in gold if k in ds]

    # always-abstain: exact_required fallback triggers (踩字 quarantine, pre-existing)
    fallback_review = {k for k in keys if _exact_fallback(ds[k], pidx.get(k, {}))}
    # risk per candidate positive (not already in fallback)
    cand = {k: risk_score(ds[k], pidx.get(k, {}), votes.get(k)) for k in keys if k not in fallback_review}
    positive_cands = {k: r for k, r in cand.items() if r >= 0}

    total = len(keys)
    rows = []
    thresholds = sorted(set(round(v, 1) for v in positive_cands.values()), reverse=True) + [-0.1]
    selected = None
    for tau in thresholds:
        abstain = {k for k, r in positive_cands.items() if r >= tau}
        review = fallback_review | abstain
        certified = [k for k in keys if k not in review]
        m = metrics_on(certified, ds, pidx, gold)
        hrr = round(len(review) / total, 4)
        cov = round(len(certified) / total, 4)
        rows.append({"tau": tau, "abstained": len(abstain), "high_risk_review": len(review), "high_risk_review_ratio": hrr,
                     "auto_coverage": cov, **m})
        ok = (m["exact_major"] == 0 and m["unsupported"] == 0 and m["penalty_major"] == 0 and m["auto_hit"] >= 0.94 and hrr <= 0.10)
        if ok and selected is None:
            selected = {"tau": tau, "high_risk_review_ratio": hrr, "auto_coverage": cov, **m,
                        "abstained_points": sorted(k for k in abstain)}

    with (out / "risk_coverage_curve.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (out / "selected_threshold.json").write_text(json.dumps(selected or {"note": "no threshold met auto_hit>=0.94 with hrr<=10% under hard gates"}, ensure_ascii=False, indent=2), encoding="utf-8")

    # abstained points detail at selected tau
    if selected:
        with (out / "abstained_points.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "student_id", "point_id", "policy_type", "deepseek_hit", "deepseek_score", "risk", "reason"])
            for k in selected["abstained_points"]:
                w.writerow([k[0], k[1], k[2], pidx.get(k, {}).get("policy_type"), ds[k].get("hit"), ds[k].get("score"), positive_cands[k], "jury_disagree+weak_signal"])

    # certified subset metrics (final operating point) + 3 gate readings
    final_review = (fallback_review | set(map(tuple, [tuple(p) for p in (selected["abstained_points"] if selected else [])])))
    certified = [k for k in keys if k not in final_review]
    cm = metrics_on(certified, ds, pidx, gold)
    npq = round(sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) / (1) for k in certified) / (len(certified) or 1), 4)  # placeholder; per-question below not needed
    legacy = "STRONG-GO" if (cm["auto_hit"] >= 0.94 and cm["raw_score_delta"] <= 0.05 and cm["exact_major"] == 0 and cm["unsupported"] == 0 and cm["penalty_major"] == 0) else ("WEAK-GO" if (cm["auto_hit"] >= 0.90 and cm["exact_major"] == 0 and cm["unsupported"] == 0) else "NO-GO")
    v2 = "STRONG-candidate" if (cm["qwk"] >= 0.85 and cm["exact_major"] == 0 and cm["unsupported"] == 0 and cm["penalty_major"] == 0 and cm["auto_hit"] >= 0.94 and (selected and selected["high_risk_review_ratio"] <= 0.10)) else ("WEAK-candidate" if cm["qwk"] >= 0.75 and cm["exact_major"] == 0 and cm["unsupported"] == 0 else "NO-GO")
    cm_out = {"certified_subset": cm, "high_risk_review_ratio": (selected or {}).get("high_risk_review_ratio"),
              "gate_readings": {
                  "legacy_raw_score_delta_gate": legacy,
                  "metric_v2_qwk_candidate_gate": v2 + " (candidate_only)",
                  "product_test_gate": "OK for test-env A/B in AI-Draft/shadow/teacher-review mode only — NOT a production accuracy claim" if cm["exact_major"] == 0 and cm["unsupported"] == 0 else "NOT OK",
              }}
    (out / "certified_subset_metrics.json").write_text(json.dumps(cm_out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total gold points: {total} | exact_fallback review: {len(fallback_review)}")
    if selected:
        print(f"SELECTED tau={selected['tau']}: high_risk_review={selected['high_risk_review_ratio']} auto_coverage={selected['auto_coverage']} "
              f"auto_hit={selected['auto_hit']} qwk={selected['qwk']} raw_delta={selected['raw_score_delta']} exact_major={selected['exact_major']} unsup={selected['unsupported']}")
    else:
        print("NO threshold reached auto_hit>=0.94 with hrr<=10% under hard gates")
    print(f"GATE readings: legacy={cm_out['gate_readings']['legacy_raw_score_delta_gate']} | v2={cm_out['gate_readings']['metric_v2_qwk_candidate_gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
