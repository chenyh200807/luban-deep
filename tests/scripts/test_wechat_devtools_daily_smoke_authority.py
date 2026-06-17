from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_wechat_devtools_daily_smoke.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("run_wechat_devtools_daily_smoke", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Args:
    project_path = str(PROJECT_ROOT / "yousenwebview")
    timeout_seconds = 1.0
    auto_port = 0
    page_wait_ms = 12000
    skip_runtime_contract = False


class _FakeCliPath:
    def exists(self) -> bool:
        return True

    def __str__(self) -> str:
        return "/fake/wechatwebdevtools/cli"


def test_devtools_smoke_names_yousenwebview_as_only_real_wechat_project_root(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "DEVTOOLS_CLI", _FakeCliPath())

    def fake_command_record(*, name: str, command: list[str], timeout_seconds: float) -> dict[str, Any]:
        if name == "devtools_islogin":
            return {"name": name, "ok": True, "stdout": '{"login": true}', "stderr": "", "exit_code": 0}
        return {"name": name, "ok": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(mod, "_command_record", fake_command_record)

    payload = mod.run(_Args())

    assert payload["entry_surface"] == "real_wechat_package"
    assert payload["devtools_project_root"] == "yousenwebview"
    assert payload["project_path"].endswith("/yousenwebview")
    assert payload["target_subpackage"] == "packageDeeptutor"
    assert payload["target_page"] == "/packageDeeptutor/pages/report/report"
    assert payload["entry_flow"] == "direct_subpackage_page"
    assert payload["scenario_evidence_status"] == "pending"
    assert payload["readiness_status"] == "WARN"
    assert "page_scenario_pending" in payload["readiness_blockers"]


def test_devtools_smoke_can_record_page_automation_pass_without_promoting_project_open(
    monkeypatch,
) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "DEVTOOLS_CLI", _FakeCliPath())
    commands: dict[str, list[str]] = {}

    def fake_command_record(*, name: str, command: list[str], timeout_seconds: float) -> dict[str, Any]:
        commands[name] = command
        if name == "devtools_islogin":
            return {"name": name, "ok": True, "stdout": '{"login": true}', "stderr": "", "exit_code": 0}
        if name == "devtools_page_automation":
            return {
                "name": name,
                "ok": True,
                "stdout": '{"ok": true, "current_page": "/packageDeeptutor/pages/report/report"}',
                "stderr": "",
                "exit_code": 0,
            }
        return {"name": name, "ok": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(mod, "_command_record", fake_command_record)
    args = _Args()
    args.auto_port = 9420

    payload = mod.run(args)

    assert payload["readiness_status"] == "PASS"
    assert payload["scenario_evidence_status"] == "passed"
    assert payload["trace_source"] == "devtools_cli_auto_page"
    assert payload["page_automation"]["current_page"] == "/packageDeeptutor/pages/report/report"
    assert payload["devtools_project_root"] == "yousenwebview"
    assert commands["devtools_auto_port"][-2:] == ["--auto-port", "9420"]
    assert commands["devtools_page_automation"][-4:] == [
        "--base-url",
        "http://127.0.0.1:8001",
        "--wait-ms",
        "12000",
    ]


def test_devtools_smoke_records_login_redirect_as_auth_blocked_evidence(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "DEVTOOLS_CLI", _FakeCliPath())

    def fake_command_record(*, name: str, command: list[str], timeout_seconds: float) -> dict[str, Any]:
        if name == "devtools_islogin":
            return {"name": name, "ok": True, "stdout": '{"login": true}', "stderr": "", "exit_code": 0}
        if name == "devtools_page_automation":
            return {
                "name": name,
                "ok": False,
                "stdout": '{"ok": false, "current_page": "packageDeeptutor/pages/login/login"}',
                "stderr": "",
                "exit_code": 1,
            }
        return {"name": name, "ok": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(mod, "_command_record", fake_command_record)
    args = _Args()
    args.auto_port = 9420

    payload = mod.run(args)

    assert payload["ok"] is True
    assert payload["readiness_status"] == "WARN"
    assert payload["scenario_evidence_status"] == "auth_blocked"
    assert payload["auth_state"] == "auth_blocked"
    assert payload["auth_mode"] == "real_wechat"
    assert payload["trace_source"] == "devtools_cli_auto_page"
    assert "wechat_auth_required_for_target_page" in payload["readiness_blockers"]
    assert payload["page_automation"]["current_page"] == "packageDeeptutor/pages/login/login"


def test_devtools_smoke_records_failed_password_login_as_auth_failed_evidence(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "DEVTOOLS_CLI", _FakeCliPath())

    def fake_command_record(*, name: str, command: list[str], timeout_seconds: float) -> dict[str, Any]:
        if name == "devtools_islogin":
            return {"name": name, "ok": True, "stdout": '{"login": true}', "stderr": "", "exit_code": 0}
        if name == "devtools_auto_port":
            return {"name": name, "ok": False, "stdout": "", "stderr": "already running", "exit_code": 255}
        if name == "devtools_page_automation":
            return {
                "name": name,
                "ok": False,
                "stdout": (
                    '{"ok": false, "auth_attempted": true, "credential_source": "env", '
                    '"login_error_present": true, "current_page": "packageDeeptutor/pages/login/manual"}'
                ),
                "stderr": "",
                "exit_code": 1,
            }
        return {"name": name, "ok": True, "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(mod, "_command_record", fake_command_record)
    args = _Args()
    args.auto_port = 9420

    payload = mod.run(args)

    assert payload["ok"] is False
    assert payload["readiness_status"] == "FAIL"
    assert payload["scenario_evidence_status"] == "auth_failed"
    assert payload["auth_state"] == "auth_failed"
    assert payload["auth_mode"] == "real_wechat"
    assert payload["trace_source"] == "devtools_cli_auto_page"
    assert "wechat_password_login_failed" in payload["readiness_blockers"]
