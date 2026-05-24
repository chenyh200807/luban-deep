#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REFUSAL = "Refusing --apply until Task 13 apply executor is implemented and release gates are signed."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.apply:
        print(REFUSAL, file=sys.stderr)
        return 1
    if not args.dry_run:
        print("Use --dry-run to generate a reviewed SQL plan. --apply is disabled until Task 13.", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else Path("artifacts") / "knowledge_compiler" / "2026" / args.run_id / "backfill_plan.sql"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                "-- 2026 source compiler reviewed SQL plan",
                f"-- run_id: {args.run_id}",
                "-- compiler_version: 2026-source-compiler-v0.2",
                "-- writeback_policy: overwrite_only_if_empty",
                "-- stable_ids and content_hash values must be copied from reviewed JSONL artifacts.",
                "-- Task 13 only: live write statements remain disabled in this PR.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"backfill_plan={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
