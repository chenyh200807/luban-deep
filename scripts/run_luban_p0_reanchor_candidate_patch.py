#!/usr/bin/env python3
"""Compile P0 re-anchor candidates into review-only patch proposals.

The output is a candidate patch workbench, not an installed runtime bundle.
Strong candidates become review-required patch proposals. Weak candidates become
pollution-refinement work items.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/p0_leaf_source_reanchor_candidates_20260611/reanchor_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/p0_leaf_reanchor_candidate_patch_20260611"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _specific_terms(row: dict[str, Any], matched_terms: list[str]) -> list[str]:
    leaf_path = str(row.get("leaf_path") or "")
    parts = [part.strip() for part in leaf_path.replace(">", "/").split("/") if part.strip()]
    terms = [str(term) for term in row.get("terms") or [] if term]
    specific: list[str] = []
    for term in [*parts[-2:], *terms]:
        if term and term not in matched_terms and len(term) >= 3 and term not in specific:
            specific.append(term)
    return specific[:8]


def _patch_for_row(row: dict[str, Any], max_candidates_per_patch: int) -> dict[str, Any]:
    leaf_id = str(row.get("leaf_id"))
    sources = []
    for candidate in (row.get("candidates") or [])[:max_candidates_per_patch]:
        sources.append(
            {
                "source_lane": candidate.get("source_lane"),
                "source_path": candidate.get("source_path"),
                "record_id": candidate.get("record_id"),
                "score": candidate.get("score"),
                "matched_terms": candidate.get("matched_terms") or [],
                "snippet": candidate.get("snippet"),
                "candidate_only": True,
            }
        )
    return {
        "patch_id": f"candidate_patch:{leaf_id}",
        "work_order_id": row.get("work_order_id"),
        "leaf_id": leaf_id,
        "leaf_path": row.get("leaf_path"),
        "target": f"canonical_unified_knowledge.nodes[{leaf_id}].sources",
        "operation": "append_candidate_sources_after_review",
        "patch_status": "review_required_not_installed",
        "source_candidates": sources,
        "preconditions": {
            "candidate_status": row.get("status"),
            "top_score": row.get("top_score"),
            "requires_human_or_ai_auditor_review": True,
            "requires_regression_ab_before_runtime_install": True,
        },
    }


def _weak_refinement_for_row(row: dict[str, Any]) -> dict[str, Any]:
    top = (row.get("candidates") or [{}])[0]
    matched_terms = [str(term) for term in top.get("matched_terms") or []]
    return {
        "refinement_id": f"weak_pollution_refinement:{row.get('leaf_id')}",
        "work_order_id": row.get("work_order_id"),
        "leaf_id": row.get("leaf_id"),
        "leaf_path": row.get("leaf_path"),
        "pollution_risk": "generic_path_term_only",
        "rejected_top_candidate": {
            "source_lane": top.get("source_lane"),
            "source_path": top.get("source_path"),
            "record_id": top.get("record_id"),
            "score": top.get("score"),
            "matched_terms": matched_terms,
            "snippet": top.get("snippet"),
        },
        "required_specific_terms": _specific_terms(row, matched_terms),
        "recommended_action": "rerun_source_search_with_specific_terms_or_mark_external_source_required",
        "install_allowed": False,
    }


def build_candidate_patch_report(
    *,
    candidates_report: dict[str, Any],
    max_candidates_per_patch: int = 3,
) -> dict[str, Any]:
    candidate_patches: list[dict[str, Any]] = []
    weak_refinements: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in candidates_report.get("reanchor_candidates") or []:
        status = row.get("status")
        if status == "strong_candidate_sources_found":
            candidate_patches.append(_patch_for_row(row, max_candidates_per_patch))
        elif status == "weak_candidate_sources_found":
            weak_refinements.append(_weak_refinement_for_row(row))
        else:
            skipped.append({"leaf_id": row.get("leaf_id"), "status": status})

    return {
        "schema": "luban_p0_reanchor_candidate_patch.v1",
        "source_candidate_schema": candidates_report.get("schema"),
        "source_bundle_content_hash": candidates_report.get("source_bundle_content_hash"),
        "summary": {
            "candidate_patch_count": len(candidate_patches),
            "weak_pollution_refinement_count": len(weak_refinements),
            "skipped_count": len(skipped),
            "max_candidates_per_patch": max_candidates_per_patch,
        },
        "candidate_patches": candidate_patches,
        "weak_pollution_refinements": weak_refinements,
        "skipped": skipped,
        "safety": {
            "candidate_only": True,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def render_compiled_data_map(report: dict[str, Any], candidates_path: Path) -> str:
    summary = report["summary"]
    lines = [
        "# Luban Nexus Compiled Data Map",
        "",
        "## Purpose",
        "",
        "This report records the current Nexus-like compilation loop outputs for AI agents. These files are compiler workbench artifacts, not release truth.",
        "",
        "## Source Data",
        "",
        "- `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/`: human-maintained source pool for textbook, standards, lectures, question bank, and student-answer materials.",
        "- `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/近三年案例题_按学生答卷排版.md`: student answer source material; not authority by itself.",
        "",
        "## Compiled Runtime Supply",
        "",
        "- `deeptutor/services/construction_grading/runtime_supply/`: versioned runtime supply shards.",
        "- `deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_unified_knowledge.json`: current unified teaching-context bundle.",
        "- `deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/source_alignment_repairs.json`: source-alignment repair overlay.",
        "",
        "## Compiler Workbench Artifacts",
        "",
        "- `artifacts/luban_grading_artifacts/docs2026_runtime_reconciliation_20260611/reconciliation_report.json`: source-to-runtime reconciliation.",
        "- `artifacts/luban_grading_artifacts/unified_knowledge_leaf_coverage_work_orders_20260611/leaf_coverage_work_orders.json`: coverage gap -> typed work orders.",
        f"- `{candidates_path}`: P0 source candidate evidence with strong/weak split.",
        "- `artifacts/luban_grading_artifacts/p0_leaf_reanchor_candidate_patch_20260611/candidate_patch_report.json`: strong candidate -> review-only patch proposals; weak candidate -> pollution refinement queue.",
        "",
        "## Current Patch Batch",
        "",
        f"- Review-only candidate patches: {summary['candidate_patch_count']}",
        f"- Weak pollution refinements: {summary['weak_pollution_refinement_count']}",
        f"- Skipped rows: {summary['skipped_count']}",
        "",
        "## Safety Boundary",
        "",
        "- `candidate_only=true`",
        "- `installed_runtime_supply=false`",
        "- `canonical_truth_written=false`",
        "- `official_score_allowed=false`",
        "- `production_write_count=0`",
        "- `release_truth_claimed=false`",
        "",
        "## Next Gate",
        "",
        "Only after source/evidence audit and regression A/B may selected patches be compiled into a new runtime_supply version. This report does not grant release authority.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-candidates-per-patch", type=int, default=3)
    args = parser.parse_args(argv)

    report = build_candidate_patch_report(
        candidates_report=_read_json(args.candidates),
        max_candidates_per_patch=args.max_candidates_per_patch,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "candidate_patch_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "COMPILED_DATA_MAP.md").write_text(
        render_compiled_data_map(report, args.candidates),
        encoding="utf-8",
    )
    print(json.dumps({"out": str(out), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
