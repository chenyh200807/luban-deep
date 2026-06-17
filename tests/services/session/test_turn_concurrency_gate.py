"""Global turn-concurrency admission gate — orderly queue + peak shaving.

Bounds simultaneously in-flight turns per worker: excess waits briefly (queue), then
is shed cleanly instead of firing another LLM call into an overload.
"""

from __future__ import annotations

import asyncio

import pytest

from deeptutor.services.session import turn_runtime as tr


@pytest.fixture(autouse=True)
def _reset_semaphore(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "_turn_concurrency_semaphore", None)
    yield
    tr._turn_concurrency_semaphore = None


def test_gate_admits_up_to_cap_then_sheds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "_MAX_CONCURRENT_TURNS", 2)
    monkeypatch.setattr(tr, "_TURN_QUEUE_TIMEOUT_S", 0.05)
    tr._turn_concurrency_semaphore = None  # rebuild at cap=2

    async def _exercise() -> tuple[bool, bool, bool, bool]:
        a = await tr._acquire_turn_slot()   # 1/2
        b = await tr._acquire_turn_slot()   # 2/2
        c = await tr._acquire_turn_slot()   # saturated -> shed after timeout
        tr._release_turn_slot()             # free one
        d = await tr._acquire_turn_slot()   # admitted again
        return a, b, c, d

    a, b, c, d = asyncio.run(_exercise())
    assert a is True
    assert b is True
    assert c is False   # shed when saturated (orderly-wait then reject)
    assert d is True    # releasing a slot re-admits


def test_gate_queues_until_a_slot_frees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tr, "_MAX_CONCURRENT_TURNS", 1)
    monkeypatch.setattr(tr, "_TURN_QUEUE_TIMEOUT_S", 1.0)
    tr._turn_concurrency_semaphore = None

    async def _exercise() -> bool:
        first = await tr._acquire_turn_slot()
        assert first is True

        async def _free_soon() -> None:
            await asyncio.sleep(0.1)
            tr._release_turn_slot()

        asyncio.create_task(_free_soon())
        # second waits in the queue and is admitted once the first releases (< timeout)
        return await tr._acquire_turn_slot()

    assert asyncio.run(_exercise()) is True
