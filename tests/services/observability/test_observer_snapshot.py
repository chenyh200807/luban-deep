from __future__ import annotations

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import build_turn_observation_event


def test_build_observer_snapshot_collects_store_and_turn_event_evidence(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    release = {
        "release_id": "rel-1",
        "git_sha": "abc",
        "deployment_environment": "dev",
        "prompt_version": "p1",
        "ff_snapshot_hash": "ff1",
    }
    store.write_run(
        kind="om_runs",
        run_id="om-1",
        release_id="rel-1",
        payload={
            "run_id": "om-1",
            "release": release,
            "health_summary": {"ready": True, "turn_success_ratio": 1.0},
            "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
        },
    )
    store.write_run(
        kind="arr_runs",
        run_id="arr-1",
        release_id="rel-1",
        payload={
            "run_id": "arr-1",
            "release": release,
            "summary": {"pass_rate": 0.9},
            "baseline_diff": {"regressions": [], "new_failures": []},
        },
    )
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        build_turn_observation_event(
            release=release,
            session_id="session-1",
            turn_id="turn-1",
            status="completed",
            capability="chat",
            latency_ms=1000,
            token_total=42,
            retrieval_hit=True,
        )
    )
    event_log.append(
        build_turn_observation_event(
            release=release,
            session_id="session-1",
            turn_id="turn-2",
            status="failed",
            capability="deep_question",
            latency_ms=3000,
            token_total=84,
            retrieval_hit=False,
        )
    )

    payload = build_observer_snapshot(store=store, event_log=event_log, event_days=1)

    assert payload["run_id"].startswith("observer-snapshot-")
    assert payload["release"]["release_id"] == "rel-1"
    assert payload["data_coverage"]["layers_with_data"] >= 3
    assert payload["turn_events"]["event_count"] == 2
    assert payload["turn_events"]["error_count"] == 1
    assert payload["turn_events"]["avg_latency_ms"] == 2000.0
    assert payload["turn_events"]["retrieval_hit_ratio"] == 0.5
    assert payload["turn_event_log"]["last_write_error"] == ""
    assert payload["source_runs"]["om_run_id"] == "om-1"
    assert payload["source_runs"]["arr_run_id"] == "arr-1"
    layers = {item["name"]: item for item in payload["data_coverage"]["layers"]}
    assert "reason" not in layers["turn_event_log"]
    assert layers["aae_composite"]["reason"] == "missing AAE composite"


def test_build_observer_snapshot_reports_blind_spots_when_sources_missing(tmp_path) -> None:
    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=TurnEventLog(events_dir=tmp_path / "events"),
        event_days=1,
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert "missing_turn_event_log" in blind_spot_types
    assert "missing_om_snapshot" in blind_spot_types
    assert "missing_quality_run" in blind_spot_types
    assert payload["data_coverage"]["coverage_ratio"] < 1.0


def test_build_observer_snapshot_reports_turn_event_log_write_error(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    assert event_log.append({"bad": object()}) is False

    payload = build_observer_snapshot(
        store=ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane"),
        event_log=event_log,
        event_days=1,
    )

    blind_spot_types = {item["type"] for item in payload["blind_spots"]}
    assert "turn_event_log_write_error" in blind_spot_types
    assert "TypeError" in payload["turn_event_log"]["last_write_error"]
