from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from deeptutor.services.benchmark.trend import (
    build_daily_trend,
    write_daily_trend_artifacts,
)


def _sample_benchmark_payload() -> dict:
    return {
        "run_manifest": {
            "run_id": "benchmark-current",
            "generated_at": "2026-04-23 09:00:00",
            "requested_suites": ["regression_watch"],
            "dataset_id": "benchmark_phase1",
            "dataset_version": "phase1.0",
        },
        "release_spine": {"release_id": "rel-current"},
        "summary": {"pass_rate": 0.5},
        "suite_summaries": [{"suite": "regression_watch", "pass_rate": 0.5}],
        "failure_taxonomy": [{"failure_type": "FAIL_CONTINUITY", "count": 1}],
        "baseline_diff": {
            "regressions": [{"case_key": "regression_watch::case_a"}],
            "new_failures": [{"case_key": "regression_watch::case_b"}],
        },
        "blind_spots": [{"suite": "incident_replay", "case_id": "surface.web.ack.smoke"}],
        "case_results": [
            {
                "suite": "regression_watch",
                "case_id": "grounding_a",
                "status": "PASS",
                "contract_domain": "grounding_contract",
                "failure_type": None,
            },
            {
                "suite": "regression_watch",
                "case_id": "continuity_a",
                "status": "FAIL",
                "contract_domain": "continuity_contract",
                "failure_type": "FAIL_CONTINUITY",
            },
            {
                "suite": "incident_replay",
                "case_id": "surface_a",
                "status": "PASS",
                "contract_domain": "surface_contract",
                "failure_type": None,
            },
            {
                "suite": "incident_replay",
                "case_id": "surface_b",
                "status": "SKIP",
                "contract_domain": "production_replay_contract",
                "failure_type": None,
            },
        ],
    }


def test_build_daily_trend_derives_six_canonical_metrics() -> None:
    payload = build_daily_trend(current_payload=_sample_benchmark_payload())

    assert payload["run_manifest"]["source_benchmark_run_id"] == "benchmark-current"
    assert payload["metrics"] == {
        "pass_rate": 0.5,
        "new_regression_count": 2,
        "continuity_floor": 0.0,
        "groundedness_floor": 1.0,
        "surface_delivery_coverage": 0.5,
        "blind_spot_count": 1,
    }
    assert payload["failure_bucket_delta"] == [{"failure_type": "FAIL_CONTINUITY", "count": 1}]
    assert payload["trend_points"][-1]["run_id"] == "benchmark-current"


def test_write_daily_trend_artifacts_writes_json_and_markdown(tmp_path: Path) -> None:
    payload = build_daily_trend(current_payload=_sample_benchmark_payload())

    paths = write_daily_trend_artifacts(payload, output_dir=tmp_path)

    json_path = Path(paths["json_path"])
    md_path = Path(paths["md_path"])
    assert json_path.exists()
    assert md_path.exists()
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["metrics"]["blind_spot_count"] == 1


def test_run_daily_benchmark_cli_writes_control_plane_and_artifacts(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(tmp_path / "store"),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_daily_benchmark.py",
            "--output-dir",
            str(tmp_path / "daily"),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Daily benchmark trend completed" in completed.stdout
    assert list((tmp_path / "daily" / "runs").glob("benchmark_run_*.json"))
    assert list((tmp_path / "daily" / "trend").glob("benchmark_daily_trend_*.json"))
    assert (tmp_path / "store" / "benchmark_runs" / "latest.json").exists()
    assert (tmp_path / "store" / "daily_trends" / "latest.json").exists()
