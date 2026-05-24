#!/usr/bin/env python3
"""Run DeepTutor eval gates from eval/gates.yaml.

This runner is the automation command authority. It keeps gate selection,
missing-dependency deferral, logs, and summaries in one place so recurring
eval jobs do not accidentally evaluate a different checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATES_PATH = PROJECT_ROOT / "eval" / "gates.yaml"
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "tmp" / "eval-gate"


@dataclass(frozen=True)
class Gate:
    name: str
    description: str
    category: str
    command: list[str]
    workdir: Path
    required_paths: list[Path]
    deferred_reason: str
    timeout_seconds: float | None


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return payload


def _as_string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_gates(path: Path) -> list[Gate]:
    payload = _load_yaml(path)
    raw_gates = payload.get("gates")
    if not isinstance(raw_gates, dict):
        raise ValueError(f"{path} must define a gates mapping")

    gates: list[Gate] = []
    for name, raw_gate in raw_gates.items():
        if not isinstance(name, str) or not isinstance(raw_gate, dict):
            raise ValueError("each gate must be a mapping keyed by name")
        command = _as_string_list(raw_gate.get("command", []), field_name=f"{name}.command")
        workdir = _resolve_project_path(str(raw_gate.get("workdir") or "."))
        required_paths = [
            _resolve_project_path(item)
            for item in _as_string_list(raw_gate.get("required_paths", []), field_name=f"{name}.required_paths")
        ]
        timeout_raw = raw_gate.get("timeout_seconds")
        gates.append(
            Gate(
                name=name,
                description=str(raw_gate.get("description") or ""),
                category=str(raw_gate.get("category") or "quick"),
                command=command,
                workdir=workdir,
                required_paths=required_paths,
                deferred_reason=str(raw_gate.get("deferred_reason") or ""),
                timeout_seconds=float(timeout_raw) if timeout_raw is not None else None,
            )
        )
    return gates


def _command_for_runtime(command: list[str], artifact_dir: Path) -> list[str]:
    rendered = [part.format(artifact_dir=str(artifact_dir)) for part in command]
    if rendered and rendered[0] in {"python", "python3"}:
        rendered[0] = sys.executable
    return rendered


def _env_with_project_root() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [str(PROJECT_ROOT)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _deferred_reason(gate: Gate) -> str:
    if gate.deferred_reason:
        return gate.deferred_reason
    missing = [str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path) for path in gate.required_paths if not path.exists()]
    if missing:
        return "missing required path(s): " + ", ".join(missing)
    return ""


def _write_log(path: Path, *, stdout: str = "", stderr: str = "") -> None:
    parts: list[str] = []
    if stdout:
        parts.append(stdout.rstrip())
    if stderr:
        if parts:
            parts.append("")
        parts.append("[stderr]")
        parts.append(stderr.rstrip())
    path.write_text("\n".join(parts).rstrip() + ("\n" if parts else ""), encoding="utf-8")


def run_gate(gate: Gate, *, artifact_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    logs_dir = artifact_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{gate.name}.log"

    reason = _deferred_reason(gate)
    if reason:
        _write_log(log_path, stdout=f"DEFERRED: {reason}")
        return {
            "name": gate.name,
            "description": gate.description,
            "category": gate.category,
            "status": "DEFERRED",
            "exit_code": None,
            "duration_s": round(time.monotonic() - started, 3),
            "reason": reason,
            "log_path": str(log_path),
        }

    command = _command_for_runtime(gate.command, artifact_dir)
    completed = subprocess.run(
        command,
        cwd=gate.workdir,
        env=_env_with_project_root(),
        text=True,
        capture_output=True,
        check=False,
        timeout=gate.timeout_seconds,
    )
    _write_log(log_path, stdout=completed.stdout, stderr=completed.stderr)
    return {
        "name": gate.name,
        "description": gate.description,
        "category": gate.category,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "duration_s": round(time.monotonic() - started, 3),
        "command": command,
        "workdir": str(gate.workdir),
        "log_path": str(log_path),
    }


def _build_summary(results: list[dict[str, Any]], *, gates_path: Path, artifact_dir: Path) -> dict[str, Any]:
    counts = {
        "passed": sum(1 for item in results if item["status"] == "PASS"),
        "failed": sum(1 for item in results if item["status"] == "FAIL"),
        "deferred": sum(1 for item in results if item["status"] == "DEFERRED"),
    }
    verdict = "FAIL" if counts["failed"] else "PASS"
    return {
        "run_id": artifact_dir.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "gates_path": str(gates_path),
        "artifact_dir": str(artifact_dir),
        "verdict": verdict,
        "summary": counts,
        "gates": results,
    }


def _write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# DeepTutor Eval Gate",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- verdict: `{summary['verdict']}`",
        f"- project_root: `{summary['project_root']}`",
        f"- artifact_dir: `{summary['artifact_dir']}`",
        "",
        "## Summary",
        "",
        f"- passed: {summary['summary']['passed']}",
        f"- failed: {summary['summary']['failed']}",
        f"- deferred: {summary['summary']['deferred']}",
        "",
        "## Gates",
        "",
    ]
    for gate in summary["gates"]:
        suffix = f" | {gate.get('reason', '')}" if gate["status"] == "DEFERRED" else ""
        lines.append(
            f"- `{gate['name']}` => `{gate['status']}`"
            f" | exit={gate.get('exit_code')} | {gate['duration_s']}s | {gate['log_path']}{suffix}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_gate_list(gates: list[Gate]) -> None:
    for gate in gates:
        reason = _deferred_reason(gate)
        status = "DEFERRED" if reason else "READY"
        print(f"{gate.name}\t{gate.category}\t{status}\t{gate.description}")
        if reason:
            print(f"  reason: {reason}")


def _default_artifact_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_ARTIFACT_ROOT / stamp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gates-path", default=str(DEFAULT_GATES_PATH))
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--list", action="store_true", help="List gates and exit.")
    args = parser.parse_args()

    gates_path = _resolve_project_path(args.gates_path)
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else _default_artifact_dir()
    gates = load_gates(gates_path)

    if args.list:
        _print_gate_list(gates)
        return 0

    artifact_dir.mkdir(parents=True, exist_ok=True)
    results = [run_gate(gate, artifact_dir=artifact_dir) for gate in gates]
    summary = _build_summary(results, gates_path=gates_path, artifact_dir=artifact_dir)
    summary_path = artifact_dir / "summary.json"
    markdown_path = artifact_dir / "summary.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(summary, markdown_path)

    print(
        "Eval gate completed: "
        f"verdict={summary['verdict']} "
        f"PASS={summary['summary']['passed']} "
        f"FAIL={summary['summary']['failed']} "
        f"DEFERRED={summary['summary']['deferred']}"
    )
    print(f"JSON: {summary_path}")
    print(f"MD:   {markdown_path}")
    return 1 if summary["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
