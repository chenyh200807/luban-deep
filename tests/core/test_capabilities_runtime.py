"""Runtime tests for built-in capabilities under the unified framework."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.chat import ChatCapability
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.capabilities.deep_research import DeepResearchCapability
from deeptutor.capabilities.deep_solve import DeepSolveCapability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import Attachment, UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> types.ModuleType:
    __import__("src")
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
    return module


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
async def test_chat_capability_streams_content_and_geogebra_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakePipeline:
        def __init__(self, language: str = "en") -> None:
            captured["pipeline_init"] = {"language": language}

        def _infer_answer_type(self, _message: str) -> str:
            return "knowledge_explainer"

        async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
            captured["process"] = {
                "message": f"{context.user_message}\nGGB commands",
                "enabled_tools": list(context.enabled_tools or []),
            }
            await stream.tool_call(
                "geogebra_analysis",
                {"image_name": "img.png"},
                source="chat",
                stage="acting",
            )
            await stream.sources(
                [
                    {"type": "rag", "kb_name": "demo-kb", "content": "grounding"},
                    {"type": "web", "url": "https://example.com", "title": "Example"},
                ],
                source="chat",
                stage="responding",
            )
            await stream.content("assistant output", source="chat", stage="responding")

    monkeypatch.setattr("deeptutor.capabilities.chat.AgenticChatPipeline", FakePipeline)

    context = UnifiedContext(
        user_message="analyze triangle",
        enabled_tools=["rag", "web_search", "geogebra_analysis"],
        knowledge_bases=["demo-kb"],
        language="en",
        attachments=[Attachment(type="image", base64="ZmFrZQ==", filename="img.png")],
    )

    capability = ChatCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert any(event.type == StreamEventType.TOOL_CALL for event in events)
    assert any(event.type == StreamEventType.SOURCES for event in events)
    assert any(event.type == StreamEventType.CONTENT and "assistant output" in event.content for event in events)
    assert "GGB commands" in captured["process"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled_tools", "knowledge_bases", "expected_tools", "expected_kb", "expected_disable"),
    [
        (["rag", "code_execution"], ["algebra"], ["rag", "code_execution"], "algebra", False),
        (None, ["algebra"], list(DeepSolveCapability.manifest.tools_used), "algebra", False),
        ([], ["algebra"], [], None, True),
    ],
)
async def test_deep_solve_capability_bridges_solver_output(
    monkeypatch: pytest.MonkeyPatch,
    enabled_tools: list[str] | None,
    knowledge_bases: list[str],
    expected_tools: list[str],
    expected_kb: str | None,
    expected_disable: bool,
) -> None:
    captured: dict[str, Any] = {}

    class FakeMainSolver:
        def __init__(self, **kwargs: Any) -> None:
            captured["solver_init"] = kwargs
            self.logger = SimpleNamespace(
                logger=SimpleNamespace(addHandler=lambda *_: None, removeHandler=lambda *_: None)
            )

        async def ainit(self) -> None:
            captured["ainit"] = True

        async def solve(self, **kwargs: Any) -> dict[str, Any]:
            self._send_progress_update("reasoning", {"status": "solver-progress"})
            captured["solve"] = kwargs
            return {
                "final_answer": "final solution",
                "output_dir": "/tmp/solve",
                "metadata": {"steps": 2},
            }

    _install_module(monkeypatch, "deeptutor.agents.solve.main_solver", MainSolver=FakeMainSolver)
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="solve x^2=4",
        enabled_tools=enabled_tools,
        knowledge_bases=knowledge_bases,
        language="en",
    )
    capability = DeepSolveCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["solver_init"]["enabled_tools"] == expected_tools
    assert captured["solver_init"]["kb_name"] == expected_kb
    assert captured["solver_init"]["disable_planner_retrieve"] is expected_disable
    assert any(event.type == StreamEventType.PROGRESS and event.content == "solver-progress" for event in events)
    assert any(event.type == StreamEventType.CONTENT and "final solution" in event.content for event in events)
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["response"] == "final solution"


@pytest.mark.asyncio
async def test_deep_solve_capability_bridges_observation_and_retrieve_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMainSolver:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None
            self.logger = SimpleNamespace(
                logger=SimpleNamespace(addHandler=lambda *_: None, removeHandler=lambda *_: None)
            )

        async def ainit(self) -> None:
            return None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def solve(self, **_kwargs: Any) -> dict[str, Any]:
            assert self._trace_callback is not None
            await self._trace_callback(
                {
                    "event": "llm_observation",
                    "phase": "reasoning",
                    "response": "round summary",
                    "call_id": "solve-s1-round-1",
                    "trace_role": "observe",
                    "trace_group": "react_round",
                }
            )
            await self._trace_callback(
                {
                    "event": "tool_log",
                    "phase": "reasoning",
                    "message": "Retrieving from KB...",
                    "call_id": "solve-retrieve-1",
                    "call_kind": "rag_retrieval",
                    "trace_role": "retrieve",
                    "trace_group": "retrieve",
                    "trace_kind": "status",
                }
            )
            return {
                "final_answer": "final solution",
                "output_dir": "/tmp/solve",
                "metadata": {"steps": 1},
            }

    _install_module(monkeypatch, "deeptutor.agents.solve.main_solver", MainSolver=FakeMainSolver)
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="solve x^2=4",
        enabled_tools=["rag"],
        knowledge_bases=["algebra"],
        language="en",
    )
    capability = DeepSolveCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    observation_event = next(event for event in events if event.type == StreamEventType.OBSERVATION)
    assert observation_event.content == "round summary"
    assert observation_event.metadata["trace_role"] == "observe"

    retrieve_event = next(
        event
        for event in events
        if event.type == StreamEventType.PROGRESS and event.metadata.get("trace_role") == "retrieve"
    )
    assert retrieve_event.content == "Retrieving from KB..."
    assert retrieve_event.metadata["trace_group"] == "retrieve"


@pytest.mark.asyncio
async def test_deep_question_capability_uses_user_message_as_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            await self._callback({"type": "idea_round", "message": "ideas"})
            await self._callback({"type": "generating", "message": "writing"})
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "What is a matrix?",
                            "options": {"A": "A table", "B": "A scalar"},
                            "correct_answer": "A",
                            "explanation": "A matrix is a table.",
                        }
                    }
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

    context = UnifiedContext(
        user_message="linear algebra fundamentals",
        config_overrides={},
        language="en",
    )
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["topic_call"]["user_topic"] == "linear algebra fundamentals"
    assert any(event.type == StreamEventType.PROGRESS and event.stage == "ideation" for event in events)
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "Question 1" in result_event.metadata["response"]


@pytest.mark.asyncio
async def test_deep_question_capability_anchors_deictic_generation_topic_to_open_chat_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "流水步距反映什么？",
                            "options": {"A": "工期", "B": "相邻专业队投入间隔"},
                            "correct_answer": "B",
                            "explanation": "步距看相邻专业队之间的时间间隔。",
                        }
                    }
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

    context = UnifiedContext(
        user_message="好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
        config_overrides={
            "topic": "好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
            "num_questions": 2,
            "question_type": "choice",
            "force_generate_questions": True,
        },
        language="zh",
        metadata={
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "session-1",
                "scope": {"domain": "session", "session_id": "session-1", "source": "wx"},
                "state_snapshot": {
                    "session_id": "session-1",
                    "title": "流水施工基本概念",
                    "compressed_summary": "用户刚刚在讨论流水节拍、流水步距和施工段的区别。",
                    "source": "wx",
                    "status": "idle",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-1",
            },
            "conversation_context_text": "最近一直在讲流水节拍、流水步距和施工段。",
        },
    )
    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    resolved_topic = captured["topic_call"]["user_topic"]
    assert "只考刚才这几个概念" in resolved_topic
    assert "流水节拍" in resolved_topic
    assert "如果锚点里没有出现某个新概念" in resolved_topic


@pytest.mark.asyncio
async def test_deep_question_capability_does_not_leak_old_open_chat_anchor_into_explicit_new_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "模板工程单选题",
                            "options": {"A": "A", "B": "B"},
                            "correct_answer": "A",
                            "explanation": "解析。",
                        }
                    }
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

    explicit_topic = "给我出一道模板工程的选择题"
    context = UnifiedContext(
        user_message=explicit_topic,
        config_overrides={"topic": explicit_topic, "question_type": "choice"},
        language="zh",
        metadata={
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "session-1",
                "scope": {"domain": "session", "session_id": "session-1", "source": "wx"},
                "state_snapshot": {
                    "session_id": "session-1",
                    "title": "流水施工基本概念",
                    "compressed_summary": "用户刚刚在讨论流水节拍、流水步距和施工段的区别。",
                    "source": "wx",
                    "status": "idle",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-1",
            },
            "conversation_context_text": "最近一直在讲流水节拍、流水步距和施工段。",
        },
    )
    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["topic_call"]["user_topic"] == explicit_topic


@pytest.mark.asyncio
async def test_deep_question_capability_prefers_broader_anchor_over_current_question_for_concept_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question": "流水步距题",
                            "options": {"A": "A", "B": "B"},
                            "correct_answer": "A",
                            "explanation": "解析。",
                        }
                    }
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

    context = UnifiedContext(
        user_message="好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
        config_overrides={
            "topic": "好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
            "num_questions": 2,
            "question_type": "choice",
            "force_generate_questions": True,
        },
        language="zh",
        metadata={
            "active_object": {
                "object_type": "single_question",
                "object_id": "quiz-check-1",
                "scope": {"domain": "question"},
                "state_snapshot": {
                    "question_id": "quiz-check-1",
                    "question": "木工和钢筋工的流水步距是几天？",
                    "question_type": "choice",
                    "options": {"A": "2天", "B": "3天"},
                    "correct_answer": "B",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-check",
            },
            "question_followup_context": {
                "question_id": "quiz-check-1",
                "question": "木工和钢筋工的流水步距是几天？",
                "question_type": "choice",
                "options": {"A": "2天", "B": "3天"},
                "correct_answer": "B",
            },
            "suspended_object_stack": [
                {
                    "object_type": "open_chat_topic",
                    "object_id": "session-1",
                    "scope": {"domain": "session", "session_id": "session-1", "source": "wx"},
                    "state_snapshot": {
                        "session_id": "session-1",
                        "title": "流水施工基本概念",
                        "compressed_summary": "用户刚刚在讨论流水节拍、流水步距和施工段的区别。",
                        "source": "wx",
                        "status": "idle",
                    },
                    "version": 1,
                    "entered_at": "",
                    "last_touched_at": "",
                    "source_turn_id": "turn-open-chat",
                }
            ],
            "conversation_context_text": "最近一直在讲流水节拍、流水步距和施工段。",
        },
    )
    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    resolved_topic = captured["topic_call"]["user_topic"]
    assert "流水节拍" in resolved_topic
    assert "施工段" in resolved_topic
    assert "当前题目内容：木工和钢筋工的流水步距是几天" not in resolved_topic


@pytest.mark.asyncio
async def test_deep_question_capability_uses_followup_anchor_fast_generation_for_small_practice_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("generate_from_topic should not be used for anchored continuation")

        async def generate_from_followup_context(self, **kwargs: Any) -> dict[str, Any]:
            captured["followup_call"] = kwargs
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question_id": "q_1",
                            "question": "流水节拍题 1",
                            "question_type": "choice",
                            "options": {"A": "A", "B": "B"},
                            "correct_answer": "A",
                            "explanation": "解析 1",
                            "concentration": "流水节拍",
                        }
                    },
                    {
                        "qa_pair": {
                            "question_id": "q_2",
                            "question": "流水步距题 2",
                            "question_type": "choice",
                            "options": {"A": "A", "B": "B"},
                            "correct_answer": "B",
                            "explanation": "解析 2",
                            "concentration": "流水步距",
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

    context = UnifiedContext(
        user_message="好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
        config_overrides={
            "topic": "好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
            "num_questions": 2,
            "question_type": "choice",
            "force_generate_questions": True,
        },
        language="zh",
        metadata={
            "selected_mode": "fast",
            "question_followup_context": {
                "question_id": "set_1",
                "question": "上一轮练习",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_prev_1",
                        "question": "流水节拍反映什么？",
                        "question_type": "choice",
                        "options": {"A": "A", "B": "B"},
                        "correct_answer": "A",
                        "explanation": "节拍反映本专业队在一个施工段上的持续时间。",
                        "concentration": "流水节拍",
                        "difficulty": "easy",
                        "knowledge_context": "上一轮重点 1",
                    },
                    {
                        "question_id": "q_prev_2",
                        "question": "流水步距反映什么？",
                        "question_type": "choice",
                        "options": {"A": "A", "B": "B"},
                        "correct_answer": "B",
                        "explanation": "步距反映相邻专业队投入间隔。",
                        "concentration": "流水步距",
                        "difficulty": "easy",
                        "knowledge_context": "上一轮重点 2",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["followup_call"]["num_questions"] == 2
    assert captured["followup_call"]["question_type"] == "choice"
    assert captured["followup_call"]["lightweight_generation"] is True
    assert captured["init"]["tool_flags_override"] == {
        "rag": False,
        "web_search": False,
        "code_execution": False,
    }
    assert len(captured["followup_call"]["followup_question_context"]["items"]) == 2
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "custom"
    assert result_event.metadata["question_followup_context"]["items"][0]["question"] == "流水节拍题 1"


@pytest.mark.asyncio
async def test_deep_question_capability_uses_lightweight_topic_generation_for_fast_open_chat_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_followup_context(self, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("followup generation should not be used without question followup context")

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question_id": "q_1",
                            "question": "流水节拍题 1",
                            "question_type": "choice",
                            "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                            "correct_answer": "A",
                            "explanation": "",
                            "concentration": "流水节拍",
                        }
                    },
                    {
                        "qa_pair": {
                            "question_id": "q_2",
                            "question": "流水步距题 2",
                            "question_type": "choice",
                            "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                            "correct_answer": "B",
                            "explanation": "",
                            "concentration": "流水步距",
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

    context = UnifiedContext(
        user_message="好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
        config_overrides={
            "topic": "好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
            "num_questions": 2,
            "question_type": "choice",
            "force_generate_questions": True,
        },
        language="zh",
        metadata={
            "selected_mode": "fast",
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "session-1",
                "scope": {"domain": "session", "session_id": "session-1", "source": "wx"},
                "state_snapshot": {
                    "session_id": "session-1",
                    "title": "流水施工基本概念",
                    "compressed_summary": "用户刚刚在讨论流水节拍、流水步距和施工段的区别。",
                    "source": "wx",
                    "status": "idle",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-open-chat",
            },
            "conversation_context_text": "最近一直在讲流水节拍、流水步距和施工段。",
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["topic_call"]["lightweight_generation"] is True
    assert captured["topic_call"]["require_explanation"] is False
    assert "如果锚点里没有出现某个新概念" in captured["topic_call"]["user_topic"]
    assert captured["init"]["tool_flags_override"] == {
        "rag": False,
        "web_search": False,
        "code_execution": False,
    }
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert len(result_event.metadata["question_followup_context"]["items"]) == 2


@pytest.mark.asyncio
async def test_deep_question_capability_uses_single_call_followup_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FakeFollowupAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **kwargs: Any) -> str:
            captured["process"] = kwargs
            assert self._trace_callback is not None
            await self._trace_callback(
                {
                    "event": "llm_call",
                    "state": "running",
                    "label": "Answer follow-up for Question 3",
                    "phase": "generation",
                    "call_id": "quiz-followup-q_3",
                }
            )
            await self._trace_callback(
                {
                    "event": "llm_call",
                    "state": "complete",
                    "response": "You missed the key distinction between density and coverage.",
                    "phase": "generation",
                    "call_id": "quiz-followup-q_3",
                }
            )
            return "You missed the key distinction between density and coverage."

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
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

    context = UnifiedContext(
        user_message="Why was my answer wrong?",
        language="en",
        metadata={
            "conversation_context_text": "User previously asked for a simpler explanation.",
            "question_followup_context": {
                "question_id": "q_3",
                "question": "What does density mean in win-rate comparison?",
                "question_type": "written",
                "user_answer": "coverage",
                "correct_answer": "relevant information without redundancy",
                "is_correct": False,
                "explanation": "Density is about relevant content without redundancy.",
            },
        },
    )
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["process"]["user_message"] == "Why was my answer wrong?"
    assert (
        captured["process"]["history_context"]
        == "User previously asked for a simpler explanation."
    )
    assert (
        captured["process"]["question_context"]["question_id"] == "q_3"
    )
    assert any(
        event.type == StreamEventType.CONTENT
        and "key distinction between density and coverage" in event.content
        for event in events
    )
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "followup"
    assert result_event.metadata["question_id"] == "q_3"


@pytest.mark.asyncio
async def test_tutorbot_capability_bridges_tutorbot_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUTORBOT_STREAM_PUBLIC_DELTAS", "0")
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None):
            captured["ensure"] = {"bot_id": bot_id, "config": config}
            return SimpleNamespace(running=True)

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            captured["session_key_args"] = (bot_id, conversation_id, user_id)
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["send"] = {
                "bot_id": bot_id,
                "content": content,
                "chat_id": chat_id,
                "mode": mode,
                "session_key": session_key,
                "session_metadata": session_metadata,
            }
            if on_progress is not None:
                await on_progress("thinking...")
            if on_tool_call is not None:
                await on_tool_call("rag", {"query": "你好", "kb_name": "construction-exam"})
            if on_tool_result is not None:
                await on_tool_result(
                    "rag",
                    "知识库命中",
                    {
                        "sources": [{"chunk_id": "q-1", "source_type": "real_exam"}],
                        "authority_applied": True,
                    },
                )
            if on_content_delta is not None:
                await on_content_delta("Tutor")
                await on_content_delta("Bot")
            return "TutorBot"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-1",
        user_message="什么是流水节拍，简单说一下",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={
            "billing_context": {"user_id": "u1", "source": "wx_miniprogram"},
            "interaction_hints": {},
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "session-1",
                "state_snapshot": {
                    "title": "流水施工入门",
                    "compressed_summary": "用户一直在用6层住宅楼的例子理解流水节拍和施工段。",
                },
            },
            "conversation_context_text": "最近一直在沿用6层住宅楼这个案例。",
        },
        language="zh",
    )

    capability = TutorBotCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["ensure"]["bot_id"] == "construction-exam-coach"
    assert captured["send"]["bot_id"] == "construction-exam-coach"
    assert captured["send"]["chat_id"] == "session-1"
    assert captured["send"]["mode"] == "fast"
    assert captured["send"]["session_metadata"]["user_id"] == "u1"
    assert captured["send"]["session_metadata"]["default_tools"] == ["rag"]
    assert captured["send"]["session_metadata"]["knowledge_bases"] == ["construction-exam"]
    assert captured["send"]["session_metadata"]["default_kb"] == "construction-exam"
    assert captured["send"]["session_metadata"]["suppress_answer_reveal_on_generate"] is True
    assert captured["send"]["session_metadata"]["requested_response_mode"] == "smart"
    assert captured["send"]["session_metadata"]["selected_mode"] == "fast"
    assert captured["send"]["session_metadata"]["effective_response_mode"] == "fast"
    assert "construction-knowledge" in captured["send"]["session_metadata"]["kb_aliases"]
    assert "construction-exam-tutor" in captured["send"]["session_metadata"]["kb_aliases"]
    assert captured["send"]["session_metadata"]["active_object"]["object_type"] == "open_chat_topic"
    assert "6层住宅楼" in captured["send"]["session_metadata"]["conversation_context_text"]
    assert any(event.type == StreamEventType.PROGRESS for event in events)
    assert any(event.type == StreamEventType.TOOL_CALL and event.content == "rag" for event in events)
    assert any(event.type == StreamEventType.TOOL_RESULT and "知识库命中" in event.content for event in events)
    assert any(event.type == StreamEventType.SOURCES and event.metadata["sources"][0]["chunk_id"] == "q-1" for event in events)
    content_events = [event for event in events if event.type == StreamEventType.CONTENT]
    assert [event.content for event in content_events] == ["TutorBot"]
    assert all(event.metadata["call_kind"] == "llm_final_response" for event in content_events)
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["response"] == "TutorBot"
    assert result_event.metadata["execution_engine"] == "tutorbot_runtime"
    assert result_event.metadata["selected_mode"] == "fast"
    assert result_event.metadata["execution_path"] == "tutorbot_fast_policy"


@pytest.mark.asyncio
async def test_tutorbot_capability_prefers_canonical_chat_mode_over_legacy_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None):
            return SimpleNamespace(running=True)

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["mode"] = mode
            captured["session_metadata"] = session_metadata
            return "Fast TutorBot"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-authority",
        user_message="简短解释流水节拍",
        enabled_tools=["rag", "web_search"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        metadata={
            "interaction_hints": {
                "requested_response_mode": "deep",
                "teaching_mode": "deep",
            }
        },
        language="zh",
    )

    capability = TutorBotCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["mode"] == "fast"
    assert captured["session_metadata"]["requested_response_mode"] == "fast"
    assert captured["session_metadata"]["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_tutorbot_capability_fast_mode_does_not_set_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None):
            return SimpleNamespace(running=True)

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["mode"] = mode
            captured["session_metadata"] = session_metadata
            return "Fast TutorBot"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-fast-model",
        user_message="简短解释流水节拍",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        metadata={"billing_context": {"user_id": "u1", "source": "wx_miniprogram"}},
        language="zh",
    )

    capability = TutorBotCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["mode"] == "fast"
    assert "preferred_model" not in captured["session_metadata"]


@pytest.mark.asyncio
async def test_tutorbot_capability_streams_intermediate_deltas_without_duplicate_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUTORBOT_STREAM_PUBLIC_DELTAS", "1")

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None):
            return SimpleNamespace(running=True)

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            if on_content_delta is not None:
                await on_content_delta("最终答案：")
                await on_content_delta("防水等级是设计标准，设防层数是施工构造。")
            return "最终答案：防水等级是设计标准，设防层数是施工构造。"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-2",
        user_message="防水等级和设防层数有什么区别？",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={"billing_context": {"user_id": "u1", "source": "wx_miniprogram"}},
        language="zh",
    )

    capability = TutorBotCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    content_events = [event for event in events if event.type == StreamEventType.CONTENT]
    assert [event.content for event in content_events] == [
        "最终答案：",
        "防水等级是设计标准，设防层数是施工构造。",
    ]
    assert all(event.metadata["call_kind"] == "llm_stream_delta" for event in content_events)
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["response"] == "最终答案：防水等级是设计标准，设防层数是施工构造。"


def test_tutorbot_stream_public_deltas_enabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TUTORBOT_STREAM_PUBLIC_DELTAS", raising=False)

    from deeptutor.capabilities.tutorbot import _stream_public_deltas_enabled

    assert _stream_public_deltas_enabled() is True


@pytest.mark.asyncio
async def test_tutorbot_capability_emits_structured_mcq_summary_for_plain_text_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            return "\n".join(
                [
                    "下面给你两道题。",
                    "",
                    "题目一：建筑构造",
                    "防火门构造的基本要求有（ ）。",
                    "A. 甲级防火门耐火极限为 1.5h",
                    "B. 向内开启",
                    "C. 关闭后应能从内外两侧手动开启",
                    "D. 具有自行关闭功能",
                    "E. 开启后，门扇不应跨越变形缝",
                    "",
                    "题目二：屋面工程",
                    "倒置式屋面保温层应设置在（ ）。",
                    "A. 找平层下",
                    "B. 防水层上",
                    "C. 结构层上",
                    "D. 保护层下",
                ]
            )

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-1",
        user_message="我想练习建筑构造相关的题目",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={"billing_context": {"user_id": "u1", "source": "wx_miniprogram"}},
        language="zh",
    )

    capability = TutorBotCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    presentation = result_event.metadata.get("presentation")
    assert isinstance(presentation, dict)
    assert len(presentation["blocks"][0]["questions"]) == 2
    assert presentation["blocks"][0]["questions"][0]["question_type"] == "multi_choice"
    followup_context = result_event.metadata.get("question_followup_context")
    assert isinstance(followup_context, dict)
    assert len(followup_context["items"]) == 2


@pytest.mark.parametrize("chat_mode", ["fast", "deep"])
@pytest.mark.asyncio
async def test_tutorbot_capability_hides_answers_for_practice_generation_in_visible_response(
    monkeypatch: pytest.MonkeyPatch,
    chat_mode: str,
) -> None:
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["mode"] = mode
            captured["session_metadata"] = session_metadata
            return "\n".join(
                [
                    "**题目**：关于混凝土养护开始时间，下列哪项说法是正确的？",
                    "A. 混凝土应在初凝前开始养护",
                    "B. 混凝土应在终凝后开始养护",
                    "C. 混凝土应在终凝前开始养护",
                    "D. 混凝土应在浇筑后立即开始养护",
                    "",
                    "**答案**：C",
                    "",
                    "**踩分点**",
                    "- 正确选项是“终凝前开始养护”。",
                ]
            )

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-practice-1",
        user_message="给我一道题测试一下这个知识点",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": chat_mode},
        metadata={
            "billing_context": {"user_id": "u1", "source": "wx_miniprogram"},
            "interaction_hints": {"suppress_answer_reveal_on_generate": True},
        },
        language="zh",
    )

    capability = TutorBotCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    content_event = next(event for event in events if event.type == StreamEventType.CONTENT)
    assert "关于混凝土养护开始时间" in content_event.content
    assert "A. 混凝土应在初凝前开始养护" in content_event.content
    assert "答案" not in content_event.content
    assert "踩分点" not in content_event.content

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert captured["mode"] == chat_mode
    assert captured["session_metadata"]["default_tools"] == ["rag"]
    assert "答案" not in result_event.metadata["response"]
    assert "踩分点" not in result_event.metadata["response"]
    assert result_event.metadata["question_followup_context"]["correct_answer"] == "C"
    assert isinstance(result_event.metadata.get("presentation"), dict)


@pytest.mark.asyncio
async def test_tutorbot_capability_keeps_fast_mode_for_question_set_practice_generation_under_smart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["mode"] = mode
            captured["session_metadata"] = session_metadata
            return "### Question 1\n\n流水节拍题"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-practice-fast",
        user_message="好，那你现在给我出2道很简单的选择题，只考刚才这几个概念，不要超纲。",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={
            "active_object": {
                "object_type": "question_set",
                "object_id": "set_1",
                "scope": {"domain": "question"},
                "state_snapshot": {"question_id": "set_1"},
            },
            "question_followup_context": {
                "question_id": "set_1",
                "question": "上一轮练习",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_prev_1",
                        "question": "流水节拍反映什么？",
                        "question_type": "choice",
                        "correct_answer": "A",
                    }
                ],
            },
            "interaction_hints": {"suppress_answer_reveal_on_generate": True},
        },
        language="zh",
    )

    capability = TutorBotCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["mode"] == "fast"
    assert captured["session_metadata"]["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_tutorbot_capability_keeps_fast_mode_for_question_set_submission_under_smart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            captured["mode"] = mode
            captured["session_metadata"] = session_metadata
            return "第1题错，第2题对。"

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-grade-fast",
        user_message="我答一下：第1题选B，第2题选C。你帮我批改，并且针对我错的地方解释一下。",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={
            "active_object": {
                "object_type": "question_set",
                "object_id": "set_1",
                "scope": {"domain": "question"},
                "state_snapshot": {"question_id": "set_1"},
            },
            "question_followup_context": {
                "question_id": "set_1",
                "question": "上一轮练习",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_prev_1",
                        "question": "流水节拍反映什么？",
                        "question_type": "choice",
                        "options": {"A": "工序时间", "B": "开工间隔"},
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_prev_2",
                        "question": "施工段是什么？",
                        "question_type": "choice",
                        "options": {"A": "空间划分", "B": "时间参数"},
                        "correct_answer": "A",
                    },
                ],
            },
        },
        language="zh",
    )

    capability = TutorBotCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["mode"] == "fast"
    assert captured["session_metadata"]["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_tutorbot_capability_hides_case_reference_sections_when_user_explicitly_suppresses_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(
            self,
            *,
            bot_id: str,
            content: str,
            chat_id: str = "web",
            on_progress=None,
            on_content_delta=None,
            on_tool_call=None,
            on_tool_result=None,
            mode: str = "smart",
            session_key: str | None = None,
            session_metadata: dict[str, Any] | None = None,
        ) -> str:
            return "\n".join(
                [
                    "【背景资料】某主体结构施工项目正在进行模板拆除。",
                    "",
                    "【问题】",
                    "1. 请说明侧模与底模的拆除判断依据。",
                    "2. 请写出作答要求与评分点提醒。",
                    "",
                    "Answer: 侧模看棱角不受损，底模按跨度和强度百分比控制。",
                    "",
                    "Explanation: 重点抓 1.0MPa、板二八、梁八悬一百。",
                ]
            )

    monkeypatch.setattr(
        "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
        lambda: FakeManager(),
    )

    context = UnifiedContext(
        session_id="session-case-practice",
        user_message="按模板拆除给我出一道案例题，先不要直接给答案，先给作答要求和评分点提醒。",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
        metadata={"billing_context": {"user_id": "u1", "source": "ws"}},
        language="zh",
    )

    capability = TutorBotCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    content_event = next(event for event in events if event.type == StreamEventType.CONTENT)
    assert "【问题】" in content_event.content
    assert "Answer:" not in content_event.content
    assert "Explanation:" not in content_event.content

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "Answer:" not in result_event.metadata["response"]
    assert "Explanation:" not in result_event.metadata["response"]


@pytest.mark.asyncio
async def test_rag_adapter_tool_uses_runtime_default_kb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")

    async def _fake_rag_search(*, query: str, kb_name: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        captured["query"] = query
        captured["kb_name"] = kb_name
        return {"answer": "ok"}

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "knowledge_bases": ["construction-exam"],
        }
    )

    result = await tool.execute(query="防水等级")

    assert result == "ok"
    assert captured["query"] == "防水等级"
    assert captured["kb_name"] == "construction-exam"


@pytest.mark.asyncio
async def test_rag_adapter_tool_normalizes_legacy_kb_alias_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")

    async def _fake_rag_search(*, query: str, kb_name: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        captured["query"] = query
        captured["kb_name"] = kb_name
        return {"answer": "ok"}

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "kb_aliases": ["construction-knowledge", "construction-exam-coach", "construction-exam-tutor"],
        }
    )

    result = await tool.execute(query="防水等级", kb_name="construction-knowledge")

    assert result == "ok"
    assert captured["query"] == "防水等级"
    assert captured["kb_name"] == "construction-exam"


@pytest.mark.asyncio
async def test_rag_adapter_tool_normalizes_legacy_tutor_alias_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")

    async def _fake_rag_search(*, query: str, kb_name: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        captured["query"] = query
        captured["kb_name"] = kb_name
        return {"answer": "ok"}

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "kb_aliases": ["construction-exam-tutor", "construction_exam_tutor"],
        }
    )

    result = await tool.execute(query="防水等级", kb_name="construction-exam-tutor")

    assert result == "ok"
    assert captured["query"] == "防水等级"
    assert captured["kb_name"] == "construction-exam"


def test_rag_adapter_tool_preview_args_normalizes_alias() -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sys.modules.setdefault("loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "kb_aliases": ["construction-exam-tutor", "construction_exam_tutor"],
        }
    )

    preview = tool.preview_args(
        {
            "query": "防水等级和设防层数有什么区别",
            "kb_name": "construction-exam-tutor",
            "mode": "hybrid",
        }
    )

    assert preview["kb_name"] == "construction-exam"


@pytest.mark.asyncio
async def test_rag_adapter_tool_coerces_none_answer_to_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")

    async def _fake_rag_search(*, query: str, kb_name: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        assert query == "防水等级"
        assert kb_name == "construction-exam"
        return {
            "answer": None,
            "content": None,
            "sources": [{"chunk_id": "c1", "source_type": "standard"}],
        }

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(metadata={"default_kb": "construction-exam"})

    result = await tool.execute(query="防水等级")

    assert result == ""
    assert tool.consume_trace_metadata() == {
        "kb_name": "construction-exam",
        "sources": [{"chunk_id": "c1", "source_type": "standard"}],
        "tool_source_count": 1,
        "exact_question": {},
        "authority_applied": False,
    }


@pytest.mark.asyncio
async def test_rag_adapter_tool_emits_only_evidence_bundle_summary_in_trace_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")

    async def _fake_rag_search(*, query: str, kb_name: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        assert query == "防水等级"
        assert kb_name == "construction-exam"
        return {
            "answer": "答案",
            "content": "答案",
            "sources": [{"chunk_id": "c1", "source_type": "standard"}],
            "evidence_bundle": {
                "bundle_id": "bundle-1",
                "kb_name": "construction-exam",
                "provider": "supabase",
                "query_shape": "concept_like",
                "retrieval_empty": False,
                "content_blocks": ["A", "B"],
                "sources": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
                "exact_question": {},
            },
        }

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(metadata={"default_kb": "construction-exam"})

    result = await tool.execute(query="防水等级")

    assert result == "答案"
    metadata = tool.consume_trace_metadata()
    assert metadata["evidence_bundle_summary"] == {
        "bundle_id": "bundle-1",
        "kb_name": "construction-exam",
        "provider": "supabase",
        "query_shape": "concept_like",
        "retrieval_empty": False,
        "source_count": 2,
        "content_block_count": 2,
        "exact_question": False,
    }
    assert "evidence_bundle" not in metadata


@pytest.mark.asyncio
async def test_rag_adapter_tool_does_not_forward_stale_question_type_without_question_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")
    captured: dict[str, Any] = {}

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"answer": "ok", "content": "ok", "sources": []}

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "question_type": "single_choice",
        }
    )

    await tool.execute(query="防水等级")

    assert captured["query"] == "防水等级"
    assert "question_type" not in captured


@pytest.mark.asyncio
async def test_rag_adapter_tool_forwards_question_type_only_for_question_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")
    captured: dict[str, Any] = {}

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"answer": "ok", "content": "ok", "sources": []}

    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "intent": "answer_questions",
            "question_type": "single_choice",
            "question_followup_context": {"question_id": "q1"},
        }
    )

    await tool.execute(query="第1题我改成C")

    assert captured["question_type"] == "single_choice"


@pytest.mark.asyncio
async def test_tutorbot_tool_registry_coerces_none_result_to_empty_string() -> None:
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry

    class NullTool(Tool):
        @property
        def name(self) -> str:
            return "null_tool"

        @property
        def description(self) -> str:
            return "returns none"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            }

        async def execute(self, **kwargs: Any) -> None:
            return None

    registry = TutorBotToolRegistry()
    registry.register(NullTool())

    result = await registry.execute("null_tool", {"topic": "x"})

    assert result == ""


async def _capture_async(bucket: list[Any], value: Any) -> None:
    bucket.append(value)


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_executes_tool_calls_with_registry_get(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict[str, Any] = {"tool_calls": [], "tool_results": []}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class FakeProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="先查一下工具",
                    tool_calls=[
                        ToolCallRequest(
                            id="call_1",
                            name="dummy_tool",
                            arguments={"topic": "alias-value"},
                        )
                    ],
                )
            return LLMResponse(content="工具已经执行完成")

        def get_default_model(self) -> str:
            return "fake-model"

    class DummyTool(Tool):
        def __init__(self) -> None:
            self._trace_metadata = {
                "sources": [{"chunk_id": "chunk-1", "source_type": "standard"}],
                "authority_applied": False,
            }

        @property
        def name(self) -> str:
            return "dummy_tool"

        @property
        def description(self) -> str:
            return "dummy tool"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            }

        def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
            return {"topic": "normalized-topic"}

        async def execute(self, **kwargs: Any) -> str:
            return f"executed:{kwargs['topic']}"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            metadata = dict(self._trace_metadata)
            self._trace_metadata = {}
            return metadata

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(DummyTool())

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "帮我查一下"}],
        on_tool_call=lambda name, args: _capture_async(captured["tool_calls"], (name, args)),
        on_tool_result=lambda name, result, metadata: _capture_async(
            captured["tool_results"], (name, result, metadata)
        ),
    )

    assert final_content == "工具已经执行完成"
    assert tools_used == ["dummy_tool"]
    assert captured["tool_calls"] == [("dummy_tool", {"topic": "normalized-topic"})]
    assert captured["tool_results"] == [
        (
            "dummy_tool",
            "executed:alias-value",
            {
                "sources": [{"chunk_id": "chunk-1", "source_type": "standard"}],
                "authority_applied": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_records_rag_round_query_and_source_overlap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict[str, Any] = {"tool_results": []}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class FakeProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="先查第一轮",
                    tool_calls=[
                        ToolCallRequest(
                            id="call_1",
                            name="rag",
                            arguments={"query": "construction exam definition", "kb_name": "construction-exam"},
                        )
                    ],
                )
            if self.calls == 2:
                return LLMResponse(
                    content="再查第二轮",
                    tool_calls=[
                        ToolCallRequest(
                            id="call_2",
                            name="rag",
                            arguments={"query": "construction definition", "kb_name": "construction-exam"},
                        )
                    ],
                )
            return LLMResponse(content="最终回答")

        def get_default_model(self) -> str:
            return "fake-model"

    class MultiRoundRagTool(Tool):
        def __init__(self) -> None:
            self._execute_count = 0

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kb_name": {"type": "string"}},
                "required": ["query"],
            }

        def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
            return dict(params)

        async def execute(self, **kwargs: Any) -> str:
            self._execute_count += 1
            return f"round-{self._execute_count}:{kwargs['query']}"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            if self._execute_count == 1:
                return {
                    "kb_name": "construction-exam",
                    "sources": [
                        {"chunk_id": "chunk-1", "source_type": "standard"},
                        {"chunk_id": "chunk-2", "source_type": "standard"},
                    ],
                }
            return {
                "kb_name": "construction-exam",
                "sources": [
                    {"chunk_id": "chunk-2", "source_type": "standard"},
                    {"chunk_id": "chunk-3", "source_type": "standard"},
                ],
            }

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(MultiRoundRagTool())

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "帮我解释建筑构造"}],
        on_tool_result=lambda name, result, metadata: _capture_async(
            captured["tool_results"], (name, result, metadata)
        ),
    )

    assert final_content == "最终回答"
    assert tools_used == ["rag", "rag"]
    first_metadata = captured["tool_results"][0][2]
    second_metadata = captured["tool_results"][1][2]

    assert first_metadata["rag_round"] == {
        "round_index": 1,
        "query": "construction exam definition",
        "kb_name": "construction-exam",
        "source_count": 2,
        "sources": [
            {"chunk_id": "chunk-1", "source_type": "standard"},
            {"chunk_id": "chunk-2", "source_type": "standard"},
        ],
        "query_similarity_to_prev": None,
        "source_overlap_to_prev": None,
        "shared_source_count_with_prev": 0,
    }
    assert first_metadata["rag_round_count"] == 1
    assert first_metadata["rag_rounds"] == [first_metadata["rag_round"]]

    assert second_metadata["rag_round"] == {
        "round_index": 2,
        "query": "construction definition",
        "kb_name": "construction-exam",
        "source_count": 2,
        "sources": [
            {"chunk_id": "chunk-2", "source_type": "standard"},
            {"chunk_id": "chunk-3", "source_type": "standard"},
        ],
        "query_similarity_to_prev": 0.6667,
        "source_overlap_to_prev": 0.3333,
        "shared_source_count_with_prev": 1,
    }
    assert second_metadata["rag_round_count"] == 2
    assert second_metadata["rag_rounds"] == [
        first_metadata["rag_round"],
        second_metadata["rag_round"],
    ]


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_disables_further_rag_after_high_overlap_saturation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict[str, Any] = {"tool_results": [], "tool_name_sets": []}

    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class FakeProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            tool_names = [
                str(item.get("function", {}).get("name") or "")
                for item in list(tools or [])
            ]
            captured["tool_name_sets"].append(tool_names)
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="先查第一轮",
                    tool_calls=[
                        ToolCallRequest(
                            id="call_1",
                            name="rag",
                            arguments={"query": "construction exam definition", "kb_name": "construction-exam"},
                        )
                    ],
                )
            if self.calls == 2:
                return LLMResponse(
                    content="再查第二轮",
                    tool_calls=[
                        ToolCallRequest(
                            id="call_2",
                            name="rag",
                            arguments={"query": "construction exam definition exam", "kb_name": "construction-exam"},
                        )
                    ],
                )
            return LLMResponse(content="基于现有资料直接回答")

        def get_default_model(self) -> str:
            return "fake-model"

    class SaturatingRagTool(Tool):
        def __init__(self) -> None:
            self._execute_count = 0

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kb_name": {"type": "string"}},
                "required": ["query"],
            }

        def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
            return dict(params)

        async def execute(self, **kwargs: Any) -> str:
            self._execute_count += 1
            return f"round-{self._execute_count}:{kwargs['query']}"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            return {
                "kb_name": "construction-exam",
                "sources": [
                    {"chunk_id": "chunk-1", "source_type": "standard"},
                    {"chunk_id": "chunk-2", "source_type": "standard"},
                ],
            }

    class DummyTool(Tool):
        @property
        def name(self) -> str:
            return "web_search"

        @property
        def description(self) -> str:
            return "dummy"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return str(kwargs)

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(SaturatingRagTool())
    loop.tools.register(DummyTool())

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "帮我解释建筑构造"}],
        on_tool_result=lambda name, result, metadata: _capture_async(
            captured["tool_results"], (name, result, metadata)
        ),
    )

    assert final_content == "基于现有资料直接回答"
    assert tools_used == ["rag", "rag"]
    assert "rag" in captured["tool_name_sets"][0]
    assert "rag" in captured["tool_name_sets"][1]
    assert "rag" not in captured["tool_name_sets"][2]
    assert "web_search" in captured["tool_name_sets"][2]
    second_metadata = captured["tool_results"][1][2]
    assert second_metadata["rag_saturation"] == {
        "detected": True,
        "reason": "high_query_similarity_and_source_overlap",
        "round_index": 2,
        "query_similarity_to_prev": 1.0,
        "source_overlap_to_prev": 1.0,
        "shared_source_count_with_prev": 2,
        "query_similarity_threshold": 0.85,
        "source_overlap_threshold": 0.6,
    }


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_forces_exact_authority_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class FakeProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="先查知识库",
                    tool_calls=[ToolCallRequest(id="call_1", name="rag", arguments={"query": "案例题"})],
                )
            return LLMResponse(content="模型自己生成了一个不完整答案")

        def get_default_model(self) -> str:
            return "fake-model"

    class ExactAuthorityTool(Tool):
        def __init__(self) -> None:
            self._trace_metadata = {
                "authority_applied": True,
                "exact_question": {
                    "answer_kind": "mcq",
                    "correct_answer": "D",
                    "analysis": "这是历史真题的标准答案。",
                },
            }

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "exact authority rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return "知识库返回了标准答案"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            metadata = dict(self._trace_metadata)
            self._trace_metadata = {}
            return metadata

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(ExactAuthorityTool())

    final_content, _tools_used, messages = await loop._run_agent_loop(
        [{"role": "user", "content": "给我讲这道题"}],
        allow_exact_authority_override=True,
    )

    assert final_content == "标准答案：D\n解析：这是历史真题的标准答案。"
    assert messages[-1]["content"] == final_content


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_does_not_override_general_chat_with_exact_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class FakeProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="先查知识库",
                    tool_calls=[ToolCallRequest(id="call_1", name="rag", arguments={"query": "建筑构造 考试重点 常见考点 真题"})],
                )
            if on_content_delta is not None:
                await on_content_delta("建筑构造是建筑物的物质组成和连接方式。")
            return LLMResponse(content="建筑构造是建筑物的物质组成和连接方式。")

        def get_default_model(self) -> str:
            return "fake-model"

    class ExactAuthorityTool(Tool):
        def __init__(self) -> None:
            self._trace_metadata = {
                "authority_applied": False,
                "exact_question": {
                    "answer_kind": "mcq",
                    "correct_answer": "CDE",
                    "analysis": "这是一道真题的标准解析。",
                },
            }

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "exact authority rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return "题库命中了相关真题"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            metadata = dict(self._trace_metadata)
            self._trace_metadata = {}
            return metadata

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FakeProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(ExactAuthorityTool())

    final_content, _tools_used, messages = await loop._run_agent_loop(
        [{"role": "user", "content": "建筑构造是什么"}],
        allow_exact_authority_override=False,
    )

    assert final_content == "建筑构造是建筑物的物质组成和连接方式。"
    assert messages[-1]["content"] == final_content


@pytest.mark.asyncio
async def test_tutorbot_process_direct_short_circuits_full_case_exact_fast_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class FailIfCalledProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            raise AssertionError("LLM should not be called after full exact fast path.")

        def get_default_model(self) -> str:
            return "fake-model"

    class ExactCaseTool(Tool):
        def __init__(self) -> None:
            self._trace_metadata = {
                "kb_name": "construction-exam",
                "sources": [{"chunk_id": "question-9717", "source_type": "real_exam"}],
                "authority_applied": False,
                "exact_question": {
                    "answer_kind": "case_study",
                    "coverage_state": "multi_subquestion_exact",
                    "coverage_ratio": 1.0,
                    "missing_subquestions": [],
                    "covered_subquestions": [
                        {
                            "display_index": "1",
                            "authoritative_answer": "（1）计划、组织、协调方案。",
                            "analysis": "",
                        },
                        {
                            "display_index": "4",
                            "authoritative_answer": "（1）12.10-0.72-1.10=10.28 亿元。",
                            "analysis": "",
                        },
                        {
                            "display_index": "5",
                            "authoritative_answer": "造价：3335.40 万元。",
                            "analysis": "",
                        },
                    ],
                },
            }

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "exact case rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kb_name": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            assert kwargs["kb_name"] == "construction-exam"
            return "知识库命中整题标准答案"

        def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
            return dict(params)

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            metadata = dict(self._trace_metadata)
            self._trace_metadata = {}
            return metadata

    captured: dict[str, Any] = {"tool_calls": [], "tool_results": []}

    loop = AgentLoop(
        bus=MessageBus(),
        provider=FailIfCalledProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(ExactCaseTool())

    content = await loop.process_direct(
        "背景资料：某旧城改造工程。问题：1. 通常进行资格预审的工程有哪些特点？2. 管理策划内容还有哪些？4. 按照完全成本法计算的工程施工项目成本是多少亿元？5. 分步骤列式计算钢结构装饰架的造价是多少万元？",
        metadata={"default_kb": "construction-exam"},
        on_tool_call=lambda name, args: _capture_async(captured["tool_calls"], (name, args)),
        on_tool_result=lambda name, result, metadata: _capture_async(
            captured["tool_results"], (name, result, metadata)
        ),
    )

    assert "10.28 亿元" in content
    assert "3335.40 万元" in content
    assert captured["tool_calls"] == [("rag", {"query": "背景资料：某旧城改造工程。问题：1. 通常进行资格预审的工程有哪些特点？2. 管理策划内容还有哪些？4. 按照完全成本法计算的工程施工项目成本是多少亿元？5. 分步骤列式计算钢结构装饰架的造价是多少万元？", "kb_name": "construction-exam"})]
    assert captured["tool_results"][0][2]["authority_applied"] is True
    assert captured["tool_results"][0][2]["rag_round"] == {
        "round_index": 1,
        "query": "背景资料：某旧城改造工程。问题：1. 通常进行资格预审的工程有哪些特点？2. 管理策划内容还有哪些？4. 按照完全成本法计算的工程施工项目成本是多少亿元？5. 分步骤列式计算钢结构装饰架的造价是多少万元？",
        "kb_name": "construction-exam",
        "source_count": 1,
        "sources": [{"chunk_id": "question-9717", "source_type": "real_exam"}],
        "query_similarity_to_prev": None,
        "source_overlap_to_prev": None,
        "shared_source_count_with_prev": 0,
    }


@pytest.mark.asyncio
async def test_tutorbot_process_direct_limits_tool_schemas_to_default_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    captured: dict[str, Any] = {}

    class CapturingProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            captured["tool_names"] = [
                str(item.get("function", {}).get("name") or "")
                for item in list(tools or [])
            ]
            if on_content_delta is not None:
                await on_content_delta("已完成")
            return LLMResponse(content="已完成")

        def get_default_model(self) -> str:
            return "fake-model"

    class NamedTool(Tool):
        def __init__(self, tool_name: str) -> None:
            self._tool_name = tool_name

        @property
        def name(self) -> str:
            return self._tool_name

        @property
        def description(self) -> str:
            return f"{self._tool_name} description"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return str(kwargs)

    loop = AgentLoop(
        bus=MessageBus(),
        provider=CapturingProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    for tool_name in ("rag", "web_search", "code_execution"):
        loop.tools.register(NamedTool(tool_name))

    content = await loop.process_direct(
        "建筑构造是什么？",
        metadata={"default_tools": ["rag"]},
    )

    assert content == "已完成"
    assert captured["tool_names"] == ["rag"]


@pytest.mark.asyncio
async def test_tutorbot_process_direct_ignores_preferred_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    captured: dict[str, Any] = {}

    class CapturingProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            captured["model"] = model
            return LLMResponse(content="已完成")

        def get_default_model(self) -> str:
            return "default-model"

    loop = AgentLoop(
        bus=MessageBus(),
        provider=CapturingProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )

    content = await loop.process_direct(
        "简要解释流水步距",
        metadata={"preferred_model": "deepseek-v3.2"},
    )

    assert content == "已完成"
    assert captured["model"] == "default-model"


@pytest.mark.asyncio
async def test_tutorbot_process_direct_fast_mode_uses_single_shot_fast_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    captured: dict[str, Any] = {}

    class CapturingProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            captured["tools"] = tools
            if on_content_delta is not None:
                await on_content_delta("快速回答")
            return LLMResponse(content="快速回答")

        def get_default_model(self) -> str:
            return "default-model"

    loop = AgentLoop(
        bus=MessageBus(),
        provider=CapturingProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )

    async def _no_fast_path(*_args, **_kwargs):
        return None

    async def _prefetched_messages(*, initial_messages, **_kwargs):
        return list(initial_messages) + [{"role": "tool", "content": "知识库命中"}]

    async def _fail_agent_loop(*_args, **_kwargs):
        raise AssertionError("fast mode should not enter the generic multi-step agent loop")

    monkeypatch.setattr(loop, "_maybe_run_exact_rag_fast_path", _no_fast_path)
    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _prefetched_messages)
    monkeypatch.setattr(loop, "_run_agent_loop", _fail_agent_loop)

    content = await loop.process_direct(
        "简短解释流水节拍",
        metadata={"effective_response_mode": "fast", "default_tools": ["rag"]},
    )

    assert content == "快速回答"
    assert captured["tools"] is None


@pytest.mark.asyncio
async def test_tutorbot_process_direct_prefetches_grounded_rag_for_current_info_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    captured: dict[str, Any] = {"tool_calls": [], "tool_results": []}

    class PrefetchProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            tool_messages = [item for item in messages if item.get("role") == "tool"]
            assert len(tool_messages) == 1
            assert "2026教材重点变化" in str(tool_messages[0].get("content") or "")
            assert any(
                item.get("role") == "system"
                and "首轮知识召回已完成" in str(item.get("content") or "")
                for item in messages
            )
            return LLMResponse(content="2026版教材确实有较大变化，重点集中在安全、BIM 和资源管理。")

        def get_default_model(self) -> str:
            return "fake-model"

    class PrefetchRagTool(Tool):
        def __init__(self) -> None:
            self._trace_metadata = {
                "kb_name": "construction-exam",
                "sources": [{"chunk_id": "DELTA26_SAFETY_FIRE_RESOURCE", "source_type": "textbook"}],
                "authority_applied": False,
                "exact_question": {},
            }

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "grounded rag"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kb_name": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            assert kwargs["query"] == "2026年的教材有什么不一样"
            assert kwargs["kb_name"] == "construction-exam"
            return "## 2026教材重点变化：安全检查·消防管理·资源管理"

        def preview_args(self, params: dict[str, Any]) -> dict[str, Any]:
            return dict(params)

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            metadata = dict(self._trace_metadata)
            self._trace_metadata = {}
            return metadata

    loop = AgentLoop(
        bus=MessageBus(),
        provider=PrefetchProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(PrefetchRagTool())

    content = await loop.process_direct(
        "2026年的教材有什么不一样",
        metadata={
            "default_kb": "construction-exam",
            "knowledge_bases": ["construction-exam"],
            "current_info_required": True,
            "bot_id": "construction-exam-coach",
        },
        on_tool_call=lambda name, args: _capture_async(captured["tool_calls"], (name, args)),
        on_tool_result=lambda name, result, metadata: _capture_async(
            captured["tool_results"], (name, result, metadata)
        ),
    )

    assert "较大变化" in content
    assert captured["tool_calls"] == [
        ("rag", {"query": "2026年的教材有什么不一样", "kb_name": "construction-exam"})
    ]
    assert captured["tool_results"][0][2]["rag_round"] == {
        "round_index": 1,
        "query": "2026年的教材有什么不一样",
        "kb_name": "construction-exam",
        "source_count": 1,
        "sources": [{"chunk_id": "DELTA26_SAFETY_FIRE_RESOURCE", "source_type": "textbook"}],
        "query_similarity_to_prev": None,
        "source_overlap_to_prev": None,
        "shared_source_count_with_prev": 0,
    }


@pytest.mark.asyncio
async def test_tutorbot_agent_loop_skips_exact_authority_for_practice_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "loguru", fake_loguru)

    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class PracticeOnlyProvider(LLMProvider):
        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            if on_content_delta is not None:
                await on_content_delta("下面这道题你先自己做：")
            return LLMResponse(content="下面这道题你先自己做：\n某双代号网络计划中，关键线路的特点是什么？")

        def get_default_model(self) -> str:
            return "fake-model"

    class ExactAuthorityTool(Tool):
        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "should not be called for practice generation"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kb_name": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            raise AssertionError("Exact-authority RAG fast path should be skipped for practice generation.")

    loop = AgentLoop(
        bus=MessageBus(),
        provider=PracticeOnlyProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(
                metadata={},
                key=key,
                messages=[],
                get_history=lambda max_messages=0: [],
            ),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(ExactAuthorityTool())

    content = await loop.process_direct(
        "考我一道关键线路的题，不要给答案",
        metadata={
            "default_kb": "construction-exam",
            "suppress_answer_reveal_on_generate": True,
        },
    )

    assert "关键线路的特点是什么" in content
    assert "答案" not in content


@pytest.mark.asyncio
async def test_deep_question_capability_skips_followup_agent_for_forced_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._callback = None

        def set_ws_callback(self, callback) -> None:
            self._callback = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["topic_call"] = kwargs
            assert self._callback is not None
            return {
                "results": [
                    {
                        "qa_pair": {
                            "question_id": "q_1",
                            "question": "新的防水工程单选题",
                            "question_type": "choice",
                            "options": {"A": "方案A", "B": "方案B"},
                            "correct_answer": "B",
                            "explanation": "B 更符合规范要求。",
                        }
                    }
                ]
            }

    class FakeFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("FollowupAgent should not be constructed for forced generation")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
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

    context = UnifiedContext(
        user_message="继续出",
        config_overrides={
            "mode": "custom",
            "topic": "继续出",
            "question_type": "choice",
            "force_generate_questions": True,
        },
        language="zh",
        metadata={
            "question_followup_context": {
                "question_id": "q_1",
                "question": "旧题",
                "question_type": "choice",
                "correct_answer": "A",
            },
        },
    )
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["topic_call"]["user_topic"].startswith("继续出")
    assert "当前题目内容：旧题" in captured["topic_call"]["user_topic"]
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "custom"
    assert result_event.metadata["question_followup_context"]["question"] == "新的防水工程单选题"
    assert result_event.metadata["question_followup_context"]["correct_answer"] == "B"


@pytest.mark.asyncio
async def test_deep_question_capability_uses_submission_grader_for_choice_submission(
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
            return "## 🧐 解析\n你这题选对了。\n\n## ⚠️ 易错点\n不要把步距和节拍混淆。\n\n## 🎯 记忆锦囊\n队与队之间看步距。\n\n## 🚀 下一步建议\n再做 1 道同类题巩固。"

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

    assert captured["process"]["question_context"]["diagnosis"] == "CORRECT"
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["user_answer"] == "B"
    assert result_event.metadata["is_correct"] is True


def test_deep_question_capability_humanizes_question_progress_labels() -> None:
    assert DeepQuestionCapability._humanize_question_id("q_3") == "Question 3"
    assert (
        DeepQuestionCapability._format_bridge_message(
            "question_update",
            {"question_id": "q_3", "current": 3, "total": 3},
        )
        == "Generating Question 3 (3/3)"
    )
    assert (
        DeepQuestionCapability._format_bridge_message(
            "result",
            {
                "question_id": "q_3",
                "index": 2,
                "question": {"question_type": "coding", "difficulty": "hard"},
                "success": True,
            },
        )
        == "Question 3 done (#3, coding/hard, success=True)"
    )


@pytest.mark.asyncio
async def test_deep_research_capability_requires_explicit_config_and_streams_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeptutor.agents.research.request_config  # noqa: F401

    captured: dict[str, Any] = {}

    class FakeResearchPipeline:
        def __init__(self, **kwargs: Any) -> None:
            captured["pipeline_init"] = kwargs

        async def run(self, topic: str) -> dict[str, Any]:
            captured["pipeline_init"]["progress_callback"](
                {"status": "gathering evidence", "stage": "researching", "block_id": "block_1"}
            )
            await captured["pipeline_init"]["trace_callback"](
                {
                    "event": "llm_call",
                    "state": "running",
                    "agent_name": "rephrase_agent",
                    "stage": "rephrase",
                }
            )
            await captured["pipeline_init"]["trace_callback"](
                {
                    "event": "tool_call",
                    "phase": "researching",
                    "tool_name": "web_search",
                    "tool_args": {"query": "agent-native tutoring"},
                    "label": "Use web_search",
                    "call_id": "research-tool-1",
                }
            )
            return {"report": f"Report about {topic}", "metadata": {"citations": 3}}

    def fake_load_config_with_main(_: str) -> dict[str, Any]:
        return {
            "research": {
                "researching": {
                    "note_agent_mode": "auto",
                    "tool_timeout": 60,
                    "tool_max_retries": 2,
                    "paper_search_years_limit": 3,
                },
                "rag": {"default_mode": "hybrid"},
            },
            "tools": {"web_search": {"enabled": True}},
        }

    _install_module(
        monkeypatch,
        "deeptutor.agents.research.research_pipeline",
        ResearchPipeline=FakeResearchPipeline,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.config",
        load_config_with_main=fake_load_config_with_main,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="agent-native tutoring",
        enabled_tools=["rag", "web_search", "paper_search"],
        knowledge_bases=["research-kb"],
        config_overrides={
            "mode": "report",
            "depth": "standard",
            "sources": ["kb", "web", "papers"],
            "confirmed_outline": [
                {"title": "核心概念", "overview": "聚焦 agent-native tutoring 的关键机制"},
            ],
        },
        language="en",
    )
    capability = DeepResearchCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    config = captured["pipeline_init"]["config"]
    assert config["planning"]["decompose"]["mode"] == "auto"
    assert config["planning"]["decompose"]["auto_max_subtopics"] == 4
    assert config["researching"]["max_iterations"] == 3
    assert config["researching"]["enable_paper_search"] is True
    assert config["researching"]["enable_web_search"] is True
    assert config["reporting"]["style"] == "report"
    assert config["tools"]["web_search"]["enabled"] is True
    progress_event = next(
        event
        for event in events
        if event.type == StreamEventType.PROGRESS and event.content == "gathering evidence"
    )
    assert progress_event.metadata["research_stage_card"] == "evidence"
    tool_call_event = next(
        event
        for event in events
        if event.type == StreamEventType.TOOL_CALL and event.content == "web_search"
    )
    assert tool_call_event.metadata["research_stage_card"] == "evidence"
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["response"] == "Report about agent-native tutoring"
