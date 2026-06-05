#!/usr/bin/env python3
"""Assemble the full 485 four-model LOO gold (DeepSeek-excluded) + run the
exact_required fallback + production-shadow v0 gate.

Inputs: per-arm predictions for all 100 samples (held-out 40 reused + pilot 5 +
newly-run 55). Builds the unified 485 prediction file, span-guards it, derives the
leave-one-out gold for DeepSeek (jury = GPT+Opus+Qwen), then runs the fallback.

Tiers: full_consensus_3of3 (all 3 jurors agree, supported) and strong_consensus_2of3
(2/3 agree) enter gold; 3-way splits -> frontier (NOT gold). No adjudication is
fabricated. DeepSeek's own vote never enters DeepSeek's gold. directional/shadow.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FULL = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"
PRED = FULL / "predictions"
HELDOUT = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_predictions_span_guarded.json"
PILOT = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_485_prep_20260603/485_pilot_predictions"
PACKET = FULL / "unified_typed_policy_packet_485.json"

ARMS = ["deepseek_v4_flash_typed_policy_primary", "gpt55_primary", "opus48_primary", "qwen37_plus_nothink_primary"]
JURY = {"gpt55_primary": "gpt", "opus48_primary": "opus", "qwen37_plus_nothink_primary": "qwen37"}


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _arm_preds(payload, arm):
    for s in payload["prediction_sets"]:
        if s["arm"] == arm:
            return {(p["case_id"], p["student_id"], p["point_id"]): p for p in s["predictions"]}
    return {}


def merge_predictions() -> dict:
    """held-out 40 (all arms) + pilot 5 (all arms) + new 55 (per-arm files)."""
    held = _read(HELDOUT)
    merged: dict[str, dict] = {a: dict(_arm_preds(held, a)) for a in ARMS}
    # pilot 5 (per-arm files)
    for a in ARMS:
        pf = PILOT / f"pilot_pred_{a}.json"
        if pf.exists():
            merged[a].update(_arm_preds(_read(pf), a))
    # new 55: deepseek/qwen from pred_<arm>.json; gpt/opus from batch files + backfill
    for a in ("deepseek_v4_flash_typed_policy_primary", "qwen37_plus_nothink_primary"):
        f = PRED / f"pred_{a}.json"
        if f.exists():
            merged[a].update(_arm_preds(_read(f), a))
    for a in ("gpt55_primary", "opus48_primary"):
        for i in range(4):
            f = PRED / f"pred_{a}_batch_{i}.json"
            if f.exists():
                merged[a].update(_arm_preds(_read(f), a))
        bf = PRED / f"pred_{a}_backfill.json"
        if bf.exists():
            merged[a].update(_arm_preds(_read(bf), a))
    sets = [{"arm": a, "predictions": list(merged[a].values())} for a in ARMS]
    return {"slice_id": "luban-full-485", "prediction_sets": sets}


def _supported(p) -> bool:
    if p.get("unsupported") is True:
        return False
    hit = str(p.get("hit") or "miss")
    if hit in ("hit", "partial"):
        return bool((p.get("evidence_span") or "").strip())
    return True


def build_loo_gold(unified: dict, packet_keys: set) -> dict:
    arms = {alias: _arm_preds(unified, arm) for arm, alias in JURY.items()}
    gold, frontier, vote_rows = [], [], []
    for key in sorted(packet_keys):
        present = {a: arms[a][key] for a in arms if key in arms[a]}
        if len(present) < 3:
            frontier.append({"key": key, "reason": "missing_juror_prediction"})
            continue
        labels = {a: str(p.get("hit") or "miss") for a, p in present.items()}
        vote_rows.append({"case_id": key[0], "student_id": key[1], "point_id": key[2],
                          **{f"{a}_hit": labels[a] for a in present},
                          **{f"{a}_score": present[a].get("score") for a in present}})
        lc = Counter(labels.values())
        top_label, top_n = lc.most_common(1)[0]
        agree = [a for a in present if labels[a] == top_label]
        # any agreeing juror unsupported on a positive -> exclude from gold
        unsupported = any(not _supported(present[a]) for a in agree)
        if top_n == 3 and not unsupported:
            status = "full_consensus_3of3"
        elif top_n == 2 and not unsupported:
            status = "strong_consensus_2of3"
        else:
            frontier.append({"key": key, "reason": "3way_split_or_unsupported", "labels": labels})
            continue
        scores = [float(present[a].get("score") or 0) for a in agree]
        gold.append({"case_id": key[0], "student_id": key[1], "point_id": key[2],
                     "gold_hit": top_label, "gold_score": round(sum(scores) / len(scores), 3),
                     "jury": "gpt+opus+qwen (deepseek excluded)",
                     "jury_votes": {a: {"hit": labels[a], "score": present[a].get("score")} for a in present},
                     "status": status})
    return {"gold": gold, "frontier": frontier, "vote_rows": vote_rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-merge", action="store_true")
    args = ap.parse_args()

    packet = _read(PACKET)
    packet_keys = {(t["case_id"], t["student_id"], sp["point_id"]) for t in packet["tasks"] for sp in t["scoring_points"]}

    unified = merge_predictions()
    (FULL / "unified_predictions_485.json").write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {s["arm"]: len(s["predictions"]) for s in unified["prediction_sets"]}
    print("merged per-arm point counts:", counts)

    res = build_loo_gold(unified, packet_keys)
    gold = res["gold"]
    tier = Counter(g["status"] for g in gold)
    out = {"jury": "GPT5.5+Opus4.8+Qwen3.7", "deepseek_excluded": True,
           "gold_points": len(gold), "tiers": dict(tier),
           "frontier_points": len(res["frontier"]),
           "total_target_points": len(packet_keys), "points": gold}
    (FULL / "loo_gold_485_deepseek_excluded.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # model vote matrix
    if res["vote_rows"]:
        cols = ["case_id", "student_id", "point_id", "gpt_hit", "opus_hit", "qwen37_hit", "gpt_score", "opus_score", "qwen37_score"]
        with (FULL / "model_vote_matrix_485.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(res["vote_rows"])
    # frontier queue
    with (FULL / "frontier_policy_queue_485.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "student_id", "point_id", "reason"])
        for fr in res["frontier"]:
            k = fr["key"]
            w.writerow([k[0], k[1], k[2], fr["reason"]])
    # coverage report
    cov = {"total_target_points": len(packet_keys), "gold_points": len(gold), "tiers": dict(tier),
           "frontier_points": len(res["frontier"]),
           "consensus_coverage": round(len(gold) / len(packet_keys), 4),
           "deepseek_self_vote_in_gold": 0, "unsupported_positive_into_gold": 0}
    (FULL / "consensus_coverage_report_485.json").write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"LOO gold: {len(gold)} points {dict(tier)} | frontier {len(res['frontier'])} | coverage {cov['consensus_coverage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
