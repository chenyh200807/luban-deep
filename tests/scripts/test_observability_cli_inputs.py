from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from deeptutor.services.observability.control_plane_store import get_control_plane_store
from deeptutor.services.observability.control_plane_store import reset_control_plane_store


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AAE_MODULE = _load_script_module("run_aae_snapshot.py")
OA_MODULE = _load_script_module("run_oa.py")
RELEASE_GATE_MODULE = _load_script_module("run_release_gate.py")
ARR_LITE_MODULE = _load_script_module("run_arr_lite.py")
PRERELEASE_MODULE = _load_script_module("run_prerelease_observability.py")
OBSERVER_SNAPSHOT_MODULE = _load_script_module("run_observer_snapshot.py")
CHANGE_IMPACT_MODULE = _load_script_module("run_change_impact.py")
DAILY_OBSERVABILITY_MODULE = _load_script_module("run_observability_daily.py")
PLAN_COMPLETION_MODULE = _load_script_module("run_plan_completion_audit.py")
READINESS_CHECK_MODULE = _load_script_module("run_readiness_check.py")
BENCHMARK_MODULE = _load_script_module("run_benchmark.py")


def test_run_aae_snapshot_load_json_accepts_control_plane_wrapper(tmp_path) -> None:
    payload = {"run_id": "arr-full-1", "summary": {"pass_rate": 0.7}}
    wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-full-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "arr-control-plane.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert AAE_MODULE._load_json(str(target), expected_kind="arr_runs") == payload


def test_run_oa_load_json_accepts_raw_payload(tmp_path) -> None:
    payload = {"run_id": "oa-1", "blind_spots": [], "root_causes": []}
    target = tmp_path / "oa-raw.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert OA_MODULE._load_json(str(target), expected_kind="oa_runs") == payload


def test_daily_observability_uses_explicit_ws_smoke_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_UNIFIED_WS_SMOKE_TOKEN", "smoke-token")

    assert (
        DAILY_OBSERVABILITY_MODULE._resolve_unified_ws_smoke_token(api_base_url="http://127.0.0.1:8001")
        == "smoke-token"
    )


def test_daily_observability_issues_local_canonical_ws_smoke_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_UNIFIED_WS_SMOKE_TOKEN", raising=False)
    monkeypatch.delenv("DEEPTUTOR_WS_SMOKE_TOKEN", raising=False)

    class _Service:
        def _issue_access_token(self, **kwargs):
            assert kwargs["user_id"] == "student_demo"
            assert kwargs["canonical_uid"] == "student_demo"
            assert kwargs["ttl_seconds"] == 300
            return "signed-token"

    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: _Service(),
    )

    assert (
        DAILY_OBSERVABILITY_MODULE._resolve_unified_ws_smoke_token(api_base_url="http://127.0.0.1:8001")
        == "signed-token"
    )


def test_daily_observability_defers_ws_smoke_when_target_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_connection_refused(**_kwargs):
        raise ConnectionRefusedError("connect call failed")

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "run_unified_ws_smoke", _raise_connection_refused)

    payload = DAILY_OBSERVABILITY_MODULE._run_unified_ws_smoke_check(
        api_base_url="http://127.0.0.1:18002",
        timeout_seconds=1.0,
    )

    assert payload["ok"] is None
    assert payload["status"] == "DEFERRED"
    assert "target API service unavailable" in payload["summary"]
    assert "api_base_url=http://127.0.0.1:18002" in payload["evidence"]


def test_daily_observability_keeps_terminal_ws_errors_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_runtime_error(**_kwargs):
        raise RuntimeError("invalid api key")

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "run_unified_ws_smoke", _raise_runtime_error)

    payload = DAILY_OBSERVABILITY_MODULE._run_unified_ws_smoke_check(
        api_base_url="http://127.0.0.1:8001",
        timeout_seconds=1.0,
    )

    assert payload["ok"] is False
    assert payload["status"] == "FAIL"
    assert "RuntimeError" in payload["summary"]


def test_daily_observability_metrics_auth_failure_is_not_silently_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = DAILY_OBSERVABILITY_MODULE.httpx.Request("GET", "http://127.0.0.1:8001/metrics")
    response = DAILY_OBSERVABILITY_MODULE.httpx.Response(401, request=request)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "load_metrics_snapshot_shared",
        lambda **_kwargs: (_ for _ in ()).throw(
            DAILY_OBSERVABILITY_MODULE.httpx.HTTPStatusError(
                "401 Unauthorized",
                request=request,
                response=response,
            )
        ),
    )

    with pytest.raises(RuntimeError, match="metrics endpoint auth blocked"):
        DAILY_OBSERVABILITY_MODULE._load_metrics_snapshot(
            api_base_url="http://127.0.0.1:8001",
            metrics_json=None,
            metrics_token=None,
        )


def test_run_observability_daily_passes_frozen_window_and_smoke_exclusions(monkeypatch, tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-current",
        "git_sha": "sha-current",
        "deployment_environment": "dev",
        "prompt_version": "p-current",
        "ff_snapshot_hash": "ff-current",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: DAILY_OBSERVABILITY_MODULE.argparse.Namespace(
            base_ref="origin/main",
            changed_file=[],
            metrics_json=None,
            api_base_url="http://127.0.0.1:8001",
            unified_ws_smoke_timeout=20.0,
            event_days=1,
            report_date="2026-06-16",
            timezone="Asia/Shanghai",
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "get_release_lineage_snapshot", lambda: dict(current_release))
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "collect_git_changed_files", lambda **_kwargs: ["scripts/run_observability_daily.py"])
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_om_payload",
        lambda **_kwargs: {
            "run_id": "om-1",
            "release": current_release,
            "metrics_snapshot": {"release": current_release},
            "health_summary": {"ready": True},
            "smoke_checks": [{"name": "unified_ws_smoke", "session_ids": ["session-smoke"]}],
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_arr_payload",
        lambda **_kwargs: {"run_id": "arr-1", "release": current_release, "summary": {"pass_rate": 1.0}},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_benchmark_payload",
        lambda **_kwargs: {"run_manifest": {"run_id": "bench-1"}, "summary": {"pass_rate": 1.0}},
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_surface_readiness_rows", lambda **_kwargs: None)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_aae_payload",
        lambda **_kwargs: {"run_id": "aae-1", "release": current_release, "scorecard": {}},
    )

    def _fake_build_observer_snapshot(**kwargs):
        captured["observer_kwargs"] = kwargs
        return {
            "run_id": "observer-1",
            "release": current_release,
            "window": {
                "report_date": kwargs["report_date"],
                "timezone": kwargs["timezone"],
                "start_ts": kwargs["start_ts"],
                "end_ts": kwargs["end_ts"],
                "excluded_session_ids": sorted(kwargs["exclude_session_ids"]),
            },
        }

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_observer_snapshot", _fake_build_observer_snapshot)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "write_observer_snapshot_artifacts",
        lambda *_args, **_kwargs: {"json_path": str(tmp_path / "observer.json")},
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_write_contract_guard_readiness", lambda **_kwargs: None)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_change_impact_run",
        lambda **_kwargs: {"run_id": "change-1", "release": current_release, "risk_level": "medium"},
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "render_change_impact_markdown", lambda _payload: "# change")
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_oa_run",
        lambda **_kwargs: {
            "run_id": "oa-1",
            "release": current_release,
            "verdict": "TRUSTED",
            "root_causes": [],
            "causal_candidates": [],
            "blind_spots": [],
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_plan_completion_payload",
        lambda **_kwargs: {"run_id": "plan-1", "release": current_release},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_current_release_readiness_matrix_payload",
        lambda **_kwargs: {"checks": []},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_release_gate_report",
        lambda **_kwargs: {
            "run_id": "gate-1",
            "release": current_release,
            "verdict": "TRUSTED",
            "final_status": "PASS",
            "recommendation": "go",
            "gate_results": [],
            "blockers": [],
        },
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_daily_run_history", lambda **_kwargs: {"items": []})

    DAILY_OBSERVABILITY_MODULE.main()

    observer_kwargs = captured["observer_kwargs"]
    assert observer_kwargs["report_date"] == "2026-06-16"
    assert observer_kwargs["timezone"] == "Asia/Shanghai"
    assert observer_kwargs["exclude_session_ids"] == {"session-smoke"}
    assert observer_kwargs["start_ts"] < observer_kwargs["end_ts"]


def test_daily_observability_missing_surface_readiness_rows_are_evidence_gaps(tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    store = get_control_plane_store()
    release = {
        "release_id": "rel-current",
        "git_sha": "sha-current",
        "deployment_environment": "local",
        "prompt_version": "p-current",
        "ff_snapshot_hash": "ff-current",
    }

    DAILY_OBSERVABILITY_MODULE._ensure_surface_readiness_rows(
        store=store,
        release=release,
        changed_files=["web/app/page.tsx", "yousenwebview/project.config.json"],
        required_checks={"playwright", "wechat_devtools"},
    )

    records = store.list_runs("readiness_checks", limit=10)
    rows = {
        str((record.get("payload") or {}).get("check_id")): record.get("payload")
        for record in records
    }
    assert rows["playwright"]["status"] == "FAIL"
    assert rows["playwright"]["blockers"] == ["playwright_evidence_missing"]
    assert "reason=no current-release readiness row existed" in rows["playwright"]["evidence"]
    assert rows["wechat_devtools"]["status"] == "FAIL"
    assert rows["wechat_devtools"]["blockers"] == ["wechat_devtools_true_entry_pending"]
    assert "boundary=islogin/open are preflight until page scenario or automator evidence exists" in rows["wechat_devtools"]["evidence"]


def test_daily_observability_marks_surface_readiness_not_required_for_non_surface_scope(tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    store = get_control_plane_store()
    release = {
        "release_id": "rel-current",
        "git_sha": "sha-current",
        "deployment_environment": "local",
        "prompt_version": "p-current",
        "ff_snapshot_hash": "ff-current",
    }

    DAILY_OBSERVABILITY_MODULE._ensure_surface_readiness_rows(
        store=store,
        release=release,
        changed_files=["docs/plan/INDEX.md"],
        required_checks=set(),
    )

    records = store.list_runs("readiness_checks", limit=10)
    rows = {
        str((record.get("payload") or {}).get("check_id")): record.get("payload")
        for record in records
    }
    assert rows["playwright"]["status"] == "SKIP"
    assert rows["playwright"]["required"] is False
    assert rows["playwright"]["blockers"] == []
    assert rows["wechat_devtools"]["status"] == "SKIP"
    assert rows["wechat_devtools"]["required"] is False


def test_run_oa_load_json_accepts_observer_snapshot_wrapper(tmp_path) -> None:
    payload = {"run_id": "observer-snapshot-1", "turn_events": {"event_count": 1}}
    wrapper = {
        "kind": "observer_snapshots",
        "run_id": "observer-snapshot-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "observer-control-plane.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert OA_MODULE._load_json(str(target), expected_kind="observer_snapshots") == payload


def test_run_release_gate_load_json_accepts_control_plane_wrapper(tmp_path) -> None:
    payload = {"run_id": "oa-1", "gate_results": [], "blockers": []}
    wrapper = {
        "kind": "oa_runs",
        "run_id": "oa-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "oa-control-plane.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert RELEASE_GATE_MODULE._load_json(str(target), expected_kind="oa_runs") == payload


def test_run_release_gate_load_json_accepts_plan_completion_wrapper(tmp_path) -> None:
    payload = {"run_id": "plan-completion-1", "status": "FAIL", "summary": {"not_done": 1}}
    wrapper = {
        "kind": "plan_completion_audits",
        "run_id": "plan-completion-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "plan-completion.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert RELEASE_GATE_MODULE._load_json(str(target), expected_kind="plan_completion_audits") == payload


def test_run_release_gate_load_json_accepts_incident_wrapper(tmp_path) -> None:
    payload = {"run_manifest": {"run_id": "incident-replay-1"}, "runtime_incidents": []}
    wrapper = {
        "kind": "incident_ledger",
        "run_id": "incident-replay-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "incident.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert RELEASE_GATE_MODULE._load_json(str(target), expected_kind="incident_ledger") == payload


def test_run_release_gate_report_only_preserves_explicit_plan_completion_json(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-current",
        "git_sha": "abc123",
        "deployment_environment": "eval",
        "prompt_version": "prompt-current",
        "ff_snapshot_hash": "ff-current",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-current",
    }
    explicit_payload = {
        "run_id": "plan-completion-explicit",
        "release": {"release_id": "rel-explicit", "git_sha": "oldsha"},
        "scope_mode": "report_only",
        "status": "WARN",
        "summary": {"total": 0},
        "warnings": ["plan_completion_report_only_placeholder"],
    }
    target = tmp_path / "plan-completion.json"
    target.write_text(
        json.dumps(
            {
                "kind": "plan_completion_audits",
                "run_id": "plan-completion-explicit",
                "release_id": "rel-explicit",
                "recorded_at": 1,
                "payload": explicit_payload,
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def _fail_if_auto_placeholder(**kwargs):
        raise AssertionError("explicit plan completion JSON must not be replaced")

    def _fake_build_release_gate_report(**kwargs):
        captured["plan_completion_payload"] = kwargs["plan_completion_payload"]
        return {
            "run_id": "release-gate-test",
            "release": current_release,
            "final_status": "WARN",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": [],
        }

    monkeypatch.setattr(RELEASE_GATE_MODULE, "get_release_lineage_snapshot", lambda: dict(current_release))
    monkeypatch.setattr(RELEASE_GATE_MODULE, "_ensure_report_only_plan_completion_payload", _fail_if_auto_placeholder)
    monkeypatch.setattr(RELEASE_GATE_MODULE, "build_release_gate_report", _fake_build_release_gate_report)
    monkeypatch.setattr(sys, "argv", ["run_release_gate.py", "--report-only", "--plan-completion-json", str(target)])

    RELEASE_GATE_MODULE.main()

    assert captured["plan_completion_payload"] == explicit_payload


def test_run_release_gate_report_only_ignores_stale_incident_latest(tmp_path, monkeypatch) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-current",
        "git_sha": "abc123",
        "deployment_environment": "local",
        "prompt_version": "prompt-current",
        "ff_snapshot_hash": "ff-current",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-current",
    }
    old_release = {
        "release_id": "rel-old",
        "git_sha": "oldsha",
        "deployment_environment": "local",
        "prompt_version": "prompt-old",
        "ff_snapshot_hash": "ff-old",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-old",
    }
    incident_dir = tmp_path / "control_plane" / "incident_ledger"
    incident_dir.mkdir(parents=True, exist_ok=True)
    (incident_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "incident_ledger",
                "run_id": "incident-old",
                "release_id": "rel-old",
                "recorded_at": 1,
                "payload": {
                    "run_manifest": {"run_id": "incident-old"},
                    "release_spine": old_release,
                    "runtime_incidents": [{"release_blocking": True}],
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def _fake_build_release_gate_report(**kwargs):
        captured["incident_payload"] = kwargs["incident_payload"]
        return {
            "run_id": "release-gate-test",
            "release": current_release,
            "final_status": "WARN",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": [],
            "stale_inputs": [],
        }

    monkeypatch.setattr(RELEASE_GATE_MODULE, "get_release_lineage_snapshot", lambda: dict(current_release))
    monkeypatch.setattr(RELEASE_GATE_MODULE, "build_release_gate_report", _fake_build_release_gate_report)
    monkeypatch.setattr(sys, "argv", ["run_release_gate.py", "--report-only"])

    RELEASE_GATE_MODULE.main()

    assert captured["incident_payload"] is None


def test_run_release_gate_store_fallback_rejects_malformed_latest_wrapper(tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    latest_path = tmp_path / "control_plane" / "oa_runs" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "kind": "oa_runs",
                "run_id": "oa-1",
                "recorded_at": 123,
                "payload": {"run_id": "oa-1"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing 'release_id'"):
        RELEASE_GATE_MODULE._load_store_payload("oa_runs")


def test_run_release_gate_store_fallback_skips_malformed_latest_wrapper(tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    kind_dir = tmp_path / "control_plane" / "oa_runs"
    kind_dir.mkdir(parents=True, exist_ok=True)
    (kind_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "oa_runs",
                "run_id": "oa-bad",
                "recorded_at": 456,
                "payload": {"run_id": "oa-bad"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (kind_dir / "oa-good.json").write_text(
        json.dumps(
            {
                "kind": "oa_runs",
                "run_id": "oa-good",
                "release_id": "rel-1",
                "recorded_at": 123,
                "payload": {"run_id": "oa-good", "root_causes": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert RELEASE_GATE_MODULE._load_store_payload("oa_runs") == {
        "run_id": "oa-good",
        "root_causes": [],
    }


def test_run_release_gate_cli_fails_closed_without_canary(monkeypatch, tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    monkeypatch.setattr(
        RELEASE_GATE_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: RELEASE_GATE_MODULE.argparse.Namespace(
            om_json=None,
            arr_json=None,
            aae_json=None,
            oa_json=None,
            incident_json=None,
            change_impact_json=None,
            plan_completion_json=None,
            report_only=False,
        ),
    )
    monkeypatch.setattr(RELEASE_GATE_MODULE, "_load_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(RELEASE_GATE_MODULE, "_load_store_payload", lambda _kind, **_kwargs: None)
    monkeypatch.setattr(
        RELEASE_GATE_MODULE,
        "build_release_gate_report",
        lambda **_kwargs: {
            "run_id": "release-gate-fail",
            "release": {"release_id": "rel-1"},
            "final_status": "FAIL",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": ["benchmark_gate_failure"],
        },
    )

    with pytest.raises(SystemExit, match="release_gate_failed: recommendation=hold"):
        RELEASE_GATE_MODULE.main()


def test_run_plan_completion_audit_cli_writes_control_plane_latest(tmp_path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    store_dir = tmp_path / "control_plane"
    plan.parent.mkdir(parents=True)
    plan.write_text("- [ ] Create: `scripts/run_ws_capacity_probe.py`\n", encoding="utf-8")
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
        "DEEPTUTOR_ALLOW_METRICS_TESTCLIENT_FALLBACK": "1",
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_plan_completion_audit.py"),
            "--plan",
            str(plan),
            "--changed-file",
            "scripts/run_ws_capacity_probe.py",
            "--report-only",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "plan_completion_audits" / "latest.json").read_text(encoding="utf-8"))
    assert latest["kind"] == "plan_completion_audits"
    assert latest["payload"]["status"] == "PASS"


def test_run_readiness_check_cli_records_command_result(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
        "DEEPTUTOR_ALLOW_METRICS_TESTCLIENT_FALLBACK": "1",
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_readiness_check.py"),
            "--check-id",
            "playwright",
            "--summary",
            "playwright smoke passed",
            "--command",
            sys.executable,
            "-c",
            "print('ok')",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "readiness_checks" / "latest.json").read_text(encoding="utf-8"))
    assert latest["kind"] == "readiness_checks"
    assert latest["payload"]["view"] == "current_release_latest_matrix"
    row = next(item for item in latest["payload"]["rows"] if item["check_id"] == "playwright")
    assert row["status"] == "PASS"
    assert "playwright smoke passed" in row["summary"]
    assert any("exit_code=0" in item for item in row["evidence"])


def test_run_readiness_check_default_contract_guard_command() -> None:
    command = READINESS_CHECK_MODULE._default_command("contract_guard", ["docs/plan/INDEX.md"])

    assert command[-2:] == [str(Path(__file__).resolve().parents[2] / "scripts" / "check_contract_guard.py"), "docs/plan/INDEX.md"]


def test_run_readiness_check_default_wechat_devtools_command() -> None:
    command = READINESS_CHECK_MODULE._default_command("wechat_devtools", [])

    assert command == [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "scripts" / "run_wechat_devtools_daily_smoke.py"),
    ]


def test_run_readiness_check_preserves_real_wechat_project_root_fields() -> None:
    class _Result:
        stdout = json.dumps(
            {
                "readiness_status": "PASS",
                "entry_surface": "real_wechat_package",
                "devtools_project_root": "yousenwebview",
                "project_path": "/repo/yousenwebview",
                "target_subpackage": "packageDeeptutor",
                "target_page": "/packageDeeptutor/pages/report/report",
                "entry_flow": "direct_subpackage_page",
                "qa_base_url": "http://127.0.0.1:8001",
                "scenario_evidence_status": "passed",
            },
            ensure_ascii=False,
        )

    meta = READINESS_CHECK_MODULE._structured_readiness_metadata(
        check_id="wechat_devtools",
        result=_Result(),
    )

    assert meta["devtools_project_root"] == "yousenwebview"
    assert meta["target_subpackage"] == "packageDeeptutor"
    assert meta["target_page"] == "/packageDeeptutor/pages/report/report"
    assert meta["entry_flow"] == "direct_subpackage_page"
    assert meta["qa_base_url"] == "http://127.0.0.1:8001"


@pytest.mark.asyncio
async def test_run_arr_lite_cli_fails_closed_on_fail_or_skip(monkeypatch, tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    monkeypatch.setattr(
        ARR_LITE_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: ARR_LITE_MODULE.argparse.Namespace(
            mode="lite",
            output_dir=str(tmp_path / "arr"),
            baseline=None,
            long_dialog_source_json=None,
            max_long_dialog_cases=None,
            api_base_url="https://test2.yousenjiaoyu.com",
            response_mode="smart",
            report_only=False,
        ),
    )
    monkeypatch.setattr(ARR_LITE_MODULE, "load_arr_baseline_payload", lambda _path: None)

    async def _fake_run_arr(**_kwargs):
        return {
            "run_id": "arr-fail",
            "release": {"release_id": "rel-1"},
            "summary": {
                "passed": 1,
                "failed": 1,
                "skipped": 1,
                "pass_rate": 0.5,
                "gate_stable_pass_rate": 0.5,
                "regression_tier_failed": 1,
            },
            "baseline_diff": {},
        }

    monkeypatch.setattr(ARR_LITE_MODULE, "run_arr", _fake_run_arr)
    monkeypatch.setattr(
        ARR_LITE_MODULE,
        "write_arr_artifacts",
        lambda _payload, output_dir: {
            "json_path": str(output_dir / "arr.json"),
            "md_path": str(output_dir / "arr.md"),
            "html_path": str(output_dir / "arr.html"),
            "analysis_json_path": str(output_dir / "analysis.json"),
        },
    )
    monkeypatch.setattr(
        ARR_LITE_MODULE,
        "build_arr_report_payload",
        lambda _payload: {
            "latency_summary": {},
            "case_tier_distribution": [],
            "failure_type_distribution": [],
            "failures": [],
            "execution_context": {},
        },
    )

    with pytest.raises(SystemExit, match="arr_gate_failed: failed=1 skipped=1"):
        await ARR_LITE_MODULE.main()


def test_run_prerelease_observability_cli_fails_closed_without_canary(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        PRERELEASE_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: PRERELEASE_MODULE.argparse.Namespace(
            api_base_url="https://test2.yousenjiaoyu.com",
            arr_mode="lite",
            ws_smoke_message=None,
            surface_smoke=None,
            metrics_json=None,
            metrics_token=None,
            output_dir=str(tmp_path),
            long_dialog_source_json=None,
            long_dialog_max_cases=None,
            changed_files=None,
            report_only=False,
        ),
    )
    monkeypatch.setattr(
        PRERELEASE_MODULE,
        "run_prerelease_observability",
        lambda **_kwargs: {
            "runs": {
                "release_gate": {
                    "run_id": "release-gate-fail",
                    "final_status": "FAIL",
                    "recommendation": "hold",
                }
            },
            "artifacts": {},
        },
    )

    with pytest.raises(SystemExit, match="prerelease_gate_failed: recommendation=hold"):
        PRERELEASE_MODULE.main()


def test_run_observer_snapshot_load_json_accepts_metrics_raw_payload(tmp_path) -> None:
    payload = {"readiness": {"ready": True}, "turn_runtime": {"turns_started_total": 1}}
    target = tmp_path / "metrics.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert OBSERVER_SNAPSHOT_MODULE._load_json(str(target)) == payload


def test_run_change_impact_load_json_accepts_observer_snapshot_wrapper(tmp_path) -> None:
    payload = {"run_id": "observer-1", "turn_events": {"event_count": 1}}
    wrapper = {
        "kind": "observer_snapshots",
        "run_id": "observer-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "observer.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert CHANGE_IMPACT_MODULE._load_json(str(target), expected_kind="observer_snapshots") == payload


def test_observability_change_impact_scripts_default_to_previous_commit() -> None:
    assert CHANGE_IMPACT_MODULE.DEFAULT_BASE_REF == "HEAD~1"
    assert DAILY_OBSERVABILITY_MODULE.DEFAULT_BASE_REF == "HEAD~1"


def test_run_change_impact_cli_writes_control_plane_latest_and_history(tmp_path) -> None:
    observer_payload = {
        "run_id": "observer-1",
        "release": {"release_id": "rel-1"},
        "turn_events": {"event_count": 1, "error_ratio": 0.0},
        "blind_spots": [],
    }
    observer_wrapper = {
        "kind": "observer_snapshots",
        "run_id": "observer-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": observer_payload,
    }
    observer_path = tmp_path / "observer.json"
    observer_path.write_text(json.dumps(observer_wrapper, ensure_ascii=False), encoding="utf-8")
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_change_impact.py"),
            "--changed-file",
            "deeptutor/services/session/turn_runtime.py",
            "--observer-json",
            str(observer_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest_path = store_dir / "change_impact_runs" / "latest.json"
    history_path = store_dir / "change_impact_runs" / "history.jsonl"
    assert latest_path.exists()
    assert history_path.exists()
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["kind"] == "change_impact_runs"
    assert latest["release_id"] == "rel-1"
    assert latest["payload"]["changed_domains"][0]["domain"] == "turn"


def test_run_observability_daily_cli_writes_end_to_end_control_plane_runs(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    output_dir = tmp_path / "daily"
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "release": {
                    "release_id": "rel-1",
                    "git_sha": "abc",
                    "deployment_environment": "dev",
                },
                "turn_runtime": {
                    "turns_started_total": 1,
                    "turns_completed_total": 1,
                    "turns_failed_total": 0,
                    "turns_cancelled_total": 0,
                    "turns_in_flight": 0,
                    "ws_active_connections": 0,
                    "turn_avg_latency_ms": 250.0,
                },
                "surface_events": {"coverage": []},
                "readiness": {"ready": True},
                "providers": {"error_rates": {}, "circuit_breakers": {}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_observability_daily.py"),
            "--changed-file",
            "deeptutor/services/session/turn_runtime.py",
            "--metrics-json",
            str(metrics_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    for kind in (
        "arr_runs",
        "aae_composite_runs",
        "benchmark_runs",
        "observer_snapshots",
        "om_runs",
        "change_impact_runs",
        "oa_runs",
        "release_gate_runs",
        "daily_trends",
        "readiness_checks",
    ):
        assert (store_dir / kind / "latest.json").exists()

    oa_latest = json.loads((store_dir / "oa_runs" / "latest.json").read_text(encoding="utf-8"))
    assert oa_latest["payload"]["causal_candidates"]
    arr_latest = json.loads((store_dir / "arr_runs" / "latest.json").read_text(encoding="utf-8"))
    assert arr_latest["payload"]["benchmark_run_manifest"]["requested_suites"] == [
        "pr_gate_core",
        "regression_watch",
        "real_exam_quality_spine",
    ]
    aae_latest = json.loads((store_dir / "aae_composite_runs" / "latest.json").read_text(encoding="utf-8"))
    assert aae_latest["payload"]["source_arr_run_id"] == arr_latest["payload"]["run_id"]
    benchmark_latest = json.loads((store_dir / "benchmark_runs" / "latest.json").read_text(encoding="utf-8"))
    assert benchmark_latest["payload"]["run_manifest"]["requested_suites"] == [
        "pr_gate_core",
        "regression_watch",
        "real_exam_quality_spine",
    ]
    om_latest = json.loads((store_dir / "om_runs" / "latest.json").read_text(encoding="utf-8"))
    assert om_latest["payload"]["run_id"].startswith("om-")
    readiness_latest = json.loads((store_dir / "readiness_checks" / "latest.json").read_text(encoding="utf-8"))
    assert readiness_latest["payload"]["view"] == "current_release_latest_matrix"
    readiness_rows = {item["check_id"]: item for item in readiness_latest["payload"]["rows"]}
    assert readiness_rows["contract_guard"]["status"] in {"PASS", "FAIL"}
    readiness_history = (store_dir / "readiness_checks" / "history.jsonl").read_text(encoding="utf-8").splitlines()
    readiness_payloads = [json.loads(line)["payload"] for line in readiness_history if line.strip()]
    assert any(item["check_id"] == "playwright" for item in readiness_payloads)
    assert any(item["check_id"] == "wechat_devtools" for item in readiness_payloads)
    wechat_devtools = next(item for item in readiness_payloads if item["check_id"] == "wechat_devtools")
    assert wechat_devtools["status"] == "SKIP"
    assert wechat_devtools["required"] is False
    assert any("scope_authority=change_impact.required_readiness_checks" == item for item in wechat_devtools["evidence"])
    run_history = DAILY_OBSERVABILITY_MODULE.build_daily_run_history(store_dir=store_dir)
    assert run_history["summary"]["total"] >= 4


def test_run_benchmark_cli_writes_control_plane_latest(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_benchmark.py"),
            "pr_gate_core",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "benchmark_runs" / "latest.json").read_text(encoding="utf-8"))
    assert latest["kind"] == "benchmark_runs"
    assert latest["payload"]["run_manifest"]["requested_suites"] == ["pr_gate_core"]


def test_run_observability_daily_marks_verdict_stale_when_input_release_lags_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: DAILY_OBSERVABILITY_MODULE.argparse.Namespace(
            base_ref="HEAD~1",
            changed_file=[],
            metrics_json=None,
            api_base_url="http://127.0.0.1:8001",
            unified_ws_smoke_timeout=12.0,
            event_days=1,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_om_payload",
        lambda **_kwargs: {
            "run_id": "om-1",
            "metrics_snapshot": {},
            "health_summary": {},
            "release": {"release_id": "rel-old", "git_sha": "old123"},
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_arr_payload",
        lambda **_kwargs: {
            "run_id": "arr-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
            "benchmark_run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["pr_gate_core", "regression_watch", "real_exam_quality_spine"],
            },
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_benchmark_payload",
        lambda **_kwargs: {
            "run_manifest": {"run_id": "benchmark-1"},
            "summary": {"pass_rate": 1.0},
            "release_spine": {"release_id": "rel-old", "git_sha": "old123"},
        },
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_surface_readiness_rows", lambda **_kwargs: None)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_aae_payload",
        lambda **_kwargs: {
            "run_id": "aae-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
            "source_arr_run_id": "arr-1",
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "write_observer_snapshot_artifacts",
        lambda payload, output_dir: {"json_path": str(output_dir / "observer.json")},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_observer_snapshot",
        lambda **_kwargs: {
            "run_id": "observer-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
        },
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "collect_git_changed_files", lambda base_ref: [])
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_change_impact_run",
        lambda **_kwargs: {
            "run_id": "change-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
            "risk_level": "low",
        },
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "render_change_impact_markdown", lambda payload: "")
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_oa_run",
        lambda **_kwargs: {
            "run_id": "oa-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
            "verdict": "STALE",
            "root_causes": [],
            "causal_candidates": [],
            "blind_spots": [],
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_release_gate_report",
        lambda **_kwargs: {
            "run_id": "gate-1",
            "release": {"release_id": "rel-old", "git_sha": "old123"},
            "verdict": "STALE",
            "final_status": "FAIL",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": ["artifact_release_stale_vs_head"],
        },
    )

    DAILY_OBSERVABILITY_MODULE.main()

    latest = json.loads((tmp_path / "control_plane" / "daily_trends" / "latest.json").read_text(encoding="utf-8"))
    assert latest["payload"]["verdict"] == "STALE"


def test_run_observability_daily_passes_current_release_through_spine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-head",
        "git_sha": "head123",
        "deployment_environment": "local",
    }
    observed_releases: dict[str, dict[str, str]] = {}

    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: DAILY_OBSERVABILITY_MODULE.argparse.Namespace(
            base_ref="HEAD~1",
            changed_file=["deeptutor/services/session/turn_runtime.py"],
            metrics_json=None,
            api_base_url="http://127.0.0.1:8001",
            unified_ws_smoke_timeout=12.0,
            event_days=1,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "get_release_lineage_snapshot", lambda: dict(current_release))

    def _ensure_om_payload(**kwargs):
        observed_releases["om"] = dict(kwargs["release"])
        assert kwargs["unified_ws_smoke_timeout"] == 12.0
        return {
            "run_id": "om-1",
            "metrics_snapshot": {},
            "health_summary": {},
            "release": dict(kwargs["release"]),
        }

    def _ensure_benchmark_payload(**kwargs):
        observed_releases["benchmark"] = dict(kwargs["release"])
        return {
            "run_manifest": {"run_id": "benchmark-1"},
            "summary": {"pass_rate": 1.0},
            "release_spine": dict(kwargs["release"]),
        }

    def _ensure_arr_payload(**kwargs):
        observed_releases["arr"] = dict(kwargs["release"])
        return {
            "run_id": "arr-1",
            "release": dict(kwargs["release"]),
            "benchmark_run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["pr_gate_core", "regression_watch", "real_exam_quality_spine"],
            },
        }

    def _ensure_aae_payload(**kwargs):
        observed_releases["aae"] = dict(kwargs["release"])
        return {"run_id": "aae-1", "release": dict(kwargs["release"]), "source_arr_run_id": "arr-1"}

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_om_payload", _ensure_om_payload)
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_arr_payload", _ensure_arr_payload)
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_benchmark_payload", _ensure_benchmark_payload)
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "_ensure_aae_payload", _ensure_aae_payload)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_surface_readiness_rows",
        lambda **kwargs: observed_releases.setdefault("surface_readiness", dict(kwargs["release"])),
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "write_observer_snapshot_artifacts",
        lambda payload, output_dir: {"json_path": str(output_dir / "observer.json")},
    )

    def _build_observer_snapshot(**kwargs):
        observed_releases["observer"] = dict(kwargs["release"])
        return {"run_id": "observer-1", "release": dict(kwargs["release"]), "blind_spots": []}

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_observer_snapshot", _build_observer_snapshot)
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_write_contract_guard_readiness",
        lambda **kwargs: observed_releases.setdefault("readiness", dict(kwargs["release"])),
    )

    def _build_change_impact_run(**kwargs):
        observed_releases["change_impact"] = dict(kwargs["release"])
        return {
            "run_id": "change-1",
            "release": dict(kwargs["release"]),
            "risk_level": "low",
            "required_gates": [],
            "blind_spots": [],
        }

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_change_impact_run", _build_change_impact_run)
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "render_change_impact_markdown", lambda payload: "")

    def _build_oa_run(**kwargs):
        observed_releases["oa"] = dict(kwargs["release"])
        return {
            "run_id": "oa-1",
            "release": dict(kwargs["release"]),
            "verdict": "TRUSTED",
            "root_causes": [],
            "causal_candidates": [],
            "blind_spots": [],
        }

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_oa_run", _build_oa_run)

    def _build_release_gate_report(**kwargs):
        observed_releases["gate"] = dict(kwargs["release"])
        assert kwargs["plan_completion_payload"]["release"] == current_release
        return {
            "run_id": "gate-1",
            "release": dict(kwargs["release"]),
            "verdict": "TRUSTED",
            "final_status": "FAIL",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": [],
        }

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_release_gate_report", _build_release_gate_report)
    def _ensure_plan_completion_payload(**kwargs):
        observed_releases["plan_completion"] = dict(kwargs["release"])
        return {"run_id": "plan-1", "release": dict(kwargs["release"]), "status": "WARN", "summary": {}}

    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_plan_completion_payload",
        _ensure_plan_completion_payload,
    )

    DAILY_OBSERVABILITY_MODULE.main()

    assert observed_releases == {
        "om": current_release,
        "arr": current_release,
        "benchmark": current_release,
        "surface_readiness": current_release,
        "aae": current_release,
        "observer": current_release,
        "readiness": current_release,
        "change_impact": current_release,
        "oa": current_release,
        "plan_completion": current_release,
        "gate": current_release,
    }


def test_run_release_gate_cli_requires_canonical_benchmark_latest(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
    }

    om_dir = store_dir / "om_runs"
    arr_dir = store_dir / "arr_runs"
    benchmark_dir = store_dir / "benchmark_runs"
    for directory in (om_dir, arr_dir, benchmark_dir):
        directory.mkdir(parents=True, exist_ok=True)

    release = {
        "release_id": "rel-1",
        "git_sha": "abc123",
        "deployment_environment": "production",
        "prompt_version": "p1",
        "ff_snapshot_hash": "ff1",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest1",
    }
    om_wrapper = {
        "kind": "om_runs",
        "run_id": "om-1",
        "release_id": "rel-1",
        "recorded_at": 1,
        "payload": {
            "run_id": "om-1",
            "release": release,
            "health_summary": {"ready": True, "unified_ws_smoke_ok": True},
            "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
        },
    }
    arr_wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-1",
        "release_id": "rel-1",
        "recorded_at": 2,
        "payload": {
            "run_id": "arr-1",
            "release": release,
            "summary": {"pass_rate": 1.0},
            "baseline_diff": {"regressions": [], "new_failures": []},
            "benchmark_run_manifest": {"run_id": "bench-embedded", "requested_suites": ["pr_gate_core"]},
            "benchmark_case_results": [
                {
                    "suite": "pr_gate_core",
                    "case_id": "case-a",
                    "status": "PASS",
                    "gate_eligible": True,
                    "case_tier": "gate_stable",
                }
            ],
            "execution_context": {"api_base_url": "https://test2.yousenjiaoyu.com", "suite_execution_modes": {}},
        },
    }
    benchmark_wrapper = {
        "kind": "benchmark_runs",
        "run_id": "benchmark-1",
        "release_id": "rel-1",
        "recorded_at": 3,
        "payload": {
            "run_manifest": {"run_id": "benchmark-1", "requested_suites": ["pr_gate_core"]},
            "release_spine": release,
            "case_results": [],
            "summary": {"pass_rate": 1.0},
            "baseline_diff": {"regressions": [], "new_failures": []},
            "blind_spots": [],
        },
    }

    (om_dir / "latest.json").write_text(json.dumps(om_wrapper), encoding="utf-8")
    (arr_dir / "latest.json").write_text(json.dumps(arr_wrapper), encoding="utf-8")
    stray_benchmark_path = benchmark_dir / "benchmark-1.json"
    stray_benchmark_path.write_text(json.dumps(benchmark_wrapper), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_release_gate.py"),
            "--report-only",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "release_gate_runs" / "latest.json").read_text(encoding="utf-8"))
    p2 = next(item for item in latest["payload"]["gate_results"] if item["gate"] == "P2 Benchmark Regression")
    assert p2["status"] == "FAIL"
    assert p2["summary"] == "canonical benchmark row missing"


def test_run_release_gate_report_only_writes_plan_completion_placeholder(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
        "DEEPTUTOR_RELEASE_ID": "rel-eval",
        "DEEPTUTOR_GIT_SHA": "abc123",
        "DEEPTUTOR_ENV": "eval",
        "DEEPTUTOR_PROMPT_VERSION": "prompt-eval",
        "DEEPTUTOR_FF_SNAPSHOT_HASH": "ff-eval",
        "DEEPTUTOR_GIT_DIRTY": "false",
        "DEEPTUTOR_DEPLOY_MANIFEST_HASH": "manifest-eval",
    }
    release = {
        "release_id": "rel-eval",
        "git_sha": "abc123",
        "deployment_environment": "eval",
        "prompt_version": "prompt-eval",
        "ff_snapshot_hash": "ff-eval",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-eval",
    }
    benchmark_dir = store_dir / "benchmark_runs"
    om_dir = store_dir / "om_runs"
    plan_completion_dir = store_dir / "plan_completion_audits"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    om_dir.mkdir(parents=True, exist_ok=True)
    plan_completion_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "benchmark_runs",
                "run_id": "benchmark-1",
                "release_id": "rel-eval",
                "recorded_at": 1,
                "payload": {
                    "run_manifest": {"run_id": "benchmark-1", "requested_suites": ["pr_gate_core"]},
                    "release_spine": release,
                    "case_results": [
                        {
                            "suite": "pr_gate_core",
                            "case_id": "case-a",
                            "status": "PASS",
                            "gate_eligible": True,
                            "case_tier": "gate_stable",
                        }
                    ],
                    "summary": {"pass_rate": 1.0},
                    "baseline_diff": {"regressions": [], "new_failures": []},
                    "blind_spots": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (om_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "om_runs",
                "run_id": "om-1",
                "release_id": "rel-eval",
                "recorded_at": 1,
                "payload": {
                    "run_id": "om-1",
                    "release": release,
                    "health_summary": {"ready": True, "unified_ws_smoke_ok": True},
                    "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
                },
            }
        ),
        encoding="utf-8",
    )
    (plan_completion_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "plan_completion_audits",
                "run_id": "plan-completion-report-only-stale",
                "release_id": "rel-old",
                "recorded_at": 1,
                "payload": {
                    "run_id": "plan-completion-report-only-stale",
                    "release": {
                        **release,
                        "release_id": "rel-old",
                        "git_sha": "oldsha",
                    },
                    "scope_mode": "report_only",
                    "status": "WARN",
                    "summary": {"total": 0},
                    "blockers": [],
                    "warnings": ["plan_completion_report_only_placeholder"],
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_release_gate.py"),
            "--report-only",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "release_gate_runs" / "latest.json").read_text(encoding="utf-8"))
    payload = latest["payload"]
    assert payload["final_status"] == "WARN"
    assert payload["recommendation"] == "hold_with_conditions"
    assert "runtime_or_release_lineage_incomplete" not in payload["blockers"]
    assert "plan_completion_audit_missing" not in payload["blockers"]
    assert "plan_completion_audit_stale_release" not in payload["blockers"]
    assert payload["latest_runs"]["plan_completion_run_id"].startswith("plan-completion-report-only-")
    assert payload["latest_runs"]["plan_completion_run_id"] != "plan-completion-report-only-stale"
    plan_latest = json.loads((store_dir / "plan_completion_audits" / "latest.json").read_text(encoding="utf-8"))
    assert plan_latest["payload"]["status"] == "WARN"
    assert plan_latest["payload"]["release"]["release_id"] == "rel-eval"
    assert plan_latest["payload"]["release"]["git_sha"] == "abc123"
    assert "plan_completion_report_only_placeholder" in plan_latest["payload"]["warnings"]


def test_run_release_gate_report_only_ignores_non_spine_om_and_writes_scoped_placeholder(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
        "DEEPTUTOR_RELEASE_ID": "rel-eval",
        "DEEPTUTOR_GIT_SHA": "abc123",
        "DEEPTUTOR_ENV": "eval",
        "DEEPTUTOR_PROMPT_VERSION": "prompt-eval",
        "DEEPTUTOR_FF_SNAPSHOT_HASH": "ff-eval",
        "DEEPTUTOR_GIT_DIRTY": "false",
        "DEEPTUTOR_DEPLOY_MANIFEST_HASH": "manifest-eval",
    }
    eval_release = {
        "release_id": "rel-eval",
        "git_sha": "abc123",
        "deployment_environment": "eval",
        "prompt_version": "prompt-eval",
        "ff_snapshot_hash": "ff-eval",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-eval",
    }
    local_release = {
        **eval_release,
        "release_id": "1.0.0+abc123+local",
        "deployment_environment": "local",
        "prompt_version": "git-abc123",
        "ff_snapshot_hash": "local-ff",
        "git_dirty": "true",
        "deploy_manifest_hash": "local-manifest",
    }
    benchmark_dir = store_dir / "benchmark_runs"
    om_dir = store_dir / "om_runs"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    om_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "benchmark_runs",
                "run_id": "benchmark-1",
                "release_id": "rel-eval",
                "recorded_at": 1,
                "payload": {
                    "run_manifest": {"run_id": "benchmark-1", "requested_suites": ["pr_gate_core"]},
                    "release_spine": eval_release,
                    "case_results": [
                        {
                            "suite": "pr_gate_core",
                            "case_id": "case-a",
                            "status": "PASS",
                            "gate_eligible": True,
                            "case_tier": "gate_stable",
                        }
                    ],
                    "summary": {"pass_rate": 1.0},
                    "baseline_diff": {"regressions": [], "new_failures": []},
                    "blind_spots": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (om_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "om_runs",
                "run_id": "om-local",
                "release_id": "1.0.0+abc123+local",
                "recorded_at": 1,
                "payload": {
                    "run_id": "om-local",
                    "release": local_release,
                    "health_summary": {
                        "ready": True,
                        "unified_ws_smoke_ok": False,
                        "unified_ws_smoke_summary": "ConnectionRefusedError",
                    },
                    "metrics_snapshot": {"surface_events": {"coverage": []}},
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_release_gate.py"),
            "--report-only",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "release_gate_runs" / "latest.json").read_text(encoding="utf-8"))
    payload = latest["payload"]
    assert payload["final_status"] == "WARN"
    assert payload["recommendation"] == "hold_with_conditions"
    assert "ws_main_path_unhealthy" not in payload["blockers"]
    assert payload["latest_runs"]["om_run_id"].startswith("om-report-only-")
    om_latest = json.loads((store_dir / "om_runs" / "latest.json").read_text(encoding="utf-8"))
    assert om_latest["payload"]["release"]["release_id"] == "rel-eval"
    assert om_latest["payload"]["health_summary"]["unified_ws_smoke_ok"] is None


def test_run_observability_daily_passes_manual_readiness_rows_to_release_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    current_release = {
        "release_id": "rel-head",
        "git_sha": "head123",
        "deployment_environment": "local",
    }

    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE.argparse.ArgumentParser,
        "parse_args",
        lambda _self: DAILY_OBSERVABILITY_MODULE.argparse.Namespace(
            base_ref="HEAD~1",
            changed_file=[],
            metrics_json=None,
            api_base_url="http://127.0.0.1:8001",
            unified_ws_smoke_timeout=12.0,
            event_days=1,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "get_release_lineage_snapshot", lambda: dict(current_release))
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_om_payload",
        lambda **kwargs: {
            "run_id": "om-1",
            "metrics_snapshot": {},
            "health_summary": {},
            "release": dict(kwargs["release"]),
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_arr_payload",
        lambda **kwargs: {
            "run_id": "arr-1",
            "release": dict(kwargs["release"]),
            "benchmark_run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["pr_gate_core", "regression_watch", "real_exam_quality_spine"],
            },
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_benchmark_payload",
        lambda **kwargs: {
            "run_manifest": {
                "run_id": "benchmark-1",
                "requested_suites": ["pr_gate_core", "regression_watch", "real_exam_quality_spine"],
            },
            "summary": {"pass_rate": 1.0},
            "release_spine": dict(kwargs["release"]),
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_aae_payload",
        lambda **kwargs: {
            "run_id": "aae-1",
            "release": dict(kwargs["release"]),
            "source_arr_run_id": "arr-1",
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "write_observer_snapshot_artifacts",
        lambda payload, output_dir: {"json_path": str(output_dir / "observer.json")},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_observer_snapshot",
        lambda **kwargs: {"run_id": "observer-1", "release": dict(kwargs["release"]), "blind_spots": []},
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_change_impact_run",
        lambda **kwargs: {
            "run_id": "change-1",
            "release": dict(kwargs["release"]),
            "risk_level": "low",
            "required_gates": [],
            "blind_spots": [],
        },
    )
    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "render_change_impact_markdown", lambda payload: "")
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "build_oa_run",
        lambda **kwargs: {
            "run_id": "oa-1",
            "release": dict(kwargs["release"]),
            "verdict": "TRUSTED",
            "root_causes": [],
            "causal_candidates": [],
            "blind_spots": [],
        },
    )
    monkeypatch.setattr(
        DAILY_OBSERVABILITY_MODULE,
        "_ensure_plan_completion_payload",
        lambda **kwargs: {"run_id": "plan-1", "release": dict(kwargs["release"]), "status": "WARN", "summary": {}},
    )

    def _build_release_gate_report(**kwargs):
        manual_checks = {row["check_id"] for row in kwargs["readiness_payload"]["rows"]}
        assert {"playwright", "wechat_devtools"}.issubset(manual_checks)
        return {
            "run_id": "gate-1",
            "release": dict(kwargs["release"]),
            "verdict": "TRUSTED",
            "final_status": "FAIL",
            "recommendation": "hold",
            "gate_results": [],
            "blockers": [],
        }

    monkeypatch.setattr(DAILY_OBSERVABILITY_MODULE, "build_release_gate_report", _build_release_gate_report)

    DAILY_OBSERVABILITY_MODULE.main()


def test_run_release_gate_report_only_consumes_current_release_readiness_history(tmp_path) -> None:
    store_dir = tmp_path / "control_plane"
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(store_dir),
        "DEEPTUTOR_RELEASE_ID": "rel-eval",
        "DEEPTUTOR_GIT_SHA": "abc123",
        "DEEPTUTOR_ENV": "eval",
        "DEEPTUTOR_PROMPT_VERSION": "prompt-eval",
        "DEEPTUTOR_FF_SNAPSHOT_HASH": "ff-eval",
        "DEEPTUTOR_GIT_DIRTY": "false",
        "DEEPTUTOR_DEPLOY_MANIFEST_HASH": "manifest-eval",
    }
    release = {
        "release_id": "rel-eval",
        "git_sha": "abc123",
        "deployment_environment": "eval",
        "prompt_version": "prompt-eval",
        "ff_snapshot_hash": "ff-eval",
        "git_dirty": "false",
        "deploy_manifest_hash": "manifest-eval",
    }
    benchmark_dir = store_dir / "benchmark_runs"
    om_dir = store_dir / "om_runs"
    readiness_dir = store_dir / "readiness_checks"
    for directory in (benchmark_dir, om_dir, readiness_dir):
        directory.mkdir(parents=True, exist_ok=True)

    (benchmark_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "benchmark_runs",
                "run_id": "benchmark-1",
                "release_id": "rel-eval",
                "recorded_at": 1,
                "payload": {
                    "run_manifest": {
                        "run_id": "benchmark-1",
                        "requested_suites": ["pr_gate_core", "regression_watch", "real_exam_quality_spine"],
                    },
                    "release_spine": release,
                    "case_results": [
                        {
                            "suite": "pr_gate_core",
                            "case_id": "case-a",
                            "status": "PASS",
                            "gate_eligible": True,
                            "case_tier": "gate_stable",
                        }
                    ],
                    "summary": {"pass_rate": 1.0},
                    "baseline_diff": {"regressions": [], "new_failures": []},
                    "blind_spots": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (om_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "om_runs",
                "run_id": "om-1",
                "release_id": "rel-eval",
                "recorded_at": 1,
                "payload": {
                    "run_id": "om-1",
                    "release": release,
                    "health_summary": {"ready": True, "unified_ws_smoke_ok": True},
                    "metrics_snapshot": {"surface_events": {"coverage": [{"surface": "web"}]}},
                },
            }
        ),
        encoding="utf-8",
    )
    readiness_rows = [
        {
            "kind": "readiness_checks",
            "run_id": "playwright-1",
            "release_id": "rel-eval",
            "recorded_at": 1,
            "payload": {
                "run_id": "playwright-1",
                "check_id": "playwright",
                "label": "Playwright",
                "status": "FAIL",
                "required": True,
                "summary": "Playwright readiness missing",
                "evidence": [],
                "blockers": ["playwright_failed"],
                "release": release,
            },
        },
        {
            "kind": "readiness_checks",
            "run_id": "wechat-1",
            "release_id": "rel-eval",
            "recorded_at": 2,
            "payload": {
                "run_id": "wechat-1",
                "check_id": "wechat_devtools",
                "label": "微信 DevTools",
                "status": "FAIL",
                "required": True,
                "summary": "WeChat readiness missing",
                "evidence": [],
                "blockers": ["wechat_devtools_failed"],
                "release": release,
            },
        },
        {
            "kind": "readiness_checks",
            "run_id": "contract-1",
            "release_id": "rel-eval",
            "recorded_at": 3,
            "payload": {
                "run_id": "contract-1",
                "check_id": "contract_guard",
                "label": "Contract Guard",
                "status": "PASS",
                "required": True,
                "summary": "contract guard passed",
                "evidence": [],
                "blockers": [],
                "release": release,
            },
        },
    ]
    (readiness_dir / "latest.json").write_text(json.dumps(readiness_rows[-1]), encoding="utf-8")
    (readiness_dir / "history.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in readiness_rows) + "\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "run_release_gate.py"),
            "--report-only",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    latest = json.loads((store_dir / "release_gate_runs" / "latest.json").read_text(encoding="utf-8"))
    payload = latest["payload"]
    assert payload["final_status"] == "FAIL"
    assert "playwright_failed" in payload["blockers"]
    assert "wechat_devtools_failed" in payload["blockers"]
