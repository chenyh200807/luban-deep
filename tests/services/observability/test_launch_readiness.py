from __future__ import annotations

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.launch_readiness import build_launch_readiness_dashboard
from deeptutor.services.observability.launch_readiness import build_launch_readiness_run


def _write_check(
    store: ObservabilityControlPlaneStore,
    check_id: str,
    status: str = "PASS",
    *,
    release: dict | None = None,
) -> None:
    release_payload = release or {
        "release_id": "rel-1",
        "git_sha": "abc123",
        "deployment_environment": "production",
    }
    run_id = f"{check_id}-{release_payload.get('release_id') or 'rel-1'}"
    store.write_run(
        kind="readiness_checks",
        run_id=run_id,
        release_id=str(release_payload.get("release_id") or "rel-1"),
        payload={
            "run_id": run_id,
            "check_id": check_id,
            "status": status,
            "summary": f"{check_id} completed",
            "evidence": [f"{check_id}=ok"],
            "release": release_payload,
        },
    )


def test_launch_readiness_dashboard_blocks_when_required_evidence_is_missing(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")

    payload = build_launch_readiness_dashboard(store=store)

    assert payload["final_status"] == "FAIL"
    assert payload["recommendation"] == "hold"
    assert "contract_guard_missing" in set(payload["blockers"])
    assert "playwright_missing" not in set(payload["blockers"])
    assert "wechat_devtools_missing" not in set(payload["blockers"])
    assert any(row["check_id"] == "release_gate" and row["status"] == "NOT_RUN" for row in payload["rows"])


def test_launch_readiness_dashboard_merges_release_gate_manual_checks_and_langfuse(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    release = {
        "release_id": "rel-1",
        "git_sha": "abc123",
        "deployment_environment": "production",
    }
    store.write_run(
        kind="release_gate_runs",
        run_id="release-gate-1",
        release_id="rel-1",
        payload={
            "run_id": "release-gate-1",
            "release": release,
            "final_status": "PASS",
            "recommendation": "canary",
            "gate_results": [
                {"gate": "P2 Benchmark Regression", "status": "PASS", "summary": "benchmark clear"},
                {"gate": "P3 AAE", "status": "PASS", "summary": "AAE clear"},
                {"gate": "P4 Blind Spot Budget", "status": "PASS", "summary": "blind spots clear"},
            ],
            "blockers": [],
        },
    )
    for check_id in ("contract_guard", "playwright", "wechat_devtools"):
        _write_check(store, check_id)
    store.write_run(
        kind="observer_snapshots",
        run_id="observer-1",
        release_id="rel-1",
        payload={
            "run_id": "observer-1",
            "release": release,
            "langfuse_trace_linkage": {
                "trace_id_count": 3,
                "langfuse_host": "https://langfuse.example.com",
            },
            "data_sources": {
                "langfuse_trace_linkage": {
                    "has_data": True,
                    "sample_count": 3,
                    "freshness": "fresh",
                }
            },
        },
    )

    payload = build_launch_readiness_dashboard(store=store)

    assert payload["final_status"] == "PASS"
    assert payload["recommendation"] == "canary"
    rows = {row["check_id"]: row for row in payload["rows"]}
    assert rows["release_gate"]["status"] == "PASS"
    assert rows["contract_guard"]["status"] == "PASS"
    assert rows["benchmark"]["status"] == "PASS"
    assert rows["oa_arr_aae"]["status"] == "PASS"
    assert rows["playwright"]["status"] == "PASS"
    assert rows["wechat_devtools"]["status"] == "PASS"
    assert rows["langfuse"]["status"] == "PASS"


def test_launch_readiness_rejects_stale_manual_and_langfuse_evidence(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-2",
        "git_sha": "git-b",
        "deployment_environment": "production",
    }
    old_release = {
        "release_id": "rel-1",
        "git_sha": "git-a",
        "deployment_environment": "production",
    }
    store.write_run(
        kind="release_gate_runs",
        run_id="release-gate-current",
        release_id="rel-2",
        payload={
            "run_id": "release-gate-current",
            "release": current_release,
            "final_status": "PASS",
            "recommendation": "canary",
            "gate_results": [
                {"gate": "P2 Benchmark Regression", "status": "PASS", "summary": "benchmark clear"},
                {"gate": "P3 AAE", "status": "PASS", "summary": "AAE clear"},
                {"gate": "P4 Blind Spot Budget", "status": "PASS", "summary": "blind spots clear"},
            ],
            "blockers": [],
        },
    )
    for check_id in ("contract_guard", "playwright", "wechat_devtools"):
        _write_check(store, check_id, release=old_release)
    store.write_run(
        kind="observer_snapshots",
        run_id="observer-old",
        release_id="rel-1",
        payload={
            "run_id": "observer-old",
            "release": old_release,
            "langfuse_trace_linkage": {"trace_id_count": 3},
            "data_sources": {"langfuse_trace_linkage": {"has_data": True, "sample_count": 3}},
        },
    )

    payload = build_launch_readiness_dashboard(store=store)
    rows = {row["check_id"]: row for row in payload["rows"]}

    assert payload["final_status"] == "FAIL"
    assert payload["recommendation"] == "hold"
    assert rows["contract_guard"]["status"] == "FAIL"
    assert rows["wechat_devtools"]["status"] == "WARN"
    assert rows["langfuse"]["status"] == "FAIL"
    assert "contract_guard_stale_release" in payload["blockers"]
    assert "wechat_devtools_stale_release" not in payload["blockers"]
    assert "langfuse_stale_release" in payload["blockers"]
    assert payload["source_runs"]["observer_snapshot_run_id"] is None


def test_launch_readiness_prefers_current_release_manual_check_over_newer_stale_record(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-2",
        "git_sha": "git-b",
        "deployment_environment": "production",
    }
    old_release = {
        "release_id": "rel-1",
        "git_sha": "git-a",
        "deployment_environment": "production",
    }
    store.write_run(
        kind="release_gate_runs",
        run_id="release-gate-current",
        release_id="rel-2",
        payload={
            "run_id": "release-gate-current",
            "release": current_release,
            "final_status": "PASS",
            "recommendation": "canary",
            "gate_results": [],
            "blockers": [],
        },
    )
    _write_check(store, "contract_guard", release=current_release)
    _write_check(store, "contract_guard", release=old_release)

    payload = build_launch_readiness_dashboard(store=store)
    rows = {row["check_id"]: row for row in payload["rows"]}

    assert rows["contract_guard"]["status"] == "PASS"
    assert rows["contract_guard"]["run_id"] == "contract_guard-rel-2"
    assert "contract_guard_stale_release" not in payload["blockers"]


def test_launch_readiness_rejects_same_git_different_deploy_manifest(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-2",
        "git_sha": "git-shared",
        "deployment_environment": "production",
        "prompt_version": "prompt-v1",
        "ff_snapshot_hash": "ff-current",
        "deploy_manifest_hash": "manifest-current",
    }
    old_release = {
        "release_id": "rel-1",
        "git_sha": "git-shared",
        "deployment_environment": "production",
        "prompt_version": "prompt-v1",
        "ff_snapshot_hash": "ff-current",
        "deploy_manifest_hash": "manifest-old",
    }
    store.write_run(
        kind="release_gate_runs",
        run_id="release-gate-current",
        release_id="rel-2",
        payload={
            "run_id": "release-gate-current",
            "release": current_release,
            "final_status": "PASS",
            "recommendation": "canary",
            "gate_results": [],
            "blockers": [],
        },
    )
    _write_check(store, "contract_guard", release=old_release)

    payload = build_launch_readiness_dashboard(store=store)
    rows = {row["check_id"]: row for row in payload["rows"]}

    assert rows["contract_guard"]["status"] == "FAIL"
    assert "contract_guard_stale_release" in payload["blockers"]


def test_launch_readiness_uses_release_gate_as_source_for_gate_rows(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-2",
        "git_sha": "git-b",
        "deployment_environment": "production",
    }
    old_release = {
        "release_id": "rel-1",
        "git_sha": "git-a",
        "deployment_environment": "production",
    }
    store.write_run(
        kind="release_gate_runs",
        run_id="release-gate-current",
        release_id="rel-2",
        payload={
            "run_id": "release-gate-current",
            "release": current_release,
            "final_status": "PASS",
            "recommendation": "canary",
            "gate_results": [
                {"gate": "P2 Benchmark Regression", "status": "PASS", "summary": "benchmark clear"},
                {"gate": "P3 AAE", "status": "PASS", "summary": "AAE clear"},
                {"gate": "P4 Blind Spot Budget", "status": "PASS", "summary": "blind spots clear"},
            ],
            "blockers": [],
        },
    )
    store.write_run(
        kind="arr_runs",
        run_id="arr-old",
        release_id="rel-1",
        payload={"run_id": "arr-old", "release": old_release, "summary": {"failed": 0, "pass_rate": 1.0}},
    )
    store.write_run(
        kind="oa_runs",
        run_id="oa-old",
        release_id="rel-1",
        payload={"run_id": "oa-old", "release": old_release, "blind_spots": [], "root_causes": []},
    )
    for check_id in ("contract_guard", "playwright", "wechat_devtools"):
        _write_check(store, check_id, release=current_release)
    store.write_run(
        kind="observer_snapshots",
        run_id="observer-current",
        release_id="rel-2",
        payload={
            "run_id": "observer-current",
            "release": current_release,
            "langfuse_trace_linkage": {"trace_id_count": 3},
            "data_sources": {"langfuse_trace_linkage": {"has_data": True, "sample_count": 3}},
        },
    )

    payload = build_launch_readiness_dashboard(store=store)
    rows = {row["check_id"]: row for row in payload["rows"]}

    assert rows["benchmark"]["run_id"] == "release-gate-current"
    assert rows["oa_arr_aae"]["run_id"] == "release-gate-current"
    assert payload["source_runs"]["arr_run_id"] is None
    assert payload["source_runs"]["oa_run_id"] is None


def test_build_launch_readiness_run_records_readyz_state() -> None:
    payload = build_launch_readiness_run(
        checks={
            "config_consistent": True,
            "llm_client_ready": True,
            "event_bus_ready": False,
        },
        release={
            "release_id": "rel-1",
            "git_sha": "abc123",
            "deployment_environment": "local",
        },
    )

    assert payload["check_id"] == "launch_readiness"
    assert payload["status"] == "FAIL"
    assert any("event_bus_ready=False" in item for item in payload["evidence"])
