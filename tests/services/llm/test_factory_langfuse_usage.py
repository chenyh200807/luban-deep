from __future__ import annotations

from contextlib import contextmanager

import pytest

from deeptutor.services.llm.executors import sdk_stream
from deeptutor.services.llm.factory import complete, stream
from deeptutor.services.llm.types import TutorResponse, TutorStreamChunk


class _FakeObservability:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []

    @contextmanager
    def start_observation(self, **_kwargs):
        yield object()

    def update_observation(self, _observation, **kwargs):
        self.updated.append(kwargs)

    def estimate_usage_details(self, **_kwargs):
        return {"input": 91.0, "output": 29.0, "total": 120.0}

    def estimate_cost_details(self, **_kwargs):
        return {"input": 0.0, "output": 0.0, "total": 0.0}


@pytest.mark.asyncio
async def test_factory_complete_prefers_provider_usage_for_langfuse(monkeypatch) -> None:
    fake_observability = _FakeObservability()

    async def _fake_sdk_complete(**_kwargs):
        return TutorResponse(
            content="provider-ok",
            usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            provider="openai",
            model="gpt-4o-mini",
        )

    monkeypatch.setattr("deeptutor.services.llm.factory.observability", fake_observability)
    monkeypatch.setattr("deeptutor.services.llm.factory.sdk_complete", _fake_sdk_complete)

    result = await complete(
        "hello",
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        binding="openai",
        max_retries=0,
    )

    assert result == "provider-ok"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 12.0,
        "output": 8.0,
        "total": 20.0,
    }


@pytest.mark.asyncio
async def test_factory_stream_prefers_provider_usage_for_langfuse(monkeypatch) -> None:
    fake_observability = _FakeObservability()

    async def _fake_sdk_stream(**_kwargs):
        yield TutorStreamChunk(content="A", delta="A", provider="openai", model="gpt-4o-mini")
        yield TutorStreamChunk(content="AB", delta="B", provider="openai", model="gpt-4o-mini")
        yield TutorStreamChunk(
            content="AB",
            delta="",
            provider="openai",
            model="gpt-4o-mini",
            is_complete=True,
            usage={"prompt_tokens": 30, "completion_tokens": 6, "total_tokens": 36},
        )

    monkeypatch.setattr("deeptutor.services.llm.factory.observability", fake_observability)
    monkeypatch.setattr("deeptutor.services.llm.factory.sdk_stream", _fake_sdk_stream)

    chunks: list[str] = []
    async for chunk in stream(
        "hello",
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        binding="openai",
        max_retries=0,
    ):
        chunks.append(chunk)

    assert "".join(chunks) == "AB"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 30.0,
        "output": 6.0,
        "total": 36.0,
    }


@pytest.mark.asyncio
async def test_sdk_stream_requests_usage_chunk_for_dashscope(monkeypatch) -> None:
    captured_payloads: list[dict[str, object]] = []

    class _FakeStream:
        def __aiter__(self):
            async def _iterate():
                if False:
                    yield None
            return _iterate()

    class _FakeCompletions:
        async def create(self, **payload):
            captured_payloads.append(payload)
            return _FakeStream()

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeAsyncOpenAI:
        def __init__(self, **_kwargs) -> None:
            self.chat = _FakeChat()

    monkeypatch.setattr("deeptutor.services.llm.executors.AsyncOpenAI", _FakeAsyncOpenAI)

    async for _ in sdk_stream(
        prompt="hello",
        system_prompt="You are helpful.",
        provider_name="dashscope",
        model="deepseek-v3.2",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        return_stream_chunks=True,
    ):
        pass

    assert captured_payloads[-1]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_sdk_stream_preserves_explicit_stream_options(monkeypatch) -> None:
    captured_payloads: list[dict[str, object]] = []

    class _FakeStream:
        def __aiter__(self):
            async def _iterate():
                if False:
                    yield None
            return _iterate()

    class _FakeCompletions:
        async def create(self, **payload):
            captured_payloads.append(payload)
            return _FakeStream()

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeAsyncOpenAI:
        def __init__(self, **_kwargs) -> None:
            self.chat = _FakeChat()

    monkeypatch.setattr("deeptutor.services.llm.executors.AsyncOpenAI", _FakeAsyncOpenAI)

    async for _ in sdk_stream(
        prompt="hello",
        system_prompt="You are helpful.",
        provider_name="dashscope",
        model="deepseek-v3.2",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        return_stream_chunks=True,
        stream_options={"include_usage": False, "custom_flag": True},
    ):
        pass

    assert captured_payloads[-1]["stream_options"] == {
        "include_usage": False,
        "custom_flag": True,
    }
