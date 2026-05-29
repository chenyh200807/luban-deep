"""H5 Gate: concurrent start_turn must not leave session stuck.

Root cause: the second create_turn() at turn_runtime.py:3214 (after the
except-block recovery path) has no try/except. If create_turn always raises
"active turn", the RuntimeError propagates unhandled — the WS handler may
not surface it as a client error event.

Fix: wrap the second create_turn in try/except so start_turn always raises
a clean RuntimeError the WS layer can catch and forward to the client.
"""
from __future__ import annotations

import pytest

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager


@pytest.mark.asyncio
async def test_start_turn_raises_clean_error_when_create_turn_always_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """When create_turn persistently raises 'active turn', start_turn must raise
    RuntimeError — not propagate an unhandled exception that leaves session stuck.
    """
    async def _no_run_turn(self, _execution):
        return None

    async def _always_conflict(session_id: str, capability: str = "") -> dict:
        raise RuntimeError("active turn exists; cannot create another")

    monkeypatch.setattr(TurnRuntimeManager, "_run_turn", _no_run_turn)

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    monkeypatch.setattr(store, "create_turn", _always_conflict)

    with pytest.raises(RuntimeError):
        await runtime.start_turn(
            {
                "session_id": "session-h5-concurrent",
                "content": "test concurrent conflict",
                "capability": "tutorbot",
                "language": "zh",
            }
        )
