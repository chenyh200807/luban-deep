from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_eval_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_eval_gate.py", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_eval_gate_runner_lists_yaml_gates(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    gates_path.write_text(
        """
version: 1
gates:
  sample_gate:
    command: ["python", "-c", "print('sample')"]
    description: "Sample gate"
""",
        encoding="utf-8",
    )

    result = _run_eval_gate("--gates-path", str(gates_path), "--list")

    assert result.returncode == 0, result.stderr
    assert "sample_gate" in result.stdout
    assert "Sample gate" in result.stdout


def test_eval_gate_runner_defers_missing_required_paths(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    gates_path.write_text(
        """
version: 1
gates:
  missing_fixture_gate:
    command: ["python", "-c", "raise SystemExit('should not run')"]
    required_paths:
      - "does/not/exist.json"
""",
        encoding="utf-8",
    )

    result = _run_eval_gate(
        "--gates-path",
        str(gates_path),
        "--artifact-dir",
        str(artifact_dir),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["verdict"] == "PASS"
    assert summary["summary"]["deferred"] == 1
    gate = summary["gates"][0]
    assert gate["name"] == "missing_fixture_gate"
    assert gate["status"] == "DEFERRED"
    assert "does/not/exist.json" in gate["reason"]


def test_eval_gate_runner_injects_project_root_first_in_pythonpath(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    gates_path.write_text(
        """
version: 1
gates:
  pythonpath_gate:
    command:
      - "python"
      - "-c"
      - "import os, sys; assert os.environ['PYTHONPATH'].split(os.pathsep)[0] == os.getcwd(); print('ok')"
""",
        encoding="utf-8",
    )

    result = _run_eval_gate(
        "--gates-path",
        str(gates_path),
        "--artifact-dir",
        str(artifact_dir),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["summary"]["passed"] == 1
    assert (artifact_dir / "logs" / "pythonpath_gate.log").read_text(encoding="utf-8").strip() == "ok"


def test_standalone_deep_scripts_resolve_repo_checkout_without_external_pythonpath() -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    semantic = subprocess.run(
        [sys.executable, "scripts/run_semantic_router_eval.py", "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert semantic.returncode == 0, semantic.stderr
    assert json.loads(semantic.stdout)["failed"] == 0

    maintenance = subprocess.run(
        [sys.executable, "scripts/run_learning_fact_retrieval_maintenance.py", "--pretty"],
        cwd=PROJECT_ROOT,
        env=env,
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )
    assert maintenance.returncode == 0, maintenance.stderr
    assert json.loads(maintenance.stdout)["ok"] is True
