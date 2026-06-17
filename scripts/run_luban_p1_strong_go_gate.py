#!/usr/bin/env python3
"""P1 Strong GO gate for the M35 Nexus-like scoring artifact engine.

This is a read-only aggregation gate. It does not call providers, write DB,
publish registries, or promote canonical learner truth. It only answers whether
the governed-label subset has enough authority and metrics for a P1 scoring
engine Strong GO.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/p1_strong_go_20260611"
DEFAULT_GOLD = (
    ROOT
    / "artifacts/luban_grading_artifacts/m35_gold_labeling_full_v3_protocol_fixed"
    / "student_answers.jsonl"
)
DEFAULT_PER_ROW = (
    ROOT
    / "artifacts/luban_grading_artifacts/four_arm_ab_20260611"
    / "live_full_162_v5_patched_gold/per_row.jsonl"
)
DEFAULT_AB_REPORT = (
    ROOT
    / "artifacts/luban_grading_artifacts/four_arm_ab_20260611"
    / "live_full_162_v5_patched_gold/report.json"
)

ARMS = ("legacy", "current_rag_offline", "artifact_first_compiled", "artifact_first_llm_judge")
OVER_CREDIT_MARGIN_RATIO = 0.2


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("question_id") or ""), str(row.get("student_id") or ""))


def _per_row_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row.get("question_id") or ""), str(row.get("student_id") or ""), str(row.get("arm") or "")): row
        for row in rows
    }


def _gold_hit_ids(row: dict[str, Any]) -> set[str]:
    return {
        str(point.get("point_id") or "")
        for point in list(row.get("gold_point_matches") or [])
        if str(point.get("status") or "") in {"hit", "partial"}
    }


def _predicted_hit_ids(row: dict[str, Any]) -> set[str]:
    return {
        str(point.get("point_id") or "")
        for point in list(row.get("point_matches") or [])
        if str(point.get("status") or "") in {"hit", "partial"}
    }


def _round_mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _summarize_scope(
    *,
    gold_rows: list[dict[str, Any]],
    per_index: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    missing_predictions: dict[str, int] = {}
    for arm in ARMS:
        deltas: list[float] = []
        fail_open: list[float] = []
        tokens: list[float] = []
        latencies: list[float] = []
        high_risk: list[float] = []
        evidence_ok = 0
        pred_hit_total = 0
        true_positive = 0
        false_positive = 0
        false_negative = 0
        missing = 0

        for gold in gold_rows:
            pred = per_index.get((_row_key(gold)[0], _row_key(gold)[1], arm))
            if not pred:
                missing += 1
                continue
            gold_score = float(gold.get("gold_score") or 0.0)
            predicted_score = float(pred.get("predicted_score") or 0.0)
            max_score = sum(float(point.get("max_score") or 0.0) for point in list(gold.get("gold_point_matches") or []))
            deltas.append(abs(predicted_score - gold_score))
            fail_open.append(
                1.0 if predicted_score > gold_score + OVER_CREDIT_MARGIN_RATIO * max(max_score, 1e-9) else 0.0
            )
            if pred.get("token_total") is not None:
                tokens.append(float(pred["token_total"]))
            if pred.get("latency_ms") is not None:
                latencies.append(float(pred["latency_ms"]))
            high_risk.append(1.0 if pred.get("high_risk_review") else 0.0)

            if arm == "artifact_first_llm_judge":
                gold_hits = _gold_hit_ids(gold)
                pred_hits = _predicted_hit_ids(pred)
                true_positive += len(gold_hits & pred_hits)
                false_positive += len(pred_hits - gold_hits)
                false_negative += len(gold_hits - pred_hits)
                hit_points = [
                    point
                    for point in list(pred.get("point_matches") or [])
                    if str(point.get("status") or "") in {"hit", "partial"}
                ]
                pred_hit_total += len(hit_points)
                evidence_ok += sum(1 for point in hit_points if str(point.get("evidence_span") or "").strip())

        point_precision = None
        point_recall = None
        evidence_span_rate = None
        if arm == "artifact_first_llm_judge":
            point_precision = round(true_positive / (true_positive + false_positive), 4) if true_positive + false_positive else 1.0
            point_recall = round(true_positive / (true_positive + false_negative), 4) if true_positive + false_negative else 1.0
            evidence_span_rate = round(evidence_ok / pred_hit_total, 4) if pred_hit_total else 1.0

        summary[arm] = {
            "sample_count": len(gold_rows) - missing,
            "score_mae": _round_mean(deltas),
            "fail_open_rate": _round_mean(fail_open),
            "point_precision": point_precision,
            "point_recall": point_recall,
            "evidence_span_rate": evidence_span_rate,
            "mean_token": _round_mean(tokens),
            "mean_latency_ms": _round_mean(latencies),
            "high_risk_review_rate": _round_mean(high_risk),
        }
        missing_predictions[arm] = missing

    return {"summary": summary, "missing_predictions": missing_predictions}


def _safety_zero(report: dict[str, Any]) -> bool:
    safety = report.get("safety") or {}
    expected = {
        "production_write_count": 0,
        "db_write_count": 0,
        "remote_write_count": 0,
        "canonical_truth_written": False,
        "published_registry_written": False,
        "official_score_allowed": False,
        "is_release_truth": False,
    }
    return all(safety.get(key) == value for key, value in expected.items())


def _phase1_blockers(
    *,
    sample_count: int,
    min_governed_rows: int,
    summary: dict[str, Any],
    missing_predictions: dict[str, int],
    provider_call_count: int,
    safety_zero: bool,
) -> list[str]:
    judge = summary["artifact_first_llm_judge"]
    legacy = summary["legacy"]
    blockers: list[str] = []
    if sample_count < min_governed_rows:
        blockers.append("governed_sample_below_threshold")
    if any(missing_predictions.values()):
        blockers.append("missing_arm_predictions")
    if provider_call_count <= 0:
        blockers.append("live_provider_not_exercised")
    if not safety_zero:
        blockers.append("safety_invariant_not_zero")
    if judge["score_mae"] is None or legacy["score_mae"] is None or judge["score_mae"] >= legacy["score_mae"]:
        blockers.append("judge_mae_not_better_than_legacy")
    if (
        judge["fail_open_rate"] is None
        or legacy["fail_open_rate"] is None
        or judge["fail_open_rate"] > legacy["fail_open_rate"]
        or judge["fail_open_rate"] > 0.01
    ):
        blockers.append("judge_fail_open_not_strong_enough")
    if judge["point_precision"] is None or judge["point_precision"] < 0.99:
        blockers.append("judge_point_precision_below_threshold")
    if judge["point_recall"] is None or judge["point_recall"] < 0.99:
        blockers.append("judge_point_recall_below_threshold")
    if judge["evidence_span_rate"] is None or judge["evidence_span_rate"] < 0.99:
        blockers.append("judge_evidence_span_below_threshold")
    return blockers


def build_p1_strong_go_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    gold_path: str | Path = DEFAULT_GOLD,
    per_row_path: str | Path = DEFAULT_PER_ROW,
    ab_report_path: str | Path = DEFAULT_AB_REPORT,
    min_governed_rows: int = 100,
) -> dict[str, Any]:
    gold_rows_all = _read_jsonl(Path(gold_path))
    per_rows = _read_jsonl(Path(per_row_path))
    ab_report = json.loads(Path(ab_report_path).read_text(encoding="utf-8"))
    per_index = _per_row_index(per_rows)

    score_valid_rows = [
        row
        for row in gold_rows_all
        if row.get("gold_score") is not None and row.get("score_label_valid") is not False
    ]
    governed_rows = [row for row in score_valid_rows if row.get("label_authority") == "ai_governed_gold"]
    label_counts = dict(Counter(str(row.get("label_authority") or "missing") for row in gold_rows_all))
    invalid_score_label_count = len(gold_rows_all) - len(score_valid_rows)

    governed_metrics = _summarize_scope(gold_rows=governed_rows, per_index=per_index)
    full_metrics = _summarize_scope(gold_rows=score_valid_rows, per_index=per_index)
    provider_call_count = int(((ab_report.get("provider") or {}).get("provider_call_count") or 0))
    safety_ok = _safety_zero(ab_report)
    governed_blockers = _phase1_blockers(
        sample_count=len(governed_rows),
        min_governed_rows=min_governed_rows,
        summary=governed_metrics["summary"],
        missing_predictions=governed_metrics["missing_predictions"],
        provider_call_count=provider_call_count,
        safety_zero=safety_ok,
    )

    full_set_blockers: list[str] = []
    if any(row.get("label_authority") != "ai_governed_gold" for row in score_valid_rows):
        full_set_blockers.append("full_set_contains_non_governed_labels")
    if invalid_score_label_count:
        full_set_blockers.append("full_set_contains_invalid_score_labels")

    package = {
        "schema_version": "luban_p1_strong_go_gate.v1",
        "generated_at": "2026-06-11",
        "inputs": {
            "gold_path": str(Path(gold_path)),
            "per_row_path": str(Path(per_row_path)),
            "ab_report_path": str(Path(ab_report_path)),
        },
        "p1_governed_subset": {
            "verdict": "STRONG-GO" if not governed_blockers else "NO-GO",
            "sample_count": len(governed_rows),
            "min_required_sample_count": min_governed_rows,
            "label_authority": "ai_governed_gold",
            "quality_claim_allowed": not governed_blockers,
            "summary": governed_metrics["summary"],
            "missing_predictions": governed_metrics["missing_predictions"],
            "blockers": governed_blockers,
        },
        "p1_full_set": {
            "verdict": "STRONG-GO" if not full_set_blockers and not governed_blockers else "WEAK-GO",
            "sample_count": len(score_valid_rows),
            "label_authority_counts": label_counts,
            "invalid_score_label_count": invalid_score_label_count,
            "quality_claim_allowed": False if full_set_blockers else not governed_blockers,
            "summary": full_metrics["summary"],
            "blockers": full_set_blockers,
        },
        "release_verdict": "NO-GO",
        "provider": ab_report.get("provider") or {},
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "human_or_governance_release_signature",
        ],
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p1_strong_go_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--per-row", default=str(DEFAULT_PER_ROW))
    parser.add_argument("--ab-report", default=str(DEFAULT_AB_REPORT))
    parser.add_argument("--min-governed-rows", type=int, default=100)
    args = parser.parse_args()
    package = build_p1_strong_go_package(
        output_dir=args.output_dir,
        gold_path=args.gold,
        per_row_path=args.per_row,
        ab_report_path=args.ab_report,
        min_governed_rows=args.min_governed_rows,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
