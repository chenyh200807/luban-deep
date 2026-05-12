#!/usr/bin/env python3
"""Build a best-effort AAE composite snapshot from ARR and OM artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.aae_composite import build_aae_composite_run  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.bi_service import get_bi_service  # noqa: E402


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _load_store_payload(kind: str) -> dict | None:
    return get_control_plane_store().latest_payload(kind)


async def _load_live_feedback(days: int = 7, limit: int = 50) -> dict:
    try:
        return await get_bi_service().get_feedback(days=days, limit=limit)
    except Exception as exc:
        return {
            "window_days": days,
            "storage_status": "error",
            "summary": {"total_feedback": 0, "thumbs_down": 0, "thumbs_up": 0, "neutral": 0},
            "top_reason_tags": [],
            "recent": [],
            "error": str(exc),
        }


def _render_markdown(payload: dict) -> str:
    lines = [
        "# AAE Snapshot",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- source_arr_run_id: `{payload.get('source_arr_run_id')}`",
        f"- source_om_run_id: `{payload.get('source_om_run_id')}`",
        "",
        "## Scorecard",
        "",
    ]
    for key, value in sorted((payload.get("scorecard") or {}).items(), key=lambda item: item[0]):
        lines.append(f"- `{key}` => {json.dumps(value, ensure_ascii=False)}")
    lines.extend(
        [
            "",
            "## Composite",
            "",
            f"- {json.dumps(payload.get('composite') or {}, ensure_ascii=False)}",
            "",
            "## Notes",
            "",
            f"- {payload.get('review_note') or '无'}",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor AAE snapshot")
    parser.add_argument("--arr-json")
    parser.add_argument("--om-json")
    parser.add_argument("--feedback-json")
    parser.add_argument("--no-live-feedback", action="store_true")
    args = parser.parse_args()

    arr_payload = _load_json(args.arr_json, expected_kind="arr_runs") or _load_store_payload("arr_runs")
    if not arr_payload:
        raise SystemExit("AAE snapshot requires ARR payload")
    om_payload = _load_json(args.om_json, expected_kind="om_runs") or _load_store_payload("om_runs")
    feedback_payload = _load_json(args.feedback_json) if args.feedback_json else None
    if feedback_payload is None and not args.no_live_feedback:
        feedback_payload = asyncio.run(_load_live_feedback())
    payload = build_aae_composite_run(
        arr_payload=arr_payload,
        om_payload=om_payload,
        feedback_payload=feedback_payload,
    )
    store_paths = get_control_plane_store().write_run(
        kind="aae_composite_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"AAE snapshot completed: {payload['run_id']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
