from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_learning_brain_dream_cycle import run_dream_cycle


def test_run_learning_brain_dream_cycle_dry_run_reports_without_writes(tmp_path: Path) -> None:
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(
        json.dumps(
            {
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "claim": "该学员反复漏写专家论证。",
                        "claim_status": "repeated",
                        "evidence_refs": ["evt1", "evt2"],
                    }
                ],
                "next_best_actions": [{"training_intent_id": "lti_1", "evidence_refs": ["evt1"]}],
            }
        ),
        encoding="utf-8",
    )

    result = run_dream_cycle(
        user_id="student_demo",
        dry_run=True,
        projection_file=projection_path,
    )

    assert result["status"] == "dry_run_ok"
    assert result["users_scanned"] == 1
    assert result["issues"] == []
    assert result["would_refresh_compiled_truth"] is False
    assert projection_path.exists()


def test_run_learning_brain_dream_cycle_cli_json(tmp_path: Path) -> None:
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(json.dumps({"weak_points": []}), encoding="utf-8")

    output = subprocess.check_output(
        [
            sys.executable,
            "scripts/run_learning_brain_dream_cycle.py",
            "--user-id",
            "student_demo",
            "--dry-run",
            "--json",
            "--projection-file",
            str(projection_path),
        ],
        text=True,
    )
    payload = json.loads(output)

    assert payload["status"] == "dry_run_ok"
    assert payload["users_scanned"] == 1
