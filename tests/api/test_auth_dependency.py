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

    # Keep the identity-alias store unconfigured so the auth flow never hits
    # live Supabase. Developer .env files (re-injected by EnvStore.load via
    # os.environ.setdefault) otherwise populate SUPABASE_URL/KEY and make
    # store.resolve_alias issue a real REST call. This test only asserts
    # log-context reset, not identity resolution, so the live store is
    # incidental — stub it out for hermetic behaviour locally and in CI.
    class _UnconfiguredIdentityStore:
        is_configured = False

        def resolve_alias(self, *, alias_type: str, alias_value: str):
            return None

    monkeypatch.setattr(
        auth_module,
        "get_wallet_identity_store",
        lambda: _UnconfiguredIdentityStore(),
    )

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
