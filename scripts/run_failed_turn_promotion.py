#!/usr/bin/env python3
"""Promote failed turn observations into incident replay candidates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.failed_turn_promotion import build_failed_turn_incident_report  # noqa: E402
from deeptutor.services.observability.failed_turn_promotion import write_failed_turn_incident_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote failed turns into incident replay candidates")
    parser.add_argument("--incident-id")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    payload = build_failed_turn_incident_report(
        incident_id=args.incident_id,
        days=args.days,
        limit=args.limit,
    )
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    artifact_paths = write_failed_turn_incident_report(payload, output_dir=output_dir)
    store_paths = get_control_plane_store().write_run(
        kind="incident_ledger",
        run_id=str((payload.get("run_manifest") or {}).get("run_id") or ""),
        release_id=str((payload.get("release_spine") or {}).get("release_id") or ""),
        payload=payload,
    )

    print("Failed turn promotion completed")
    print(f"Replay candidates: {payload.get('classification', {}).get('replay_candidate_count')}")
    print(f"JSON: {artifact_paths['json_path']}")
    print(f"MD:   {artifact_paths['md_path']}")
    print(f"Store latest: {store_paths['latest_path']}")


if __name__ == "__main__":
    main()
