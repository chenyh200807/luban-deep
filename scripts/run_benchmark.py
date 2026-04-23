#!/usr/bin/env python3
"""Run canonical DeepTutor benchmark suites."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.runner import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REGISTRY_PATH,
    run_benchmark,
    write_benchmark_artifacts,
)

CANONICAL_SUITES = ("pr_gate_core", "regression_watch", "incident_replay", "exploration_lab")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor canonical benchmark suites.")
    parser.add_argument("suites", nargs="*")
    parser.add_argument("--suite", dest="suite_flags", action="append", choices=CANONICAL_SUITES)
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--output-dir", "--output", dest="output_dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--api-base-url")
    parser.add_argument("--response-mode", choices=["smart", "fast", "deep"], default="smart")
    parser.add_argument("--long-dialog-mode", choices=["lite", "full"], default="lite")
    args = parser.parse_args()

    suite_names = [*(args.suites or []), *(args.suite_flags or [])]
    if not suite_names:
        parser.error("at least one suite is required")
    unknown_suites = sorted(set(suite_names) - set(CANONICAL_SUITES))
    if unknown_suites:
        parser.error(f"unknown benchmark suite(s): {', '.join(unknown_suites)}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    payload = await run_benchmark(
        suite_names=suite_names,
        registry_path=args.registry_path,
        api_base_url=args.api_base_url,
        response_mode=args.response_mode,
        long_dialog_mode=args.long_dialog_mode,
        output_dir=output_dir,
    )
    artifact_paths = write_benchmark_artifacts(payload, output_dir=output_dir)
    summary = payload["summary"]

    print("")
    print("=" * 60)
    print("Benchmark 完成")
    print(f"Run ID: {payload['run_manifest']['run_id']}")
    print(f"Suites: {', '.join(payload['run_manifest']['requested_suites'])}")
    print(
        f"PASS={summary['passed']} FAIL={summary['failed']} "
        f"SKIP={summary['skipped']} RATE={summary['pass_rate']}"
    )
    if payload["failure_taxonomy"]:
        failure_summary = ", ".join(
            f"{item['failure_type']}={item['count']}" for item in payload["failure_taxonomy"]
        )
        print(f"Failure types: {failure_summary}")
    if payload["blind_spots"]:
        print("Blind spots:")
        for item in payload["blind_spots"]:
            print(f"  - {item['suite']}::{item['case_id']} -> {item['reason']}")
    print(f"JSON: {artifact_paths['json_path']}")
    print(f"MD:   {artifact_paths['md_path']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
