#!/usr/bin/env python3
"""Consensus-gold builder: derive a scalable grading gold from a multi-model panel.

Replaces mass human labeling with: (1) 4-model independent consensus, (2) a deterministic
list_rule k/n scorer that fixes the panel's only systematic blind spot (rounding near-complete
list answers up to hit), and (3) flagging the small split frontier for a thin human/official-key
calibration screw. NOT runtime — this builds the OFFLINE gold/regression set.

Method doc: docs/plan/评分引擎与金标工件/2026-06-03-luban-consensus-gold-protocol.md
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.build_luban_no_human_v1_5_golden import _anchor_normalized  # noqa: E402

DEFAULT_GOLDEN = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"


def _term_hit(term: str, answer: str) -> bool:
    nt = _anchor_normalized(term)
    return bool(nt) and nt in _anchor_normalized(answer)


def _point_meta(golden_path: Path) -> dict:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    meta = {}
    for c in golden["cases"]:
        for p in c.get("gold_scoring_points") or []:
            meta[(c["case_id"], p["point_id"])] = {
                "point_type": str(p.get("point_type") or ""),
                "list_rule": p.get("list_rule"),
                "max_score": float(p.get("max_score") or 0),
                "required_terms": [str(t) for t in (p.get("required_terms_v1_5") or []) if str(t).strip()],
            }
    return meta


def _arm(path: Path, name: str) -> dict:
    for ps in json.loads(path.read_text(encoding="utf-8")).get("prediction_sets") or []:
        if ps.get("arm") == name:
            return {(p["case_id"], p["student_id"], p["point_id"]): p for p in ps["predictions"]}
    return {}


def build_consensus_gold(*, model_arms: list[tuple[str, Path]], golden_path: Path, packet_path: Path, list_rule_deterministic: bool = False) -> dict:
    meta = _point_meta(golden_path)
    students = {}
    for t in json.loads(packet_path.read_text(encoding="utf-8"))["tasks"]:
        students[(t["case_id"], t["student_id"])] = t["student_answer"]
    models = {name: _arm(path, name) for name, path in model_arms}
    n_models = len(models)
    keys = set.intersection(*[set(m) for m in models.values()]) if models else set()

    gold = []
    for key in sorted(keys):
        cid, sid, pid = key
        m = meta.get((cid, pid), {})
        votes = {name: models[name][key] for name in models}
        labels = [str(v.get("hit") or "") for v in votes.values()]
        scores = {name: float(v.get("score") or 0) for name, v in votes.items()}
        answer = students.get((cid, sid), "")
        req = m.get("required_terms") or []
        max_score = m.get("max_score", 0.0)

        # (1) OPTIONAL list_rule deterministic k/n. DEFAULT OFF: validated WORSE than pure
        # panel consensus (required_terms regex mis-counts vs LLM semantic reading; fixed 2
        # blind spots but broke 7 — net regression 0.952 -> 0.913 on dev). Kept opt-in for
        # the record only.
        if list_rule_deterministic and m.get("list_rule") and len(req) >= 2:
            matched = [t for t in req if _term_hit(t, answer)]
            k, n = len(matched), len(req)
            score = round(k / n * max_score, 4) if n else 0.0
            label = "hit" if k == n and n else ("partial" if k else "miss")
            gold.append({**dict(zip(("case_id", "student_id", "point_id"), key)),
                         "gold_hit": label, "gold_score": score, "basis": "list_rule_deterministic",
                         "confidence": "high", "matched_terms": k, "total_terms": n,
                         "model_votes": {k2: v.get("hit") for k2, v in votes.items()}})
            continue

        # (2)(3)(4) panel consensus on hit-label.
        counts = {lab: labels.count(lab) for lab in set(labels)}
        top_label, top_n = max(counts.items(), key=lambda x: x[1])
        agree_scores = [scores[name] for name in models if str(votes[name].get("hit")) == top_label]
        cons_score = round(statistics.median(agree_scores), 4) if agree_scores else 0.0
        if top_n == n_models:
            basis, conf, label = "unanimous_consensus", "high", top_label
        elif top_n > n_models / 2:
            basis, conf, label = "majority_consensus", "medium", top_label
        else:
            basis, conf, label = "split_frontier_needs_human", "low", None
        gold.append({**dict(zip(("case_id", "student_id", "point_id"), key)),
                     "gold_hit": label, "gold_score": (cons_score if label else None), "basis": basis,
                     "confidence": conf, "model_votes": {name: votes[name].get("hit") for name in models}})

    return {"n_models": n_models, "n_points": len(gold), "gold": gold}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True, help="arm_name=path.json (repeat 3-4x)")
    ap.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--packet", required=True)
    ap.add_argument("--human", default="", help="optional po_labels_filled.csv to validate the auto-gold")
    ap.add_argument("--list-rule-deterministic", action="store_true", help="(off by default; validated worse)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    model_arms = []
    for spec in args.model:
        name, path = spec.split("=", 1)
        model_arms.append((name, Path(path)))
    result = build_consensus_gold(
        model_arms=model_arms, golden_path=Path(args.golden), packet_path=Path(args.packet),
        list_rule_deterministic=args.list_rule_deterministic,
    )

    from collections import Counter

    basis_counts = dict(Counter(g["basis"] for g in result["gold"]))
    result["basis_counts"] = basis_counts
    result["needs_human_calibration"] = [
        {k: g[k] for k in ("case_id", "student_id", "point_id", "model_votes")}
        for g in result["gold"] if g["basis"] == "split_frontier_needs_human"
    ]

    if args.human:
        import csv

        hum = {}
        for r in csv.DictReader(open(args.human, encoding="utf-8")):
            if (r.get("human_hit") or "").strip():
                hum[(r["case_id"], r["student_id"], r["point_id"])] = r["human_hit"].strip()
        auto = [g for g in result["gold"] if g["gold_hit"] is not None]
        checkable = [g for g in auto if (g["case_id"], g["student_id"], g["point_id"]) in hum]
        agree = sum(1 for g in checkable if g["gold_hit"] == hum[(g["case_id"], g["student_id"], g["point_id"])])
        result["validation_vs_human"] = {
            "auto_gold_points": len(auto), "checkable": len(checkable),
            "agree_with_human": agree, "agreement": round(agree / len(checkable), 4) if checkable else None,
        }

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("basis_counts:", basis_counts)
    print("needs_human_calibration:", len(result["needs_human_calibration"]))
    if args.human:
        print("validation_vs_human:", result["validation_vs_human"])
    print("out ->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
