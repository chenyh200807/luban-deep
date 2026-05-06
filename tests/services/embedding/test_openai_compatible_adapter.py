"""Tests for OpenAI-compatible embedding response parsing."""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.embedding.adapters.openai_compatible import (
    OpenAICompatibleEmbeddingAdapter,
)
from deeptutor.services.embedding.adapters.base import EmbeddingRequest


def _extract(data):
    return OpenAICompatibleEmbeddingAdapter._extract_embeddings_from_response(data)


def test_none_embedding_value_is_normalized_to_empty_list() -> None:
    data = {
        "data": [
            {"embedding": [0.1, 0.2]},
            {"embedding": None},
            {"embedding": [0.3, 0.4]},
        ]
    }

    assert _extract(data) == [[0.1, 0.2], [], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_local_placeholder_key_is_not_sent_as_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        headers: dict[str, str] = {}
        text = '{"data":[{"embedding":[0.1,0.2]}]}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"data": [{"embedding": [0.1, 0.2]}], "model": "local-embed"}

    class _Client:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr("httpx.AsyncClient", _Client)

    adapter = OpenAICompatibleEmbeddingAdapter(
        {
            "api_key": "sk-no-key-required",
            "base_url": "http://127.0.0.1:8000/v1",
            "model": "local-embed",
            "dimensions": None,
            "request_timeout": 1,
        }
    )

    response = await adapter.embed(EmbeddingRequest(texts=["hello"], model="local-embed"))

    assert response.embeddings == [[0.1, 0.2]]
    assert captured["url"] == "http://127.0.0.1:8000/v1/embeddings"
    assert captured["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_local_placeholder_key_is_not_sent_as_azure_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        headers: dict[str, str] = {}
        text = '{"data":[{"embedding":[0.1]}]}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"data": [{"embedding": [0.1]}]}

    class _Client:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):
            captured["url"] = url
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr("httpx.AsyncClient", _Client)

    adapter = OpenAICompatibleEmbeddingAdapter(
        {
            "api_key": "sk-no-key-required",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_version": "2024-02-01",
            "model": "local-embed",
            "dimensions": None,
            "request_timeout": 1,
        }
    )

    await adapter.embed(EmbeddingRequest(texts=["hello"], model="local-embed"))

    assert captured["url"] == "http://127.0.0.1:8000/v1/embeddings?api-version=2024-02-01"
    assert captured["headers"] == {"Content-Type": "application/json"}
