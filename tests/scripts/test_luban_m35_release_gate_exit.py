"""Release gate must be usable as a deterministic CI gate via --fail-on-no-go."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests/fixtures/luban_m35_case_scoring"
SCRIPT = REPO_ROOT / "scripts/run_luban_m35_scoring_artifact_release_gate.py"


def test_release_gate_fail_on_no_go_exits_nonzero(tmp_path):
    out = tmp_path / "gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            str(FIXTURE),
            "--output",
            str(out),
            "--fail-on-no-go",
        ],
        capture_output=True,
        cwd=REPO_ROOT,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] == "NO-GO"
    assert proc.returncode == 1


def test_release_gate_default_remains_report_generator(tmp_path):
    out = tmp_path / "gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            str(FIXTURE),
            "--output",
            str(out),
        ],
        capture_output=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
