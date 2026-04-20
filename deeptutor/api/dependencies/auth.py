from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from deeptutor.logging.context import bind_log_context, reset_log_context
from deeptutor.services.config import get_env_store
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


def _resolve_authoritative_user_id(claims: dict[str, Any]) -> str:
    canonical_uid = str((claims or {}).get("canonical_uid") or "").strip()
    if canonical_uid:
        return canonical_uid

    raw_user_id = str((claims or {}).get("uid") or (claims or {}).get("sub") or "").strip()
    resolution = resolve_wallet_identity(raw_user_id=raw_user_id, claims=dict(claims or {}))
    if resolution.canonical_user_id:
        return resolution.canonical_user_id
    if resolution.needs_lookup and resolution.raw_user_id:
        service = get_member_console_service()
        store = get_wallet_identity_store()
        if getattr(store, "is_configured", False):
            candidates: list[str] = []

            def _append_candidate(alias_type: str, alias_value: str) -> None:
                row = store.resolve_alias(alias_type=alias_type, alias_value=alias_value)
                if not isinstance(row, dict):
                    return
                alias_user_id = str(row.get("user_id") or "").strip()
                if alias_user_id and alias_user_id not in candidates:
                    candidates.append(alias_user_id)

            for alias_type in ("legacy_user_id", "auth_username", "phone", "wx_openid", "wx_unionid"):
                _append_candidate(alias_type, resolution.raw_user_id)

            if not candidates:
                member: dict[str, Any] = {}
                snapshot_loader = getattr(service, "_load_member_snapshot", None)
                if callable(snapshot_loader):
                    try:
                        snapshot = snapshot_loader(resolution.raw_user_id)
                    except Exception:
                        snapshot = {}
                    maybe_member = snapshot.get("member") if isinstance(snapshot, dict) else {}
                    if isinstance(maybe_member, dict):
                        member = maybe_member
                if not member:
                    raw_loader = getattr(service, "_load", None)
                    if callable(raw_loader):
                        try:
                            data = raw_loader()
                        except Exception:
                            data = {}
                        rows = data.get("members") if isinstance(data, dict) else []
                        if isinstance(rows, list):
                            for row in rows:
                                if not isinstance(row, dict):
                                    continue
                                if str(row.get("user_id") or "").strip() == resolution.raw_user_id:
                                    member = row
                                    break
                if isinstance(member, dict) and member:
                    for alias_type, key in (
                        ("auth_username", "auth_username"),
                        ("phone", "phone"),
                        ("wx_openid", "wx_openid"),
                        ("wx_unionid", "wx_unionid"),
                    ):
                        alias_value = str(member.get(key) or "").strip()
                        if alias_value:
                            _append_candidate(alias_type, alias_value)
                    external_auth_user_id = str(member.get("external_auth_user_id") or "").strip()
                    if external_auth_user_id:
                        external_resolution = resolve_wallet_identity(
                            raw_user_id=external_auth_user_id,
                            claims={"external_auth_user_id": external_auth_user_id},
                        )
                        if external_resolution.canonical_user_id:
                            return external_resolution.canonical_user_id
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
    requested_user_id = str(user_id or "").strip()
    if current_user.is_admin or requested_user_id == "self" or current_user.user_id == requested_user_id:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden",
    )
