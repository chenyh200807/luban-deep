"""Subagent spawn must be bounded — anti fan-out DoS / LLM-cost amplification."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.tutorbot.agent.subagent import SubagentManager


def _make_manager(tmp_path: Path) -> SubagentManager:
    provider = SimpleNamespace(get_default_model=lambda: "test-model")
    bus = SimpleNamespace()
    return SubagentManager(provider=provider, workspace=tmp_path, bus=bus)


@pytest.mark.asyncio
async def test_spawn_refused_at_cap(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    # Saturate the running set without launching real tasks.
    mgr._running_tasks = {f"t{i}": object() for i in range(mgr._MAX_RUNNING_SUBAGENTS)}

    result = await mgr.spawn("do something")

    assert "refused" in result.lower()
    # no new task was created beyond the cap
    assert len(mgr._running_tasks) == mgr._MAX_RUNNING_SUBAGENTS
