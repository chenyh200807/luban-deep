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


def test_eval_gate_runner_passes_gate_env_overrides(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    gates_path.write_text(
        """
version: 1
gates:
  env_gate:
    env:
      DEEPTUTOR_ENV: "eval"
      DEEPTUTOR_DEPLOY_MANIFEST_HASH: "manifest-{artifact_dir_name}"
    command:
      - "python"
      - "-c"
      - "import os; print(os.environ['DEEPTUTOR_ENV']); print(os.environ['DEEPTUTOR_DEPLOY_MANIFEST_HASH'])"
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
    assert (artifact_dir / "logs" / "env_gate.log").read_text(encoding="utf-8").splitlines() == [
        "eval",
        f"manifest-{artifact_dir.name}",
    ]


def test_eval_gate_runner_records_timeout_as_failed_gate(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    gates_path.write_text(
        """
version: 1
gates:
  timeout_gate:
    command: ["python", "-c", "import time; time.sleep(2)"]
    timeout_seconds: 0.05
""",
        encoding="utf-8",
    )

    result = _run_eval_gate(
        "--gates-path",
        str(gates_path),
        "--artifact-dir",
        str(artifact_dir),
    )

    assert result.returncode == 1
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    gate = summary["gates"][0]
    assert summary["summary"]["failed"] == 1
    assert gate["status"] == "FAIL"
    assert gate["failure_signature"] == "gate_timeout"
    assert "timeout after 0.05s" in gate["reason"]
    assert "TIMEOUT" in (artifact_dir / "logs" / "timeout_gate.log").read_text(encoding="utf-8")


def test_eval_gate_runner_reports_slow_gates(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    gates_path.write_text(
        """
version: 1
gates:
  slow_gate:
    command: ["python", "-c", "print('ok')"]
    slow_seconds: 0
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
    assert summary["summary"]["slow"] == 1
    assert summary["slow_gates"][0]["name"] == "slow_gate"
    assert "## Slow Gates" in (artifact_dir / "summary.md").read_text(encoding="utf-8")


def test_eval_gate_runner_fails_release_report_only_when_payload_holds(tmp_path: Path) -> None:
    gates_path = tmp_path / "gates.yaml"
    artifact_dir = tmp_path / "artifacts"
    release_payload = tmp_path / "release_gate.json"
    release_payload.write_text(
        json.dumps(
            {
                "kind": "release_gate_runs",
                "payload": {
                    "final_status": "FAIL",
                    "recommendation": "hold",
                    "blockers": ["plan_completion_audit_missing"],
                },
            }
        ),
        encoding="utf-8",
    )
    gates_path.write_text(
        f"""
version: 1
gates:
  release_gate_report_only:
    command:
      - "python"
      - "-c"
      - "print('Final status: FAIL'); print('Recommendation: hold'); print('JSON: {release_payload}')"
""",
        encoding="utf-8",
    )

    result = _run_eval_gate(
        "--gates-path",
        str(gates_path),
        "--artifact-dir",
        str(artifact_dir),
    )

    assert result.returncode == 1
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    gate = summary["gates"][0]
    assert summary["verdict"] == "FAIL"
    assert summary["summary"]["failed"] == 1
    assert gate["status"] == "FAIL"
    assert gate["failure_signature"] == "release_gate_report_only_hold"
    assert gate["release_gate_final_status"] == "FAIL"
    assert gate["release_gate_recommendation"] == "hold"
    assert "plan_completion_audit_missing" in gate["reason"]


def test_eval_gate_yaml_turns_coverage_gaps_into_runnable_gates() -> None:
    gates = (PROJECT_ROOT / "eval" / "gates.yaml").read_text(encoding="utf-8")

    assert "required_paths:\n      - \"web/package-lock.json\"" in gates
    assert "test:wechat-harness:e2e:ci" in gates
    assert "tests/fixtures/long_dialog_v1_retest_source.json" in gates
    assert "--start-local-api" in gates
    assert "web/node_modules/.bin/playwright" not in gates
    assert "requires --source-json historical artifact" not in gates
    assert "requires local API server" not in gates


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
