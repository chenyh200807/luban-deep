from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UNKNOWN_CREATED_AT = "1970-01-01T00:00:00+00:00"
_UNKNOWN_EXPIRE_AT = "9999-12-31T00:00:00+00:00"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class SupabaseMemberDirectoryReadModel:
    """Canonical read model for BI/member-ops member directory rows.

    This service is intentionally read-only. Member operations may still write
    local notes/audit overlays, but the member pool itself comes from Supabase.
    """

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

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def list_members(self, *, limit: int = 5000) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []
        rows = self._select_rows(
            table="v_members",
            params={
                "select": (
                    "user_id,identifier,phone,display_name,profession,exam_target,"
                    "plan_id,balance_micros,frozen_micros,wallet_created_at,wallet_updated_at,"
                    "first_chat_at,last_chat_at,total_conversations,total_messages,"
                    "has_user_record,has_wallet,has_profile,has_chat_history"
                ),
                "order": "last_chat_at.desc.nullslast,wallet_updated_at.desc.nullslast,user_id.asc",
                "limit": max(1, min(int(limit), 10000)),
            },
        )
        members = [self._member_from_row(row) for row in rows]
        return [member for member in members if member.get("user_id")]

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
        }

    def _client_instance(self) -> Any:
        if self._client is None:
            self._client = httpx.Client(timeout=10.0)
        return self._client

    def _select_rows(self, *, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        client = self._client_instance()
        response = client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/{table}",
            headers=self._headers(),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            logger.warning("Supabase member directory returned non-list payload: table=%s", table)
            return []
        return [row for row in payload if isinstance(row, dict)]

    @staticmethod
    def _member_from_row(row: dict[str, Any]) -> dict[str, Any]:
        user_id = _normalize_text(row.get("user_id") or row.get("identifier"))
        identifier = _normalize_text(row.get("identifier"))
        plan_id = _normalize_text(row.get("plan_id"))
        phone = _normalize_text(row.get("phone"))
        wallet_created_at = _normalize_text(row.get("wallet_created_at"))
        first_chat_at = _normalize_text(row.get("first_chat_at"))
        wallet_updated_at = _normalize_text(row.get("wallet_updated_at"))
        last_chat_at = _normalize_text(row.get("last_chat_at"))
        created_at = wallet_created_at or first_chat_at or _UNKNOWN_CREATED_AT
        last_active_at = last_chat_at or wallet_updated_at or first_chat_at or wallet_created_at or _UNKNOWN_CREATED_AT
        aliases = sorted({value for value in (user_id, identifier) if value})
        has_user_record = _coerce_bool(row.get("has_user_record"))
        has_wallet = _coerce_bool(row.get("has_wallet"))
        has_profile = _coerce_bool(row.get("has_profile"))
        has_chat_history = _coerce_bool(row.get("has_chat_history"))
        return {
            "user_id": user_id,
            "canonical_user_id": user_id,
            "external_auth_user_id": user_id,
            "alias_user_ids": aliases,
            "display_name": _normalize_text(row.get("display_name")) or identifier or user_id,
            "phone": phone,
            "tier": plan_id or "trial",
            "status": "active" if any((has_user_record, has_wallet, has_profile, has_chat_history, phone)) else "inactive",
            "segment": _normalize_text(row.get("profession") or row.get("exam_target")) or "general",
            "risk_level": "low",
            "auto_renew": False,
            "created_at": created_at,
            "last_active_at": last_active_at,
            "expire_at": _UNKNOWN_EXPIRE_AT,
            "avatar_url": "",
            "points_balance": max(0, _coerce_int(row.get("balance_micros"))) // 1_000_000,
            "frozen_points": max(0, _coerce_int(row.get("frozen_micros"))) // 1_000_000,
            "level": 1,
            "xp": 0,
            "study_days": 0,
            "review_due": 0,
            "focus_topic": _normalize_text(row.get("exam_target")),
            "chapter_mastery": {},
            "chapter_practice_stats": {},
            "daily_practice_counts": {},
            "ledger": [],
            "notes": [],
            "badges": [],
            "earned_badge_ids": [],
            "member_directory_source": "supabase.v_members",
            "member_directory_metrics": {
                "total_conversations": _coerce_int(row.get("total_conversations")),
                "total_messages": _coerce_int(row.get("total_messages")),
                "has_user_record": has_user_record,
                "has_wallet": has_wallet,
                "has_profile": has_profile,
                "has_chat_history": has_chat_history,
            },
        }


_instance: SupabaseMemberDirectoryReadModel | None = None


def get_member_directory_read_model() -> SupabaseMemberDirectoryReadModel:
    global _instance
    if _instance is None:
        _instance = SupabaseMemberDirectoryReadModel()
    return _instance
