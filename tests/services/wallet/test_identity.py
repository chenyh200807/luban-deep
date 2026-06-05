from __future__ import annotations

import httpx

from deeptutor.services.wallet.identity import (
    IdentityInventoryRow,
    WalletIdentitySupabaseStore,
    WalletIdentityResolution,
    collect_identity_inventory_rows,
    resolve_wallet_identity,
)


def test_resolve_wallet_identity_prefers_canonical_uid_claim() -> None:
    result = resolve_wallet_identity(
        raw_user_id="user_2008",
        claims={"uid": "user_2008", "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"},
    )

    assert result == WalletIdentityResolution(
        raw_user_id="user_2008",
        canonical_user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        source="claims.canonical_uid",
        needs_lookup=False,
    )


def test_resolve_wallet_identity_accepts_uuid_raw_user_id() -> None:
    result = resolve_wallet_identity(
        raw_user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        claims={"uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"},
    )

    assert result == WalletIdentityResolution(
        raw_user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        canonical_user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        source="raw_user_id",
        needs_lookup=False,
    )


def test_resolve_wallet_identity_marks_legacy_id_for_lookup_when_no_uuid_present() -> None:
    result = resolve_wallet_identity(
        raw_user_id="user_2008",
        claims={"uid": "user_2008", "provider": "local"},
    )

    assert result == WalletIdentityResolution(
        raw_user_id="user_2008",
        canonical_user_id="",
        source="unresolved",
        needs_lookup=True,
    )


def test_collect_identity_inventory_rows_flattens_member_aliases() -> None:
    rows = collect_identity_inventory_rows(
        members=[
            {
                "user_id": "user_2008",
                "auth_username": "chenyh2008",
                "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "wx_openid": "openid_123",
                "wx_unionid": "union_123",
                "phone": "13812345678",
            }
        ]
    )

    assert IdentityInventoryRow(
        alias_type="legacy_user_id",
        alias_value="user_2008",
        member_user_id="user_2008",
        canonical_user_id="",
        source="member_console",
    ) in rows
    assert IdentityInventoryRow(
        alias_type="external_auth_user_id",
        alias_value="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        member_user_id="user_2008",
        canonical_user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        source="member_console",
    ) in rows


def test_wallet_identity_supabase_store_resolves_alias_row() -> None:
    calls = []

    class _FakeClient:
        def get(self, url, *, headers=None, params=None):
            calls.append({"url": url, "headers": headers, "params": params})
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json=[
                    {
                        "alias_type": "legacy_user_id",
                        "alias_value": "user_2008",
                        "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    }
                ],
            )

    store = WalletIdentitySupabaseStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=_FakeClient(),
    )

    row = store.resolve_alias(alias_type="legacy_user_id", alias_value="user_2008")

    assert row is not None
    assert row["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert calls[0]["params"]["alias_type"] == "eq.legacy_user_id"
    assert calls[0]["params"]["alias_value"] == "eq.user_2008"


def test_wallet_identity_supabase_store_treats_missing_alias_read_model_as_alias_miss() -> None:
    class _FakeClient:
        def get(self, url, *, headers=None, params=None):
            return httpx.Response(
                404,
                request=httpx.Request("GET", url),
                json={"message": "relation user_identity_aliases does not exist"},
            )

    store = WalletIdentitySupabaseStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=_FakeClient(),
    )

    assert store.resolve_alias(alias_type="legacy_user_id", alias_value="user_2008") is None
