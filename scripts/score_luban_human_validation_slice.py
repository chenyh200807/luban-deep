#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
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


def parse_review_book_markdown(markdown: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_case_id = ""
    current_student_id = ""
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        case_match = re.match(r"^#\s+\d+\.\s+([^\s（(]+)", line)
        if case_match:
            current_case_id = case_match.group(1).strip()
            current_student_id = ""
            continue
        student_match = re.match(r"^###\s+学生\s+([A-Za-z0-9_-]+)", line)
        if student_match:
            current_student_id = student_match.group(1).strip()
            continue
        if not (line.startswith("| P") and current_case_id and current_student_id):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        point_id, _max_score, human_hit, human_score = cells[:4]
        human_note = "|".join(cells[4:]).strip()
        rows.append(
            {
                "case_id": current_case_id,
                "student_id": current_student_id,
                "point_id": point_id,
                "human_hit": human_hit,
                "human_score": human_score,
                "human_error_codes": "",
                "human_note": human_note,
            }
        )
    return rows


def write_labels_csv_from_review_book(*, review_book_path: Path, template_path: Path, output_path: Path) -> dict[str, Any]:
    parsed = parse_review_book_markdown(review_book_path.read_text(encoding="utf-8"))
    parsed_by_key = {
        (row["case_id"], row["student_id"], row["point_id"]): row
        for row in parsed
    }
    template_rows = list(csv.DictReader(template_path.open(encoding="utf-8")))
    fieldnames = list(template_rows[0]) if template_rows else [
        "case_id",
        "student_id",
        "point_id",
        "max_score",
        "point_label",
        "human_hit",
        "human_score",
        "human_error_codes",
        "human_note",
    ]
    output_rows: list[dict[str, Any]] = []
    matched_keys: set[tuple[str, str, str]] = set()
    for template_row in template_rows:
        key = (template_row["case_id"], template_row["student_id"], template_row["point_id"])
        filled = parsed_by_key.get(key)
        row = dict(template_row)
        if filled:
            matched_keys.add(key)
            row["human_hit"] = filled["human_hit"]
            row["human_score"] = filled["human_score"]
            row["human_error_codes"] = filled.get("human_error_codes") or ""
            row["human_note"] = filled.get("human_note") or ""
        output_rows.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    extra = [
        {"case_id": case_id, "student_id": student_id, "point_id": point_id}
        for case_id, student_id, point_id in sorted(set(parsed_by_key) - matched_keys)
    ]
    return {
        "parsed_row_count": len(parsed),
        "template_row_count": len(template_rows),
        "matched_row_count": len(matched_keys),
        "extra_rows": extra,
        "output": str(output_path),
    }


def validate_human_labels(*, manifest: dict[str, Any], labels: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    allowed_hits = {"hit", "partial", "miss"}
    expected: dict[tuple[str, str, str], float] = {}
    for sample in manifest.get("selected_samples") or []:
        for point in sample.get("ledger_point_rows") or []:
            expected[(str(sample["case_id"]), str(sample["student_id"]), str(point["point_id"]))] = float(point.get("max_score") or 0)

    missing = []
    invalid = []
    for key, max_score in expected.items():
        label = labels.get(key)
        if not label:
            missing.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "reason": "missing"})
            continue
        hit = str(label.get("human_hit") or "").strip()
        score = label.get("human_score")
        if hit not in allowed_hits:
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "human_hit", "value": hit})
        try:
            score_float = float(score)
        except (TypeError, ValueError):
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "human_score", "value": score})
            continue
        if score_float < 0 or score_float > max_score:
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "human_score", "value": score_float, "max_score": max_score})

    extra = [
        {"case_id": key[0], "student_id": key[1], "point_id": key[2]}
        for key in sorted(set(labels) - set(expected))
    ]
    return {
        "expected_label_count": len(expected),
        "filled_label_count": sum(1 for key in expected if key in labels),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "extra_count": len(extra),
        "missing": missing,
        "invalid": invalid,
        "extra": extra,
        "is_complete": not missing and not invalid and not extra,
        "reviewer_count": 1,
        "irr_status": "single_reviewer_directional_not_inter_rater_reliability",
    }


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
    validation = validate_human_labels(manifest=manifest, labels=labels)
    return {
        "slice_id": manifest.get("slice_id"),
        "label_file": str(labels_path),
        "validation": validation,
        "human_vs_ledger": _compare(samples=samples, labels=labels, target="ledger"),
        "human_vs_artifact_first": _compare(samples=samples, labels=labels, target="artifact_first"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Luban v1 human validation labels.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output")
    parser.add_argument("--review-book")
    parser.add_argument("--template")
    parser.add_argument("--write-labels-csv")
    args = parser.parse_args()
    conversion = None
    labels_path = Path(args.labels)
    if args.review_book:
        if not args.template or not args.write_labels_csv:
            raise SystemExit("--review-book requires --template and --write-labels-csv")
        labels_path = Path(args.write_labels_csv)
        conversion = write_labels_csv_from_review_book(
            review_book_path=Path(args.review_book),
            template_path=Path(args.template),
            output_path=labels_path,
        )
    result = score_human_labels(manifest_path=Path(args.manifest), labels_path=labels_path)
    if conversion:
        result["review_book_conversion"] = conversion
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
