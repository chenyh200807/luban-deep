from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from deeptutor.logging.context import bind_log_context
from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.wallet.identity import get_wallet_identity_store, resolve_wallet_identity


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


def _resolve_authoritative_user_id(claims: dict[str, Any]) -> str:
    canonical_uid = str((claims or {}).get("canonical_uid") or "").strip()
    if canonical_uid:
        return canonical_uid

    raw_user_id = str((claims or {}).get("uid") or (claims or {}).get("sub") or "").strip()
    resolution = resolve_wallet_identity(raw_user_id=raw_user_id, claims=dict(claims or {}))
    if resolution.canonical_user_id:
        return resolution.canonical_user_id
    if resolution.needs_lookup and resolution.raw_user_id:
        store = get_wallet_identity_store()
        if getattr(store, "is_configured", False):
            candidates: list[str] = []
            for alias_type in ("legacy_user_id", "auth_username", "phone", "wx_openid", "wx_unionid"):
                row = store.resolve_alias(alias_type=alias_type, alias_value=resolution.raw_user_id)
                if not isinstance(row, dict):
                    continue
                alias_user_id = str(row.get("user_id") or "").strip()
                if alias_user_id and alias_user_id not in candidates:
                    candidates.append(alias_user_id)
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                return ""
    return resolution.raw_user_id


def resolve_auth_context(authorization: str | None) -> AuthContext | None:
    token = _extract_bearer_token(authorization)
    if not token:
        return None

    service = get_member_console_service()
    claims = service.verify_access_token(token)
    user_id = _resolve_authoritative_user_id(dict(claims or {}))
    if not user_id:
        return None

    return AuthContext(
        user_id=user_id,
        provider=str((claims or {}).get("provider") or "local"),
        token=token,
        claims=dict(claims or {}),
        is_admin=service.is_admin_user(user_id),
    )


def resolve_wallet_user_id(authorization: str | None) -> str:
    token = _extract_bearer_token(authorization)
    if not token:
        return ""
    service = get_member_console_service()
    claims = service.verify_access_token(token)
    return _resolve_authoritative_user_id(dict(claims or {}))


def get_current_user(authorization: str | None = Header(default=None)) -> AuthContext:
    current_user = resolve_auth_context(authorization)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    bind_log_context(user_id=current_user.user_id)
    return current_user


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
