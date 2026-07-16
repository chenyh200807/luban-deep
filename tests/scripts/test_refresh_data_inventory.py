from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "refresh_data_inventory.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("refresh_data_inventory", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_plan_shares_one_timestamp_and_keeps_dependency_order():
    script = _load_script()
    generated_at = "2026-07-16T13:30:44+08:00"

    commands = [script.command_for(name, generated_at) for name in script.STEP_SCRIPTS]

    assert script.STEP_SCRIPTS[0] == "profile_raw_data_assets.py"
    assert script.STEP_SCRIPTS[-1] == "profile_compiled_assets.py"
    assert script.STEP_SCRIPTS.index("build_data_asset_brief.py") < script.STEP_SCRIPTS.index("build_asset_gap_map.py")
    assert script.STEP_SCRIPTS.index("build_topic_okf.py") < script.STEP_SCRIPTS.index("build_okf_bundle.py")
    assert all(command[-2:] == ["--generated-at", generated_at] for command in commands)


def test_refresh_stops_at_first_failed_builder(tmp_path, monkeypatch):
    script = _load_script()
    manifest_path = tmp_path / "latest_refresh_manifest.json"
    calls = []

    monkeypatch.setattr(script, "STEP_SCRIPTS", ("first.py", "must_not_run.py"))
    monkeypatch.setattr(script, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(script, "git_output", lambda *args: "main" if args[:2] == ("branch", "--show-current") else "deadbeef")

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7, stdout="synthetic failure")

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    result = script.main(["--generated-at", "2026-07-16T13:30:44+08:00"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result == 7
    assert len(calls) == 1
    assert calls[0][1].endswith("first.py")
    assert manifest["status"] == "failed"
    assert manifest["failed_step"] == "first.py"
    assert manifest["steps"] == [{"script": "first.py", "exit_code": 7}]
