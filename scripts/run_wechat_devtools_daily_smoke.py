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
DEVTOOLS_PROJECT_ROOT = "yousenwebview"
TARGET_PAGE = "/packageDeeptutor/pages/report/report"
ENTRY_FLOW = "direct_subpackage_page"
RUNTIME_BASE_CONTRACT = PROJECT_ROOT / "yousenwebview" / "tests" / "test_app_runtime_base_selection.js"
PAGE_AUTOMATION = PROJECT_ROOT / "scripts" / "run_wechat_devtools_page_automation.js"


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


def _auth_boundary_from_devtools_login(
    login: dict[str, Any],
    *,
    page_auth_blocked: bool = False,
    page_auth_failed: bool = False,
) -> dict[str, str]:
    devtools_logged_in = _login_ok(login)
    if page_auth_failed:
        auth_state = "auth_failed"
    elif page_auth_blocked or not devtools_logged_in:
        auth_state = "auth_blocked"
    else:
        auth_state = "unknown"
    return {
        "devtools_account_login_state": "logged_in" if devtools_logged_in else "auth_blocked",
        "auth_state": auth_state,
        "auth_mode": "real_wechat" if page_auth_blocked or page_auth_failed else "none",
    }


def _readiness_boundary(
    *,
    preflight_ok: bool,
    page_automation_ok: bool = False,
    page_auth_blocked: bool = False,
    page_auth_failed: bool = False,
) -> dict[str, Any]:
    if not preflight_ok:
        return {
            "readiness_status": "FAIL",
            "scenario_evidence_status": "not_run",
            "readiness_blockers": ["wechat_devtools_failed"],
        }
    if page_auth_failed:
        return {
            "readiness_status": "FAIL",
            "scenario_evidence_status": "auth_failed",
            "readiness_blockers": ["wechat_password_login_failed"],
        }
    if page_auth_blocked:
        return {
            "readiness_status": "WARN",
            "scenario_evidence_status": "auth_blocked",
            "readiness_blockers": ["wechat_auth_required_for_target_page"],
        }
    if page_automation_ok:
        return {
            "readiness_status": "PASS",
            "scenario_evidence_status": "passed",
            "readiness_blockers": [],
        }
    return {
        "readiness_status": "WARN",
        "scenario_evidence_status": "pending",
        "readiness_blockers": ["page_scenario_pending"],
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


def _json_stdout(record: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(str(record.get("stdout") or "").strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_page_path(page_path: Any) -> str:
    raw = str(page_path or "").strip()
    return raw if raw.startswith("/") else f"/{raw}" if raw else ""


def _page_automation_auth_blocked(payload: dict[str, Any]) -> bool:
    current_page = _normalize_page_path(payload.get("current_page"))
    return current_page == "/packageDeeptutor/pages/login/login"


def _page_automation_auth_failed(payload: dict[str, Any]) -> bool:
    return bool(payload.get("auth_attempted") and payload.get("login_error_present"))


def run(args: argparse.Namespace) -> dict[str, Any]:
    project_path = Path(args.project_path).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    if not DEVTOOLS_CLI.exists():
        return {
            "ok": False,
            "run_id": f"wechat-devtools-daily-smoke-{int(time.time())}",
            "entry_surface": "real_wechat_package",
            "trace_source": "devtools_cli_open",
            "devtools_project_root": DEVTOOLS_PROJECT_ROOT,
            "project_path": str(project_path),
            "target_subpackage": TARGET_SUBPACKAGE,
            "target_page": TARGET_PAGE,
            "entry_flow": ENTRY_FLOW,
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
            "devtools_project_root": DEVTOOLS_PROJECT_ROOT,
            "project_path": str(project_path),
            "target_subpackage": TARGET_SUBPACKAGE,
            "target_page": TARGET_PAGE,
            "entry_flow": ENTRY_FLOW,
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
                    "--port",
                    str(int(args.auto_port)),
                ],
                timeout_seconds=args.timeout_seconds,
            )
        )
        checks.append(
            _command_record(
                name="devtools_page_automation",
                command=[
                    "node",
                    str(PAGE_AUTOMATION),
                    "--port",
                    str(int(args.auto_port)),
                    "--target-page",
                    TARGET_PAGE,
                ],
                timeout_seconds=args.timeout_seconds,
            )
        )

    page_automation = next((check for check in checks if check.get("name") == "devtools_page_automation"), None)
    page_automation_payload = _json_stdout(page_automation or {})
    page_automation_ran = bool(page_automation and page_automation_payload)
    preflight_checks = [
        check
        for check in checks
        if check.get("name") not in {"devtools_page_automation", "devtools_auto_port"}
    ]
    if page_automation_ran:
        preflight_ok = all(bool(check.get("ok")) for check in preflight_checks)
    else:
        preflight_ok = all(
            bool(check.get("ok")) for check in checks if check.get("name") != "devtools_page_automation"
        )
    page_automation_ok = bool(
        page_automation
        and page_automation.get("ok")
        and page_automation_payload.get("ok") is True
        and _normalize_page_path(page_automation_payload.get("current_page")) == TARGET_PAGE
    )
    page_auth_blocked = bool(page_automation and _page_automation_auth_blocked(page_automation_payload))
    page_auth_failed = bool(page_automation and _page_automation_auth_failed(page_automation_payload))
    ok = preflight_ok and (not page_automation or page_automation_ok or page_auth_blocked)
    auth_boundary = _auth_boundary_from_devtools_login(
        login,
        page_auth_blocked=page_auth_blocked,
        page_auth_failed=page_auth_failed,
    )
    return {
        "ok": ok,
        "run_id": f"wechat-devtools-daily-smoke-{int(time.time())}",
        "entry_surface": "real_wechat_package",
        "trace_source": (
            "devtools_cli_auto_page"
            if page_automation_ok or page_auth_blocked or page_auth_failed
            else "devtools_cli_open"
        ),
        "devtools_project_root": DEVTOOLS_PROJECT_ROOT,
        "project_path": str(project_path),
        "target_subpackage": TARGET_SUBPACKAGE,
        "target_page": TARGET_PAGE,
        "entry_flow": ENTRY_FLOW,
        **auth_boundary,
        **_readiness_boundary(
            preflight_ok=preflight_ok,
            page_automation_ok=page_automation_ok,
            page_auth_blocked=page_auth_blocked,
            page_auth_failed=page_auth_failed,
        ),
        "devtools_cli": str(DEVTOOLS_CLI),
        "coverage_targets": _coverage_targets(),
        "evidence_boundary": (
            "DevTools CLI islogin/open covers only environment preflight; page-level scenario "
            "PASS requires devtools_page_automation on the yousenwebview project root."
        ),
        "page_automation": page_automation_payload if page_automation else None,
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
