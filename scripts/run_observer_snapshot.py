#!/usr/bin/env python3
"""Build the minimal ObserverSnapshot raw evidence bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot  # noqa: E402
from deeptutor.services.observability.observer_snapshot import write_observer_snapshot_artifacts  # noqa: E402


def _load_json(path: str | None) -> dict | None:
    if not path:
        return None
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Observer snapshot input must be a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor ObserverSnapshot")
    parser.add_argument("--metrics-json", help="可选 live /metrics JSON；提供后进入 raw evidence bundle")
    parser.add_argument("--event-days", type=int, default=1)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    metrics_snapshot = _load_json(args.metrics_json)
    store = get_control_plane_store()
    payload = build_observer_snapshot(
        store=store,
        event_days=max(int(args.event_days or 1), 1),
        metrics_snapshot=metrics_snapshot,
    )
    artifact_paths = write_observer_snapshot_artifacts(
        payload,
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
    )
    store_paths = store.write_run(
        kind="observer_snapshots",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )

    print(f"Observer snapshot completed: {payload['run_id']}")
    print(f"JSON: {artifact_paths['json_path']}")
    print(f"MD:   {artifact_paths['md_path']}")
    print(f"Store JSON: {store_paths['json_path']}")


if __name__ == "__main__":
    main()
