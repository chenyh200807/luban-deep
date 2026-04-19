from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from deeptutor.logging.context import bind_log_context, reset_log_context
from deeptutor.services.config import get_env_store
from deeptutor.services.member_console import get_member_console_service


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: str
    provider: str
    token: str
    claims: dict[str, Any]
    is_admin: bool = False


def _extract_bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _get_metrics_token() -> str:
    return get_env_store().get("DEEPTUTOR_METRICS_TOKEN", "").strip()


def _has_metrics_token_access(
    authorization: str | None,
    metrics_token: str | None,
) -> bool:
    configured = _get_metrics_token()
    if not configured:
        return False
    candidates = (
        _extract_bearer_token(authorization),
        str(metrics_token or "").strip(),
    )
    return any(candidate and compare_digest(candidate, configured) for candidate in candidates)


def resolve_auth_context(authorization: str | None) -> AuthContext | None:
    token = _extract_bearer_token(authorization)
    if not token:
        return None

    service = get_member_console_service()
    claims = service.verify_access_token(token)
    user_id = str((claims or {}).get("uid") or (claims or {}).get("sub") or "").strip()
    if not user_id:
        return None

    return AuthContext(
        user_id=user_id,
        provider=str((claims or {}).get("provider") or "local"),
        token=token,
        claims=dict(claims or {}),
        is_admin=service.is_admin_user(user_id),
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> AsyncGenerator[AuthContext, None]:
    current_user = resolve_auth_context(authorization)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    tokens = bind_log_context(user_id=current_user.user_id)
    try:
        yield current_user
    finally:
        reset_log_context(tokens)


def require_admin(current_user: AuthContext = Depends(get_current_user)) -> AuthContext:
    if current_user.is_admin:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


def require_metrics_access(
    authorization: str | None = Header(default=None),
    metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
) -> AuthContext | None:
    if _has_metrics_token_access(authorization, metrics_token):
        return None

    current_user = resolve_auth_context(authorization)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if current_user.is_admin:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


def require_self_or_admin(
    user_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> AuthContext:
    if current_user.is_admin or current_user.user_id == str(user_id or "").strip():
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden",
    )
