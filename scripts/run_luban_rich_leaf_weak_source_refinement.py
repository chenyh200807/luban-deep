#!/usr/bin/env python3
"""Create review-only work orders for RichLeaf leaves without strong source evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_GAP_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_source_gap_candidates_20260611/source_gap_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_weak_source_refinement_20260611"
SCHEMA = "luban_rich_leaf_weak_source_refinement.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate_snapshot(candidates: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for candidate in candidates[:limit]:
        snapshot.append(
            {
                "source_lane": candidate.get("source_lane"),
                "source_path": candidate.get("source_path"),
                "record_id": candidate.get("record_id"),
                "score": candidate.get("score"),
                "matched_terms": list(candidate.get("matched_terms") or []),
                "snippet": candidate.get("snippet"),
                "candidate_only": True,
                "install_allowed": False,
            }
        )
    return snapshot


def _reason_codes(row: dict[str, Any]) -> list[str]:
    status = str(row.get("status") or "")
    if status == "no_candidate_sources_found":
        return ["no_candidate_source"]
    reasons = ["below_strong_threshold"]
    candidates = [c for c in row.get("candidates") or [] if isinstance(c, dict)]
    best = candidates[0] if candidates else {}
    if len(best.get("matched_terms") or []) <= 1:
        reasons.append("low_term_overlap")
    if not candidates:
        reasons.append("candidate_list_empty")
    return reasons


def _next_action(reason_codes: list[str]) -> str:
    if "no_candidate_source" in reason_codes:
        return "expand_authority_corpus_for_lane"
    if "low_term_overlap" in reason_codes:
        return "find_better_authority_source_for_lane"
    return "review_terms_or_split_leaf_before_retrieval"


def _lane_work_order(row: dict[str, Any]) -> dict[str, Any]:
    reasons = _reason_codes(row)
    return {
        "missing_lane": row.get("missing_lane"),
        "status": row.get("status"),
        "top_score": row.get("top_score"),
        "strong_candidate_threshold": row.get("strong_candidate_threshold"),
        "reason_codes": reasons,
        "next_action": _next_action(reasons),
        "terms": list(row.get("terms") or []),
        "candidate_snapshot": _candidate_snapshot([c for c in row.get("candidates") or [] if isinstance(c, dict)]),
        "promotion_allowed": False,
        "runtime_install_allowed": False,
    }


def build_weak_source_refinement_report(*, source_gap_report: dict[str, Any]) -> dict[str, Any]:
    rows_by_leaf: dict[str, list[dict[str, Any]]] = {}
    for row in source_gap_report.get("source_gap_candidates") or []:
        if isinstance(row, dict) and row.get("leaf_id"):
            rows_by_leaf.setdefault(str(row["leaf_id"]), []).append(row)

    leaf_work_orders: list[dict[str, Any]] = []
    leaves_with_existing_strong_skipped = 0
    weak_lane_count = 0
    no_candidate_lane_count = 0

    for leaf_id, rows in sorted(rows_by_leaf.items()):
        if any(row.get("status") == "strong_candidate_sources_found" for row in rows):
            leaves_with_existing_strong_skipped += 1
            continue
        lane_orders = [_lane_work_order(row) for row in rows]
        weak_lane_count += sum(1 for row in rows if row.get("status") == "weak_candidate_sources_found")
        no_candidate_lane_count += sum(1 for row in rows if row.get("status") == "no_candidate_sources_found")
        leaf_work_orders.append(
            {
                "leaf_id": leaf_id,
                "artifact_id": rows[0].get("artifact_id"),
                "name_path": rows[0].get("name_path"),
                "status": "source_authority_gap",
                "lane_work_orders": lane_orders,
                "promotion_allowed": False,
                "runtime_install_allowed": False,
            }
        )

    lane_work_order_count = sum(len(order["lane_work_orders"]) for order in leaf_work_orders)
    return {
        "schema": SCHEMA,
        "source_gap_schema": source_gap_report.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "work_orders_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "leaf_work_order_count": len(leaf_work_orders),
            "lane_work_order_count": lane_work_order_count,
            "weak_lane_count": weak_lane_count,
            "no_candidate_lane_count": no_candidate_lane_count,
            "leaves_with_existing_strong_skipped": leaves_with_existing_strong_skipped,
        },
        "leaf_work_orders": leaf_work_orders,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-gap-candidates", type=Path, default=DEFAULT_SOURCE_GAP_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    source_gap_report = _read_json(args.source_gap_candidates)
    report = build_weak_source_refinement_report(source_gap_report=source_gap_report)
    output_path = args.output_dir / "weak_source_refinement_work_orders.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
