"""H4 Gate: _create_payment_gateway_order must be async (non-blocking).

Single uvicorn worker + sync httpx.post(timeout=8s) = event loop blocked 8s
per payment call, freezing all concurrent WS users.
"""
from __future__ import annotations

import inspect
import pytest


def test_payment_gateway_order_is_coroutine():
    """_create_payment_gateway_order must be an async def to avoid blocking the event loop."""
    from deeptutor.api.routers.mobile import _create_payment_gateway_order  # type: ignore[attr-defined]

    assert inspect.iscoroutinefunction(_create_payment_gateway_order), (
        "_create_payment_gateway_order uses sync httpx.post which blocks the event loop; "
        "it must be async and use httpx.AsyncClient"
    )


@pytest.mark.asyncio
async def test_payment_gateway_returns_none_when_unconfigured(monkeypatch):
    """When no gateway URL is configured, the async function returns None without IO."""
    monkeypatch.setenv("DEEPTUTOR_PAYMENT_GATEWAY_URL", "")
    from deeptutor.api.routers.mobile import _create_payment_gateway_order  # type: ignore[attr-defined]

    result = await _create_payment_gateway_order({"amount": 1000})
    assert result is None
