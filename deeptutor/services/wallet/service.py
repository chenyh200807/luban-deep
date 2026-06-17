from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from uuid import uuid4

import httpx


BILLING_ENFORCEMENT_FLAG = "DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def is_billing_enforcement_enabled() -> bool:
    """Single authority for whether real wallet charging is enforced.

    Launch default is ON: usage is fail-closed against the canonical wallet.
    Set ``DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED`` to 0/false/no/off only for
    explicit internal-beta rollback or QA bypass windows.
    """
    return _env_flag(BILLING_ENFORCEMENT_FLAG, default=True)


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
class WalletCaptureResult:
    captured_micros: int
    requested_micros: int
    balance_after_micros: int
    entry: WalletLedgerEntry | None


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

    def ensure_wallet_seeded(
        self,
        *,
        user_id: str,
        opening_points: int = 0,
        plan_id: str = "",
        reference_type: str = "signup_bonus",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WalletSnapshot | None:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            return None
        if not self.is_configured:
            raise RuntimeError("Supabase wallet service is not configured")

        opening_micros = max(0, _coerce_int(opening_points)) * 1_000_000
        snapshot = self.get_wallet(normalized_user_id)
        created_snapshot: WalletSnapshot | None = None
        rows: list[dict[str, Any]] = []
        if snapshot is None:
            try:
                rows = self._post_rows(
                    table="wallets",
                    rows=[
                        {
                            "user_id": normalized_user_id,
                            "balance_micros": opening_micros,
                            "frozen_micros": 0,
                            "plan_id": _normalize_text(plan_id),
                            "version": 1,
                        }
                    ],
                )
            except httpx.HTTPStatusError as exc:
                if exc.response is None or exc.response.status_code != 409:
                    raise
                rows = []

        if rows:
            row = rows[0]
            created_snapshot = WalletSnapshot(
                user_id=_normalize_text(row.get("user_id")),
                balance_micros=_coerce_int(row.get("balance_micros")),
                frozen_micros=_coerce_int(row.get("frozen_micros")),
                plan_id=_normalize_text(row.get("plan_id")),
                version=_coerce_int(row.get("version")),
                created_at=_normalize_text(row.get("created_at")),
            )

        snapshot = created_snapshot or self.get_wallet(normalized_user_id)
        if snapshot is None:
            return None

        normalized_idempotency_key = _normalize_text(idempotency_key) or f"signup_bonus:{normalized_user_id}"
        if opening_micros > 0:
            existing_entry = self.find_wallet_ledger_by_idempotency_key(
                normalized_user_id,
                idempotency_key=normalized_idempotency_key,
            )
            if existing_entry is None:
                payload_metadata = dict(metadata or {}) if isinstance(metadata, dict) else {}
                payload_reason = _normalize_text(payload_metadata.get("reason")) or "signup_bonus"
                payload_metadata.setdefault("reason", payload_reason)
                self._insert_wallet_ledger(
                    {
                        "user_id": normalized_user_id,
                        "event_type": "grant",
                        "delta_micros": opening_micros,
                        "balance_after_micros": snapshot.balance_micros,
                        "frozen_after_micros": snapshot.frozen_micros,
                        "reference_type": _normalize_text(reference_type) or "signup_bonus",
                        "reference_id": _normalize_text(reference_id),
                        "reason": payload_reason,
                        "idempotency_key": normalized_idempotency_key,
                        "metadata": payload_metadata,
                    }
                )
        return snapshot

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

    def list_recent_wallet_ledger(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WalletLedgerEntry]:
        rows = self._select_rows(
            table="wallet_ledger",
            params={
                "select": (
                    "id,user_id,event_type,delta_micros,balance_after_micros,"
                    "frozen_after_micros,reference_type,reference_id,idempotency_key,metadata,created_at"
                ),
                "order": "created_at.desc,id.desc",
                "limit": max(1, int(limit)),
                "offset": max(0, int(offset)),
            },
        )
        entries: list[WalletLedgerEntry] = []
        for row in rows:
            entries.append(self._build_ledger_entry(row))
        return entries

    def find_wallet_ledger_by_idempotency_key(
        self,
        user_id: str,
        *,
        idempotency_key: str,
    ) -> WalletLedgerEntry | None:
        rows = self._select_rows(
            table="wallet_ledger",
            params={
                "select": (
                    "id,user_id,event_type,delta_micros,balance_after_micros,"
                    "frozen_after_micros,reference_type,reference_id,idempotency_key,metadata,created_at"
                ),
                "user_id": f"eq.{_normalize_text(user_id)}",
                "idempotency_key": f"eq.{_normalize_text(idempotency_key)}",
                "limit": 1,
            },
        )
        if not rows:
            return None
        return self._build_ledger_entry(rows[0])

    def capture_points(
        self,
        *,
        user_id: str,
        amount_points: int,
        idempotency_key: str,
        reference_id: str,
        reason: str = "capture",
        reference_type: str = "ai_usage",
        metadata: dict[str, Any] | None = None,
    ) -> WalletCaptureResult:
        normalized_user_id = _normalize_text(user_id)
        normalized_idempotency_key = _normalize_text(idempotency_key)
        requested_points = max(0, _coerce_int(amount_points))
        requested_micros = requested_points * 1_000_000
        if not normalized_user_id or not normalized_idempotency_key or requested_micros <= 0:
            return WalletCaptureResult(
                captured_micros=0,
                requested_micros=requested_micros,
                balance_after_micros=0,
                entry=None,
            )
        if not self.is_configured:
            raise RuntimeError("Supabase wallet service is not configured")

        mutation = self.debit_points(
            user_id=normalized_user_id,
            amount_micros=requested_micros,
            reference_type=_normalize_text(reference_type) or "ai_usage",
            reference_id=_normalize_text(reference_id),
            idempotency_key=normalized_idempotency_key,
            reason=_normalize_text(reason) or "capture",
            metadata={
                "reason": _normalize_text(reason) or "capture",
                **(dict(metadata or {}) if isinstance(metadata, dict) else {}),
            },
            operator_type="system",
            operator_id=_normalize_text(reference_id) or "turn_runtime",
        )
        metadata_payload = {
            "reason": _normalize_text(reason) or "capture",
            **(dict(metadata or {}) if isinstance(metadata, dict) else {}),
        }
        entry = WalletLedgerEntry(
            id=mutation.ledger_event_id,
            user_id=mutation.user_id,
            event_type=mutation.event_type,
            delta_micros=mutation.delta_micros,
            balance_after_micros=mutation.balance_micros,
            frozen_after_micros=mutation.frozen_micros,
            reference_type=mutation.reference_type,
            reference_id=mutation.reference_id,
            idempotency_key=mutation.idempotency_key,
            metadata=metadata_payload,
            created_at=mutation.created_at,
        )
        return WalletCaptureResult(
            captured_micros=abs(mutation.delta_micros),
            requested_micros=requested_micros,
            balance_after_micros=mutation.balance_micros,
            entry=entry,
        )

    def record_usage_points(
        self,
        *,
        user_id: str,
        amount_points: int,
        idempotency_key: str,
        reference_id: str,
        reason: str = "capture",
        reference_type: str = "ai_usage",
        metadata: dict[str, Any] | None = None,
    ) -> WalletCaptureResult:
        normalized_user_id = _normalize_text(user_id)
        normalized_idempotency_key = _normalize_text(idempotency_key)
        requested_points = max(0, _coerce_int(amount_points))
        requested_micros = requested_points * 1_000_000

        # Explicit internal-beta override: billing enforcement OFF. No balance
        # mutation and no ledger write — keep the wallet pristine so QA/free
        # windows never pollute the canonical ledger. The call stays a no-op
        # that returns a skipped/zero-capture result so the caller flow is
        # unchanged.
        if not is_billing_enforcement_enabled():
            return WalletCaptureResult(
                captured_micros=0,
                requested_micros=requested_micros,
                balance_after_micros=0,
                entry=None,
            )

        if not normalized_user_id or not normalized_idempotency_key or requested_micros <= 0:
            return WalletCaptureResult(
                captured_micros=0,
                requested_micros=requested_micros,
                balance_after_micros=0,
                entry=None,
            )
        if not self.is_configured:
            raise RuntimeError("Supabase wallet service is not configured")

        # Enforcement ON: route through the canonical atomic RPC path
        # (debit_points -> _mutate_points -> apply_wallet_mutation). The RPC
        # row-locks the wallet, decrements balance_micros, writes the correct
        # after-image (balance + delta), is transactionally idempotent on the
        # idempotency key, and raises WalletInsufficientBalanceError (P0001)
        # when the debit would overdraw — without writing a ledger row.
        return self.capture_points(
            user_id=normalized_user_id,
            amount_points=requested_points,
            idempotency_key=normalized_idempotency_key,
            reference_id=reference_id,
            reason=reason,
            reference_type=reference_type,
            metadata=metadata,
        )

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

    def _build_ledger_entry(self, row: dict[str, Any]) -> WalletLedgerEntry:
        return WalletLedgerEntry(
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

    def _is_invalid_wallet_identity_query(self, exc: httpx.HTTPStatusError) -> bool:
        response = exc.response
        if response is None or response.status_code != 400:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        if not isinstance(payload, dict):
            return False
        if str(payload.get("code") or "").strip() != "22P02":
            return False
        return "type uuid" in str(payload.get("message") or "").lower()

    def _insert_wallet_ledger(self, row: dict[str, Any]) -> WalletLedgerEntry | None:
        payload = dict(row or {})
        payload.setdefault("id", str(uuid4()))
        payload_metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
        payload_reason = (
            _normalize_text(payload.get("reason"))
            or _normalize_text(payload_metadata.get("reason"))
            or _normalize_text(payload.get("reference_type"))
            or _normalize_text(payload.get("event_type"))
        )
        payload["reason"] = payload_reason
        payload_operator_type = _normalize_text(payload.get("operator_type")) or "system"
        payload_operator_id = (
            _normalize_text(payload.get("operator_id"))
            or _normalize_text(payload_metadata.get("operator_id"))
            or _normalize_text(payload_metadata.get("source"))
            or _normalize_text(payload.get("reference_id"))
            or payload_reason
            or "system"
        )
        payload["operator_type"] = payload_operator_type
        payload["operator_id"] = payload_operator_id
        try:
            rows = self._post_rows(table="wallet_ledger", rows=[payload])
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                return None
            raise
        if not rows:
            return None
        return self._build_ledger_entry(rows[0])

    def _select_rows(self, *, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []
        client = self._client or httpx.Client(timeout=5.0)
        try:
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
            except httpx.HTTPStatusError as exc:
                if self._is_invalid_wallet_identity_query(exc):
                    return []
                raise
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
        detail_suffix = f" ({details})" if details else ""
        if code == "P0001" and "insufficient" in message.lower():
            raise WalletInsufficientBalanceError(f"{message}{detail_suffix}")
        raise WalletServiceError(f"{message}{detail_suffix}")

    def _post_rows(self, *, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.is_configured:
            raise RuntimeError("Supabase wallet service is not configured")
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.post(
                f"{self._base_url.rstrip('/')}/rest/v1/{table}",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                json=rows,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return []
            return [dict(item) for item in payload if isinstance(item, dict)]
        finally:
            if self._owns_client and self._client is None:
                client.close()

    def _patch_rows(
        self,
        *,
        table: str,
        params: dict[str, Any],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self.is_configured:
            raise RuntimeError("Supabase wallet service is not configured")
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.patch(
                f"{self._base_url.rstrip('/')}/rest/v1/{table}",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                params={key: str(value) for key, value in params.items()},
                json=payload,
            )
            response.raise_for_status()
            patch_payload = response.json()
            if not isinstance(patch_payload, list):
                return []
            return [dict(item) for item in patch_payload if isinstance(item, dict)]
        finally:
            if self._owns_client and self._client is None:
                client.close()


_wallet_service: SupabaseWalletService | None = None


def get_wallet_service() -> SupabaseWalletService:
    global _wallet_service
    if _wallet_service is None:
        _wallet_service = SupabaseWalletService()
    return _wallet_service
