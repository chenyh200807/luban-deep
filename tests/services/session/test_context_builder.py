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
    monkeypatch.setattr(
        "deeptutor.services.session.context_builder._ContextSummaryAgent.__init__",
        lambda self, language="en": None,
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

    assert builder._history_budget(llm_config) == int(16384 * builder.history_budget_ratio)


def test_context_builder_uses_large_model_default_when_context_missing(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)

    llm_config = type("FakeConfig", (), {"model": "qwen3.6-flash", "max_tokens": 4096})()

    assert builder._history_budget(llm_config) == int(65536 * builder.history_budget_ratio)


def test_context_builder_caps_explicit_large_context_window(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)

    llm_config = type("FakeConfig", (), {"model": "deepseek-v4-flash", "context_window_tokens": 2_000_000})()

    assert builder.context_window_tokens(llm_config) == 1_000_000


@pytest.mark.asyncio
async def test_context_builder_respects_explicit_budget_override(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)
    session = await store.create_session("预算覆盖测试")
    await store.add_message(
        session_id=session["id"],
        role="user",
        content="请保留最近这段上下文",
        capability="chat",
    )

    llm_config = type("FakeConfig", (), {"max_tokens": 4096, "context_window_tokens": 32768})()
    result = await builder.build(
        session_id=session["id"],
        llm_config=llm_config,
        language="zh",
        budget_override=256,
    )

    assert result.budget == 256
    assert result.token_count <= 256


# --- Battle1 W1-T2: single-pass count_tokens approximation + O(n) packing ---


def test_count_tokens_single_pass_calibration() -> None:
    """Approximation stays within ±35%/-16% of tiktoken cl100k_base on
    bilingual exam-domain samples (expected values precomputed offline), and
    Chinese prose never underestimates by more than a few percent."""
    from deeptutor.services.session.context_builder import count_tokens

    # (text, tiktoken_cl100k_tokens) — precomputed 2026-07-11
    samples = [
        ("word " * 100, 101),
        ("消防工程师考试重点内容涵盖建筑防火设计规范" * 20, 520),
        (
            "根据GB50016-2014建筑设计防火规范第5.5.17条,疏散楼梯间 stairwell 的净宽度 net width 不应小于1.10m。" * 10,
            570,
        ),
        ("答案是: 5m深基坑需要专家论证, 3.5%坡度, 50.00万元造价。" * 15, 540),
        (
            "在建筑高度大于二十七米的住宅建筑中，疏散楼梯应当采用防烟楼梯间，并且前室的使用面积不应小于规定数值，管理人员需要定期检查。" * 12,
            936,
        ),
    ]
    for text, real in samples:
        approx = count_tokens(text)
        ratio = approx / real
        assert 0.80 <= ratio <= 2.2, f"ratio {ratio:.2f} out of calibrated band for sample {text[:20]!r}"

    assert count_tokens("") == 0
    assert count_tokens("a") == 1


def test_count_tokens_is_single_pass_fast() -> None:
    """10k-message-scale text must count in linear time (previously each call
    ran a full tiktoken BPE encode on the event loop)."""
    import time

    from deeptutor.services.session.context_builder import count_tokens

    text = ("消防安全技术实务重点章节 fire safety technical practice " * 50) * 200  # ~500KB
    start = time.perf_counter()
    count_tokens(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"count_tokens took {elapsed:.3f}s on 500KB text"


@pytest.mark.asyncio
async def test_context_builder_packing_prunes_to_budget_and_keeps_summary_prefix(tmp_path: Path) -> None:
    """Two-phase packing keeps the original postcondition: fits budget by full
    joined-text count, keeps at least one message, preserves system summary."""
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)
    session = await store.create_session("装箱测试")
    for i in range(30):
        await store.add_message(
            session_id=session["id"],
            role="user" if i % 2 == 0 else "assistant",
            content=f"第{i}条：防烟楼梯间前室使用面积与疏散净宽度的计算要点回顾，包含大量正文内容用于撑大token计数。" * 6,
            capability="chat",
        )

    llm_config = type("FakeConfig", (), {"max_tokens": 4096, "context_window_tokens": 32768})()
    result = await builder.build(
        session_id=session["id"],
        llm_config=llm_config,
        language="zh",
        budget_override=512,
    )

    from deeptutor.services.session.context_builder import build_history_text, count_tokens

    assert result.conversation_history, "history must not be emptied by packing"
    assert count_tokens(build_history_text(result.conversation_history)) <= 512 or len(result.conversation_history) <= 2
    assert result.token_count <= 512 or len(result.conversation_history) <= 2


@pytest.mark.asyncio
async def test_pathological_ascii_history_cannot_breach_budget(tmp_path: Path) -> None:
    """Battle1 对抗审查 MAJOR-2: base64/hex 类 ASCII 使单 pass 近似低估至 ~0.5x，
    旧 gate 会放行真实超窗 2x 的 history。模糊带(approx≤budget<approx*2.2)必须
    经精确计数终判——最终 history 的**精确** token 数不得超预算。"""
    import base64
    import random

    from deeptutor.services.session.context_builder import (
        build_history_text,
        count_tokens_precise,
    )

    rng = random.Random(7)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    builder = ContextBuilder(store)
    session = await store.create_session("对抗装箱")
    for i in range(20):
        blob = base64.b64encode(bytes(rng.randrange(256) for _ in range(300))).decode()
        await store.add_message(
            session_id=session["id"],
            role="user" if i % 2 == 0 else "assistant",
            content=f"报错凭证{i}: {blob}",
            capability="chat",
        )

    llm_config = type("FakeConfig", (), {"max_tokens": 4096, "context_window_tokens": 32768})()
    result = await builder.build(
        session_id=session["id"],
        llm_config=llm_config,
        language="zh",
        budget_override=512,
    )

    precise = count_tokens_precise(build_history_text(result.conversation_history))
    assert precise <= 512 or len(result.conversation_history) <= 2, (
        f"精确 token 数 {precise} 超预算 512——近似低估被放行(爆窗路径复活)"
    )
