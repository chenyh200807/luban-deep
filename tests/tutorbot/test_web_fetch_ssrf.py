"""SSRF guard for the LLM-facing web_fetch tool.

web_fetch is exposed to the model, so a crafted URL must never let it reach
internal/loopback/link-local addresses or cloud metadata endpoints. On Aliyun
the metadata service lives at 100.100.100.200 — which Python's ipaddress marks
as neither ``is_private`` nor ``is_global`` — so the guard must reject any
non-global target, follow redirects defensively, and resolve hostnames first.
"""

from __future__ import annotations

import json
import socket

import pytest

from deeptutor.tutorbot.agent.tools.web import WebFetchTool, _assert_url_safe

# Addresses an LLM must never be able to reach through web_fetch.
BLOCKED_TARGETS = [
    "http://127.0.0.1:8080/admin",          # loopback
    "http://[::1]/",                          # IPv6 loopback
    "http://169.254.169.254/latest/meta-data/",  # AWS/GCP/generic metadata
    "http://100.100.100.200/latest/meta-data/",  # Aliyun metadata (not is_private!)
    "http://10.1.2.3/internal",               # RFC1918
    "http://192.168.0.1/",                    # RFC1918
    "http://172.16.5.5/",                     # RFC1918
    "http://0.0.0.0/",                        # unspecified
]


@pytest.mark.parametrize("url", BLOCKED_TARGETS)
def test_assert_url_safe_blocks_internal_and_metadata_targets(url: str) -> None:
    ok, err = _assert_url_safe(url)
    assert ok is False
    assert err  # human-readable reason, not empty


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "gopher://127.0.0.1/", "ftp://host/x", "http:///nohost"],
)
def test_assert_url_safe_blocks_non_http_or_hostless(url: str) -> None:
    ok, _err = _assert_url_safe(url)
    assert ok is False


def test_assert_url_safe_allows_public_ip_literal() -> None:
    ok, err = _assert_url_safe("https://8.8.8.8/")
    assert ok is True
    assert err == ""


def test_assert_url_safe_blocks_domain_resolving_to_private_ip(monkeypatch) -> None:
    def fake_getaddrinfo(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 0))]

    monkeypatch.setattr(
        "deeptutor.tutorbot.agent.tools.web.socket.getaddrinfo", fake_getaddrinfo
    )
    ok, err = _assert_url_safe("https://rebind.example.com/")
    assert ok is False
    assert "10.0.0.7" in err


def test_assert_url_safe_allows_domain_resolving_to_public_ip(monkeypatch) -> None:
    def fake_getaddrinfo(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(
        "deeptutor.tutorbot.agent.tools.web.socket.getaddrinfo", fake_getaddrinfo
    )
    ok, err = _assert_url_safe("https://example.com/page")
    assert ok is True
    assert err == ""


class _NoNetworkClient:
    """httpx.AsyncClient stand-in that fails if any request is attempted."""

    def __init__(self, *_a, **_k) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, *_a, **_k):
        raise AssertionError("blocked URL must not reach the network")


@pytest.mark.asyncio
async def test_web_fetch_execute_blocks_metadata_without_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.tutorbot.agent.tools.web.httpx.AsyncClient", _NoNetworkClient
    )
    tool = WebFetchTool()
    raw = await tool.execute("http://100.100.100.200/latest/meta-data/")
    payload = json.loads(raw)
    assert "error" in payload


class _FakeURL:
    def __init__(self, url: str) -> None:
        self._u = url

    def __str__(self) -> str:
        return self._u


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = _FakeURL(url)


class _FakeResponse:
    def __init__(self, *, is_redirect: bool, next_url: str | None = None) -> None:
        self.is_redirect = is_redirect
        self.next_request = _FakeRequest(next_url) if next_url else None
        self.url = _FakeURL(next_url or "")
        self.status_code = 302 if is_redirect else 200
        self.headers = {"content-type": "text/html"}
        self.text = ""

    def raise_for_status(self) -> None:
        pass


class _RedirectToInternalClient:
    """First hop (public) 302-redirects to an internal metadata address."""

    calls: list[str] = []

    def __init__(self, *_a, **_k) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, url, *_a, **_k):
        type(self).calls.append(str(url))
        return _FakeResponse(
            is_redirect=True, next_url="http://169.254.169.254/latest/meta-data/"
        )


@pytest.mark.asyncio
async def test_web_fetch_blocks_redirect_to_internal(monkeypatch) -> None:
    async def _no_jina(self, *_a, **_k):
        return None

    monkeypatch.setattr(WebFetchTool, "_fetch_jina", _no_jina)
    monkeypatch.setattr(
        "deeptutor.tutorbot.agent.tools.web.httpx.AsyncClient",
        _RedirectToInternalClient,
    )
    _RedirectToInternalClient.calls = []

    tool = WebFetchTool()
    raw = await tool.execute("http://8.8.8.8/start")
    payload = json.loads(raw)

    assert "error" in payload
    # The internal redirect target must never be requested.
    assert all("169.254" not in c for c in _RedirectToInternalClient.calls)
