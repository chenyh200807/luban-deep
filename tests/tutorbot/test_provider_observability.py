from __future__ import annotations

import sys
from types import SimpleNamespace
from types import ModuleType

import pytest

if "loguru" not in sys.modules:
    module = ModuleType("loguru")
    module.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    sys.modules["loguru"] = module
if "json_repair" not in sys.modules:
    module = ModuleType("json_repair")
    module.loads = lambda value: value
    sys.modules["json_repair"] = module

from deeptutor.tutorbot.providers.anthropic_provider import AnthropicProvider
from deeptutor.tutorbot.providers.base import LLMProvider
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


def _async_return(value):
    async def _inner(**_kwargs):
        return value

    return _inner
