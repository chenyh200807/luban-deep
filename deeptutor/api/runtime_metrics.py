from __future__ import annotations

import threading
import time
from collections import Counter
from collections import defaultdict
from collections import deque
from typing import Any


# Battle2 S3-T3: fixed histogram bucket bounds (ms) for turn-level time to first
# useful content (TTFVT). Same observe-only discipline as the W1-T6 lag sentinel.
_FUC_BUCKET_BOUNDS_MS: tuple[float, ...] = (
    500.0,
    1000.0,
    2000.0,
    4000.0,
    8000.0,
    16000.0,
    32000.0,
    64000.0,
)

# Known first-useful-content sources (discriminator label: streamed first delta
# vs. one-shot result payload). Anything else collapses into "other" so the
# label set stays bounded.
_FUC_KNOWN_SOURCES = frozenset({"content.delta", "result.response"})


# Assessment deep-explanation LLM call wall-clock (ms). This is a one-shot
# (non-streaming) paid explanation generated outside the turn pipeline, so it has
# no TTFT; the histogram captures end-to-end call duration for p50/p95 ops
# visibility. Observe-only, fail-open, label-free (single bounded series).
_ASSESSMENT_EXPLANATION_BUCKET_BOUNDS_MS: tuple[float, ...] = (
    500.0,
    1000.0,
    2000.0,
    4000.0,
    8000.0,
    16000.0,
    32000.0,
    64000.0,
)


def normalize_latency_stage_timings(value: Any) -> dict[str, float]:
    """Return stable non-negative latency stage timings in milliseconds."""
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, float] = {}
    for raw_stage, raw_ms in value.items():
        stage = str(raw_stage or "").strip()
        if not stage or len(stage) > 80:
            continue
        if not all(ch.isalnum() or ch in {"_", "-", ".", ":"} for ch in stage):
            continue
        try:
            duration_ms = float(raw_ms)
        except (TypeError, ValueError):
            continue
        if duration_ms < 0:
            continue
        normalized[stage] = round(duration_ms, 2)
    return dict(sorted(normalized.items(), key=lambda item: item[0]))


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
        self._turn_stage_latency_totals_ms: defaultdict[str, float] = defaultdict(float)
        self._turn_stage_latency_counts: Counter[str] = Counter()
        # Battle1 W4-T6: observe-only fast/deep x model-tier occupancy (A/B denominator).
        self._response_mode_counts: Counter[str] = Counter()
        # Battle2 S1-T4: observe-only summary-maintainer gate decisions keyed by
        # "decision|outcome". This is the independent read for the S1 gate hit rate
        # (skip ratio) and the changed/no_change mix; same discipline as
        # response_mode and it must ship in the same PR as the gate itself.
        self._summary_maintainer_counts: Counter[str] = Counter()
        # Battle2 S1 同病同修: observe-only public-memory rewrite gate decisions
        # keyed by "decision|outcome". Independent read for the memory-maintainer
        # (SUMMARY.md + PROFILE.md) gate hit rate; same discipline as summary_maintainer
        # and it must ship in the same PR as the gate itself.
        self._memory_maintainer_counts: Counter[str] = Counter()
        # Battle1 W1-T6: event-loop lag sentinel (真闭环). A 0.5s sampler feeds
        # record_loop_lag; any future hot-path blocking (new sync SDK, CPU-heavy work)
        # necessarily inflates these and trips the existing Prometheus alert chain,
        # without depending on enumerating pathogens. Observe-only, fail-open.
        self._loop_lag_samples_total = 0
        self._loop_lag_max_seconds = 0.0
        self._loop_lag_over_200ms_total = 0
        # Battle2 S3-T3: observe-only TTFVT histogram. One hop export of the
        # existing turn_runtime _first_useful_content_observation (the single
        # latency authority) so p50/p95 become readable in Prometheus.
        # Keyed by content_source; non-cumulative bucket counts + sum + count.
        self._fuc_histograms: dict[str, dict[str, Any]] = {}
        # Observe-only assessment deep-explanation LLM call duration histogram.
        # Single label-free series (non-cumulative bucket counts + sum + count),
        # lazily initialized so an idle process exports nothing.
        self._assessment_explanation_hist: dict[str, Any] = {}

    def record_first_useful_content(self, *, elapsed_ms: float, content_source: str = "") -> None:
        """Observe-only: record one turn-level time-to-first-useful-content sample
        (ms). Fail-open, never raises; invalid input is dropped silently."""
        try:
            value = float(elapsed_ms)
        except (TypeError, ValueError):
            return
        if value < 0 or value != value:  # reject negatives and NaN
            return
        source = str(content_source or "").strip()
        if source not in _FUC_KNOWN_SOURCES:
            source = "other"
        with self._lock:
            hist = self._fuc_histograms.setdefault(
                source,
                {
                    "bucket_counts": [0] * (len(_FUC_BUCKET_BOUNDS_MS) + 1),
                    "sum_ms": 0.0,
                    "count": 0,
                },
            )
            hist["count"] += 1
            hist["sum_ms"] += value
            for index, bound in enumerate(_FUC_BUCKET_BOUNDS_MS):
                if value <= bound:
                    hist["bucket_counts"][index] += 1
                    break
            else:
                hist["bucket_counts"][-1] += 1

    def record_assessment_explanation(self, *, elapsed_ms: float) -> None:
        """Observe-only: record one assessment deep-explanation LLM call duration
        sample (ms). Fail-open, never raises; invalid input is dropped silently."""
        try:
            value = float(elapsed_ms)
        except (TypeError, ValueError):
            return
        if value < 0 or value != value:  # reject negatives and NaN
            return
        with self._lock:
            hist = self._assessment_explanation_hist
            if not hist:
                hist["bucket_counts"] = [0] * (len(_ASSESSMENT_EXPLANATION_BUCKET_BOUNDS_MS) + 1)
                hist["sum_ms"] = 0.0
                hist["count"] = 0
            hist["count"] += 1
            hist["sum_ms"] += value
            for index, bound in enumerate(_ASSESSMENT_EXPLANATION_BUCKET_BOUNDS_MS):
                if value <= bound:
                    hist["bucket_counts"][index] += 1
                    break
            else:
                hist["bucket_counts"][-1] += 1

    def record_loop_lag(self, lag_seconds: float) -> None:
        """Observe-only: record one event-loop lag sample (expected vs. actual sleep
        skew, seconds). Monotonic max + over-200ms counter. Never raises (fail-open)."""
        try:
            lag = float(lag_seconds)
        except (TypeError, ValueError):
            return
        if lag < 0.0:
            lag = 0.0
        with self._lock:
            self._loop_lag_samples_total += 1
            if lag > self._loop_lag_max_seconds:
                self._loop_lag_max_seconds = lag
            if lag > 0.2:
                self._loop_lag_over_200ms_total += 1

    def record_response_mode(self, selected_mode: str, model_tier: str) -> None:
        """Observe-only: count one turn by (selected_mode, model_tier). fail-open."""
        mode = str(selected_mode or "").strip().lower() or "unknown"
        tier = str(model_tier or "").strip().lower() or "primary"
        with self._lock:
            self._response_mode_counts[f"{mode}|{tier}"] += 1

    def record_summary_maintainer(self, *, decision: str, outcome: str = "") -> None:
        """Observe-only: count one summary-maintainer gate (decision, outcome).
        fail-open, never raises on stringifiable input."""
        decision_key = str(decision or "").strip().lower() or "unknown"
        outcome_key = str(outcome or "").strip().lower() or "-"
        with self._lock:
            self._summary_maintainer_counts[f"{decision_key}|{outcome_key}"] += 1

    def record_memory_maintainer(self, *, decision: str, outcome: str = "") -> None:
        """Observe-only: count one public-memory rewrite gate (decision, outcome).
        fail-open, never raises on stringifiable input."""
        decision_key = str(decision or "").strip().lower() or "unknown"
        outcome_key = str(outcome or "").strip().lower() or "-"
        with self._lock:
            self._memory_maintainer_counts[f"{decision_key}|{outcome_key}"] += 1

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

    def record_turn_finished(
        self,
        *,
        status: str,
        duration_ms: float,
        stage_timings_ms: dict[str, Any] | None = None,
    ) -> None:
        normalized_status = str(status or "").strip().lower() or "completed"
        normalized_stage_timings = normalize_latency_stage_timings(stage_timings_ms)
        with self._lock:
            self._turns_in_flight = max(0, self._turns_in_flight - 1)
            self._turn_latency_total_ms += max(float(duration_ms), 0.0)
            self._turn_latency_count += 1
            for stage, stage_duration_ms in normalized_stage_timings.items():
                self._turn_stage_latency_totals_ms[stage] += stage_duration_ms
                self._turn_stage_latency_counts[stage] += 1
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
            stage_avg_latency = [
                {
                    "stage": stage,
                    "avg_latency_ms": round(
                        float(self._turn_stage_latency_totals_ms.get(stage) or 0.0) / count,
                        2,
                    ),
                    "count": int(count),
                }
                for stage, count in sorted(self._turn_stage_latency_counts.items(), key=lambda item: item[0])
                if count
            ]
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
                "turn_stage_avg_latency_ms": stage_avg_latency,
                "response_mode_counts": [
                    {
                        "mode": key.split("|", 1)[0],
                        "model_tier": key.split("|", 1)[1],
                        "count": int(value),
                    }
                    for key, value in sorted(self._response_mode_counts.items())
                ],
                "summary_maintainer_counts": [
                    {
                        "decision": key.split("|", 1)[0],
                        "outcome": key.split("|", 1)[1],
                        "count": int(value),
                    }
                    for key, value in sorted(self._summary_maintainer_counts.items())
                ],
                "memory_maintainer_counts": [
                    {
                        "decision": key.split("|", 1)[0],
                        "outcome": key.split("|", 1)[1],
                        "count": int(value),
                    }
                    for key, value in sorted(self._memory_maintainer_counts.items())
                ],
                "loop_lag_max_seconds": round(float(self._loop_lag_max_seconds), 6),
                "loop_lag_over_200ms_total": int(self._loop_lag_over_200ms_total),
                "loop_lag_samples_total": int(self._loop_lag_samples_total),
                "first_useful_content_ms": [
                    {
                        "content_source": source,
                        "bucket_bounds_ms": list(_FUC_BUCKET_BOUNDS_MS),
                        "bucket_counts": [int(c) for c in hist["bucket_counts"]],
                        "sum_ms": round(float(hist["sum_ms"]), 2),
                        "count": int(hist["count"]),
                    }
                    for source, hist in sorted(self._fuc_histograms.items())
                ],
                "assessment_explanation_ms": (
                    {
                        "bucket_bounds_ms": list(_ASSESSMENT_EXPLANATION_BUCKET_BOUNDS_MS),
                        "bucket_counts": [int(c) for c in self._assessment_explanation_hist["bucket_counts"]],
                        "sum_ms": round(float(self._assessment_explanation_hist["sum_ms"]), 2),
                        "count": int(self._assessment_explanation_hist["count"]),
                    }
                    if self._assessment_explanation_hist
                    else None
                ),
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

    lines.append("# HELP deeptutor_turn_stage_avg_latency_ms Average turn runtime latency by internal stage in milliseconds.")
    lines.append("# TYPE deeptutor_turn_stage_avg_latency_ms gauge")
    lines.append("# HELP deeptutor_turn_stage_count Number of turns contributing to each internal stage latency.")
    lines.append("# TYPE deeptutor_turn_stage_count gauge")
    for stage_entry in turn_snapshot.get("turn_stage_avg_latency_ms") or []:
        stage = str(stage_entry.get("stage") or "").strip()
        if not stage:
            continue
        labels = {"stage": stage}
        emit("deeptutor_turn_stage_avg_latency_ms", stage_entry.get("avg_latency_ms", 0), labels)
        emit("deeptutor_turn_stage_count", stage_entry.get("count", 0), labels)

    lines.append("# HELP deeptutor_turn_response_mode_total Turns by selected response mode and model tier.")
    lines.append("# TYPE deeptutor_turn_response_mode_total counter")
    for mode_entry in turn_snapshot.get("response_mode_counts") or []:
        emit(
            "deeptutor_turn_response_mode_total",
            mode_entry.get("count", 0),
            {
                "mode": mode_entry.get("mode", ""),
                "model_tier": mode_entry.get("model_tier", ""),
            },
        )

    lines.append("# HELP deeptutor_summary_maintainer_total Summary-maintainer gate decisions by decision and outcome.")
    lines.append("# TYPE deeptutor_summary_maintainer_total counter")
    for gate_entry in turn_snapshot.get("summary_maintainer_counts") or []:
        emit(
            "deeptutor_summary_maintainer_total",
            gate_entry.get("count", 0),
            {
                "decision": gate_entry.get("decision", ""),
                "outcome": gate_entry.get("outcome", ""),
            },
        )

    lines.append("# HELP deeptutor_memory_maintainer_total Public-memory rewrite gate decisions by decision and outcome.")
    lines.append("# TYPE deeptutor_memory_maintainer_total counter")
    for gate_entry in turn_snapshot.get("memory_maintainer_counts") or []:
        emit(
            "deeptutor_memory_maintainer_total",
            gate_entry.get("count", 0),
            {
                "decision": gate_entry.get("decision", ""),
                "outcome": gate_entry.get("outcome", ""),
            },
        )

    lines.append("# HELP deeptutor_turn_loop_lag_max_seconds Max observed event-loop lag (expected vs. actual sleep skew) since process start.")
    lines.append("# TYPE deeptutor_turn_loop_lag_max_seconds gauge")
    emit("deeptutor_turn_loop_lag_max_seconds", turn_snapshot.get("loop_lag_max_seconds", 0))

    lines.append("# HELP deeptutor_turn_loop_lag_over_200ms_total Event-loop lag samples exceeding 200ms (hot-path blocking signal).")
    lines.append("# TYPE deeptutor_turn_loop_lag_over_200ms_total counter")
    emit("deeptutor_turn_loop_lag_over_200ms_total", turn_snapshot.get("loop_lag_over_200ms_total", 0))

    lines.append("# HELP deeptutor_turn_loop_lag_samples_total Total event-loop lag samples taken by the sentinel.")
    lines.append("# TYPE deeptutor_turn_loop_lag_samples_total counter")
    emit("deeptutor_turn_loop_lag_samples_total", turn_snapshot.get("loop_lag_samples_total", 0))

    lines.append(
        "# HELP deeptutor_turn_first_useful_content_ms Server turn start to first useful content (TTFVT) in milliseconds."
    )
    lines.append("# TYPE deeptutor_turn_first_useful_content_ms histogram")
    for fuc_entry in turn_snapshot.get("first_useful_content_ms") or []:
        source_label = {"content_source": fuc_entry.get("content_source", "")}
        bounds = [float(b) for b in fuc_entry.get("bucket_bounds_ms") or []]
        counts = [int(c) for c in fuc_entry.get("bucket_counts") or []]
        if len(counts) != len(bounds) + 1:
            continue
        cumulative = 0
        for bound, bucket_count in zip(bounds, counts[:-1]):
            cumulative += bucket_count
            le = str(int(bound)) if float(bound).is_integer() else str(bound)
            emit(
                "deeptutor_turn_first_useful_content_ms_bucket",
                cumulative,
                {**source_label, "le": le},
            )
        cumulative += counts[-1]
        emit(
            "deeptutor_turn_first_useful_content_ms_bucket",
            cumulative,
            {**source_label, "le": "+Inf"},
        )
        emit("deeptutor_turn_first_useful_content_ms_sum", fuc_entry.get("sum_ms", 0), source_label)
        emit("deeptutor_turn_first_useful_content_ms_count", fuc_entry.get("count", 0), source_label)

    lines.append(
        "# HELP deeptutor_assessment_deep_explanation_ms Assessment deep-explanation LLM call duration (one-shot, non-streaming) in milliseconds."
    )
    lines.append("# TYPE deeptutor_assessment_deep_explanation_ms histogram")
    explain_entry = turn_snapshot.get("assessment_explanation_ms")
    if isinstance(explain_entry, dict):
        bounds = [float(b) for b in explain_entry.get("bucket_bounds_ms") or []]
        counts = [int(c) for c in explain_entry.get("bucket_counts") or []]
        if bounds and len(counts) == len(bounds) + 1:
            cumulative = 0
            for bound, bucket_count in zip(bounds, counts[:-1]):
                cumulative += bucket_count
                le = str(int(bound)) if float(bound).is_integer() else str(bound)
                emit("deeptutor_assessment_deep_explanation_ms_bucket", cumulative, {"le": le})
            cumulative += counts[-1]
            emit("deeptutor_assessment_deep_explanation_ms_bucket", cumulative, {"le": "+Inf"})
            emit("deeptutor_assessment_deep_explanation_ms_sum", explain_entry.get("sum_ms", 0))
            emit("deeptutor_assessment_deep_explanation_ms_count", explain_entry.get("count", 0))

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
            "git_dirty": release_snapshot.get("git_dirty", ""),
            "deploy_manifest_hash": release_snapshot.get("deploy_manifest_hash", ""),
        },
    )

    return "\n".join(lines) + "\n"
