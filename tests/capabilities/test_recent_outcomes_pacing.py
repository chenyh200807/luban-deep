"""plan §Phase 5 / Batch E Gap 4 — recent_grading_outcomes 写入与消费真接入测试。

验证：
  1. _emit_grading_result 在 result_payload.active_object.state_snapshot 写
     recent_outcomes 滑动窗口 (最近 5 条)。
  2. 下一次 capability.run 时把 active_object.state_snapshot.recent_outcomes
     读到 context.metadata.recent_grading_outcomes。
  3. classify_difficulty_pacing 用真实写入的窗口能正确分类：
     - 连错 2 次 → suggest_consolidation
     - 连对 3 次 → suggest_step_up
     - mixed → hold
"""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.construction_grading.progressive_disclosure import (
    classify_difficulty_pacing,
)


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)
    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)


async def _collect_events(run_coro) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await run_coro(bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


def _build_grading_context(
    *, user_selection: str, correct: str, prev_recent: list[bool] | None = None
) -> UnifiedContext:
    active = None
    if prev_recent is not None:
        active = {
            "object_type": "question_set",
            "object_id": "qset",
            "scope": {"domain": "session", "session_id": "sess"},
            "state_snapshot": {
                "question_id": "q_prev",
                "recent_outcomes": list(prev_recent),
            },
            "version": 1,
            "entered_at": "",
            "last_touched_at": "",
            "source_turn_id": "t_prev",
        }
    metadata = {
        "conversation_context_text": "",
        "question_followup_context": {
            "question_id": "q_X",
            "question": "test",
            "question_type": "choice",
            "options": {"A": "A", "B": "B"},
            "correct_answer": correct,
        },
    }
    if active:
        metadata["active_object"] = active
    return UnifiedContext(user_message=user_selection, language="zh", metadata=metadata)


@pytest.mark.asyncio
async def test_recent_outcomes_written_to_active_object_after_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoord:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used in grading")

    class FakeGrader:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("deterministic feedback should not invoke grader")

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoord)
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeGrader,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    # 第 1 次：答错 (selected A, correct B) — 写入 [False]
    context = _build_grading_context(user_selection="我选A", correct="B", prev_recent=None)
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    result = next(e for e in events if e.type == StreamEventType.RESULT)
    ao = result.metadata.get("active_object") or {}
    snap = ao.get("state_snapshot") or {}
    assert snap.get("recent_outcomes") == [False], "first wrong answer must push False"


@pytest.mark.asyncio
async def test_recent_outcomes_sliding_window_keeps_five_most_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoord:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    class FakeGrader:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoord)
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeGrader,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    # 已有 5 个 True，再答错 1 次 → 新窗口应是 [False, T, T, T, T] (drop oldest True)
    context = _build_grading_context(
        user_selection="我选A", correct="B", prev_recent=[True, True, True, True, True]
    )
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    result = next(e for e in events if e.type == StreamEventType.RESULT)
    snap = (result.metadata.get("active_object") or {}).get("state_snapshot") or {}
    outcomes = snap.get("recent_outcomes") or []
    assert len(outcomes) == 5, "sliding window must keep at most 5"
    assert outcomes[0] is False, "newest entry must be at index 0"


@pytest.mark.asyncio
async def test_progressive_disclosure_pacing_suggest_consolidation_after_two_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoord:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    class FakeGrader:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoord)
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeGrader,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    # 已有 [False]（上次错），再答错一次 → recent_outcomes=[False, False] → suggest_consolidation
    context = _build_grading_context(user_selection="我选A", correct="B", prev_recent=[False])
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    result = next(e for e in events if e.type == StreamEventType.RESULT)
    disclosure = result.metadata.get("progressive_disclosure") or {}
    assert disclosure.get("difficulty_pacing") == "suggest_consolidation"


@pytest.mark.asyncio
async def test_progressive_disclosure_pacing_suggest_step_up_after_three_correct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoord:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    class FakeGrader:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoord)
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeGrader,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    # 已有 [True, True]，再答对一次 → [True, True, True] → suggest_step_up
    context = _build_grading_context(user_selection="我选B", correct="B", prev_recent=[True, True])
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    result = next(e for e in events if e.type == StreamEventType.RESULT)
    disclosure = result.metadata.get("progressive_disclosure") or {}
    assert disclosure.get("difficulty_pacing") == "suggest_step_up"


@pytest.mark.asyncio
async def test_progressive_disclosure_pacing_hold_for_mixed_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoord:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    class FakeGrader:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoord)
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeGrader,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    # mixed: [True, False] 之后答对 → [True, True, False] → hold (no 2 consecutive false, no 3 consecutive true)
    context = _build_grading_context(user_selection="我选B", correct="B", prev_recent=[True, False])
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    result = next(e for e in events if e.type == StreamEventType.RESULT)
    disclosure = result.metadata.get("progressive_disclosure") or {}
    assert disclosure.get("difficulty_pacing") == "hold"


def test_classify_difficulty_pacing_basic_cases() -> None:
    assert classify_difficulty_pacing([False, False]) == "suggest_consolidation"
    assert classify_difficulty_pacing([True, True, True]) == "suggest_step_up"
    assert classify_difficulty_pacing([True, False, True]) == "hold"
    assert classify_difficulty_pacing([]) == "hold"
