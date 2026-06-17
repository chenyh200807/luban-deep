from __future__ import annotations

import asyncio

import pytest

from deeptutor.api.routers.unified_ws import (
    _await_stopped_subscription_task,
    _discard_current_subscription_task,
)


@pytest.mark.asyncio
async def test_failed_subscription_task_does_not_break_stop_cleanup(caplog: pytest.LogCaptureFixture) -> None:
    async def fail() -> None:
        raise RuntimeError("forward failed")

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)

    await _await_stopped_subscription_task("turn-1", task)

    assert task.done()
    assert "turn-1" in caplog.text
    assert "forward failed" in caplog.text


@pytest.mark.asyncio
async def test_subscription_task_cleanup_only_discards_matching_task() -> None:
    old_task = asyncio.create_task(asyncio.sleep(0))
    current_task = asyncio.create_task(asyncio.sleep(10))
    subscription_tasks = {"turn-1": current_task}

    _discard_current_subscription_task(subscription_tasks, "turn-1", old_task)
    assert subscription_tasks["turn-1"] is current_task

    _discard_current_subscription_task(subscription_tasks, "turn-1", current_task)
    assert "turn-1" not in subscription_tasks

    await old_task
    current_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await current_task
