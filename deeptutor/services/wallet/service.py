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


@dataclass(frozen=True, slots=True)
class WalletMutationResult:
    ledger_event_id: str
    user_id: str
    event_type: str
    delta_micros: int
    balance_micros: int
    frozen_micros: int
    version: int
    idempotency_key: str
    reference_type: str
    reference_id: str
    created_at: str


class WalletServiceError(RuntimeError):
    """Raised when a wallet mutation request fails."""


class WalletInsufficientBalanceError(WalletServiceError):
    """Raised when a debit would overdraw the available wallet balance."""


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

    def debit_points(
        self,
        *,
        user_id: str,
        amount_micros: int,
        reference_type: str,
        reference_id: str,
        idempotency_key: str,
        reason: str = "capture",
        metadata: dict[str, Any] | None = None,
        operator_type: str = "system",
        operator_id: str | None = None,
    ) -> WalletMutationResult:
        return self._mutate_points(
            user_id=user_id,
            event_type="debit",
            delta_micros=-abs(_coerce_int(amount_micros)),
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            reason=reason,
            metadata=metadata,
            operator_type=operator_type,
            operator_id=operator_id,
        )

    def grant_points(
        self,
        *,
        user_id: str,
        amount_micros: int,
        reference_type: str,
        reference_id: str,
        idempotency_key: str,
        reason: str = "grant",
        metadata: dict[str, Any] | None = None,
        operator_type: str = "system",
        operator_id: str | None = None,
    ) -> WalletMutationResult:
        return self._mutate_points(
            user_id=user_id,
            event_type="grant",
            delta_micros=abs(_coerce_int(amount_micros)),
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            reason=reason,
            metadata=metadata,
            operator_type=operator_type,
            operator_id=operator_id,
        )

    def refund_points(
        self,
        *,
        user_id: str,
        amount_micros: int,
        reference_type: str,
        reference_id: str,
        idempotency_key: str,
        reason: str = "refund",
        metadata: dict[str, Any] | None = None,
        operator_type: str = "system",
        operator_id: str | None = None,
    ) -> WalletMutationResult:
        return self._mutate_points(
            user_id=user_id,
            event_type="refund",
            delta_micros=abs(_coerce_int(amount_micros)),
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            reason=reason,
            metadata=metadata,
            operator_type=operator_type,
            operator_id=operator_id,
        )

    def admin_adjust_points(
        self,
        *,
        user_id: str,
        delta_micros: int,
        reference_id: str,
        idempotency_key: str,
        reason: str = "admin_adjust",
        metadata: dict[str, Any] | None = None,
        operator_type: str = "admin",
        operator_id: str | None = None,
    ) -> WalletMutationResult:
        return self._mutate_points(
            user_id=user_id,
            event_type="admin_adjust",
            delta_micros=_coerce_int(delta_micros),
            reference_type="ticket",
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            reason=reason,
            metadata=metadata,
            operator_type=operator_type,
            operator_id=operator_id,
        )

    def _mutate_points(
        self,
        *,
        user_id: str,
        event_type: str,
        delta_micros: int,
        reference_type: str,
        reference_id: str,
        idempotency_key: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        operator_type: str = "system",
        operator_id: str | None = None,
    ) -> WalletMutationResult:
        if not self.is_configured:
            raise RuntimeError("Wallet service is not configured")

        normalized_delta = _coerce_int(delta_micros)
        if normalized_delta == 0:
            raise ValueError("delta_micros must be non-zero")

        row = self._rpc_row(
            function_name="apply_wallet_mutation",
            payload={
                "p_user_id": _normalize_text(user_id),
                "p_event_type": _normalize_text(event_type),
                "p_delta_micros": normalized_delta,
                "p_reference_type": _normalize_text(reference_type),
                "p_reference_id": _normalize_text(reference_id),
                "p_reason": _normalize_text(reason) or _normalize_text(event_type),
                "p_idempotency_key": _normalize_text(idempotency_key),
                "p_operator_type": _normalize_text(operator_type) or "system",
                "p_operator_id": _normalize_text(operator_id),
                "p_metadata": dict(metadata or {}),
            },
        )
        return WalletMutationResult(
            ledger_event_id=_normalize_text(row.get("ledger_event_id")),
            user_id=_normalize_text(row.get("user_id")),
            event_type=_normalize_text(row.get("event_type")),
            delta_micros=_coerce_int(row.get("delta_micros")),
            balance_micros=_coerce_int(row.get("balance_micros")),
            frozen_micros=_coerce_int(row.get("frozen_micros")),
            version=_coerce_int(row.get("version")),
            idempotency_key=_normalize_text(row.get("idempotency_key")),
            reference_type=_normalize_text(row.get("reference_type")),
            reference_id=_normalize_text(row.get("reference_id")),
            created_at=_normalize_text(row.get("created_at")),
        )

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

    def _rpc_row(self, *, function_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.post(
                f"{self._base_url.rstrip('/')}/rest/v1/rpc/{function_name}",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.is_error:
                self._raise_wallet_error(response)
            body = response.json()
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict):
                        return dict(item)
                return {}
            if isinstance(body, dict):
                return dict(body)
            return {}
        finally:
            if self._owns_client and self._client is None:
                client.close()

    @staticmethod
    def _raise_wallet_error(response: httpx.Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = _normalize_text(payload.get("message")) if isinstance(payload, dict) else ""
        details = _normalize_text(payload.get("details")) if isinstance(payload, dict) else ""
        code = _normalize_text(payload.get("code")) if isinstance(payload, dict) else ""
        if not message:
            message = _normalize_text(response.text) or "Wallet mutation failed."
        if code == "P0001" and "insufficient" in message.lower():
            detail_suffix = f" ({details})" if details else ""
            raise WalletInsufficientBalanceError(f"{message}{detail_suffix}")
        detail_suffix = f" ({details})" if details else ""
        raise WalletServiceError(f"{message}{detail_suffix}")


_wallet_service: SupabaseWalletService | None = None


def get_wallet_service() -> SupabaseWalletService:
    global _wallet_service
    if _wallet_service is None:
        _wallet_service = SupabaseWalletService()
    return _wallet_service
