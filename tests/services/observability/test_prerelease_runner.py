from __future__ import annotations

from pathlib import Path

from deeptutor.services.observability import reset_control_plane_store
from deeptutor.services.observability.prerelease_runner import run_prerelease_observability


def test_run_prerelease_observability_runs_pipeline_and_persists_outputs(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")

    async def fake_run_unified_ws_smoke(**kwargs):
        return {
            "run_id": "ws-smoke-1",
            "passed": True,
            "terminal_event": {"type": "done"},
            "messages": [{"type": "done"}],
            "metrics_after": {
                "turn_runtime": {
                    "turns_started_total": 1,
                    "turns_completed_total": 1,
                    "turns_failed_total": 0,
                    "turns_cancelled_total": 0,
                    "turns_in_flight": 0,
                }
            },
        }

    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.run_unified_ws_smoke",
        fake_run_unified_ws_smoke,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.run_surface_ack_smoke",
        lambda **kwargs: {
            "run_id": "surface-smoke-1",
            "passed": True,
            "surface": kwargs["surface"],
            "coverage": {"first_render_coverage_ratio": 1.0, "done_render_coverage_ratio": 1.0},
            "posted_events": [],
            "missing_requirements": [],
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.load_metrics_snapshot",
        lambda **kwargs: {
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc123",
                "deployment_environment": "dev",
                "prompt_version": "prompt-v1",
                "ff_snapshot_hash": "ff-1",
            },
            "readiness": {"ready": True},
            "turn_runtime": {
                "turns_started_total": 1,
                "turns_completed_total": 1,
                "turns_failed_total": 0,
                "turns_cancelled_total": 0,
                "turn_avg_latency_ms": 1200.0,
            },
            "surface_events": {
                "coverage": [
                    {
                        "surface": "web",
                        "start_turn_sent": 1,
                        "first_visible_content_rendered": 1,
                        "done_rendered": 1,
                        "surface_render_failed": 0,
                        "first_render_coverage_ratio": 1.0,
                        "done_render_coverage_ratio": 1.0,
                    }
                ]
            },
            "providers": {"error_rates": {}},
        },
    )

    async def fake_run_arr(**kwargs):
        assert kwargs["mode"] == "lite"
        assert kwargs["api_base_url"] == "http://127.0.0.1:8001"
        return {
            "run_id": "arr-lite-1",
            "mode": "lite",
            "release": {
                "release_id": "rel-1",
                "git_sha": "abc123",
                "deployment_environment": "dev",
                "prompt_version": "prompt-v1",
                "ff_snapshot_hash": "ff-1",
            },
            "suite_summaries": [],
            "case_results": [],
            "summary": {
                "total_cases": 3,
                "executed_cases": 3,
                "passed": 3,
                "failed": 0,
                "skipped": 0,
                "pass_rate": 1.0,
                "gate_stable_pass_rate": 1.0,
                "regression_tier_failed": 0,
            },
            "baseline_diff": {"regressions": [], "new_failures": [], "recovered": []},
            "gate_summary": {"bootstrap_mode": True, "gate_stable_pass_rate": 1.0, "regression_tier_failed": 0},
        }

    monkeypatch.setattr("deeptutor.services.observability.prerelease_runner.run_arr", fake_run_arr)
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.write_arr_artifacts",
        lambda payload, output_dir=None: {
            "json_path": str((Path(output_dir) if output_dir else tmp_path) / "arr.json"),
            "md_path": str((Path(output_dir) if output_dir else tmp_path) / "arr.md"),
        },
    )

    result = run_prerelease_observability(
        api_base_url="http://127.0.0.1:8001",
        arr_mode="lite",
        ws_smoke_message="请回复 ok",
        surface_smoke="web",
        output_dir=tmp_path / "artifacts",
    )

    assert result["ws_smoke"]["passed"] is True
    assert result["surface_smoke"]["passed"] is True
    assert result["runs"]["om"]["run_id"].startswith("om-")
    assert result["runs"]["arr"]["run_id"] == "arr-lite-1"
    assert result["runs"]["aae"]["source_arr_run_id"] == "arr-lite-1"
    assert result["runs"]["oa"]["mode"] == "pre-release"
    assert result["runs"]["release_gate"]["final_status"] in {"PASS", "WARN"}
    assert result["artifacts"]["arr"]["json_path"].endswith("arr.json")
