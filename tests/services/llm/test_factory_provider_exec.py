"""Tests for provider-backed execution in llm.factory."""

from __future__ import annotations

import asyncio

import pytest

from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.llm import traffic_control
from deeptutor.services.llm.factory import complete, stream
from deeptutor.services.llm.providers.base_provider import BaseLLMProvider


@pytest.mark.asyncio
async def test_factory_complete_uses_litellm(monkeypatch) -> None:
    cfg = LLMConfig(
        model="google/gemini-2.5-pro",
        api_key="sk-or-test",
        base_url="https://openrouter.ai/api/v1",
        binding="openrouter",
        provider_name="openrouter",
        provider_mode="gateway",
    )
    captured: dict[str, object] = {}

    async def _fake_litellm_complete(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_complete", _fake_litellm_complete)

    result = await complete("hello")
    assert result == "ok"
    assert captured["provider_name"] == "openrouter"
    assert captured["model"] == "google/gemini-2.5-pro"


@pytest.mark.asyncio
async def test_factory_complete_applies_provider_traffic_control(monkeypatch) -> None:
    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="deep-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=1,
        requests_per_minute=600,
    )
    active = 0
    max_active = 0

    async def _fake_litellm_complete(**kwargs):
        nonlocal active, max_active
        _ = kwargs
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "ok"

    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_complete", _fake_litellm_complete)

    await asyncio.gather(complete("one", max_retries=0), complete("two", max_retries=0))

    assert max_active == 1


@pytest.mark.asyncio
async def test_factory_complete_explicit_provider_uses_runtime_traffic_limits(monkeypatch) -> None:
    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="runtime-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=1,
        requests_per_minute=600,
    )
    active = 0
    max_active = 0

    async def _fake_litellm_complete(**kwargs):
        nonlocal active, max_active
        _ = kwargs
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "ok"

    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    monkeypatch.delenv("DEEPTUTOR_LLM_MAX_CONCURRENCY", raising=False)
    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_complete", _fake_litellm_complete)

    await asyncio.gather(
        complete(
            "one",
            api_key="deep-key",
            base_url="https://api.deepseek.com",
            binding="deepseek",
            max_retries=0,
        ),
        complete(
            "two",
            api_key="deep-key",
            base_url="https://api.deepseek.com",
            binding="deepseek",
            max_retries=0,
        ),
    )

    assert max_active == 1


def test_factory_traffic_controller_is_scoped_per_event_loop() -> None:
    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="deep-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=1,
        requests_per_minute=600,
    )
    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()

    async def _controller():
        return traffic_control.get_provider_traffic_controller(provider_name="dashscope", config=cfg)

    first = asyncio.run(_controller())
    second = asyncio.run(_controller())

    assert first is not second


def test_base_provider_uses_shared_provider_traffic_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="deep-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=2,
        requests_per_minute=321,
    )
    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    monkeypatch.delenv("DEEPTUTOR_LLM_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("DEEPTUTOR_LLM_REQUESTS_PER_MINUTE", raising=False)

    provider = BaseLLMProvider(cfg)
    controller = traffic_control.get_provider_traffic_controller(provider_name="dashscope", config=cfg)

    assert provider.traffic_controller is controller
    assert controller.max_concurrency == 2
    assert controller.rpm == 321


@pytest.mark.asyncio
async def test_traffic_controller_releases_semaphore_when_cancelled_waiting_for_token() -> None:
    controller = traffic_control.TrafficController(
        provider_name="dashscope",
        max_concurrency=1,
        requests_per_minute=1,
        acquisition_timeout=0.1,
    )
    controller._tokens = 0.0

    task = asyncio.create_task(controller.__aenter__())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    controller._tokens = 1.0
    await asyncio.wait_for(controller.__aenter__(), timeout=0.1)
    await controller.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_factory_complete_passes_explicit_extra_headers_once(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_litellm_complete(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_complete", _fake_litellm_complete)

    result = await complete(
        "hello",
        model="deepseek-chat",
        api_key="deep-key",
        base_url="https://api.deepseek.com/v1",
        binding="deepseek",
        extra_headers={"APP-Code": "abc"},
        max_retries=0,
    )

    assert result == "ok"
    assert captured["extra_headers"] == {"APP-Code": "abc"}


@pytest.mark.asyncio
async def test_factory_complete_uses_direct_azure(monkeypatch) -> None:
    cfg = LLMConfig(
        model="gpt-4o-mini",
        api_key="azure-key",
        base_url="https://example.openai.azure.com/openai/deployments/demo",
        binding="azure_openai",
        provider_name="azure_openai",
        provider_mode="direct",
        api_version="2024-10-21",
    )
    captured: dict[str, object] = {}

    async def _fake_cloud_complete(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: False)
    monkeypatch.setattr("deeptutor.services.llm.cloud_provider.complete", _fake_cloud_complete)

    result = await complete("hello")
    assert result == "ok"
    assert captured["binding"] == "azure_openai"


@pytest.mark.asyncio
async def test_factory_complete_openai_codex_requires_oauth(monkeypatch) -> None:
    cfg = LLMConfig(
        model="openai_codex/codex-mini-latest",
        api_key="",
        base_url="https://chatgpt.com/backend-api",
        binding="openai_codex",
        provider_name="openai_codex",
        provider_mode="oauth",
    )
    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: False)

    with pytest.raises(Exception):
        await complete("hello", max_retries=0)


@pytest.mark.asyncio
async def test_factory_stream_uses_litellm(monkeypatch) -> None:
    cfg = LLMConfig(
        model="deepseek-chat",
        api_key="deep-key",
        base_url="https://api.deepseek.com/v1",
        binding="deepseek",
        provider_name="deepseek",
        provider_mode="standard",
    )

    async def _fake_litellm_stream(**kwargs):
        _ = kwargs
        yield "a"
        yield "b"

    monkeypatch.setattr("deeptutor.services.llm.factory.get_llm_config", lambda: cfg)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_stream", _fake_litellm_stream)

    chunks = []
    async for item in stream("hello"):
        chunks.append(item)
    assert "".join(chunks) == "ab"


@pytest.mark.asyncio
async def test_factory_stream_passes_explicit_extra_headers_once(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_litellm_stream(**kwargs):
        captured.update(kwargs)
        yield "ok"

    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_available", lambda: True)
    monkeypatch.setattr("deeptutor.services.llm.factory.litellm_stream", _fake_litellm_stream)

    chunks = []
    async for item in stream(
        "hello",
        model="deepseek-chat",
        api_key="deep-key",
        base_url="https://api.deepseek.com/v1",
        binding="deepseek",
        extra_headers={"APP-Code": "abc"},
        max_retries=0,
    ):
        chunks.append(item)

    assert "".join(chunks) == "ok"
    assert captured["extra_headers"] == {"APP-Code": "abc"}
