"""Battle1 W2-T3: CONTENT-delta batch persistence must be replay-equivalent.

Contract under test (contracts/turn.md §15, turn_runtime W2-T3 comments):

- seq is allocated by the per-turn in-memory allocator, stamped before any
  fan-out, and the DB always holds a contiguous seq prefix (1..MAX, no holes).
- The batch path writes rows field-equivalent to the preserved single-event
  ``append_turn_event`` path (one row per event — deltas are never merged).
- Non-content events (result/error/done/tool_*/progress/…) are persisted
  before fan-out, in ONE transaction together with all buffered deltas.
- A crash inside the flush window loses only unflushed content deltas; the
  terminal event later lands at MAX+1 with no seq hole (orphan-recovery path).
- A same-worker subscriber attaching while deltas are buffered sees a
  contiguous seq sequence (flush-on-subscribe before the catchup read).
"""

from __future__ import annotations

import asyncio

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import (
    TurnRuntimeManager,
    _TurnExecution,
)

_REPLAY_FIELDS = ("type", "source", "stage", "content", "metadata", "timestamp")


@pytest.fixture()
def store(tmp_path):
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    yield store
    store.close()


@pytest.fixture()
def runtime(store, monkeypatch):
    monkeypatch.setattr(
        TurnRuntimeManager,
        "_mirror_event_to_workspace",
        staticmethod(lambda *_args, **_kwargs: None),
    )
    return TurnRuntimeManager(store)


async def _new_execution(store, runtime, session_id: str) -> _TurnExecution:
    session = await store.create_session(session_id=session_id)
    turn = await store.create_turn(session["id"], capability="chat")
    execution = _TurnExecution(
        turn_id=turn["id"],
        session_id=session["id"],
        capability="chat",
        payload={},
    )
    execution.next_seq = int(turn.get("last_seq") or 0) + 1
    runtime._executions[turn["id"]] = execution
    return execution


def _content(text: str) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.CONTENT,
        source="chat",
        stage="responding",
        content=text,
    )


def _design_sequence() -> list[StreamEvent]:
    """content×40 + tool_call + content×20 + result + done (design assertion 1)."""
    events: list[StreamEvent] = [_content(f"delta-{i:03d}") for i in range(40)]
    events.append(
        StreamEvent(
            type=StreamEventType.TOOL_CALL,
            source="chat",
            stage="acting",
            metadata={"tool": "rag", "args": {"query": "q"}},
        )
    )
    events.extend(_content(f"tail-{i:03d}") for i in range(20))
    events.append(
        StreamEvent(
            type=StreamEventType.RESULT,
            source="chat",
            stage="responding",
            metadata={"response": "final answer"},
        )
    )
    events.append(StreamEvent(type=StreamEventType.DONE, source="chat"))
    return events


@pytest.mark.asyncio
async def test_batched_replay_rows_equal_legacy_single_append_rows(store, runtime) -> None:
    """(1) 回放等价: batch-written rows == legacy per-event append rows, seq==1..N."""
    execution = await _new_execution(store, runtime, "session-replay-eq")
    for event in _design_sequence():
        await runtime._persist_and_publish(execution, event)

    rows_batched = await store.get_turn_events(execution.turn_id, 0)
    assert [row["seq"] for row in rows_batched] == list(range(1, len(rows_batched) + 1))
    assert len(rows_batched) == 63  # 40 + tool_call + 20 + result + done — one row per event

    # Legacy baseline: replay the SAME logical events one-by-one through the
    # preserved single-event path (store-side MAX+1 allocation, one commit each).
    baseline = await _new_execution(store, runtime, "session-replay-baseline")
    for row in rows_batched:
        legacy_payload = {
            key: value
            for key, value in row.items()
            if key not in ("seq", "turn_id", "session_id")
        }
        await store.append_turn_event(baseline.turn_id, legacy_payload)

    rows_legacy = await store.get_turn_events(baseline.turn_id, 0)
    assert len(rows_legacy) == len(rows_batched)
    for batched, legacy in zip(rows_batched, rows_legacy):
        assert batched["seq"] == legacy["seq"]
        assert batched.get("visibility") == legacy.get("visibility")
        for field_name in _REPLAY_FIELDS:
            assert batched[field_name] == legacy[field_name], field_name


@pytest.mark.asyncio
async def test_resume_after_seq_returns_exact_suffix(store, runtime) -> None:
    """(2) resume 等价: after_seq=k returns exactly the events with seq>k."""
    execution = await _new_execution(store, runtime, "session-resume")
    for event in _design_sequence():
        await runtime._persist_and_publish(execution, event)
    total = 63
    # k=0 (full replay), k=17 (inside the first content batch), k=40 (content/
    # tool_call batch boundary), k=41 (start of the second content run), k=62
    # (only the terminal done left).
    for k in (0, 17, 40, 41, 62):
        rows = await store.get_turn_events(execution.turn_id, k)
        assert [row["seq"] for row in rows] == list(range(k + 1, total + 1)), k
    assert await store.get_turn_events(execution.turn_id, total) == []


@pytest.mark.asyncio
async def test_crash_window_keeps_contiguous_prefix_and_recovery_continues_at_max_plus_one(
    store, runtime
) -> None:
    """(3) 崩溃窗口: unflushed deltas are lost, prefix stays contiguous, recovery appends MAX+1."""
    execution = await _new_execution(store, runtime, "session-crash")
    # 3 deltas, then a progress event → ONE transaction with 4 rows.
    for i in range(3):
        await runtime._persist_and_publish(execution, _content(f"pre-{i}"))
    await runtime._persist_and_publish(
        execution,
        StreamEvent(type=StreamEventType.PROGRESS, source="turn_runtime", stage="writing"),
    )
    # 6 more deltas stay in the buffer (below every flush threshold), then the
    # process "crashes": the execution is dropped without any terminal flush.
    for i in range(6):
        await runtime._persist_and_publish(execution, _content(f"lost-{i}"))
    runtime._executions.pop(execution.turn_id, None)

    rows = await store.get_turn_events(execution.turn_id, 0)
    seqs = [row["seq"] for row in rows]
    assert seqs == list(range(1, len(seqs) + 1))  # contiguous prefix, no holes
    assert len(rows) == 4 < 10  # 10 events were stamped; only the flushed prefix survives

    # Orphan recovery appends its terminal event through the preserved
    # single-event path (no pre-allocated seq → store-side MAX+1).
    recovered = await store.append_turn_event(
        execution.turn_id,
        {"type": "done", "source": "turn_runtime", "metadata": {"status": "failed"}},
    )
    assert recovered["seq"] == 5
    seqs_after = [row["seq"] for row in await store.get_turn_events(execution.turn_id, 0)]
    assert seqs_after == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_terminal_event_lands_in_same_transaction_as_buffered_deltas(
    store, runtime, monkeypatch
) -> None:
    """(4) 终态不丢: content×5 + done → 6 rows via exactly ONE batch call."""
    execution = await _new_execution(store, runtime, "session-terminal")
    batch_calls: list[int] = []
    original_batch = store.append_turn_events_batch

    async def _spy_batch(turn_id, events):
        batch_calls.append(len(events))
        return await original_batch(turn_id, events)

    monkeypatch.setattr(store, "append_turn_events_batch", _spy_batch)

    for i in range(5):
        await runtime._persist_and_publish(execution, _content(f"chunk-{i}"))
    await runtime._persist_and_publish(
        execution,
        StreamEvent(type=StreamEventType.DONE, source="chat", metadata={"status": "completed"}),
    )

    assert batch_calls == [6]  # one transaction carrying the 5 deltas + done
    rows = await store.get_turn_events(execution.turn_id, 0)
    assert [row["seq"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[-1]["type"] == "done"
    assert execution.pending_events == []


@pytest.mark.asyncio
async def test_subscriber_attaching_over_buffered_deltas_sees_no_seq_hole(
    store, runtime
) -> None:
    """(5) 订阅无空洞: flush-on-subscribe closes the buffered-but-fanned-out gap."""
    execution = await _new_execution(store, runtime, "session-subscribe")
    for i in range(5):
        await runtime._persist_and_publish(execution, _content(f"early-{i}"))
    # All five deltas are still buffered: nothing has reached the store yet.
    assert await store.get_turn_events(execution.turn_id, 0) == []

    received: list[dict] = []
    subscription = runtime.subscribe_turn(execution.turn_id, after_seq=0)
    # Pull the five catch-up items — the generator attaches the subscriber and
    # runs the flush-on-subscribe hook before its catchup read.
    for _ in range(5):
        received.append(await asyncio.wait_for(subscription.__anext__(), timeout=5))
    assert [item["seq"] for item in received] == [1, 2, 3, 4, 5]
    # The flush hook persisted the buffered deltas before the catchup read.
    assert len(await store.get_turn_events(execution.turn_id, 0)) == 5

    # Live phase: two more deltas and the terminal done fan out to the queue.
    await runtime._persist_and_publish(execution, _content("live-0"))
    await runtime._persist_and_publish(execution, _content("live-1"))
    await runtime._persist_and_publish(
        execution,
        StreamEvent(type=StreamEventType.DONE, source="chat", metadata={"status": "completed"}),
    )
    for _ in range(3):
        received.append(await asyncio.wait_for(subscription.__anext__(), timeout=5))
    await subscription.aclose()

    assert [item["seq"] for item in received] == list(range(1, 9))  # contiguous, no dupes


@pytest.mark.asyncio
async def test_concurrent_turns_batch_commits_and_keep_per_turn_contiguity(
    store, runtime, monkeypatch
) -> None:
    """并发冒烟: 8 turns × (200 deltas + done) → 1608 rows, contiguous seqs, few batches."""
    batch_calls: list[int] = []
    original_batch = store.append_turn_events_batch

    async def _spy_batch(turn_id, events):
        batch_calls.append(len(events))
        return await original_batch(turn_id, events)

    monkeypatch.setattr(store, "append_turn_events_batch", _spy_batch)

    executions = [
        await _new_execution(store, runtime, f"session-load-{i}") for i in range(8)
    ]

    async def _drive(execution: _TurnExecution) -> None:
        for i in range(200):
            await runtime._persist_and_publish(execution, _content("x"))
        await runtime._persist_and_publish(
            execution,
            StreamEvent(type=StreamEventType.DONE, source="chat", metadata={"status": "completed"}),
        )

    await asyncio.gather(*(_drive(execution) for execution in executions))

    total_rows = 0
    for execution in executions:
        rows = await store.get_turn_events(execution.turn_id, 0)
        assert [row["seq"] for row in rows] == list(range(1, 202))
        assert rows[-1]["type"] == "done"
        total_rows += len(rows)
    assert total_rows == 8 * 201 == 1608
    assert sum(batch_calls) == 1608  # every stamped event was persisted exactly once
    # Batching must actually batch: with the 64-event threshold each turn needs
    # ~4 commits (3 threshold flushes + terminal flush); allow slack for
    # elapsed-window flushes on slow machines but stay far below one-per-event.
    assert len(batch_calls) < 400
