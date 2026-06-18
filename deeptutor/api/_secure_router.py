"""Default-secure router factory — SR1 single authority.

Why this file exists (v2.1 SR1 root cause): FastAPI `APIRouter()` defaults
to zero authentication. Every router author has to remember to add
`Depends(get_current_user)`; forget once and you ship A1/A2/A4-style
anonymous-LLM-trigger holes. This factory inverts the default — every router
is authenticated unless explicitly marked public via `public_router(reason=...)`.

Companion CI gates (must both pass):
1. `scripts/ci/check_secure_routers.sh` — static grep: no bare `APIRouter(`
   in `deeptutor/api/routers/`, `public_router` always has a `reason=`.
2. `scripts/ci/runtime_route_inventory.py` — runtime reflection: every
   `app.routes` endpoint is either authenticated OR appears in `_public_manifest`.

Grep alone is not a security boundary (codex review R1): alias imports,
wrappers, `include_router` chains, and test fixtures can bypass it. Runtime
inventory is the real authority; the grep gate is just a fast pre-commit lint.

Usage:

    from deeptutor.api._secure_router import secure_router, secure_ws_endpoint

    router = secure_router(prefix="/vision", tags=["vision"])

    @router.post("/analyze")
    async def analyze(current_user: AuthContext = Depends(get_current_user)):
        ...

    @router.websocket("/solve")
    async def solve_ws(ws: WebSocket):
        auth = await secure_ws_endpoint(
            ws, rate_limit_scope="vision_solve_ws",
            rate_limit_max=30, rate_limit_window_seconds=60.0,
        )
        if auth is None:
            return  # ws already closed by us
        # ... use auth.user_id, RLS check, etc.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, WebSocket

from deeptutor.api.dependencies.auth import (
    AuthContext,
    get_current_user,
    resolve_auth_context,
)
from deeptutor.api.dependencies.rate_limit import enforce_websocket_rate_limit

__all__ = [
    "AuthContext",
    "secure_router",
    "secure_ws_router",
    "public_router",
    "secure_ws_endpoint",
]


def secure_router(
    prefix: str = "",
    *,
    tags: list[str] | None = None,
    extra_dependencies: list[Any] | None = None,
    **kwargs: Any,
) -> APIRouter:
    """Default-secure HTTP router. Every endpoint inherits `Depends(get_current_user)`.

    Pass `extra_dependencies` to stack admin / BI / metrics / self_or_admin deps
    on top. The factory always adds `get_current_user` first, so admin checks
    layer correctly on the authenticated context.
    """
    deps = [Depends(get_current_user), *(extra_dependencies or [])]
    return APIRouter(prefix=prefix, tags=tags, dependencies=deps, **kwargs)


def public_router(
    prefix: str = "",
    *,
    reason: str,
    tags: list[str] | None = None,
    **kwargs: Any,
) -> APIRouter:
    """Explicitly anonymous router. `reason` is mandatory and CI-grepped.

    Accepted reason categories (CI gate Layer A only checks reason is non-trivial;
    Layer B runtime inventory cross-checks against `_public_manifest.PUBLIC_PATHS`):

    - "anonymous registration / login / phone-bind (rate-limited)"
    - "static UI metadata, read-only"
    - "system public capability advertisement"
    - "k8s liveness / readiness"
    """
    if not reason or not isinstance(reason, str) or len(reason.strip()) < 12:
        raise ValueError(
            "public_router requires a non-trivial reason string (>=12 chars). "
            "See deeptutor/api/_public_manifest.py for the accepted categories."
        )
    router = APIRouter(prefix=prefix, tags=tags, **kwargs)
    # Marker for runtime introspection (read by runtime_route_inventory.py).
    router.__public_reason__ = reason.strip()  # type: ignore[attr-defined]
    return router


def secure_ws_router(
    prefix: str = "",
    *,
    tags: list[str] | None = None,
    **kwargs: Any,
) -> APIRouter:
    """WS-only router factory.

    WebSocket auth must happen inside the endpoint via ``secure_ws_endpoint`` so
    the handler can close with the contract-specific 4401 / 1013 codes. This
    factory intentionally does not add FastAPI router dependencies.
    """
    router = APIRouter(prefix=prefix, tags=tags, **kwargs)
    router.__secure_ws_router__ = True  # type: ignore[attr-defined]
    return router


async def secure_ws_endpoint(
    ws: WebSocket,
    *,
    rate_limit_scope: str,
    rate_limit_max: int,
    rate_limit_window_seconds: float,
) -> AuthContext | None:
    """Mandatory authenticated WS handshake.

    Returns `AuthContext` on success — caller can rely on `auth.user_id` being non-empty.
    Returns `None` when either rate-limited or unauthenticated; in both cases the
    WS connection has already been closed by us. **Caller MUST early-return on None.**

    Closing codes:
    - 1013 — rate-limited (set by `enforce_websocket_rate_limit`)
    - 4401 — unauthenticated (Bearer missing / invalid / expired)

    This helper consolidates the previously-duplicated `resolve_auth_context` +
    `_authorize_session_access` "owner_key 缺失 + anon 放行" bypass in
    `unified_ws.py` — once callers always receive a non-None `AuthContext`,
    the bypass branch becomes dead code and gets removed at the site.
    """
    if not await enforce_websocket_rate_limit(
        ws,
        rate_limit_scope,
        default_max_requests=rate_limit_max,
        default_window_seconds=rate_limit_window_seconds,
    ):
        return None  # ws.close(code=1013) already called by rate_limit helper
    auth = resolve_auth_context(ws.headers.get("authorization"))
    if auth is None:
        await ws.close(code=4401, reason="Authentication required")
        return None
    await ws.accept()
    return auth
