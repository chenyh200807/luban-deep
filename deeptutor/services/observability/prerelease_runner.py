from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from deeptutor.services.observability import get_control_plane_store
from deeptutor.services.observability.aae_composite import build_aae_composite_run
from deeptutor.services.observability.arr_runner import run_arr, write_arr_artifacts
from deeptutor.services.observability.change_impact import build_change_impact_run
from deeptutor.services.observability.change_impact import collect_git_changed_files
from deeptutor.services.observability.change_impact import render_change_impact_markdown
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot
from deeptutor.services.observability.observer_snapshot import write_observer_snapshot_artifacts
from deeptutor.services.observability.oa_runner import build_oa_run
from deeptutor.services.observability.om_snapshot import build_om_run
from deeptutor.services.observability.release_gate import build_release_gate_report
from deeptutor.services.observability.surface_ack_smoke import run_surface_ack_smoke
from deeptutor.services.observability.unified_ws_smoke import run_unified_ws_smoke


def _write_markdown(path: Path, lines: list[str]) -> str:
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return str(path)


def _write_control_plane_artifact(
    *,
    kind: str,
    payload: dict[str, Any],
    markdown_lines: list[str],
) -> dict[str, str]:
    store_paths = get_control_plane_store().write_run(
        kind=kind,
        run_id=str(payload.get("run_id") or ""),
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    _write_markdown(md_path, markdown_lines)
    return {
        **store_paths,
        "md_path": str(md_path),
    }


def load_metrics_snapshot(*, api_base_url: str, metrics_json: str | None = None) -> dict[str, Any]:
    if metrics_json:
        target = Path(metrics_json).expanduser().resolve()
        if not target.exists():
            raise FileNotFoundError(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("Metrics snapshot must be a JSON object")
        return payload

    url = f"{api_base_url.rstrip('/')}/metrics"
    with httpx.Client(timeout=5.0, trust_env=False) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Metrics snapshot must be a JSON object")
        return payload


def run_prerelease_observability(
    *,
    api_base_url: str,
    arr_mode: str = "lite",
    ws_smoke_message: str | None = None,
    surface_smoke: str | None = None,
    metrics_json: str | None = None,
    output_dir: Path | None = None,
    explicit_long_dialog_source_json: str | None = None,
    long_dialog_max_cases: int | None = None,
) -> dict[str, Any]:
    if arr_mode not in {"lite", "full"}:
        raise ValueError(f"Unsupported arr_mode: {arr_mode}")

    target_output_dir = (output_dir or (Path.cwd() / "tmp" / "observability" / "prerelease")).expanduser().resolve()
    target_output_dir.mkdir(parents=True, exist_ok=True)

    ws_smoke_payload = None
    if ws_smoke_message:
        ws_smoke_payload = asyncio.run(
            run_unified_ws_smoke(
                api_base_url=api_base_url,
                message=ws_smoke_message,
            )
        )

    surface_smoke_payload = None
    if surface_smoke:
        surface_smoke_payload = run_surface_ack_smoke(
            api_base_url=api_base_url,
            surface=surface_smoke,
            session_id=f"surface-smoke-session-{arr_mode}",
            turn_id=f"surface-smoke-turn-{arr_mode}",
            metadata={"source": "run_prerelease_observability"},
        )

    metrics_snapshot = load_metrics_snapshot(api_base_url=api_base_url, metrics_json=metrics_json)
    smoke_checks: list[dict[str, Any]] = []
    if ws_smoke_payload is not None:
        terminal_event = ws_smoke_payload.get("terminal_event") or {}
        smoke_checks.append(
            {
                "name": "unified_ws_smoke",
                "ok": bool(ws_smoke_payload.get("passed")),
                "summary": str(terminal_event.get("content") or terminal_event.get("type") or "").strip(),
                "evidence": [
                    f"terminal_type={terminal_event.get('type')}",
                    f"duration_ms={ws_smoke_payload.get('duration_ms')}",
                ],
            }
        )
    om_payload = build_om_run(metrics_snapshot=metrics_snapshot, stack_health=[], smoke_checks=smoke_checks)
    om_artifacts = _write_control_plane_artifact(
        kind="om_runs",
        payload=om_payload,
        markdown_lines=[
            "# OM Snapshot",
            "",
            f"- run_id: `{om_payload['run_id']}`",
            f"- ready: `{(om_payload.get('health_summary') or {}).get('ready')}`",
            f"- turn_success_ratio: `{(om_payload.get('health_summary') or {}).get('turn_success_ratio')}`",
            f"- turn_first_render_ratio: `{(om_payload.get('health_summary') or {}).get('turn_first_render_ratio')}`",
        ],
    )

    arr_payload = asyncio.run(
        run_arr(
            mode=arr_mode,
            explicit_long_dialog_source_json=explicit_long_dialog_source_json,
            long_dialog_max_cases=long_dialog_max_cases,
            output_dir=target_output_dir / "arr",
            api_base_url=api_base_url,
        )
    )
    arr_artifacts = write_arr_artifacts(arr_payload, output_dir=target_output_dir / "arr")
    arr_store_paths = get_control_plane_store().write_run(
        kind="arr_runs",
        run_id=str(arr_payload.get("run_id") or ""),
        release_id=str((arr_payload.get("release") or {}).get("release_id") or ""),
        payload=arr_payload,
    )

    aae_payload = build_aae_composite_run(arr_payload=arr_payload, om_payload=om_payload)
    aae_artifacts = _write_control_plane_artifact(
        kind="aae_composite_runs",
        payload=aae_payload,
        markdown_lines=[
            "# AAE Snapshot",
            "",
            f"- run_id: `{aae_payload['run_id']}`",
            f"- source_arr_run_id: `{aae_payload.get('source_arr_run_id')}`",
            f"- composite: `{json.dumps(aae_payload.get('composite') or {}, ensure_ascii=False)}`",
            f"- review_note: {aae_payload.get('review_note') or '无'}",
        ],
    )

    observer_payload = build_observer_snapshot(
        metrics_snapshot=metrics_snapshot,
        surface_snapshot=surface_smoke_payload,
    )
    observer_artifacts = write_observer_snapshot_artifacts(
        observer_payload,
        output_dir=target_output_dir / "observer",
    )
    observer_store_paths = get_control_plane_store().write_run(
        kind="observer_snapshots",
        run_id=str(observer_payload.get("run_id") or ""),
        release_id=str((observer_payload.get("release") or {}).get("release_id") or ""),
        payload=observer_payload,
    )
    persisted_observer_payload = get_control_plane_store().latest_payload("observer_snapshots")
    if not isinstance(persisted_observer_payload, dict):
        raise RuntimeError("observer snapshot was written but could not be read from control plane latest")

    change_impact_payload = build_change_impact_run(
        changed_files=collect_git_changed_files(),
        observer_payload=persisted_observer_payload,
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
    )
    change_impact_store_paths = get_control_plane_store().write_run(
        kind="change_impact_runs",
        run_id=str(change_impact_payload.get("run_id") or ""),
        release_id=str((change_impact_payload.get("release") or {}).get("release_id") or ""),
        payload=change_impact_payload,
    )
    change_impact_md_path = Path(change_impact_store_paths["json_path"]).with_suffix(".md")
    change_impact_md_path.write_text(render_change_impact_markdown(change_impact_payload), encoding="utf-8")
    persisted_change_impact_payload = get_control_plane_store().latest_payload("change_impact_runs")
    if not isinstance(persisted_change_impact_payload, dict):
        raise RuntimeError("change impact was written but could not be read from control plane latest")

    oa_payload = build_oa_run(
        mode="pre-release",
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        observer_payload=persisted_observer_payload,
        change_impact_payload=persisted_change_impact_payload,
    )
    oa_artifacts = _write_control_plane_artifact(
        kind="oa_runs",
        payload=oa_payload,
        markdown_lines=[
            "# OA Run",
            "",
            f"- run_id: `{oa_payload['run_id']}`",
            f"- blind_spots: `{len(oa_payload.get('blind_spots') or [])}`",
            f"- root_causes: `{len(oa_payload.get('root_causes') or [])}`",
        ],
    )

    release_gate_payload = build_release_gate_report(
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
        change_impact_payload=persisted_change_impact_payload,
    )
    release_gate_artifacts = _write_control_plane_artifact(
        kind="release_gate_runs",
        payload=release_gate_payload,
        markdown_lines=[
            "# Release Gate",
            "",
            f"- run_id: `{release_gate_payload['run_id']}`",
            f"- final_status: `{release_gate_payload.get('final_status')}`",
            f"- recommendation: `{release_gate_payload.get('recommendation')}`",
        ],
    )

    return {
        "ws_smoke": ws_smoke_payload,
        "surface_smoke": surface_smoke_payload,
        "runs": {
            "om": om_payload,
            "arr": arr_payload,
            "aae": aae_payload,
            "observer_snapshot": persisted_observer_payload,
            "change_impact": persisted_change_impact_payload,
            "oa": oa_payload,
            "release_gate": release_gate_payload,
        },
        "artifacts": {
            "om": om_artifacts,
            "arr": {
                **arr_artifacts,
                "store_json_path": arr_store_paths["json_path"],
                "store_latest_path": arr_store_paths["latest_path"],
                "store_history_path": arr_store_paths["history_path"],
            },
            "aae": aae_artifacts,
            "observer_snapshot": {
                **observer_artifacts,
                "store_json_path": observer_store_paths["json_path"],
                "store_latest_path": observer_store_paths["latest_path"],
                "store_history_path": observer_store_paths["history_path"],
            },
            "change_impact": {
                "json_path": change_impact_store_paths["json_path"],
                "latest_path": change_impact_store_paths["latest_path"],
                "history_path": change_impact_store_paths["history_path"],
                "md_path": str(change_impact_md_path),
            },
            "oa": oa_artifacts,
            "release_gate": release_gate_artifacts,
        },
    }
