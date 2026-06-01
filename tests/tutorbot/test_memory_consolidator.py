from __future__ import annotations

import gc
import sys
import types
import weakref
from types import SimpleNamespace

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
    info=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
    debug=lambda *args, **kwargs: None,
    exception=lambda *args, **kwargs: None,
)
sys.modules.setdefault("loguru", fake_loguru)

from deeptutor.tutorbot.agent.memory import MemoryConsolidator


def test_memory_consolidator_session_lock_is_strongly_retained(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )

    lock = consolidator.get_lock("session-1")
    lock_ref = weakref.ref(lock)
    del lock
    gc.collect()

    assert lock_ref() is not None
    assert consolidator.get_lock("session-1") is lock_ref()
