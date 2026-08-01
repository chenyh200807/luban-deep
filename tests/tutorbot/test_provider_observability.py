from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from deeptutor.tutorbot.providers.anthropic_provider import AnthropicProvider
from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from deeptutor.tutorbot.providers.failover import FailoverProvider
from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider


class _FakeObservability:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []

    def estimate_usage_details(self, **_kwargs):
        return {"input": 9.0, "output": 3.0, "total": 12.0}

    def estimate_cost_details(self, **_kwargs):
        return {"input": 0.0, "output": 0.0, "total": 0.0}

    def start_observation(self, **_kwargs):
        class _Manager:
            def __enter__(self_inner):
                return object()

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Manager()

    def update_observation(self, _observation, **kwargs):
        self.updated.append(kwargs)


def test_dashscope_minimal_reasoning_disables_thinking_without_invalid_reasoning_effort() -> None:
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1")
    provider.default_model = "deepseek-v4-flash"
    provider.extra_headers = {}
    provider._spec = SimpleNamespace(
        name="dashscope",
        supports_prompt_caching=False,
        strip_model_prefix=False,
        supports_max_completion_tokens=False,
        model_overrides=(),
    )
    provider._provider_name = "dashscope"

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="deepseek-v4-flash",
        max_tokens=256,
        temperature=0.7,
        reasoning_effort="minimal",
        tool_choice=None,
    )

    assert kwargs["extra_body"] == {"enable_thinking": False}
    assert "reasoning_effort" not in kwargs


def test_dashscope_default_chat_disables_thinking_for_visible_answers() -> None:
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1")
    provider.default_model = "deepseek-v4-flash"
    provider.extra_headers = {}
    provider._spec = SimpleNamespace(
        name="dashscope",
        supports_prompt_caching=False,
        strip_model_prefix=False,
        supports_max_completion_tokens=False,
        model_overrides=(),
    )
    provider._provider_name = "dashscope"

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="deepseek-v4-flash",
        max_tokens=256,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert kwargs["extra_body"] == {"enable_thinking": False}
    assert "reasoning_effort" not in kwargs


def test_deepseek_default_chat_disables_thinking_for_visible_answers() -> None:
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://api.deepseek.com/v1")
    provider.default_model = "deepseek-v4-flash"
    provider.extra_headers = {}
    provider._spec = SimpleNamespace(
        name="deepseek",
        supports_prompt_caching=False,
        strip_model_prefix=False,
        supports_max_completion_tokens=False,
        model_overrides=(),
    )
    provider._provider_name = "deepseek"

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="deepseek-v4-flash",
        max_tokens=256,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in kwargs


def test_deepseek_high_reasoning_explicitly_enables_thinking() -> None:
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://api.deepseek.com/v1")
    provider.default_model = "deepseek-v4-flash"
    provider.extra_headers = {}
    provider._spec = SimpleNamespace(
        name="deepseek",
        supports_prompt_caching=False,
        strip_model_prefix=False,
        supports_max_completion_tokens=False,
        model_overrides=(),
    )
    provider._provider_name = "deepseek"

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="deepseek-v4-flash",
        max_tokens=256,
        temperature=0.7,
        reasoning_effort="high",
        tool_choice=None,
    )

    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_failover_provider_uses_backup_model_when_primary_has_no_visible_content() -> None:
    class PrimaryProvider(LLMProvider):
        async def chat(self, **_kwargs):
            return LLMResponse(content=None, reasoning_content="internal only")

        def get_default_model(self) -> str:
            return "deepseek-v4-flash"

    class BackupProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.model = ""

        async def chat(self, **kwargs):
            self.model = str(kwargs.get("model") or "")
            return LLMResponse(content="备用答案")

        def get_default_model(self) -> str:
            return "qwen3.6-flash"

    backup = BackupProvider()
    provider = FailoverProvider(
        primary=PrimaryProvider(),
        fallback=backup,
        fallback_model="qwen3.6-flash",
    )

    response = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "备用答案"
    assert backup.model == "qwen3.6-flash"


@pytest.mark.asyncio
async def test_failover_provider_keeps_primary_tool_calls_without_backup() -> None:
    class PrimaryProvider(LLMProvider):
        async def chat(self, on_content_delta=None, **_kwargs):
            if on_content_delta is not None:
                await on_content_delta("partial")
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(id="call-1", name="rag", arguments={"query": "防水"})
                ],
            )

        def get_default_model(self) -> str:
            return "deepseek-v4-flash"

    class BackupProvider(LLMProvider):
        async def chat(self, **_kwargs):
            raise AssertionError("tool calls are valid primary output")

        def get_default_model(self) -> str:
            return "qwen3.6-flash"

    provider = FailoverProvider(
        primary=PrimaryProvider(),
        fallback=BackupProvider(),
        fallback_model="qwen3.6-flash",
    )

    response = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.has_tool_calls
    assert response.tool_calls[0].name == "rag"


@pytest.mark.asyncio
async def test_failover_provider_preserves_truncation_without_mixing_fallback_stream() -> None:
    class PrimaryProvider(LLMProvider):
        async def chat(self, on_content_delta=None, **_kwargs):
            if on_content_delta is not None:
                await on_content_delta("partial")
            return LLMResponse(
                content="partial",
                finish_reason="length",
                tool_calls=[
                    ToolCallRequest(id="partial", name="rag", arguments={"query": "partial"})
                ],
            )

        def get_default_model(self) -> str:
            return "primary"

    class BackupProvider(LLMProvider):
        async def chat(self, **_kwargs):
            raise AssertionError("truncated streamed responses must reach the terminal consumer")

        def get_default_model(self) -> str:
            return "backup"

    provider = FailoverProvider(
        primary=PrimaryProvider(),
        fallback=BackupProvider(),
        fallback_model="backup",
    )

    deltas: list[str] = []

    async def _collect(text: str) -> None:
        deltas.append(text)

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        on_content_delta=_collect,
    )

    assert response.content == "partial"
    assert not response.is_complete
    assert deltas == ["partial"]


@pytest.mark.asyncio
async def test_failover_provider_does_not_mix_error_after_primary_stream_with_backup() -> None:
    backup_calls = 0

    class PrimaryProvider(LLMProvider):
        async def chat(self, on_content_delta=None, **_kwargs):
            if on_content_delta is not None:
                await on_content_delta("primary partial")
            return LLMResponse(
                content=None,
                finish_reason="error",
                failure_kind="provider_timeout",
                error_detail="stream timed out",
            )

        def get_default_model(self) -> str:
            return "primary"

    class BackupProvider(LLMProvider):
        async def chat(self, **_kwargs):
            nonlocal backup_calls
            backup_calls += 1
            return LLMResponse(content="backup complete")

        def get_default_model(self) -> str:
            return "backup"

    provider = FailoverProvider(
        primary=PrimaryProvider(),
        fallback=BackupProvider(),
        fallback_model="backup",
    )
    deltas: list[str] = []

    async def _collect(text: str) -> None:
        deltas.append(text)

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        on_content_delta=_collect,
    )

    assert response.failure_kind == "provider_timeout"
    assert backup_calls == 0
    assert deltas == ["primary partial"]


@pytest.mark.asyncio
async def test_openai_compat_provider_records_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.openai_compat_provider.observability",
        fake_observability,
    )

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "gpt-test"
    provider.extra_headers = {}
    provider._spec = None
    provider._provider_name = "openai"
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_async_return(
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content="hello",
                                    tool_calls=[],
                                    reasoning_content=None,
                                ),
                                finish_reason="stop",
                            )
                        ],
                        usage=SimpleNamespace(prompt_tokens=14, completion_tokens=6, total_tokens=20),
                    )
                )
            )
        )
    )

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
    )

    assert response.content == "hello"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 14.0,
        "output": 6.0,
        "total": 20.0,
    }


@pytest.mark.asyncio
async def test_openai_compat_provider_records_stream_first_token_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.openai_compat_provider.observability",
        fake_observability,
    )

    class _FakeStream:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "gpt-test"
    provider.extra_headers = {}
    provider._spec = None
    provider._provider_name = "openai"
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_async_return(
                    _FakeStream(
                        [
                            SimpleNamespace(
                                choices=[
                                    SimpleNamespace(
                                        delta=SimpleNamespace(content="你", tool_calls=[]),
                                        finish_reason=None,
                                    )
                                ]
                            ),
                            SimpleNamespace(
                                choices=[
                                    SimpleNamespace(
                                        delta=SimpleNamespace(content="好", tool_calls=[]),
                                        finish_reason="stop",
                                    )
                                ]
                            ),
                        ]
                    )
                )
            )
        )
    )
    deltas: list[str] = []

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
        on_content_delta=lambda text: _capture_async(deltas, text),
    )

    assert response.content == "你好"
    assert deltas == ["你", "好"]
    assert response.telemetry["provider_name"] == "openai"
    assert response.telemetry["model"] == "gpt-test"
    assert response.telemetry["stream_chunk_count"] == 2
    assert response.telemetry["stream_content_chunk_count"] == 2
    assert set(response.telemetry["stage_timings_ms"]) >= {
        "provider_stream_create",
        "provider_first_chunk",
        "provider_first_content_delta",
        "provider_stream_read",
    }
    final_metadata = fake_observability.updated[-1]["metadata"]
    assert final_metadata["stream_chunk_count"] == 2
    assert final_metadata["stream_content_chunk_count"] == 2
    assert final_metadata["stage_timings_ms"]["provider_first_content_delta"] >= 0
    # Battle2 S3-T2: first-chunk wall-clock reaches Langfuse as completion_start_time.
    completion_start = fake_observability.updated[-1]["completion_start_time"]
    assert isinstance(completion_start, datetime)
    assert completion_start.tzinfo is not None


@pytest.mark.asyncio
async def test_openai_compat_provider_stream_error_before_first_chunk_has_no_completion_start_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honest missing value: a stream that fails before its first chunk must export
    completion_start_time=None instead of fabricating a timestamp."""
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.openai_compat_provider.observability",
        fake_observability,
    )

    async def _raise_create(**_kwargs):
        raise RuntimeError("boom before first chunk")

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "gpt-test"
    provider.extra_headers = {}
    provider._spec = None
    provider._provider_name = "openai"
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_raise_create))
    )

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
        on_content_delta=lambda text: _capture_async([], text),
    )

    assert response.finish_reason == "error"
    assert fake_observability.updated[-1]["completion_start_time"] is None


@pytest.mark.asyncio
async def test_anthropic_provider_stream_records_completion_start_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.anthropic_provider.observability",
        fake_observability,
    )

    class _FakeTextStream:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class _FakeMessageStream:
        def __init__(self):
            self.text_stream = _FakeTextStream(["你", "好"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="你好")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=8, output_tokens=2),
            )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "claude-test"
    provider.extra_headers = {}
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(stream=lambda **_kwargs: _FakeMessageStream())
    )
    deltas: list[str] = []

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-test",
        on_content_delta=lambda text: _capture_async(deltas, text),
    )

    assert response.content == "你好"
    assert deltas == ["你", "好"]
    completion_start = fake_observability.updated[-1]["completion_start_time"]
    assert isinstance(completion_start, datetime)
    assert completion_start.tzinfo is not None


@pytest.mark.asyncio
async def test_openai_compat_provider_does_not_promote_reasoning_to_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.openai_compat_provider.observability",
        fake_observability,
    )

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "gpt-test"
    provider.extra_headers = {}
    provider._spec = None
    provider._provider_name = "openai"
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_async_return(
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content=None,
                                    tool_calls=[],
                                    reasoning="internal-only reasoning",
                                    reasoning_content=None,
                                ),
                                finish_reason="stop",
                            )
                        ],
                        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                    )
                )
            )
        )
    )

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
    )

    assert response.content is None
    assert response.reasoning_content == "internal-only reasoning"


@pytest.mark.asyncio
async def test_anthropic_provider_records_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.anthropic_provider.observability",
        fake_observability,
    )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://example.com")
    provider.default_model = "claude-test"
    provider.extra_headers = {}
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(
            create=_async_return(
                SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="anthropic-ok")],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=18, output_tokens=4),
                )
            )
        )
    )

    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-test",
    )

    assert response.content == "anthropic-ok"
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 18.0,
        "output": 4.0,
        "total": 22.0,
    }


@pytest.mark.asyncio
async def test_openai_compat_provider_uses_shared_traffic_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.llm import traffic_control

    fake_observability = _FakeObservability()
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.openai_compat_provider.observability",
        fake_observability,
    )
    monkeypatch.setenv("DEEPTUTOR_LLM_MAX_CONCURRENCY", "1")
    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    active = 0
    max_active = 0

    async def _create(**_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1")
    provider.default_model = "deepseek-v4-flash"
    provider.extra_headers = {}
    provider._spec = SimpleNamespace(
        name="dashscope",
        supports_prompt_caching=False,
        strip_model_prefix=False,
        supports_max_completion_tokens=False,
        model_overrides=(),
    )
    provider._provider_name = "dashscope"
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_create)))

    await asyncio.gather(
        provider.chat(messages=[{"role": "user", "content": "a"}]),
        provider.chat(messages=[{"role": "user", "content": "b"}]),
    )

    assert max_active == 1


def test_tutorbot_provider_traffic_controller_uses_runtime_llm_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.llm import traffic_control
    from deeptutor.services.llm.config import LLMConfig

    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="deep-key",  # pragma: allowlist secret
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=3,
        requests_per_minute=77,
    )
    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    monkeypatch.delenv("DEEPTUTOR_LLM_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("DEEPTUTOR_LLM_REQUESTS_PER_MINUTE", raising=False)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: cfg)

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    LLMProvider.__init__(provider, api_key="sk-test", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1")

    controller = provider._provider_traffic_controller("dashscope")

    assert controller.max_concurrency == 3
    assert controller.rpm == 77


def _async_return(value):
    async def _inner(**_kwargs):
        return value

    return _inner


async def _capture_async(bucket: list[str], value: str) -> None:
    bucket.append(value)
