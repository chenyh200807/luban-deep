from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from deeptutor.services.benchmark.cassette import Cassette
from deeptutor.services.benchmark.llm_replay import (
    build_recording_stream,
    build_replaying_stream,
    stream_key,
)


def _kwargs(content: str = "hi") -> dict[str, Any]:
    return {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 10,
    }


async def _drain(stream) -> list[str]:
    return [chunk async for chunk in stream]


def test_stream_key_stable_for_same_inputs() -> None:
    assert stream_key(_kwargs()) == stream_key(_kwargs())
    assert stream_key(_kwargs("a")) != stream_key(_kwargs("b"))


@pytest.mark.asyncio
async def test_recording_passes_through_and_records_full_text() -> None:
    async def fake_real(**_kwargs: Any) -> AsyncIterator[str]:
        for chunk in ("Four", "ier"):
            yield chunk

    cassette = Cassette()
    rec = build_recording_stream(fake_real, cassette)
    out = await _drain(rec(**_kwargs()))
    assert out == ["Four", "ier"]  # chunks pass through live unchanged
    assert cassette.replay_llm(stream_key(_kwargs())) == "Fourier"  # full text recorded


@pytest.mark.asyncio
async def test_replaying_returns_recorded_without_calling_real_stream() -> None:
    cassette = Cassette()
    cassette.record_llm(stream_key(_kwargs()), "Fourier")
    rep = build_replaying_stream(cassette)
    out = await _drain(rep(**_kwargs()))
    assert out == ["Fourier"]


@pytest.mark.asyncio
async def test_replay_miss_raises_as_drift_signal() -> None:
    rep = build_replaying_stream(Cassette())
    with pytest.raises(KeyError):
        await _drain(rep(**_kwargs("never-recorded")))


@pytest.mark.asyncio
async def test_record_then_replay_round_trip_is_deterministic() -> None:
    async def fake_real(**_kwargs: Any) -> AsyncIterator[str]:
        yield "ANSWER"

    cassette = Cassette()
    await _drain(build_recording_stream(fake_real, cassette)(**_kwargs()))
    # Replay twice from the same cassette → identical, no real stream needed.
    rep = build_replaying_stream(cassette)
    assert await _drain(rep(**_kwargs())) == ["ANSWER"]
    assert await _drain(rep(**_kwargs())) == ["ANSWER"]
