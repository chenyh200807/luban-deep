#!/usr/bin/env python3
"""Run or record launch-readiness evidence into the observability control plane."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot  # noqa: E402

ALLOWED_CHECK_IDS = {"contract_guard", "playwright", "wechat_devtools"}
ALLOWED_STATUS = {"PASS", "WARN", "FAIL", "SKIP"}
WECHAT_DEVTOOLS_DAILY_SMOKE = PROJECT_ROOT / "scripts" / "run_wechat_devtools_daily_smoke.py"


def _default_command(check_id: str, changed_files: list[str]) -> list[str]:
    if check_id == "contract_guard":
        return [sys.executable, str(PROJECT_ROOT / "scripts" / "check_contract_guard.py"), *changed_files]
    if check_id == "wechat_devtools":
        return [sys.executable, str(WECHAT_DEVTOOLS_DAILY_SMOKE)]
    raise ValueError(f"--command is required for {check_id}")


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _json_stdout_payload(result: subprocess.CompletedProcess[str] | None) -> dict:
    if result is None:
        return {}
    stdout = (result.stdout or "").strip()
    if not stdout:
        return {}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_from_result(
    *,
    check_id: str,
    result: subprocess.CompletedProcess[str] | None,
    explicit_status: str | None,
) -> str:
    if explicit_status:
        return explicit_status
    if result is None:
        return "WARN"
    if result.returncode != 0:
        return "FAIL"
    if check_id == "wechat_devtools":
        structured_status = (
            str(_json_stdout_payload(result).get("readiness_status") or "")
            .strip()
            .upper()
        )
        if structured_status in ALLOWED_STATUS:
            return structured_status
    return "PASS"


def _structured_readiness_metadata(
    *,
    check_id: str,
    result: subprocess.CompletedProcess[str] | None,
) -> dict:
    if check_id != "wechat_devtools":
        return {}
    payload = _json_stdout_payload(result)
    if not payload:
        return {}
    metadata: dict[str, object] = {}
    for key in (
        "entry_surface",
        "trace_source",
        "project_path",
        "target_subpackage",
        "target_page",
        "devtools_account_login_state",
        "auth_state",
        "auth_mode",
        "scenario_evidence_status",
        "evidence_boundary",
    ):
        value = payload.get(key)
        if value is not None:
            metadata[key] = str(value)
    blockers = payload.get("readiness_blockers")
    if isinstance(blockers, list):
        metadata["readiness_blockers"] = [str(item) for item in blockers]
    return metadata


def _blockers_for_status(
    *,
    check_id: str,
    status: str,
    structured_blockers: list[str],
) -> list[str]:
    if structured_blockers:
        return structured_blockers
    if status == "FAIL":
        return [f"{check_id}_failed"]
    return []


def _summary_from_result(
    check_id: str,
    result: subprocess.CompletedProcess[str] | None,
    summary: str,
) -> str:
    if summary:
        return summary
    if result is None:
        return f"{check_id} recorded"
    if result.returncode == 0:
        return f"{check_id} command passed"
    return f"{check_id} command failed with exit_code={result.returncode}"


def _evidence_lines(
    *,
    command: list[str],
    result: subprocess.CompletedProcess[str] | None,
    explicit_evidence: list[str],
    max_output_chars: int,
    structured_metadata: dict | None = None,
) -> list[str]:
    evidence = list(explicit_evidence)
    for key, value in (structured_metadata or {}).items():
        if key == "readiness_blockers":
            continue
        evidence.append(f"{key}={value}")
    if command:
        evidence.append(f"command={' '.join(command)}")
    if result is not None:
        evidence.append(f"exit_code={result.returncode}")
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stdout:
            evidence.append(f"stdout={stdout[:max_output_chars]}")
        if stderr:
            evidence.append(f"stderr={stderr[:max_output_chars]}")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Record DeepTutor launch readiness evidence")
    parser.add_argument("--check-id", choices=sorted(ALLOWED_CHECK_IDS), required=True)
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUS), help="Override command-derived status")
    parser.add_argument("--summary", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--max-output-chars", type=int, default=1200)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Record the check but do not fail the process when status is FAIL.",
    )
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="Command to run and record")
    args = parser.parse_args()

    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command and not args.status:
        command = _default_command(args.check_id, args.changed_file)

    result = _run_command(command) if command else None
    status = _status_from_result(check_id=args.check_id, result=result, explicit_status=args.status)
    structured_metadata = _structured_readiness_metadata(check_id=args.check_id, result=result)
    structured_blockers = [str(item) for item in structured_metadata.pop("readiness_blockers", [])]
    release = get_release_lineage_snapshot()
    payload = {
        "run_id": f"{args.check_id}-{int(time.time())}",
        "check_id": args.check_id,
        "label": args.check_id.replace("_", " ").title(),
        "status": status,
        "required": True,
        "summary": _summary_from_result(args.check_id, result, args.summary),
        "evidence": _evidence_lines(
            command=command,
            result=result,
            explicit_evidence=args.evidence,
            max_output_chars=max(200, int(args.max_output_chars or 1200)),
            structured_metadata=structured_metadata,
        ),
        "blockers": _blockers_for_status(
            check_id=args.check_id,
            status=status,
            structured_blockers=structured_blockers,
        ),
        "release": release,
        **structured_metadata,
    }
    store_paths = get_control_plane_store().write_run(
        kind="readiness_checks",
        run_id=payload["run_id"],
        release_id=str(release.get("release_id") or ""),
        payload=payload,
    )

    print(f"Readiness check recorded: {payload['run_id']}")
    print(f"Check: {payload['check_id']}")
    print(f"Status: {payload['status']}")
    print(f"JSON: {store_paths['json_path']}")
    if status == "FAIL" and not args.report_only:
        raise SystemExit(f"readiness_check_failed: check_id={args.check_id}")


if __name__ == "__main__":
    main()
