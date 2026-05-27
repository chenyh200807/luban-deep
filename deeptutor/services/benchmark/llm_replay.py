"""LLM interception shim for record/replay (harness 9+ roadmap H1 keystone).

Wraps the chat pipeline's streaming LLM entry point (``agentic_pipeline.llm_stream``)
so a turn's completions can be recorded once (live) and replayed deterministically
(zero network / zero key). Only the non-deterministic LLM I/O is intercepted; the
rest of the pipeline executes normally — the record-and-replay principle.

Scope (C8 step-1, deliberately minimal): covers the streaming entry that the
no-tool chat stages use. The tool-loop client and ``factory.complete`` are NOT
yet intercepted — that is the next increment once stream replay determinism is
validated. ``replay`` raises ``KeyError`` on a cassette miss on purpose: a miss
means the prompt drifted, which is exactly the regression/determinism signal we
want to surface (roadmap C1b), not silently swallow.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable

from deeptutor.services.benchmark.cassette import Cassette, llm_key

# Decode parameters that affect the token distribution and so must be part of
# the cassette key (record-and-replay research: model id + decode params + input).
_DECODE_PARAM_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "reasoning_effort",
)

LLMStream = Callable[..., AsyncIterator[str]]


def stream_key(kwargs: dict[str, Any]) -> str:
    """Cassette key for an ``llm_stream`` call from its kwargs."""
    params = {key: kwargs[key] for key in _DECODE_PARAM_KEYS if key in kwargs}
    return llm_key(
        model=str(kwargs.get("model") or ""),
        messages=list(kwargs.get("messages") or []),
        params=params,
    )


def build_recording_stream(real_stream: LLMStream, cassette: Cassette) -> LLMStream:
    """Wrap ``real_stream``: pass chunks through live, then record the full text."""

    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        key = stream_key(kwargs)
        chunks: list[str] = []
        async for chunk in real_stream(*args, **kwargs):
            chunks.append(chunk)
            yield chunk
        cassette.record_llm(key, "".join(chunks))

    return _stream


def build_replaying_stream(cassette: Cassette) -> LLMStream:
    """Replay the recorded completion for a call; raise on a cassette miss."""

    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        recorded = cassette.replay_llm(stream_key(kwargs))  # KeyError on drift
        yield recorded

    return _stream
