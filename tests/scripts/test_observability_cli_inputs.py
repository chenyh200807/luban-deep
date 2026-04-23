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
OBSERVER_SNAPSHOT_MODULE = _load_script_module("run_observer_snapshot.py")
CHANGE_IMPACT_MODULE = _load_script_module("run_change_impact.py")
DAILY_OBSERVABILITY_MODULE = _load_script_module("run_observability_daily.py")


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
