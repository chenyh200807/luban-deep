"""Battle1 W4 model-tiering wiring tests.

Covers the single-authority utility (light-tier) model injection into AgentLoop
subagents + memory consolidation, the MemoryConsolidator double-duty split
(consolidation model vs token-estimation anchor), and the FailoverProvider
per-call override interaction (T4 现状固化).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.agent.memory import MemoryConsolidator
from deeptutor.tutorbot.bus.queue import MessageBus
from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse
from deeptutor.tutorbot.providers.failover import FailoverProvider


class _StubProvider(LLMProvider):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta=None,
    ) -> LLMResponse:
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "default-model"


def _make_loop(tmp_path, *, utility_model: str | None) -> AgentLoop:
    return AgentLoop(
        bus=MessageBus(),
        provider=_StubProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={}, key=key, messages=[], get_history=lambda max_messages=0: []
            ),
            save=lambda session: None,
        ),
        utility_model=utility_model,
    )


def test_agent_loop_injects_utility_model_into_subagents_and_consolidator(tmp_path) -> None:
    loop = _make_loop(tmp_path, utility_model="light-x")
    assert loop.utility_model == "light-x"
    assert loop.subagents.model == "light-x"
    assert loop.memory_consolidator.consolidation_model == "light-x"
    # Main-loop token-estimation anchor stays on the primary model.
    assert loop.memory_consolidator.model == loop.model == "default-model"


def test_agent_loop_without_utility_model_falls_back_bit_for_bit(tmp_path) -> None:
    loop = _make_loop(tmp_path, utility_model=None)
    assert loop.utility_model is None
    assert loop.subagents.model == loop.model == "default-model"
    assert loop.memory_consolidator.consolidation_model is None


def test_agent_loop_blank_utility_model_normalizes_to_none(tmp_path) -> None:
    loop = _make_loop(tmp_path, utility_model="   ")
    assert loop.utility_model is None
    assert loop.subagents.model == loop.model


def _make_consolidator(tmp_path, *, model: str, consolidation_model: str | None) -> MemoryConsolidator:
    return MemoryConsolidator(
        workspace=tmp_path,
        provider=_StubProvider(),
        model=model,
        sessions=SimpleNamespace(),
        context_window_tokens=65_536,
        build_messages=lambda **_kwargs: [{"role": "user", "content": "[probe]"}],
        get_tool_definitions=lambda: [],
        consolidation_model=consolidation_model,
    )


@pytest.mark.asyncio
async def test_consolidate_messages_uses_consolidation_model(tmp_path) -> None:
    consolidator = _make_consolidator(tmp_path, model="main-model", consolidation_model="light-x")
    captured: dict[str, Any] = {}

    async def _fake_consolidate(messages, provider, model):
        captured["model"] = model
        return True

    consolidator.store.consolidate = _fake_consolidate  # type: ignore[assignment]
    ok = await consolidator.consolidate_messages([{"role": "user", "content": "hi"}])
    assert ok is True
    assert captured["model"] == "light-x"


@pytest.mark.asyncio
async def test_consolidate_messages_falls_back_to_main_model(tmp_path) -> None:
    consolidator = _make_consolidator(tmp_path, model="main-model", consolidation_model=None)
    captured: dict[str, Any] = {}

    async def _fake_consolidate(messages, provider, model):
        captured["model"] = model
        return True

    consolidator.store.consolidate = _fake_consolidate  # type: ignore[assignment]
    await consolidator.consolidate_messages([{"role": "user", "content": "hi"}])
    assert captured["model"] == "main-model"


def test_token_estimation_anchor_never_drifts_to_light_model(tmp_path, monkeypatch) -> None:
    consolidator = _make_consolidator(tmp_path, model="main-model", consolidation_model="light-x")
    captured: dict[str, Any] = {}

    def _fake_chain(provider, model, messages, tools):
        captured["model"] = model
        return (123, "probe")

    monkeypatch.setattr(
        "deeptutor.tutorbot.agent.memory.estimate_prompt_tokens_chain", _fake_chain
    )
    session = SimpleNamespace(
        key="cli:direct", get_history=lambda max_messages=0: []
    )
    tokens, _ = consolidator.estimate_session_prompt_tokens(session)  # type: ignore[arg-type]
    assert tokens == 123
    # Hard invariant: the token anchor is the PRIMARY model, not the light tier.
    assert captured["model"] == "main-model"


class _ErrorPrimary(LLMProvider):
    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", finish_reason="error")

    def get_default_model(self) -> str:
        return "primary-model"


class _CapturingFallback(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.captured: dict[str, Any] = {}

    async def chat(self, *args: Any, model: str | None = None, **kwargs: Any) -> LLMResponse:
        self.captured["model"] = model
        return LLMResponse(content="fallback answer")

    def get_default_model(self) -> str:
        return "fallback-model"


@pytest.mark.asyncio
async def test_failover_does_not_forward_per_call_light_model_override() -> None:
    # T4现状固化: on failover the backup is always called with fallback_model;
    # the per-call light-tier override is NOT透传 (guards future silent change).
    fallback = _CapturingFallback()
    failover = FailoverProvider(
        primary=_ErrorPrimary(), fallback=fallback, fallback_model="fallback-model"
    )
    response = await failover.chat(messages=[{"role": "user", "content": "hi"}], model="light-x")
    assert response.content == "fallback answer"
    assert fallback.captured["model"] == "fallback-model"
