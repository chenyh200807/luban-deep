#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deeptutor.services.source_compiler.graph_projection import project_graph_edges
from deeptutor.services.source_compiler.jsonl import read_jsonl, write_jsonl


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        run_dir = _run_dir(args.run_id)
        questions = read_jsonl(run_dir / "question_capsules.jsonl") if (run_dir / "question_capsules.jsonl").exists() else []
        standards = read_jsonl(run_dir / "standard_clauses.jsonl") if (run_dir / "standard_clauses.jsonl").exists() else []
        lectures = read_jsonl(run_dir / "lecture_teaching_cards.jsonl") if (run_dir / "lecture_teaching_cards.jsonl").exists() else []
        kb_refs = read_jsonl(run_dir / "kb_standard_refs.jsonl") if (run_dir / "kb_standard_refs.jsonl").exists() else []
        edges = project_graph_edges(
            questions=questions,
            standard_clauses=standards,
            lecture_cards=lectures,
            kb_standard_refs=kb_refs,
            run_id=args.run_id,
        )
        write_jsonl(run_dir / "graph_edges_projection.jsonl", edges)
        families = sorted({f"{edge['source_type']}->{edge['target_type']}:{edge['relation']}" for edge in edges})
        print(f"graph_edges={len(edges)} families={','.join(families)}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
