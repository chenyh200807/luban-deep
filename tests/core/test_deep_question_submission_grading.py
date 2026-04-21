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
    assert result_event.metadata["question_followup_context"]["user_answer"] == "B"


@pytest.mark.asyncio
async def test_deep_question_routes_batch_submission_to_grading_agent(
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
            items = kwargs["question_context"]["items"]
            assert [item["user_answer"] for item in items] == ["C", "A", "B"]
            assert [item["is_correct"] for item in items] == [True, True, False]
            return "第1题和第2题正确，第3题需要回看防水等级与设防道数。"

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
        user_message="第1题：C；第2题：A；第3题：B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚完成一组建筑构造选择题。",
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "choice",
                        "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "choice",
                        "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "choice",
                        "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                        "correct_answer": "D",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["process"]["history_context"] == "用户刚完成一组建筑构造选择题。"
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert result_event.metadata["question_followup_context"]["items"][0]["user_answer"] == "C"
    assert result_event.metadata["question_followup_context"]["items"][2]["is_correct"] is False


@pytest.mark.asyncio
async def test_deep_question_fast_mode_uses_deterministic_grading_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FailingSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("fast deterministic grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FailingSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题选B，第2题选C。你帮我批改，并且针对我错的地方解释一下。",
        language="zh",
        metadata={
            "selected_mode": "fast",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
            },
            "question_followup_action": {
                "intent": "answer_questions",
                "answers": [
                    {"question_id": "q_1", "answer": "B"},
                    {"question_id": "q_2", "answer": "C"},
                ],
            },
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "choice",
                        "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                        "correct_answer": "B",
                        "explanation": "第1题考查流水步距定义。",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "choice",
                        "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                        "correct_answer": "B",
                        "explanation": "第2题关键在于先抓住同一施工段的起算点。",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert "得分" in result_event.metadata["response"]
    assert "第2题：错误" in result_event.metadata["response"]
    assert "第2题关键在于先抓住同一施工段的起算点。" in result_event.metadata["response"]


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

    answer = capability._build_submission_context(
        {
            "question": "流水施工题",
            "question_type": "choice",
            "correct_answer": "B",
        },
        "B",
    )["user_answer"]

    assert answer == "B"


def test_build_submission_context_accepts_judgment_style_submission() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "判断：流水步距反映相邻专业队投入的时间间隔。",
            "question_type": "choice",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "B",
        },
        "B",
    )

    assert context["is_correct"] is True
    assert context["diagnosis"] == "CORRECT"
