"""Cross-worker metric snapshot merge (Step 2 multiworker fix, design B).

`/metrics/prometheus` renders from in-process singletons. With ``UVICORN_WORKERS>1``
each worker keeps its own counters and a scrape only hits one of them, so counts are
under-reported and a per-worker state gauge (an open circuit breaker on the unscraped
worker) can be missed entirely.

Design B keeps the hot path untouched: each worker periodically dumps its existing
``snapshot()`` output to ``<observability_dir>/worker_metrics/worker-<pid>.json``; the
scrape endpoint reads every fresh worker file, combines them with its own live snapshot,
and feeds the merged result into the unchanged renderer. No new dependency, no contract
change, no per-request overhead — only a low-frequency background dump and a read+merge
at scrape time.

A bundle is ``{"http", "turn", "surface", "providers", "circuit_breakers"}``. Readiness
and release lineage are per-worker-consistent and are taken from the live worker directly
by the endpoint, so they are not part of the merge.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

WORKER_METRICS_SUBDIR = "worker_metrics"
DEFAULT_STALENESS_SECONDS = 60.0
DEFAULT_DUMP_INTERVAL_SECONDS = 15.0

BUNDLE_KEYS = ("http", "turn", "surface", "providers", "circuit_breakers")


def _now(now: float | None) -> float:
    return time.time() if now is None else now


def metrics_dir(base_dir: Path) -> Path:
    return Path(base_dir) / WORKER_METRICS_SUBDIR


# --------------------------------------------------------------------------- I/O

def dump_worker_snapshot(base_dir: Path, pid: int, bundle: dict[str, Any], *, now: float | None = None) -> None:
    """Atomically write one worker's snapshot bundle. Temp + os.replace so a concurrent
    reader never observes a half-written file."""
    target_dir = metrics_dir(base_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {"pid": int(pid), "ts": _now(now), "bundle": bundle}
    final = target_dir / f"worker-{int(pid)}.json"
    tmp = target_dir / f".worker-{int(pid)}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, final)


def remove_worker_snapshot(base_dir: Path, pid: int) -> None:
    """Best-effort removal of this worker's file on graceful shutdown."""
    try:
        (metrics_dir(base_dir) / f"worker-{int(pid)}.json").unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _pid_is_alive(pid: int) -> bool:
    """Whether a process with this pid currently exists in the shared namespace.
    uvicorn --workers forks all workers inside one container (one pid namespace), so the
    scrape-handling worker can probe a sibling worker's pid with signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user — still alive
    except OSError:
        return True  # unknown error: be conservative, do not reap on uncertainty
    return True


def read_worker_snapshots(
    base_dir: Path,
    *,
    staleness_seconds: float = DEFAULT_STALENESS_SECONDS,
    now: float | None = None,
    exclude_pid: int | None = None,
    pid_is_alive: "callable | None" = None,
) -> list[dict[str, Any]]:
    """Return fresh sibling worker bundles for cross-worker merge. A file is excluded when:

    - it is not a dict (corrupt / unexpected-shape JSON) — skipped, never fatal (a valid
      JSON scalar/list must not raise AttributeError on ``.get``);
    - it belongs to ``exclude_pid`` (caller merges its own live snapshot for itself);
    - its writer pid is no longer alive — the worker crashed; the file is **reaped
      immediately** so a dead worker's last snapshot cannot keep being summed. Without this,
      on an OOM-kill the dead file stays within the staleness window while the replacement
      worker (new pid) also dumps, double-counting counters ~Nx until age-out, then dropping
      them (a counter reset that corrupts ``rate()``). This is the crash path the saturated
      single-host deployment invites;
    - its recorded ``ts`` is older than ``staleness_seconds`` — backstop for a live-but-not-
      dumping worker (its dump loop died) and for pid reuse.

    ``pid_is_alive`` is injectable for deterministic tests; production uses real ``os.kill``.
    """
    alive = pid_is_alive or _pid_is_alive
    now_ts = _now(now)
    directory = metrics_dir(base_dir)
    bundles: list[dict[str, Any]] = []
    if not directory.is_dir():
        return bundles
    for path in sorted(directory.glob("worker-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue  # valid JSON but not our shape — skip, never .get on a non-dict
        pid = int(payload.get("pid", -1))
        if exclude_pid is not None and pid == int(exclude_pid):
            continue
        if not alive(pid):
            # Crashed worker: drop now AND reap, so it neither double-counts nor leaks.
            try:
                path.unlink()
            except OSError:
                pass
            continue
        ts = float(payload.get("ts", 0.0))
        if now_ts - ts > staleness_seconds:
            continue
        bundle = payload.get("bundle")
        if isinstance(bundle, dict):
            bundles.append(bundle)
    return bundles


def collect_merged_snapshots(
    base_dir: Path,
    live_pid: int,
    live_bundle: dict[str, Any],
    *,
    staleness_seconds: float = DEFAULT_STALENESS_SECONDS,
    now: float | None = None,
    pid_is_alive: "callable | None" = None,
) -> dict[str, Any]:
    """Merge this worker's live (always-fresh) bundle with every other worker's fresh
    file. Single-worker => identity on ``live_bundle``."""
    others = read_worker_snapshots(
        base_dir,
        staleness_seconds=staleness_seconds,
        now=now,
        exclude_pid=live_pid,
        pid_is_alive=pid_is_alive,
    )
    return merge_metric_snapshots([live_bundle, *others])


# ------------------------------------------------------------------------- merge

def merge_metric_snapshots(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    bundles = [b for b in bundles if isinstance(b, dict)]
    if not bundles:
        bundles = [{}]
    return {
        "http": _merge_http([b.get("http") or {} for b in bundles]),
        "turn": _merge_turn([b.get("turn") or {} for b in bundles]),
        "surface": _merge_surface([b.get("surface") or {} for b in bundles]),
        "providers": _merge_providers([b.get("providers") or {} for b in bundles]),
        "circuit_breakers": _merge_circuit_breakers([b.get("circuit_breakers") or {} for b in bundles]),
    }


def _weighted_avg(pairs: list[tuple[float, float]]) -> float:
    """pairs of (avg, weight) -> exact combined mean. weight is the per-worker count, so
    avg*weight reconstructs the per-worker total and the merge is exact."""
    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return 0.0
    return round(sum(a * w for a, w in pairs) / total_weight, 2)


def _merge_http(snaps: list[dict[str, Any]]) -> dict[str, Any]:
    requests_total = sum(int(s.get("requests_total", 0)) for s in snaps)
    errors_total = sum(int(s.get("errors_total", 0)) for s in snaps)
    uptime = max((float(s.get("uptime_seconds", 0.0)) for s in snaps), default=0.0)
    started = min(
        (float(s["started_at"]) for s in snaps if s.get("started_at")),
        default=0.0,
    )

    status_counts: dict[str, int] = defaultdict(int)
    for s in snaps:
        for code, count in (s.get("status_counts") or {}).items():
            status_counts[str(code)] += int(count)

    route_req: dict[str, int] = defaultdict(int)
    route_err: dict[str, int] = defaultdict(int)
    route_lat_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for s in snaps:
        for r in s.get("routes") or []:
            key = str(r.get("route", ""))
            req = int(r.get("requests", 0))
            route_req[key] += req
            route_err[key] += int(r.get("errors", 0))
            route_lat_pairs[key].append((float(r.get("avg_latency_ms", 0.0)), req))
    routes = [
        {
            "route": key,
            "requests": route_req[key],
            "errors": route_err[key],
            "avg_latency_ms": _weighted_avg(route_lat_pairs[key]),
        }
        for key in sorted(route_req, key=lambda k: (-route_req[k], k))
    ]

    recent: list[dict[str, Any]] = []
    for s in snaps:
        recent.extend(s.get("recent_errors") or [])
    recent.sort(key=lambda e: float(e.get("timestamp", 0.0)), reverse=True)

    return {
        "started_at": started,
        "uptime_seconds": round(uptime, 3),
        "requests_total": requests_total,
        "errors_total": errors_total,
        "status_counts": dict(sorted(status_counts.items())),
        "routes": routes,
        "recent_errors": recent[:50],
    }


def _merge_turn(snaps: list[dict[str, Any]]) -> dict[str, Any]:
    def s(field: str) -> int:
        return sum(int(x.get(field, 0)) for x in snaps)

    # finished turns = completed + failed + cancelled; this is exactly the latency sample
    # count behind turn_avg_latency_ms, so it re-weights the merged average exactly.
    lat_pairs = [
        (
            float(x.get("turn_avg_latency_ms", 0.0)),
            int(x.get("turns_completed_total", 0))
            + int(x.get("turns_failed_total", 0))
            + int(x.get("turns_cancelled_total", 0)),
        )
        for x in snaps
    ]

    stage_count: dict[str, int] = defaultdict(int)
    stage_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for x in snaps:
        for entry in x.get("turn_stage_avg_latency_ms") or []:
            stage = str(entry.get("stage", ""))
            count = int(entry.get("count", 0))
            stage_count[stage] += count
            stage_pairs[stage].append((float(entry.get("avg_latency_ms", 0.0)), count))
    stages = [
        {"stage": stage, "avg_latency_ms": _weighted_avg(stage_pairs[stage]), "count": stage_count[stage]}
        for stage in sorted(stage_count)
    ]

    return {
        "ws_active_connections": s("ws_active_connections"),
        "ws_opened_total": s("ws_opened_total"),
        "ws_closed_total": s("ws_closed_total"),
        "turns_started_total": s("turns_started_total"),
        "turns_completed_total": s("turns_completed_total"),
        "turns_failed_total": s("turns_failed_total"),
        "turns_cancelled_total": s("turns_cancelled_total"),
        "turns_in_flight": s("turns_in_flight"),
        "turn_avg_latency_ms": _weighted_avg(lat_pairs),
        "turn_stage_avg_latency_ms": stages,
    }


def _merge_surface(snaps: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for s in snaps:
        for e in s.get("event_counts") or []:
            key = (str(e.get("surface", "")), str(e.get("event_name", "")), str(e.get("status", "")))
            event_counts[key] += int(e.get("count", 0))
    merged_events = [
        {"surface": k[0], "event_name": k[1], "status": k[2], "count": v}
        for k, v in sorted(event_counts.items())
    ]

    raw: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in snaps:
        for c in s.get("coverage") or []:
            surface = str(c.get("surface", ""))
            for field in ("start_turn_sent", "first_visible_content_rendered", "done_rendered", "surface_render_failed"):
                raw[surface][field] += int(c.get(field, 0))
    coverage = []
    for surface in sorted(raw):
        counts = raw[surface]
        start = counts["start_turn_sent"]
        coverage.append(
            {
                "surface": surface,
                "start_turn_sent": start,
                "first_visible_content_rendered": counts["first_visible_content_rendered"],
                "done_rendered": counts["done_rendered"],
                "surface_render_failed": counts["surface_render_failed"],
                "first_render_coverage_ratio": round(counts["first_visible_content_rendered"] / start, 4) if start else None,
                "done_render_coverage_ratio": round(counts["done_rendered"] / start, 4) if start else None,
            }
        )

    return {"event_counts": merged_events, "coverage": coverage, "recent_events": []}


def _merge_providers(snaps: list[dict[str, Any]]) -> dict[str, Any]:
    providers: dict[str, dict[str, Any]] = {}
    names = {name for s in snaps for name in s.keys()}
    for name in sorted(names):
        total = sum(int(s.get(name, {}).get("total_calls", 0)) for s in snaps)
        errors = sum(int(s.get(name, {}).get("error_calls", 0)) for s in snaps)
        providers[name] = {
            "total_calls": total,
            "error_calls": errors,
            "error_rate": (errors / total) if total > 0 else 0.0,
            # OR across workers: any worker over threshold / alerting => merged alerts.
            "threshold_exceeded": any(bool(s.get(name, {}).get("threshold_exceeded")) for s in snaps),
            "alert_open": any(bool(s.get(name, {}).get("alert_open")) for s in snaps),
        }
    return providers


_BREAKER_SEVERITY = {"closed": 0, "half-open": 1, "open": 2}


def _merge_circuit_breakers(snaps: list[dict[str, Any]]) -> dict[str, Any]:
    breakers: dict[str, dict[str, Any]] = {}
    names = {name for s in snaps for name in s.keys()}
    for name in sorted(names):
        entries = [s[name] for s in snaps if name in s]
        # worst state wins so an open breaker on any worker is never masked by a closed one.
        state = max((str(e.get("state", "closed")) for e in entries), key=lambda st: _BREAKER_SEVERITY.get(st, 0))
        breakers[name] = {
            "state": state,
            "failure_count": max(int(e.get("failure_count", 0)) for e in entries),
            "last_failure_time": max(float(e.get("last_failure_time", 0.0)) for e in entries),
            "recovery_timeout": max(int(e.get("recovery_timeout", 0)) for e in entries),
            "failure_threshold": max(int(e.get("failure_threshold", 0)) for e in entries),
        }
    return breakers
