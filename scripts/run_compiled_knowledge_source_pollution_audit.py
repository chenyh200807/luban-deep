#!/usr/bin/env python3
"""Audit compiled source/path pollution and emit compiler feedback work orders.

This is a compiler feedback producer, not a runtime patch. It reads the
system-level compiled knowledge query plan, records candidates where source text
matches a query but the canonical path does not, and writes shadow-only
``luban_compiler_candidate`` work orders for the next compiler run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.compiled_knowledge import general_knowledge
from deeptutor.services.construction_grading import compiler_feedback as cf
from scripts.run_tutorbot_compiled_knowledge_online_shadow import DEFAULT_CASES

REPO = PROJECT_ROOT
DEFAULT_OUT = (
    REPO
    / "artifacts"
    / "qa"
    / f"compiled-knowledge-source-pollution-audit-{time.strftime('%Y%m%d-%H%M%S')}"
)


def _default_queries(limit: int) -> list[str]:
    return [case.query for case in list(DEFAULT_CASES)[:limit]]


def _report(summary: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    lines = [
        "# Compiled Source Pollution Audit",
        "",
        "This audit feeds source/path conflicts back to the compiler. It does not",
        "change runtime defaults, canonical learner truth, DB state, or release bundles.",
        "",
        f"- query_count: {summary['query_count']}",
        f"- work_order_count: {summary['work_order_count']}",
        f"- affected_node_count: {summary['affected_node_count']}",
        f"- release_truth_written: {summary['release_truth_written']}",
        "",
        "## Top Work Orders",
    ]
    for entry in entries[:20]:
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        lines.extend(
            [
                "",
                f"### {payload.get('node_code') or 'unknown'}",
                f"- query: {payload.get('query_text') or ''}",
                f"- path: {payload.get('leaf_name_path') or ''}",
                f"- source_hits: {', '.join(payload.get('source_hits') or [])}",
                f"- negative_evidence: {', '.join(payload.get('negative_evidence') or [])}",
                f"- compiler_action: {payload.get('compiler_action') or ''}",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def run_audit(*, queries: list[str], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []
    for query in queries:
        plan = general_knowledge.build_general_knowledge_query_plan(query)
        query_entries = cf.work_orders_from_source_path_conflicts(
            query_text=query,
            query_plan=plan,
        )
        entries.extend(query_entries)
        per_query.append(
            {
                "query": query,
                "candidate_count": plan.get("candidate_count"),
                "work_order_count": len(query_entries),
            }
        )

    ledger_summary = cf.build_ledger(entries)
    affected_nodes = sorted(
        {
            str((entry.get("payload") or {}).get("node_code") or "").strip()
            for entry in entries
            if str((entry.get("payload") or {}).get("node_code") or "").strip()
        }
    )
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "query_count": len(queries),
        "work_order_count": len(entries),
        "affected_node_count": len(affected_nodes),
        "affected_nodes": affected_nodes,
        "namespace": cf.NAMESPACE,
        "release_truth_written": False,
        "canonical_truth_written": False,
        "runtime_default_changed": False,
        "ledger": ledger_summary,
        "queries": per_query,
    }
    with (output_dir / "compiler_feedback_ledger.jsonl").open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.write(json.dumps({"_ledger_summary": ledger_summary}, ensure_ascii=False, sort_keys=True) + "\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "FINDING_compiled_source_pollution.md").write_text(
        _report(summary, entries),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--query", action="append", default=[])
    args = parser.parse_args()

    queries = [str(item).strip() for item in args.query if str(item).strip()]
    if not queries:
        queries = _default_queries(max(1, int(args.limit)))
    summary = run_audit(queries=queries, output_dir=Path(args.out))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
