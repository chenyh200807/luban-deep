from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from deeptutor.services.observability import get_control_plane_store
from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot
from deeptutor.services.observability.surface_events import get_surface_event_store
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import get_turn_event_log
from deeptutor.services.path_service import get_path_service

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OBSERVER_DIR = PROJECT_ROOT / "tmp" / "observability" / "observer"
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"1[3-9]\d{9}"), "[PHONE]"),
    (re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[EMAIL]"),
    (re.compile(r"(?i)(sk-|pk-|api[_-]?key)[A-Za-z0-9_\-]{8,}"), "[API_KEY]"),
)
_LOG_LEVEL_PATTERN = re.compile(r"\[(ERROR|WARNING|WARN|CRITICAL)\s*\]|\b(ERROR|WARNING|WARN|CRITICAL)\b")


def _safe_latest_payload(
    store: ObservabilityControlPlaneStore,
    kind: str,
) -> dict[str, Any] | None:
    try:
        payload = store.latest_payload(kind)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _safe_latest_run(
    store: ObservabilityControlPlaneStore,
    kind: str,
) -> dict[str, Any] | None:
    try:
        record = store.latest_run(kind)
    except Exception:
        return None
    return record if isinstance(record, dict) else None


def _payload_from_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = (record or {}).get("payload")
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


def _redact_excerpt(value: Any, *, limit: int = 240) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _timestamp_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value)).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return ""


def _default_conversation_db_path() -> Path:
    return get_path_service().get_chat_history_db()


def _default_backend_log_paths(*, days: int) -> list[Path]:
    path_service = get_path_service()
    paths: list[Path] = []
    for offset in range(max(int(days or 1), 1)):
        day = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        paths.append(path_service.get_logs_dir() / f"deeptutor_{day}.log")
    paths.append(PROJECT_ROOT / "tmp" / "backend.log")
    return paths


def _sqlite_count(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _sqlite_counter(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> dict[str, int]:
    counter: dict[str, int] = {}
    for row in conn.execute(query, params).fetchall():
        key = str(row[0] or "unknown").strip() or "unknown"
        counter[key] = int(row[1] or 0)
    return dict(sorted(counter.items(), key=lambda item: item[0]))


def _build_recent_conversations_snapshot(
    *,
    db_path: Path | None,
    days: int,
    limit: int,
) -> dict[str, Any]:
    target = (db_path or _default_conversation_db_path()).expanduser().resolve()
    window_days = max(int(days or 1), 1)
    cutoff = time.time() - (window_days * 24 * 60 * 60)
    base: dict[str, Any] = {
        "db_path": str(target),
        "window_days": window_days,
        "cutoff_timestamp": cutoff,
        "session_count": 0,
        "conversation_count": 0,
        "message_count": 0,
        "turn_count": 0,
        "failed_turn_count": 0,
        "role_distribution": {},
        "turn_status_distribution": {},
        "capability_distribution": {},
        "source_distribution": {},
        "recent_sessions": [],
        "sample_limit": max(int(limit or 1), 1),
        "read_error": "",
    }
    if not target.exists():
        base["read_error"] = "conversation db missing"
        return base

    try:
        with sqlite3.connect(target) as conn:
            conn.row_factory = sqlite3.Row
            session_rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.source,
                    s.archived,
                    COALESCE(NULLIF(s.conversation_id, ''), s.id) AS conversation_key,
                    COUNT(m.id) AS message_count,
                    SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) AS user_message_count,
                    SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) AS assistant_message_count,
                    (
                        SELECT content FROM messages lm
                        WHERE lm.session_id = s.id AND lm.role = 'user'
                        ORDER BY lm.id DESC LIMIT 1
                    ) AS last_user_message,
                    (
                        SELECT content FROM messages lm
                        WHERE lm.session_id = s.id AND lm.role = 'assistant'
                        ORDER BY lm.id DESC LIMIT 1
                    ) AS last_assistant_message,
                    (
                        SELECT status FROM turns lt
                        WHERE lt.session_id = s.id
                        ORDER BY lt.updated_at DESC LIMIT 1
                    ) AS latest_turn_status,
                    (
                        SELECT error FROM turns lt
                        WHERE lt.session_id = s.id
                        ORDER BY lt.updated_at DESC LIMIT 1
                    ) AS latest_turn_error
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.updated_at >= ?
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.id DESC
                LIMIT ?
                """,
                (cutoff, max(int(limit or 1), 1)),
            ).fetchall()
            base["session_count"] = _sqlite_count(
                conn,
                "SELECT COUNT(*) FROM sessions WHERE updated_at >= ?",
                (cutoff,),
            )
            base["conversation_count"] = _sqlite_count(
                conn,
                "SELECT COUNT(DISTINCT COALESCE(NULLIF(conversation_id, ''), id)) FROM sessions WHERE updated_at >= ?",
                (cutoff,),
            )
            base["message_count"] = _sqlite_count(
                conn,
                "SELECT COUNT(*) FROM messages WHERE created_at >= ?",
                (cutoff,),
            )
            base["turn_count"] = _sqlite_count(
                conn,
                "SELECT COUNT(*) FROM turns WHERE updated_at >= ?",
                (cutoff,),
            )
            base["failed_turn_count"] = _sqlite_count(
                conn,
                "SELECT COUNT(*) FROM turns WHERE updated_at >= ? AND status IN ('failed', 'error', 'timeout', 'cancelled')",
                (cutoff,),
            )
            base["role_distribution"] = _sqlite_counter(
                conn,
                "SELECT role, COUNT(*) FROM messages WHERE created_at >= ? GROUP BY role",
                (cutoff,),
            )
            base["turn_status_distribution"] = _sqlite_counter(
                conn,
                "SELECT status, COUNT(*) FROM turns WHERE updated_at >= ? GROUP BY status",
                (cutoff,),
            )
            base["capability_distribution"] = _sqlite_counter(
                conn,
                "SELECT capability, COUNT(*) FROM turns WHERE updated_at >= ? GROUP BY capability",
                (cutoff,),
            )
            base["source_distribution"] = _sqlite_counter(
                conn,
                "SELECT source, COUNT(*) FROM sessions WHERE updated_at >= ? GROUP BY source",
                (cutoff,),
            )
            base["recent_sessions"] = [
                {
                    "session_id": str(row["id"] or ""),
                    "conversation_key": str(row["conversation_key"] or ""),
                    "title": _redact_excerpt(row["title"], limit=160),
                    "source": str(row["source"] or ""),
                    "archived": bool(row["archived"]),
                    "created_at": _timestamp_iso(row["created_at"]),
                    "updated_at": _timestamp_iso(row["updated_at"]),
                    "message_count": int(row["message_count"] or 0),
                    "user_message_count": int(row["user_message_count"] or 0),
                    "assistant_message_count": int(row["assistant_message_count"] or 0),
                    "latest_turn_status": str(row["latest_turn_status"] or ""),
                    "latest_turn_error": _redact_excerpt(row["latest_turn_error"], limit=240),
                    "last_user_excerpt": _redact_excerpt(row["last_user_message"], limit=240),
                    "last_assistant_excerpt": _redact_excerpt(row["last_assistant_message"], limit=240),
                }
                for row in session_rows
            ]
    except Exception as exc:
        base["read_error"] = f"{type(exc).__name__}: {exc}"
    return base


def _build_backend_log_snapshot(
    *,
    paths: list[Path] | None,
    days: int,
    tail_lines: int,
) -> dict[str, Any]:
    candidates = paths if paths is not None else _default_backend_log_paths(days=days)
    line_limit = max(int(tail_lines or 1000), 1)
    files: list[dict[str, Any]] = []
    error_samples: list[str] = []
    warning_samples: list[str] = []
    level_counter: Counter[str] = Counter()
    scanned_lines = 0

    for raw_path in candidates:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-line_limit:]
        except OSError as exc:
            files.append({"path": str(path), "read_error": f"{type(exc).__name__}: {exc}", "line_count": 0})
            continue
        file_counter: Counter[str] = Counter()
        for line in lines:
            scanned_lines += 1
            match = _LOG_LEVEL_PATTERN.search(line)
            level = ""
            if match:
                level = str(match.group(1) or match.group(2) or "").upper()
            elif "Traceback" in line or "Exception" in line:
                level = "ERROR"
            if not level:
                continue
            if level == "WARN":
                level = "WARNING"
            level_counter[level] += 1
            file_counter[level] += 1
            sample = _redact_excerpt(line, limit=320)
            if level in {"ERROR", "CRITICAL"} and len(error_samples) < 12:
                error_samples.append(sample)
            if level == "WARNING" and len(warning_samples) < 12:
                warning_samples.append(sample)
        files.append(
            {
                "path": str(path),
                "line_count": len(lines),
                "levels": dict(sorted(file_counter.items(), key=lambda item: item[0])),
                "mtime": _timestamp_iso(path.stat().st_mtime),
            }
        )

    return {
        "window_days": max(int(days or 1), 1),
        "tail_lines_per_file": line_limit,
        "files": files,
        "scanned_lines": scanned_lines,
        "error_count": int(level_counter.get("ERROR", 0) + level_counter.get("CRITICAL", 0)),
        "warning_count": int(level_counter.get("WARNING", 0)),
        "level_distribution": dict(sorted(level_counter.items(), key=lambda item: item[0])),
        "error_samples": error_samples,
        "warning_samples": warning_samples,
    }


def _build_trace_linkage_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    trace_ids = [
        str(item.get("trace_id") or "").strip()
        for item in events
        if str(item.get("trace_id") or "").strip()
    ]
    unique_trace_ids = sorted(set(trace_ids))
    return {
        "trace_id_count": len(trace_ids),
        "unique_trace_id_count": len(unique_trace_ids),
        "sample_trace_ids": unique_trace_ids[:20],
        "langfuse_enabled": str(os.getenv("LANGFUSE_ENABLED", "") or "").strip().lower()
        in {"1", "true", "yes", "on"},
        "langfuse_host": str(os.getenv("LANGFUSE_BASE_URL", "") or os.getenv("LANGFUSE_HOST", "") or "").strip(),
    }


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


def _source_entry(
    name: str,
    *,
    has_data: bool,
    source_id: str | None = None,
    recorded_at: int | float | None = None,
    sample_count: int | None = None,
    confidence: str | None = None,
    reason: str = "",
    now: int | None = None,
) -> dict[str, Any]:
    current = int(now if now is not None else time.time())
    normalized_recorded_at = int(recorded_at) if isinstance(recorded_at, (int, float)) else None
    age_seconds = max(current - normalized_recorded_at, 0) if normalized_recorded_at is not None else None
    if not has_data:
        freshness = "missing"
    elif age_seconds is None:
        freshness = "unknown"
    elif age_seconds > 24 * 60 * 60:
        freshness = "stale"
    else:
        freshness = "fresh"

    entry: dict[str, Any] = {
        "name": name,
        "has_data": bool(has_data),
        "source_id": source_id or "",
        "recorded_at": normalized_recorded_at,
        "age_seconds": age_seconds,
        "freshness": freshness,
        "sample_count": max(int(sample_count or 0), 0),
        "confidence": confidence or ("high" if has_data else "low"),
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
    conversation_db_path: Path | None = None,
    conversation_limit: int = 100,
    backend_log_paths: list[Path] | None = None,
    backend_log_tail_lines: int = 1000,
) -> dict[str, Any]:
    control_store = store or get_control_plane_store()
    turn_log = event_log or get_turn_event_log()

    om_record = _safe_latest_run(control_store, "om_runs")
    arr_record = _safe_latest_run(control_store, "arr_runs")
    aae_record = _safe_latest_run(control_store, "aae_composite_runs")
    benchmark_record = _safe_latest_run(control_store, "benchmark_runs")
    daily_trend_record = _safe_latest_run(control_store, "daily_trends")
    om_payload = _payload_from_record(om_record)
    arr_payload = _payload_from_record(arr_record)
    aae_payload = _payload_from_record(aae_record)
    benchmark_payload = _payload_from_record(benchmark_record)
    daily_trend_payload = _payload_from_record(daily_trend_record)
    turn_events = turn_log.load_events_range(days=event_days)
    turn_log_stats = turn_log.stats()
    turn_summary = _summarize_turn_events(turn_events)
    recent_conversations = _build_recent_conversations_snapshot(
        db_path=conversation_db_path,
        days=event_days,
        limit=conversation_limit,
    )
    backend_logs = _build_backend_log_snapshot(
        paths=backend_log_paths,
        days=event_days,
        tail_lines=backend_log_tail_lines,
    )
    trace_linkage = _build_trace_linkage_snapshot(turn_events)
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

    now = int(time.time())
    data_sources = {
        "turn_event_log": _source_entry(
            "turn_event_log",
            has_data=turn_summary["event_count"] > 0,
            source_id=turn_log_stats.get("file_path"),
            sample_count=turn_summary["event_count"],
            confidence="high" if turn_summary["event_count"] > 0 else "low",
            reason="no turn events in window",
            now=now,
        ),
        "om_snapshot": _source_entry(
            "om_snapshot",
            has_data=bool(om_payload),
            source_id=(om_payload or {}).get("run_id"),
            recorded_at=(om_record or {}).get("recorded_at"),
            sample_count=1 if om_payload else 0,
            reason="missing OM snapshot",
            now=now,
        ),
        "quality_run": _source_entry(
            "quality_run",
            has_data=has_quality_run,
            source_id=(arr_payload or {}).get("run_id")
            or ((benchmark_payload or {}).get("run_manifest") or {}).get("run_id")
            or (benchmark_payload or {}).get("run_id"),
            recorded_at=(arr_record or benchmark_record or {}).get("recorded_at"),
            sample_count=1 if has_quality_run else 0,
            reason="missing ARR or benchmark run",
            now=now,
        ),
        "aae_composite": _source_entry(
            "aae_composite",
            has_data=bool(aae_payload),
            source_id=(aae_payload or {}).get("run_id"),
            recorded_at=(aae_record or {}).get("recorded_at"),
            sample_count=1 if aae_payload else 0,
            reason="missing AAE composite",
            now=now,
        ),
        "surface_ack": _source_entry(
            "surface_ack",
            has_data=has_surface_coverage,
            source_id="surface_event_store",
            sample_count=len(surface_coverage or []),
            confidence="medium" if has_surface_coverage else "low",
            reason="missing surface ack coverage",
            now=now,
        ),
        "recent_conversations": _source_entry(
            "recent_conversations",
            has_data=int(recent_conversations.get("session_count") or 0) > 0,
            source_id=str(recent_conversations.get("db_path") or ""),
            sample_count=int(recent_conversations.get("session_count") or 0),
            confidence="high"
            if int(recent_conversations.get("session_count") or 0) > 0
            and not recent_conversations.get("read_error")
            else "low",
            reason=str(recent_conversations.get("read_error") or "no recent conversations in window"),
            now=now,
        ),
        "backend_logs": _source_entry(
            "backend_logs",
            has_data=int(backend_logs.get("scanned_lines") or 0) > 0,
            source_id=",".join(str(item.get("path") or "") for item in backend_logs.get("files") or []),
            sample_count=int(backend_logs.get("scanned_lines") or 0),
            confidence="medium" if int(backend_logs.get("scanned_lines") or 0) > 0 else "low",
            reason="no backend log files found",
            now=now,
        ),
        "langfuse_trace_linkage": _source_entry(
            "langfuse_trace_linkage",
            has_data=int(trace_linkage.get("trace_id_count") or 0) > 0,
            source_id=str(trace_linkage.get("langfuse_host") or ""),
            sample_count=int(trace_linkage.get("trace_id_count") or 0),
            confidence="medium" if int(trace_linkage.get("trace_id_count") or 0) > 0 else "low",
            reason="no trace_id values in turn event window",
            now=now,
        ),
        "daily_trend": _source_entry(
            "daily_trend",
            has_data=bool(daily_trend_payload),
            source_id=((daily_trend_payload or {}).get("run_manifest") or {}).get("run_id")
            or (daily_trend_payload or {}).get("run_id"),
            recorded_at=(daily_trend_record or {}).get("recorded_at"),
            sample_count=1 if daily_trend_payload else 0,
            reason="missing daily trend",
            now=now,
        ),
        "live_metrics": _source_entry(
            "live_metrics",
            has_data=has_metrics,
            source_id="provided_metrics_snapshot" if has_metrics else "",
            sample_count=1 if has_metrics else 0,
            confidence="medium" if has_metrics else "low",
            reason="not provided to snapshot builder",
            now=now,
        ),
    }
    layers = list(data_sources.values())
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
    if recent_conversations.get("read_error"):
        blind_spots.append(
            {
                "type": "recent_conversation_evidence_read_error",
                "severity": "medium",
                "evidence": {"read_error": recent_conversations.get("read_error")},
            }
        )
    elif int(recent_conversations.get("session_count") or 0) <= 0:
        blind_spots.append({"type": "missing_recent_conversation_evidence", "severity": "medium"})
    if int(backend_logs.get("scanned_lines") or 0) <= 0:
        blind_spots.append({"type": "missing_backend_log_evidence", "severity": "medium"})
    if int(trace_linkage.get("trace_id_count") or 0) <= 0:
        blind_spots.append({"type": "missing_langfuse_trace_linkage", "severity": "medium"})

    run_id = f"observer-snapshot-{int(time.time())}"
    return {
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "window": {"event_days": max(int(event_days or 1), 1)},
        "data_coverage": _build_data_coverage(layers),
        "data_sources": data_sources,
        "blind_spots": blind_spots,
        "turn_events": turn_summary,
        "turn_event_log": turn_log_stats,
        "recent_conversations": recent_conversations,
        "backend_logs": backend_logs,
        "langfuse_trace_linkage": trace_linkage,
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
            "recent_conversations": recent_conversations,
            "backend_logs": backend_logs,
            "langfuse_trace_linkage": trace_linkage,
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
        f"- recent_conversations: `{(payload.get('recent_conversations') or {}).get('session_count')}` sessions",
        f"- backend_log_errors: `{(payload.get('backend_logs') or {}).get('error_count')}`",
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
