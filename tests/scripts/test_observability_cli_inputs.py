from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

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
            change_impact_json=None,
            plan_completion_json=None,
            report_only=False,
        ),
    )
    monkeypatch.setattr(RELEASE_GATE_MODULE, "_load_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(RELEASE_GATE_MODULE, "_load_store_payload", lambda _kind: None)
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
    assert latest["payload"]["check_id"] == "playwright"
    assert latest["payload"]["status"] == "PASS"
    assert "playwright smoke passed" in latest["payload"]["summary"]
    assert any("exit_code=0" in item for item in latest["payload"]["evidence"])


def test_run_readiness_check_default_contract_guard_command() -> None:
    command = READINESS_CHECK_MODULE._default_command("contract_guard", ["docs/plan/INDEX.md"])

    assert command[-2:] == [str(Path(__file__).resolve().parents[2] / "scripts" / "check_contract_guard.py"), "docs/plan/INDEX.md"]


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
        "observer_snapshots",
        "change_impact_runs",
        "oa_runs",
        "release_gate_runs",
        "daily_trends",
    ):
        assert (store_dir / kind / "latest.json").exists()

    oa_latest = json.loads((store_dir / "oa_runs" / "latest.json").read_text(encoding="utf-8"))
    assert oa_latest["payload"]["causal_candidates"]
    run_history = DAILY_OBSERVABILITY_MODULE.build_daily_run_history(store_dir=store_dir)
    assert run_history["summary"]["total"] >= 4
