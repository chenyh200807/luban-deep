#!/usr/bin/env python3
"""Score filled J01 governed-gold annotations: IRR (Cohen/Fleiss κ) + governed-gold artifact.

Inputs:  manifest.json (from build) + >=2 filled annotator CSVs (annotator_A.csv, ...).
Outputs: IRR report + adjudication queue + governed_gold.json (consensus rows + governance meta).

Trust discipline (eval-design / anti-self-attestation):
  - κ computed from INDEPENDENT annotator files; never auto-filled from AI.
  - Only rows with unanimous human agreement enter gold as `agreed`; disagreements go to an
    adjudication queue and are EXCLUDED from gold until a human resolves them.
  - Single-reviewer input is reported as `directional`, NOT gold.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

HIT_VALUES = ("hit", "partial", "miss")
# binary "credited" collapse: did the point earn credit at all?
CREDITED = {"hit": 1, "partial": 1, "miss": 0}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_annotator_labels(path: Path) -> dict[str, dict[str, Any]]:
    """row_id -> {human_hit, human_score, human_note}. Skips blank rows."""
    labels: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            hit = str(row.get("human_hit") or "").strip().lower()
            if not hit:
                continue
            rid = str(row.get("row_id") or "").strip()
            labels[rid] = {
                "human_hit": hit,
                "human_score": str(row.get("human_score") or "").strip(),
                "human_note": str(row.get("human_note") or "").strip(),
            }
    return labels


# ---------------------------------------------------------------------------
# kappa
# ---------------------------------------------------------------------------
def cohen_kappa(labels_a: list[str], labels_b: list[str], categories: tuple[str, ...]) -> float:
    """Cohen's κ for two raters over paired label lists."""
    n = len(labels_a)
    if n == 0:
        return float("nan")
    po = mean(1.0 if a == b else 0.0 for a, b in zip(labels_a, labels_b))
    ca, cb = Counter(labels_a), Counter(labels_b)
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in categories)
    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0
    return round((po - pe) / (1.0 - pe), 4)


def fleiss_kappa(item_ratings: list[list[str]], categories: tuple[str, ...]) -> float:
    """Fleiss' κ. item_ratings[i] = list of category labels for item i (same rater count n)."""
    items = [r for r in item_ratings if r]
    if not items:
        return float("nan")
    n = len(items[0])
    if n < 2 or any(len(r) != n for r in items):
        return float("nan")
    N = len(items)
    p_j = {c: 0 for c in categories}
    P_sum = 0.0
    for ratings in items:
        counts = Counter(ratings)
        for c in categories:
            p_j[c] += counts.get(c, 0)
        P_i = (sum(counts.get(c, 0) ** 2 for c in categories) - n) / (n * (n - 1))
        P_sum += P_i
    Pbar = P_sum / N
    total = N * n
    Pe = sum((p_j[c] / total) ** 2 for c in categories)
    if abs(1.0 - Pe) < 1e-12:
        return 1.0 if abs(Pbar - 1.0) < 1e-12 else 0.0
    return round((Pbar - Pe) / (1.0 - Pe), 4)


def kappa_block(rid_labels: dict[str, list[str]], categories: tuple[str, ...]) -> dict[str, Any]:
    """Compute κ over rows every annotator labelled. rid_labels: row_id -> [labels...]."""
    rated = {rid: labs for rid, labs in rid_labels.items() if len(labs) >= 2}
    if not rated:
        return {"n_rows": 0, "kappa": None, "method": None, "percent_agreement": None}
    n_raters = len(next(iter(rated.values())))
    complete = {rid: labs for rid, labs in rated.items() if len(labs) == n_raters}
    ordered = sorted(complete)
    item_ratings = [complete[rid] for rid in ordered]
    percent = round(mean(1.0 if len(set(labs)) == 1 else 0.0 for labs in item_ratings), 4) if item_ratings else None
    if n_raters == 2:
        a = [complete[rid][0] for rid in ordered]
        b = [complete[rid][1] for rid in ordered]
        return {"n_rows": len(ordered), "n_raters": 2, "method": "cohen",
                "kappa": cohen_kappa(a, b, categories), "percent_agreement": percent}
    return {"n_rows": len(ordered), "n_raters": n_raters, "method": "fleiss",
            "kappa": fleiss_kappa(item_ratings, categories), "percent_agreement": percent}


def kappa_interpretation(k: float | None) -> str:
    if k is None:
        return "n/a"
    if k < 0:
        return "worse-than-chance (RED — 反例, 不可当 gold)"
    if k < 0.20:
        return "slight"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial"
    return "almost-perfect"


# ---------------------------------------------------------------------------
# aggregation -> governed gold
# ---------------------------------------------------------------------------
def score(*, manifest_path: Path, label_paths: list[Path]) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    annotators = [p.stem for p in label_paths]
    per_annotator = {p.stem: read_annotator_labels(p) for p in label_paths}
    n_annotators = len(label_paths)

    # union of labelled row_ids, with row metadata carried from the first CSV that has it
    row_meta: dict[str, dict[str, Any]] = {}
    for p in label_paths:
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rid = str(r.get("row_id") or "").strip()
                if rid and rid not in row_meta:
                    row_meta[rid] = {
                        "qid": r.get("qid"), "sub_no": r.get("sub_no"), "student_id": r.get("student_id"),
                        "point_id": r.get("point_id"), "point_text": r.get("point_text"),
                        "j01_relevance": r.get("j01_relevance"),
                    }

    hit3: dict[str, list[str]] = {}
    hit2: dict[str, list[str]] = {}
    for rid in row_meta:
        for stem in annotators:
            lab = per_annotator[stem].get(rid)
            if not lab:
                continue
            h = lab["human_hit"]
            hit3.setdefault(rid, []).append(h)
            hit2.setdefault(rid, []).append(str(CREDITED.get(h, 0)))

    irr = {
        "hit_3category": {**kappa_block(hit3, HIT_VALUES),
                          "interpretation": kappa_interpretation(kappa_block(hit3, HIT_VALUES)["kappa"])},
        "credited_binary": {**kappa_block(hit2, ("0", "1")),
                            "interpretation": kappa_interpretation(kappa_block(hit2, ("0", "1"))["kappa"])},
    }
    # per relevance tier (3-category)
    tiers: dict[str, dict[str, list[str]]] = {}
    for rid, labs in hit3.items():
        tier = row_meta[rid].get("j01_relevance") or "unknown"
        tiers.setdefault(tier, {})[rid] = labs
    irr["by_relevance_tier"] = {t: kappa_block(d, HIT_VALUES) for t, d in sorted(tiers.items())}

    # governed gold: unanimous human agreement only
    gold_rows: list[dict[str, Any]] = []
    adjudication_queue: list[dict[str, Any]] = []
    for rid, labs in sorted(hit3.items()):
        meta = row_meta[rid]
        if len(labs) < 2:
            adjudication_queue.append({"row_id": rid, **meta, "labels": labs, "reason": "single_reviewer_directional"})
            continue
        if len(set(labs)) == 1:
            gold_rows.append({"row_id": rid, **meta, "gold_hit": labs[0], "agreement": "unanimous",
                              "reviewer_count": len(labs)})
        else:
            adjudication_queue.append({"row_id": rid, **meta, "labels": labs, "reason": "reviewer_disagreement"})

    complete_expected = manifest.get("expected_rows", 0)
    validation = {
        "expected_rows": complete_expected,
        "rows_with_any_label": len(hit3),
        "rows_multi_reviewer": sum(1 for labs in hit3.values() if len(labs) >= 2),
        "annotators": annotators,
        "n_annotators": n_annotators,
        "meets_min_reviewers": n_annotators >= manifest.get("min_reviewers_for_irr", 2),
    }

    status = "governed_gold" if (validation["meets_min_reviewers"] and gold_rows and not adjudication_queue) else (
        "gold_partial_needs_adjudication" if validation["meets_min_reviewers"] else "directional_single_reviewer")

    return {
        "slice_version": manifest.get("slice_version"),
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "manifest_content_hash": manifest.get("content_hash"),
        "source_hashes": manifest.get("source_hashes"),
        "status": status,
        "validation": validation,
        "irr": irr,
        "gold_rows": gold_rows,
        "adjudication_queue": adjudication_queue,
        "governance": {
            "gold_row_count": len(gold_rows),
            "adjudication_count": len(adjudication_queue),
            "gold_definition": "unanimous multi-reviewer agreement on hit/partial/miss; disagreements excluded pending adjudication.",
            "red_line": "单标注人=directional 不得称 gold；κ<0 是反例；AI 面板不得补 gold。",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score J01 governed-gold annotations (IRR + governed gold).")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", required=True, nargs="+", help="filled annotator CSVs (>=2 for IRR)")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = score(manifest_path=Path(args.manifest), label_paths=[Path(p) for p in args.labels])
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    # concise console summary
    print(json.dumps({
        "status": result["status"],
        "irr_hit3_kappa": result["irr"]["hit_3category"]["kappa"],
        "irr_credited_binary_kappa": result["irr"]["credited_binary"]["kappa"],
        "gold_rows": result["governance"]["gold_row_count"],
        "adjudication": result["governance"]["adjudication_count"],
        "validation": result["validation"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
