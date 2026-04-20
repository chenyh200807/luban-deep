#!/usr/bin/env python3
"""Run a best-effort Observer Analyst pass from OM/ARR/AAE signals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.oa_runner import build_oa_run  # noqa: E402


def _load_json(path: str | None) -> dict | None:
    if not path:
        return None
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    return json.loads(target.read_text(encoding="utf-8"))


def _load_store_payload(kind: str) -> dict | None:
    latest = get_control_plane_store().latest_run(kind)
    return (latest or {}).get("payload") if latest else None


def _render_markdown(payload: dict) -> str:
    lines = [
        "# OA Run",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- mode: `{payload.get('mode')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        "",
        "## Blind Spots",
        "",
    ]
    blind_spots = payload.get("blind_spots") or []
    if not blind_spots:
        lines.append("- 无")
    else:
        for item in blind_spots:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.extend(["", "## Root Causes", ""])
    root_causes = payload.get("root_causes") or []
    if not root_causes:
        lines.append("- 无")
    else:
        for item in root_causes:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor OA")
    parser.add_argument("--mode", choices=["daily", "pre-release", "incident"], default="daily")
    parser.add_argument("--om-json")
    parser.add_argument("--arr-json")
    parser.add_argument("--aae-json")
    args = parser.parse_args()

    om_payload = _load_json(args.om_json) or _load_store_payload("om_runs")
    arr_payload = _load_json(args.arr_json) or _load_store_payload("arr_runs")
    aae_payload = _load_json(args.aae_json) or _load_store_payload("aae_composite_runs")
    payload = build_oa_run(mode=args.mode, om_payload=om_payload, arr_payload=arr_payload, aae_payload=aae_payload)
    store_paths = get_control_plane_store().write_run(
        kind="oa_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"OA run completed: {payload['run_id']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
