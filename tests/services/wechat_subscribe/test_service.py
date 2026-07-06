"""wechat_subscribe 域测试：§9-D12 降级契约——一切失败折叠为红点，绝不 raise。"""
from __future__ import annotations

import httpx
import pytest

from deeptutor.services.wechat_subscribe import (
    TEMPLATE_ENV_KEYS,
    send_subscribe_message,
)

_ENV_KEY = TEMPLATE_ENV_KEYS["next_day_retest"]


async def _token_ok() -> str:
    return "fake-token"


async def _token_boom() -> str:
    raise RuntimeError("token backend down")


def _patch_send(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


@pytest.mark.anyio
async def test_unconfigured_template_degrades_to_red_dot(monkeypatch):
    monkeypatch.delenv(_ENV_KEY, raising=False)
    result = await send_subscribe_message(
        openid="o-x", template_key="next_day_retest", data={},
        access_token_provider=_token_ok,
    )
    assert result.status == "degraded_red_dot"
    assert result.reason == "template_not_configured"


@pytest.mark.anyio
async def test_unregistered_template_key_is_programming_error():
    with pytest.raises(ValueError):
        await send_subscribe_message(
            openid="o-x", template_key="nope", data={},
            access_token_provider=_token_ok,
        )


@pytest.mark.anyio
async def test_token_failure_degrades_not_raises(monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "TMPL123")
    result = await send_subscribe_message(
        openid="o-x", template_key="next_day_retest", data={},
        access_token_provider=_token_boom,
    )
    assert result.status == "degraded_red_dot"
    assert result.reason == "access_token_unavailable"


@pytest.mark.anyio
async def test_send_success(monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "TMPL123")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "fake-token"
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    _patch_send(monkeypatch, handler)
    result = await send_subscribe_message(
        openid="o-x", template_key="next_day_retest",
        data={"thing1": {"value": "临时用电三级配电"}},
        access_token_provider=_token_ok,
    )
    assert result.sent


@pytest.mark.anyio
async def test_user_refused_43101_is_legal_degradation(monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "TMPL123")
    _patch_send(monkeypatch, lambda req: httpx.Response(
        200, json={"errcode": 43101, "errmsg": "user refused"}))
    result = await send_subscribe_message(
        openid="o-x", template_key="next_day_retest", data={},
        access_token_provider=_token_ok,
    )
    assert result.status == "degraded_red_dot"
    assert result.reason == "user_refused"
    assert result.errcode == 43101


@pytest.mark.anyio
async def test_upstream_http_error_degrades(monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "TMPL123")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    _patch_send(monkeypatch, handler)
    result = await send_subscribe_message(
        openid="o-x", template_key="next_day_retest", data={},
        access_token_provider=_token_ok,
    )
    assert result.status == "degraded_red_dot"
    assert result.reason == "upstream_error"


@pytest.mark.anyio
async def test_missing_openid_degrades(monkeypatch):
    monkeypatch.setenv(_ENV_KEY, "TMPL123")
    result = await send_subscribe_message(
        openid="  ", template_key="next_day_retest", data={},
        access_token_provider=_token_ok,
    )
    assert result.status == "degraded_red_dot"
    assert result.reason == "missing_openid"
