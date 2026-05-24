#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.metadata import utc_now_iso
from deeptutor.services.source_compiler.platform import RunDirectoryLock
from deeptutor.services.source_compiler.source_inventory import build_source_inventory, summarize_inventory


def _source_root_from_env() -> Path:
    value = os.environ.get("LUBAN_2026_SOURCE_ROOT")
    if not value:
        raise RuntimeError("LUBAN_2026_SOURCE_ROOT is required and must point to docs/2026.")
    root = Path(value)
    if not root.exists():
        raise RuntimeError("LUBAN_2026_SOURCE_ROOT is required and must point to docs/2026.")
    if not (root / "taxonomy").exists() or not (root / "标准文件").exists():
        raise RuntimeError("LUBAN_2026_SOURCE_ROOT must contain taxonomy and standard files.")
    if not (root / "题库").exists():
        raise RuntimeError("LUBAN_2026_SOURCE_ROOT must contain at least one exam or question source.")
    return root


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--require-platform", default="darwin")
    parser.add_argument("--allow-dataless-scan-disabled", action="store_true")
    parser.add_argument("--only-class")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        root = _source_root_from_env()
        lock = RunDirectoryLock(_run_dir(args.run_id), force=args.force)
        lock.prepare()
        try:
            records = build_source_inventory(
                root,
                run_id=args.run_id,
                compiled_at=utc_now_iso(),
                require_platform=args.require_platform,
                allow_dataless_scan_disabled=args.allow_dataless_scan_disabled,
                only_class=args.only_class,
                limit=args.limit,
            )
            run_dir = _run_dir(args.run_id)
            write_jsonl(run_dir / "source_inventory.jsonl", records)
            write_jsonl(
                run_dir / "source_manifest.jsonl",
                [
                    {
                        "stable_source_id": record["stable_source_id"],
                        "source_path": record["source_path"],
                        "source_class": record["source_class"],
                        "content_hash": record["sha256"],
                        "compile_eligibility": record["compile_eligibility"],
                        "compiler_version": record["compiler_version"],
                        "compiled_at": record["compiled_at"],
                        "run_id": record["run_id"],
                    }
                    for record in records
                ],
            )
            summary = summarize_inventory(records)
            print(" ".join(f"{key}={value}" for key, value in sorted(summary.items())))
            return 0
        finally:
            lock.release()
    except Exception as exc:  # noqa: BLE001 - CLI should fail closed with a clear message.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

