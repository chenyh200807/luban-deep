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


# ----------------------------------------------------------------------------------
# Battle2 S3-T3: turn-level TTFVT histogram (observe-only, one-hop export)
# ----------------------------------------------------------------------------------
def test_record_first_useful_content_buckets_sum_and_count() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_first_useful_content(elapsed_ms=300.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=3000.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=999999.0, content_source="content.delta")

    entries = metrics.snapshot()["first_useful_content_ms"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["content_source"] == "content.delta"
    assert entry["bucket_bounds_ms"] == [
        500.0,
        1000.0,
        2000.0,
        4000.0,
        8000.0,
        16000.0,
        32000.0,
        64000.0,
    ]
    # 300 -> le=500 bucket; 3000 -> le=4000 bucket; 999999 -> overflow (+Inf) bucket.
    assert entry["bucket_counts"] == [1, 0, 0, 1, 0, 0, 0, 0, 1]
    assert entry["count"] == 3
    assert entry["sum_ms"] == 1003299.0


def test_record_first_useful_content_is_fail_open_on_bad_input() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_first_useful_content(elapsed_ms=None, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms="not-a-number", content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=-5.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=float("nan"), content_source="content.delta")
    # Unknown source collapses into "other" instead of exploding label cardinality.
    metrics.record_first_useful_content(elapsed_ms=120.0, content_source="weird.source")

    entries = metrics.snapshot()["first_useful_content_ms"]
    assert len(entries) == 1
    assert entries[0]["content_source"] == "other"
    assert entries[0]["count"] == 1


def test_render_prometheus_metrics_exposes_fuc_histogram_cumulative() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_first_useful_content(elapsed_ms=300.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=700.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=70000.0, content_source="content.delta")
    metrics.record_first_useful_content(elapsed_ms=1500.0, content_source="result.response")

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert "# TYPE deeptutor_turn_first_useful_content_ms histogram" in body
    # Cumulative buckets are monotonically non-decreasing up to +Inf == count.
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="500"} 1' in body
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="1000"} 2' in body
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="64000"} 2' in body
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="+Inf"} 3' in body
    assert 'deeptutor_turn_first_useful_content_ms_sum{content_source="content.delta"} 71000.0' in body
    assert 'deeptutor_turn_first_useful_content_ms_count{content_source="content.delta"} 3' in body
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="result.response",le="2000"} 1' in body
    assert 'deeptutor_turn_first_useful_content_ms_count{content_source="result.response"} 1' in body


def test_merge_metric_snapshots_sums_fuc_histogram_across_workers() -> None:
    """Commander-verified hardening: UVICORN_WORKERS=2 merges per-worker snapshots via
    multiworker_metrics; a missing merge would systematically halve the TTFVT
    distribution (scrape only sees the answering worker)."""
    worker_a = TurnRuntimeMetrics()
    worker_a.record_first_useful_content(elapsed_ms=300.0, content_source="content.delta")
    worker_a.record_first_useful_content(elapsed_ms=5000.0, content_source="content.delta")
    worker_b = TurnRuntimeMetrics()
    worker_b.record_first_useful_content(elapsed_ms=450.0, content_source="content.delta")
    worker_b.record_first_useful_content(elapsed_ms=1200.0, content_source="result.response")

    merged = merge_metric_snapshots(
        [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
    )["turn"]["first_useful_content_ms"]

    by_source = {entry["content_source"]: entry for entry in merged}
    delta = by_source["content.delta"]
    assert delta["count"] == 3
    assert delta["sum_ms"] == 5750.0
    assert delta["bucket_counts"][0] == 2  # 300 + 450 in the le=500 bucket
    assert delta["bucket_counts"][4] == 1  # 5000 in the le=8000 bucket
    assert by_source["result.response"]["count"] == 1

    # Merged snapshot renders through the unchanged renderer with summed buckets.
    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=merge_metric_snapshots(
            [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
        )["turn"],
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="500"} 2' in body
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="+Inf"} 3' in body


def test_merge_metric_snapshots_fuc_histogram_skips_corrupt_entries() -> None:
    worker_a = TurnRuntimeMetrics()
    worker_a.record_first_useful_content(elapsed_ms=300.0, content_source="content.delta")
    corrupt = {
        "turn": {
            "first_useful_content_ms": [
                {"content_source": "content.delta", "bucket_bounds_ms": [1.0], "bucket_counts": [1]},
            ]
        }
    }
    merged = merge_metric_snapshots([{"turn": worker_a.snapshot()}, corrupt])["turn"][
        "first_useful_content_ms"
    ]
    assert len(merged) == 1
    assert merged[0]["count"] == 1


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


# ----------------------------------------------------------------------------------
# Battle2 S1-T4: summary-maintainer gate decisions (observe-only, ships with the gate)
# ----------------------------------------------------------------------------------
def test_summary_maintainer_counts_snapshot_and_prometheus() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_summary_maintainer(decision="skip_throttled", outcome="skipped")
    metrics.record_summary_maintainer(decision="skip_throttled", outcome="skipped")
    metrics.record_summary_maintainer(decision="run_counter", outcome="no_change")
    metrics.record_summary_maintainer(decision="run_fail_open", outcome="changed")
    metrics.record_summary_maintainer(decision="", outcome="")  # normalizes, never raises

    counts = metrics.snapshot()["summary_maintainer_counts"]
    assert {"decision": "skip_throttled", "outcome": "skipped", "count": 2} in counts
    assert {"decision": "run_counter", "outcome": "no_change", "count": 1} in counts
    assert {"decision": "run_fail_open", "outcome": "changed", "count": 1} in counts
    assert {"decision": "unknown", "outcome": "-", "count": 1} in counts

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert "# TYPE deeptutor_summary_maintainer_total counter" in body
    assert 'deeptutor_summary_maintainer_total{decision="skip_throttled",outcome="skipped"} 2' in body
    assert 'deeptutor_summary_maintainer_total{decision="run_counter",outcome="no_change"} 1' in body
    assert 'deeptutor_summary_maintainer_total{decision="run_fail_open",outcome="changed"} 1' in body


def test_merge_metric_snapshots_sums_summary_maintainer_counts_across_workers() -> None:
    """Commander hard ruling: production runs UVICORN_WORKERS=2 and /metrics/prometheus
    merges per-worker snapshot files; a snapshot key missing from the multiworker merge
    would systematically under-count the gate hit rate (scrape sees one worker only)."""
    worker_a = TurnRuntimeMetrics()
    worker_a.record_summary_maintainer(decision="skip_throttled", outcome="skipped")
    worker_a.record_summary_maintainer(decision="skip_throttled", outcome="skipped")
    worker_a.record_summary_maintainer(decision="run_counter", outcome="changed")
    worker_b = TurnRuntimeMetrics()
    worker_b.record_summary_maintainer(decision="skip_throttled", outcome="skipped")
    worker_b.record_summary_maintainer(decision="run_evidence", outcome="no_change")

    merged_turn = merge_metric_snapshots(
        [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
    )["turn"]
    merged = merged_turn["summary_maintainer_counts"]
    assert {"decision": "skip_throttled", "outcome": "skipped", "count": 3} in merged
    assert {"decision": "run_counter", "outcome": "changed", "count": 1} in merged
    assert {"decision": "run_evidence", "outcome": "no_change", "count": 1} in merged

    # Merged snapshot renders through the unchanged renderer with summed counters.
    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=merged_turn,
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert 'deeptutor_summary_maintainer_total{decision="skip_throttled",outcome="skipped"} 3' in body
    assert 'deeptutor_summary_maintainer_total{decision="run_evidence",outcome="no_change"} 1' in body


def test_memory_maintainer_counts_snapshot_and_prometheus() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_memory_maintainer(decision="skip_throttled", outcome="skipped")
    metrics.record_memory_maintainer(decision="skip_throttled", outcome="skipped")
    metrics.record_memory_maintainer(decision="run_counter", outcome="no_change")
    metrics.record_memory_maintainer(decision="run_fail_open", outcome="changed")
    metrics.record_memory_maintainer(decision="", outcome="")  # normalizes, never raises

    counts = metrics.snapshot()["memory_maintainer_counts"]
    assert {"decision": "skip_throttled", "outcome": "skipped", "count": 2} in counts
    assert {"decision": "run_counter", "outcome": "no_change", "count": 1} in counts
    assert {"decision": "run_fail_open", "outcome": "changed", "count": 1} in counts
    assert {"decision": "unknown", "outcome": "-", "count": 1} in counts

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert "# TYPE deeptutor_memory_maintainer_total counter" in body
    assert 'deeptutor_memory_maintainer_total{decision="skip_throttled",outcome="skipped"} 2' in body
    assert 'deeptutor_memory_maintainer_total{decision="run_counter",outcome="no_change"} 1' in body
    assert 'deeptutor_memory_maintainer_total{decision="run_fail_open",outcome="changed"} 1' in body


def test_merge_metric_snapshots_sums_memory_maintainer_counts_across_workers() -> None:
    """UVICORN_WORKERS=2 下 /metrics/prometheus 合并 per-worker 快照;记忆门控计数
    若缺多 worker 合并路径会系统性低估门命中率(一次抓取只见一个 worker)。"""
    worker_a = TurnRuntimeMetrics()
    worker_a.record_memory_maintainer(decision="skip_throttled", outcome="skipped")
    worker_a.record_memory_maintainer(decision="skip_throttled", outcome="skipped")
    worker_a.record_memory_maintainer(decision="run_counter", outcome="changed")
    worker_b = TurnRuntimeMetrics()
    worker_b.record_memory_maintainer(decision="skip_throttled", outcome="skipped")
    worker_b.record_memory_maintainer(decision="run_fail_open", outcome="no_change")

    merged_turn = merge_metric_snapshots(
        [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
    )["turn"]
    merged = merged_turn["memory_maintainer_counts"]
    assert {"decision": "skip_throttled", "outcome": "skipped", "count": 3} in merged
    assert {"decision": "run_counter", "outcome": "changed", "count": 1} in merged
    assert {"decision": "run_fail_open", "outcome": "no_change", "count": 1} in merged

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=merged_turn,
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert 'deeptutor_memory_maintainer_total{decision="skip_throttled",outcome="skipped"} 3' in body
    assert 'deeptutor_memory_maintainer_total{decision="run_fail_open",outcome="no_change"} 1' in body


def test_record_assessment_explanation_buckets_sum_and_count() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_assessment_explanation(elapsed_ms=300.0)
    metrics.record_assessment_explanation(elapsed_ms=3000.0)
    metrics.record_assessment_explanation(elapsed_ms=999999.0)

    entry = metrics.snapshot()["assessment_explanation_ms"]
    assert entry is not None
    assert entry["bucket_bounds_ms"] == [
        500.0,
        1000.0,
        2000.0,
        4000.0,
        8000.0,
        16000.0,
        32000.0,
        64000.0,
    ]
    # 300 -> le=500 bucket; 3000 -> le=4000 bucket; 999999 -> overflow (+Inf) bucket.
    assert entry["bucket_counts"] == [1, 0, 0, 1, 0, 0, 0, 0, 1]
    assert entry["count"] == 3
    assert entry["sum_ms"] == 1003299.0


def test_record_assessment_explanation_is_fail_open_on_bad_input() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_assessment_explanation(elapsed_ms=None)  # type: ignore[arg-type]
    metrics.record_assessment_explanation(elapsed_ms="nan-ish")  # type: ignore[arg-type]
    metrics.record_assessment_explanation(elapsed_ms=-5.0)
    metrics.record_assessment_explanation(elapsed_ms=float("nan"))
    # An idle/rejected-only histogram exports nothing (None), not an empty series.
    assert metrics.snapshot()["assessment_explanation_ms"] is None

    metrics.record_assessment_explanation(elapsed_ms=120.0)
    assert metrics.snapshot()["assessment_explanation_ms"]["count"] == 1


def test_render_prometheus_metrics_exposes_assessment_explanation_histogram() -> None:
    metrics = TurnRuntimeMetrics()
    metrics.record_assessment_explanation(elapsed_ms=300.0)
    metrics.record_assessment_explanation(elapsed_ms=700.0)
    metrics.record_assessment_explanation(elapsed_ms=70000.0)

    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    assert "# TYPE deeptutor_assessment_deep_explanation_ms histogram" in body
    assert 'deeptutor_assessment_deep_explanation_ms_bucket{le="500"} 1' in body
    assert 'deeptutor_assessment_deep_explanation_ms_bucket{le="1000"} 2' in body
    assert 'deeptutor_assessment_deep_explanation_ms_bucket{le="64000"} 2' in body
    assert 'deeptutor_assessment_deep_explanation_ms_bucket{le="+Inf"} 3' in body
    assert "deeptutor_assessment_deep_explanation_ms_sum 71000.0" in body
    assert "deeptutor_assessment_deep_explanation_ms_count 3" in body


def test_render_prometheus_metrics_omits_assessment_explanation_when_idle() -> None:
    metrics = TurnRuntimeMetrics()
    body = render_prometheus_metrics(
        http_snapshot={},
        turn_snapshot=metrics.snapshot(),
        surface_snapshot={},
        readiness_snapshot={},
        provider_error_rates={},
        circuit_breakers={},
        release_snapshot={},
    )
    # HELP/TYPE headers always present; no data lines when nothing was recorded.
    assert "# TYPE deeptutor_assessment_deep_explanation_ms histogram" in body
    assert "deeptutor_assessment_deep_explanation_ms_count" not in body


def test_merge_metric_snapshots_sums_assessment_explanation_across_workers() -> None:
    worker_a = TurnRuntimeMetrics()
    worker_a.record_assessment_explanation(elapsed_ms=300.0)
    worker_a.record_assessment_explanation(elapsed_ms=5000.0)
    worker_b = TurnRuntimeMetrics()
    worker_b.record_assessment_explanation(elapsed_ms=450.0)

    merged = merge_metric_snapshots(
        [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
    )["turn"]["assessment_explanation_ms"]

    assert merged["count"] == 3
    assert merged["sum_ms"] == 5750.0
    assert merged["bucket_counts"][0] == 2  # 300 + 450 in the le=500 bucket
    assert merged["bucket_counts"][4] == 1  # 5000 in the le=8000 bucket


def test_merge_metric_snapshots_assessment_explanation_none_when_idle() -> None:
    worker_a = TurnRuntimeMetrics()
    worker_b = TurnRuntimeMetrics()
    merged = merge_metric_snapshots(
        [{"turn": worker_a.snapshot()}, {"turn": worker_b.snapshot()}]
    )["turn"]["assessment_explanation_ms"]
    assert merged is None
