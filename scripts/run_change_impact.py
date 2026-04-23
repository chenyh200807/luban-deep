#!/usr/bin/env python3
"""Build a change-impact control-plane run from git changes and observer evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.change_impact import DEFAULT_CHANGE_IMPACT_BASE_REF  # noqa: E402
from deeptutor.services.observability.change_impact import build_change_impact_run  # noqa: E402
from deeptutor.services.observability.change_impact import collect_git_changed_files  # noqa: E402
from deeptutor.services.observability.change_impact import render_change_impact_markdown  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402

DEFAULT_BASE_REF = DEFAULT_CHANGE_IMPACT_BASE_REF


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _load_store_payload(kind: str) -> dict | None:
    return get_control_plane_store().latest_payload(kind)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor change-impact analysis")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--observer-json")
    parser.add_argument("--om-json")
    parser.add_argument("--arr-json")
    parser.add_argument("--aae-json")
    args = parser.parse_args()

    changed_files = args.changed_file or collect_git_changed_files(base_ref=args.base_ref)
    observer_payload = _load_json(args.observer_json, expected_kind="observer_snapshots") or _load_store_payload("observer_snapshots")
    om_payload = _load_json(args.om_json, expected_kind="om_runs") or _load_store_payload("om_runs")
    arr_payload = _load_json(args.arr_json, expected_kind="arr_runs") or _load_store_payload("arr_runs")
    aae_payload = _load_json(args.aae_json, expected_kind="aae_composite_runs") or _load_store_payload("aae_composite_runs")

    payload = build_change_impact_run(
        changed_files=changed_files,
        observer_payload=observer_payload,
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
    )
    store_paths = get_control_plane_store().write_run(
        kind="change_impact_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(render_change_impact_markdown(payload), encoding="utf-8")

    print(f"Change impact completed: {payload['run_id']}")
    print(f"Risk: {payload['risk_level']} ({payload['risk_score']})")
    print(f"Recommendation: {payload['blocking_recommendation']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
