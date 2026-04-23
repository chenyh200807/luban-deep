from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from deeptutor.services.observability.failed_turn_promotion import build_failed_turn_incident_report
from deeptutor.services.observability.failed_turn_promotion import write_failed_turn_incident_report
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import build_turn_observation_event


def test_build_failed_turn_incident_report_promotes_failed_turns_to_replay_candidates(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        build_turn_observation_event(
            session_id="session-1",
            turn_id="turn-ok",
            status="completed",
            capability="chat",
        )
    )
    event_log.append(
        build_turn_observation_event(
            session_id="session-1",
            turn_id="turn-failed",
            trace_id="trace-1",
            status="failed",
            capability="deep_question",
            route="deep_question",
            error_type="TimeoutError",
            metadata={"message": "worker timeout"},
        )
    )

    payload = build_failed_turn_incident_report(
        event_log=event_log,
        incident_id="INC-TURN-1",
        days=1,
    )

    assert payload["run_manifest"]["incident_id"] == "INC-TURN-1"
    assert payload["classification"]["failed_turn_count"] == 1
    assert payload["replay_candidates"] == [
        {
            "incident_id": "INC-TURN-1",
            "source": "turn_event_log",
            "session_id": "session-1",
            "turn_id": "turn-failed",
            "trace_id": "trace-1",
            "status": "failed",
            "capability": "deep_question",
            "route": "deep_question",
            "error_type": "TimeoutError",
            "reason": "worker timeout",
            "recommended_tier": "incident_replay",
        }
    ]


def test_write_failed_turn_incident_report_writes_json_and_markdown(tmp_path) -> None:
    payload = {
        "run_manifest": {"run_id": "failed-turn-incident-1", "incident_id": "INC-1"},
        "classification": {"failed_turn_count": 0},
        "replay_candidates": [],
    }

    paths = write_failed_turn_incident_report(payload, output_dir=tmp_path)

    assert paths["json_path"].endswith(".json")
    assert paths["md_path"].endswith(".md")


def test_run_failed_turn_promotion_cli_writes_incident_ledger(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        build_turn_observation_event(
            session_id="session-1",
            turn_id="turn-timeout",
            status="timeout",
            error_type="TimeoutError",
        )
    )
    env = {
        **os.environ,
        "DEEPTUTOR_OBSERVER_EVENT_DIR": str(tmp_path / "events"),
        "DEEPTUTOR_OBSERVABILITY_STORE_DIR": str(tmp_path / "store"),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_failed_turn_promotion.py",
            "--incident-id",
            "INC-FAILED-TURN",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    latest_path = tmp_path / "store" / "incident_ledger" / "latest.json"
    assert latest_path.exists()
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["kind"] == "incident_ledger"
    assert latest["payload"]["classification"]["failed_turn_count"] == 1
