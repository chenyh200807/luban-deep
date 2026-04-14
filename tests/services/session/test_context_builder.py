from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.core.stream import StreamEventType
from deeptutor.services.session.context_builder import (
    ContextBuilder,
    sanitize_conversation_summary,
)
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def test_sanitize_conversation_summary_removes_internal_headings() -> None:
    raw = """
**压缩后的上下文摘要 (供后续轮次直接使用):**

*   **用户核心目标**：掌握钢筋工程中“搭接长度”与“锚固长度”的区别。
*   **当前状态**：
    1. **概念与计算已讲解**：已经讲过 Lab → La → Ll。
*   **助理当前任务**：
    1. 继续出一道综合判断题。
""".strip()

    cleaned = sanitize_conversation_summary(raw)

    assert "压缩后的上下文摘要" not in cleaned
    assert "用户核心目标" not in cleaned
    assert "当前状态" not in cleaned
    assert "助理当前任务" not in cleaned
    assert "**" not in cleaned
    assert "目标：掌握钢筋工程中" in cleaned
    assert "进展：" in cleaned
    assert "下一步：" in cleaned


def test_context_builder_wraps_summary_as_private_memory(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)

    history = builder._build_history(
        """
**压缩后的上下文摘要 (供后续轮次直接使用):**
*   **用户核心目标**：掌握搭接与锚固的区别。
""",
        [],
        language="zh",
    )

    assert history[0]["role"] == "system"
    assert "内部连续性备忘" in history[0]["content"]
    assert "不要逐字复述" in history[0]["content"]
    assert "压缩后的上下文摘要" not in history[0]["content"]
    assert "用户核心目标" not in history[0]["content"]
    assert "目标：掌握搭接与锚固的区别。" in history[0]["content"]


@pytest.mark.asyncio
async def test_summarize_does_not_stream_internal_summary_to_users(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)
    published = []

    async def collect(event) -> None:
        published.append(event)

    async def fake_stream_llm(self, **_kwargs):
        callback = getattr(self, "_trace_callback", None)
        if callback is not None:
            await callback({"event": "llm_call", "state": "running"})
        yield "目标：掌握搭接与锚固。"
        if callback is not None:
            await callback(
                {
                    "event": "llm_call",
                    "state": "complete",
                    "response": "目标：掌握搭接与锚固。",
                }
            )

    monkeypatch.setattr(
        "deeptutor.services.session.context_builder._ContextSummaryAgent.stream_llm",
        fake_stream_llm,
    )

    summary, events = await builder._summarize(
        session_id="session-1",
        language="zh",
        source_text="User: hello",
        summary_budget=128,
        on_event=collect,
    )

    assert summary == "目标：掌握搭接与锚固。"
    assert events
    assert all(event.type != StreamEventType.CONTENT for event in events)
    assert all(event.type != StreamEventType.CONTENT for event in published)


def test_context_builder_uses_context_window_budget_when_available(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)

    llm_config = type(
        "FakeConfig",
        (),
        {
            "max_tokens": 4096,
            "context_window_tokens": 16384,
        },
    )()

    assert builder._history_budget(llm_config) == int(16384 * builder.history_budget_ratio)


def test_context_builder_uses_safe_minimum_context_window(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)

    llm_config = type("FakeConfig", (), {"max_tokens": 4096})()

    assert builder._history_budget(llm_config) == int(8192 * builder.history_budget_ratio)
