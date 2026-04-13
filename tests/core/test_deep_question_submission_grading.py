from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


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
        setattr(parent, parts[-1], module)


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


@pytest.mark.asyncio
async def test_deep_question_routes_choice_submission_to_grading_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **kwargs: Any) -> str:
            captured["process"] = kwargs
            assert kwargs["question_context"]["user_answer"] == "B"
            assert kwargs["question_context"]["is_correct"] is True
            assert kwargs["question_context"]["diagnosis"] == "CORRECT"
            return "## 🧐 解析\n你这题选对了。\n\n## ⚠️ 易错点\n不要混淆步距和节拍。\n\n## 🎯 记忆锦囊\n队与队之间看步距。\n\n## 🚀 下一步建议\n再做 1 道同类题巩固。"

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "q_5",
                "question": "流水步距反映的是什么？",
                "question_type": "choice",
                "options": {"A": "工期", "B": "相邻专业队投入间隔"},
                "correct_answer": "B",
                "explanation": "步距看相邻专业队之间的时间间隔。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["process"]["history_context"] == "用户刚做完一道选择题。"
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["user_answer"] == "B"
    assert result_event.metadata["is_correct"] is True


def test_build_submission_context_marks_oversight_for_negative_stem() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "下列关于流水施工的说法，错误的是哪一项？",
            "question_type": "choice",
            "correct_answer": "C",
            "explanation": "题干问的是错误项，关键在于先识别否定式设问。",
        },
        "A",
    )

    assert context["diagnosis"] == "OVERSIGHT"
    assert context["score"] == 0


def test_build_submission_context_marks_memory_decay_for_numeric_fact() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "防水混凝土养护时间至少应为多少天？",
            "question_type": "choice",
            "correct_answer": "B",
            "explanation": "规范要求连续养护不少于14天。",
        },
        "A",
    )

    assert context["diagnosis"] == "MEMORY_DECAY"


def test_extract_submission_answer_accepts_slip_style_submission() -> None:
    capability = DeepQuestionCapability()

    answer = capability._extract_submission_answer(
        "我手滑选了B",
        {
            "question_type": "choice",
        },
    )

    assert answer == "B"
