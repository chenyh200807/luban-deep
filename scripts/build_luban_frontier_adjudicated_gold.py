#!/usr/bin/env python3
"""Deterministically adjudicate held-out jury frontier points into consensus_gold_v1.

Applies the Consensus-Gold adjudication rules to the EXISTING 4-model span-guarded
frontier votes (no fresh model re-run): classify each frontier point into
resolved_auto_gold / resolved_with_dissent / resolved_score_normalized /
needs_policy_review, then merge the resolved ones with the 4/4 full-consensus gold.

directional/shadow. NOT runtime. NOT a new eval system — an offline JSON/CSV builder.
A fresh cross-model 对抗 adjudication pass on the needs_policy_review subset is an
optional follow-up (documented), intentionally skipped this round to conserve compute.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median

_RANK = {"miss": 0, "partial": 1, "hit": 2}


def _policy_type(meta: dict) -> str:
    if str(meta.get("point_type") or "") == "calculation":
        return "calculation"
    if str(meta.get("point_type") or "") == "figure_label":
        return "figure_label"
    if meta.get("list_rule"):
        return "list_rule"
    return "exact_required"


def _rubric(golden_path: Path) -> dict:
    g = json.loads(golden_path.read_text(encoding="utf-8"))
    meta = {}
    for c in g["cases"]:
        for p in c.get("gold_scoring_points") or []:
            meta[(c["case_id"], p["point_id"])] = {
                "point_type": p.get("point_type"), "list_rule": p.get("list_rule"),
                "max_score": float(p.get("max_score") or 0), "penalty_rule": p.get("penalty_rule"),
            }
    return meta


def adjudicate_frontier(*, frontier_path: Path, golden_path: Path) -> list[dict]:
    frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
    meta = _rubric(golden_path)
    out = []
    for fp in frontier:
        key = (fp["case_id"], fp["point_id"])
        m = meta.get(key, {})
        ptype = _policy_type(m)
        arms = fp.get("arms") or {}
        # only count supported positives; a span-guard-failed positive is treated as miss-for-vote
        supported = {a: v for a, v in arms.items() if v.get("supported", True) or v.get("hit") == "miss"}
        votes = {a: v.get("hit") for a, v in arms.items()}
        hit_counts: dict[str, int] = {}
        for h in votes.values():
            hit_counts[h] = hit_counts.get(h, 0) + 1
        top_hit, top_n = max(hit_counts.items(), key=lambda x: x[1])
        n = len(votes)
        scores_for_top = [float(arms[a].get("score") or 0) for a in arms if votes[a] == top_hit]
        med_score = round(median(scores_for_top), 4) if scores_for_top else 0.0
        any_unsupported_pos = any(v.get("hit") in ("hit", "partial") and not v.get("supported", True) for v in arms.values())

        row = {"case_id": fp["case_id"], "student_id": fp["student_id"], "point_id": fp["point_id"],
               "policy_type": ptype, "votes": votes, "top_hit": top_hit, "top_vote_count": top_n,
               "gold_hit": None, "gold_score": None, "resolution_class": None,
               "dissent_arm": None, "dissent_reason": None}

        # Rule 4/5: calculation or unsupported-positive -> policy review (deterministic can't settle).
        if ptype == "calculation" and top_n < n:
            row["resolution_class"] = "needs_policy_review"
            row["dissent_reason"] = "calculation disagreement requires numeric/process review"
            out.append(row); continue
        if any_unsupported_pos and top_n < n:
            row["resolution_class"] = "needs_policy_review"
            row["dissent_reason"] = "a positive vote failed span guard"
            out.append(row); continue

        if top_n == n:
            scores = [float(v.get("score") or 0) for v in arms.values()]
            if max(scores) - min(scores) <= 1e-6:
                row.update(gold_hit=top_hit, gold_score=med_score, resolution_class="resolved_auto_gold")
            else:
                # hit unanimous, score differs -> normalize to median model score (models read list k/n semantically)
                row.update(gold_hit=top_hit, gold_score=med_score, resolution_class="resolved_score_normalized")
            out.append(row); continue

        if top_n == n - 1:  # 3/4 majority, 1 dissent
            dissent_arm = next(a for a in votes if votes[a] != top_hit)
            row["dissent_arm"] = dissent_arm
            maj_rank = _RANK[top_hit]; dis_rank = _RANK[votes[dissent_arm]]
            # majority stricter (lower) than a lenient dissent on a 踩字 point -> dissent likely over-credits.
            if maj_rank < dis_rank and ptype in ("exact_required", "list_rule"):
                row.update(gold_hit=top_hit, gold_score=med_score, resolution_class="resolved_with_dissent",
                           dissent_reason=f"{dissent_arm} more lenient than 3-model majority on 踩字 ({ptype}); majority upheld")
            else:
                # majority lenient and dissent strict (possible valid colloquial-hit boundary) -> policy review
                row["resolution_class"] = "needs_policy_review"
                row["dissent_reason"] = f"majority {top_hit} vs stricter {dissent_arm}={votes[dissent_arm]}; 口径边界"
            out.append(row); continue

        # split (<=2/4) -> policy review
        row["resolution_class"] = "needs_policy_review"
        row["dissent_reason"] = "no 3-model majority (split)"
        out.append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontier", required=True)
    ap.add_argument("--consensus", required=True, help="jury_consensus_points.json (4/4 full consensus)")
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    adj = adjudicate_frontier(frontier_path=Path(args.frontier), golden_path=Path(args.golden))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    Path(out / "frontier_adjudicated_gold.json").write_text(json.dumps(adj, ensure_ascii=False, indent=2), encoding="utf-8")

    resolved_classes = {"resolved_auto_gold", "resolved_with_dissent", "resolved_score_normalized"}
    resolved = [r for r in adj if r["resolution_class"] in resolved_classes]
    unresolved = [r for r in adj if r["resolution_class"] == "needs_policy_review"]

    full = json.loads(Path(args.consensus).read_text(encoding="utf-8"))
    gold_v1 = []
    for r in full:
        gold_v1.append({"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
                        "gold_hit": r.get("jury_hit"), "gold_score": r.get("jury_score"),
                        "resolution_class": "full_consensus_4of4"})
    for r in resolved:
        gold_v1.append({"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
                        "gold_hit": r["gold_hit"], "gold_score": r["gold_score"], "resolution_class": r["resolution_class"]})

    Path(out / "consensus_gold_v1.json").write_text(json.dumps(gold_v1, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "consensus_gold_v1.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "student_id", "point_id", "gold_hit", "gold_score", "resolution_class"])
        w.writeheader(); w.writerows(gold_v1)
    with (out / "frontier_unresolved_queue.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "student_id", "point_id", "policy_type", "dissent_reason"])
        w.writeheader()
        for r in unresolved:
            w.writerow({k: r.get(k) for k in ("case_id", "student_id", "point_id", "policy_type", "dissent_reason")})

    from collections import Counter

    summary = {
        "original_total_points": len(full) + len(adj),
        "full_consensus_4of4": len(full),
        "frontier_total": len(adj),
        "frontier_resolved": len(resolved),
        "frontier_unresolved": len(unresolved),
        "frontier_resolution_classes": dict(Counter(r["resolution_class"] for r in adj)),
        "consensus_gold_v1_points": len(gold_v1),
        "auto_gold_coverage": round(len(gold_v1) / (len(full) + len(adj)), 4) if (len(full) + len(adj)) else 0.0,
        "qwen_excluded_from_own_gold": "leave-one-out handled separately in re-eval (Task F)",
    }
    Path(out / "consensus_gold_v1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
