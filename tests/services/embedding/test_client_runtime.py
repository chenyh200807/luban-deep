"""Tests for embedding client provider-backed execution path."""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.embedding.client import EmbeddingClient, _resolve_adapter_class
from deeptutor.services.embedding.config import EmbeddingConfig


class _FakeAdapter:
    instances: list["_FakeAdapter"] = []

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.calls = []
        _FakeAdapter.instances.append(self)

    async def embed(self, request):
        self.calls.append(request)
        return type(
            "Resp",
            (),
            {
                "embeddings": [[float(i)] * (request.dimensions or 2) for i, _ in enumerate(request.texts)],
                "usage": {},
            },
        )()


class _FakeObservability:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def start_observation(self, **kwargs):
        self.started.append(kwargs)

        class _Ctx:
            def __enter__(self_inner):
                return object()

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    def update_observation(self, observation, **kwargs):
        self.updated.append(kwargs)

    def estimate_usage_details(self, **_kwargs):
        return {"input": 11.0, "output": 0.0, "total": 11.0}

    def estimate_cost_details(self, *, model, usage_details):
        return {"input": 0.1, "output": 0.0, "total": 0.1}


def _build_config(binding: str) -> EmbeddingConfig:
    return EmbeddingConfig(
        model="text-embedding-3-small",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        effective_url="https://api.openai.com/v1",
        binding=binding,
        provider_name=binding,
        provider_mode="standard",
        dim=8,
        batch_size=2,
        request_timeout=30,
    )


@pytest.mark.asyncio
async def test_embedding_client_batches_requests(monkeypatch) -> None:
    _FakeAdapter.instances = []
    monkeypatch.setattr("deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _FakeAdapter)
    client = EmbeddingClient(_build_config("openai"))
    vectors = await client.embed(["a", "b", "c"])
    assert len(vectors) == 3
    adapter = _FakeAdapter.instances[0]
    assert len(adapter.calls) == 2
    assert len(adapter.calls[0].texts) == 2
    assert len(adapter.calls[1].texts) == 1
    assert adapter.config["dimensions"] == 8


def test_resolve_adapter_class_supports_canonical_providers() -> None:
    assert _resolve_adapter_class("openai").__name__ == "OpenAICompatibleEmbeddingAdapter"
    assert _resolve_adapter_class("custom").__name__ == "OpenAICompatibleEmbeddingAdapter"
    assert _resolve_adapter_class("azure_openai").__name__ == "OpenAICompatibleEmbeddingAdapter"
    assert _resolve_adapter_class("cohere").__name__ == "CohereEmbeddingAdapter"
    assert _resolve_adapter_class("jina").__name__ == "JinaEmbeddingAdapter"
    assert _resolve_adapter_class("ollama").__name__ == "OllamaEmbeddingAdapter"
    assert _resolve_adapter_class("vllm").__name__ == "OpenAICompatibleEmbeddingAdapter"


def test_resolve_adapter_class_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown embedding binding"):
        _resolve_adapter_class("huggingface")


@pytest.mark.asyncio
async def test_embedding_client_prefers_provider_usage_for_observability(monkeypatch) -> None:
    class ProviderUsageAdapter(_FakeAdapter):
        async def embed(self, request):
            self.calls.append(request)
            return type(
                "Resp",
                (),
                {
                    "embeddings": [[1.0] * (request.dimensions or 2) for _ in request.texts],
                    "usage": {"prompt_tokens": 7, "total_tokens": 7},
                },
            )()

    fake_observability = _FakeObservability()
    monkeypatch.setattr("deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: ProviderUsageAdapter)
    monkeypatch.setattr("deeptutor.services.embedding.client.observability", fake_observability)

    client = EmbeddingClient(_build_config("openai"))
    await client.embed(["a", "b", "c"])

    assert fake_observability.started[0].get("usage_details") is None
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 7.0 + 7.0,
        "output": 0.0,
        "total": 7.0 + 7.0,
    }


@pytest.mark.asyncio
async def test_embedding_client_falls_back_to_estimated_usage_when_provider_missing(monkeypatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr("deeptutor.services.embedding.client._resolve_adapter_class", lambda _b: _FakeAdapter)
    monkeypatch.setattr("deeptutor.services.embedding.client.observability", fake_observability)

    client = EmbeddingClient(_build_config("openai"))
    await client.embed(["a"])

    assert fake_observability.updated[-1]["usage_source"] == "tiktoken"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 11.0,
        "output": 0.0,
        "total": 11.0,
    }
