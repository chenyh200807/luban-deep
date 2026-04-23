from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from deeptutor.services.benchmark.incident import (
    build_incident_replay_report,
    write_incident_replay_artifacts,
)


def _sample_benchmark_payload() -> dict:
    return {
        "run_manifest": {
            "run_id": "benchmark-incident",
            "requested_suites": ["incident_replay"],
            "dataset_id": "benchmark_phase1",
            "dataset_version": "phase1.0",
        },
        "release_spine": {"release_id": "rel-current"},
        "failure_taxonomy": [{"failure_type": "FAIL_SURFACE_DELIVERY", "count": 1}],
        "baseline_diff": {
            "regressions": [{"case_key": "incident_replay::surface_a"}],
            "new_failures": [],
        },
        "blind_spots": [
            {
                "suite": "incident_replay",
                "case_id": "surface.web.ack.smoke",
                "reason": "missing_api_base_url",
            }
        ],
        "case_results": [
            {
                "suite": "incident_replay",
                "case_id": "surface_a",
                "status": "FAIL",
                "failure_type": "FAIL_SURFACE_DELIVERY",
            }
        ],
    }


def test_build_incident_replay_report_classifies_regression_and_blind_spot() -> None:
    payload = build_incident_replay_report(
        benchmark_payload=_sample_benchmark_payload(),
        incident_id="INC-001",
    )

    assert payload["run_manifest"]["incident_id"] == "INC-001"
    assert payload["run_manifest"]["source_benchmark_run_id"] == "benchmark-incident"
    assert payload["classification"] == {
        "known_regression_count": 1,
        "new_failure_count": 0,
        "current_failure_count": 1,
        "blind_spot_count": 1,
    }
    assert payload["replay_candidates"] == [
        {
            "incident_id": "INC-001",
            "case_id": "surface.web.ack.smoke",
            "suite": "incident_replay",
            "reason": "missing_api_base_url",
            "recommended_tier": "incident_replay",
        }
    ]


def test_write_incident_replay_artifacts_writes_json_and_markdown(tmp_path: Path) -> None:
    payload = build_incident_replay_report(
        benchmark_payload=_sample_benchmark_payload(),
        incident_id="INC-001",
    )

    paths = write_incident_replay_artifacts(payload, output_dir=tmp_path)

    json_path = Path(paths["json_path"])
    md_path = Path(paths["md_path"])
    assert json_path.exists()
    assert md_path.exists()
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["classification"]["blind_spot_count"] == 1


def test_run_incident_replay_cli_writes_control_plane_and_artifacts(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(tmp_path / "store"),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_incident_replay.py",
            "--incident-id",
            "INC-CLI",
            "--output-dir",
            str(tmp_path / "incident"),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Incident replay completed" in completed.stdout
    assert list((tmp_path / "incident" / "runs").glob("benchmark_run_*.json"))
    assert list((tmp_path / "incident" / "incident").glob("benchmark_incident_replay_*.json"))
    assert (tmp_path / "store" / "benchmark_runs" / "latest.json").exists()
    assert (tmp_path / "store" / "incident_ledger" / "latest.json").exists()
