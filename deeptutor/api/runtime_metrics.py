from __future__ import annotations

import threading
import time
from collections import Counter
from collections import defaultdict
from collections import deque
from typing import Any


class APIRuntimeMetrics:
    """Lightweight in-process HTTP metrics for ops visibility."""

    def __init__(self, *, max_recent_errors: int = 50) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._requests_total = 0
        self._errors_total = 0
        self._status_counts: Counter[str] = Counter()
        self._route_counts: Counter[str] = Counter()
        self._route_error_counts: Counter[str] = Counter()
        self._route_latency_totals_ms: defaultdict[str, float] = defaultdict(float)
        self._route_latency_counts: Counter[str] = Counter()
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=max_recent_errors)

    def record_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        normalized_method = str(method or "GET").upper()
        normalized_route = str(route or "/")
        route_key = f"{normalized_method} {normalized_route}"
        status_key = str(int(status_code))
        with self._lock:
            self._requests_total += 1
            self._status_counts[status_key] += 1
            self._route_counts[route_key] += 1
            self._route_latency_totals_ms[route_key] += float(duration_ms)
            self._route_latency_counts[route_key] += 1
            if int(status_code) >= 500:
                self._errors_total += 1
                self._route_error_counts[route_key] += 1
                self._recent_errors.append(
                    {
                        "method": normalized_method,
                        "route": normalized_route,
                        "status_code": int(status_code),
                        "duration_ms": round(float(duration_ms), 2),
                        "timestamp": time.time(),
                    }
                )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = []
            for route_key, requests in sorted(
                self._route_counts.items(),
                key=lambda item: (-item[1], item[0]),
            ):
                latency_count = int(self._route_latency_counts.get(route_key) or 0)
                latency_total_ms = float(self._route_latency_totals_ms.get(route_key) or 0.0)
                avg_latency_ms = latency_total_ms / latency_count if latency_count else 0.0
                routes.append(
                    {
                        "route": route_key,
                        "requests": int(requests),
                        "errors": int(self._route_error_counts.get(route_key) or 0),
                        "avg_latency_ms": round(avg_latency_ms, 2),
                    }
                )

            return {
                "started_at": self._started_at,
                "uptime_seconds": round(max(time.time() - self._started_at, 0.0), 3),
                "requests_total": int(self._requests_total),
                "errors_total": int(self._errors_total),
                "status_counts": {
                    key: int(value) for key, value in sorted(self._status_counts.items(), key=lambda item: item[0])
                },
                "routes": routes,
                "recent_errors": list(self._recent_errors),
            }


class TurnRuntimeMetrics:
    """In-process websocket and turn runtime metrics for OM baseline."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ws_active_connections = 0
        self._ws_opened_total = 0
        self._ws_closed_total = 0
        self._turns_started_total = 0
        self._turns_completed_total = 0
        self._turns_failed_total = 0
        self._turns_cancelled_total = 0
        self._turns_in_flight = 0
        self._turn_latency_total_ms = 0.0
        self._turn_latency_count = 0

    def record_ws_open(self) -> None:
        with self._lock:
            self._ws_active_connections += 1
            self._ws_opened_total += 1

    def record_ws_close(self) -> None:
        with self._lock:
            self._ws_closed_total += 1
            self._ws_active_connections = max(0, self._ws_active_connections - 1)

    def record_turn_started(self) -> None:
        with self._lock:
            self._turns_started_total += 1
            self._turns_in_flight += 1

    def record_turn_finished(self, *, status: str, duration_ms: float) -> None:
        normalized_status = str(status or "").strip().lower() or "completed"
        with self._lock:
            self._turns_in_flight = max(0, self._turns_in_flight - 1)
            self._turn_latency_total_ms += max(float(duration_ms), 0.0)
            self._turn_latency_count += 1
            if normalized_status == "completed":
                self._turns_completed_total += 1
            elif normalized_status == "cancelled":
                self._turns_cancelled_total += 1
            else:
                self._turns_failed_total += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_turn_latency_ms = (
                self._turn_latency_total_ms / self._turn_latency_count if self._turn_latency_count else 0.0
            )
            return {
                "ws_active_connections": int(self._ws_active_connections),
                "ws_opened_total": int(self._ws_opened_total),
                "ws_closed_total": int(self._ws_closed_total),
                "turns_started_total": int(self._turns_started_total),
                "turns_completed_total": int(self._turns_completed_total),
                "turns_failed_total": int(self._turns_failed_total),
                "turns_cancelled_total": int(self._turns_cancelled_total),
                "turns_in_flight": int(self._turns_in_flight),
                "turn_avg_latency_ms": round(avg_turn_latency_ms, 2),
            }


_turn_runtime_metrics = TurnRuntimeMetrics()


def get_turn_runtime_metrics() -> TurnRuntimeMetrics:
    return _turn_runtime_metrics


def reset_turn_runtime_metrics() -> None:
    global _turn_runtime_metrics
    _turn_runtime_metrics = TurnRuntimeMetrics()


def _escape_label(value: object) -> str:
    return str(value).replace("\\", r"\\").replace("\n", r"\n").replace('"', r"\"")


def render_prometheus_metrics(
    *,
    http_snapshot: dict[str, Any],
    turn_snapshot: dict[str, Any],
    surface_snapshot: dict[str, Any],
    readiness_snapshot: dict[str, Any],
    provider_error_rates: dict[str, dict[str, float | int | bool]],
    circuit_breakers: dict[str, dict[str, float | int | str]],
    release_snapshot: dict[str, str],
) -> str:
    """Render a Prometheus-compatible text exposition."""
    lines: list[str] = []

    def emit(metric: str, value: object, labels: dict[str, object] | None = None) -> None:
        if labels:
            label_text = ",".join(
                f'{key}="{_escape_label(raw_value)}"' for key, raw_value in sorted(labels.items(), key=lambda item: item[0])
            )
            lines.append(f"{metric}{{{label_text}}} {value}")
        else:
            lines.append(f"{metric} {value}")

    lines.append("# HELP deeptutor_http_uptime_seconds DeepTutor API process uptime in seconds.")
    lines.append("# TYPE deeptutor_http_uptime_seconds gauge")
    emit("deeptutor_http_uptime_seconds", http_snapshot.get("uptime_seconds", 0))

    lines.append("# HELP deeptutor_http_requests_total Total HTTP requests observed by the API process.")
    lines.append("# TYPE deeptutor_http_requests_total counter")
    emit("deeptutor_http_requests_total", http_snapshot.get("requests_total", 0))

    lines.append("# HELP deeptutor_http_errors_total Total HTTP 5xx responses observed by the API process.")
    lines.append("# TYPE deeptutor_http_errors_total counter")
    emit("deeptutor_http_errors_total", http_snapshot.get("errors_total", 0))

    lines.append("# HELP deeptutor_http_status_total HTTP responses by status code.")
    lines.append("# TYPE deeptutor_http_status_total counter")
    for status_code, count in sorted((http_snapshot.get("status_counts") or {}).items(), key=lambda item: item[0]):
        emit("deeptutor_http_status_total", count, {"status_code": status_code})

    lines.append("# HELP deeptutor_http_route_requests_total HTTP requests by route.")
    lines.append("# TYPE deeptutor_http_route_requests_total counter")
    lines.append("# HELP deeptutor_http_route_errors_total HTTP 5xx responses by route.")
    lines.append("# TYPE deeptutor_http_route_errors_total counter")
    lines.append("# HELP deeptutor_http_route_avg_latency_ms Average response latency by route in milliseconds.")
    lines.append("# TYPE deeptutor_http_route_avg_latency_ms gauge")
    for route_entry in http_snapshot.get("routes") or []:
        route_labels = {"route": route_entry.get("route", "")}
        emit("deeptutor_http_route_requests_total", route_entry.get("requests", 0), route_labels)
        emit("deeptutor_http_route_errors_total", route_entry.get("errors", 0), route_labels)
        emit("deeptutor_http_route_avg_latency_ms", route_entry.get("avg_latency_ms", 0), route_labels)

    lines.append("# HELP deeptutor_ws_active_connections Current active websocket connections.")
    lines.append("# TYPE deeptutor_ws_active_connections gauge")
    emit("deeptutor_ws_active_connections", turn_snapshot.get("ws_active_connections", 0))

    lines.append("# HELP deeptutor_ws_opened_total Total websocket connections opened.")
    lines.append("# TYPE deeptutor_ws_opened_total counter")
    emit("deeptutor_ws_opened_total", turn_snapshot.get("ws_opened_total", 0))

    lines.append("# HELP deeptutor_ws_closed_total Total websocket connections closed.")
    lines.append("# TYPE deeptutor_ws_closed_total counter")
    emit("deeptutor_ws_closed_total", turn_snapshot.get("ws_closed_total", 0))

    lines.append("# HELP deeptutor_turns_started_total Total turns started by the runtime.")
    lines.append("# TYPE deeptutor_turns_started_total counter")
    emit("deeptutor_turns_started_total", turn_snapshot.get("turns_started_total", 0))

    lines.append("# HELP deeptutor_turns_completed_total Total turns completed by the runtime.")
    lines.append("# TYPE deeptutor_turns_completed_total counter")
    emit("deeptutor_turns_completed_total", turn_snapshot.get("turns_completed_total", 0))

    lines.append("# HELP deeptutor_turns_failed_total Total turns failed by the runtime.")
    lines.append("# TYPE deeptutor_turns_failed_total counter")
    emit("deeptutor_turns_failed_total", turn_snapshot.get("turns_failed_total", 0))

    lines.append("# HELP deeptutor_turns_cancelled_total Total turns cancelled by the runtime.")
    lines.append("# TYPE deeptutor_turns_cancelled_total counter")
    emit("deeptutor_turns_cancelled_total", turn_snapshot.get("turns_cancelled_total", 0))

    lines.append("# HELP deeptutor_turns_in_flight Current number of in-flight turns.")
    lines.append("# TYPE deeptutor_turns_in_flight gauge")
    emit("deeptutor_turns_in_flight", turn_snapshot.get("turns_in_flight", 0))

    lines.append("# HELP deeptutor_turn_avg_latency_ms Average turn runtime latency in milliseconds.")
    lines.append("# TYPE deeptutor_turn_avg_latency_ms gauge")
    emit("deeptutor_turn_avg_latency_ms", turn_snapshot.get("turn_avg_latency_ms", 0))

    lines.append("# HELP deeptutor_surface_event_total Total surface telemetry events by surface, event, and ingest status.")
    lines.append("# TYPE deeptutor_surface_event_total counter")
    for event_entry in surface_snapshot.get("event_counts") or []:
        emit(
            "deeptutor_surface_event_total",
            event_entry.get("count", 0),
            {
                "surface": event_entry.get("surface", ""),
                "event_name": event_entry.get("event_name", ""),
                "status": event_entry.get("status", ""),
            },
        )

    lines.append("# HELP deeptutor_surface_first_render_coverage_ratio Ratio of first render ACKs over start_turn_sent by surface.")
    lines.append("# TYPE deeptutor_surface_first_render_coverage_ratio gauge")
    lines.append("# HELP deeptutor_surface_done_render_coverage_ratio Ratio of done_rendered ACKs over start_turn_sent by surface.")
    lines.append("# TYPE deeptutor_surface_done_render_coverage_ratio gauge")
    for coverage_entry in surface_snapshot.get("coverage") or []:
        surface = coverage_entry.get("surface", "")
        first_ratio = coverage_entry.get("first_render_coverage_ratio")
        done_ratio = coverage_entry.get("done_render_coverage_ratio")
        if first_ratio is not None:
            emit(
                "deeptutor_surface_first_render_coverage_ratio",
                first_ratio,
                {"surface": surface},
            )
        if done_ratio is not None:
            emit(
                "deeptutor_surface_done_render_coverage_ratio",
                done_ratio,
                {"surface": surface},
            )

    lines.append("# HELP deeptutor_ready Whether DeepTutor readiness checks currently pass.")
    lines.append("# TYPE deeptutor_ready gauge")
    emit("deeptutor_ready", 1 if readiness_snapshot.get("ready") else 0)

    lines.append("# HELP deeptutor_readiness_check Status of individual readiness checks.")
    lines.append("# TYPE deeptutor_readiness_check gauge")
    for check_name, ready in sorted((readiness_snapshot.get("checks") or {}).items(), key=lambda item: item[0]):
        emit("deeptutor_readiness_check", 1 if ready else 0, {"check": check_name})

    lines.append("# HELP deeptutor_provider_total_calls Total provider calls in the sliding error-rate window.")
    lines.append("# TYPE deeptutor_provider_total_calls gauge")
    lines.append("# HELP deeptutor_provider_error_calls Provider errors in the sliding error-rate window.")
    lines.append("# TYPE deeptutor_provider_error_calls gauge")
    lines.append("# HELP deeptutor_provider_error_rate Provider error rate in the sliding error-rate window.")
    lines.append("# TYPE deeptutor_provider_error_rate gauge")
    lines.append("# HELP deeptutor_provider_threshold_exceeded Whether the provider error-rate threshold is exceeded.")
    lines.append("# TYPE deeptutor_provider_threshold_exceeded gauge")
    lines.append("# HELP deeptutor_provider_alert_open Whether the provider alert latch is currently open.")
    lines.append("# TYPE deeptutor_provider_alert_open gauge")
    for provider, snapshot in sorted(provider_error_rates.items(), key=lambda item: item[0]):
        provider_labels = {"provider": provider}
        emit("deeptutor_provider_total_calls", snapshot.get("total_calls", 0), provider_labels)
        emit("deeptutor_provider_error_calls", snapshot.get("error_calls", 0), provider_labels)
        emit("deeptutor_provider_error_rate", snapshot.get("error_rate", 0), provider_labels)
        emit(
            "deeptutor_provider_threshold_exceeded",
            1 if snapshot.get("threshold_exceeded") else 0,
            provider_labels,
        )
        emit("deeptutor_provider_alert_open", 1 if snapshot.get("alert_open") else 0, provider_labels)

    lines.append("# HELP deeptutor_circuit_breaker_failure_count Provider circuit-breaker failure counts.")
    lines.append("# TYPE deeptutor_circuit_breaker_failure_count gauge")
    lines.append("# HELP deeptutor_circuit_breaker_open Whether the circuit breaker is open for a provider.")
    lines.append("# TYPE deeptutor_circuit_breaker_open gauge")
    lines.append("# HELP deeptutor_circuit_breaker_half_open Whether the circuit breaker is half-open for a provider.")
    lines.append("# TYPE deeptutor_circuit_breaker_half_open gauge")
    for provider, snapshot in sorted(circuit_breakers.items(), key=lambda item: item[0]):
        state = str(snapshot.get("state", "closed"))
        provider_labels = {"provider": provider}
        emit("deeptutor_circuit_breaker_failure_count", snapshot.get("failure_count", 0), provider_labels)
        emit("deeptutor_circuit_breaker_open", 1 if state == "open" else 0, provider_labels)
        emit("deeptutor_circuit_breaker_half_open", 1 if state == "half-open" else 0, provider_labels)

    lines.append("# HELP deeptutor_release_info Build and release lineage for the running service.")
    lines.append("# TYPE deeptutor_release_info gauge")
    emit(
        "deeptutor_release_info",
        1,
        {
            "release_id": release_snapshot.get("release_id", ""),
            "service_version": release_snapshot.get("service_version", ""),
            "git_sha": release_snapshot.get("git_sha", ""),
            "deployment_environment": release_snapshot.get("deployment_environment", ""),
            "prompt_version": release_snapshot.get("prompt_version", ""),
            "ff_snapshot_hash": release_snapshot.get("ff_snapshot_hash", ""),
        },
    )

    return "\n".join(lines) + "\n"
