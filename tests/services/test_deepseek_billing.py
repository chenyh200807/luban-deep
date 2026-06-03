from __future__ import annotations

import pytest

from deeptutor.services.observability.deepseek_billing import (
    DeepSeekBalanceTotals,
    DeepSeekBillingClient,
    DeepSeekBillingConfig,
)


def test_deepseek_balance_totals_parse_official_payload() -> None:
    payload = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "CNY",
                "total_balance": "110.00",
                "granted_balance": "10.00",
                "topped_up_balance": "100.00",
            }
        ],
    }

    totals = DeepSeekBalanceTotals.from_payload(payload)

    assert totals.is_available is True
    assert totals.currency_balances["CNY"]["total_balance"] == 110.0
    assert totals.currency_balances["CNY"]["granted_balance"] == 10.0
    assert totals.currency_balances["CNY"]["topped_up_balance"] == 100.0


@pytest.mark.asyncio
async def test_deepseek_balance_returns_unconfigured_without_api_key() -> None:
    class FailingHttpClient:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("HTTP should not be called without an API key")

    client = DeepSeekBillingClient(
        DeepSeekBillingConfig(api_key=""),
        http_client=FailingHttpClient(),
    )

    totals = await client.get_balance()

    assert totals.status == "unconfigured"
    assert totals.is_available is False


@pytest.mark.asyncio
async def test_deepseek_balance_client_fetches_official_balance_endpoint() -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "USD",
                        "total_balance": "1.25",
                        "granted_balance": "0",
                        "topped_up_balance": "1.25",
                    }
                ],
            }

    class FakeHttpClient:
        async def get(self, url: str, *, headers: dict[str, str], timeout: float):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["timeout"] = timeout
            return FakeResponse()

    client = DeepSeekBillingClient(
        DeepSeekBillingConfig(api_key="sk-test", base_url="https://api.deepseek.com"),
        http_client=FakeHttpClient(),
    )

    totals = await client.get_balance()

    assert captured["url"] == "https://api.deepseek.com/user/balance"
    assert captured["headers"] == {"Authorization": "Bearer sk-test"}
    assert totals.status == "ok"
    assert totals.currency_balances["USD"]["total_balance"] == 1.25
