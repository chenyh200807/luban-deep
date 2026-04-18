from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.observability.bailian_billing import (
    BailianBillingClient,
    BailianBillingConfig,
)


class _FakeDescribeInstanceBillRequest:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeModels:
    DescribeInstanceBillRequest = _FakeDescribeInstanceBillRequest


class _FakeResponseBody:
    def __init__(self, payload) -> None:
        self._payload = payload

    def to_map(self):
        return self._payload


class _FakeResponse:
    def __init__(self, payload) -> None:
        self.body = _FakeResponseBody(payload)


class _FakeClient:
    def __init__(self, _config, pages) -> None:
        self._pages = pages

    def describe_instance_bill(self, request):
        token = getattr(request, "next_token", None) or ""
        return _FakeResponse(self._pages[token])


@pytest.mark.asyncio
async def test_bailian_billing_client_aggregates_cycles_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "": {
            "Data": {
                "Items": [
                    {
                        "InstanceID": "2880115;llm-910ww5yeitoaabl2;deepseek-v3.2;input_token;;0",
                        "PretaxAmount": 1.25,
                        "AfterDiscountAmount": 1.25,
                        "Currency": "CNY",
                    },
                    {
                        "InstanceID": "2880115;llm-910ww5yeitoaabl2;deepseek-v3.2;output_token;;0",
                        "PretaxAmount": 2.5,
                        "AfterDiscountAmount": 2.5,
                        "Currency": "CNY",
                    },
                    {
                        "InstanceID": "other-key;llm-910ww5yeitoaabl2;deepseek-v3.2;output_token;;0",
                        "PretaxAmount": 99,
                        "AfterDiscountAmount": 99,
                        "Currency": "CNY",
                    },
                ],
                "NextToken": "page-2",
            }
        },
        "page-2": {
            "Data": {
                "Items": [
                    {
                        "InstanceID": "2880115;llm-910ww5yeitoaabl2;text-embedding-v3;input_token;;0",
                        "PretaxAmount": 0.5,
                        "AfterDiscountAmount": 0.45,
                        "Currency": "CNY",
                    },
                    {
                        "InstanceID": "2880115;other-workspace;deepseek-v3.2;input_token;;0",
                        "PretaxAmount": 88,
                        "AfterDiscountAmount": 88,
                        "Currency": "CNY",
                    },
                ],
                "NextToken": "",
            }
        },
    }

    def _fake_load_sdk():
        return (
            lambda config: _FakeClient(config, pages),
            _FakeModels,
            SimpleNamespace(Config=lambda **kwargs: SimpleNamespace(**kwargs)),
        )

    monkeypatch.setattr(BailianBillingClient, "_load_sdk", staticmethod(_fake_load_sdk))

    client = BailianBillingClient(
        BailianBillingConfig(
            access_key_id="ak",
            access_key_secret="sk",
            workspace_id="llm-910ww5yeitoaabl2",
            apikey_id="2880115",
        )
    )

    totals = await client.get_totals(
        billing_cycles=["2026-04"],
        workspace_id="llm-910ww5yeitoaabl2",
        apikey_id="2880115",
    )

    assert totals.pretax_amount == pytest.approx(4.25)
    assert totals.after_discount_amount == pytest.approx(4.2)
    assert totals.items_count == 3
    assert totals.model_amounts == {
        "deepseek-v3.2": pytest.approx(3.75),
        "text-embedding-v3": pytest.approx(0.5),
    }
    assert totals.usage_kind_amounts == {
        "input_token": pytest.approx(1.75),
        "output_token": pytest.approx(2.5),
    }
    assert totals.billing_cycles[0]["billing_cycle"] == "2026-04"


@pytest.mark.asyncio
async def test_bailian_billing_client_returns_empty_when_unconfigured() -> None:
    client = BailianBillingClient(BailianBillingConfig())
    totals = await client.get_totals(billing_cycles=["2026-04"])
    assert totals.pretax_amount == 0.0
    assert totals.items_count == 0
