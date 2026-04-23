#!/usr/bin/env python3
"""Run canonical incident replay benchmark and RCA seed report."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.incident import (  # noqa: E402
    build_incident_replay_report,
    write_incident_replay_artifacts,
)
from deeptutor.services.benchmark.runner import run_benchmark, write_benchmark_artifacts  # noqa: E402
from deeptutor.services.observability import get_control_plane_store  # noqa: E402


def _payload_from_record(record: dict | None) -> dict | None:
    if not record:
        return None
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor benchmark incident replay.")
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "tmp" / "benchmark" / "incident"))
    parser.add_argument("--api-base-url")
    args = parser.parse_args()

    store = get_control_plane_store()
    latest_benchmark = _payload_from_record(store.latest_run("benchmark_runs"))
    payload = await run_benchmark(
        suite_names=("incident_replay",),
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

    incident_payload = build_incident_replay_report(
        benchmark_payload=payload,
        incident_id=args.incident_id,
    )
    incident_paths = write_incident_replay_artifacts(incident_payload, output_dir=output_dir / "incident")
    incident_store_paths = store.write_run(
        kind="incident_ledger",
        run_id=incident_payload["run_manifest"]["run_id"],
        release_id=str((incident_payload.get("release_spine") or {}).get("release_id") or ""),
        payload=incident_payload,
    )

    print("Incident replay completed")
    print(f"Benchmark JSON: {benchmark_paths['json_path']}")
    print(f"Incident JSON:  {incident_paths['json_path']}")
    print(f"Benchmark store latest: {benchmark_store_paths['latest_path']}")
    print(f"Incident store latest:  {incident_store_paths['latest_path']}")


if __name__ == "__main__":
    asyncio.run(main())
