"""Unit tests for PR-1a SR1 secure_router factory.

Verifies the contract documented in `deeptutor/api/_secure_router.py`:
- `secure_router(...)` returns an APIRouter with `Depends(get_current_user)` at router level
- `secure_ws_router(...)` returns a WS-only APIRouter without router-level dependencies
- `public_router(reason=...)` requires non-trivial reason; stores it on router
- `secure_ws_endpoint(ws, ...)` rate-limits THEN auths; returns None on either failure
- `_public_manifest.is_public()` correctly maps paths to reasons

PR-1a does NOT migrate any routers; PR-1b does. These tests guard the factory
contract itself.
"""
from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends

from deeptutor.api._public_manifest import PUBLIC_PATHS, is_public
from deeptutor.api._secure_router import (
    AuthContext,
    public_router,
    secure_router,
    secure_ws_router,
)


class TestSecureRouter:
    def test_secure_router_has_get_current_user_dep(self):
        r = secure_router(prefix="/x")
        assert isinstance(r, APIRouter)
        # FastAPI stores deps on the router; check we wired at least one.
        # The exact attribute is internal; verify by inspecting deps.
        assert len(r.dependencies) >= 1, "secure_router must inject auth dep"
        names = [getattr(d.dependency, "__name__", "?") for d in r.dependencies]
        assert "get_current_user" in names, f"expected get_current_user in {names}"

    def test_secure_router_stacks_extra_deps(self):
        def custom_dep() -> None:
            return None

        r = secure_router(prefix="/x", extra_dependencies=[Depends(custom_dep)])
        names = [getattr(d.dependency, "__name__", "?") for d in r.dependencies]
        # get_current_user must come FIRST (so admin/self_or_admin can layer on it)
        assert names[0] == "get_current_user"
        assert "custom_dep" in names

    def test_secure_ws_router_has_no_router_level_auth_dependency(self):
        r = secure_ws_router(prefix="/x")
        assert isinstance(r, APIRouter)
        assert r.dependencies == []
        assert getattr(r, "__secure_ws_router__", None) is True


class TestPublicRouter:
    def test_public_router_rejects_empty_reason(self):
        with pytest.raises(ValueError, match="non-trivial reason"):
            public_router(prefix="/x", reason="")

    def test_public_router_rejects_short_reason(self):
        with pytest.raises(ValueError, match="non-trivial reason"):
            public_router(prefix="/x", reason="short")  # < 12 chars

    def test_public_router_accepts_valid_reason(self):
        r = public_router(prefix="/x", reason="anonymous registration form")
        assert isinstance(r, APIRouter)
        # No auth dep — that's the whole point
        names = [getattr(d.dependency, "__name__", "?") for d in r.dependencies]
        assert "get_current_user" not in names
        # Reason stored as introspectable marker
        assert getattr(r, "__public_reason__", None) == "anonymous registration form"

    def test_public_router_strips_whitespace_in_reason(self):
        r = public_router(prefix="/x", reason="   k8s liveness probe   ")
        assert getattr(r, "__public_reason__", None) == "k8s liveness probe"


class TestPublicManifest:
    def test_is_public_known_path(self):
        # /healthz is in the manifest
        reason = is_public("GET", "/healthz")
        assert reason is not None
        assert "liveness" in reason.lower()

    def test_is_public_unknown_path(self):
        # Random business path should NOT be public
        assert is_public("GET", "/api/v1/billing/wallet") is None

    def test_is_public_method_specific(self):
        # POST /healthz should not match GET-only entry
        assert is_public("GET", "/healthz") is not None
        assert is_public("POST", "/healthz") is None

    def test_manifest_no_duplicates(self):
        # Defensive: (method, path) must be unique to prevent ambiguous reasons
        seen: set[tuple[str, str]] = set()
        for method, path, _reason in PUBLIC_PATHS:
            key = (method, path)
            assert key not in seen, f"duplicate manifest entry: {key}"
            seen.add(key)

    def test_manifest_reasons_meet_min_length(self):
        # Same threshold as public_router() — keeps manifest non-trivial.
        for method, path, reason in PUBLIC_PATHS:
            assert len(reason) >= 12, f"manifest reason too short for {method} {path}: {reason!r}"


class TestSecureWsEndpoint:
    """Smoke test only — full WS integration is PR-1b scope."""

    def test_import_succeeds(self):
        # If module imports cleanly, the symbol contract is intact.
        from deeptutor.api._secure_router import secure_ws_endpoint

        assert callable(secure_ws_endpoint)


class TestAuthContextReexport:
    def test_auth_context_reexported(self):
        # PR-1b routers will import AuthContext from _secure_router for ergonomics
        assert hasattr(AuthContext, "user_id")
        assert hasattr(AuthContext, "is_admin")
