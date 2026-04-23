#!/usr/bin/env python3
"""Run the daily observability spine: ObserverSnapshot -> ChangeImpact -> OA -> Gate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.change_impact import DEFAULT_CHANGE_IMPACT_BASE_REF  # noqa: E402
from deeptutor.services.observability.change_impact import build_change_impact_run  # noqa: E402
from deeptutor.services.observability.change_impact import collect_git_changed_files  # noqa: E402
from deeptutor.services.observability.change_impact import render_change_impact_markdown  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.observability.oa_runner import build_oa_run  # noqa: E402
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot  # noqa: E402
from deeptutor.services.observability.observer_snapshot import write_observer_snapshot_artifacts  # noqa: E402
from deeptutor.services.observability.release_gate import build_release_gate_report  # noqa: E402
from deeptutor.services.observability.run_history import build_observability_run_history_from_dir  # noqa: E402

DEFAULT_BASE_REF = DEFAULT_CHANGE_IMPACT_BASE_REF


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict[str, Any] | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_oa_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# OA Run",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- mode: `{payload.get('mode')}`",
        f"- causal_candidates: `{len(payload.get('causal_candidates') or [])}`",
        f"- root_causes: `{len(payload.get('root_causes') or [])}`",
        f"- blind_spots: `{len(payload.get('blind_spots') or [])}`",
    ]
    return "\n".join(lines)


def _render_gate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Release Gate",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- final_status: `{payload.get('final_status')}`",
        f"- recommendation: `{payload.get('recommendation')}`",
        "",
        "## Gates",
        "",
    ]
    for item in payload.get("gate_results") or []:
        lines.append(f"- `{item.get('gate')}` => `{item.get('status')}` | {item.get('summary')}")
    return "\n".join(lines)


def build_daily_run_history(*, store_dir: str | Path, limit: int = 20) -> dict[str, Any]:
    return build_observability_run_history_from_dir(store_dir=store_dir, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor daily observability control-plane spine")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--metrics-json")
    parser.add_argument("--event-days", type=int, default=1)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    store = get_control_plane_store()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else store.base_dir / "_daily"
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_snapshot = _load_json(args.metrics_json)
    observer_payload = build_observer_snapshot(
        store=store,
        event_days=max(int(args.event_days or 1), 1),
        metrics_snapshot=metrics_snapshot,
    )
    observer_artifacts = write_observer_snapshot_artifacts(
        observer_payload,
        output_dir=output_dir / "observer",
    )
    store.write_run(
        kind="observer_snapshots",
        run_id=observer_payload["run_id"],
        release_id=str((observer_payload.get("release") or {}).get("release_id") or ""),
        payload=observer_payload,
    )

    changed_files = args.changed_file or collect_git_changed_files(base_ref=args.base_ref)
    om_payload = store.latest_payload("om_runs")
    arr_payload = store.latest_payload("arr_runs")
    aae_payload = store.latest_payload("aae_composite_runs")
    change_impact_payload = build_change_impact_run(
        changed_files=changed_files,
        observer_payload=observer_payload,
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
    )
    change_paths = store.write_run(
        kind="change_impact_runs",
        run_id=change_impact_payload["run_id"],
        release_id=str((change_impact_payload.get("release") or {}).get("release_id") or ""),
        payload=change_impact_payload,
    )
    Path(change_paths["json_path"]).with_suffix(".md").write_text(
        render_change_impact_markdown(change_impact_payload),
        encoding="utf-8",
    )

    oa_payload = build_oa_run(
        mode="daily",
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        observer_payload=observer_payload,
        change_impact_payload=change_impact_payload,
    )
    oa_paths = store.write_run(
        kind="oa_runs",
        run_id=oa_payload["run_id"],
        release_id=str((oa_payload.get("release") or {}).get("release_id") or ""),
        payload=oa_payload,
    )
    Path(oa_paths["json_path"]).with_suffix(".md").write_text(
        _render_oa_markdown(oa_payload),
        encoding="utf-8",
    )

    gate_payload = build_release_gate_report(
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
        change_impact_payload=change_impact_payload,
    )
    gate_paths = store.write_run(
        kind="release_gate_runs",
        run_id=gate_payload["run_id"],
        release_id=str((gate_payload.get("release") or {}).get("release_id") or ""),
        payload=gate_payload,
    )
    Path(gate_paths["json_path"]).with_suffix(".md").write_text(
        _render_gate_markdown(gate_payload),
        encoding="utf-8",
    )

    daily_payload = {
        "run_id": f"observability-daily-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": gate_payload.get("release") or oa_payload.get("release") or {},
        "source_runs": {
            "observer_snapshot_run_id": observer_payload.get("run_id"),
            "change_impact_run_id": change_impact_payload.get("run_id"),
            "oa_run_id": oa_payload.get("run_id"),
            "release_gate_run_id": gate_payload.get("run_id"),
        },
        "metrics": {
            "change_impact_risk_level": change_impact_payload.get("risk_level"),
            "oa_root_cause_count": len(oa_payload.get("root_causes") or []),
            "oa_causal_candidate_count": len(oa_payload.get("causal_candidates") or []),
            "release_gate_status": gate_payload.get("final_status"),
        },
    }
    daily_paths = store.write_run(
        kind="daily_trends",
        run_id=daily_payload["run_id"],
        release_id=str((daily_payload.get("release") or {}).get("release_id") or ""),
        payload=daily_payload,
    )
    run_history = build_daily_run_history(store_dir=store.base_dir)
    _write_json(output_dir / "run_history_latest.json", run_history)

    print(f"Daily observability completed: {daily_payload['run_id']}")
    print(f"Observer JSON: {observer_artifacts['json_path']}")
    print(f"ChangeImpact JSON: {change_paths['json_path']}")
    print(f"OA JSON: {oa_paths['json_path']}")
    print(f"ReleaseGate JSON: {gate_paths['json_path']}")
    print(f"DailyTrend JSON: {daily_paths['json_path']}")
    print(f"RunHistory JSON: {output_dir / 'run_history_latest.json'}")


if __name__ == "__main__":
    main()
