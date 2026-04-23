from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.observability import get_control_plane_store
from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot
from deeptutor.services.observability.surface_events import get_surface_event_store
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import get_turn_event_log

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OBSERVER_DIR = PROJECT_ROOT / "tmp" / "observability" / "observer"


def _safe_latest_payload(
    store: ObservabilityControlPlaneStore,
    kind: str,
) -> dict[str, Any] | None:
    try:
        payload = store.latest_payload(kind)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _release_from_sources(*sources: dict[str, Any] | None) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("release", "release_spine"):
            release = source.get(key)
            if isinstance(release, dict) and release:
                return dict(release)
    return get_release_lineage_snapshot()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return round(float(ordered[index]), 1)


def _summarize_turn_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_count = len(events)
    status_counter = Counter(str(item.get("status") or "unknown").strip() or "unknown" for item in events)
    capability_counter = Counter(str(item.get("capability") or "").strip() or "unknown" for item in events)
    latencies = [
        float(item.get("latency_ms") or 0.0)
        for item in events
        if isinstance(item.get("latency_ms"), (int, float)) and float(item.get("latency_ms") or 0.0) >= 0
    ]
    token_values = [
        int(item.get("token_total") or 0)
        for item in events
        if isinstance(item.get("token_total"), (int, float)) and int(item.get("token_total") or 0) >= 0
    ]
    retrieval_values = [
        bool(item.get("retrieval_hit"))
        for item in events
        if isinstance(item.get("retrieval_hit"), bool)
    ]
    error_count = sum(
        count
        for status, count in status_counter.items()
        if status in {"failed", "error", "cancelled", "timeout"}
    )
    timeout_count = int(status_counter.get("timeout") or 0)
    return {
        "event_count": event_count,
        "status_distribution": dict(sorted(status_counter.items(), key=lambda item: item[0])),
        "capability_distribution": dict(sorted(capability_counter.items(), key=lambda item: item[0])),
        "error_count": int(error_count),
        "timeout_count": timeout_count,
        "error_ratio": round(error_count / event_count, 4) if event_count else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "avg_tokens": round(sum(token_values) / len(token_values), 1) if token_values else None,
        "retrieval_hit_ratio": round(sum(1 for item in retrieval_values if item) / len(retrieval_values), 4)
        if retrieval_values
        else None,
    }


def _coverage_layer(name: str, has_data: bool, reason: str = "") -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "has_data": bool(has_data),
    }
    if reason and not has_data:
        entry["reason"] = reason
    return entry


def _build_data_coverage(layers: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(layers)
    with_data = len([item for item in layers if item.get("has_data")])
    return {
        "layers_total": total,
        "layers_with_data": with_data,
        "coverage_ratio": round(with_data / total, 4) if total else 0.0,
        "layers": layers,
    }


def build_observer_snapshot(
    *,
    store: ObservabilityControlPlaneStore | None = None,
    event_log: TurnEventLog | None = None,
    event_days: int = 1,
    metrics_snapshot: dict[str, Any] | None = None,
    surface_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_store = store or get_control_plane_store()
    turn_log = event_log or get_turn_event_log()

    om_payload = _safe_latest_payload(control_store, "om_runs")
    arr_payload = _safe_latest_payload(control_store, "arr_runs")
    aae_payload = _safe_latest_payload(control_store, "aae_composite_runs")
    benchmark_payload = _safe_latest_payload(control_store, "benchmark_runs")
    daily_trend_payload = _safe_latest_payload(control_store, "daily_trends")
    turn_events = turn_log.load_events_range(days=event_days)
    turn_log_stats = turn_log.stats()
    turn_summary = _summarize_turn_events(turn_events)
    surface_payload = surface_snapshot if isinstance(surface_snapshot, dict) else get_surface_event_store().snapshot()
    surface_coverage = surface_payload.get("coverage") if isinstance(surface_payload, dict) else []
    has_quality_run = bool(arr_payload or benchmark_payload)
    has_surface_coverage = bool(surface_coverage)
    has_metrics = bool(metrics_snapshot)
    release = _release_from_sources(
        metrics_snapshot,
        om_payload,
        arr_payload,
        benchmark_payload,
        aae_payload,
        daily_trend_payload,
        turn_events[0] if turn_events else None,
    )

    layers = [
        _coverage_layer("turn_event_log", turn_summary["event_count"] > 0, "no turn events in window"),
        _coverage_layer("om_snapshot", bool(om_payload), "missing OM snapshot"),
        _coverage_layer("quality_run", has_quality_run, "missing ARR or benchmark run"),
        _coverage_layer("aae_composite", bool(aae_payload), "missing AAE composite"),
        _coverage_layer("surface_ack", has_surface_coverage, "missing surface ack coverage"),
        _coverage_layer("daily_trend", bool(daily_trend_payload), "missing daily trend"),
        _coverage_layer("live_metrics", has_metrics, "not provided to snapshot builder"),
    ]
    blind_spots: list[dict[str, Any]] = []
    if turn_summary["event_count"] <= 0:
        blind_spots.append({"type": "missing_turn_event_log", "severity": "high"})
    if turn_log_stats.get("last_write_error"):
        blind_spots.append(
            {
                "type": "turn_event_log_write_error",
                "severity": "high",
                "evidence": {"last_write_error": turn_log_stats.get("last_write_error")},
            }
        )
    if not om_payload:
        blind_spots.append({"type": "missing_om_snapshot", "severity": "high"})
    if not has_quality_run:
        blind_spots.append({"type": "missing_quality_run", "severity": "high"})
    if not has_surface_coverage:
        blind_spots.append({"type": "missing_surface_coverage", "severity": "medium"})
    if not daily_trend_payload:
        blind_spots.append({"type": "missing_daily_trend", "severity": "low"})

    run_id = f"observer-snapshot-{int(time.time())}"
    return {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "window": {"event_days": max(int(event_days or 1), 1)},
        "data_coverage": _build_data_coverage(layers),
        "blind_spots": blind_spots,
        "turn_events": turn_summary,
        "turn_event_log": turn_log_stats,
        "source_runs": {
            "om_run_id": (om_payload or {}).get("run_id"),
            "arr_run_id": (arr_payload or {}).get("run_id"),
            "aae_run_id": (aae_payload or {}).get("run_id"),
            "benchmark_run_id": ((benchmark_payload or {}).get("run_manifest") or {}).get("run_id")
            or (benchmark_payload or {}).get("run_id"),
            "daily_trend_run_id": ((daily_trend_payload or {}).get("run_manifest") or {}).get("run_id")
            or (daily_trend_payload or {}).get("run_id"),
        },
        "signals": {
            "om_health_summary": (om_payload or {}).get("health_summary") or {},
            "arr_summary": (arr_payload or {}).get("summary") or {},
            "aae_scorecard": (aae_payload or {}).get("scorecard") or {},
            "benchmark_summary": (benchmark_payload or {}).get("summary") or {},
            "daily_trend_metrics": (daily_trend_payload or {}).get("metrics") or {},
            "surface_snapshot": surface_payload,
            "live_metrics_snapshot": metrics_snapshot or {},
        },
    }


def write_observer_snapshot_artifacts(
    payload: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = (output_dir or DEFAULT_OBSERVER_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "raw_data_latest.json"
    md_path = target_dir / "raw_data_latest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_observer_snapshot_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def render_observer_snapshot_markdown(payload: dict[str, Any]) -> str:
    coverage = payload.get("data_coverage") or {}
    turn_events = payload.get("turn_events") or {}
    lines = [
        "# Observer Snapshot",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- coverage: `{coverage.get('layers_with_data')}/{coverage.get('layers_total')}`",
        f"- turn_events: `{turn_events.get('event_count')}`",
        f"- turn_error_ratio: `{turn_events.get('error_ratio')}`",
        "",
        "## Blind Spots",
        "",
    ]
    blind_spots = payload.get("blind_spots") or []
    if not blind_spots:
        lines.append("- none")
    else:
        for item in blind_spots:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)
