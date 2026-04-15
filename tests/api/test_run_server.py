from __future__ import annotations

import importlib

import pytest

run_server = importlib.import_module("deeptutor.api.run_server")


def _capture_uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(run_server.uvicorn, "run", _fake_run)
    monkeypatch.setattr(run_server.os, "chdir", lambda *_args, **_kwargs: None)
    return captured


def test_run_server_disables_reload_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_uvicorn_run(monkeypatch)
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setattr(
        "deeptutor.services.setup.get_backend_port",
        lambda *_args, **_kwargs: 8123,
    )

    run_server.main()

    assert captured["app"] == "deeptutor.api.main:app"
    kwargs = captured["kwargs"]
    assert kwargs["reload"] is False
    assert kwargs["port"] == 8123
    assert "reload_excludes" not in kwargs


def test_run_server_enables_reload_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_uvicorn_run(monkeypatch)
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setattr(
        "deeptutor.services.setup.get_backend_port",
        lambda *_args, **_kwargs: 8124,
    )

    run_server.main()

    assert captured["app"] == "deeptutor.api.main:app"
    kwargs = captured["kwargs"]
    assert kwargs["reload"] is True
    assert kwargs["port"] == 8124
    assert isinstance(kwargs["reload_excludes"], list)
    assert "access_log" in kwargs and kwargs["access_log"] is False
