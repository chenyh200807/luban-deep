#!/usr/bin/env python3
"""Run the canonical daily benchmark trend."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.runner import run_benchmark, write_benchmark_artifacts  # noqa: E402
from deeptutor.services.benchmark.trend import build_daily_trend, write_daily_trend_artifacts  # noqa: E402
from deeptutor.services.observability import get_control_plane_store  # noqa: E402


def _payload_from_record(record: dict | None) -> dict | None:
    if not record:
        return None
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor benchmark daily trend.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "tmp" / "benchmark" / "daily"))
    parser.add_argument("--api-base-url")
    parser.add_argument("--history-limit", type=int, default=7)
    args = parser.parse_args()

    store = get_control_plane_store()
    latest_benchmark = _payload_from_record(store.latest_run("benchmark_runs"))
    payload = await run_benchmark(
        suite_names=("regression_watch",),
        baseline_payload=latest_benchmark,
        api_base_url=args.api_base_url,
    )
    output_dir = Path(args.output_dir).expanduser().resolve()
    benchmark_paths = write_benchmark_artifacts(payload, output_dir=output_dir / "runs")
    benchmark_store_paths = store.write_run(
        kind="benchmark_runs",
        run_id=payload["run_manifest"]["run_id"],
        release_id=str((payload.get("release_spine") or {}).get("release_id") or ""),
        payload=payload,
    )

    history_records = store.list_runs("benchmark_runs", limit=max(0, int(args.history_limit or 0)))
    history_payloads = [
        record["payload"]
        for record in reversed(history_records)
        if isinstance(record.get("payload"), dict)
        and (record.get("payload") or {}).get("run_manifest", {}).get("run_id")
        != payload["run_manifest"]["run_id"]
    ]
    trend_payload = build_daily_trend(current_payload=payload, history_payloads=history_payloads)
    trend_paths = write_daily_trend_artifacts(trend_payload, output_dir=output_dir / "trend")
    trend_store_paths = store.write_run(
        kind="daily_trends",
        run_id=trend_payload["run_manifest"]["run_id"],
        release_id=str((trend_payload.get("release_spine") or {}).get("release_id") or ""),
        payload=trend_payload,
    )

    print("Daily benchmark trend completed")
    print(f"Benchmark JSON: {benchmark_paths['json_path']}")
    print(f"Trend JSON:     {trend_paths['json_path']}")
    print(f"Benchmark store latest: {benchmark_store_paths['latest_path']}")
    print(f"Trend store latest:     {trend_store_paths['latest_path']}")


if __name__ == "__main__":
    asyncio.run(main())
