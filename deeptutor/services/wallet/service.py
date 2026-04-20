from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import httpx


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True, slots=True)
class WalletSnapshot:
    user_id: str
    balance_micros: int
    frozen_micros: int
    plan_id: str
    version: int
    created_at: str


@dataclass(frozen=True, slots=True)
class WalletLedgerEntry:
    id: str
    user_id: str
    event_type: str
    delta_micros: int
    balance_after_micros: int
    frozen_after_micros: int
    reference_type: str
    reference_id: str
    idempotency_key: str
    metadata: dict[str, Any]
    created_at: str


class SupabaseWalletService:
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

    def get_wallet(self, user_id: str) -> WalletSnapshot | None:
        rows = self._select_rows(
            table="wallets",
            params={
                "select": "user_id,balance_micros,frozen_micros,plan_id,version,created_at",
                "user_id": f"eq.{_normalize_text(user_id)}",
                "limit": 1,
            },
        )
        if not rows:
            return None
        row = rows[0]
        return WalletSnapshot(
            user_id=_normalize_text(row.get("user_id")),
            balance_micros=_coerce_int(row.get("balance_micros")),
            frozen_micros=_coerce_int(row.get("frozen_micros")),
            plan_id=_normalize_text(row.get("plan_id")),
            version=_coerce_int(row.get("version")),
            created_at=_normalize_text(row.get("created_at")),
        )

    def list_wallet_ledger(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WalletLedgerEntry]:
        rows = self._select_rows(
            table="wallet_ledger",
            params={
                "select": (
                    "id,user_id,event_type,delta_micros,balance_after_micros,"
                    "frozen_after_micros,reference_type,reference_id,idempotency_key,metadata,created_at"
                ),
                "user_id": f"eq.{_normalize_text(user_id)}",
                "order": "created_at.desc,id.desc",
                "limit": max(1, int(limit)),
                "offset": max(0, int(offset)),
            },
        )
        entries: list[WalletLedgerEntry] = []
        for row in rows:
            entries.append(
                WalletLedgerEntry(
                    id=_normalize_text(row.get("id")),
                    user_id=_normalize_text(row.get("user_id")),
                    event_type=_normalize_text(row.get("event_type")),
                    delta_micros=_coerce_int(row.get("delta_micros")),
                    balance_after_micros=_coerce_int(row.get("balance_after_micros")),
                    frozen_after_micros=_coerce_int(row.get("frozen_after_micros")),
                    reference_type=_normalize_text(row.get("reference_type")),
                    reference_id=_normalize_text(row.get("reference_id")),
                    idempotency_key=_normalize_text(row.get("idempotency_key")),
                    metadata=dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {},
                    created_at=_normalize_text(row.get("created_at")),
                )
            )
        return entries

    def _select_rows(self, *, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.get(
                f"{self._base_url.rstrip('/')}/rest/v1/{table}",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Content-Type": "application/json",
                },
                params={key: str(value) for key, value in params.items()},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return []
            return [dict(item) for item in payload if isinstance(item, dict)]
        finally:
            if self._owns_client and self._client is None:
                client.close()


_wallet_service: SupabaseWalletService | None = None


def get_wallet_service() -> SupabaseWalletService:
    global _wallet_service
    if _wallet_service is None:
        _wallet_service = SupabaseWalletService()
    return _wallet_service
