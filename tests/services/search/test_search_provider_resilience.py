from __future__ import annotations

import requests

from deeptutor.services.search.base import BaseSearchProvider
from deeptutor.services.search.exceptions import SearchRateLimitError
from deeptutor.services.search.types import WebSearchResponse
from deeptutor.utils.network.circuit_breaker import reset_circuit_breakers


class _DummyProvider(BaseSearchProvider):
    name = "dummy"
    requires_api_key = False
    API_KEY_ENV_VARS = ()

    def search(self, query: str, **kwargs) -> WebSearchResponse:
        raise NotImplementedError


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(self.text or "error", response=self)

    def json(self) -> dict:
        return dict(self._payload)


def test_request_json_retries_timeout_then_succeeds(monkeypatch) -> None:
    provider = _DummyProvider()
    reset_circuit_breakers()
    attempts = {"count": 0}

    def _fake_request(method: str, url: str, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise requests.Timeout("slow")
        return _Response(payload={"ok": True})

    monkeypatch.setattr("deeptutor.services.search.base.requests.request", _fake_request)

    payload = provider.request_json("GET", "https://example.com")

    assert payload == {"ok": True}
    assert attempts["count"] == 3


def test_request_json_maps_rate_limit_with_retry_after(monkeypatch) -> None:
    provider = _DummyProvider()
    reset_circuit_breakers()

    def _fake_request(method: str, url: str, **kwargs):
        return _Response(status_code=429, text="too many", headers={"Retry-After": "7"})

    monkeypatch.setattr("deeptutor.services.search.base.requests.request", _fake_request)

    try:
        provider.request_json("GET", "https://example.com", max_retries=0)
    except SearchRateLimitError as exc:
        assert exc.retry_after == 7.0
        assert exc.status_code == 429
    else:
        raise AssertionError("expected SearchRateLimitError")
