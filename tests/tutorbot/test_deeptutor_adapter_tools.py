from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from deeptutor.tutorbot.agent.tools.deeptutor_tools import CodeExecutionAdapterTool


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> types.ModuleType:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                monkeypatch.setattr(parent, parts[idx - 1], pkg, raising=False)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)
    return module


@pytest.mark.asyncio
async def test_code_execution_adapter_rejects_non_positive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_code(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("run_code should not be called for invalid timeout")

    _install_module(monkeypatch, "deeptutor.tools.code_executor", run_code=fake_run_code)

    result = await CodeExecutionAdapterTool().execute(code="print(1)", timeout=0)

    assert "Error:" in result
    assert "timeout" in result
    assert "positive integer" in result


@pytest.mark.asyncio
async def test_code_execution_adapter_defaults_missing_timeout_to_30(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_code(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"stdout": "ok\n", "stderr": "", "exit_code": 0}

    _install_module(monkeypatch, "deeptutor.tools.code_executor", run_code=fake_run_code)

    result = await CodeExecutionAdapterTool().execute(code="print('ok')")

    assert result == "ok"
    assert captured["timeout"] == 30
