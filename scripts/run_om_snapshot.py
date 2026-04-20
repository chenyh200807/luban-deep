#!/usr/bin/env python3
"""Build a best-effort OM snapshot from /metrics and optional stack probes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.om_snapshot import build_om_run  # noqa: E402


def _load_metrics_from_url(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/metrics"
    with httpx.Client(timeout=5.0, trust_env=False) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _load_metrics_from_file(path: str) -> dict:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    return json.loads(target.read_text(encoding="utf-8"))


def _probe_url(name: str, url: str) -> dict:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
        return {
            "name": name,
            "url": url,
            "ok": 200 <= response.status_code < 400,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "ok": False,
            "error": str(exc),
        }


def _render_markdown(payload: dict) -> str:
    health = payload.get("health_summary") or {}
    lines = [
        "# OM Snapshot",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- ready: `{health.get('ready')}`",
        f"- turn_success_ratio: `{health.get('turn_success_ratio')}`",
        f"- turn_first_render_ratio: `{health.get('turn_first_render_ratio')}`",
        f"- provider_error_ratio: `{health.get('provider_error_ratio')}`",
        "",
        "## SLO Checks",
        "",
    ]
    for item in (payload.get("slo_summary") or {}).get("checks") or []:
        lines.append(f"- `{item['name']}` => `{item['status']}` value={item.get('value')} target={item.get('target')}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor OM snapshot")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--metrics-json", help="离线 metrics JSON 文件；提供后不走 live HTTP 拉取")
    parser.add_argument("--langfuse-url")
    parser.add_argument("--grafana-url")
    parser.add_argument("--prometheus-url")
    args = parser.parse_args()

    metrics_snapshot = _load_metrics_from_file(args.metrics_json) if args.metrics_json else _load_metrics_from_url(args.api_base_url)
    stack_health = []
    if args.langfuse_url:
        stack_health.append(_probe_url("langfuse", args.langfuse_url))
    if args.grafana_url:
        stack_health.append(_probe_url("grafana", args.grafana_url))
    if args.prometheus_url:
        stack_health.append(_probe_url("prometheus", args.prometheus_url))

    payload = build_om_run(metrics_snapshot=metrics_snapshot, stack_health=stack_health)
    store = get_control_plane_store()
    store_paths = store.write_run(
        kind="om_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    for index, candidate in enumerate(payload.get("incident_candidates") or []):
        store.write_run(
            kind="incident_ledger",
            run_id=f"{payload['run_id']}-incident-{index + 1}",
            release_id=str((payload.get("release") or {}).get("release_id") or ""),
            payload={
                "source_om_run_id": payload["run_id"],
                "candidate": candidate,
            },
        )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"OM snapshot completed: {payload['run_id']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
