#!/usr/bin/env python3
"""Build a release gate report from OM/ARR/AAE/OA runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.observability.release_gate import build_release_gate_report  # noqa: E402


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _load_store_payload(kind: str) -> dict | None:
    return get_control_plane_store().latest_payload(kind)


def _render_markdown(payload: dict) -> str:
    lines = [
        "# Release Gate",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- final_status: `{payload.get('final_status')}`",
        f"- recommendation: `{payload.get('recommendation')}`",
        "",
        "## Gates",
        "",
    ]
    for item in payload.get("gate_results") or []:
        lines.append(f"- `{item['gate']}` => `{item['status']}` | {item['summary']}")
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    if not blockers:
        lines.append("- 无")
    else:
        for blocker in blockers:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor release gate")
    parser.add_argument("--om-json")
    parser.add_argument("--arr-json")
    parser.add_argument("--aae-json")
    parser.add_argument("--oa-json")
    args = parser.parse_args()

    om_payload = _load_json(args.om_json, expected_kind="om_runs") or _load_store_payload("om_runs")
    arr_payload = _load_json(args.arr_json, expected_kind="arr_runs") or _load_store_payload("arr_runs")
    aae_payload = _load_json(args.aae_json, expected_kind="aae_composite_runs") or _load_store_payload("aae_composite_runs")
    oa_payload = _load_json(args.oa_json, expected_kind="oa_runs") or _load_store_payload("oa_runs")
    payload = build_release_gate_report(
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
    )
    store_paths = get_control_plane_store().write_run(
        kind="release_gate_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"Release gate completed: {payload['run_id']}")
    print(f"Final status: {payload['final_status']}")
    print(f"Recommendation: {payload['recommendation']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
