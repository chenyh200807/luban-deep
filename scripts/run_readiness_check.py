#!/usr/bin/env python3
"""Run or record launch-readiness evidence into the observability control plane."""

from __future__ import annotations

import argparse
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


def _default_command(check_id: str, changed_files: list[str]) -> list[str]:
    if check_id == "contract_guard":
        return [sys.executable, str(PROJECT_ROOT / "scripts" / "check_contract_guard.py"), *changed_files]
    raise ValueError(f"--command is required for {check_id}")


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _summary_from_result(check_id: str, result: subprocess.CompletedProcess[str] | None, summary: str) -> str:
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
) -> list[str]:
    evidence = list(explicit_evidence)
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
    status = args.status or ("PASS" if result and result.returncode == 0 else "FAIL" if result else "WARN")
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
        ),
        "blockers": [f"{args.check_id}_failed"] if status == "FAIL" else [],
        "release": release,
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
