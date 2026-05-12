from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from deeptutor.services.wallet.service import (
    SupabaseWalletService,
    WalletInsufficientBalanceError,
)


def test_get_wallet_returns_normalized_snapshot() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rest/v1/wallets")
        assert request.url.params["user_id"] == "eq.2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
        return httpx.Response(
            200,
            json=[
                {
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "balance_micros": 600000000,
                    "frozen_micros": 1000000,
                    "plan_id": "free",
                    "version": 12,
                    "created_at": "2026-04-19T12:00:00+08:00",
                }
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    snapshot = service.get_wallet("2d9eac15-5d26-4e93-941b-9ec6345ce6d9")

    assert snapshot is not None
    assert snapshot.user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert snapshot.balance_micros == 600000000
    assert snapshot.frozen_micros == 1000000
    assert snapshot.plan_id == "free"
    assert snapshot.version == 12


def test_list_wallet_ledger_returns_descending_entries() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rest/v1/wallet_ledger")
        assert request.url.params["user_id"] == "eq.2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
        assert request.url.params["limit"] == "2"
        assert request.url.params["offset"] == "0"
        assert request.url.params["order"] == "created_at.desc,id.desc"
        assert "frozen_after_micros" in request.url.params["select"]
        return httpx.Response(
            200,
            json=[
                {
                    "id": "evt_2",
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "event_type": "debit",
                    "delta_micros": -2000000,
                    "balance_after_micros": 598000000,
                    "frozen_after_micros": 0,
                    "reference_type": "ai_usage",
                    "reference_id": "msg_2",
                    "idempotency_key": "debit:msg_2",
                    "metadata": {"provider": "deepseek"},
                    "created_at": "2026-04-19T12:05:00+08:00",
                },
                {
                    "id": "evt_1",
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "event_type": "grant",
                    "delta_micros": 600000000,
                    "balance_after_micros": 600000000,
                    "frozen_after_micros": 0,
                    "reference_type": "plan",
                    "reference_id": "free",
                    "idempotency_key": "grant:free",
                    "metadata": {},
                    "created_at": "2026-04-19T12:00:00+08:00",
                },
            ],
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    entries = service.list_wallet_ledger("2d9eac15-5d26-4e93-941b-9ec6345ce6d9", limit=2, offset=0)

    assert [item.id for item in entries] == ["evt_2", "evt_1"]
    assert entries[0].delta_micros == -2000000
    assert entries[0].frozen_after_micros == 0
    assert entries[0].reference_type == "ai_usage"
    assert entries[1].idempotency_key == "grant:free"


def test_wallet_service_reports_unconfigured_without_env() -> None:
    service = SupabaseWalletService(base_url="", service_key="")

    assert service.is_configured is False
    assert service.get_wallet("user_2008") is None
    assert service.list_wallet_ledger("user_2008") == []
    with pytest.raises(RuntimeError, match="Wallet service is not configured"):
        service.debit_points(
            user_id="user_2008",
            amount_micros=20_000_000,
            reference_type="ai_usage",
            reference_id="turn_2008",
            idempotency_key="capture:turn_2008",
        )


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


def test_admin_adjust_points_posts_signed_adjustment() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode("utf-8")
        assert '"p_event_type":"admin_adjust"' in payload
        assert '"p_delta_micros":-5000000' in payload
        assert '"p_operator_type":"admin"' in payload
        assert '"p_operator_id":"ops_42"' in payload
        return httpx.Response(
            200,
            json={
                "ledger_event_id": "evt_adjust_123",
                "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "event_type": "admin_adjust",
                "delta_micros": -5000000,
                "balance_micros": 575000000,
                "frozen_micros": 0,
                "version": 17,
                "idempotency_key": "admin_adjust:ticket_42",
                "reference_type": "ticket",
                "reference_id": "ticket_42",
                "created_at": "2026-04-19T12:25:00+08:00",
            },
            request=request,
        )

    service = SupabaseWalletService(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    result = service.admin_adjust_points(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        delta_micros=-5_000_000,
        reference_id="ticket_42",
        idempotency_key="admin_adjust:ticket_42",
        operator_id="ops_42",
        metadata={"note": "manual correction"},
    )

    assert result.ledger_event_id == "evt_adjust_123"
    assert result.event_type == "admin_adjust"
    assert result.delta_micros == -5000000
