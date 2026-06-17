#!/usr/bin/env python3
"""R5: deterministic quality report for the FastAPI official MCQ fixture."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE_DIR = Path("tests/fixtures/luban_m35_fastapi_mcq_20q_100a")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _letters(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = raw
    else:
        values = list(str(raw or ""))
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def _point_scores(row: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for point in row.get("scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        if point_id.startswith("OPT_"):
            option = point_id.removeprefix("OPT_").upper()
            scores[option] = float(point.get("max_score") or 0.0)
    return scores


def _deterministic_score(row: dict[str, Any]) -> float:
    protocol = row.get("scoring_protocol") or {}
    correct = _letters(protocol.get("correct_answer") or row.get("correct_answer"))
    wrong_options = set(_letters(protocol.get("wrong_options") or []))
    selected = _letters(row.get("student_answer"))
    total_score = sum(_point_scores(row).values())
    if selected == correct:
        return round(total_score, 6)
    if any(option in wrong_options for option in selected):
        return 0.0
    per_option = float(protocol.get("partial_credit_per_selected_correct_option") or 0.5)
    return round(min(total_score, per_option * len([option for option in selected if option in correct])), 6)


def build_report(*, fixture: Path) -> dict[str, Any]:
    manifest_path = fixture / "manifest.json"
    answers_path = fixture / "student_answers.jsonl"
    manifest = _read_json(manifest_path)
    rows = _read_jsonl(answers_path)
    mismatches: list[dict[str, Any]] = []
    absolute_error = 0.0
    for row in rows:
        predicted = _deterministic_score(row)
        gold = float(row.get("gold_score") or 0.0)
        absolute_error += abs(predicted - gold)
        if predicted != gold:
            mismatches.append(
                {
                    "answer_id": row.get("answer_id"),
                    "predicted_score": predicted,
                    "gold_score": gold,
                }
            )
    answer_count = len(rows)
    return {
        "schema_version": "luban_m35_fastapi_mcq_quality.v1",
        "fixture": {
            "manifest_path": str(manifest_path),
            "answers_path": str(answers_path),
            "source": manifest.get("source"),
            "question_count": manifest.get("actual_question_count"),
            "answer_count": answer_count,
            "label_authority": manifest.get("label_authority"),
        },
        "metrics": {
            "exact_score_accuracy": round((answer_count - len(mismatches)) / answer_count, 6)
            if answer_count
            else 0.0,
            "score_mae": round(absolute_error / answer_count, 6) if answer_count else 0.0,
            "mismatch_count": len(mismatches),
            "variant_counts": dict(Counter(str(row.get("variant") or "") for row in rows)),
        },
        "authority": {
            "answer_key_authority": "generated_from_official_mcq_key",
            "quality_claim_allowed": True,
            "official_score_allowed": False,
            "basis": "deterministic replay against official MCQ answer key fixture",
        },
        "safety": {
            "db_write_count": 0,
            "remote_write_count": 0,
            "provider_call_count": 0,
            "canonical_truth_written": False,
        },
        "mismatches": mismatches[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(fixture=args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["metrics"]["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
