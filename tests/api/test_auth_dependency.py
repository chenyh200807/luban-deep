from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deeptutor.logging.context import get_log_context


def test_get_current_user_resets_bound_user_context_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_module = importlib.import_module("deeptutor.api.dependencies.auth")

    class _FakeMemberConsoleService:
        def verify_access_token(self, token: str):
            if token != "admin-token":
                return None
            return {"uid": "admin_demo", "provider": "test"}

        def is_admin_user(self, user_id: str) -> bool:
            return user_id == "admin_demo"

    monkeypatch.setattr(
        auth_module,
        "get_member_console_service",
        lambda: _FakeMemberConsoleService(),
    )

    app = FastAPI()

    @app.get("/_auth_probe")
    async def _auth_probe(_current_user=Depends(auth_module.get_current_user)):
        return get_log_context()

    @app.get("/_log_context_probe")
    async def _log_context_probe():
        return get_log_context()

    with TestClient(app) as client:
        authenticated = client.get(
            "/_auth_probe",
            headers={"Authorization": "Bearer admin-token"},
        )
        after = client.get("/_log_context_probe")

    assert authenticated.status_code == 200
    assert authenticated.json()["user_id"] == "admin_demo"
    assert after.status_code == 200
    assert after.json()["user_id"] == ""
