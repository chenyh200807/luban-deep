from __future__ import annotations

from deeptutor.api.runtime_metrics import TurnRuntimeMetrics, render_prometheus_metrics


def test_turn_runtime_metrics_snapshot_tracks_ws_and_turn_lifecycle() -> None:
    metrics = TurnRuntimeMetrics()

    metrics.record_ws_open()
    metrics.record_turn_started()
    metrics.record_turn_finished(status="completed", duration_ms=150.5)
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
        },
    )

    assert "deeptutor_ws_opened_total 2" in body
    assert "deeptutor_turns_started_total 3" in body
    assert "deeptutor_turns_failed_total 1" in body
    assert "deeptutor_turn_avg_latency_ms 222.0" in body
    assert (
        'deeptutor_surface_event_total{event_name="start_turn_sent",status="accepted",surface="web"} 5'
        in body
    )
    assert 'deeptutor_surface_first_render_coverage_ratio{surface="web"} 0.8' in body
    assert 'deeptutor_surface_done_render_coverage_ratio{surface="web"} 0.6' in body
    assert (
        'deeptutor_release_info{deployment_environment="prod",ff_snapshot_hash="ffaa00112233",git_sha="abc123",prompt_version="prompt-v9",release_id="1.0.0+abc123+prod",service_version="1.0.0"} 1'
        in body
    )
