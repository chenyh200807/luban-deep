#!/usr/bin/env python
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = Path("artifacts") / "knowledge_compiler" / "2026" / args.run_id
    tracked = subprocess.run(["git", "ls-files", "artifacts/"], text=True, capture_output=True, timeout=10)
    apply_probe = subprocess.run(
        [sys.executable, "scripts/apply_2026_compiler_backfill.py", "--run-id", args.run_id, "--apply"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    apply_refuses = apply_probe.returncode != 0 and "Refusing --apply" in apply_probe.stderr
    graph_exists = (run_dir / "graph_edges_projection.jsonl").exists()
    qa_exists = Path("docs/qa/2026-05-24-2026-source-compiler-dry-run.md").exists()
    artifact_safe = tracked.returncode == 0 and tracked.stdout == ""
    print(f"artifact_safe={str(artifact_safe).lower()}")
    print(f"apply_refuses={str(apply_refuses).lower()}")
    print(f"graph_exists={str(graph_exists).lower()}")
    print(f"qa_exists={str(qa_exists).lower()}")
    return 0 if artifact_safe and apply_refuses and graph_exists and qa_exists else 1


if __name__ == "__main__":
    raise SystemExit(main())
