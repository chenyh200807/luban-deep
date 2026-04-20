from __future__ import annotations

from deeptutor.services.observability.release_gate import build_release_gate_report


def test_release_gate_report_marks_fail_and_warn_correctly() -> None:
    payload = build_release_gate_report(
        om_payload={
            "run_id": "om-1",
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc",
                "deployment_environment": "prod",
                "prompt_version": "p1",
                "ff_snapshot_hash": "ff1",
            },
            "health_summary": {"ready": True},
            "metrics_snapshot": {"surface_events": {"coverage": []}},
        },
        arr_payload={
            "run_id": "arr-1",
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc",
                "deployment_environment": "prod",
                "prompt_version": "p1",
                "ff_snapshot_hash": "ff1",
            },
            "summary": {"pass_rate": 1.0},
            "baseline_diff": {"regressions": [{"case_key": "semantic-router::critical"}], "new_failures": []},
        },
        aae_payload={
            "run_id": "aae-1",
            "composite": {"value": 0.92, "coverage_ratio": 0.8},
            "scorecard": {"paid_student_satisfaction_score": {"is_proxy": True}},
        },
        oa_payload={
            "run_id": "oa-1",
            "blind_spots": [{"type": "surface"}],
            "root_causes": [{"hypothesis": "x"}],
        },
    )

    assert payload["final_status"] == "FAIL"
    assert any(item["gate"] == "P1 Trace Completeness" and item["status"] == "WARN" for item in payload["gate_results"])
    assert any(item["gate"] == "P2 ARR" and item["status"] == "FAIL" for item in payload["gate_results"])


def test_release_gate_report_fails_when_unified_ws_smoke_failed() -> None:
    payload = build_release_gate_report(
        om_payload={
            "run_id": "om-1",
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc",
                "deployment_environment": "prod",
                "prompt_version": "p1",
                "ff_snapshot_hash": "ff1",
            },
            "health_summary": {
                "ready": True,
                "unified_ws_smoke_ok": False,
                "unified_ws_smoke_summary": "invalid api key",
            },
            "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
            "smoke_checks": [{"name": "unified_ws_smoke", "ok": False}],
        },
        arr_payload=None,
        aae_payload=None,
        oa_payload=None,
    )

    assert payload["final_status"] == "FAIL"
    assert any(item["gate"] == "P0 Runtime" and item["status"] == "FAIL" for item in payload["gate_results"])
    assert "ws_main_path_unhealthy" in payload["blockers"]
