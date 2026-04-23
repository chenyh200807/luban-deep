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
            "benchmark_run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["pr_gate_core"],
            },
            "benchmark_case_results": [
                {"suite": "pr_gate_core", "case_id": "case_a", "status": "FAIL"}
            ],
            "blind_spots": [{"type": "benchmark_surface"}],
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
    assert any(item["gate"] == "P2 Benchmark Regression" and item["status"] == "FAIL" for item in payload["gate_results"])
    assert payload["latest_runs"]["benchmark_run_id"] == "benchmark-1"
    assert "new_benchmark_regression" in payload["blockers"]


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


def test_release_gate_uses_benchmark_blind_spots_without_oa_payload() -> None:
    payload = build_release_gate_report(
        om_payload=None,
        arr_payload={
            "run_id": "arr-1",
            "benchmark_run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["incident_replay"],
            },
            "benchmark_case_results": [
                {"suite": "incident_replay", "case_id": "surface_a", "status": "SKIP"}
            ],
            "blind_spots": [
                {"suite": "incident_replay", "case_id": "surface_a", "reason": "missing_api_base_url"}
            ],
            "summary": {"pass_rate": None},
            "baseline_diff": {"regressions": [], "new_failures": [], "recovered": []},
        },
        aae_payload=None,
        oa_payload=None,
    )

    p4 = next(item for item in payload["gate_results"] if item["gate"] == "P4 Blind Spot Budget")
    assert p4["status"] == "PASS"
    assert p4["evidence"][0] == "blind_spots=1"
