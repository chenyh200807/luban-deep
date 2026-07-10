#!/usr/bin/env python3
"""J01 governed-gold IRR + arbitration + freeze engine (阶段0, 我方自动化部分).

Reads ≥2 annotators' filled hit/miss labels for a J01 governed-gold slice and:
  1. validates each annotator against the frozen slice manifest (missing/invalid/extra);
  2. computes REAL inter-rater reliability — Cohen's κ (exactly 2 annotators) or
     Fleiss' κ (≥3) on the 3-class {hit,partial,miss} verdict, overall + per
     scoring-point (point_id);
  3. builds the arbitration queue (non-unanimous cells + points below the frozen κ
     gate) — these do NOT auto-enter gold;
  4. enforces evidence_span (verbatim substring of the student answer) + source_ref
     presence per hit/partial;
  5. freezes only the cells that pass (unanimous OR arbitration-resolved) AND span-valid
     AND whose point clears the κ gold gate → governed_gold_frozen.json with
     content_hash + version_id.

Red lines (baked in): gold = human; a SINGLE annotator is directional, NEVER gold
(refuses to freeze); κ is recomputable by a third party from (manifest + labels).
`fleiss_kappa=-0.05` (AI panel) is the standing counter-example that AI panels are
not gold — reproduced by the selftest's random-annotator arm.

Pure κ math (no sklearn dependency) so any third party can recompute. Offline,
no network, no production / canonical / writeback. `production_write_count == 0`.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

ALLOWED_HITS = ("hit", "partial", "miss")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _read_labels(path: Path) -> dict[str, dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = _read_json(path)
        rows = payload.get("labels") if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
    else:
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
    labels: dict[str, dict[str, Any]] = {}
    for row in rows:
        cell_id = str(row.get("cell_id") or "").strip()
        hit = str(row.get("human_hit") or "").strip()
        score_raw = str(row.get("human_score") or "").strip()
        if not cell_id or not hit or not score_raw:
            continue
        labels[cell_id] = {
            "human_hit": hit,
            "human_score": _to_float(score_raw),
            "evidence_span": str(row.get("evidence_span") or "").strip(),
            "human_error_codes": str(row.get("human_error_codes") or "").strip(),
            "human_note": str(row.get("human_note") or "").strip(),
        }
    return labels


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- IRR

def cohen_kappa(labels_a: list[str], labels_b: list[str], categories: tuple[str, ...]) -> float | None:
    """Cohen's κ for two raters over paired categorical labels."""
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        return None
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    pe = sum((count_a.get(c, 0) / n) * (count_b.get(c, 0) / n) for c in categories)
    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else None
    return round((po - pe) / (1.0 - pe), 4)


def fleiss_kappa(item_ratings: list[list[str]], categories: tuple[str, ...]) -> float | None:
    """Fleiss' κ for a fixed number of raters per item (n ≥ 3)."""
    if not item_ratings:
        return None
    n = len(item_ratings[0])
    if n < 2 or any(len(r) != n for r in item_ratings):
        return None
    big_n = len(item_ratings)
    cat_index = {c: i for i, c in enumerate(categories)}
    matrix: list[list[int]] = []
    for ratings in item_ratings:
        counts = [0] * len(categories)
        for label in ratings:
            if label in cat_index:
                counts[cat_index[label]] += 1
        matrix.append(counts)
    p_j = [sum(row[j] for row in matrix) / (big_n * n) for j in range(len(categories))]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in matrix]
    p_bar = mean(p_i)
    p_e = sum(p * p for p in p_j)
    if abs(1.0 - p_e) < 1e-12:
        return 1.0 if abs(p_bar - 1.0) < 1e-12 else None
    return round((p_bar - p_e) / (1.0 - p_e), 4)


def compute_irr(
    verdicts_by_annotator: dict[str, dict[str, str]], cell_ids: list[str]
) -> dict[str, Any]:
    annotators = sorted(verdicts_by_annotator)
    complete = [cid for cid in cell_ids if all(cid in verdicts_by_annotator[a] for a in annotators)]
    if len(annotators) < 2 or not complete:
        return {"method": None, "kappa": None, "annotators": annotators, "scored_cells": len(complete)}
    if len(annotators) == 2:
        a, b = annotators
        kappa = cohen_kappa(
            [verdicts_by_annotator[a][cid] for cid in complete],
            [verdicts_by_annotator[b][cid] for cid in complete],
            ALLOWED_HITS,
        )
        method = "cohen_kappa"
    else:
        item_ratings = [[verdicts_by_annotator[a][cid] for a in annotators] for cid in complete]
        kappa = fleiss_kappa(item_ratings, ALLOWED_HITS)
        method = "fleiss_kappa"
    return {"method": method, "kappa": kappa, "annotators": annotators, "scored_cells": len(complete)}


# ------------------------------------------------------------------- validation

def validate_annotator(
    *, annotator: str, labels: dict[str, dict[str, Any]], manifest_cells: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    missing, invalid = [], []
    for cid, cell in manifest_cells.items():
        label = labels.get(cid)
        if not label:
            missing.append(cid)
            continue
        if label["human_hit"] not in ALLOWED_HITS:
            invalid.append({"cell_id": cid, "field": "human_hit", "value": label["human_hit"]})
        score = label["human_score"]
        max_score = float(cell.get("max_score") or 0)
        if score is None or score < 0 or score > max_score + 1e-9:
            invalid.append({"cell_id": cid, "field": "human_score", "value": score, "max_score": max_score})
        if label["human_hit"] in ("hit", "partial") and not label["evidence_span"]:
            invalid.append({"cell_id": cid, "field": "evidence_span", "value": "empty_on_hit_or_partial"})
    extra = sorted(set(labels) - set(manifest_cells))
    return {
        "annotator": annotator,
        "expected": len(manifest_cells),
        "filled": sum(1 for cid in manifest_cells if cid in labels),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "extra_count": len(extra),
        "missing": missing,
        "invalid": invalid,
        "extra": extra,
        "is_complete": not missing and not invalid and not extra,
    }


def _span_valid(span: str, student_answer: str) -> bool:
    if not span:
        return False
    return span in (student_answer or "")


# ----------------------------------------------------------------- adjudication

def adjudicate(
    *,
    manifest: dict[str, Any],
    labels_by_annotator: dict[str, dict[str, dict[str, Any]]],
    arbiter_labels: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    manifest_cells = {str(c["cell_id"]): c for c in manifest.get("cells") or []}
    annotators = sorted(labels_by_annotator)
    thresholds = manifest.get("frozen_definitions", {}).get("irr_thresholds", {})
    gold_gate = float(thresholds.get("point_kappa_gold_gate", 0.6))
    warn_gate = float(thresholds.get("point_kappa_warn", 0.4))

    verdicts_by_annotator = {
        a: {cid: labels_by_annotator[a][cid]["human_hit"] for cid in labels_by_annotator[a]}
        for a in annotators
    }
    cell_ids = list(manifest_cells)

    overall_irr = compute_irr(verdicts_by_annotator, cell_ids)

    # per-point IRR
    per_point: dict[str, list[str]] = {}
    for cell in manifest_cells.values():
        per_point.setdefault(str(cell["point_id"]), []).append(str(cell["cell_id"]))
    per_point_irr: dict[str, Any] = {}
    for pid, cids in sorted(per_point.items()):
        per_point_irr[pid] = compute_irr(verdicts_by_annotator, cids)

    frozen_gold: list[dict[str, Any]] = []
    arbitration_queue: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    single_annotator = len(annotators) < 2

    for cid, cell in manifest_cells.items():
        votes = {a: labels_by_annotator[a].get(cid) for a in annotators}
        if any(v is None for v in votes.values()):
            rejected.append({"cell_id": cid, "reason": "incomplete_labels"})
            continue
        hits = [v["human_hit"] for v in votes.values()]
        unanimous = len(set(hits)) == 1
        student_answer = str(cell.get("student_answer_text") or "")
        span_ok = all(
            v["human_hit"] == "miss" or _span_valid(v["evidence_span"], student_answer)
            for v in votes.values()
        )
        source_ref_ok = bool(str(cell.get("source_ref") or "").strip())
        point_kappa = per_point_irr.get(str(cell["point_id"]), {}).get("kappa")
        point_gate_ok = point_kappa is not None and point_kappa >= gold_gate

        resolved_hit: str | None = None
        resolution = None
        if unanimous:
            resolved_hit = hits[0]
            resolution = "unanimous"
        elif arbiter_labels and cid in arbiter_labels:
            resolved_hit = arbiter_labels[cid]["human_hit"]
            resolution = "arbiter_resolved"

        record = {
            "cell_id": cid,
            "case_id": cell.get("case_id"),
            "student_id": cell.get("student_id"),
            "point_id": cell.get("point_id"),
            "annotator_hits": {a: votes[a]["human_hit"] for a in annotators},
            "annotator_scores": {a: votes[a]["human_score"] for a in annotators},
            "unanimous": unanimous,
            "point_kappa": point_kappa,
            "span_valid": span_ok,
            "source_ref_present": source_ref_ok,
            "resolution": resolution,
            "resolved_hit": resolved_hit,
        }

        if single_annotator:
            rejected.append({**record, "reason": "single_annotator_directional_not_gold"})
            continue
        if not span_ok:
            rejected.append({**record, "reason": "evidence_span_invalid"})
            continue
        if not source_ref_ok:
            rejected.append({**record, "reason": "missing_source_ref"})
            continue
        if resolved_hit is None:
            arbitration_queue.append({**record, "reason": "disagreement_no_arbiter"})
            continue
        if not point_gate_ok:
            arbitration_queue.append({**record, "reason": "point_kappa_below_gold_gate", "gold_gate": gold_gate})
            continue
        # passes all gates → gold-eligible
        scores = [votes[a]["human_score"] for a in annotators]
        frozen_gold.append(
            {
                "cell_id": cid,
                "case_id": cell.get("case_id"),
                "student_id": cell.get("student_id"),
                "point_id": cell.get("point_id"),
                "max_score": cell.get("max_score"),
                "gold_hit": resolved_hit,
                "gold_score": round(mean(scores), 4),
                "resolution": resolution,
                "point_kappa": point_kappa,
                "source_ref": cell.get("source_ref"),
                "evidence_spans": {a: votes[a]["evidence_span"] for a in annotators},
                "authority": "human_per_scoring_point_adjudication",
            }
        )

    point_reliability = {
        pid: (
            "gold_eligible"
            if (irr.get("kappa") is not None and irr["kappa"] >= gold_gate)
            else "arbitration" if (irr.get("kappa") is not None and irr["kappa"] >= warn_gate)
            else "redefine_point"
        )
        for pid, irr in per_point_irr.items()
    }

    frozen_gold_sorted = sorted(frozen_gold, key=lambda r: r["cell_id"])
    gold_content_hash = _hash_payload(frozen_gold_sorted)
    return {
        "slice_id": manifest.get("slice_id"),
        "schema_version": "luban_j01_governed_gold_result.v1",
        "annotators": annotators,
        "reviewer_count": len(annotators),
        "single_annotator_directional_only": single_annotator,
        "gold_authority": "human_per_scoring_point_adjudication",
        "overall_irr": overall_irr,
        "per_point_irr": per_point_irr,
        "point_reliability": point_reliability,
        "thresholds": {"point_kappa_gold_gate": gold_gate, "point_kappa_warn": warn_gate},
        "counts": {
            "cells_total": len(manifest_cells),
            "frozen_gold": len(frozen_gold_sorted),
            "arbitration_queue": len(arbitration_queue),
            "rejected": len(rejected),
        },
        "frozen_gold": frozen_gold_sorted,
        "arbitration_queue": arbitration_queue,
        "rejected": rejected,
        "gold_version": {
            "version_id": f"{manifest.get('slice_id')}::gold::{gold_content_hash[:12]}",
            "content_hash": gold_content_hash,
            "frozen_definitions_hash": _hash_payload(manifest.get("frozen_definitions", {})),
        },
        "redlines": {
            "gold_is_human_not_ai_panel": True,
            "ai_panel_counter_example": "fleiss_kappa=-0.05 (run_luban_arbitration_gold_panel.py) — AI 面板不可当金标",
            "single_reviewer_is_directional_not_gold": True,
            "kappa_recomputable_by_third_party_from_manifest_plus_labels": True,
        },
        "production_write_count": 0,
    }


def run(
    *, manifest_path: Path, label_specs: dict[str, Path], arbiter_path: Path | None
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    manifest_cells = {str(c["cell_id"]): c for c in manifest.get("cells") or []}
    labels_by_annotator = {name: _read_labels(path) for name, path in label_specs.items()}
    validations = [
        validate_annotator(annotator=name, labels=labels, manifest_cells=manifest_cells)
        for name, labels in sorted(labels_by_annotator.items())
    ]
    arbiter_labels = _read_labels(arbiter_path) if arbiter_path else None
    result = adjudicate(
        manifest=manifest, labels_by_annotator=labels_by_annotator, arbiter_labels=arbiter_labels
    )
    result["validations"] = validations
    result["source_hashes"] = {
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "labels_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in label_specs.items()
        },
    }
    return result


def _parse_labels(raw_list: list[str]) -> dict[str, Path]:
    specs: dict[str, Path] = {}
    for item in raw_list:
        if "=" not in item:
            raise SystemExit(f"--labels expects annotator=path, got {item!r}")
        name, path = item.split("=", 1)
        specs[name.strip()] = Path(path.strip())
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description="Score J01 governed-gold labels: IRR + arbitration + freeze.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", nargs="+", required=True, help="annotator=path (≥2 for gold).")
    parser.add_argument("--arbiter", default=None, help="Optional arbiter label file (resolves splits).")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = run(
        manifest_path=Path(args.manifest),
        label_specs=_parse_labels(args.labels),
        arbiter_path=Path(args.arbiter) if args.arbiter else None,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    # Keep stdout compact; full result goes to --output.
    print(json.dumps(
        {
            "slice_id": result["slice_id"],
            "reviewer_count": result["reviewer_count"],
            "overall_irr": result["overall_irr"],
            "counts": result["counts"],
            "gold_version": result["gold_version"],
        },
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
