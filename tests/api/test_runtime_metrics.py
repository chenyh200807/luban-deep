from __future__ import annotations

import asyncio
import time

from deeptutor.api.runtime_metrics import TurnRuntimeMetrics, render_prometheus_metrics
from deeptutor.services.observability.multiworker_metrics import merge_metric_snapshots


def test_turn_runtime_metrics_snapshot_tracks_ws_and_turn_lifecycle() -> None:
    metrics = TurnRuntimeMetrics()

    metrics.record_ws_open()
    metrics.record_turn_started()
    metrics.record_turn_finished(
        status="completed",
        duration_ms=150.5,
        stage_timings_ms={
            "context_build": 40.0,
            "capability_stream": 100.5,
        },
    )
    metrics.record_ws_close()

    snapshot = metrics.snapshot()
    assert snapshot["ws_active_connections"] == 0
    assert snapshot["ws_opened_total"] == 1
    assert snapshot["ws_closed_total"] == 1
    assert snapshot["turns_started_total"] == 1
    assert snapshot["turns_completed_total"] == 1
    assert snapshot["turns_failed_total"] == 0
    assert snapshot["turns_cancelled_total"] == 0
    assert snapshot["turns_in_flight"] == 0
    assert snapshot["turn_avg_latency_ms"] == 150.5
    assert snapshot["turn_stage_avg_latency_ms"] == [
        {"stage": "capability_stream", "avg_latency_ms": 100.5, "count": 1},
        {"stage": "context_build", "avg_latency_ms": 40.0, "count": 1},
    ]


def test_render_prometheus_metrics_includes_release_and_turn_runtime_metrics() -> None:
    body = render_prometheus_metrics(
        http_snapshot={
            "uptime_seconds": 12.3,
            "requests_total": 4,
            "errors_total": 1,
            "status_counts": {"200": 3, "500": 1},
            "routes": [
                {
                    "route": "GET /metrics",
                    "requests": 2,
                    "errors": 0,
                    "avg_latency_ms": 10.5,
                }
            ],
        },
        turn_snapshot={
            "ws_active_connections": 1,
            "ws_opened_total": 2,
            "ws_closed_total": 1,
            "turns_started_total": 3,
            "turns_completed_total": 2,
            "turns_failed_total": 1,
            "turns_cancelled_total": 0,
            "turns_in_flight": 0,
            "turn_avg_latency_ms": 222.0,
            "turn_stage_avg_latency_ms": [
                {"stage": "context_build", "avg_latency_ms": 40.0, "count": 2},
                {"stage": "capability_stream", "avg_latency_ms": 120.0, "count": 2},
            ],
        },
        surface_snapshot={
            "event_counts": [
                {
                    "surface": "web",
                    "event_name": "start_turn_sent",
                    "status": "accepted",
                    "count": 5,
                },
                {
                    "surface": "web",
                    "event_name": "first_visible_content_rendered",
                    "status": "accepted",
                    "count": 4,
                },
            ],
            "coverage": [
                {
                    "surface": "web",
                    "first_render_coverage_ratio": 0.8,
                    "done_render_coverage_ratio": 0.6,
                }
            ],
        },
        readiness_snapshot={"ready": True, "checks": {"llm_client_ready": True}},
        provider_error_rates={
            "dashscope": {
                "total_calls": 10,
                "error_calls": 2,
                "error_rate": 0.2,
                "threshold_exceeded": True,
                "alert_open": True,
            }
        },
        circuit_breakers={"dashscope": {"failure_count": 3, "state": "open"}},
        release_snapshot={
            "release_id": "1.0.0+abc123+prod",
            "service_version": "1.0.0",
            "git_sha": "abc123",
            "deployment_environment": "prod",
            "prompt_version": "prompt-v9",
            "ff_snapshot_hash": "ffaa00112233",
            "git_dirty": "false",
            "deploy_manifest_hash": "manifest123",
        },
    )

    assert "deeptutor_ws_opened_total 2" in body
    assert "deeptutor_turns_started_total 3" in body
    assert "deeptutor_turns_failed_total 1" in body
    assert "deeptutor_turn_avg_latency_ms 222.0" in body
    assert 'deeptutor_turn_stage_avg_latency_ms{stage="context_build"} 40.0' in body
    assert 'deeptutor_turn_stage_count{stage="capability_stream"} 2' in body
    assert (
        'deeptutor_surface_event_total{event_name="start_turn_sent",status="accepted",surface="web"} 5'
        in body
    )
    assert 'deeptutor_surface_first_render_coverage_ratio{surface="web"} 0.8' in body
    assert 'deeptutor_surface_done_render_coverage_ratio{surface="web"} 0.6' in body
    assert (
        'deeptutor_release_info{deploy_manifest_hash="manifest123",deployment_environment="prod",ff_snapshot_hash="ffaa00112233",git_dirty="false",git_sha="abc123",prompt_version="prompt-v9",release_id="1.0.0+abc123+prod",service_version="1.0.0"} 1'
        in body
    )


def test_response_mode_counts_snapshot_and_prometheus() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_response_mode("fast", "primary")
    metrics.record_response_mode("fast", "primary")
    metrics.record_response_mode("deep", "primary")
    metrics.record_response_mode("fast", "light")

    counts = metrics.snapshot()["response_mode_counts"]
    assert {"mode": "fast", "model_tier": "primary", "count": 2} in counts
    assert {"mode": "deep", "model_tier": "primary", "count": 1} in counts
    assert {"mode": "fast", "model_tier": "light", "count": 1} in counts

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert 'deeptutor_turn_response_mode_total{mode="fast",model_tier="light"} 1' in body
    assert 'deeptutor_turn_response_mode_total{mode="fast",model_tier="primary"} 2' in body


def test_response_mode_defaults_normalize_blanks() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_response_mode("", "")
    counts = metrics.snapshot()["response_mode_counts"]
    assert {"mode": "unknown", "model_tier": "primary", "count": 1} in counts


def test_merge_metric_snapshots_sums_response_mode_counts_across_workers() -> None:
    worker_a = {
        "turn": {
            "response_mode_counts": [
                {"mode": "fast", "model_tier": "light", "count": 3},
                {"mode": "deep", "model_tier": "primary", "count": 1},
            ]
        }
    }
    worker_b = {
        "turn": {
            "response_mode_counts": [
                {"mode": "fast", "model_tier": "light", "count": 2},
            ]
        }
    }
    merged = merge_metric_snapshots([worker_a, worker_b])["turn"]["response_mode_counts"]
    assert {"mode": "fast", "model_tier": "light", "count": 5} in merged
    assert {"mode": "deep", "model_tier": "primary", "count": 1} in merged


# ----------------------------------------------------------------------------------
# Battle1 W1-T6: event-loop lag sentinel (真闭环)
# ----------------------------------------------------------------------------------
def test_record_loop_lag_aggregates_max_and_over_200ms_threshold() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_loop_lag(0.19)  # boundary: under 200ms, not counted
    metrics.record_loop_lag(0.21)  # boundary: over 200ms, counted
    metrics.record_loop_lag(0.30)  # over 200ms, new max
    metrics.record_loop_lag(-1.0)  # negative clamps to 0.0, still a sample
    metrics.record_loop_lag("not-a-number")  # fail-open: ignored entirely

    snapshot = metrics.snapshot()
    assert snapshot["loop_lag_samples_total"] == 4
    assert snapshot["loop_lag_over_200ms_total"] == 2
    assert snapshot["loop_lag_max_seconds"] == 0.3


def test_render_prometheus_metrics_includes_loop_lag() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_loop_lag(0.25)

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert "deeptutor_turn_loop_lag_max_seconds 0.25" in body
    assert "deeptutor_turn_loop_lag_over_200ms_total 1" in body
    assert "deeptutor_turn_loop_lag_samples_total 1" in body


def test_merge_metric_snapshots_aggregates_loop_lag_across_workers() -> None:
    worker_a = {"turn": {"loop_lag_max_seconds": 0.12, "loop_lag_over_200ms_total": 0, "loop_lag_samples_total": 100}}
    worker_b = {"turn": {"loop_lag_max_seconds": 0.44, "loop_lag_over_200ms_total": 3, "loop_lag_samples_total": 100}}
    merged = merge_metric_snapshots([worker_a, worker_b])["turn"]
    # Worst worker dominates the gauge; counters sum.
    assert merged["loop_lag_max_seconds"] == 0.44
    assert merged["loop_lag_over_200ms_total"] == 3
    assert merged["loop_lag_samples_total"] == 200


def test_loop_lag_sentinel_detects_blocking_sync_callback() -> None:
    """Integration: run the sentinel sampling loop on a live event loop. A blocking
    ``time.sleep(0.3)`` sync callback inflates lag past 200ms; pure idle does not.
    Mirrors deeptutor.api.main._loop_lag_sentinel (kept identical in shape)."""

    async def _drive() -> tuple[int, int]:
        metrics = TurnRuntimeMetrics()
        interval = 0.05

        async def _sentinel() -> None:
            while True:
                t0 = time.monotonic()
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
                metrics.record_loop_lag(max(0.0, time.monotonic() - t0 - interval))

        task = asyncio.create_task(_sentinel())
        # Idle for several cycles: no blocking → no over-200ms samples.
        await asyncio.sleep(0.25)
        idle_over = metrics.snapshot()["loop_lag_over_200ms_total"]

        # Block the event loop with a synchronous callback.
        time.sleep(0.3)
        await asyncio.sleep(0.1)  # let the sentinel wake and record the induced lag

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return idle_over, metrics.snapshot()["loop_lag_over_200ms_total"]

    idle_over, after_block_over = asyncio.run(_drive())
    assert idle_over == 0
    assert after_block_over >= 1
