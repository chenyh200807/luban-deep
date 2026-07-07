from __future__ import annotations

import httpx
import pytest

from deeptutor.services.wallet.service import (
    SupabaseWalletService,
    WalletInsufficientBalanceError,
    is_billing_enforcement_enabled,
)


def test_is_billing_enforcement_enabled_defaults_on_for_launch(monkeypatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", raising=False)
    assert is_billing_enforcement_enabled() is True


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_is_billing_enforcement_enabled_honors_truthy_env(monkeypatch, raw: str) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", raw)
    assert is_billing_enforcement_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "off", "no"])
def test_is_billing_enforcement_enabled_treats_falsey_env_as_off(monkeypatch, raw: str) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", raw)
    assert is_billing_enforcement_enabled() is False


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
        self.patch_calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

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

    def patch(self, url: str, headers=None, params=None, json=None):
        del headers
        payload = dict(json or {})
        query = dict(params or {})
        self.patch_calls.append((url, query, payload))
        if not url.endswith("/rest/v1/wallets"):
            raise AssertionError(f"unexpected PATCH url: {url}")
        user_id = str(query.get("user_id", "")).removeprefix("eq.")
        wallet = self.wallets.get(user_id)
        if not wallet:
            return _FakeResponse([])
        wallet.update(payload)
        return _FakeResponse([dict(wallet)])


def test_capture_points_writes_wallet_and_ledger() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/rpc/apply_wallet_mutation")
        payload = request.read().decode("utf-8")
        assert '"p_event_type":"debit"' in payload
        assert '"p_delta_micros":-20000000' in payload
        assert '"p_idempotency_key":"mini_program_capture:turn_1"' in payload
        assert '"p_reference_type":"ai_usage"' in payload
        assert '"p_operator_id":"turn_1"' in payload
        return httpx.Response(
            200,
            json=[
                {
                    "ledger_event_id": "evt_capture_1",
                    "user_id": "wallet_user_1",
                    "event_type": "debit",
                    "delta_micros": -20_000_000,
                    "balance_micros": 80_000_000,
                    "frozen_micros": 0,
                    "version": 3,
                    "idempotency_key": "mini_program_capture:turn_1",
                    "reference_type": "ai_usage",
                    "reference_id": "turn_1",
                    "created_at": "2026-04-21T10:01:00+08:00",
                }
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
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
    assert result.entry.id == "evt_capture_1"
    assert result.entry.event_type == "debit"
    assert result.entry.reference_type == "ai_usage"
    assert result.entry.reference_id == "turn_1"
    assert result.entry.metadata["reason"] == "capture"
    assert result.entry.metadata["source"] == "wx_miniprogram"


def test_capture_points_is_idempotent_by_ledger_key() -> None:
    calls = {"rpc": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        calls["rpc"] += 1
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/rpc/apply_wallet_mutation")
        return httpx.Response(
            200,
            json=[
                {
                    "ledger_event_id": "evt_existing",
                    "user_id": "wallet_user_1",
                    "event_type": "debit",
                    "delta_micros": -20_000_000,
                    "balance_micros": 80_000_000,
                    "frozen_micros": 0,
                    "version": 3,
                    "idempotency_key": "mini_program_capture:turn_1",
                    "reference_type": "ai_usage",
                    "reference_id": "turn_1",
                    "created_at": "2026-04-21T10:01:00+08:00",
                }
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
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
    assert calls["rpc"] == 1


def test_record_usage_points_is_noop_when_enforcement_disabled(monkeypatch) -> None:
    # Explicit internal-beta override: enforcement OFF -> no balance mutation,
    # no ledger write. The wallet stays pristine and the call returns a skipped
    # result.
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "false")
    client = _FakeWalletRestClient()
    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=client,
    )

    result = service.record_usage_points(
        user_id="wallet_user_1",
        amount_points=20,
        idempotency_key="mini_program_capture:turn_usage_1",
        reference_id="turn_usage_1",
        metadata={"source": "wx_miniprogram"},
    )

    assert result.captured_micros == 0
    assert result.requested_micros == 20_000_000
    assert result.balance_after_micros == 0
    assert result.entry is None
    assert client.post_calls == 0
    assert client.ledger == []
    assert client.wallet["balance_micros"] == 100_000_000


def test_record_usage_points_debits_wallet_atomically_when_enforcement_enabled(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")
    rpc_calls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/rpc/apply_wallet_mutation")
        payload = request.read().decode("utf-8")
        rpc_calls.append(payload)
        assert '"p_event_type":"debit"' in payload
        assert '"p_delta_micros":-20000000' in payload
        assert '"p_idempotency_key":"mini_program_capture:turn_usage_2"' in payload
        return httpx.Response(
            200,
            json=[
                {
                    "ledger_event_id": "evt_usage_2",
                    "user_id": "wallet_user_1",
                    "event_type": "debit",
                    "delta_micros": -20_000_000,
                    "balance_micros": 80_000_000,
                    "frozen_micros": 0,
                    "version": 5,
                    "idempotency_key": "mini_program_capture:turn_usage_2",
                    "reference_type": "ai_usage",
                    "reference_id": "turn_usage_2",
                    "created_at": "2026-04-21T10:01:00+08:00",
                }
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    result = service.record_usage_points(
        user_id="wallet_user_1",
        amount_points=20,
        idempotency_key="mini_program_capture:turn_usage_2",
        reference_id="turn_usage_2",
        metadata={"source": "wx_miniprogram"},
    )

    # Balance truly decremented to balance + delta (100M - 20M).
    assert result.captured_micros == 20_000_000
    assert result.requested_micros == 20_000_000
    assert result.balance_after_micros == 80_000_000
    assert result.entry is not None
    assert result.entry.id == "evt_usage_2"
    assert result.entry.event_type == "debit"
    assert result.entry.balance_after_micros == 80_000_000
    assert len(rpc_calls) == 1


def test_record_usage_points_raises_and_writes_nothing_on_insufficient_balance(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "1")

    def _handler(request: httpx.Request) -> httpx.Response:
        # RPC raises P0001 insufficient inside the transaction; no ledger row.
        return httpx.Response(
            400,
            json={
                "message": "Insufficient wallet balance.",
                "details": "available_micros=1000000 requested_delta_micros=-20000000",
                "code": "P0001",
            },
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    with pytest.raises(WalletInsufficientBalanceError):
        service.record_usage_points(
            user_id="wallet_user_1",
            amount_points=20,
            idempotency_key="mini_program_capture:turn_usage_3",
            reference_id="turn_usage_3",
            metadata={"source": "wx_miniprogram"},
        )


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


def test_ensure_wallet_seeded_updates_existing_wallet_plan_without_granting_points() -> None:
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
        opening_points=0,
        plan_id="vip",
        reference_type="manual_membership_purchase",
        reference_id="purchase_1",
        idempotency_key="wallet_seed:manual_membership:purchase_1",
        metadata={"source": "bi_manual_membership"},
    )

    assert snapshot is not None
    assert snapshot.plan_id == "vip"
    assert client.wallets[snapshot.user_id]["plan_id"] == "vip"
    assert client.patch_calls[-1][2] == {"plan_id": "vip"}
    assert client.ledger == []


def test_debit_points_posts_rpc_and_normalizes_mutation_result() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/rpc/apply_wallet_mutation")
        payload = request.read().decode("utf-8")
        assert '"p_user_id":"2d9eac15-5d26-4e93-941b-9ec6345ce6d9"' in payload
        assert '"p_event_type":"debit"' in payload
        assert '"p_delta_micros":-20000000' in payload
        assert '"p_reference_type":"ai_usage"' in payload
        assert '"p_reference_id":"turn_123"' in payload
        assert '"p_idempotency_key":"capture:turn_123"' in payload
        return httpx.Response(
            200,
            json=[
                {
                    "ledger_event_id": "evt_capture_123",
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "event_type": "debit",
                    "delta_micros": -20000000,
                    "balance_micros": 580000000,
                    "frozen_micros": 0,
                    "version": 13,
                    "idempotency_key": "capture:turn_123",
                    "reference_type": "ai_usage",
                    "reference_id": "turn_123",
                    "created_at": "2026-04-19T12:10:00+08:00",
                }
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    result = service.debit_points(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        amount_micros=20_000_000,
        reference_type="ai_usage",
        reference_id="turn_123",
        idempotency_key="capture:turn_123",
        reason="capture",
        operator_type="system",
        operator_id="turn_runtime",
        metadata={"source": "wx_miniprogram"},
    )

    assert result.ledger_event_id == "evt_capture_123"
    assert result.user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert result.balance_micros == 580000000
    assert result.version == 13


def test_debit_points_maps_supabase_insufficient_balance_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "message": "Insufficient wallet balance.",
                "details": "available_micros=1000000 requested_delta_micros=-20000000",
                "code": "P0001",
            },
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    with pytest.raises(WalletInsufficientBalanceError, match="Insufficient wallet balance"):
        service.debit_points(
            user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            amount_micros=20_000_000,
            reference_type="ai_usage",
            reference_id="turn_123",
            idempotency_key="capture:turn_123",
        )


def test_grant_points_posts_positive_grant_mutation() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/rpc/apply_wallet_mutation")
        payload = request.read().decode("utf-8")
        assert '"p_event_type":"grant"' in payload
        assert '"p_delta_micros":600000000' in payload
        assert '"p_reference_type":"order"' in payload
        assert '"p_reference_id":"order_123"' in payload
        assert '"p_reason":"purchase_grant"' in payload
        return httpx.Response(
            200,
            json={
                "ledger_event_id": "evt_grant_123",
                "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "event_type": "grant",
                "delta_micros": 600000000,
                "balance_micros": 1200000000,
                "frozen_micros": 0,
                "version": 16,
                "idempotency_key": "grant:order_123",
                "reference_type": "order",
                "reference_id": "order_123",
                "created_at": "2026-04-19T12:20:00+08:00",
            },
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    result = service.grant_points(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        amount_micros=600_000_000,
        reference_type="order",
        reference_id="order_123",
        idempotency_key="grant:order_123",
        reason="purchase_grant",
        metadata={"channel": "wechat_pay"},
    )

    assert result.ledger_event_id == "evt_grant_123"
    assert result.event_type == "grant"
    assert result.delta_micros == 600000000
    assert result.balance_micros == 1200000000
