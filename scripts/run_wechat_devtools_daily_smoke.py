#!/usr/bin/env python3
"""Run the daily WeChat DevTools CLI smoke for the primary Yousen package."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVTOOLS_CLI = Path(
    os.environ.get("WX_DEVTOOLS_CLI") or "/Applications/wechatwebdevtools.app/Contents/MacOS/cli"
)
DEFAULT_PROJECT_PATH = PROJECT_ROOT / "yousenwebview"
TARGET_SUBPACKAGE = "packageDeeptutor"
RUNTIME_BASE_CONTRACT = PROJECT_ROOT / "yousenwebview" / "tests" / "test_app_runtime_base_selection.js"


def _command_record(
    *,
    name: str,
    command: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "ok": False,
            "command": " ".join(command),
            "timeout_seconds": timeout_seconds,
            "error": f"timeout: {exc.cmd}",
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return {
        "name": name,
        "ok": completed.returncode == 0,
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "stdout": stdout[:1200],
        "stderr": stderr[:1200],
    }


def _login_ok(record: dict[str, Any]) -> bool:
    if not record.get("ok"):
        return False
    compact = str(record.get("stdout") or "").replace(" ", "").lower()
    return '"login":true' in compact or "'login':true" in compact


def _auth_boundary_from_devtools_login(login: dict[str, Any]) -> dict[str, str]:
    devtools_logged_in = _login_ok(login)
    return {
        "devtools_account_login_state": "logged_in" if devtools_logged_in else "auth_blocked",
        "auth_state": "auth_blocked" if not devtools_logged_in else "unknown",
        "auth_mode": "none",
    }


def _readiness_boundary(*, preflight_ok: bool) -> dict[str, Any]:
    if not preflight_ok:
        return {
            "readiness_status": "FAIL",
            "scenario_evidence_status": "not_run",
            "readiness_blockers": ["wechat_devtools_failed"],
        }
    return {
        "readiness_status": "WARN",
        "scenario_evidence_status": "pending",
        "readiness_blockers": ["wechat_devtools_true_entry_pending"],
    }


def _coverage_targets() -> list[str]:
    return [
        "real mini-program container",
        "project config",
        "page stack bootstrap",
        "network baseURL selection",
        "WebSocket surface exposure",
        "DevTools storage/cache surface",
        "DevTools login state",
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    project_path = Path(args.project_path).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    if not DEVTOOLS_CLI.exists():
        return {
            "ok": False,
            "run_id": f"wechat-devtools-daily-smoke-{int(time.time())}",
            "entry_surface": "real_wechat_package",
            "trace_source": "devtools_cli_open",
            "project_path": str(project_path),
            "target_subpackage": TARGET_SUBPACKAGE,
            "devtools_account_login_state": "unknown",
            "auth_state": "unknown",
            "auth_mode": "none",
            **_readiness_boundary(preflight_ok=False),
            "error": f"WeChat DevTools CLI not found: {DEVTOOLS_CLI}",
            "coverage_targets": _coverage_targets(),
        }

    if not project_path.exists():
        return {
            "ok": False,
            "run_id": f"wechat-devtools-daily-smoke-{int(time.time())}",
            "entry_surface": "real_wechat_package",
            "trace_source": "devtools_cli_open",
            "project_path": str(project_path),
            "target_subpackage": TARGET_SUBPACKAGE,
            "devtools_account_login_state": "unknown",
            "auth_state": "unknown",
            "auth_mode": "none",
            **_readiness_boundary(preflight_ok=False),
            "error": f"WeChat project path not found: {project_path}",
            "coverage_targets": _coverage_targets(),
        }

    if not args.skip_runtime_contract:
        checks.append(
            _command_record(
                name="yousen_runtime_base_contract",
                command=["node", str(RUNTIME_BASE_CONTRACT)],
                timeout_seconds=args.timeout_seconds,
            )
        )

    login = _command_record(
        name="devtools_islogin",
        command=[str(DEVTOOLS_CLI), "islogin"],
        timeout_seconds=args.timeout_seconds,
    )
    login["ok"] = _login_ok(login)
    if not login["ok"] and not login.get("error"):
        login["error"] = "DevTools CLI islogin did not report login=true"
    checks.append(login)

    checks.append(
        _command_record(
            name="devtools_open_project",
            command=[str(DEVTOOLS_CLI), "open", "--project", str(project_path), "--lang", "zh"],
            timeout_seconds=args.timeout_seconds,
        )
    )

    if int(args.auto_port or 0) > 0:
        checks.append(
            _command_record(
                name="devtools_auto_port",
                command=[
                    str(DEVTOOLS_CLI),
                    "auto",
                    "--project",
                    str(project_path),
                    "--auto-port",
                    str(int(args.auto_port)),
                ],
                timeout_seconds=args.timeout_seconds,
            )
        )

    ok = all(bool(check.get("ok")) for check in checks)
    auth_boundary = _auth_boundary_from_devtools_login(login)
    return {
        "ok": ok,
        "run_id": f"wechat-devtools-daily-smoke-{int(time.time())}",
        "entry_surface": "real_wechat_package",
        "trace_source": "devtools_cli_open",
        "project_path": str(project_path),
        "target_subpackage": TARGET_SUBPACKAGE,
        **auth_boundary,
        **_readiness_boundary(preflight_ok=ok),
        "devtools_cli": str(DEVTOOLS_CLI),
        "coverage_targets": _coverage_targets(),
        "evidence_boundary": (
            "DevTools CLI smoke covers project-open/runtime-base preflight; page-level "
            "scenario pass and app auth still require automator or manual page evidence."
        ),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily WeChat DevTools CLI smoke")
    parser.add_argument("--project-path", default=str(DEFAULT_PROJECT_PATH))
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--auto-port",
        type=int,
        default=0,
        help="Optionally enable DevTools automation on this port after opening the project.",
    )
    parser.add_argument("--skip-runtime-contract", action="store_true")
    args = parser.parse_args()

    payload = run(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
