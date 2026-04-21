from __future__ import annotations

import httpx

from deeptutor.services.wallet.service import SupabaseWalletService


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.supabase.co")

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class _FakeWalletRestClient:
    def __init__(self) -> None:
        self.wallet = {
            "user_id": "wallet_user_1",
            "balance_micros": 100_000_000,
            "frozen_micros": 0,
            "plan_id": "free",
            "version": 2,
            "created_at": "2026-04-21T10:00:00+08:00",
        }
        self.ledger: list[dict[str, object]] = []
        self.patch_calls = 0
        self.post_calls = 0

    def get(self, url: str, headers=None, params=None):
        del headers
        params = dict(params or {})
        if url.endswith("/rest/v1/wallets"):
            user_id = str(params.get("user_id", "")).removeprefix("eq.")
            if user_id == self.wallet["user_id"]:
                return _FakeResponse([dict(self.wallet)])
            return _FakeResponse([])
        if url.endswith("/rest/v1/wallet_ledger"):
            user_id = str(params.get("user_id", "")).removeprefix("eq.")
            idempotency_key = str(params.get("idempotency_key", "")).removeprefix("eq.")
            rows = [row for row in self.ledger if row["user_id"] == user_id]
            if idempotency_key:
                rows = [row for row in rows if row["idempotency_key"] == idempotency_key]
            return _FakeResponse([dict(row) for row in rows])
        raise AssertionError(f"unexpected GET url: {url}")

    def patch(self, url: str, headers=None, params=None, json=None):
        del headers
        params = dict(params or {})
        payload = dict(json or {})
        self.patch_calls += 1
        if not url.endswith("/rest/v1/wallets"):
            raise AssertionError(f"unexpected PATCH url: {url}")
        user_id = str(params.get("user_id", "")).removeprefix("eq.")
        version = int(str(params.get("version", "eq.-1")).removeprefix("eq."))
        if user_id != self.wallet["user_id"] or version != int(self.wallet["version"]):
            return _FakeResponse([])
        self.wallet["balance_micros"] = int(payload["balance_micros"])
        self.wallet["version"] = int(payload["version"])
        return _FakeResponse([dict(self.wallet)])

    def post(self, url: str, headers=None, json=None):
        del headers
        rows = list(json or [])
        self.post_calls += 1
        if not url.endswith("/rest/v1/wallet_ledger"):
            raise AssertionError(f"unexpected POST url: {url}")
        inserted: list[dict[str, object]] = []
        for index, row in enumerate(rows, start=1):
            item = {
                "id": f"evt_{index}",
                "created_at": "2026-04-21T10:01:00+08:00",
                **dict(row),
            }
            self.ledger.append(item)
            inserted.append(dict(item))
        return _FakeResponse(inserted)


class _InvalidUuidWalletRestClient:
    def get(self, url: str, headers=None, params=None):
        del headers
        params = dict(params or {})
        request = httpx.Request("GET", url, params=params)
        user_id = str(params.get("user_id", "")).removeprefix("eq.")
        if url.endswith("/rest/v1/wallets") or url.endswith("/rest/v1/wallet_ledger"):
            if user_id.startswith("wx_"):
                response = httpx.Response(
                    400,
                    request=request,
                    json={
                        "code": "22P02",
                        "details": None,
                        "hint": None,
                        "message": f'invalid input syntax for type uuid: "{user_id}"',
                    },
                )
                raise httpx.HTTPStatusError("request failed", request=request, response=response)
            return _FakeResponse([])
        raise AssertionError(f"unexpected GET url: {url}")


class _SeedWalletRestClient:
    def __init__(self) -> None:
        self.wallets: dict[str, dict[str, object]] = {}
        self.ledger: list[dict[str, object]] = []
        self.post_calls: list[tuple[str, list[dict[str, object]]]] = []

    def get(self, url: str, headers=None, params=None):
        del headers
        params = dict(params or {})
        if url.endswith("/rest/v1/wallets"):
            user_id = str(params.get("user_id", "")).removeprefix("eq.")
            wallet = self.wallets.get(user_id)
            return _FakeResponse([dict(wallet)] if wallet else [])
        if url.endswith("/rest/v1/wallet_ledger"):
            user_id = str(params.get("user_id", "")).removeprefix("eq.")
            idempotency_key = str(params.get("idempotency_key", "")).removeprefix("eq.")
            rows = [row for row in self.ledger if row["user_id"] == user_id]
            if idempotency_key:
                rows = [row for row in rows if row["idempotency_key"] == idempotency_key]
            return _FakeResponse([dict(row) for row in rows])
        raise AssertionError(f"unexpected GET url: {url}")

    def post(self, url: str, headers=None, json=None):
        del headers
        rows = [dict(item) for item in list(json or [])]
        self.post_calls.append((url, rows))
        if url.endswith("/rest/v1/wallets"):
            inserted: list[dict[str, object]] = []
            for row in rows:
                wallet = {
                    "created_at": "2026-04-21T10:00:00+08:00",
                    **row,
                }
                self.wallets[str(row["user_id"])] = wallet
                inserted.append(dict(wallet))
            return _FakeResponse(inserted)
        if url.endswith("/rest/v1/wallet_ledger"):
            inserted = []
            for index, row in enumerate(rows, start=1):
                item = {
                    "id": f"seed_evt_{index}",
                    "created_at": "2026-04-21T10:01:00+08:00",
                    **row,
                }
                self.ledger.append(item)
                inserted.append(dict(item))
            return _FakeResponse(inserted)
        raise AssertionError(f"unexpected POST url: {url}")


def test_capture_points_writes_wallet_and_ledger() -> None:
    client = _FakeWalletRestClient()
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=client,
    )

    result = service.capture_points(
        user_id="wallet_user_1",
        amount_points=20,
        idempotency_key="mini_program_capture:turn_1",
        reference_id="turn_1",
        metadata={"source": "wx_miniprogram"},
    )

    assert result.captured_micros == 20_000_000
    assert result.requested_micros == 20_000_000
    assert result.balance_after_micros == 80_000_000
    assert result.entry is not None
    assert result.entry.event_type == "debit"
    assert result.entry.reference_type == "ai_usage"
    assert result.entry.reference_id == "turn_1"
    assert result.entry.metadata["reason"] == "capture"
    assert result.entry.metadata["source"] == "wx_miniprogram"
    assert result.entry.id
    assert client.wallet["balance_micros"] == 80_000_000
    assert client.wallet["version"] == 3
    assert len(client.ledger) == 1
    assert client.ledger[0]["id"]
    assert client.ledger[0]["reason"] == "capture"
    assert client.ledger[0]["operator_type"] == "system"
    assert client.ledger[0]["operator_id"] == "wx_miniprogram"


def test_capture_points_is_idempotent_by_ledger_key() -> None:
    client = _FakeWalletRestClient()
    client.wallet["balance_micros"] = 80_000_000
    client.ledger.append(
        {
            "id": "evt_existing",
            "user_id": "wallet_user_1",
            "event_type": "debit",
            "delta_micros": -20_000_000,
            "balance_after_micros": 80_000_000,
            "frozen_after_micros": 0,
            "reference_type": "ai_usage",
            "reference_id": "turn_1",
            "idempotency_key": "mini_program_capture:turn_1",
            "metadata": {"reason": "capture", "source": "wx_miniprogram"},
            "created_at": "2026-04-21T10:01:00+08:00",
        }
    )
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=client,
    )

    result = service.capture_points(
        user_id="wallet_user_1",
        amount_points=20,
        idempotency_key="mini_program_capture:turn_1",
        reference_id="turn_1",
        metadata={"source": "wx_miniprogram"},
    )

    assert result.captured_micros == 20_000_000
    assert result.entry is not None
    assert result.entry.id == "evt_existing"
    assert client.patch_calls == 0
    assert client.post_calls == 0


def test_get_wallet_returns_none_for_invalid_uuid_identity_query() -> None:
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=_InvalidUuidWalletRestClient(),
    )

    assert service.get_wallet("wx_O4aNJg7O_wRk") is None


def test_list_wallet_ledger_returns_empty_for_invalid_uuid_identity_query() -> None:
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=_InvalidUuidWalletRestClient(),
    )

    assert service.list_wallet_ledger("wx_O4aNJg7O_wRk") == []


def test_ensure_wallet_seeded_creates_wallet_and_signup_bonus_ledger() -> None:
    client = _SeedWalletRestClient()
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=client,
    )

    snapshot = service.ensure_wallet_seeded(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        opening_points=120,
        plan_id="trial",
        reference_type="signup_bonus",
        reference_id="wx_user_bootstrap",
        idempotency_key="signup_bonus:2d9eac15-5d26-4e93-941b-9ec6345ce6d9:member_console_bootstrap",
        metadata={"source": "member_console_auth_bootstrap"},
    )

    assert snapshot is not None
    assert snapshot.user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert snapshot.balance_micros == 120_000_000
    assert snapshot.plan_id == "trial"
    assert client.wallets[snapshot.user_id]["version"] == 1
    assert len(client.ledger) == 1
    assert client.ledger[0]["id"]
    assert client.ledger[0]["event_type"] == "grant"
    assert client.ledger[0]["reference_type"] == "signup_bonus"
    assert client.ledger[0]["reason"] == "signup_bonus"
    assert client.ledger[0]["operator_type"] == "system"
    assert client.ledger[0]["operator_id"] == "member_console_auth_bootstrap"
    assert client.ledger[0]["metadata"]["reason"] == "signup_bonus"


def test_ensure_wallet_seeded_backfills_missing_opening_ledger_for_existing_wallet() -> None:
    client = _SeedWalletRestClient()
    client.wallets["2d9eac15-5d26-4e93-941b-9ec6345ce6d9"] = {
        "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        "balance_micros": 120_000_000,
        "frozen_micros": 0,
        "plan_id": "trial",
        "version": 1,
        "created_at": "2026-04-21T10:00:00+08:00",
    }
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=client,
    )

    snapshot = service.ensure_wallet_seeded(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        opening_points=120,
        plan_id="trial",
        reference_type="signup_bonus",
        reference_id="wx_user_bootstrap",
        idempotency_key="signup_bonus:2d9eac15-5d26-4e93-941b-9ec6345ce6d9:member_console_bootstrap",
        metadata={"source": "member_console_auth_bootstrap"},
    )

    assert snapshot is not None
    assert len(client.ledger) == 1
    assert client.ledger[0]["reason"] == "signup_bonus"
    assert client.ledger[0]["operator_type"] == "system"
    assert client.ledger[0]["operator_id"] == "member_console_auth_bootstrap"
    assert client.ledger[0]["idempotency_key"] == (
        "signup_bonus:2d9eac15-5d26-4e93-941b-9ec6345ce6d9:member_console_bootstrap"
    )
