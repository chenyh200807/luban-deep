from __future__ import annotations

from contextlib import contextmanager
import sys
from types import SimpleNamespace
from types import ModuleType

import pytest

from deeptutor.services.llm.config import LLMConfig

if "deeptutor.services.llm.http_client" not in sys.modules:
    module = ModuleType("deeptutor.services.llm.http_client")

    async def _get_shared_http_client():
        return object()

    module.get_shared_http_client = _get_shared_http_client
    sys.modules["deeptutor.services.llm.http_client"] = module

from deeptutor.services.llm.providers.anthropic import AnthropicProvider
from deeptutor.services.llm.providers.open_ai import OpenAIProvider


class _FakeObservability:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []

    @contextmanager
    def start_observation(self, **_kwargs):
        yield object()

    def update_observation(self, _observation, **kwargs):
        self.updated.append(kwargs)

    def estimate_usage_details(self, **_kwargs):
        return {"input": 9.0, "output": 3.0, "total": 12.0}

    def estimate_cost_details(self, **_kwargs):
        return {"input": 0.0, "output": 0.0, "total": 0.0}


def _config(provider_name: str, model: str) -> LLMConfig:
    return LLMConfig(
        model=model,
        api_key="sk-test",
        base_url="https://example.com/v1",
        binding=provider_name,
        provider_name=provider_name,
        provider_mode="standard",
    )


def _async_return(value):
    async def _inner(**_kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_openai_provider_complete_records_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.services.llm.providers.open_ai.observability",
        fake_observability,
    )

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.config = _config("openai", "gpt-test")
    provider.provider_name = "openai"
    provider.api_key = "sk-test"
    provider.base_url = "https://example.com/v1"
    provider.execute_with_retry = _async_return(  # type: ignore[method-assign]
        SimpleNamespace(
            content="provider-ok",
            usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        )
    )
    provider.client = SimpleNamespace()

    async def _execute_with_retry(func):
        return await func()

    provider.execute_with_retry = _execute_with_retry  # type: ignore[method-assign]
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_async_return(
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content="provider-ok"),
                                finish_reason="stop",
                            )
                        ],
                        usage=SimpleNamespace(
                            model_dump=lambda: {
                                "prompt_tokens": 12,
                                "completion_tokens": 8,
                                "total_tokens": 20,
                            }
                        ),
                        model_dump=lambda: {},
                    )
                )
            )
        )
    )

    response = await provider.complete("hello", model="gpt-test")

    assert response.content == "provider-ok"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 12.0,
        "output": 8.0,
        "total": 20.0,
    }


@pytest.mark.asyncio
async def test_openai_provider_stream_records_estimated_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.services.llm.providers.open_ai.observability",
        fake_observability,
    )

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.config = _config("openai", "gpt-test")
    provider.provider_name = "openai"
    provider.api_key = "sk-test"
    provider.base_url = "https://example.com/v1"

    async def _execute_with_retry(func):
        return await func()

    async def _fake_stream():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="A"))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="B"))])

    provider.execute_with_retry = _execute_with_retry  # type: ignore[method-assign]
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_async_return(_fake_stream())
            )
        )
    )

    chunks: list[str] = []
    async for chunk in provider.stream("hello", model="gpt-test"):
        chunks.append(chunk.delta)

    assert chunks == ["A", "B", ""]
    assert fake_observability.updated[-1]["usage_source"] == "tiktoken"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 9.0,
        "output": 3.0,
        "total": 12.0,
    }


@pytest.mark.asyncio
async def test_anthropic_provider_complete_records_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.services.llm.providers.anthropic.observability",
        fake_observability,
    )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.config = _config("anthropic", "claude-test")
    provider.provider_name = "anthropic"
    provider.api_key = "sk-test"
    provider.base_url = "https://example.com"

    async def _execute_with_retry(func):
        return await func()

    provider.execute_with_retry = _execute_with_retry  # type: ignore[method-assign]
    provider._get_client = _async_return(  # type: ignore[method-assign]
        SimpleNamespace(
            messages=SimpleNamespace(
                create=_async_return(
                    SimpleNamespace(
                        content=[SimpleNamespace(text="anthropic-ok")],
                        stop_reason="end_turn",
                        usage=SimpleNamespace(input_tokens=18, output_tokens=4),
                        model_dump=lambda: {},
                    )
                )
            )
        )
    )

    response = await provider.complete("hello", model="claude-test")

    assert response.content == "anthropic-ok"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 18.0,
        "output": 4.0,
        "total": 22.0,
    }


@pytest.mark.asyncio
async def test_anthropic_provider_stream_records_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.services.llm.providers.anthropic.observability",
        fake_observability,
    )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.config = _config("anthropic", "claude-test")
    provider.provider_name = "anthropic"
    provider.api_key = "sk-test"
    provider.base_url = "https://example.com"

    async def _execute_with_retry(func):
        return await func()

    async def _fake_stream():
        yield SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(text="A"),
            usage=None,
        )
        yield SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(text=None),
            usage=SimpleNamespace(input_tokens=13, output_tokens=5),
        )

    provider.execute_with_retry = _execute_with_retry  # type: ignore[method-assign]
    provider._get_client = _async_return(  # type: ignore[method-assign]
        SimpleNamespace(messages=SimpleNamespace(create=_async_return(_fake_stream())))
    )

    chunks: list[str] = []
    stream = provider.stream.__wrapped__(provider, "hello", model="claude-test")
    async for chunk in stream:
        chunks.append(chunk.delta)

    assert chunks == ["A", ""]
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 13.0,
        "output": 5.0,
        "total": 18.0,
    }
