#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _avg(values: list[float]) -> float:
    return round(float(mean(values)), 4) if values else 0.0


def _read_labels(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows: list[dict[str, Any]]
    if path.suffix.lower() == ".json":
        payload = _read_json(path)
        rows = payload.get("labels") if isinstance(payload.get("labels"), list) else []
    else:
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
    labels: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        hit = str(row.get("human_hit") or "").strip()
        score_raw = str(row.get("human_score") or "").strip()
        if not hit or not score_raw:
            continue
        key = (str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))
        labels[key] = {
            "human_hit": hit,
            "human_score": float(score_raw),
            "human_note": row.get("human_note") or "",
            "human_error_codes": row.get("human_error_codes") or "",
        }
    return labels


def _ledger_scores(sample: dict[str, Any]) -> dict[str, float]:
    return {str(row.get("point_id")): float(row.get("gold_score") or 0) for row in sample.get("ledger_point_rows") or []}


def _ledger_hits(sample: dict[str, Any]) -> dict[str, str]:
    return {str(row.get("point_id")): str(row.get("ledger_hit") or "") for row in sample.get("ledger_point_rows") or []}


def _artifact_scores(sample: dict[str, Any]) -> dict[str, float]:
    return {str(key): float(value or 0) for key, value in (sample.get("artifact_point_scores") or {}).items()}


def _compare(
    *,
    samples: list[dict[str, Any]],
    labels: dict[tuple[str, str, str], dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    score_deltas: list[float] = []
    hit_matches: list[float] = []
    disagreements: list[dict[str, Any]] = []
    completed_samples = 0
    for sample in samples:
        case_id = str(sample["case_id"])
        student_id = str(sample["student_id"])
        ledger_score_map = _ledger_scores(sample)
        target_scores = ledger_score_map if target == "ledger" else _artifact_scores(sample)
        target_hits = _ledger_hits(sample)
        point_ids = sorted(ledger_score_map)
        if not all((case_id, student_id, point_id) in labels for point_id in point_ids):
            continue
        completed_samples += 1
        human_total = 0.0
        target_total = 0.0
        for point_id in point_ids:
            label = labels[(case_id, student_id, point_id)]
            human_score = float(label["human_score"])
            target_score = float(target_scores.get(point_id, 0))
            human_total += human_score
            target_total += target_score
            human_hit = str(label["human_hit"])
            compare_hit = target_hits.get(point_id, "hit" if target_score > 0 else "miss") if target == "ledger" else ("hit" if target_score > 0 else "miss")
            hit_matches.append(1.0 if human_hit == compare_hit else 0.0)
            if abs(human_score - target_score) > 1e-6 or human_hit != compare_hit:
                disagreements.append(
                    {
                        "case_id": case_id,
                        "student_id": student_id,
                        "point_id": point_id,
                        "human_hit": human_hit,
                        "target_hit": compare_hit,
                        "human_score": round(human_score, 4),
                        "target_score": round(target_score, 4),
                        "target": target,
                        "note": label.get("human_note") or "",
                    }
                )
        score_deltas.append(abs(human_total - target_total))
    return {
        "target": target,
        "sample_count": completed_samples,
        "point_count": len(hit_matches),
        "mean_abs_score_delta": _avg(score_deltas),
        "point_hit_agreement": _avg(hit_matches),
        "disagreements": disagreements,
    }


def score_human_labels(*, manifest_path: Path, labels_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    labels = _read_labels(labels_path)
    samples = manifest.get("selected_samples") or []
    return {
        "slice_id": manifest.get("slice_id"),
        "label_file": str(labels_path),
        "human_vs_ledger": _compare(samples=samples, labels=labels, target="ledger"),
        "human_vs_artifact_first": _compare(samples=samples, labels=labels, target="artifact_first"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Luban v1 human validation labels.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = score_human_labels(manifest_path=Path(args.manifest), labels_path=Path(args.labels))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
