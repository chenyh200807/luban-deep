from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, status

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


def get_current_user(authorization: str | None = Header(default=None)) -> AuthContext:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    service = get_member_console_service()
    claims = service.verify_access_token(token)
    user_id = str((claims or {}).get("uid") or (claims or {}).get("sub") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return AuthContext(
        user_id=user_id,
        provider=str((claims or {}).get("provider") or "local"),
        token=token,
        claims=dict(claims or {}),
        is_admin=service.is_admin_user(user_id),
    )


def require_admin(current_user: AuthContext = Depends(get_current_user)) -> AuthContext:
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
