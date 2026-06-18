from __future__ import annotations

from deeptutor.services.observability.om_snapshot import build_om_run


def test_build_om_run_captures_smoke_check_failures() -> None:
    payload = build_om_run(
        metrics_snapshot={
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc",
                "deployment_environment": "dev",
                "prompt_version": "p1",
                "ff_snapshot_hash": "ff1",
            },
            "readiness": {"ready": True},
            "turn_runtime": {
                "turns_started_total": 1,
                "turns_completed_total": 1,
                "turns_failed_total": 0,
                "turns_cancelled_total": 0,
                "turn_avg_latency_ms": 1200.0,
            },
            "surface_events": {"coverage": []},
            "providers": {"error_rates": {}},
        },
        smoke_checks=[
            {
                "name": "unified_ws_smoke",
                "ok": False,
                "summary": "ws main path failed",
                "evidence": ["invalid_api_key"],
            }
        ],
    )

    assert payload["health_summary"]["ready"] is True
    assert payload["health_summary"]["unified_ws_smoke_ok"] is False
    assert payload["smoke_checks"][0]["name"] == "unified_ws_smoke"
    assert payload["incident_candidates"][0]["title"] == "unified_ws_smoke_failed"


def test_build_om_run_preserves_deferred_smoke_as_unknown() -> None:
    payload = build_om_run(
        metrics_snapshot={
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc",
                "deployment_environment": "dev",
                "prompt_version": "p1",
                "ff_snapshot_hash": "ff1",
            },
            "readiness": {"ready": True},
            "turn_runtime": {
                "turns_started_total": 0,
                "turns_completed_total": 0,
                "turns_failed_total": 0,
                "turns_cancelled_total": 0,
                "turn_avg_latency_ms": 0.0,
            },
            "surface_events": {"coverage": []},
            "providers": {"error_rates": {}},
        },
        smoke_checks=[
            {
                "name": "unified_ws_smoke",
                "ok": None,
                "status": "DEFERRED",
                "summary": "target API service unavailable",
                "evidence": ["ConnectionRefusedError"],
            }
        ],
    )

    assert payload["health_summary"]["ready"] is True
    assert payload["health_summary"]["unified_ws_smoke_ok"] is None
    assert payload["smoke_checks"][0]["status"] == "DEFERRED"
    assert not any(
        item["title"] == "unified_ws_smoke_failed"
        for item in payload["incident_candidates"]
    )


def test_build_om_run_flags_turn_in_flight_without_ws_subscriber() -> None:
    payload = build_om_run(
        metrics_snapshot={
            "release": {"release_id": "rel-1", "git_sha": "abc"},
            "readiness": {"ready": True},
            "turn_runtime": {
                "ws_active_connections": 0,
                "turns_started_total": 11,
                "turns_completed_total": 10,
                "turns_failed_total": 0,
                "turns_cancelled_total": 0,
                "turns_in_flight": 1,
                "turn_avg_latency_ms": 1200.0,
            },
            "surface_events": {"coverage": []},
            "providers": {"error_rates": {}},
        },
    )

    assert payload["health_summary"]["orphaned_turns"] == 1
    assert any(
        item["title"] == "turn_in_flight_without_ws_subscriber"
        for item in payload["incident_candidates"]
    )
