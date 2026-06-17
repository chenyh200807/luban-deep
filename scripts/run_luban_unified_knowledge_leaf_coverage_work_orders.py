#!/usr/bin/env python3
"""Compile canonical unified knowledge coverage gaps into work orders.

This is the next Nexus-like compiler loop step after source/runtime reconciliation:
turn coverage gaps into typed, prioritized compiler tasks. It does not mutate the
runtime bundle or claim release truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY_INDEX = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json"
)
DEFAULT_UNIFIED_BUNDLE = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_unified_knowledge.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO
    / "artifacts/luban_grading_artifacts/unified_knowledge_leaf_coverage_work_orders_20260611"
)
SOURCE_KEYS = ("textbook", "standard", "lecture", "question")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _taxonomy_name_path(taxonomy_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for leaf in taxonomy_index.get("leaves") or []:
        if isinstance(leaf, dict) and leaf.get("code"):
            out[str(leaf["code"])] = leaf
    return out


def _node_counts(node: dict[str, Any] | None) -> dict[str, int]:
    raw = (node or {}).get("counts") or {}
    return {source: int(raw.get(source) or 0) for source in SOURCE_KEYS}


def _work_order(
    *,
    category: str,
    priority: str,
    node_code: str,
    taxonomy_leaf: dict[str, Any] | None,
    counts: dict[str, int],
    missing_sources: list[str],
    recommended_action: str,
    reason: str,
) -> dict[str, Any]:
    work_order_id = f"{priority}:{category}:{node_code}"
    return {
        "work_order_id": work_order_id,
        "category": category,
        "gap_type": category,
        "priority": priority,
        "node_code": node_code,
        "leaf_id": node_code,
        "name_path": str((taxonomy_leaf or {}).get("name_path") or node_code),
        "leaf_path": str((taxonomy_leaf or {}).get("name_path") or node_code),
        "keywords": list((taxonomy_leaf or {}).get("keywords") or [])[:12],
        "current_counts": counts,
        "missing_sources": missing_sources,
        "recommended_action": recommended_action,
        "action": recommended_action,
        "reason": reason,
        "authority": "canonical_unified_knowledge_coverage_compiler",
        "canonical_truth_written": False,
        "production_write_count": 0,
        "official_score_allowed": False,
    }


def build_work_orders(
    *,
    taxonomy_index: dict[str, Any],
    unified_bundle: dict[str, Any],
    max_question_no_knowledge: int = 120,
    max_knowledge_no_question: int = 120,
    max_missing_source: int = 240,
) -> dict[str, Any]:
    manifest = unified_bundle.get("manifest") or {}
    coverage = manifest.get("coverage") or {}
    nodes = unified_bundle.get("nodes") or {}
    taxonomy_by_code = _taxonomy_name_path(taxonomy_index)

    work_orders: list[dict[str, Any]] = []
    question_no_knowledge = [str(code) for code in coverage.get("leaves_question_no_knowledge") or []]
    for code in question_no_knowledge[:max_question_no_knowledge]:
        work_orders.append(
            _work_order(
                category="question_without_knowledge",
                priority="P0",
                node_code=code,
                taxonomy_leaf=taxonomy_by_code.get(code),
                counts=_node_counts(nodes.get(code)),
                missing_sources=["textbook", "standard", "lecture"],
                recommended_action="compile_or_reanchor_source_context_for_question_leaf",
                reason="Assessment/question evidence exists for this canonical leaf, but the unified teaching context has no supporting knowledge source.",
            )
        )

    knowledge_no_question_rows: list[dict[str, Any]] = []
    for code, node in nodes.items():
        counts = _node_counts(node if isinstance(node, dict) else {})
        if counts["question"] == 0 and any(counts[source] > 0 for source in ("textbook", "standard", "lecture")):
            knowledge_no_question_rows.append(
                _work_order(
                    category="knowledge_without_question",
                    priority="P1",
                    node_code=str(code),
                    taxonomy_leaf=taxonomy_by_code.get(str(code)),
                    counts=counts,
                    missing_sources=["question"],
                    recommended_action="attach_question_bank_or_mark_no_exam_evidence",
                    reason="Teaching knowledge exists for this canonical leaf, but question-bank assessment evidence is absent.",
                )
            )
    work_orders.extend(knowledge_no_question_rows[:max_knowledge_no_question])

    missing_source_rows: list[dict[str, Any]] = []
    for code, node in nodes.items():
        counts = _node_counts(node if isinstance(node, dict) else {})
        missing = [source for source in ("textbook", "standard", "lecture") if counts[source] == 0]
        if missing and counts["question"] > 0:
            missing_source_rows.append(
                _work_order(
                    category="incomplete_multisource_context",
                    priority="P2",
                    node_code=str(code),
                    taxonomy_leaf=taxonomy_by_code.get(str(code)),
                    counts=counts,
                    missing_sources=missing,
                    recommended_action="enrich_missing_source_lanes_or_mark_not_applicable",
                    reason="Runtime teaching context is usable but not yet Nexus-like multi-source complete.",
                )
            )
    missing_source_rows.sort(key=lambda row: (-int(row["current_counts"].get("question") or 0), row["node_code"]))
    work_orders.extend(missing_source_rows[:max_missing_source])

    order_rank = {"P0": 0, "P1": 1, "P2": 2}
    work_orders.sort(key=lambda row: (order_rank.get(str(row["priority"]), 99), row["node_code"], row["category"]))
    total = int(coverage.get("canonical_leaves_total") or 0)
    populated = int(coverage.get("leaves_populated") or 0)
    report = {
        "schema": "luban_unified_knowledge_leaf_coverage_work_orders.v1",
        "source_bundle_namespace": manifest.get("namespace") or "canonical_unified_knowledge",
        "source_bundle_content_hash": manifest.get("content_hash"),
        "coverage": {
            "canonical_leaves_total": total,
            "leaves_populated": populated,
            "populated_leaf_rate": (populated / total) if total else None,
            "leaves_with_textbook": coverage.get("leaves_with_textbook"),
            "leaves_with_standard": coverage.get("leaves_with_standard"),
            "leaves_with_lecture": coverage.get("leaves_with_lecture"),
            "leaves_with_question": coverage.get("leaves_with_question"),
        },
        "summary": {
            "question_no_knowledge_count": len(question_no_knowledge),
            "knowledge_no_question_count": len(knowledge_no_question_rows),
            "missing_source_work_order_count": len(missing_source_rows),
            "emitted_work_order_count": len(work_orders),
        },
        "work_orders": work_orders,
        "safety": {
            "read_only_work_order_compile": True,
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy-index", type=Path, default=DEFAULT_TAXONOMY_INDEX)
    parser.add_argument("--unified-bundle", type=Path, default=DEFAULT_UNIFIED_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-question-no-knowledge", type=int, default=120)
    parser.add_argument("--max-knowledge-no-question", type=int, default=120)
    parser.add_argument("--max-missing-source", type=int, default=240)
    args = parser.parse_args(argv)

    report = build_work_orders(
        taxonomy_index=_read_json(args.taxonomy_index),
        unified_bundle=_read_json(args.unified_bundle),
        max_question_no_knowledge=args.max_question_no_knowledge,
        max_knowledge_no_question=args.max_knowledge_no_question,
        max_missing_source=args.max_missing_source,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "leaf_coverage_work_orders.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out),
                "emitted_work_order_count": report["summary"]["emitted_work_order_count"],
                "question_no_knowledge_count": report["summary"]["question_no_knowledge_count"],
                "knowledge_no_question_count": report["summary"]["knowledge_no_question_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
