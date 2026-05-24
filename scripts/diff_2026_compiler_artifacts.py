#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deeptutor.services.source_compiler.jsonl import read_jsonl


ARTIFACT_KEYS = {
    "standard_clauses": "stable_clause_id",
    "question_capsules": "stable_question_source_id",
    "lecture_teaching_cards": "stable_lecture_card_id",
}


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def _load(run_id: str, name: str, key: str) -> dict[str, dict]:
    path = _run_dir(run_id) / f"{name}.jsonl"
    if not path.exists():
        return {}
    return {str(row[key]): row for row in read_jsonl(path) if key in row}


def diff_runs(base: str, head: str) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for name, key in ARTIFACT_KEYS.items():
        base_rows = _load(base, name, key)
        head_rows = _load(head, name, key)
        base_ids = set(base_rows)
        head_ids = set(head_rows)
        shared = base_ids & head_ids
        changed = sum(
            1
            for stable_id in shared
            if base_rows[stable_id].get("content_hash") != head_rows[stable_id].get("content_hash")
        )
        summary[name] = {
            "added": len(head_ids - base_ids),
            "removed": len(base_ids - head_ids),
            "unchanged": len(shared) - changed,
            "content_hash_changed": changed,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    try:
        summary = diff_runs(args.base, args.head)
        out_dir = _run_dir(args.head)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "artifact_diff_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# 2026 Compiler Artifact Diff", "", "| Artifact | Added | Removed | Unchanged | Content hash changed |", "| --- | ---: | ---: | ---: | ---: |"]
        for name, stats in summary.items():
            lines.append(
                f"| `{name}` | {stats['added']} | {stats['removed']} | {stats['unchanged']} | {stats['content_hash_changed']} |"
            )
        (out_dir / "artifact_diff_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, stats in summary.items():
            print(
                f"{name}: added={stats['added']} removed={stats['removed']} unchanged={stats['unchanged']} content_hash_changed={stats['content_hash_changed']}"
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
