from __future__ import annotations

import asyncio
from typing import Any

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _RecordingQueue:
    def __init__(self) -> None:
        self.items: list[Any] = []

    async def put(self, item: Any) -> None:
        self.items.append(item)


class _RemovingQueue(_RecordingQueue):
    def __init__(self, bus: StreamBus) -> None:
        super().__init__()
        self.bus = bus

    async def put(self, item: Any) -> None:
        self.bus._subscribers.remove(self)  # type: ignore[arg-type, attr-defined]
        await asyncio.sleep(0)
        self.items.append(item)


@pytest.mark.asyncio
async def test_emit_fanout_uses_stable_subscriber_snapshot() -> None:
    bus = StreamBus()
    first = _RemovingQueue(bus)
    second = _RecordingQueue()
    bus._subscribers = [first, second]  # type: ignore[list-item, attr-defined]
    event = StreamEvent(type=StreamEventType.CONTENT, content="hello")

    await bus.emit(event)

    assert first.items == [event]
    assert second.items == [event]


@pytest.mark.asyncio
async def test_close_fanout_uses_stable_subscriber_snapshot() -> None:
    bus = StreamBus()
    first = _RemovingQueue(bus)
    second = _RecordingQueue()
    bus._subscribers = [first, second]  # type: ignore[list-item, attr-defined]

    await bus.close()

    assert first.items == [None]
    assert second.items == [None]


@pytest.mark.asyncio
async def test_subscribe_history_replay_does_not_duplicate_live_event() -> None:
    bus = StreamBus()
    first = StreamEvent(type=StreamEventType.CONTENT, content="first")
    second = StreamEvent(type=StreamEventType.CONTENT, content="second")
    await bus.emit(first)

    subscription = bus.subscribe()
    assert await anext(subscription) is first

    await bus.emit(second)

    assert await asyncio.wait_for(anext(subscription), timeout=0.1) is second
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(anext(subscription), timeout=0.05)

    await subscription.aclose()


@pytest.mark.asyncio
async def test_subscribe_drains_live_event_queued_before_close_after_history_replay() -> None:
    bus = StreamBus()
    first = StreamEvent(type=StreamEventType.CONTENT, content="first")
    second = StreamEvent(type=StreamEventType.CONTENT, content="second")
    await bus.emit(first)

    subscription = bus.subscribe()
    assert await anext(subscription) is first

    await bus.emit(second)
    await bus.close()

    assert await asyncio.wait_for(anext(subscription), timeout=0.1) is second
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(subscription), timeout=0.1)


@pytest.mark.asyncio
async def test_late_subscriber_replays_history_and_stops_after_close() -> None:
    bus = StreamBus()
    event = StreamEvent(type=StreamEventType.ERROR, content="closed")

    await bus.emit(event)
    await bus.close()

    subscription = bus.subscribe()
    assert await asyncio.wait_for(anext(subscription), timeout=0.1) is event
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(subscription), timeout=0.1)
