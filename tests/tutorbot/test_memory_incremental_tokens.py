"""Battle1 W1-T1 — incremental token-estimation cache for MemoryConsolidator.

Covers the two shipped sub-steps (① per-message incremental cache, ② cold-start
``asyncio.to_thread`` seeding).  The provider-usage writeback (design step ③) was
CUT by the commander — it would have injected a cross-time-point second input
into consolidation's single decider — so there is intentionally NO assertion for
``observed``/``provider_usage`` here.

Assertion groups:
  1. incremental vs full: within 10% AND incremental is an upper bound (>= full);
  2. steady state: appending 3 messages re-encodes exactly 3 messages;
  3. clear() resets the per-message cache (no stale reads);
  4. cold start (> threshold messages) seeds the table via asyncio.to_thread;
  5. boundary selection reads the per-message cache instead of re-encoding.
"""

from __future__ import annotations

import asyncio

import pytest

import deeptutor.tutorbot.agent.memory as memory
from deeptutor.tutorbot.agent.memory import MemoryConsolidator
from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from deeptutor.tutorbot.session.manager import Session

_SYSTEM_PROMPT = (
    "你是鲁班智考的助教。请依据教材原文与采分点作答，"
    "保持严谨、可溯源。You are a construction-exam tutor assistant."
)
_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the knowledge base for grounded evidence.",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def _build_messages(history, current_message, channel=None, chat_id=None):
    """Minimal stand-in for the loop's message builder used by the estimator."""
    msgs = [{"role": "system", "content": _SYSTEM_PROMPT}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": current_message})
    return msgs


def _make_consolidator(tmp_path, *, context_window_tokens=100_000) -> MemoryConsolidator:
    return MemoryConsolidator(
        tmp_path,
        provider=object(),  # no estimate_prompt_tokens -> tiktoken fallback
        model="demo",
        sessions=object(),
        context_window_tokens=context_window_tokens,
        build_messages=_build_messages,
        get_tool_definitions=lambda: _TOOL_DEFS,
    )


def _make_session(n: int, *, key: str = "chan:chat") -> Session:
    msgs: list[dict] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        content = (
            f"这是第{i}条消息，讨论一级建造师建筑工程实务的采分点与教材来源。"
            f"Message number {i} covers scoring points and textbook provenance "
            f"for the construction management exam, with enough length to matter."
        )
        msgs.append({"role": role, "content": content})
    return Session(key=key, messages=msgs)


@pytest.mark.asyncio
async def test_memory_consolidation_rejects_truncated_tool_payload(tmp_path) -> None:
    class TruncatedProvider(LLMProvider):
        async def chat(self, *args, **kwargs):
            return LLMResponse(
                content="partial",
                finish_reason="length",
                tool_calls=[
                    ToolCallRequest(
                        id="partial",
                        name="save_memory",
                        arguments={
                            "history_entry": "must not persist",
                            "memory_update": "must not persist",
                        },
                    )
                ],
            )

        def get_default_model(self) -> str:
            return "fake"

    store = memory.MemoryStore(tmp_path)

    result = await store.consolidate(
        [{"role": "user", "content": "remember this"}],
        TruncatedProvider(),
        "fake",
    )

    assert result is False
    assert not store.memory_file.exists()
    assert not store.history_file.exists()


@pytest.mark.asyncio
async def test_incremental_is_upper_bound_within_ten_percent(tmp_path) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(100)

    full, _ = consolidator.estimate_session_prompt_tokens(session)
    incremental, source = await consolidator._incremental_prompt_tokens(session)

    assert source == "tiktoken_incremental"
    assert full > 0
    # Upper bound: raw messages (superset of stable history) + per-message
    # boundary overhead never under-counts.
    assert incremental >= full
    deviation = (incremental - full) / full
    assert deviation <= 0.10, f"deviation {deviation:.3%} exceeds 10% (full={full}, inc={incremental})"


@pytest.mark.asyncio
async def test_appending_three_messages_encodes_only_three(tmp_path, monkeypatch) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(20)  # below cold-start threshold

    # Prime the cache with the real encoder.
    await consolidator._incremental_prompt_tokens(session)

    calls = {"n": 0}
    real = memory.estimate_message_tokens

    def _counting(message):
        calls["n"] += 1
        return real(message)

    monkeypatch.setattr(memory, "estimate_message_tokens", _counting)

    for i in range(20, 23):
        session.messages.append(
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"追加消息 {i}"}
        )
    await consolidator._incremental_prompt_tokens(session)

    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_clear_resets_cache_no_stale_read(tmp_path) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(30)

    await consolidator._incremental_prompt_tokens(session)
    assert len(consolidator._token_cache[session.key]["per_msg"]) == 30
    base = consolidator._token_cache[session.key]["base"]

    session.clear()  # messages -> [], last_consolidated -> 0
    estimated, _ = await consolidator._incremental_prompt_tokens(session)

    # Stale per-message counts must be dropped; with no messages the estimate is
    # just the constant base segment.
    assert consolidator._token_cache[session.key]["per_msg"] == []
    assert estimated == base

    # A fresh conversation re-populates cleanly, index-aligned.
    session.messages.append({"role": "user", "content": "clear 之后的新会话第一句"})
    session.messages.append({"role": "assistant", "content": "重新开始计数"})
    await consolidator._incremental_prompt_tokens(session)
    assert len(consolidator._token_cache[session.key]["per_msg"]) == 2


@pytest.mark.asyncio
async def test_cold_start_seeds_via_to_thread(tmp_path, monkeypatch) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(70)  # above _COLD_START_MESSAGE_THRESHOLD (64)

    calls = {"n": 0}

    async def _spy_to_thread(func, *args, **kwargs):
        calls["n"] += 1
        return func(*args, **kwargs)

    monkeypatch.setattr(memory.asyncio, "to_thread", _spy_to_thread)

    await consolidator._incremental_prompt_tokens(session)

    assert calls["n"] == 1
    assert len(consolidator._token_cache[session.key]["per_msg"]) == 70


@pytest.mark.asyncio
async def test_cold_start_not_triggered_below_threshold(tmp_path, monkeypatch) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(64)  # exactly at threshold -> NOT above it

    calls = {"n": 0}

    async def _spy_to_thread(func, *args, **kwargs):
        calls["n"] += 1
        return func(*args, **kwargs)

    monkeypatch.setattr(memory.asyncio, "to_thread", _spy_to_thread)

    await consolidator._incremental_prompt_tokens(session)

    assert calls["n"] == 0
    assert len(consolidator._token_cache[session.key]["per_msg"]) == 64


@pytest.mark.asyncio
async def test_boundary_selection_reads_cache(tmp_path, monkeypatch) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session(40)

    # Populate the per-message table.
    await consolidator._incremental_prompt_tokens(session)

    calls = {"n": 0}
    real = memory.estimate_message_tokens

    def _counting(message):
        calls["n"] += 1
        return real(message)

    monkeypatch.setattr(memory, "estimate_message_tokens", _counting)

    boundary = consolidator.pick_consolidation_boundary(session, tokens_to_remove=50)

    assert boundary is not None
    # Fully cached per-message counts -> boundary picking must not re-encode.
    assert calls["n"] == 0
