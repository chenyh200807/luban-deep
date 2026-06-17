"""Release gate must be usable as a deterministic CI gate via --fail-on-no-go."""
import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("tests/fixtures/luban_m35_case_scoring")


def test_release_gate_fail_on_no_go_exits_nonzero(tmp_path):
    out = tmp_path / "gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_luban_m35_scoring_artifact_release_gate.py",
            "--fixture",
            str(FIXTURE),
            "--output",
            str(out),
            "--fail-on-no-go",
        ],
        capture_output=True,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] == "NO-GO"
    assert proc.returncode == 1


def test_release_gate_default_remains_report_generator(tmp_path):
    out = tmp_path / "gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_luban_m35_scoring_artifact_release_gate.py",
            "--fixture",
            str(FIXTURE),
            "--output",
            str(out),
        ],
        capture_output=True,
    )
    assert proc.returncode == 0
