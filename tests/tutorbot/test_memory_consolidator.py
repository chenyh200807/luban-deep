from __future__ import annotations

import gc
import sys
import types
import weakref
from types import SimpleNamespace

import pytest

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
    info=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
    debug=lambda *args, **kwargs: None,
    exception=lambda *args, **kwargs: None,
)
sys.modules.setdefault("loguru", fake_loguru)

from deeptutor.tutorbot.agent.memory import MemoryConsolidator


def test_memory_consolidator_session_lock_is_strongly_retained(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )

    lock = consolidator.get_lock("session-1")
    lock_ref = weakref.ref(lock)
    del lock
    gc.collect()

    assert lock_ref() is not None
    assert consolidator.get_lock("session-1") is lock_ref()


def test_memory_consolidator_release_lock_drops_idle_session_lock(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )

    lock = consolidator.get_lock("session-1")

    assert consolidator.release_lock("session-1") is True
    assert consolidator.get_lock("session-1") is not lock


@pytest.mark.asyncio
async def test_memory_consolidator_release_lock_keeps_locked_session_lock(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )
    lock = consolidator.get_lock("session-1")

    await lock.acquire()
    try:
        assert consolidator.release_lock("session-1") is False
        assert consolidator.get_lock("session-1") is lock
    finally:
        lock.release()


@pytest.mark.asyncio
async def test_agent_loop_new_releases_idle_memory_lock(tmp_path) -> None:
    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class FakeProvider(LLMProvider):
        async def chat(self, *args, **kwargs) -> LLMResponse:
            return LLMResponse(content="unused")

        def get_default_model(self) -> str:
            return "fake-model"

    loop = AgentLoop(MessageBus(), FakeProvider(), tmp_path)
    session_key = "test:new"
    lock = loop.memory_consolidator.get_lock(session_key)

    result = await loop.process_direct("/new", session_key=session_key)

    assert result == "New session started."
    assert loop.memory_consolidator.get_lock(session_key) is not lock
