#!/usr/bin/env python3
"""Run DeepTutor eval gates from eval/gates.yaml.

This runner is the automation command authority. It keeps gate selection,
missing-dependency deferral, logs, and summaries in one place so recurring
eval jobs do not accidentally evaluate a different checkout.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
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
    env: dict[str, str]
    workdir: Path
    required_paths: list[Path]
    deferred_reason: str
    timeout_seconds: float | None
    slow_seconds: float | None


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


def _as_string_dict(value: Any, *, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise ValueError(f"{field_name} must be a mapping of strings")
    return dict(value)


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
        slow_raw = raw_gate.get("slow_seconds")
        gates.append(
            Gate(
                name=name,
                description=str(raw_gate.get("description") or ""),
                category=str(raw_gate.get("category") or "quick"),
                command=command,
                env=_as_string_dict(raw_gate.get("env", {}), field_name=f"{name}.env"),
                workdir=workdir,
                required_paths=required_paths,
                deferred_reason=str(raw_gate.get("deferred_reason") or ""),
                timeout_seconds=float(timeout_raw) if timeout_raw is not None else None,
                slow_seconds=float(slow_raw) if slow_raw is not None else None,
            )
        )
    return gates


def _execution_order(gates: list[Gate]) -> list[Gate]:
    release_gate_names = {"release_gate_report_only"}
    release_gates = [gate for gate in gates if gate.name in release_gate_names]
    if not release_gates:
        return gates
    return [gate for gate in gates if gate.name not in release_gate_names] + release_gates


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


def _default_eval_env(*, artifact_dir: Path) -> dict[str, str]:
    artifact_name = artifact_dir.name
    return {
        "DEEPTUTOR_ENV": "eval",
        "DEEPTUTOR_PROMPT_VERSION": "eval-gate",
        "DEEPTUTOR_FF_SNAPSHOT_HASH": "eval-gate",
        "DEEPTUTOR_GIT_DIRTY": "false",
        "DEEPTUTOR_DEPLOY_MANIFEST_HASH": f"eval-gate-{artifact_name}",
        "DEEPTUTOR_RELEASE_ID": f"eval-gate-{artifact_name}",
    }


def _env_for_gate(gate: Gate, *, artifact_dir: Path) -> dict[str, str]:
    env = _env_with_project_root()
    format_values = {
        "artifact_dir": str(artifact_dir),
        "artifact_dir_name": artifact_dir.name,
        "project_root": str(PROJECT_ROOT),
    }
    env.update(_default_eval_env(artifact_dir=artifact_dir))
    env.update({key: value.format(**format_values) for key, value in gate.env.items()})
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


def _release_gate_payload_path(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        if line.startswith("JSON:"):
            path_text = line.split(":", 1)[1].strip()
            return Path(path_text) if path_text else None
    return None


def _release_gate_payload_status(stdout: str) -> dict[str, Any]:
    payload_path = _release_gate_payload_path(stdout)
    if payload_path is None:
        return {
            "status": "FAIL",
            "reason": "release gate payload path missing",
            "failure_signature": "release_gate_report_only_payload_missing",
        }
    try:
        raw_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "reason": f"release gate payload unreadable: {exc}",
            "failure_signature": "release_gate_report_only_payload_unreadable",
        }

    payload = raw_payload.get("payload") if isinstance(raw_payload.get("payload"), dict) else raw_payload
    final_status = str(payload.get("final_status") or "").upper()
    if final_status not in {"PASS", "WARN", "FAIL"}:
        return {
            "status": "FAIL",
            "reason": f"release gate final_status invalid: {final_status or '<empty>'}",
            "failure_signature": "release_gate_report_only_payload_invalid",
            "release_gate_json_path": str(payload_path),
        }
    recommendation = str(payload.get("recommendation") or "")
    blockers = [str(item) for item in payload.get("blockers") or []]
    reason_parts = [f"release gate final_status={final_status}"]
    if recommendation:
        reason_parts.append(f"recommendation={recommendation}")
    if blockers:
        reason_parts.append("blockers=" + ",".join(blockers))
    return {
        "status": final_status,
        "reason": "; ".join(reason_parts),
        **(
            {"failure_signature": "release_gate_report_only_hold"}
            if final_status == "FAIL"
            else {}
        ),
        "release_gate_final_status": final_status,
        "release_gate_recommendation": recommendation,
        "release_gate_blockers": blockers,
        "release_gate_json_path": str(payload_path),
    }


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
    try:
        completed = subprocess.run(
            command,
            cwd=gate.workdir,
            env=_env_for_gate(gate, artifact_dir=artifact_dir),
            text=True,
            capture_output=True,
            check=False,
            timeout=gate.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration_s = round(time.monotonic() - started, 3)
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        reason = f"timeout after {gate.timeout_seconds:g}s"
        _write_log(log_path, stdout=f"TIMEOUT: {reason}\n{stdout}".rstrip(), stderr=stderr)
        return {
            "name": gate.name,
            "description": gate.description,
            "category": gate.category,
            "status": "FAIL",
            "exit_code": None,
            "duration_s": duration_s,
            "command": command,
            "workdir": str(gate.workdir),
            "reason": reason,
            "failure_signature": "gate_timeout",
            "log_path": str(log_path),
        }

    duration_s = round(time.monotonic() - started, 3)
    _write_log(log_path, stdout=completed.stdout, stderr=completed.stderr)
    slow_threshold = gate.slow_seconds
    slow = slow_threshold is not None and duration_s >= slow_threshold
    payload_status = (
        _release_gate_payload_status(completed.stdout)
        if gate.name == "release_gate_report_only" and completed.returncode == 0
        else None
    )
    return {
        "name": gate.name,
        "description": gate.description,
        "category": gate.category,
        "status": payload_status["status"] if payload_status else ("PASS" if completed.returncode == 0 else "FAIL"),
        "exit_code": completed.returncode,
        "duration_s": duration_s,
        "command": command,
        "workdir": str(gate.workdir),
        "log_path": str(log_path),
        **(payload_status or {}),
        **({"slow": True, "slow_threshold_s": slow_threshold} if slow else {}),
    }


def _build_summary(results: list[dict[str, Any]], *, gates_path: Path, artifact_dir: Path) -> dict[str, Any]:
    counts = {
        "passed": sum(1 for item in results if item["status"] == "PASS"),
        "failed": sum(1 for item in results if item["status"] == "FAIL"),
        "warned": sum(1 for item in results if item["status"] == "WARN"),
        "deferred": sum(1 for item in results if item["status"] == "DEFERRED"),
        "slow": sum(1 for item in results if item.get("slow")),
    }
    slow_gates = [
        {
            "name": item["name"],
            "duration_s": item["duration_s"],
            "slow_threshold_s": item.get("slow_threshold_s"),
            "status": item["status"],
        }
        for item in results
        if item.get("slow")
    ]
    verdict = (
        "FAIL"
        if counts["failed"]
        else "WARN"
        if counts["warned"] or counts["deferred"]
        else "PASS"
    )
    return {
        "run_id": artifact_dir.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "gates_path": str(gates_path),
        "artifact_dir": str(artifact_dir),
        "verdict": verdict,
        "summary": counts,
        "slow_gates": slow_gates,
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
        f"- slow: {summary['summary'].get('slow', 0)}",
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
    if summary.get("slow_gates"):
        lines.extend(["", "## Slow Gates", ""])
        for gate in summary["slow_gates"]:
            lines.append(
                f"- `{gate['name']}`: {gate['duration_s']}s"
                f" >= {gate.get('slow_threshold_s')}s | status={gate['status']}"
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
    parser.add_argument(
        "--category",
        default="",
        help="Only run gates whose category matches (e.g. 'quick' for the "
        "hermetic, no-key, no-network set the observability cron runs). "
        "Empty = every gate.",
    )
    args = parser.parse_args()

    gates_path = _resolve_project_path(args.gates_path)
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else _default_artifact_dir()
    gates = _execution_order(load_gates(gates_path))
    if args.category:
        gates = [gate for gate in gates if gate.category == args.category]

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
