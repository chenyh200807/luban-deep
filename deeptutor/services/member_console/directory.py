from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UNKNOWN_CREATED_AT = "1970-01-01T00:00:00+00:00"
_UNKNOWN_EXPIRE_AT = "9999-12-31T00:00:00+00:00"
_MAX_MEMBER_DIRECTORY_ROWS = 10000
_MEMBER_DIRECTORY_PAGE_SIZE = 1000
_TRUSTED_PHONE_ALIAS_SOURCES = frozenset(
    {
        "phone_backfill",
        "member_console_backfill",
        "phone_verification",
    }
)
_IDENTITY_METADATA_FIELDS = (
    "account_kind",
    "member_account_kind",
    "actor_type",
    "created_by",
    "is_internal_test",
    "is_test_account",
    "runner",
    "agent_tool",
    "eval_run_id",
    "phone_binding_method",
    "reg_channel",
    "reg_scene",
)


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


def _normalize_phone(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-11:] if len(digits) >= 11 else ""


def _is_cn_mainland_mobile(value: Any) -> bool:
    phone = _normalize_phone(value)
    return bool(re.fullmatch(r"1[3-9]\d{9}", phone)) and phone not in {
        "13800000000",
        "13900000000",
        "18888888888",
        "19999999999",
    } and not re.fullmatch(r"1380000000\d", phone)


def _identity_metadata_from_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    metadata: dict[str, Any] = {}
    for field in _IDENTITY_METADATA_FIELDS:
        raw = value.get(field)
        if raw in (None, "", [], {}):
            continue
        if field in {"is_internal_test", "is_test_account"}:
            metadata[field] = _coerce_bool(raw)
        else:
            metadata[field] = _normalize_text(raw)
    return metadata


def _merge_identity_metadata(*values: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for value in values:
        metadata.update(_identity_metadata_from_mapping(value))
    return metadata


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
        requested_limit = max(1, min(int(limit), _MAX_MEMBER_DIRECTORY_ROWS))
        eligible_phone_aliases = self._eligible_phone_aliases(limit=requested_limit)
        if not eligible_phone_aliases:
            return []
        # Query v_members for exactly the users who have phone aliases — avoids the
        # mismatch that occurs when the top-N-by-activity v_members slice and the
        # top-N-by-registration phone alias slice cover different user sets.
        alias_user_ids = list(eligible_phone_aliases.keys())
        uid_in_filter = f"in.({','.join(alias_user_ids)})"
        # 注意：不要从 v_members 读任何 chat_conversations 派生列
        # （first_chat_at/last_chat_at/total_conversations/total_messages/has_chat_history）。
        # Postgres 的 chat_conversations 是死表（真实对话在宿主 SQLite chat_history.db），
        # 这些列全是空壳/陈旧值。真实对话事实由 member_console service 的
        # _merge_session_activity_for_member_list 从 SQLite sessions 派生。
        rows = self._select_rows_paginated(
            table="v_members",
            params={
                "select": (
                    "user_id,identifier,phone,display_name,profession,exam_target,"
                    "plan_id,balance_micros,frozen_micros,wallet_created_at,wallet_updated_at,"
                    "has_user_record,has_wallet,has_profile"
                ),
                "user_id": uid_in_filter,
                "order": "wallet_updated_at.desc.nullslast,user_id.asc",
            },
            limit=len(alias_user_ids),
        )
        rows_by_user_id = {_normalize_text(row.get("user_id")): row for row in rows}
        user_rows = self._select_rows_paginated(
            table="users",
            params={
                "select": "id,identifier,createdAt,metadata,phone",
                "id": uid_in_filter,
            },
            limit=len(alias_user_ids),
        )
        users_by_id = {_normalize_text(row.get("id")): row for row in user_rows}
        eligible_rows: list[dict[str, Any]] = []
        for user_id, phone_alias in eligible_phone_aliases.items():
            user_row = users_by_id.get(user_id) or {}
            row = dict(rows_by_user_id.get(user_id) or {})
            row.setdefault("user_id", user_id)
            row["identifier"] = _normalize_text(row.get("identifier")) or _normalize_text(
                user_row.get("identifier")
            ) or user_id
            row["phone"] = phone_alias["phone"]
            row["phone_alias_source"] = phone_alias["source"]
            row["phone_alias_created_at"] = phone_alias["created_at"]
            row["phone_verified_at"] = phone_alias["verified_at"]
            row["user_created_at"] = _normalize_text(user_row.get("createdAt"))
            row["user_metadata"] = user_row.get("metadata") or {}
            row["identity_metadata"] = phone_alias.get("identity_metadata") or {}
            eligible_rows.append(row)
        members = [self._member_from_row(row) for row in eligible_rows]
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

    def _select_rows_paginated(
        self,
        *,
        table: str,
        params: dict[str, Any],
        limit: int,
        page_size: int = _MEMBER_DIRECTORY_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        bounded_page_size = max(1, min(page_size, _MEMBER_DIRECTORY_PAGE_SIZE, limit))
        while len(rows) < limit:
            remaining = limit - len(rows)
            batch_limit = min(bounded_page_size, remaining)
            batch = self._select_rows(
                table=table,
                params={
                    **params,
                    "limit": batch_limit,
                    "offset": offset,
                },
            )
            rows.extend(batch[:remaining])
            if len(batch) < batch_limit:
                break
            offset += batch_limit
        return rows

    def _eligible_phone_aliases(self, *, limit: int) -> dict[str, dict[str, Any]]:
        rows = self._select_rows_paginated(
            table="user_identity_aliases",
            params={
                "select": "user_id,alias_value,source,created_at,verified_at,metadata",
                "alias_type": "eq.phone",
                # Recent phone registrations must not be starved by old backfill
                # aliases when the alias table exceeds the read cap.
                "order": "created_at.desc,user_id.asc",
            },
            limit=min(limit * 4, _MAX_MEMBER_DIRECTORY_ROWS),
        )
        aliases: dict[str, dict[str, Any]] = {}
        for row in rows:
            user_id = _normalize_text(row.get("user_id"))
            source = _normalize_text(row.get("source"))
            phone = _normalize_phone(row.get("alias_value"))
            if (
                not user_id
                or source not in _TRUSTED_PHONE_ALIAS_SOURCES
                or not _is_cn_mainland_mobile(phone)
            ):
                continue
            aliases.setdefault(
                user_id,
                {
                    "phone": phone,
                    "source": source,
                    "created_at": _normalize_text(row.get("created_at")),
                    "verified_at": _normalize_text(row.get("verified_at")),
                    "identity_metadata": _identity_metadata_from_mapping(row.get("metadata")),
                },
            )
            if len(aliases) >= limit:
                break
        return aliases

    @staticmethod
    def _member_from_row(row: dict[str, Any]) -> dict[str, Any]:
        user_id = _normalize_text(row.get("user_id") or row.get("identifier"))
        identifier = _normalize_text(row.get("identifier"))
        plan_id = _normalize_text(row.get("plan_id"))
        phone = _normalize_text(row.get("phone"))
        phone_alias_source = _normalize_text(row.get("phone_alias_source"))
        phone_alias_created_at = _normalize_text(row.get("phone_alias_created_at"))
        phone_verified_at = _normalize_text(row.get("phone_verified_at"))
        identity_metadata = _identity_metadata_from_mapping(row.get("identity_metadata"))
        identity_metadata = _merge_identity_metadata(row.get("user_metadata"), identity_metadata)
        wallet_created_at = _normalize_text(row.get("wallet_created_at"))
        user_created_at = _normalize_text(row.get("user_created_at"))
        wallet_updated_at = _normalize_text(row.get("wallet_updated_at"))
        phone_registered_at = ""
        if phone_alias_source == "phone_verification":
            phone_registered_at = phone_verified_at or phone_alias_created_at
        created_at = (
            phone_registered_at
            or wallet_created_at
            or user_created_at
            or _UNKNOWN_CREATED_AT
        )
        # 对话活跃事实不在这里派生（chat_conversations 是死表）；
        # last_active_at 的真实值由 SQLite session 活跃合并覆盖。
        last_active_at = wallet_updated_at or wallet_created_at or _UNKNOWN_CREATED_AT
        aliases = sorted({value for value in (user_id, identifier) if value})
        has_user_record = _coerce_bool(row.get("has_user_record"))
        has_wallet = _coerce_bool(row.get("has_wallet"))
        has_profile = _coerce_bool(row.get("has_profile"))
        return {
            "user_id": user_id,
            "canonical_user_id": user_id,
            "external_auth_user_id": user_id,
            "alias_user_ids": aliases,
            "display_name": _normalize_text(row.get("display_name")) or identifier or user_id,
            "phone": phone,
            "tier": plan_id or "trial",
            "status": "active" if any((has_user_record, has_wallet, has_profile, phone)) else "inactive",
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
            "identity_metadata": identity_metadata,
            "member_directory_source": "supabase.phone_identity_aliases+v_members",
            # 宁缺毋假：total_conversations/total_messages/has_chat_history 来自
            # 死表 chat_conversations，已明确移除；真实对话统计走 SQLite sessions。
            "member_directory_metrics": {
                "has_user_record": has_user_record,
                "has_wallet": has_wallet,
                "has_profile": has_profile,
            },
        }


_instance: SupabaseMemberDirectoryReadModel | None = None


def get_member_directory_read_model() -> SupabaseMemberDirectoryReadModel:
    global _instance
    if _instance is None:
        _instance = SupabaseMemberDirectoryReadModel()
    return _instance
