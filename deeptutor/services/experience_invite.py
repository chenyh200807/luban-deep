from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
import hashlib
import os
import secrets
from typing import Any, Mapping

import httpx

from deeptutor.services.feedback_service import (
    _supabase_rest_headers,
    _supabase_service_key,
)

_DAILY_LIMIT_MICROS_CNY = 1_000_000
# Preserve 0.2 CNY of per-request headroom once settled daily usage reaches
# roughly 0.8 CNY. This exceeds the observed 30-day extreme (0.1509 CNY)
# without reducing the normal experience to only a handful of turns.
_TURN_RESERVATION_MICROS_CNY = 200_000
_MISSING_COST_SETTLEMENT_MICROS_CNY = 800_000
_USD_TO_CNY = Decimal("7.20")
EXPERIENCE_VIDEO_ACCESS_LIMIT = 30


class ExperienceInviteUnavailable(RuntimeError):
    pass


class ExperienceInviteRejected(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExperienceCost:
    amount_micros_cny: int
    provenance: str


def experience_cost_from_usage_summary(summary: Mapping[str, Any] | None) -> ExperienceCost:
    usage = summary if isinstance(summary, Mapping) else {}
    measured = _positive_decimal(usage.get("total_cost_usd"))
    estimated = _positive_decimal(usage.get("estimated_total_cost_usd"))
    if measured is not None and estimated is not None:
        return ExperienceCost(
            amount_micros_cny=_usd_to_cny_micros(measured + estimated),
            provenance="langfuse_measured_plus_model_estimated_usd_fixed_fx_7_20",
        )
    if measured is not None:
        return ExperienceCost(
            amount_micros_cny=_usd_to_cny_micros(measured),
            provenance="langfuse_measured_usd_fixed_fx_7_20",
        )
    if estimated is not None:
        return ExperienceCost(
            amount_micros_cny=_usd_to_cny_micros(estimated),
            provenance="model_usage_estimated_usd_fixed_fx_7_20",
        )
    return ExperienceCost(
        amount_micros_cny=_MISSING_COST_SETTLEMENT_MICROS_CNY,
        provenance="reservation_estimate_missing_model_cost",
    )


def experience_usage_has_incurred_cost(summary: Mapping[str, Any] | None) -> bool:
    usage = summary if isinstance(summary, Mapping) else {}
    return any(
        _positive_decimal(usage.get(key)) is not None
        for key in (
            "total_cost_usd",
            "estimated_total_cost_usd",
            "total_calls",
            "total_tokens",
            "estimated_total_tokens",
        )
    )


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    return parsed if parsed > 0 and parsed.is_finite() else None


def _usd_to_cny_micros(value: Decimal) -> int:
    return max(
        1,
        int((value * _USD_TO_CNY * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING)),
    )


class ExperienceInviteAuthority:
    """Single authority adapter for invite qualification and internal AI cost.

    All state transitions are Postgres RPCs.  There is deliberately no local
    fallback: a process-local mirror cannot enforce a cross-worker hard cap.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self._service_key = _supabase_service_key(service_key)
        self._timeout = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    @property
    def is_enabled(self) -> bool:
        return str(os.getenv("DEEPTUTOR_EXPERIENCE_INVITE_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def status(self, user_id: str) -> dict[str, Any]:
        rows = self._request(
            "GET",
            "/rest/v1/experience_access",
            params={
                "user_id": f"eq.{_required(user_id, 'user_id')}",
                "select": "redeemed_at,expires_at,source",
                "limit": "1",
            },
        )
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, Mapping):
            return {"state": "not_redeemed", "active": False}
        expires_at = _parse_datetime(row.get("expires_at"))
        active = expires_at is not None and expires_at > datetime.now(timezone.utc)
        return {
            "state": "active" if active else "expired",
            "active": active,
            "redeemed_at": str(row.get("redeemed_at") or ""),
            "expires_at": str(row.get("expires_at") or ""),
            "source": str(row.get("source") or ""),
            "video_access_limit": EXPERIENCE_VIDEO_ACCESS_LIMIT if active else None,
        }

    def redeem(self, *, user_id: str, code: str) -> dict[str, Any]:
        payload = self._rpc(
            "redeem_experience_invite",
            {
                "p_user_id": _required(user_id, "user_id"),
                "p_code_hash": _hash_code(code),
            },
        )
        row = _unwrap_rpc_row(payload)
        active = str(row.get("state") or "") == "active"
        return {
            **row,
            "active": active,
            "video_access_limit": EXPERIENCE_VIDEO_ACCESS_LIMIT if active else None,
        }

    def reserve_turn(self, *, user_id: str, turn_key: str) -> dict[str, Any] | None:
        status = self.status(user_id)
        if status.get("state") == "expired":
            raise ExperienceInviteRejected("expired")
        if not status.get("active"):
            return None
        payload = self._rpc(
            "reserve_experience_turn",
            {
                "p_user_id": _required(user_id, "user_id"),
                "p_turn_key": _required(turn_key, "turn_key"),
                "p_reservation_micros": _TURN_RESERVATION_MICROS_CNY,
                "p_daily_limit_micros": _DAILY_LIMIT_MICROS_CNY,
            },
        )
        row = _unwrap_rpc_row(payload)
        if not row.get("allowed"):
            raise ExperienceInviteRejected(str(row.get("reason") or "daily_limit"))
        return {
            "experience": "reserved",
            "experience_turn_key": str(row.get("turn_key") or turn_key),
        }

    def release_turn(self, *, user_id: str, turn_key: str, reason: str) -> None:
        self._rpc(
            "release_experience_turn",
            {
                "p_user_id": _required(user_id, "user_id"),
                "p_turn_key": _required(turn_key, "turn_key"),
                "p_reason": str(reason or "released")[:64],
            },
        )

    def settle_turn(
        self,
        *,
        user_id: str,
        turn_key: str,
        usage_summary: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        cost = experience_cost_from_usage_summary(usage_summary)
        payload = self._rpc(
            "settle_experience_turn",
            {
                "p_user_id": _required(user_id, "user_id"),
                "p_turn_key": _required(turn_key, "turn_key"),
                "p_actual_micros": cost.amount_micros_cny,
                "p_provenance": cost.provenance,
                "p_daily_limit_micros": _DAILY_LIMIT_MICROS_CNY,
            },
        )
        row = _unwrap_rpc_row(payload)
        status = str(row.get("status") or "")
        if status != "settled":
            raise ExperienceInviteUnavailable(
                f"experience settlement rejected: {status or 'invalid_status'}"
            )
        return {
            "status": status,
            "provenance": str(row.get("provenance") or cost.provenance),
            "daily_blocked": bool(row.get("daily_blocked")),
        }

    def create_invite(
        self,
        *,
        actor_id: str,
        source: str,
        max_redemptions: int = 1,
        valid_until: str | None = None,
    ) -> dict[str, Any]:
        return self.create_invites(
            actor_id=actor_id,
            source=source,
            quantity=1,
            max_redemptions=max_redemptions,
            valid_until=valid_until,
        )[0]

    def create_invites(
        self,
        *,
        actor_id: str,
        source: str,
        quantity: int,
        max_redemptions: int = 1,
        valid_until: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_quantity = int(quantity)
        normalized_max_redemptions = int(max_redemptions)
        if not 1 <= normalized_quantity <= 100:
            raise ValueError("quantity must be between 1 and 100")
        if not 1 <= normalized_max_redemptions <= 1000:
            raise ValueError("max_redemptions must be between 1 and 1000")
        normalized_valid_until = None
        if valid_until:
            parsed_valid_until = _parse_datetime(valid_until)
            if parsed_valid_until is None:
                raise ValueError("valid_until must be an ISO-8601 timestamp")
            normalized_valid_until = parsed_valid_until.isoformat()
        codes = [f"YS-{secrets.token_hex(16).upper()}" for _ in range(normalized_quantity)]
        payload = [
            {
                "code_hash": _hash_code(code),
                "code_prefix": code[:6],
                "source": str(source or "yousen_paid_student")[:64],
                "max_redemptions": normalized_max_redemptions,
                "valid_until": normalized_valid_until,
                "created_by": _required(actor_id, "actor_id"),
            }
            for code in codes
        ]
        rows = self._request(
            "POST",
            "/rest/v1/experience_invites",
            headers=_supabase_rest_headers(self._service_key, prefer="return=representation"),
            json=payload,
        )
        if not isinstance(rows, list) or len(rows) != len(codes):
            raise ExperienceInviteUnavailable("experience invite batch creation was incomplete")
        rows_by_hash = {
            str(row.get("code_hash") or ""): row for row in rows if isinstance(row, Mapping)
        }
        created: list[dict[str, Any]] = []
        for code in codes:
            row = rows_by_hash.get(_hash_code(code))
            if not isinstance(row, Mapping):
                raise ExperienceInviteUnavailable("experience invite batch response was incomplete")
            created.append(
                {
                    "id": str(row.get("id") or ""),
                    "code": code,
                    "code_prefix": code[:6],
                    "source": str(row.get("source") or source),
                    "valid_until": row.get("valid_until"),
                }
            )
        return created

    def list_invites(self, *, limit: int = 100) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/rest/v1/experience_invites",
            params={
                "select": "id,code_prefix,source,status,max_redemptions,redeemed_count,valid_until,created_at,created_by",
                "order": "created_at.desc",
                "limit": str(max(1, min(int(limit), 500))),
            },
        )
        return [dict(row) for row in payload] if isinstance(payload, list) else []

    def _rpc(self, name: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", f"/rest/v1/rpc/{name}", json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.is_configured:
            raise ExperienceInviteUnavailable("experience authority is not configured")
        headers = kwargs.pop("headers", _supabase_rest_headers(self._service_key))
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
            if response.status_code >= 400:
                try:
                    detail = str((response.json() or {}).get("message") or "")
                except ValueError:
                    detail = ""
                for code in ("invite_invalid", "invite_expired", "invite_exhausted"):
                    if code in detail:
                        raise ExperienceInviteRejected(code)
            response.raise_for_status()
            return response.json() if response.content else None
        except ExperienceInviteRejected:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ExperienceInviteUnavailable("experience authority unavailable") from exc


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _hash_code(value: str) -> str:
    normalized = _required(value, "code").replace(" ", "").upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _unwrap_rpc_row(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, Mapping):
        raise ExperienceInviteUnavailable("experience authority returned an invalid payload")
    return dict(payload)


_authority: ExperienceInviteAuthority | None = None


def get_experience_invite_authority() -> ExperienceInviteAuthority:
    global _authority
    if _authority is None:
        _authority = ExperienceInviteAuthority()
    return _authority
