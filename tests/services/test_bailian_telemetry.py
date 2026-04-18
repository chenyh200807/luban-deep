from __future__ import annotations

import httpx
import pytest

from deeptutor.services.observability.bailian_telemetry import (
    BailianTelemetryClient,
    BailianTelemetryConfig,
)


@pytest.mark.asyncio
async def test_bailian_telemetry_client_queries_prometheus_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_queries: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_queries.append(str(request.url))
        query = request.url.params.get("query", "")
        if 'sum by (model) (increase(model_usage{usage_type="input_tokens",workspace_id="ws-1",apikey_id="42"}[3600s]))' in query:
            payload = {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"model": "deepseek-v3.2"}, "value": [0, "120"]},
                        {"metric": {"model": "text-embedding-v3"}, "value": [0, "5"]},
                    ],
                },
            }
        elif 'sum by (model) (increase(model_usage{usage_type="output_tokens",workspace_id="ws-1",apikey_id="42"}[3600s]))' in query:
            payload = {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"model": "deepseek-v3.2"}, "value": [0, "30"]},
                    ],
                },
            }
        elif 'sum by (model) (increase(model_usage{usage_type="total_tokens",workspace_id="ws-1",apikey_id="42"}[3600s]))' in query:
            payload = {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"model": "deepseek-v3.2"}, "value": [0, "150"]},
                        {"metric": {"model": "text-embedding-v3"}, "value": [0, "5"]},
                    ],
                },
            }
        else:
            raise AssertionError(f"unexpected query: {query}")
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(_handler)
    original_async_client = httpx.AsyncClient

    def _fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client)

    client = BailianTelemetryClient(
        BailianTelemetryConfig(
            base_url="https://example.com/prometheus/demo/bailian-model-metrics",
            access_key_id="ak",
            access_key_secret="sk",
        )
    )
    totals = await client.get_usage_totals(
        start_ts=1_700_000_000,
        end_ts=1_700_003_600,
        workspace_id="ws-1",
        apikey_id="42",
    )

    assert totals.input_tokens == 125
    assert totals.output_tokens == 30
    assert totals.total_tokens == 155
    assert totals.models == {
        "deepseek-v3.2": 150,
        "text-embedding-v3": 5,
    }
    assert totals.model_details["deepseek-v3.2"]["input_tokens"] == 120
    assert totals.model_details["deepseek-v3.2"]["output_tokens"] == 30
    assert totals.model_details["deepseek-v3.2"]["estimated_cost_usd"] > 0
    assert totals.estimated_total_cost_usd > 0
    assert len(captured_queries) == 3


@pytest.mark.asyncio
async def test_bailian_telemetry_client_returns_empty_totals_when_unconfigured() -> None:
    client = BailianTelemetryClient(BailianTelemetryConfig())
    totals = await client.get_usage_totals(start_ts=0, end_ts=60)

    assert totals.input_tokens == 0
    assert totals.output_tokens == 0
    assert totals.total_tokens == 0
    assert totals.models == {}
    assert totals.model_details == {}
    assert totals.estimated_total_cost_usd == 0
