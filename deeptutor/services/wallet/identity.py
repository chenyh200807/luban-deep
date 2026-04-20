from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from uuid import UUID

import httpx


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def is_uuid_like(value: Any) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    try:
        UUID(text)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class WalletIdentityResolution:
    raw_user_id: str
    canonical_user_id: str
    source: str
    needs_lookup: bool


class WalletIdentitySupabaseStore:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._base_url = _normalize_text(base_url or os.getenv("SUPABASE_URL"))
        self._service_key = _normalize_text(
            service_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
        )
        self._client = client
        self._owns_client = client is None

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    def resolve_alias(self, *, alias_type: str, alias_value: str) -> dict[str, Any] | None:
        if not self.is_configured:
            return None
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.get(
                f"{self._base_url.rstrip('/')}/rest/v1/user_identity_aliases",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Content-Type": "application/json",
                },
                params={
                    "select": "alias_type,alias_value,user_id,source,confidence,metadata",
                    "alias_type": f"eq.{_normalize_text(alias_type)}",
                    "alias_value": f"eq.{_normalize_text(alias_value)}",
                    "limit": 1,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload:
                row = payload[0]
                if isinstance(row, dict):
                    return dict(row)
            return None
        finally:
            if self._owns_client and self._client is None:
                client.close()


def resolve_wallet_identity(*, raw_user_id: str, claims: dict[str, Any] | None = None) -> WalletIdentityResolution:
    normalized_raw = _normalize_text(raw_user_id)
    claim_map = dict(claims or {})
    for source_key in ("canonical_uid", "supabase_uid", "wallet_uid"):
        candidate = _normalize_text(claim_map.get(source_key))
        if is_uuid_like(candidate):
            return WalletIdentityResolution(
                raw_user_id=normalized_raw,
                canonical_user_id=candidate,
                source=f"claims.{source_key}",
                needs_lookup=False,
            )
    if is_uuid_like(normalized_raw):
        return WalletIdentityResolution(
            raw_user_id=normalized_raw,
            canonical_user_id=normalized_raw,
            source="raw_user_id",
            needs_lookup=False,
        )
    if is_uuid_like(claim_map.get("external_auth_user_id")):
        candidate = _normalize_text(claim_map.get("external_auth_user_id"))
        return WalletIdentityResolution(
            raw_user_id=normalized_raw,
            canonical_user_id=candidate,
            source="claims.external_auth_user_id",
            needs_lookup=False,
        )
    return WalletIdentityResolution(
        raw_user_id=normalized_raw,
        canonical_user_id="",
        source="unresolved",
        needs_lookup=bool(normalized_raw),
    )


_identity_store: WalletIdentitySupabaseStore | None = None


def get_wallet_identity_store() -> WalletIdentitySupabaseStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = WalletIdentitySupabaseStore()
    return _identity_store
