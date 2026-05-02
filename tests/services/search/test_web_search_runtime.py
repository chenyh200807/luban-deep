"""Tests for TutorBot-style web_search runtime behavior."""

from __future__ import annotations

import pytest

from deeptutor.services.setup.init import DEFAULT_MAIN_SETTINGS
from deeptutor.services.config.provider_runtime import ResolvedSearchConfig
from deeptutor.services.search import is_web_search_runtime_available, web_search
from deeptutor.services.search.exceptions import SearchError, SearchTimeoutError
from deeptutor.services.search.types import WebSearchResponse


class _FakeProvider:
    def __init__(self, name: str, supports_answer: bool = False):
        self.name = name
        self.supports_answer = supports_answer

    def search(self, query: str, **kwargs):
        return WebSearchResponse(
            query=query,
            answer="",
            provider=self.name,
            citations=[],
            search_results=[],
        )


def test_web_search_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {},
    )

    result = web_search("hello")

    assert result["provider"] == "disabled"
    assert result["citations"] == []
    assert result["search_results"] == []


def test_setup_defaults_keep_web_search_fail_closed() -> None:
    assert DEFAULT_MAIN_SETTINGS["tools"]["web_search"]["enabled"] is False


def test_web_search_runtime_unavailable_without_explicit_enabled_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": False},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(provider="brave", requested_provider="brave", api_key="secret"),
    )

    assert is_web_search_runtime_available() is False


def test_web_search_rejects_deprecated_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="exa",
            requested_provider="exa",
            unsupported_provider=True,
            deprecated_provider=True,
        ),
    )
    with pytest.raises(ValueError):
        web_search("hello")


def test_web_search_perplexity_missing_key_hard_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="perplexity",
            requested_provider="perplexity",
            api_key="",
            max_results=5,
            missing_credentials=True,
        ),
    )
    monkeypatch.setattr("deeptutor.services.search._resolve_provider_key", lambda _p, _k: "")
    with pytest.raises(ValueError, match="perplexity requires api_key"):
        web_search("hello")


def test_web_search_missing_key_hard_fails_without_duckduckgo_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="brave",
            requested_provider="brave",
            api_key="",
            base_url="",
            max_results=3,
            proxy="http://127.0.0.1:7890",
        ),
    )
    monkeypatch.setattr("deeptutor.services.search._resolve_provider_key", lambda _p, _k: "")

    with pytest.raises(ValueError, match="brave requires api_key"):
        web_search("hello")


def test_web_search_searxng_uses_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_get_provider(name: str, **kwargs):
        captured["provider"] = name
        captured["kwargs"] = kwargs
        return _FakeProvider(name)

    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="searxng",
            requested_provider="searxng",
            base_url="https://searx.example.com",
            max_results=4,
        ),
    )
    monkeypatch.setattr("deeptutor.services.search.get_provider", _fake_get_provider)
    result = web_search("hello")
    assert captured["provider"] == "searxng"
    assert captured["kwargs"]["base_url"] == "https://searx.example.com"
    assert captured["kwargs"]["max_results"] == 4
    assert result["provider"] == "searxng"


def test_web_search_preserves_typed_provider_errors(monkeypatch) -> None:
    class _FailingProvider(_FakeProvider):
        def search(self, query: str, **kwargs):
            raise SearchTimeoutError("timeout", provider=self.name)

    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="brave",
            requested_provider="brave",
            api_key="secret",
            max_results=3,
        ),
    )
    monkeypatch.setattr("deeptutor.services.search.get_provider", lambda _name, **_kwargs: _FailingProvider("brave"))

    with pytest.raises(SearchTimeoutError, match="timeout"):
        web_search("hello")


def test_web_search_wraps_unexpected_provider_errors(monkeypatch) -> None:
    class _ExplodingProvider(_FakeProvider):
        def search(self, query: str, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "deeptutor.services.search._get_web_search_config",
        lambda: {"enabled": True},
    )
    monkeypatch.setattr(
        "deeptutor.services.search.resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(
            provider="brave",
            requested_provider="brave",
            api_key="secret",
            max_results=3,
        ),
    )
    monkeypatch.setattr("deeptutor.services.search.get_provider", lambda _name, **_kwargs: _ExplodingProvider("brave"))

    with pytest.raises(SearchError, match="brave search failed: boom"):
        web_search("hello")
