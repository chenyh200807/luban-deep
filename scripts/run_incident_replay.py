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
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.observability import get_control_plane_store  # noqa: E402


def _payload_from_record(record: dict | None) -> dict | None:
    if not record:
        return None
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else None


def _payload_release(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    release = payload.get("release")
    if isinstance(release, dict) and release:
        return release
    release_spine = payload.get("release_spine")
    return release_spine if isinstance(release_spine, dict) else {}


def _same_release_spine(expected: dict, actual: dict) -> bool:
    expected_git_sha = str((expected or {}).get("git_sha") or "").strip()
    actual_git_sha = str((actual or {}).get("git_sha") or "").strip()
    if expected_git_sha and actual_git_sha:
        return expected_git_sha == actual_git_sha
    expected_release_id = str((expected or {}).get("release_id") or "").strip()
    actual_release_id = str((actual or {}).get("release_id") or "").strip()
    if expected_release_id and actual_release_id:
        return expected_release_id == actual_release_id
    return False


def _latest_same_release_payload(store, kind: str, *, release: dict) -> dict | None:
    try:
        records = store.list_runs(kind, limit=100)
    except (FileNotFoundError, TypeError, ValueError):
        records = []
    for record in records:
        payload = _payload_from_record(record)
        if isinstance(payload, dict) and _same_release_spine(release, _payload_release(payload)):
            return payload
    latest = store.latest_payload(kind, fallback=False)
    if isinstance(latest, dict) and _same_release_spine(release, _payload_release(latest)):
        return latest
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor benchmark incident replay.")
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "tmp" / "benchmark" / "incident"))
    parser.add_argument("--api-base-url")
    parser.add_argument("--observer-json")
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
    observer_payload = (
        load_payload_json(args.observer_json, expected_kind="observer_snapshots")
        if args.observer_json
        else _latest_same_release_payload(store, "observer_snapshots", release=payload.get("release_spine") or {})
    )

    incident_payload = build_incident_replay_report(
        benchmark_payload=payload,
        incident_id=args.incident_id,
        observer_payload=observer_payload,
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
