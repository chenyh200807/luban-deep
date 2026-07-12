"""Cross-worker metric snapshot merge (Step 2 multiworker fix, design B).

`/metrics/prometheus` reads in-process singletons; with UVICORN_WORKERS>1 a scrape
sees only one worker. These tests pin the pure merge semantics that let the scrape
endpoint combine every worker's snapshot into a correct aggregate — counters summed,
averages re-weighted by their counts, per-worker state gauges OR'd so an open breaker
on the unscraped worker is never missed.
"""
from __future__ import annotations

from deeptutor.services.observability import multiworker_metrics as mwm

# Treat every pid as alive so file-IO/merge tests exercise the age/exclude/merge logic
# deterministically, independent of whether a fake pid happens to exist on the CI runner.
# pid-liveness reaping has its own dedicated tests below.
ALIVE = lambda _pid: True  # noqa: E731


def _http(requests=0, errors=0, uptime=0.0, status=None, routes=None):
    return {
        "started_at": 1000.0,
        "uptime_seconds": uptime,
        "requests_total": requests,
        "errors_total": errors,
        "status_counts": status or {},
        "routes": routes or [],
        "recent_errors": [],
    }


def _turn(**kw):
    base = {
        "ws_active_connections": 0,
        "ws_opened_total": 0,
        "ws_closed_total": 0,
        "turns_started_total": 0,
        "turns_completed_total": 0,
        "turns_failed_total": 0,
        "turns_cancelled_total": 0,
        "turns_in_flight": 0,
        "turn_avg_latency_ms": 0.0,
        "turn_stage_avg_latency_ms": [],
    }
    base.update(kw)
    return base


def _bundle(http=None, turn=None, surface=None, providers=None, breakers=None):
    return {
        "http": http or _http(),
        "turn": turn or _turn(),
        "surface": surface or {"event_counts": [], "coverage": [], "recent_events": []},
        "providers": providers or {},
        "circuit_breakers": breakers or {},
    }


# ---------------------------------------------------------------- identity

def test_single_bundle_merges_to_itself() -> None:
    """One worker => merge is identity on the fields the renderer consumes."""
    b = _bundle(
        http=_http(requests=10, errors=2, status={"200": 8, "500": 2}),
        turn=_turn(turns_started_total=5, turns_in_flight=1),
    )
    merged = mwm.merge_metric_snapshots([b])
    assert merged["http"]["requests_total"] == 10
    assert merged["http"]["errors_total"] == 2
    assert merged["http"]["status_counts"] == {"200": 8, "500": 2}
    assert merged["turn"]["turns_started_total"] == 5
    assert merged["turn"]["turns_in_flight"] == 1


# ---------------------------------------------------------------- http

def test_http_counters_sum_across_workers() -> None:
    a = _http(requests=10, errors=1, uptime=100.0, status={"200": 9, "500": 1})
    b = _http(requests=20, errors=3, uptime=90.0, status={"200": 17, "500": 3})
    merged = mwm.merge_metric_snapshots([_bundle(http=a), _bundle(http=b)])["http"]
    assert merged["requests_total"] == 30
    assert merged["errors_total"] == 4
    assert merged["status_counts"] == {"200": 26, "500": 4}
    assert merged["uptime_seconds"] == 100.0  # max


def test_http_route_avg_latency_is_request_weighted() -> None:
    a = _http(routes=[{"route": "GET /x", "requests": 1, "errors": 0, "avg_latency_ms": 100.0}])
    b = _http(routes=[{"route": "GET /x", "requests": 3, "errors": 0, "avg_latency_ms": 200.0}])
    merged = mwm.merge_metric_snapshots([_bundle(http=a), _bundle(http=b)])["http"]
    route = {r["route"]: r for r in merged["routes"]}["GET /x"]
    assert route["requests"] == 4
    # weighted: (100*1 + 200*3) / 4 = 175
    assert route["avg_latency_ms"] == 175.0


# ---------------------------------------------------------------- turn

def test_turn_avg_latency_weighted_by_finished_turns() -> None:
    # finished = completed+failed+cancelled. worker A: 1 finished @100ms, B: 3 finished @300ms
    a = _turn(turns_completed_total=1, turn_avg_latency_ms=100.0)
    b = _turn(turns_completed_total=2, turns_failed_total=1, turn_avg_latency_ms=300.0)
    merged = mwm.merge_metric_snapshots([_bundle(turn=a), _bundle(turn=b)])["turn"]
    assert merged["turns_completed_total"] == 3
    assert merged["turns_failed_total"] == 1
    # (100*1 + 300*3) / 4 = 250
    assert merged["turn_avg_latency_ms"] == 250.0


def test_turn_stage_latency_count_weighted() -> None:
    a = _turn(turn_stage_avg_latency_ms=[{"stage": "llm", "avg_latency_ms": 50.0, "count": 2}])
    b = _turn(turn_stage_avg_latency_ms=[{"stage": "llm", "avg_latency_ms": 150.0, "count": 2}])
    merged = mwm.merge_metric_snapshots([_bundle(turn=a), _bundle(turn=b)])["turn"]
    stage = {s["stage"]: s for s in merged["turn_stage_avg_latency_ms"]}["llm"]
    assert stage["count"] == 4
    assert stage["avg_latency_ms"] == 100.0  # (50*2 + 150*2)/4


def test_fuc_histogram_summed_per_source_across_workers() -> None:
    """Battle2 S3-T3 hardening: without this merge, UVICORN_WORKERS=2 halves the
    TTFVT distribution (a scrape only sees the answering worker's histogram)."""
    bounds = [500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 32000.0, 64000.0]
    a = _turn(first_useful_content_ms=[
        {"content_source": "content.delta", "bucket_bounds_ms": bounds,
         "bucket_counts": [2, 1, 0, 0, 0, 0, 0, 0, 0], "sum_ms": 1400.0, "count": 3},
    ])
    b = _turn(first_useful_content_ms=[
        {"content_source": "content.delta", "bucket_bounds_ms": bounds,
         "bucket_counts": [1, 0, 0, 1, 0, 0, 0, 0, 1], "sum_ms": 103500.0, "count": 3},
        {"content_source": "result.response", "bucket_bounds_ms": bounds,
         "bucket_counts": [0, 0, 1, 0, 0, 0, 0, 0, 0], "sum_ms": 1500.0, "count": 1},
    ])
    merged = mwm.merge_metric_snapshots([_bundle(turn=a), _bundle(turn=b)])["turn"]
    by_source = {e["content_source"]: e for e in merged["first_useful_content_ms"]}
    delta = by_source["content.delta"]
    assert delta["bucket_counts"] == [3, 1, 0, 1, 0, 0, 0, 0, 1]
    assert delta["count"] == 6
    assert delta["sum_ms"] == 104900.0
    assert by_source["result.response"]["count"] == 1


def test_fuc_histogram_merge_tolerates_missing_and_corrupt_entries() -> None:
    bounds = [500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 32000.0, 64000.0]
    good = _turn(first_useful_content_ms=[
        {"content_source": "content.delta", "bucket_bounds_ms": bounds,
         "bucket_counts": [1, 0, 0, 0, 0, 0, 0, 0, 0], "sum_ms": 300.0, "count": 1},
    ])
    legacy_no_key = _turn()  # pre-Battle2 worker snapshot without the key
    corrupt = _turn(first_useful_content_ms=[
        {"content_source": "content.delta", "bucket_bounds_ms": [1.0], "bucket_counts": [9]},
    ])
    merged = mwm.merge_metric_snapshots(
        [_bundle(turn=good), _bundle(turn=legacy_no_key), _bundle(turn=corrupt)]
    )["turn"]["first_useful_content_ms"]
    assert len(merged) == 1
    assert merged[0]["count"] == 1


def test_fuc_histogram_survives_dump_read_merge_render_round_trip(tmp_path) -> None:
    """End-to-end two-worker path: worker 222 dumps its snapshot file, live worker 111
    merges via collect_merged_snapshots, and the real renderer exposes summed buckets."""
    from deeptutor.api.runtime_metrics import TurnRuntimeMetrics, render_prometheus_metrics

    worker_222 = TurnRuntimeMetrics()
    worker_222.record_first_useful_content(elapsed_ms=400.0, content_source="content.delta")
    worker_222.record_first_useful_content(elapsed_ms=6000.0, content_source="content.delta")
    mwm.dump_worker_snapshot(tmp_path, 222, _bundle(turn=worker_222.snapshot()), now=1000.0)

    worker_111 = TurnRuntimeMetrics()
    worker_111.record_first_useful_content(elapsed_ms=250.0, content_source="content.delta")
    merged = mwm.collect_merged_snapshots(
        tmp_path, 111, _bundle(turn=worker_111.snapshot()),
        staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE,
    )

    text = render_prometheus_metrics(
        http_snapshot=merged["http"],
        turn_snapshot=merged["turn"],
        surface_snapshot=merged["surface"],
        readiness_snapshot={"ready": True, "checks": {}},
        provider_error_rates=merged["providers"],
        circuit_breakers=merged["circuit_breakers"],
        release_snapshot={},
    )
    # 250 + 400 in le=500; 6000 lands in le=8000; +Inf carries all three samples.
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="500"} 2' in text
    assert 'deeptutor_turn_first_useful_content_ms_bucket{content_source="content.delta",le="+Inf"} 3' in text
    assert 'deeptutor_turn_first_useful_content_ms_count{content_source="content.delta"} 3' in text


# ---------------------------------------------------------------- surface

def test_surface_coverage_recomputed_from_summed_raw_counts() -> None:
    a = {
        "event_counts": [{"surface": "wx", "event_name": "start_turn_sent", "status": "accepted", "count": 4}],
        "coverage": [{"surface": "wx", "start_turn_sent": 4, "first_visible_content_rendered": 2,
                      "done_rendered": 1, "surface_render_failed": 0,
                      "first_render_coverage_ratio": 0.5, "done_render_coverage_ratio": 0.25}],
        "recent_events": [],
    }
    b = {
        "event_counts": [{"surface": "wx", "event_name": "start_turn_sent", "status": "accepted", "count": 6}],
        "coverage": [{"surface": "wx", "start_turn_sent": 6, "first_visible_content_rendered": 6,
                      "done_rendered": 5, "surface_render_failed": 1,
                      "first_render_coverage_ratio": 1.0, "done_render_coverage_ratio": 0.8333}],
        "recent_events": [],
    }
    merged = mwm.merge_metric_snapshots([_bundle(surface=a), _bundle(surface=b)])["surface"]
    ev = {(e["surface"], e["event_name"], e["status"]): e for e in merged["event_counts"]}
    assert ev[("wx", "start_turn_sent", "accepted")]["count"] == 10
    cov = {c["surface"]: c for c in merged["coverage"]}["wx"]
    assert cov["start_turn_sent"] == 10
    assert cov["first_visible_content_rendered"] == 8
    # ratio recomputed from summed raw: 8/10 = 0.8 (NOT mean of 0.5 and 1.0)
    assert cov["first_render_coverage_ratio"] == 0.8


# ---------------------------------------------------------------- providers

def test_provider_error_rate_recomputed_and_threshold_ord() -> None:
    a = {"deepseek": {"total_calls": 10, "error_calls": 1, "error_rate": 0.1,
                      "threshold_exceeded": False, "alert_open": False}}
    b = {"deepseek": {"total_calls": 10, "error_calls": 5, "error_rate": 0.5,
                      "threshold_exceeded": True, "alert_open": False}}
    merged = mwm.merge_metric_snapshots([_bundle(providers=a), _bundle(providers=b)])["providers"]
    p = merged["deepseek"]
    assert p["total_calls"] == 20
    assert p["error_calls"] == 6
    assert p["error_rate"] == 0.3  # 6/20
    assert p["threshold_exceeded"] is True  # OR: one worker exceeded


# ---------------------------------------------------------------- circuit breakers

def test_breaker_open_on_any_worker_is_never_missed() -> None:
    """The core alert-correctness win: scrape lands on a closed worker, but another
    worker's breaker is open => merged must report open."""
    a = {"deepseek": {"state": "closed", "failure_count": 0, "last_failure_time": 0.0,
                      "recovery_timeout": 30, "failure_threshold": 5}}
    b = {"deepseek": {"state": "open", "failure_count": 7, "last_failure_time": 123.0,
                      "recovery_timeout": 30, "failure_threshold": 5}}
    merged = mwm.merge_metric_snapshots([_bundle(breakers=a), _bundle(breakers=b)])["circuit_breakers"]
    assert merged["deepseek"]["state"] == "open"
    assert merged["deepseek"]["failure_count"] == 7  # max


def test_breaker_half_open_beats_closed() -> None:
    a = {"x": {"state": "closed", "failure_count": 0, "last_failure_time": 0.0,
               "recovery_timeout": 30, "failure_threshold": 5}}
    b = {"x": {"state": "half-open", "failure_count": 3, "last_failure_time": 5.0,
               "recovery_timeout": 30, "failure_threshold": 5}}
    merged = mwm.merge_metric_snapshots([_bundle(breakers=a), _bundle(breakers=b)])["circuit_breakers"]
    assert merged["x"]["state"] == "half-open"


# ---------------------------------------------------------------- file I/O

def test_dump_then_read_round_trip(tmp_path) -> None:
    b = _bundle(http=_http(requests=7))
    mwm.dump_worker_snapshot(tmp_path, 111, b, now=1000.0)
    read = mwm.read_worker_snapshots(tmp_path, staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE)
    assert len(read) == 1
    assert read[0]["http"]["requests_total"] == 7


def test_read_excludes_stale_files(tmp_path) -> None:
    mwm.dump_worker_snapshot(tmp_path, 111, _bundle(http=_http(requests=7)), now=1000.0)
    # 200s later, worker 111 stopped dumping (alive but dump loop dead) → age-out
    read = mwm.read_worker_snapshots(tmp_path, staleness_seconds=60.0, now=1200.0, pid_is_alive=ALIVE)
    assert read == []


def test_read_excludes_self_pid(tmp_path) -> None:
    mwm.dump_worker_snapshot(tmp_path, 111, _bundle(http=_http(requests=7)), now=1000.0)
    mwm.dump_worker_snapshot(tmp_path, 222, _bundle(http=_http(requests=9)), now=1000.0)
    read = mwm.read_worker_snapshots(
        tmp_path, staleness_seconds=60.0, now=1000.0, exclude_pid=111, pid_is_alive=ALIVE
    )
    assert len(read) == 1
    assert read[0]["http"]["requests_total"] == 9


def test_collect_merged_combines_live_self_with_other_workers(tmp_path) -> None:
    # other worker 222 wrote a (possibly slightly stale) file; live self 111 is fresh
    mwm.dump_worker_snapshot(tmp_path, 222, _bundle(http=_http(requests=20)), now=995.0)
    live = _bundle(http=_http(requests=10))
    merged = mwm.collect_merged_snapshots(
        tmp_path, 111, live, staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE
    )
    assert merged["http"]["requests_total"] == 30  # live 10 + other 20


def test_collect_merged_single_worker_is_live_identity(tmp_path) -> None:
    live = _bundle(http=_http(requests=10, errors=2))
    merged = mwm.collect_merged_snapshots(
        tmp_path, 111, live, staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE
    )
    assert merged["http"]["requests_total"] == 10
    assert merged["http"]["errors_total"] == 2


# -------------------------------------------------------- render shape contract

def test_merged_bundle_renders_with_real_renderer(tmp_path) -> None:
    """Integration guard: the merged bundle's shape must be exactly what the unchanged
    render_prometheus_metrics consumes. A dump (worker 222) + live (worker 111) merge,
    fed into the real renderer, must render and reflect the summed counters / OR'd state."""
    from deeptutor.api.runtime_metrics import render_prometheus_metrics

    mwm.dump_worker_snapshot(
        tmp_path,
        222,
        _bundle(
            http=_http(requests=20, errors=4, status={"200": 16, "500": 4}),
            breakers={"deepseek": {"state": "open", "failure_count": 9, "last_failure_time": 1.0,
                                   "recovery_timeout": 30, "failure_threshold": 5}},
        ),
        now=1000.0,
    )
    live = _bundle(
        http=_http(requests=10, errors=1, status={"200": 9, "500": 1}),
        breakers={"deepseek": {"state": "closed", "failure_count": 0, "last_failure_time": 0.0,
                               "recovery_timeout": 30, "failure_threshold": 5}},
    )
    merged = mwm.collect_merged_snapshots(
        tmp_path, 111, live, staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE
    )

    text = render_prometheus_metrics(
        http_snapshot=merged["http"],
        turn_snapshot=merged["turn"],
        surface_snapshot=merged["surface"],
        readiness_snapshot={"ready": True, "checks": {}},
        provider_error_rates=merged["providers"],
        circuit_breakers=merged["circuit_breakers"],
        release_snapshot={},
    )
    assert "deeptutor_http_requests_total 30" in text  # 10 + 20 summed across workers
    assert "deeptutor_http_errors_total 5" in text  # 1 + 4
    # breaker open on worker 222 surfaces even though live worker 111 was closed
    assert 'deeptutor_circuit_breaker_open{provider="deepseek"} 1' in text


# -------------------------------------------------- crash safety (pid liveness)

def test_dead_worker_file_is_excluded_and_reaped(tmp_path) -> None:
    """SEV-1 regression: an OOM-killed worker's file must NOT keep being summed (it would
    double-count counters ~Nx until age-out, then drop them = a counter reset to rate()).
    A dead pid is dropped immediately AND the file is reaped, regardless of freshness."""
    mwm.dump_worker_snapshot(tmp_path, 999, _bundle(http=_http(requests=50)), now=1000.0)
    # file is fresh (now==dump ts) — only pid-liveness, not age, can exclude it.
    read = mwm.read_worker_snapshots(
        tmp_path, staleness_seconds=60.0, now=1000.0, pid_is_alive=lambda p: p != 999
    )
    assert read == []
    assert not (mwm.metrics_dir(tmp_path) / "worker-999.json").exists()  # reaped


def test_live_worker_fresh_file_survives_when_pid_alive(tmp_path) -> None:
    mwm.dump_worker_snapshot(tmp_path, 999, _bundle(http=_http(requests=50)), now=1000.0)
    read = mwm.read_worker_snapshots(
        tmp_path, staleness_seconds=60.0, now=1000.0, pid_is_alive=lambda p: True
    )
    assert len(read) == 1
    assert (mwm.metrics_dir(tmp_path) / "worker-999.json").exists()  # not reaped


def test_crash_then_restart_does_not_double_count(tmp_path) -> None:
    """Concrete crash path: worker 100 dumped then OOM-died; replacement worker 200 (new
    pid) is now live and dumped too. Merge from the scrape worker must count only the live
    replacement, never sum the dead worker's lingering-but-fresh file."""
    mwm.dump_worker_snapshot(tmp_path, 100, _bundle(http=_http(requests=40)), now=1000.0)  # dead
    mwm.dump_worker_snapshot(tmp_path, 200, _bundle(http=_http(requests=40)), now=1000.0)  # live replacement
    live = _bundle(http=_http(requests=10))  # the scrape worker itself
    merged = mwm.collect_merged_snapshots(
        tmp_path, 111, live, staleness_seconds=60.0, now=1000.0, pid_is_alive=lambda p: p != 100
    )
    assert merged["http"]["requests_total"] == 50  # live 10 + replacement 40; dead 40 excluded


# -------------------------------------------------- corrupt / edge robustness

def test_non_dict_json_payload_is_skipped_not_fatal(tmp_path) -> None:
    """A valid-JSON-but-wrong-shape file (e.g. a bare list) must be skipped, not raise
    AttributeError on .get — the docstring promises corrupt files are never fatal."""
    directory = mwm.metrics_dir(tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "worker-1.json").write_text("[]", encoding="utf-8")  # valid JSON, not a dict
    (directory / "worker-2.json").write_text("not json at all", encoding="utf-8")  # invalid JSON
    read = mwm.read_worker_snapshots(tmp_path, staleness_seconds=60.0, now=1000.0, pid_is_alive=ALIVE)
    assert read == []  # both skipped, no exception


def test_merge_empty_list_returns_zeroed_shape(tmp_path) -> None:
    merged = mwm.merge_metric_snapshots([])
    assert set(merged) == {"http", "turn", "surface", "providers", "circuit_breakers"}
    assert merged["http"]["requests_total"] == 0
    assert merged["turn"]["turns_started_total"] == 0
    assert merged["providers"] == {}
    assert merged["circuit_breakers"] == {}


def test_merge_provider_present_in_only_one_worker() -> None:
    a = {"deepseek": {"total_calls": 10, "error_calls": 2, "error_rate": 0.2,
                      "threshold_exceeded": False, "alert_open": False}}
    b = {}  # this worker never called deepseek
    merged = mwm.merge_metric_snapshots([_bundle(providers=a), _bundle(providers=b)])["providers"]
    assert merged["deepseek"]["total_calls"] == 10
    assert merged["deepseek"]["error_calls"] == 2
    assert merged["deepseek"]["error_rate"] == 0.2  # missing side counts as 0, no crash


def test_merge_coverage_zero_start_no_division_error() -> None:
    a = {"event_counts": [], "coverage": [{"surface": "wx", "start_turn_sent": 0,
         "first_visible_content_rendered": 0, "done_rendered": 0, "surface_render_failed": 0,
         "first_render_coverage_ratio": None, "done_render_coverage_ratio": None}], "recent_events": []}
    merged = mwm.merge_metric_snapshots([_bundle(surface=a)])["surface"]
    cov = {c["surface"]: c for c in merged["coverage"]}["wx"]
    assert cov["first_render_coverage_ratio"] is None  # start=0 → None, no ZeroDivisionError


def test_merge_breaker_missing_state_field_defaults_closed() -> None:
    a = {"x": {"failure_count": 1, "last_failure_time": 0.0, "recovery_timeout": 30,
               "failure_threshold": 5}}  # no "state" key
    merged = mwm.merge_metric_snapshots([_bundle(breakers=a)])["circuit_breakers"]
    assert merged["x"]["state"] == "closed"  # absent state must not read as open
