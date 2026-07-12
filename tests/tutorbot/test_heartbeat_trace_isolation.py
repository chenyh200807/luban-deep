"""Battle2 S5-T2: the heartbeat background loop runs in an EMPTY contextvars
Context so it cannot inherit (and pollute) the creating turn's Langfuse/OTel
trace context or usage scope.

Root cause being pinned: asyncio.create_task snapshots the caller's
contextvars. The heartbeat is started from inside a user turn
(capabilities/tutorbot.py ensure_bot_running → manager.start_bot →
heartbeat.start()), so without an explicit empty Context every future tick's
LLM observation is adopted by that first turn's trace (production traces
observed stretched to ~79,000-90,000s).
"""

from __future__ import annotations

import asyncio
import contextvars
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.tutorbot.heartbeat import service as hb

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = (_REPO_ROOT / "deeptutor" / "tutorbot" / "templates" / "HEARTBEAT.md").read_text(
    encoding="utf-8"
)

# Stand-in for the Langfuse/OTel current-span contextvar a turn would set.
_TURN_CONTEXT = contextvars.ContextVar("test_heartbeat_turn_context", default="clean")


class _ContextProbeProvider:
    """Records the value of _TURN_CONTEXT visible at LLM-call time."""

    def __init__(self) -> None:
        self.seen_contexts: list[str] = []

    async def chat_with_retry(self, *, messages, tools, model):
        _ = (messages, tools, model)
        self.seen_contexts.append(_TURN_CONTEXT.get())
        return SimpleNamespace(
            has_tool_calls=True,
            tool_calls=[SimpleNamespace(arguments={"action": "skip", "tasks": ""})],
        )


@pytest.mark.asyncio
async def test_heartbeat_loop_does_not_inherit_turn_context(tmp_path: Path) -> None:
    provider = _ContextProbeProvider()
    service = hb.HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="m",
        interval_s=0.01,  # tick almost immediately
    )
    # Real task text so the tick reaches the LLM (deterministic gate passes).
    (tmp_path / "HEARTBEAT.md").write_text(
        _TEMPLATE.replace("## Active Tasks", "## Active Tasks\n\n- 每周小测", 1),
        encoding="utf-8",
    )

    # Simulate being inside a user turn (turn-scoped contextvar set).
    token = _TURN_CONTEXT.set("polluted-turn-trace")
    try:
        # Control experiment: a DIRECT call in this context does see the turn
        # value — proving isolation below comes from the task's empty Context.
        await service._tick()
        assert provider.seen_contexts == ["polluted-turn-trace"]

        # The direct tick memoized the LLM "skip" verdict; clear it so the
        # background tick reaches the LLM again.
        service._last_skip_hash = None

        await service.start()
        try:
            assert service._task is not None
            assert service._task.get_name() == "tutorbot:heartbeat"
            for _ in range(200):
                if len(provider.seen_contexts) >= 2:
                    break
                await asyncio.sleep(0.01)
        finally:
            service.stop()
    finally:
        _TURN_CONTEXT.reset(token)

    assert len(provider.seen_contexts) >= 2, "background tick never fired"
    # Every background tick must run with the default (clean) context.
    assert set(provider.seen_contexts[1:]) == {"clean"}
