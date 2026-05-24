from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_learning_synthesis_bootstraps_repo_root_before_deeptutor_imports() -> None:
    source = Path("scripts/run_learning_synthesis.py").read_text(encoding="utf-8")

    assert "sys.path.insert(0, str(PROJECT_ROOT))" in source


def test_run_learning_synthesis_dry_run_outputs_projection() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_learning_synthesis.py",
            "--user-id",
            "student_demo",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] in {"ok", "no_events"}
    assert payload["user_id"] == "student_demo"
    assert payload["dry_run"] is True
    assert "created_claim_count" in payload
    assert "output_projection_hash" in payload
