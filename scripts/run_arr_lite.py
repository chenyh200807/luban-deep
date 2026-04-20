#!/usr/bin/env python3
"""DeepTutor ARR bootstrap runner."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.arr_runner import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    build_arr_report_payload,
    load_arr_baseline_payload,
    run_arr,
    write_arr_artifacts,
)
from deeptutor.services.observability import get_control_plane_store  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor ARR bootstrap suites.")
    parser.add_argument(
        "--mode",
        choices=["lite", "full"],
        default="lite",
        help="lite=semantic/context/long-dialog-focus; full=adds long-dialog-full",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="ARR artifact 输出目录，默认 tmp/arr",
    )
    parser.add_argument(
        "--baseline",
        help="之前一次 ARR JSON artifact 路径，用于 diff",
    )
    parser.add_argument(
        "--long-dialog-source-json",
        help="显式指定 long dialog 历史 artifact JSON",
    )
    parser.add_argument(
        "--max-long-dialog-cases",
        type=int,
        help="限制 long dialog case 数；lite 默认 1",
    )
    parser.add_argument(
        "--api-base-url",
        help="提供后，long-dialog-full 将通过真实 /api/v1/ws 执行，而不是本进程 runtime 重放",
    )
    args = parser.parse_args()

    baseline_payload = load_arr_baseline_payload(args.baseline)
    output_dir = Path(args.output_dir).expanduser().resolve()
    payload = await run_arr(
        mode=args.mode,
        baseline_payload=baseline_payload,
        explicit_long_dialog_source_json=args.long_dialog_source_json,
        long_dialog_max_cases=args.max_long_dialog_cases,
        output_dir=output_dir,
        api_base_url=args.api_base_url,
    )
    payload["baseline_source"] = "explicit" if args.baseline else "control_plane_latest" if baseline_payload else "none"
    artifact_paths = write_arr_artifacts(payload, output_dir=output_dir)
    report = build_arr_report_payload(payload)
    control_plane_paths = get_control_plane_store().write_run(
        kind="arr_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    summary = payload["summary"]

    print("")
    print("=" * 60)
    print(f"ARR {args.mode} 完成")
    print(f"Run ID: {payload['run_id']}")
    print(f"PASS={summary['passed']} FAIL={summary['failed']} SKIP={summary['skipped']}")
    print(f"Pass rate: {summary['pass_rate']}")
    print(
        "Gate summary: "
        f"gate_stable_pass_rate={summary.get('gate_stable_pass_rate')} "
        f"regression_tier_failed={summary.get('regression_tier_failed')}"
    )
    latency = report["latency_summary"]
    print(
        "Latency(ms): "
        f"avg={latency.get('avg_latency_ms')} "
        f"p50={latency.get('p50_latency_ms')} "
        f"p95={latency.get('p95_latency_ms')} "
        f"max={latency.get('max_latency_ms')}"
    )
    if report["case_tier_distribution"]:
        tier_summary = ", ".join(f"{item['name']}={item['count']}" for item in report["case_tier_distribution"])
        print(f"Case tiers: {tier_summary}")
    execution_context = report.get("execution_context") or payload.get("execution_context") or {}
    if execution_context:
        print(f"Execution context: {execution_context}")
    if report["failure_type_distribution"]:
        failure_summary = ", ".join(
            f"{item['name']}={item['count']}" for item in report["failure_type_distribution"]
        )
        print(f"Failure types: {failure_summary}")
    print(f"Baseline source: {payload.get('baseline_source')}")
    if payload.get("baseline_diff"):
        diff = payload["baseline_diff"]
        print(
            "Diff: "
            f"delta={diff.get('pass_rate_delta')} "
            f"regressions={len(diff.get('regressions') or [])} "
            f"new_failures={len(diff.get('new_failures') or [])} "
            f"recovered={len(diff.get('recovered') or [])}"
        )
    if report["failures"]:
        print("Failure details:")
        for item in report["failures"][:5]:
            print(
                f"  - {item['case_key']} {item['failure_type']} conf={item['confidence']} "
                f"reason={item['reason']}"
            )
    print(f"JSON: {artifact_paths['json_path']}")
    print(f"MD:   {artifact_paths['md_path']}")
    print(f"HTML: {artifact_paths['html_path']}")
    print(f"Analysis JSON: {artifact_paths['analysis_json_path']}")
    print(f"Control plane JSON: {control_plane_paths['json_path']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
