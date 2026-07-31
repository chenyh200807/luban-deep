from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from deeptutor.services.llm.executors import sdk_stream
from deeptutor.services.llm.factory import _prompt_content_hash, complete, stream
from deeptutor.services.llm.types import TutorResponse, TutorStreamChunk


class _FakeObservability:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []
        self.started: list[dict[str, object]] = []

    @contextmanager
    def start_observation(self, **kwargs):
        self.started.append(kwargs)
        yield object()

    def update_observation(self, _observation, **kwargs):
        self.updated.append(kwargs)

    def estimate_usage_details(self, **_kwargs):
        return {"input": 91.0, "output": 29.0, "total": 120.0}

    def estimate_cost_details(self, **_kwargs):
        return {"input": 0.0, "output": 0.0, "total": 0.0}


def test_prompt_content_hash_tracks_effective_messages_deterministically() -> None:
    messages = [{"role": "system", "content": "teach"}, {"role": "user", "content": "Q1"}]
    assert _prompt_content_hash(messages) == _prompt_content_hash(list(messages))
    assert _prompt_content_hash(messages) != _prompt_content_hash(
        [{"role": "system", "content": "teach"}, {"role": "user", "content": "Q2"}]
    )


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
        prompt_registry_identity={
            "source_path": "deeptutor/agents/question/prompts/en/idea_agent.yaml",
            "content_hash": "a" * 64,
        },
    )

    assert result == "provider-ok"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 12.0,
        "output": 8.0,
        "total": 20.0,
    }
    assert fake_observability.started[-1]["metadata"]["prompt_content_hash"] == _prompt_content_hash(
        [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "hello"}]
    )
    assert fake_observability.started[-1]["metadata"]["prompt_registry_identity"] == {
        "source_path": "deeptutor/agents/question/prompts/en/idea_agent.yaml",
        "content_hash": "a" * 64,
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
    # Battle2 S3-T2: first-chunk wall-clock reaches Langfuse as completion_start_time.
    completion_start = fake_observability.updated[-1]["completion_start_time"]
    assert isinstance(completion_start, datetime)
    assert completion_start.tzinfo is not None


@pytest.mark.asyncio
async def test_factory_stream_completion_start_time_comes_from_successful_attempt(monkeypatch) -> None:
    """A failed first attempt (retriable error before any yield) must not pollute the
    successful attempt's completion_start_time: the timestamp is reset on retry."""
    fake_observability = _FakeObservability()
    attempt_counter = {"calls": 0}
    second_attempt_started_at: list[datetime] = []

    async def _fake_sdk_stream(**_kwargs):
        attempt_counter["calls"] += 1
        if attempt_counter["calls"] == 1:
            raise asyncio.TimeoutError("first attempt dies before first chunk")
        second_attempt_started_at.append(datetime.now(timezone.utc))
        yield TutorStreamChunk(content="A", delta="A", provider="openai", model="gpt-4o-mini")
        yield TutorStreamChunk(
            content="A",
            delta="",
            provider="openai",
            model="gpt-4o-mini",
            is_complete=True,
            usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
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
        max_retries=1,
        retry_delay=0,
    ):
        chunks.append(chunk)

    assert "".join(chunks) == "A"
    assert attempt_counter["calls"] == 2
    completion_start = fake_observability.updated[-1]["completion_start_time"]
    assert isinstance(completion_start, datetime)
    assert completion_start.tzinfo is not None
    # The exported timestamp is from the second (successful) attempt, not the failed one.
    assert completion_start >= second_attempt_started_at[0]


@pytest.mark.asyncio
async def test_factory_stream_error_before_first_chunk_has_no_completion_start_time(monkeypatch) -> None:
    fake_observability = _FakeObservability()

    async def _fake_sdk_stream(**_kwargs):
        raise ValueError("non-retriable, dies before first chunk")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr("deeptutor.services.llm.factory.observability", fake_observability)
    monkeypatch.setattr("deeptutor.services.llm.factory.sdk_stream", _fake_sdk_stream)

    with pytest.raises(ValueError):
        async for _chunk in stream(
            "hello",
            model="gpt-4o-mini",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            binding="openai",
            max_retries=0,
        ):
            pass

    assert fake_observability.updated[-1]["completion_start_time"] is None


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

    monkeypatch.setattr(
        "deeptutor.services.llm.executors.get_pooled_openai_client",
        lambda *args, **kwargs: _FakeAsyncOpenAI(),
    )

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

    monkeypatch.setattr(
        "deeptutor.services.llm.executors.get_pooled_openai_client",
        lambda *args, **kwargs: _FakeAsyncOpenAI(),
    )

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


class _NameCapturingObservability:
    """Captures the start_observation name so we can assert the caller's
    observe-only generation name reaches Langfuse."""

    def __init__(self) -> None:
        self.start_kwargs: list[dict[str, object]] = []

    @contextmanager
    def start_observation(self, **kwargs):
        self.start_kwargs.append(kwargs)
        yield object()

    def update_observation(self, _observation, **_kwargs):
        pass

    def estimate_usage_details(self, **_kwargs):
        return {"input": 1.0, "output": 1.0, "total": 2.0}

    def estimate_cost_details(self, **_kwargs):
        return {"input": 0.0, "output": 0.0, "total": 0.0}


@pytest.mark.asyncio
async def test_factory_complete_defaults_observation_name(monkeypatch) -> None:
    fake_observability = _NameCapturingObservability()

    async def _fake_sdk_complete(**_kwargs):
        return TutorResponse(content="ok", usage={}, provider="openai", model="gpt-4o-mini")

    monkeypatch.setattr("deeptutor.services.llm.factory.observability", fake_observability)
    monkeypatch.setattr("deeptutor.services.llm.factory.sdk_complete", _fake_sdk_complete)

    await complete(
        "hello",
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        binding="openai",
        max_retries=0,
    )

    assert fake_observability.start_kwargs[-1]["name"] == "llm.complete"


@pytest.mark.asyncio
async def test_factory_complete_threads_observation_name(monkeypatch) -> None:
    """Observe-only: an explicit observation_name reaches the Langfuse generation
    without leaking into the provider request kwargs."""
    fake_observability = _NameCapturingObservability()
    captured_provider_kwargs: dict[str, object] = {}

    async def _fake_sdk_complete(**kwargs):
        captured_provider_kwargs.update(kwargs)
        return TutorResponse(content="ok", usage={}, provider="openai", model="gpt-4o-mini")

    monkeypatch.setattr("deeptutor.services.llm.factory.observability", fake_observability)
    monkeypatch.setattr("deeptutor.services.llm.factory.sdk_complete", _fake_sdk_complete)

    await complete(
        "hello",
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        binding="openai",
        max_retries=0,
        max_tokens=2048,
        observation_name="assessment.deep_explanation",
    )

    assert fake_observability.start_kwargs[-1]["name"] == "assessment.deep_explanation"
    # observation_name is observe-only: it must not be forwarded to the provider.
    assert "observation_name" not in captured_provider_kwargs
    # the caller's max_tokens still reaches the provider unchanged.
    assert captured_provider_kwargs.get("max_tokens") == 2048
