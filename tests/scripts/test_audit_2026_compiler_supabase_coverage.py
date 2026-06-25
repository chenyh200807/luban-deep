from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "audit_2026_compiler_supabase_coverage.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "audit_2026_compiler_supabase_coverage",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_refuses_main_db_without_explicit_allow_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    monkeypatch.setattr(sys, "argv", ["audit_2026_compiler_supabase_coverage.py", "--run-id", "test-run"])

    code = module.main()

    captured = capsys.readouterr()
    assert code == 2
    assert "--allow-main-db" in captured.err
