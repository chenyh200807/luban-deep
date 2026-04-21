from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from deeptutor.services.member_console import get_member_console_service
from deeptutor.services.wallet import get_wallet_identity_store, get_wallet_service
from deeptutor.services.wallet.identity import is_uuid_like


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_points(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mint_canonical_uid(member: dict[str, Any]) -> str:
    legacy_user_id = _normalize_text(member.get("user_id"))
    wx_openid = _normalize_text(member.get("wx_openid"))
    seed = f"deeptutor:member_console_wallet_identity_backfill:{legacy_user_id}:{wx_openid}"
    return str(uuid5(NAMESPACE_URL, seed))


def _stable_alias_payload(member: dict[str, Any]) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for alias_type, key in (
        ("legacy_user_id", "user_id"),
        ("auth_username", "auth_username"),
        ("wx_openid", "wx_openid"),
        ("wx_unionid", "wx_unionid"),
    ):
        value = _normalize_text(member.get(key))
        if value:
            aliases.append((alias_type, value))
    return aliases


def _migration_opening_balance_key(canonical_uid: str) -> str:
    return f"migration_opening_balance:{_normalize_text(canonical_uid)}:member_console_wallet_identity_backfill"


@dataclass(frozen=True, slots=True)
class BackfillAction:
    legacy_user_id: str
    canonical_uid: str
    resolution_source: str
    points_balance: int
    tier: str
    needs_user_insert: bool
    needs_wallet_seed: bool
    needs_local_member_link: bool
    alias_inserts: tuple[tuple[str, str], ...]
    metadata: dict[str, Any]


class SupabaseCanonicalAdminClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.Client | None = None,
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

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, table: str, *, params: dict[str, Any] | None = None, json_body: Any = None) -> Any:
        if not self.is_configured:
            raise RuntimeError("Supabase admin client is not configured")
        client = self._client or httpx.Client(timeout=10.0)
        try:
            response = client.request(
                method,
                f"{self._base_url.rstrip('/')}/rest/v1/{table}",
                headers=self._headers(),
                params=params,
                json=json_body,
            )
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()
        finally:
            if self._owns_client and self._client is None:
                client.close()

    def user_exists(self, user_id: str) -> bool:
        rows = self._request(
            "GET",
            "users",
            params={
                "select": "id",
                "id": f"eq.{_normalize_text(user_id)}",
                "limit": 1,
            },
        )
        return bool(rows)

    def create_user(self, *, user_id: str, identifier: str, metadata: dict[str, Any]) -> None:
        if self.user_exists(user_id):
            return
        self._request(
            "POST",
            "users",
            params={"select": "id"},
            json_body=[
                {
                    "id": _normalize_text(user_id),
                    "identifier": _normalize_text(identifier),
                    "createdAt": _utc_now(),
                    "metadata": dict(metadata or {}),
                }
            ],
        )

    def alias_exists(self, *, alias_type: str, alias_value: str, user_id: str) -> bool:
        rows = self._request(
            "GET",
            "user_identity_aliases",
            params={
                "select": "user_id",
                "alias_type": f"eq.{_normalize_text(alias_type)}",
                "alias_value": f"eq.{_normalize_text(alias_value)}",
                "user_id": f"eq.{_normalize_text(user_id)}",
                "limit": 1,
            },
        )
        return bool(rows)

    def ensure_alias(
        self,
        *,
        alias_type: str,
        alias_value: str,
        user_id: str,
        metadata: dict[str, Any],
    ) -> None:
        if self.alias_exists(alias_type=alias_type, alias_value=alias_value, user_id=user_id):
            return
        self._request(
            "POST",
            "user_identity_aliases",
            params={"select": "user_id"},
            json_body=[
                {
                    "user_id": _normalize_text(user_id),
                    "alias_type": _normalize_text(alias_type),
                    "alias_value": _normalize_text(alias_value),
                    "source": "member_console_backfill",
                    "confidence": 1.0,
                    "metadata": dict(metadata or {}),
                }
            ],
        )


def build_backfill_actions(
    *,
    members: list[dict[str, Any]],
    identity_store: Any,
    wallet_service: Any,
    admin_client: SupabaseCanonicalAdminClient,
    target_user_id: str = "",
) -> dict[str, Any]:
    actions: list[BackfillAction] = []
    summary = {
        "wx_total": 0,
        "planned_actions": 0,
        "minted_canonical_uid": 0,
        "resolved_via_existing_alias": 0,
        "already_linked": 0,
        "ambiguous_alias": 0,
    }
    target = _normalize_text(target_user_id)
    for member in members:
        if not isinstance(member, dict):
            continue
        legacy_user_id = _normalize_text(member.get("user_id"))
        if not legacy_user_id.startswith("wx_"):
            continue
        if target and legacy_user_id != target:
            continue
        summary["wx_total"] += 1
        existing_external_uid = _normalize_text(member.get("external_auth_user_id"))
        canonical_uid = existing_external_uid if is_uuid_like(existing_external_uid) else ""
        resolution_source = "external_auth_user_id" if canonical_uid else ""
        if not canonical_uid:
            candidates: list[str] = []
            for alias_type, alias_value in _stable_alias_payload(member):
                row = identity_store.resolve_alias(alias_type=alias_type, alias_value=alias_value)
                if not isinstance(row, dict):
                    continue
                alias_user_id = _normalize_text(row.get("user_id"))
                if alias_user_id and alias_user_id not in candidates:
                    candidates.append(alias_user_id)
            if len(candidates) == 1 and is_uuid_like(candidates[0]):
                canonical_uid = candidates[0]
                resolution_source = "existing_alias"
            elif len(candidates) > 1:
                summary["ambiguous_alias"] += 1
                continue
            else:
                canonical_uid = _mint_canonical_uid(member)
                resolution_source = "minted_uuid"
        alias_inserts: list[tuple[str, str]] = []
        for alias_type, alias_value in _stable_alias_payload(member):
            if not admin_client.alias_exists(
                alias_type=alias_type,
                alias_value=alias_value,
                user_id=canonical_uid,
            ):
                alias_inserts.append((alias_type, alias_value))
        opening_points = _coerce_points(member.get("points_balance"))
        wallet_exists = wallet_service.get_wallet(canonical_uid) is not None
        opening_ledger_exists = True
        if opening_points > 0:
            finder = getattr(wallet_service, "find_wallet_ledger_by_idempotency_key", None)
            if callable(finder):
                opening_ledger_exists = (
                    finder(
                        canonical_uid,
                        idempotency_key=_migration_opening_balance_key(canonical_uid),
                    )
                    is not None
                )
        needs_user_insert = not admin_client.user_exists(canonical_uid)
        needs_local_member_link = existing_external_uid != canonical_uid
        needs_wallet_seed = (not wallet_exists) or (opening_points > 0 and not opening_ledger_exists)
        metadata = {
            "source": "member_console_wallet_identity_backfill",
            "legacy_user_id": legacy_user_id,
            "wx_openid": _normalize_text(member.get("wx_openid")),
            "migration_batch": "member_console_wallet_identity_backfill",
        }
        needs_action = needs_user_insert or needs_wallet_seed or needs_local_member_link or bool(alias_inserts)
        if not needs_action:
            summary["already_linked"] += 1
            continue
        if resolution_source == "minted_uuid":
            summary["minted_canonical_uid"] += 1
        elif resolution_source == "existing_alias":
            summary["resolved_via_existing_alias"] += 1
        actions.append(
            BackfillAction(
                legacy_user_id=legacy_user_id,
                canonical_uid=canonical_uid,
                resolution_source=resolution_source,
                points_balance=_coerce_points(member.get("points_balance")),
                tier=_normalize_text(member.get("tier")),
                needs_user_insert=needs_user_insert,
                needs_wallet_seed=needs_wallet_seed,
                needs_local_member_link=needs_local_member_link,
                alias_inserts=tuple(alias_inserts),
                metadata=metadata,
            )
        )
    summary["planned_actions"] = len(actions)
    return {
        "summary": summary,
        "actions": [asdict(action) for action in actions],
    }


def apply_backfill_actions(
    *,
    actions: list[dict[str, Any]],
    member_service: Any,
    wallet_service: Any,
    admin_client: SupabaseCanonicalAdminClient,
) -> dict[str, int]:
    result = {
        "user_rows_inserted": 0,
        "alias_rows_inserted": 0,
        "wallets_seeded": 0,
        "local_members_linked": 0,
    }
    for action in actions:
        canonical_uid = _normalize_text(action.get("canonical_uid"))
        legacy_user_id = _normalize_text(action.get("legacy_user_id"))
        metadata = dict(action.get("metadata") or {})
        if action.get("needs_user_insert"):
            admin_client.create_user(
                user_id=canonical_uid,
                identifier=legacy_user_id,
                metadata=metadata,
            )
            result["user_rows_inserted"] += 1
        for alias_type, alias_value in list(action.get("alias_inserts") or []):
            admin_client.ensure_alias(
                alias_type=_normalize_text(alias_type),
                alias_value=_normalize_text(alias_value),
                user_id=canonical_uid,
                metadata=metadata,
            )
            result["alias_rows_inserted"] += 1
        if action.get("needs_wallet_seed"):
            wallet_service.ensure_wallet_seeded(
                user_id=canonical_uid,
                opening_points=_coerce_points(action.get("points_balance")),
                plan_id=_normalize_text(action.get("tier")),
                reference_type="migration",
                reference_id="opening_balance",
                idempotency_key=_migration_opening_balance_key(canonical_uid),
                metadata={
                    **metadata,
                    "reason": "migration_opening_balance",
                },
            )
            result["wallets_seeded"] += 1
        if action.get("needs_local_member_link"):
            def _persist(data: dict[str, Any]) -> None:
                target = member_service._ensure_member(data, legacy_user_id)
                target["external_auth_user_id"] = canonical_uid

            member_service._mutate(_persist)
            result["local_members_linked"] += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill legacy wx_* members into canonical wallet identity authority.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write Supabase/member_console changes. Default is dry-run.",
    )
    parser.add_argument(
        "--user-id",
        default="",
        help="Only backfill one legacy wx_* user_id.",
    )
    args = parser.parse_args()

    member_service = get_member_console_service()
    identity_store = get_wallet_identity_store()
    wallet_service = get_wallet_service()
    admin_client = SupabaseCanonicalAdminClient()
    if not getattr(identity_store, "is_configured", False):
        raise SystemExit("wallet identity store is not configured")
    if not getattr(wallet_service, "is_configured", False):
        raise SystemExit("wallet service is not configured")
    if not admin_client.is_configured:
        raise SystemExit("supabase admin client is not configured")

    data = member_service._load()
    members = list(data.get("members") or [])
    report = build_backfill_actions(
        members=members,
        identity_store=identity_store,
        wallet_service=wallet_service,
        admin_client=admin_client,
        target_user_id=args.user_id,
    )
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    **report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    apply_result = apply_backfill_actions(
        actions=list(report["actions"]),
        member_service=member_service,
        wallet_service=wallet_service,
        admin_client=admin_client,
    )
    print(
        json.dumps(
            {
                "mode": "apply",
                **report,
                "applied": apply_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
