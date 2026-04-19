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
from deeptutor.services.semantic_router import build_active_object_from_question_context


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
async def test_deep_question_grading_result_emits_active_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "你这题选对了。"

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

    question_context = {
        "question_id": "q_5",
        "question": "流水步距反映的是什么？",
        "question_type": "choice",
        "options": {"A": "工期", "B": "相邻专业队投入间隔"},
        "correct_answer": "B",
        "explanation": "步距看相邻专业队之间的时间间隔。",
    }
    active_object = build_active_object_from_question_context(
        question_context,
        source_turn_id="turn-grade",
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "active_object": active_object or {},
            "turn_semantic_decision": {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
                "target_object_ref": {"object_type": "single_question", "object_id": "q_5"},
                "allowed_patch": ["update_answer_slot"],
                "confidence": 0.95,
                "reason": "用户正在回答当前题目。",
            },
            "question_followup_context": question_context,
            "question_followup_action": {
                "intent": "answer_questions",
                "confidence": 0.95,
                "preserve_other_answers": False,
                "answers": [{"index": 1, "question_id": "q_5", "user_answer": "B"}],
                "reason": "用户正在回答当前题目。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["active_object"]["object_type"] == "single_question"
    assert result_event.metadata["active_object"]["object_id"] == "q_5"
    assert result_event.metadata["turn_semantic_decision"]["next_action"] == "route_to_grading"


@pytest.mark.asyncio
async def test_deep_question_generation_pushes_previous_active_object_into_suspended_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, _callback) -> None:
            return None

        def set_trace_callback(self, _callback) -> None:
            return None

        async def generate_from_topic(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "新题组第1题：流水节拍反映什么？",
                            "options": {"A": "时间", "B": "资源"},
                            "correct_answer": "A",
                            "explanation": "节拍反映单位工作队的作业时间。",
                        }
                    },
                    {
                        "qa_pair": {
                            "question": "新题组第2题：流水步距反映什么？",
                            "options": {"A": "工期", "B": "相邻专业队投入间隔"},
                            "correct_answer": "B",
                            "explanation": "步距看相邻专业队之间的投入间隔。",
                        }
                    },
                ]
            }

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    old_question_context = {
        "question_id": "quiz_old",
        "question": "旧题组第1题...\n旧题组第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_old_1",
                "question": "旧题1",
                "question_type": "choice",
                "options": {"A": "A1", "B": "B1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_old_2",
                "question": "旧题2",
                "question_type": "choice",
                "options": {"A": "A2", "B": "B2"},
                "correct_answer": "B",
            },
        ],
    }
    active_object = build_active_object_from_question_context(
        old_question_context,
        source_turn_id="turn-old",
    )

    context = UnifiedContext(
        user_message="再来两题类似的",
        language="zh",
        config_overrides={"mode": "custom", "topic": "流水施工", "num_questions": 2, "question_type": "choice"},
        metadata={
            "turn_id": "turn-new",
            "active_object": active_object or {},
            "question_followup_context": old_question_context,
            "turn_semantic_decision": {
                "relation_to_active_object": "continue_same_learning_flow",
                "next_action": "route_to_generation",
                "target_object_ref": {"object_type": "question_set", "object_id": "quiz_old"},
                "allowed_patch": ["set_active_object"],
                "confidence": 0.96,
                "reason": "用户在当前练题流里继续要新题。",
            },
            "suspended_object_stack": [],
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["active_object"]["object_id"] != "quiz_old"
    assert result_event.metadata["suspended_object_stack"]
    assert result_event.metadata["suspended_object_stack"][0]["object_id"] == "quiz_old"


@pytest.mark.asyncio
async def test_deep_question_prefers_turn_semantic_decision_over_legacy_followup_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for followup mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Legacy question_followup_action should not override turn_semantic_decision")

    class FakeFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "这题关键看相邻专业队之间的投入间隔。"

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
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FakeFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    question_context = {
        "question_id": "q_5",
        "question": "流水步距反映的是什么？",
        "question_type": "choice",
        "options": {"A": "工期", "B": "相邻专业队投入间隔"},
        "correct_answer": "B",
        "explanation": "步距看相邻专业队之间的时间间隔。",
    }
    active_object = build_active_object_from_question_context(
        question_context,
        source_turn_id="turn-followup-priority",
    )

    context = UnifiedContext(
        user_message="为什么这题不是A",
        language="zh",
        metadata={
            "conversation_context_text": "用户正在追问题目解析。",
            "active_object": active_object or {},
            "turn_semantic_decision": {
                "relation_to_active_object": "ask_about_active_object",
                "next_action": "route_to_followup_explainer",
                "target_object_ref": {"object_type": "single_question", "object_id": "q_5"},
                "allowed_patch": ["no_state_change"],
                "confidence": 0.95,
                "reason": "当前输入是在追问当前题目。",
            },
            "question_followup_context": question_context,
            "question_followup_action": {
                "intent": "answer_questions",
                "confidence": 0.88,
                "preserve_other_answers": False,
                "answers": [{"index": 1, "question_id": "q_5", "user_answer": "A"}],
                "reason": "这是一条故意构造的旧字段冲突样例。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "followup"
    assert result_event.metadata["turn_semantic_decision"]["next_action"] == "route_to_followup_explainer"


@pytest.mark.asyncio
async def test_deep_question_primary_mode_skips_legacy_followup_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, _callback) -> None:
            return None

        def set_trace_callback(self, _callback) -> None:
            return None

        async def generate_from_topic(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "新题：流水节拍反映什么？",
                            "options": {"A": "时间", "B": "资源"},
                            "correct_answer": "A",
                            "explanation": "节拍反映单位工作队作业时间。",
                        }
                    }
                ]
            }

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("primary mode should not fall back to legacy grading parser")

    class FakeFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("primary mode should not fall back to legacy followup parser")

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
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FakeFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    question_context = {
        "question_id": "q_legacy",
        "question": "流水步距反映的是什么？",
        "question_type": "choice",
        "options": {"A": "工期", "B": "相邻专业队投入间隔"},
        "correct_answer": "B",
    }
    active_object = build_active_object_from_question_context(
        question_context,
        source_turn_id="turn-primary-no-legacy",
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        config_overrides={"mode": "custom", "topic": "流水施工", "num_questions": 1, "question_type": "choice"},
        metadata={
            "turn_id": "turn-primary-no-legacy",
            "semantic_router_mode": "primary",
            "active_object": active_object or {},
            "question_followup_context": question_context,
            "turn_semantic_decision": {},
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "custom"
    assert result_event.metadata["turn_semantic_decision"]["next_action"] == "route_to_generation"
