from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from deeptutor.services.observability import (
    get_control_plane_store,
    reset_control_plane_store,
    reset_turn_event_log,
)
from deeptutor.services.observability import prerelease_runner as prerelease_module
from deeptutor.services.observability.prerelease_runner import (
    load_metrics_snapshot,
    run_prerelease_observability,
)


def test_run_prerelease_observability_runs_pipeline_and_persists_outputs(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    reset_turn_event_log(events_dir=tmp_path / "events")
    monkeypatch.setenv("DEEPTUTOR_UNIFIED_WS_SMOKE_TOKEN", "eval-token")
    release = {
        "release_id": "rel-1",
        "service_version": "1.0.0",
        "git_sha": "abc123",
        "deployment_environment": "staging",
        "prompt_version": "prompt-v1",
        "ff_snapshot_hash": "ff-1",
        "git_dirty": "false",
        "deploy_manifest_hash": "a" * 64,
    }
    monkeypatch.setattr(prerelease_module, "get_release_lineage_snapshot", lambda: dict(release))
    monkeypatch.setattr(
        prerelease_module,
        "resolve_governed_metrics_urls",
        lambda: ("https://runtime.example/metrics",),
    )

    async def fake_verify_eval_runner_identity(**_kwargs):
        return {"verified": True, "reason": "verified"}

    monkeypatch.setattr(prerelease_module, "verify_eval_runner_identity", fake_verify_eval_runner_identity)

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
        lambda **kwargs: (
            {
                "run_id": "surface-smoke-1",
                "passed": True,
                "surface": kwargs["surface"],
                "coverage": {"first_render_coverage_ratio": 1.0, "done_render_coverage_ratio": 1.0},
                "posted_events": [],
                "missing_requirements": [],
            }
            if kwargs.get("metrics_token") == "metrics-secret"
            else pytest.fail("surface smoke did not receive metrics token")
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.load_metrics_snapshot",
        lambda **kwargs: (
            {
                "release": {
                    "release_id": "rel-1",
                    "service_version": "1.0.0",
                    "git_sha": "abc123",
                    "deployment_environment": "staging",
                    "prompt_version": "prompt-v1",
                    "ff_snapshot_hash": "ff-1",
                    "git_dirty": "false",
                    "deploy_manifest_hash": "a" * 64,
                },
                "observability_metrics_provenance": {
                    "source": "live_metrics_endpoint",
                    "fallback_used": False,
                    "status_code": 200,
                    "url": "https://runtime.example/metrics",
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
            }
            if kwargs.get("metrics_token") == "metrics-secret"
            else pytest.fail("metrics snapshot did not receive metrics token")
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.collect_git_changed_files",
        lambda: pytest.fail("explicit changed_files should bypass git collection"),
    )

    async def fake_run_arr(**kwargs):
        assert kwargs["mode"] == "lite"
        assert kwargs["api_base_url"] == "https://runtime.example"
        return {
            "run_id": "arr-lite-1",
            "mode": "lite",
            "release": {
                "release_id": "rel-1",
                "service_version": "1.0.0",
                "git_sha": "abc123",
                "deployment_environment": "staging",
                "prompt_version": "prompt-v1",
                "ff_snapshot_hash": "ff-1",
                "git_dirty": "false",
                "deploy_manifest_hash": "a" * 64,
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
    async def fake_load_live_feedback():
        return {
            "window_days": 7,
            "storage_status": "ok",
            "summary": {
                "total_feedback": 2,
                "thumbs_up": 1,
                "neutral": 0,
                "thumbs_down": 1,
            },
            "top_reason_tags": [],
            "recent": [],
        }

    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner._load_live_feedback",
        fake_load_live_feedback,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.write_arr_artifacts",
        lambda payload, output_dir=None: {
            "json_path": str((Path(output_dir) if output_dir else tmp_path) / "arr.json"),
            "md_path": str((Path(output_dir) if output_dir else tmp_path) / "arr.md"),
        },
    )
    original_build_observer_snapshot = prerelease_module.build_observer_snapshot
    original_build_oa_run = prerelease_module.build_oa_run
    built_observer_payload = {}

    def spy_build_observer_snapshot(**kwargs):
        payload = original_build_observer_snapshot(**kwargs)
        built_observer_payload["payload"] = payload
        return payload

    def spy_build_oa_run(**kwargs):
        observer_payload = kwargs.get("observer_payload")
        change_impact_payload = kwargs.get("change_impact_payload")
        assert observer_payload is built_observer_payload["payload"]
        assert change_impact_payload["run_id"].startswith("change-impact-")
        return original_build_oa_run(**kwargs)

    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.build_observer_snapshot",
        spy_build_observer_snapshot,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.prerelease_runner.build_oa_run",
        spy_build_oa_run,
    )

    result = run_prerelease_observability(
        api_base_url="https://runtime.example",
        arr_mode="lite",
        ws_smoke_message="请回复 ok",
        surface_smoke="web",
        metrics_token="metrics-secret",
        output_dir=tmp_path / "artifacts",
        changed_files=["docs/zh/guide/observability-control-plane.md"],
    )

    assert result["ws_smoke"]["passed"] is True
    assert result["surface_smoke"]["passed"] is True
    assert result["runs"]["om"]["run_id"].startswith("om-")
    assert result["runs"]["arr"]["run_id"] == "arr-lite-1"
    assert result["runs"]["aae"]["source_arr_run_id"] == "arr-lite-1"
    assert result["runs"]["aae"]["scorecard"]["paid_student_satisfaction_score"]["source"] == "supabase_ai_feedback"
    assert result["runs"]["aae"]["scorecard"]["paid_student_satisfaction_score"]["is_proxy"] is False
    assert result["runs"]["feedback"]["summary"]["total_feedback"] == 2
    assert result["runs"]["observer_snapshot"]["run_id"].startswith("observer-snapshot-")
    assert result["runs"]["observer_snapshot"]["source_runs"]["arr_run_id"] == "arr-lite-1"
    assert result["runs"]["change_impact"]["run_id"].startswith("change-impact-")
    assert result["runs"]["change_impact"] == get_control_plane_store().latest_payload("change_impact_runs")
    assert result["runs"]["oa"]["mode"] == "pre-release"
    assert result["runs"]["oa"]["raw_evidence_bundle"]["observer_snapshot_run_id"] == result["runs"][
        "observer_snapshot"
    ]["run_id"]
    assert result["runs"]["oa"]["raw_evidence_bundle"]["change_impact_run_id"] == result["runs"][
        "change_impact"
    ]["run_id"]
    assert result["runs"]["release_gate"]["final_status"] == "FAIL"
    assert "plan_completion_audit_missing" in result["runs"]["release_gate"]["blockers"]
    assert get_control_plane_store().latest_payload("plan_completion_audits") is None
    assert result["artifacts"]["arr"]["json_path"].endswith("arr.json")
    assert result["artifacts"]["observer_snapshot"]["json_path"].endswith("raw_data_latest.json")
    assert result["artifacts"]["change_impact"]["json_path"].endswith(".json")


def test_prerelease_blocks_before_synthetic_or_store_on_ungoverned_runtime(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    local_release = {
        "release_id": "rel-local",
        "service_version": "1.0.0",
        "git_sha": "abc123",
        "deployment_environment": "local",
        "prompt_version": "prompt-v1",
        "ff_snapshot_hash": "ff-1",
        "git_dirty": "false",
        "deploy_manifest_hash": "local-manifest",
    }
    monkeypatch.setattr(prerelease_module, "get_release_lineage_snapshot", lambda: dict(local_release))
    monkeypatch.setattr(
        prerelease_module,
        "resolve_governed_metrics_urls",
        lambda: ("https://runtime.example/metrics",),
    )
    monkeypatch.setattr(
        prerelease_module,
        "load_metrics_snapshot",
        lambda **_kwargs: {
            "release": dict(local_release),
            "observability_metrics_provenance": {
                "source": "live_metrics_endpoint",
                "fallback_used": False,
                "status_code": 200,
                "url": "https://runtime.example/metrics",
            },
        },
    )
    monkeypatch.setattr(
        prerelease_module,
        "run_unified_ws_smoke",
        lambda **_kwargs: pytest.fail("WS smoke ran before runtime authority PASS"),
    )
    monkeypatch.setattr(
        prerelease_module,
        "run_surface_ack_smoke",
        lambda **_kwargs: pytest.fail("surface smoke ran before runtime authority PASS"),
    )

    with pytest.raises(RuntimeError, match="runtime_authority_blocked"):
        run_prerelease_observability(
            api_base_url="https://runtime.example",
            ws_smoke_message="should not run",
            surface_smoke="web",
            output_dir=tmp_path / "artifacts",
        )

    assert get_control_plane_store().list_runs("om_runs") == []


def test_prerelease_preserves_blocked_preflight_when_metrics_are_unavailable(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    monkeypatch.setattr(
        prerelease_module,
        "load_metrics_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError("refused")),
    )
    monkeypatch.setattr(
        prerelease_module,
        "run_unified_ws_smoke",
        lambda **_kwargs: pytest.fail("WS smoke ran before metrics preflight"),
    )

    output_dir = tmp_path / "artifacts"
    with pytest.raises(RuntimeError, match="runtime_authority_blocked"):
        run_prerelease_observability(
            api_base_url="http://127.0.0.1:8001",
            ws_smoke_message="should not run",
            output_dir=output_dir,
        )

    preflight = json.loads((output_dir / "runtime_authority_preflight.json").read_text(encoding="utf-8"))
    assert preflight["status"] == "BLOCKED"
    assert preflight["metrics_provenance"]["error_type"] == "ConnectionRefusedError"
    assert get_control_plane_store().list_runs("om_runs") == []


def test_prerelease_blocks_promotion_when_runtime_rolls_after_preflight(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    release = {
        "release_id": "rel-1",
        "service_version": "1.0.0",
        "git_sha": "abc123",
        "deployment_environment": "staging",
        "prompt_version": "prompt-v1",
        "ff_snapshot_hash": "ff-1",
        "git_dirty": "false",
        "deploy_manifest_hash": "a" * 64,
    }
    foreign_release = {**release, "ff_snapshot_hash": "foreign"}
    monkeypatch.setattr(
        prerelease_module,
        "resolve_governed_metrics_urls",
        lambda: ("https://runtime.example/metrics",),
    )
    snapshots = iter(
        [
            {
                "release": release,
                "observability_metrics_provenance": {
                    "source": "live_metrics_endpoint",
                    "fallback_used": False,
                    "status_code": 200,
                    "url": "https://runtime.example/metrics",
                },
            },
            {
                "release": foreign_release,
                "observability_metrics_provenance": {
                    "source": "live_metrics_endpoint",
                    "fallback_used": False,
                    "status_code": 200,
                    "url": "https://runtime.example/metrics",
                },
            },
        ]
    )
    monkeypatch.setattr(prerelease_module, "get_release_lineage_snapshot", lambda: dict(release))
    monkeypatch.setattr(prerelease_module, "load_metrics_snapshot", lambda **_kwargs: next(snapshots))

    output_dir = tmp_path / "artifacts"
    with pytest.raises(RuntimeError, match="runtime_authority_postflight_blocked"):
        run_prerelease_observability(
            api_base_url="https://runtime.example",
            output_dir=output_dir,
        )

    postflight = json.loads((output_dir / "runtime_authority_postflight.json").read_text(encoding="utf-8"))
    assert postflight["mismatched_fields"] == ["ff_snapshot_hash"]
    assert get_control_plane_store().list_runs("om_runs") == []


def test_load_metrics_snapshot_rejects_non_object_json(tmp_path) -> None:
    target = tmp_path / "metrics.json"
    target.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(TypeError, match="Metrics snapshot must be a JSON object"):
        load_metrics_snapshot(api_base_url="http://127.0.0.1:8001", metrics_json=str(target))


def test_load_metrics_snapshot_sends_metrics_token(monkeypatch) -> None:
    seen_token = None
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_token
        seen_token = request.headers.get("X-Metrics-Token")
        return httpx.Response(200, json={"readiness": {"ready": True}})

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: original_client(transport=httpx.MockTransport(handler)))

    payload = load_metrics_snapshot(
        api_base_url="http://127.0.0.1:8001",
        metrics_token="metrics-secret",
    )

    assert payload["readiness"]["ready"] is True
    assert seen_token == "metrics-secret"
