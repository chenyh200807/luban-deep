from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_apply_refuses_production_apply() -> None:
    result = run_script(["scripts/apply_2026_compiler_backfill.py", "--run-id", "pytest", "--apply"])

    assert result.returncode != 0
    assert "Refusing --apply until Task 13 apply executor is implemented" in result.stderr


def test_apply_dry_run_generates_plan(tmp_path: Path) -> None:
    result = run_script(
        [
            "scripts/apply_2026_compiler_backfill.py",
            "--run-id",
            "pytest-dry-run",
            "--dry-run",
            "--output",
            str(tmp_path / "plan.sql"),
        ]
    )

    assert result.returncode == 0, result.stderr
    sql = (tmp_path / "plan.sql").read_text(encoding="utf-8")
    assert "compiler_version" in sql
    assert "overwrite_only_if_empty" in sql


def test_release_gate_script_reports_apply_refusal() -> None:
    result = run_script(["scripts/check_2026_source_compiler_release_gates.py", "--run-id", "missing"])

    assert result.returncode != 0
    assert "apply_refuses=true" in result.stdout
