from __future__ import annotations

import asyncio
import sqlite3
import importlib
from types import SimpleNamespace

import pytest

from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.sqlite_store import (
    SQLiteSessionStore,
    build_active_object_from_session,
    build_user_owner_key,
)
from deeptutor.services.session.turn_runtime import (
    TurnRuntimeManager,
    _LiveSubscriber,
    _TurnExecution,
    _resolve_question_followup_context_and_action,
)

unified_ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")


async def _noop_refresh(**_kwargs):
    return None


@pytest.mark.asyncio
async def test_redacted_public_followup_context_does_not_override_grading_authority() -> None:
    public_context = {
        "question_id": "q_1",
        "question": "屋面防水卷材施工前，基层应满足哪项要求？",
        "question_type": "choice",
        "options": {"A": "含水率适宜且表面平整", "B": "可带明水直接铺贴"},
        "correct_answer": "",
        "explanation": "",
        "user_answer": "A",
    }
    stored_context = {
        **public_context,
        "correct_answer": "A",
        "explanation": "基层应平整、干净、含水率符合要求。",
        "user_answer": "",
    }

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="我选 A",
        explicit_context=public_context,
        explicit_action={"intent": "answer_questions", "answers": [{"index": 1, "user_answer": "A"}]},
        candidate_contexts=[stored_context],
    )

    assert resolved_context is not None
    assert resolved_context["correct_answer"] == "A"
    assert resolved_context["explanation"] == "基层应平整、干净、含水率符合要求。"
    assert resolved_context["user_answer"] == "A"
    assert resolved_action is not None


@pytest.mark.asyncio
async def test_turn_runtime_replays_events_and_materializes_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event is not None:
                await on_event(
                    StreamEvent(
                        type=StreamEventType.PROGRESS,
                        source="context",
                        stage="summarizing",
                        content="summarize context",
                    )
                )
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Hello Frank",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello, i'm frank",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "progress", "content", "done"]
    assert events[-1]["metadata"]["status"] == "completed"

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "Hello Frank"
    assert detail["preferences"]["archived"] is False
    assert detail["preferences"]["capability"] == "chat"
    assert detail["preferences"]["chat_mode"] == get_default_chat_mode()
    assert detail["preferences"]["tools"] == []
    assert detail["preferences"]["knowledge_bases"] == []
    assert detail["preferences"]["language"] == "en"

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["status"] == "completed"


@pytest.mark.asyncio
async def test_turn_runtime_captures_exact_authority_response_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="1. 标准答案\n\n2. 标准答案",
                metadata={"call_kind": "exact_authority_response", "call_id": "exact-1"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "案例题",
            "session_id": None,
            "capability": None,
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert events[-1]["type"] == "done"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["role"] == "assistant"
    assert detail["messages"][-1]["content"] == "1. 标准答案\n\n2. 标准答案"


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_open_chat_active_object_when_no_stronger_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_object"] = context.metadata.get("active_object")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "继续聊这个话题。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我们继续聊施工组织总设计",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    active_object = captured["active_object"]
    assert active_object["object_type"] == "open_chat_topic"
    assert active_object["object_id"] == session["id"]
    assert active_object["state_snapshot"]["session_id"] == session["id"]


@pytest.mark.asyncio
async def test_turn_runtime_prefers_result_response_as_assistant_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="## 结论\n",
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="建筑构造是研究建筑物组成与连接方式的技术。",
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "建筑构造是研究建筑物组成与连接方式的技术。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["content"] == "建筑构造是研究建筑物组成与连接方式的技术。"


@pytest.mark.asyncio
async def test_turn_runtime_excludes_internal_content_from_assistant_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content="我来读取相关技能文件。",
                visibility="internal",
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": "建筑构造是研究建筑物组成方式和连接关系的学科。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["content"] == "建筑构造是研究建筑物组成方式和连接关系的学科。"
    assert any(event["visibility"] == "internal" for event in events if event["type"] == "content")
    assert all(
        item.get("visibility") == "public"
        for item in detail["messages"][-1]["events"]
        if item.get("type") not in {"done", "session"}
    )


@pytest.mark.asyncio
async def test_turn_runtime_routes_construction_exam_bot_to_tutorbot_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            assert context.active_capability == "tutorbot"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content="TutorBot reply",
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你好",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"bot_id": "construction-exam-coach"},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert turn["capability"] == "tutorbot"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "tutorbot"
    assert detail["preferences"]["tools"] == ["rag"]
    assert detail["preferences"]["knowledge_bases"] == ["construction-exam"]
    assert detail["messages"][-1]["content"] == "TutorBot reply"


@pytest.mark.asyncio
async def test_turn_runtime_pins_tutorbot_practice_generation_to_tutorbot_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["user_message"] = context.user_message
            captured["config_overrides"] = dict(context.config_overrides)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content="第1题",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我想练习施工管理，请给我来5道选择题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "tutorbot"
    assert captured["active_capability"] == "tutorbot"
    assert captured["user_message"] == "我想练习施工管理，请给我来5道选择题"
    assert captured["config_overrides"]["bot_id"] == "construction-exam-coach"

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "tutorbot"
    assert detail["messages"][-1]["content"] == "第1题"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "tutorbot"


@pytest.mark.asyncio
async def test_turn_runtime_leaves_tutorbot_question_followup_for_orchestrator_autoroute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["followup_question_context"] = dict(
                context.metadata.get("question_followup_context", {}) or {}
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="第1题：判断正确",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选B",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "subject_domain": "construction_exam",
                },
                "followup_question_context": {
                    "question_id": "q_1",
                    "question": "关于施工组织设计，下列说法正确的是：",
                    "question_type": "choice",
                    "options": {
                        "A": "说法A",
                        "B": "说法B",
                        "C": "说法C",
                        "D": "说法D",
                    },
                    "correct_answer": "B",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert captured["followup_question_context"]["question_id"] == "q_1"
    assert captured["followup_question_context"]["correct_answer"] == "B"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_question"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_injects_usage_summary_into_result_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                content=(
                    "Error: {'message': 'Authentication Fails, Your api key: ****486e is invalid', "
                    "'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}"
                ),
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": "answer",
                    "metadata": {"cost_summary": {"total_tokens": 11, "total_calls": 1}},
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "scope_id": "turn_scope",
            "session_id": "session_scope",
            "turn_id": "turn_scope",
            "capability": "chat",
            "total_input_tokens": 120,
            "total_output_tokens": 45,
            "total_tokens": 165,
            "total_calls": 3,
            "measured_calls": 1,
            "estimated_calls": 2,
            "usage_accuracy": "mixed",
            "usage_sources": {"provider": 1, "tiktoken": 2},
            "models": {"gpt-4o": 3},
            "total_cost_usd": 0.00123,
        },
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    result_event = next(event for event in events if event["type"] == "result")
    cost_summary = result_event["metadata"]["metadata"]["cost_summary"]
    assert cost_summary["total_tokens"] == 165
    assert cost_summary["total_calls"] == 3
    assert cost_summary["usage_accuracy"] == "mixed"
    assert result_event["metadata"]["metadata"]["capability_cost_summary"] == {
        "total_tokens": 11,
        "total_calls": 1,
    }


@pytest.mark.asyncio
async def test_turn_runtime_updates_turn_observation_with_usage_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "answer", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "scope_id": "turn_scope",
            "session_id": "session_scope",
            "turn_id": "turn_scope",
            "capability": "chat",
            "total_input_tokens": 90,
            "total_output_tokens": 10,
            "total_tokens": 100,
            "total_calls": 1,
            "measured_calls": 1,
            "estimated_calls": 0,
            "usage_accuracy": "measured",
            "usage_sources": {"provider": 1},
            "models": {"gpt-4o": 1},
            "total_cost_usd": 0.0008,
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    final_update = captured_updates[-1]
    assert final_update["usage_details"] == {
        "input": 90.0,
        "output": 10.0,
        "total": 100.0,
    }
    assert final_update["cost_details"] == {
        "input": 0.0,
        "output": 0.0,
        "total": 0.0008,
    }


@pytest.mark.asyncio
async def test_turn_runtime_records_release_lineage_in_observation_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "answer", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.get_release_lineage_metadata",
        lambda: {
            "release_id": "1.0.0+abc123+prod",
            "service_version": "1.0.0",
            "git_sha": "abc123",
            "deployment_environment": "prod",
            "prompt_version": "prompt-v9",
            "ff_snapshot_hash": "ffaa00112233",
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["release_id"] == "1.0.0+abc123+prod"
    assert metadata["service_version"] == "1.0.0"
    assert metadata["git_sha"] == "abc123"
    assert metadata["deployment_environment"] == "prod"
    assert metadata["prompt_version"] == "prompt-v9"
    assert metadata["ff_snapshot_hash"] == "ffaa00112233"


@pytest.mark.asyncio
async def test_turn_runtime_records_aae_scores_in_observation_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeSurfaceEventStore:
        def get_turn_summary(self, _turn_id: str) -> dict[str, object]:
            return {
                "turn_id": "turn-test",
                "event_counts": {
                    "first_visible_content_rendered": 1,
                    "done_rendered": 1,
                },
                "first_visible_content_rendered": 1,
                "done_rendered": 1,
                "surface_render_failed": 0,
            }

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "继续分析这道题。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.get_surface_event_store",
        lambda: FakeSurfaceEventStore(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "为什么我这题错了",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "followup_question_context": {
                    "parent_quiz_session_id": "quiz_session_1",
                    "question_id": "q_2",
                    "question_type": "choice",
                    "difficulty": "hard",
                    "concentration": "win-rate comparison",
                    "question": "Which criterion best describes density?",
                    "options": {
                        "A": "Coverage",
                        "B": "Informative value",
                        "C": "Relevant content without redundancy",
                        "D": "Credibility",
                    },
                    "user_answer": "B",
                    "correct_answer": "C",
                    "is_correct": True,
                    "explanation": "Density focuses on including relevant content without redundancy.",
                    "knowledge_context": "Density measures whether content is relevant and non-redundant.",
                }
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["aae_scores"]["correctness_score"]["value"] == 1.0
    assert metadata["aae_scores"]["surface_render_score"]["value"] == 1.0
    assert metadata["aae_scores"]["paid_student_satisfaction_score"]["is_proxy"] is True
    assert metadata["aae_scores"]["latency_class"]["value"] in {"fast", "acceptable", "slow"}
    assert metadata["aae_composite"]["input_count"] >= 2
    assert metadata["aae_composite"]["is_proxy"] is True


@pytest.mark.asyncio
async def test_turn_runtime_wraps_selector_llm_calls_in_parent_turn_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeObservability:
        def __init__(self) -> None:
            self.active_observations: list[str] = []
            self.scope_active = False
            self.started: list[dict[str, object]] = []
            self.scopes: list[SimpleNamespace] = []
            self.updated: list[dict[str, object]] = []

        def usage_scope(self, **kwargs):
            outer = self

            class _UsageScope:
                def __enter__(self):
                    outer.scope_active = True
                    scope = SimpleNamespace(**kwargs)
                    outer.scopes.append(scope)
                    return scope

                def __exit__(self, *_args):
                    outer.scope_active = False
                    return False

            return _UsageScope()

        def start_observation(self, **kwargs):
            outer = self
            name = str(kwargs.get("name") or "")
            parent = outer.active_observations[-1] if outer.active_observations else None

            class _Observation:
                def __enter__(self):
                    outer.started.append(
                        {
                            "name": name,
                            "parent": parent,
                            "scope_active": outer.scope_active,
                            "metadata": dict(kwargs.get("metadata") or {}),
                        }
                    )
                    outer.active_observations.append(name)
                    return SimpleNamespace(name=name)

                def __exit__(self, *_args):
                    outer.active_observations.pop()
                    return False

            return _Observation()

        def update_observation(self, _observation, **kwargs):
            self.updated.append(kwargs)

        def get_current_usage_summary(self):
            return {}

        def summary_metadata(self, _summary):
            return {}

        def usage_details_from_summary(self, _summary):
            return None

        def cost_details_from_summary(self, _summary):
            return None

    fake_observability = FakeObservability()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "context_builder"},
            ):
                pass
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            with fake_observability.start_observation(
                name="llm.complete",
                as_type="generation",
                metadata={"call_site": "selector"},
            ):
                return "deep_question"

        async def handle(self, context):
            assert context.active_capability == "deep_question"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="第1题",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    class FakeMemoryService:
        def build_memory_context(self):
            return ""

        async def refresh_from_turn(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "post_turn_memory"},
            ):
                pass

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", fake_observability)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: FakeMemoryService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "followup_question_context": {
                    "question_id": "q_1",
                    "question": "关于单层钢结构吊装顺序的说法，正确的有（ ）。",
                    "question_type": "choice",
                    "options": {"A": "单跨构宜从跨端一侧向另一侧吊装"},
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    selector_llm = next(item for item in fake_observability.started if item["name"] == "llm.complete")
    assert selector_llm["parent"] == "turn.runtime"
    assert selector_llm["scope_active"] is True
    assert fake_observability.scopes[0].capability == "deep_question"
    context_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "context_builder"
    )
    assert context_llm["parent"] == "turn.runtime"
    assert context_llm["scope_active"] is True
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))
    memory_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "post_turn_memory"
    )
    assert memory_llm["parent"] == "memory.consolidation"
    assert memory_llm["scope_active"] is True


@pytest.mark.asyncio
async def test_turn_runtime_wraps_learner_state_refresh_llm_in_parent_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeObservability:
        def __init__(self) -> None:
            self.active_observations: list[str] = []
            self.scope_active = False
            self.started: list[dict[str, object]] = []
            self.scopes: list[SimpleNamespace] = []

        def usage_scope(self, **kwargs):
            outer = self

            class _UsageScope:
                def __enter__(self):
                    outer.scope_active = True
                    scope = SimpleNamespace(**kwargs)
                    outer.scopes.append(scope)
                    return scope

                def __exit__(self, *_args):
                    outer.scope_active = False
                    return False

            return _UsageScope()

        def start_observation(self, **kwargs):
            outer = self
            name = str(kwargs.get("name") or "")
            parent = outer.active_observations[-1] if outer.active_observations else None

            class _Observation:
                def __enter__(self):
                    outer.started.append(
                        {
                            "name": name,
                            "parent": parent,
                            "scope_active": outer.scope_active,
                            "metadata": dict(kwargs.get("metadata") or {}),
                        }
                    )
                    outer.active_observations.append(name)
                    return SimpleNamespace(name=name)

                def __exit__(self, *_args):
                    outer.active_observations.pop()
                    return False

            return _Observation()

        def update_observation(self, _observation, **_kwargs):
            return None

        def get_current_usage_summary(self):
            return {}

        def summary_metadata(self, _summary):
            return {}

        def usage_details_from_summary(self, _summary):
            return None

        def cost_details_from_summary(self, _summary):
            return None

    fake_observability = FakeObservability()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="ok",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, **_kwargs):
            return ""

        async def refresh_from_turn(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "post_turn_learner"},
            ):
                pass

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", fake_observability)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wechat",
                    "user_id": "learner-1",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    learner_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "post_turn_learner"
    )
    assert learner_llm["parent"] == "learner_state.refresh"
    assert learner_llm["scope_active"] is True
    assert fake_observability.scopes[-1].scope_id == f"{turn['id']}:post_turn_refresh"
    assert fake_observability.scopes[-1].turn_id == turn["id"]
    assert fake_observability.scopes[-1].capability == "chat"


@pytest.mark.asyncio
async def test_post_turn_refresh_continues_when_observability_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    refreshed = {"value": False}

    class FailingObservability:
        def usage_scope(self, **_kwargs):
            raise RuntimeError("usage scope unavailable")

        def start_observation(self, **_kwargs):
            raise RuntimeError("observation unavailable")

    class FakeMemoryService:
        async def refresh_from_turn(self, **_kwargs):
            refreshed["value"] = True

    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", FailingObservability())

    runtime._schedule_post_turn_refresh(
        turn_id="turn_observability_fail",
        user_id="",
        raw_user_content="hello",
        assistant_content="ok",
        session_id="session_observability_fail",
        capability_name="chat",
        language="zh",
        source_bot_id="",
        context_route="",
        task_anchor_type="",
        learner_state_service=SimpleNamespace(),
        memory_service=FakeMemoryService(),
    )
    await asyncio.gather(*list(runtime._background_tasks))

    assert refreshed["value"] is True


@pytest.mark.asyncio
async def test_turn_runtime_metrics_track_completed_and_failed_turns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.api.runtime_metrics import get_turn_runtime_metrics, reset_turn_runtime_metrics
    from deeptutor.services.observability import get_turn_event_log, reset_turn_event_log

    reset_turn_runtime_metrics()
    reset_turn_event_log(events_dir=tmp_path / "observer_events")
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    usage_scope_closed = {"value": False}

    class FakeUsageScope:
        def __enter__(self):
            usage_scope_closed["value"] = False
            return None

        def __exit__(self, *_args):
            usage_scope_closed["value"] = True
            return False

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class CompletedOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "ok", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FailedOrchestrator:
        async def handle(self, _context):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.usage_scope",
        lambda **_kwargs: FakeUsageScope(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {}
        if usage_scope_closed["value"]
        else {
            "total_input_tokens": 7,
            "total_output_tokens": 5,
            "total_tokens": 12,
            "total_calls": 1,
        },
    )

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", CompletedOrchestrator)
    _session, completed_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(completed_turn["id"], after_seq=0):
        pass

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FailedOrchestrator)
    _session, failed_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello again",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(failed_turn["id"], after_seq=0):
        pass

    snapshot = get_turn_runtime_metrics().snapshot()
    assert snapshot["turns_started_total"] == 2
    assert snapshot["turns_completed_total"] == 1
    assert snapshot["turns_failed_total"] == 1
    assert snapshot["turns_in_flight"] == 0
    assert snapshot["turn_avg_latency_ms"] >= 0
    turn_events = get_turn_event_log().load_events()
    assert [item["status"] for item in turn_events] == ["completed", "failed"]
    assert [item["token_total"] for item in turn_events] == [12, 12]
    assert all((item.get("metadata") or {}).get("source") == "turn_runtime_terminal" for item in turn_events)


@pytest.mark.asyncio
async def test_turn_runtime_records_semantic_router_rollout_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured_context: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured_context["config_overrides"] = dict(context.config_overrides)
            context.metadata["semantic_router_mode"] = "shadow"
            context.metadata["semantic_router_mode_reason"] = "shadow_compare_only"
            context.metadata["semantic_router_scope"] = "question_only"
            context.metadata["semantic_router_scope_match"] = True
            context.metadata["semantic_router_shadow_decision"] = {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
            }
            context.metadata["semantic_router_shadow_route"] = "deep_question"
            context.metadata["semantic_router_selected_capability"] = "chat"
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "仍按旧链路执行。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "semantic_router_enabled": False,
                "semantic_router_shadow_mode": True,
                "semantic_router_scope": "question_only",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    config_overrides = captured_context["config_overrides"]
    assert config_overrides["semantic_router_enabled"] is False
    assert config_overrides["semantic_router_shadow_mode"] is True
    assert config_overrides["semantic_router_scope"] == "question_only"
    assert captured_updates
    final_update = captured_updates[-1]
    metadata = final_update["metadata"]
    assert metadata["semantic_router_mode"] == "shadow"
    assert metadata["semantic_router_mode_reason"] == "shadow_compare_only"
    assert metadata["semantic_router_scope"] == "question_only"
    assert metadata["semantic_router_scope_match"] is True
    assert metadata["semantic_router_shadow_route"] == "deep_question"
    assert metadata["semantic_router_selected_capability"] == "chat"
    assert metadata["semantic_router_shadow_decision"]["next_action"] == "route_to_grading"


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_question_followup_context_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            captured["history_messages"] = messages
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["conversation_history"] = context.conversation_history
            captured["config_overrides"] = context.config_overrides
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Let's discuss this question.",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "Why is my answer wrong?",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {
                "followup_question_context": {
                    "parent_quiz_session_id": "quiz_session_1",
                    "question_id": "q_2",
                    "question_type": "choice",
                    "difficulty": "hard",
                    "concentration": "win-rate comparison",
                    "question": "Which criterion best describes density?",
                    "options": {
                        "A": "Coverage",
                        "B": "Informative value",
                        "C": "Relevant content without redundancy",
                        "D": "Credibility",
                    },
                    "user_answer": "B",
                    "correct_answer": "C",
                    "explanation": "Density focuses on including relevant content without redundancy.",
                    "knowledge_context": "Density measures whether content is relevant and non-redundant.",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    assert [event["type"] for event in events] == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["system", "user", "assistant"]
    assert "Question Follow-up Context" in detail["messages"][0]["content"]
    assert "Which criterion best describes density?" in detail["messages"][0]["content"]
    assert "User answer: B" in detail["messages"][0]["content"]
    assert captured["conversation_history"][0]["role"] == "system"
    assert "followup_question_context" not in captured["config_overrides"]
    assert captured["metadata"]["question_followup_context"]["question_id"] == "q_2"


@pytest.mark.asyncio
async def test_turn_runtime_publishes_live_events_when_persistence_degrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.create_session(session_id="session-live")
    turn = await store.create_turn(session["id"], capability="chat")
    execution = _TurnExecution(
        turn_id=turn["id"],
        session_id=session["id"],
        capability="chat",
        payload={},
    )
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    execution.subscribers.append(_LiveSubscriber(queue=queue))
    runtime._executions[turn["id"]] = execution

    async def _broken_append(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "append_turn_event", _broken_append)
    monkeypatch.setattr(
        TurnRuntimeManager,
        "_mirror_event_to_workspace",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    payload = await runtime._persist_and_publish(
        execution,
        StreamEvent(
            type=StreamEventType.CONTENT,
            source="chat",
            stage="responding",
            content="partial answer",
        ),
    )
    delivered = await queue.get()

    assert execution.persistence_degraded is True
    assert payload["content"] == "partial answer"
    assert delivered["content"] == "partial answer"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_active_question_context_from_previous_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        call_count = 0

        async def handle(self, context):
            FakeOrchestrator.call_count += 1
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            if FakeOrchestrator.call_count == 1:
                yield StreamEvent(
                    type=StreamEventType.RESULT,
                    source="deep_question",
                    metadata={
                        "mode": "custom",
                        "question_followup_context": {
                            "question_id": "q_saved",
                            "question": "案例背景......第1问：判断是否合理。",
                            "question_type": "written",
                            "reveal_answers": False,
                            "reveal_explanations": False,
                        },
                    },
                )
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="第1问：判断是否合理。",
                    metadata={"call_kind": "llm_final_response"},
                )
            else:
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="好的，只问第1问。",
                    metadata={"call_kind": "llm_final_response"},
                )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "给我一道案例题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先别给答案，只问我第1问",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(second_turn[1]["id"], after_seq=0):
        pass

    active_context = await store.get_active_question_context(session["id"])
    assert active_context is not None
    assert active_context["question_id"] == "q_saved"
    assert captured["contexts"][1]["question_id"] == "q_saved"


@pytest.mark.asyncio
async def test_turn_runtime_backfills_result_execution_metadata_for_deep_question(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.create_session(session_id="session-meta")
    turn = await store.create_turn(session["id"], capability="deep_question")
    execution = _TurnExecution(
        turn_id=turn["id"],
        session_id=session["id"],
        capability="chat",
        payload={
            "capability": None,
            "config": {
                "chat_mode": "fast",
                "interaction_hints": {
                    "requested_response_mode": "smart",
                    "selected_mode": "fast",
                },
            },
        },
    )
    monkeypatch.setattr(
        TurnRuntimeManager,
        "_mirror_event_to_workspace",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    payload = await runtime._persist_and_publish(
        execution,
        StreamEvent(
            type=StreamEventType.RESULT,
            source="deep_question",
            metadata={
                "response": "graded response",
                "mode": "grading",
            },
        ),
    )

    assert payload["metadata"]["selected_mode"] == "fast"
    assert payload["metadata"]["execution_path"] == "deep_question_grading"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_active_question_context_from_result_presentation_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        call_count = 0

        async def handle(self, context):
            FakeOrchestrator.call_count += 1
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            if FakeOrchestrator.call_count == 1:
                yield StreamEvent(
                    type=StreamEventType.RESULT,
                    source="chat",
                    metadata={
                        "response": "### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                        "presentation": {
                            "schema_version": 1,
                            "blocks": [
                                {
                                    "type": "mcq",
                                    "questions": [
                                        {
                                            "index": 1,
                                            "question_id": "q_saved_from_presentation",
                                            "stem": "关于屋面防水等级和设防要求，下列说法正确的是？",
                                            "question_type": "single_choice",
                                            "options": [
                                                {"key": "A", "text": "说法A"},
                                                {"key": "B", "text": "说法B"},
                                                {"key": "C", "text": "说法C"},
                                                {"key": "D", "text": "说法D"},
                                            ],
                                            "followup_context": {
                                                "question_id": "q_saved_from_presentation",
                                                "question": "关于屋面防水等级和设防要求，下列说法正确的是？",
                                                "question_type": "choice",
                                                "options": {
                                                    "A": "说法A",
                                                    "B": "说法B",
                                                    "C": "说法C",
                                                    "D": "说法D",
                                                },
                                                "correct_answer": "C",
                                                "explanation": "C 正确。",
                                            },
                                        }
                                    ],
                                }
                            ],
                            "fallback_text": "### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                        },
                    },
                )
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="chat",
                    stage="responding",
                    content="### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                    metadata={"call_kind": "llm_final_response"},
                )
            else:
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="你选了 A，正确答案是 C。",
                    metadata={"call_kind": "llm_final_response"},
                )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "给我一道屋面防水单选题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A。",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(second_turn[1]["id"], after_seq=0):
        pass

    active_context = await store.get_active_question_context(session["id"])
    assert active_context is not None
    assert active_context["question_id"] == "q_saved_from_presentation"
    assert captured["contexts"][1]["question_id"] == "q_saved_from_presentation"
    assert captured["contexts"][1]["correct_answer"] == "C"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_pin_tutorbot_for_recovered_question_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="你选了 A。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_saved",
            "question": "关于屋面防水等级与对应防水设防道数的要求，以下说法正确的是？",
            "question_type": "choice",
            "options": {
                "A": "一级防水时，防水设防不应少于2道",
                "B": "二级防水时，防水设防不应少于3道",
                "C": "三级防水时，防水设防不应少于2道",
                "D": "一级防水时，防水设防不应少于3道",
            },
            "correct_answer": "D",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A。",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "q_saved"
    assert captured["question_followup_context"]["correct_answer"] == "D"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_pin_tutorbot_when_llm_identifies_followup_that_regex_misses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            captured["question_followup_action"] = context.metadata.get(
                "question_followup_action"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="按修正后的答案继续批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    async def _fake_interpret(_message, question_context, **_kwargs):
        if str((question_context or {}).get("question_id") or "") != "quiz_llm_runtime":
            return None
        return {
            "intent": "revise_answers",
            "confidence": 0.97,
            "preserve_other_answers": True,
            "answers": [
                {
                    "index": 1,
                    "question_id": "q_1",
                    "user_answer": "C",
                }
            ],
            "reason": "用户是在基于已有题组修改第一题答案。",
        }

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _fake_interpret,
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_llm_followup")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_llm_runtime",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "B",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                    "user_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一题我改C，别的不动",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "quiz_llm_runtime"
    assert captured["question_followup_action"]["intent"] == "revise_answers"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_suspends_active_question_for_unrelated_general_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = dict(context.metadata)
            captured["active_capability"] = context.active_capability
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="先回答这个新问题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_suspend_question", title="流水施工")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_suspend_runtime",
            "question": "第1题...\n第2题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "C",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先暂停一下。顺便问个别的：横道图和网络图哪个更适合考试答题时分析关键线路？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_profile": "mini_tutor",
                "interaction_hints": {
                    "profile": "mini_tutor",
                    "teaching_mode": "smart",
                },
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["active_capability"] is None
    assert "question_followup_context" not in captured["metadata"]
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["active_object"]["object_type"] == "open_chat_topic"
    assert captured["metadata"]["suspended_object_stack"][0]["object_type"] == "question_set"

    stored_active_object = await store.get_active_object(session["id"])
    stored_suspended_stack = await store.get_suspended_object_stack(session["id"])
    assert stored_active_object is not None
    assert stored_active_object["object_type"] == "open_chat_topic"
    assert stored_suspended_stack[0]["object_type"] == "question_set"


@pytest.mark.asyncio
async def test_turn_runtime_suspends_active_question_before_smart_mode_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "先回答这个新问题。",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session = await store.create_session(
        session_id="session_suspend_question_mode",
        title="流水施工",
    )
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_suspend_runtime_mode",
            "question": "第1题...\n第2题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "C",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先暂停一下。顺便问个别的：横道图和网络图哪个更适合考试答题时分析关键线路？",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    assert "question_followup_context" not in captured["metadata"]
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["active_object"]["object_type"] == "open_chat_topic"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_batch_submission_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始批改这一组题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_batch",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第1题：C；第2题：A；第3题：B",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert captured["question_followup_context"]["question_id"] == "quiz_batch"
    assert len(captured["question_followup_context"]["items"]) == 3
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_compact_batch_letters_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按顺序批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_compact_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_compact",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "ACD；",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert [item["question_id"] for item in captured["question_followup_context"]["items"]] == [
        "q_1",
        "q_2",
        "q_3",
    ]
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_compact_numbered_batch_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按编号顺序批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_compact_numbered_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_compact_numbered",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一题A第二题C第三题D",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert [item["question_id"] for item in captured["question_followup_context"]["items"]] == [
        "q_1",
        "q_2",
        "q_3",
    ]
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_batch_correction_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按修正后的答案批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_batch_correction_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_correction",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                    "user_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第2题改成C，其他不变",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "quiz_correction"
    assert len(captured["question_followup_context"]["items"]) == 3
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_inject_stale_question_context_for_unrelated_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="普通讲解回复",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_general")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_saved",
            "question": "第1题：判断是否合理。",
            "question_type": "written",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["contexts"] == [None]


@pytest.mark.asyncio
async def test_turn_runtime_recovers_orphaned_running_turn_before_new_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="after recovery",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="orphan-session")
    orphan_turn = await store.create_turn(session["id"], capability="chat")

    _session, new_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续下一轮",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(new_turn["id"], after_seq=0):
        pass

    recovered = await store.get_turn(orphan_turn["id"])
    assert recovered is not None
    assert recovered["status"] == "failed"


@pytest.mark.asyncio
async def test_turn_runtime_cancels_superseded_running_turn_before_new_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    first_turn_started = asyncio.Event()
    first_turn_cancelled = asyncio.Event()
    orchestrator_calls = {"count": 0}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            orchestrator_calls["count"] += 1
            if orchestrator_calls["count"] == 1:
                first_turn_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    first_turn_cancelled.set()
                    raise
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="second turn answer",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一轮问题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(first_turn_started.wait(), timeout=1.0)

    _session, second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第二轮问题",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(first_turn_cancelled.wait(), timeout=1.0)
    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    cancelled_turn = await store.get_turn(first_turn["id"])
    completed_turn = await store.get_turn(second_turn["id"])

    assert cancelled_turn is not None
    assert cancelled_turn["status"] == "cancelled"
    assert completed_turn is not None
    assert completed_turn["status"] == "completed"
    messages = await store.get_messages(session["id"])
    cancelled_assistant = [
        item for item in messages
        if item["role"] == "assistant" and "取消" in item["content"]
    ]
    assert cancelled_assistant


@pytest.mark.asyncio
async def test_turn_runtime_fails_closed_for_provider_raw_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            raise RuntimeError("<400> InternalError.Algo.DataInspectionFailed: raw provider rejection")
            yield

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "触发 provider error",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    failed_turn = await store.get_turn(turn["id"])
    messages = await store.get_messages(session["id"])
    error_events = [item for item in events if item.get("type") == "error"]

    assert failed_turn is not None
    assert failed_turn["status"] == "failed"
    assert error_events
    assert "InternalError" not in error_events[-1]["content"]
    assert "DataInspectionFailed" not in error_events[-1]["content"]
    assistant_messages = [item for item in messages if item["role"] == "assistant"]
    assert assistant_messages
    assert "InternalError" not in assistant_messages[-1]["content"]
    assert "DataInspectionFailed" not in assistant_messages[-1]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_coerces_provider_auth_error_returned_as_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": (
                        "Error: {'message': 'Authentication Fails, Your api key: ****486e is invalid', "
                        "'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}"
                    )
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "触发 provider auth error",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    messages = await store.get_messages(session["id"])
    assistant_messages = [item for item in messages if item["role"] == "assistant"]
    result_events = [item for item in events if item.get("type") == "result"]
    assert result_events
    assert result_events[-1]["metadata"]["response"] == "暂时未生成适合直接展示的答案，请重试一次。"
    assert "Authentication Fails" not in result_events[-1]["metadata"]["response"]
    assert "invalid_request_error" not in result_events[-1]["metadata"]["response"]
    assert assistant_messages
    assert assistant_messages[-1]["content"] == "暂时未生成适合直接展示的答案，请重试一次。"
    assert "Authentication Fails" not in assistant_messages[-1]["content"]
    assert "invalid_request_error" not in assistant_messages[-1]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_interaction_hints_as_soft_system_guidance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            captured["history_messages"] = messages
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["config_overrides"] = context.config_overrides
            captured["metadata"] = context.metadata
            captured["conversation_history"] = context.conversation_history
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="好的，我们按学习场景来处理。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道流水施工的题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "preferred_question_type": "choice",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["preferences"]["interaction_hints"]["profile"] == "tutorbot"
    assert detail["preferences"]["interaction_hints"]["preferred_question_type"] == "choice"
    assert "suppress_answer_reveal_on_generate" not in detail["preferences"]["interaction_hints"]
    assert "interaction_hints" not in captured["config_overrides"]
    assert captured["metadata"]["interaction_hints"]["profile"] == "tutorbot"
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["escalation_level"] == 1
    assert "suppress_answer_reveal_on_generate" not in captured["metadata"]["interaction_hints"]
    assert captured["conversation_history"] == []


@pytest.mark.asyncio
async def test_turn_runtime_persists_exam_track_as_scoped_runtime_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "不是一建，是一造案例题，按一级造价工程师口径回答",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    config = execution.payload["config"]
    detail = await store.get_session(session["id"])

    assert config["exam_track"] == "first_cost"
    assert config["interaction_hints"]["exam_track"] == "first_cost"
    assert detail is not None
    assert detail["preferences"]["exam_track"] == "first_cost"
    assert detail["preferences"]["interaction_hints"]["exam_track"] == "first_cost"


@pytest.mark.asyncio
async def test_turn_runtime_clears_stored_exam_track_when_user_denies_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.ensure_session(None)
    await store.update_session_preferences(
        session["id"],
        {
            "exam_track": "first_cost",
            "interaction_hints": {
                "profile": "tutorbot",
                "subject_domain": "construction_exam",
                "exam_track": "first_cost",
            },
        },
    )

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "不是一造，这里先按普通建筑实务问题讲",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    detail = await store.get_session(session["id"])

    assert "exam_track" not in execution.payload["config"]
    assert execution.payload["config"]["interaction_hints"]["profile"] == "tutorbot"
    assert "exam_track" not in execution.payload["config"]["interaction_hints"]
    assert detail is not None
    assert detail["preferences"].get("exam_track") == ""
    assert "exam_track" not in detail["preferences"]["interaction_hints"]


@pytest.mark.asyncio
async def test_turn_runtime_does_not_restore_stored_exam_track_for_comparison_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.ensure_session(None)
    await store.update_session_preferences(
        session["id"],
        {
            "exam_track": "first_cost",
            "interaction_hints": {
                "profile": "tutorbot",
                "subject_domain": "construction_exam",
                "exam_track": "first_cost",
            },
        },
    )

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "一建和一造有什么区别？我该怎么选？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    detail = await store.get_session(session["id"])

    assert "exam_track" not in execution.payload["config"]
    assert "exam_track" not in execution.payload["config"]["interaction_hints"]
    assert detail is not None
    assert detail["preferences"]["exam_track"] == "first_cost"
    assert "exam_track" not in detail["preferences"]["interaction_hints"]


@pytest.mark.asyncio
async def test_turn_runtime_normalizes_legacy_mini_tutor_profile_to_tutorbot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["config_overrides"] = dict(context.config_overrides)
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="TutorBot ready",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么叫流水施工？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_profile": "mini_tutor",
                "interaction_hints": {
                    "profile": "mini_tutor",
                    "teaching_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["interaction_hints"]["profile"] == "tutorbot"
    assert captured["config_overrides"]["interaction_profile"] == "tutorbot"
    assert captured["metadata"]["interaction_hints"]["profile"] == "tutorbot"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_treat_default_rag_binding_as_grounding_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一般讲解。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "general_learning_query"


@pytest.mark.asyncio
async def test_turn_runtime_preserves_auto_capability_selection_when_unspecified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["user_message"] = context.user_message
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="### Question 1\n流水施工中，流水步距反映什么？",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道流水施工的题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert captured["active_capability"] is None
    assert captured["user_message"] == "考我一道流水施工的题"

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_question"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"
    assert [event["type"] for event in events] == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_marks_explicit_chat_mode_in_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "解释一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"chat_mode": "fast"},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert captured["chat_mode_explicit"] is True
    assert [event["type"] for event in events] == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_uses_canonical_requested_response_mode_to_set_explicit_chat_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "解释一下屋面防水等级",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "requested_response_mode": "fast",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert captured["chat_mode"] == "fast"
    assert captured["chat_mode_explicit"] is True
    assert detail["preferences"]["chat_mode"] == "fast"
    assert [event["type"] for event in events] == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_prefers_requested_response_mode_hint_when_chat_mode_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode via requested_response_mode",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "简要说明流水节拍",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "requested_response_mode": "fast",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert captured["chat_mode"] == "fast"
    assert captured["chat_mode_explicit"] is True
    assert detail["preferences"]["chat_mode"] == "fast"
    assert [event["type"] for event in events] == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_trace_requested_response_mode_records_selected_mode_for_smart_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": "smart mode from chat_mode",
                    "metadata": {},
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_fast_policy",
                    "exact_fast_path_hit": False,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "概括一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_turn_runtime_open_chat_active_object_does_not_force_deep_mode_for_smart_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["active_object"] = context.metadata.get("active_object")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "简短回答",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session = await store.create_session(session_id="session_open_chat_mode", title="新对话")
    active_object = build_active_object_from_session(session)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么是流水节拍，简单说一下",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    assert captured["active_object"]["object_type"] == "open_chat_topic"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"
    assert metadata["execution_path"] == "tutorbot_fast_policy"


@pytest.mark.asyncio
async def test_turn_runtime_separates_requested_smart_from_selected_fast_in_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "简短回答",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么是流水节拍，简单说一下",
            "session_id": None,
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"
    assert metadata["execution_path"] == "tutorbot_fast_policy"
    assert metadata["exact_fast_path_hit"] is False


def test_bind_authenticated_user_promotes_legacy_response_mode_hints() -> None:
    payload = {
        "type": "start_turn",
        "config": {
            "requested_response_mode": "deep",
            "teaching_mode": "fast",
            "interaction_hints": {
                "profile": "tutorbot",
                "requested_response_mode": "smart",
            },
        },
    }

    bound = unified_ws_module._bind_authenticated_user(payload, current_user=None)
    config = bound["config"]
    hints = config["interaction_hints"]

    assert hints["profile"] == "tutorbot"
    assert hints["requested_response_mode"] == "smart"
    assert "teaching_mode" not in hints
    assert "requested_response_mode" not in config
    assert "teaching_mode" not in config


@pytest.mark.asyncio
async def test_turn_runtime_captures_points_for_mini_program_turns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一次会扣分的回复。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeMemberService:
        def record_chat_learning(self, user_id: str, *, query: str, assistant_content: str):
            captured["learning_user_id"] = user_id
            captured["learning_query"] = query
            captured["learning_content"] = assistant_content
            return {"today_done": 1}

    class FakeWalletService:
        is_configured = True

        def capture_points(
            self,
            *,
            user_id: str,
            amount_points: int,
            idempotency_key: str,
            reference_id: str,
            reason: str = "capture",
            reference_type: str = "ai_usage",
            metadata: dict[str, object] | None = None,
        ):
            captured["wallet_user_id"] = user_id
            captured["amount_points"] = amount_points
            captured["idempotency_key"] = idempotency_key
            captured["reference_id"] = reference_id
            captured["reason"] = reason
            captured["reference_type"] = reference_type
            captured["capture_metadata"] = dict(metadata or {})
            return {"captured": amount_points}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: FakeMemberService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FakeWalletService(),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                    "wallet_user_id": "wallet_demo",
                    "learning_user_id": "learner_demo",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    assert captured == {
        "wallet_user_id": "wallet_demo",
        "amount_points": 20,
        "idempotency_key": f"mini_program_capture:{turn['id']}",
        "reference_id": turn["id"],
        "reason": "capture",
        "reference_type": "ai_usage",
        "capture_metadata": {
            "source": "wx_miniprogram",
            "turn_id": turn["id"],
            "session_id": session["id"],
        },
        "learning_user_id": "learner_demo",
        "learning_query": "考我一道题",
        "learning_content": "这是一次会扣分的回复。",
    }


@pytest.mark.asyncio
async def test_turn_runtime_skips_mini_program_capture_without_wallet_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一次不会扣分的回复。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeMemberService:
        def record_chat_learning(self, user_id: str, *, query: str, assistant_content: str):
            captured["learning_user_id"] = user_id
            captured["learning_query"] = query
            captured["learning_content"] = assistant_content
            return {"today_done": 1}

    class FakeWalletService:
        is_configured = True

        def capture_points(self, **_kwargs):
            captured["wallet_capture_called"] = True
            return {"captured": 20}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: FakeMemberService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FakeWalletService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续解释这道题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                    "learning_user_id": "learner_demo",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    assert captured == {
        "learning_user_id": "learner_demo",
        "learning_query": "继续解释这道题",
        "learning_content": "这是一次不会扣分的回复。",
    }


@pytest.mark.asyncio
async def test_turn_runtime_rejects_deep_research_without_explicit_config(
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    with pytest.raises(RuntimeError, match="Invalid deep research config"):
        await runtime.start_turn(
            {
                "type": "start_turn",
                "content": "research transformers",
                "session_id": None,
                "capability": "deep_research",
                "tools": ["rag"],
                "knowledge_bases": ["research-kb"],
                "attachments": [],
                "language": "en",
                "config": {},
            }
        )


@pytest.mark.asyncio
async def test_turn_runtime_persists_deep_research_session_preference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_research",
                stage="reporting",
                content="Research report ready.",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_research")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "research transformers",
            "session_id": None,
            "capability": "deep_research",
            "tools": ["rag", "web_search"],
            "knowledge_bases": ["research-kb"],
            "attachments": [],
            "language": "en",
            "config": {
                "mode": "report",
                "depth": "standard",
                "sources": ["kb", "web"],
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_research"
    assert detail["preferences"]["tools"] == ["rag", "web_search"]


@pytest.mark.asyncio
async def test_turn_runtime_injects_memory_and_refreshes_after_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["conversation_history"] = context.conversation_history
            captured["memory_context"] = context.memory_context
            captured["conversation_context_text"] = context.metadata.get("conversation_context_text")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Stored reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    refresh_calls: list[dict[str, object]] = []

    async def fake_refresh_from_turn(**kwargs):
        refresh_calls.append(kwargs)
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "## Memory\n## Preferences\n- Prefer concise answers.",
            refresh_from_turn=fake_refresh_from_turn,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello, i'm frank",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    await asyncio.sleep(0)

    assert captured["memory_context"] == "## Memory\n## Preferences\n- Prefer concise answers."
    assert captured["conversation_history"] == []
    assert captured["conversation_context_text"] == "Recent chat summary"
    assert refresh_calls[0]["assistant_message"] == "Stored reply"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_block_done_on_background_memory_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="后台刷新前先返回",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    async def fake_refresh_from_turn(**kwargs):
        refresh_started.set()
        await release_refresh.wait()
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "## Memory\n- fast",
            refresh_from_turn=fake_refresh_from_turn,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async def _collect() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
            events.append(event)
        return events

    events = await asyncio.wait_for(_collect(), timeout=0.5)
    assert [event["type"] for event in events] == ["session", "content", "done"]

    await asyncio.wait_for(refresh_started.wait(), timeout=0.5)
    release_refresh.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_skips_heavy_context_for_low_signal_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"notebook_called": False}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["notebook_context"] = context.notebook_context
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="当前还剩 20 点。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeNotebookManager:
        def get_records_by_references(self, _refs):
            captured["notebook_called"] = True
            return [{"id": "note_1", "title": "不应加载", "summary": "不应出现"}]

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.notebook.notebook_manager", FakeNotebookManager())
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "还有多少点数",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "notebook_references": [{"notebook_id": "nb_1", "id": "rec_1"}],
            "history_references": ["session_prev"],
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["user_message"] == "还有多少点数"
    assert captured["notebook_context"] == ""
    assert captured["history_context"] == ""
    assert captured["metadata"]["context_route"] == "low_signal_social"
    assert captured["metadata"]["loaded_sources"] == []
    assert captured["notebook_called"] is False


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_loads_history_evidence_for_cross_session_recall(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话")
    await store.update_summary(
        history_session["id"],
        "之前建议先复习流水施工，再做网络计划，最后回到案例题。",
        0,
    )
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工，再做网络计划。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="上次我建议你先复习流水施工。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "history_references": [history_session["id"]],
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["escalation_attempts"] == [1, 2, 3]
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "target_level_reached"
    assert "history" in captured["metadata"]["loaded_sources"]
    assert "blocks" in captured["metadata"]["context_pack_trace"]
    assert captured["metadata"]["context_pack_trace"]["blocks"]["evidence"]["selected_candidates"]
    assert "之前建议先复习流水施工" in captured["history_context"]
    assert "参考证据" in captured["user_message"]
    assert "当前用户问题" in captured["user_message"]


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_implicitly_recalls_cross_session_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话", owner_key=build_user_owner_key("student_demo"))
    await store.update_summary(
        history_session["id"],
        "之前建议先复习流水施工，再做网络计划，最后回到案例题。",
        0,
    )
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工，再做网络计划。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="上次我建议你先复习流水施工。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                }
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["history_search_applied"] is True
    assert captured["metadata"]["escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["escalation_attempts"] == [1, 2, 3]
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "target_level_reached"
    assert "history" in captured["metadata"]["loaded_sources"]
    assert "Title: 历史会话" in captured["history_context"]
    assert "之前建议先复习流水施工" in captured["history_context"]


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_respects_history_source_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话", owner_key=build_user_owner_key("student_demo"))
    await store.update_summary(history_session["id"], "之前建议先复习流水施工。", 0)
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这轮不应加载历史证据。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                },
                "context_sources": {
                    "history": False,
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["history_search_applied"] is False
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["source_flags"]["history"] is False
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "source_flag_disabled:history"
    assert "history" not in captured["metadata"]["loaded_sources"]
    assert captured["history_context"] == ""


@pytest.mark.asyncio
async def test_turn_runtime_can_fallback_to_legacy_context_builder_by_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="legacy-summary",
                context_text="legacy-context",
                token_count=16,
                budget=128,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            captured["user_message"] = context.user_message
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="走旧链路。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下这个概念",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "context_orchestration_enabled": False,
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["fallback_path"] == "legacy"
    assert captured["metadata"]["escalation_level"] == 0
    assert captured["metadata"]["context_pack_trace"]["fallback_path"] == "legacy"
    assert captured["metadata"]["context_pack_trace"]["fallback_stage"] == "legacy_flag"
    assert captured["metadata"]["context_pack_trace"]["fallback_reason"] == "context_orchestration_disabled"
    assert captured["user_message"] == "请讲解一下这个概念"


@pytest.mark.asyncio
async def test_turn_runtime_records_stage_specific_orchestration_fallback_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class BrokenContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            raise RuntimeError("builder boom")

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="已退回旧链路。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", BrokenContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下这个概念",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["fallback_path"] == "legacy_context_builder:session_history"
    assert captured["metadata"]["escalation_level"] == 0
    assert captured["metadata"]["context_pack_trace"]["fallback_path"] == "legacy_context_builder:session_history"
    assert captured["metadata"]["context_pack_trace"]["fallback_stage"] == "session_history"
    assert captured["metadata"]["context_pack_trace"]["fallback_reason"] == "RuntimeError"


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_prioritizes_active_plan_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeLearningPlanService:
        def read_guided_session_view(self, plan_id: str):
            if plan_id != "plan_demo":
                return None
            return {
                "session_id": "plan_demo",
                "user_id": "",
                "status": "in_progress",
                "current_index": 1,
                "summary": "当前正在学流水施工与网络计划。",
                "notebook_id": "nb_demo",
                "notebook_name": "施工组织",
                "progress": 50,
                "ready_count": 2,
                "page_count": 3,
                "pages": [
                    {
                        "page_index": 0,
                        "knowledge_title": "流水施工基础",
                        "knowledge_summary": "先理解流水节拍与流水步距。",
                        "user_difficulty": "medium",
                    },
                    {
                        "page_index": 1,
                        "knowledge_title": "网络计划关键线路",
                        "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
                        "user_difficulty": "hard",
                    },
                ],
            }

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续当前学习页面。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learning_plan.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_sources.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才这个学习页面",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"active_plan_id": "plan_demo"},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "guided_plan_continuation"
    assert captured["metadata"]["active_object"]["object_type"] == "guide_page"
    assert captured["metadata"]["active_object"]["state_snapshot"]["plan_id"] == "plan_demo"
    assert "question_followup_context" not in captured["metadata"]
    assert "question_followup_action" not in captured["metadata"]
    assert "active_plan" in captured["metadata"]["loaded_sources"]
    assert "网络计划关键线路" in captured["user_message"]
    assert "当前用户问题" in captured["user_message"]

    stored_active_object = await store.get_active_object(session["id"])
    assert stored_active_object is not None
    assert stored_active_object["object_type"] == "guide_page"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_guided_plan_active_object_without_repassing_plan_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeLearningPlanService:
        def read_guided_session_view(self, plan_id: str):
            if plan_id != "plan_demo":
                return None
            return {
                "session_id": "plan_demo",
                "user_id": "",
                "status": "in_progress",
                "current_index": 1,
                "summary": "当前正在学流水施工与网络计划。",
                "notebook_id": "nb_demo",
                "notebook_name": "施工组织",
                "progress": 50,
                "ready_count": 2,
                "page_count": 3,
                "pages": [
                    {
                        "page_index": 1,
                        "knowledge_title": "网络计划关键线路",
                        "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
                        "user_difficulty": "hard",
                    },
                ],
            }

    class FakeOrchestrator:
        async def handle(self, context):
            captured.append(
                {
                    "user_message": context.user_message,
                    "metadata": context.metadata,
                }
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续当前学习页面。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learning_plan.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_sources.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才这个学习页面",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"active_plan_id": "plan_demo"},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn_payload = {
        "type": "start_turn",
        "content": "继续刚才这个学习页面",
        "session_id": session["id"],
        "capability": None,
        "tools": [],
        "knowledge_bases": [],
        "attachments": [],
        "language": "zh",
        "config": {},
    }
    _session, second_turn = await runtime.start_turn(second_turn_payload)
    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    assert len(captured) == 2
    second_metadata = captured[1]["metadata"]
    assert second_metadata["active_object"]["object_type"] == "guide_page"
    assert second_metadata["active_object"]["state_snapshot"]["plan_id"] == "plan_demo"
    assert second_metadata["context_route"] == "guided_plan_continuation"
    assert "active_plan" in second_metadata["loaded_sources"]


@pytest.mark.asyncio
async def test_turn_runtime_uses_user_scoped_learner_state_when_user_id_is_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"global_memory_called": False, "global_refresh_called": False}
    refresh_calls: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["memory_context"] = context.memory_context
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="User scoped reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, *, user_id: str, language: str = "en", max_chars: int = 5000):
            captured["learner_user_id"] = user_id
            captured["learner_language"] = language
            return "## 学员级长期状态\n### Student Profile\n- user: student_demo"

        async def refresh_from_turn(self, **kwargs):
            refresh_calls.append(kwargs)
            return None

    class FakeOverlayService:
        def read_overlay(self, bot_id: str, user_id: str):
            captured["overlay_read"] = {"bot_id": bot_id, "user_id": user_id}
            return {
                "effective_overlay": {},
                "promotion_candidates": [],
                "heartbeat_override_candidate": {},
            }

        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, *, source_feature: str, source_id: str):
            captured["overlay_patch"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "patch": patch,
                "source_feature": source_feature,
                "source_id": source_id,
            }
            return {"effective_overlay": {}}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            captured["overlay_promotions"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "min_confidence": min_confidence,
                "max_candidates": max_candidates,
                "learner_state_service_type": learner_state_service.__class__.__name__,
            }
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    async def _unexpected_global_refresh(**_kwargs):
        captured["global_refresh_called"] = True
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: captured.__setitem__("global_memory_called", True) or "## Global Memory",
            refresh_from_turn=_unexpected_global_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续我的专项训练",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    assert captured["memory_context"] == "## 学员级长期状态\n### Student Profile\n- user: student_demo"
    assert captured["learner_user_id"] == "student_demo"
    assert captured["global_memory_called"] is False
    assert captured["global_refresh_called"] is False
    assert captured["overlay_read"] == {
        "bot_id": "construction-exam-coach",
        "user_id": "student_demo",
    }
    assert captured["overlay_patch"]["bot_id"] == "construction-exam-coach"
    assert captured["overlay_patch"]["source_feature"] == "turn"
    assert captured["overlay_promotions"]["bot_id"] == "construction-exam-coach"
    assert refresh_calls[0]["user_id"] == "student_demo"
    assert refresh_calls[0]["assistant_message"] == "User scoped reply"
    assert refresh_calls[0]["source_bot_id"] == "construction-exam-coach"


@pytest.mark.asyncio
async def test_turn_runtime_uses_guide_completion_summary_from_real_learner_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            return tmp_path / "learner_state"

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "地基基础",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    async def _no_summary_rewrite(**_kwargs):
        yield "NO_CHANGE"

    learner_state_service = LearnerStateService(
        path_service=PathServiceStub(),
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    await learner_state_service.record_guide_completion(
        user_id="student_demo",
        guide_id="guide_foundation_1",
        notebook_name="地基基础",
        summary="已完成地基承载力与沉降控制的引导学习，下一步应做案例题巩固。",
        knowledge_points=[
            {
                "knowledge_title": "地基承载力验算",
                "knowledge_summary": "先明确承载力修正与基础埋深。",
                "user_difficulty": "hard",
            }
        ],
        source_bot_id="construction-exam-coach",
    )

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"global_memory_called": False}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["memory_context"] = context.memory_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="下一步做案例题巩固。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeOverlayService:
        def read_overlay(self, _bot_id: str, _user_id: str):
            return {"effective_overlay": {}, "promotion_candidates": [], "heartbeat_override_candidate": {}}

        def patch_overlay(self, *_args, **_kwargs):
            return {"effective_overlay": {}}

        def apply_promotions(self, *_args, **_kwargs):
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _no_summary_rewrite)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: captured.__setitem__("global_memory_called", True) or "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: learner_state_service,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我下一步应该怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    memory_context = str(captured["memory_context"])
    assert captured["global_memory_called"] is False
    assert "最近完成的引导学习" in memory_context
    assert "已完成地基承载力与沉降控制的引导学习" in memory_context
    assert "地基承载力验算" in memory_context


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_loads_bot_overlay_into_context_pack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["memory_context"] = context.memory_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续专项训练。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context_candidates(self, *, user_id: str, query: str, route: str, language: str = "en"):
            captured["learner_context_request"] = {
                "user_id": user_id,
                "query": query,
                "route": route,
                "language": language,
            }
            return {
                "learner_candidates": [],
                "memory_candidates": [],
            }

        async def refresh_from_turn(self, **_kwargs):
            return None

    class FakeOverlayService:
        def read_overlay(self, bot_id: str, user_id: str):
            captured["overlay_request"] = {"bot_id": bot_id, "user_id": user_id}
            return {
                "effective_overlay": {
                    "local_focus": {
                        "current_goal": "聚焦建筑案例题第 2 问",
                        "teaching_intent": "保持追问，不要切题",
                    },
                    "working_memory_projection": "刚才停在案例题第 2 问，先完成关键线路判断。",
                }
            }

        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, *, source_feature: str, source_id: str):
            captured["overlay_patch"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "patch": patch,
                "source_feature": source_feature,
                "source_id": source_id,
            }
            return {"effective_overlay": {}}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            captured["overlay_promotions"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "min_confidence": min_confidence,
                "max_candidates": max_candidates,
            }
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才的专项训练",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_overlay",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    metadata = dict(captured["metadata"])
    trace = dict(metadata["context_pack_trace"])
    learner_selected = list(trace["blocks"]["learner"]["selected_candidates"])
    evidence_selected = list(trace["blocks"]["evidence"]["selected_candidates"])

    assert captured["overlay_request"] == {
        "bot_id": "construction-exam-coach",
        "user_id": "student_overlay",
    }
    assert captured["learner_context_request"] == {
        "user_id": "student_overlay",
        "query": "继续刚才的专项训练",
        "route": metadata["context_route"],
        "language": "zh",
    }
    assert "overlay" in metadata["loaded_sources"]
    assert "overlay" in metadata["candidate_sources"]
    assert int(trace["overlay_candidate_count"]) >= 2
    assert any(
        str(item.get("metadata", {}).get("source_tag", "")) == "overlay_local_focus"
        for item in learner_selected
    )
    assert any(
        str(item.get("metadata", {}).get("source_tag", "")) == "overlay_working_memory"
        for item in evidence_selected
    )
    assert "Bot 局部 Focus" in str(captured["memory_context"])
    assert "刚才停在案例题第 2 问" in str(captured["user_message"])
    assert "当前用户问题" in str(captured["user_message"])
    assert captured["overlay_patch"]["bot_id"] == "construction-exam-coach"
    assert captured["overlay_patch"]["source_feature"] == "turn"
    assert captured["overlay_promotions"]["bot_id"] == "construction-exam-coach"


@pytest.mark.asyncio
async def test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.learner_state.overlay_service import BotLearnerOverlayService
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            path = tmp_path / "learner_state"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "案例题",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    async def _no_summary_rewrite(**_kwargs):
        yield "NO_CHANGE"

    path_service = PathServiceStub()
    learner_state_service = LearnerStateService(
        path_service=path_service,
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    overlay_service = BotLearnerOverlayService(path_service=path_service)
    overlay_service.promote_candidate(
        "case-study-coach",
        "student_demo",
        "possible_weak_point",
        {
            "topic": "防火间距",
            "confidence": 0.93,
            "promotion_basis": "structured_result",
        },
        source_feature="quiz",
        source_id="quiz_case_1",
    )

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_contexts: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured_contexts.append(
                {
                    "user_message": context.user_message,
                    "memory_context": context.memory_context,
                    "metadata": context.metadata,
                }
            )
            reply = "已记录本轮案例题复习。" if len(captured_contexts) == 1 else "已读取你的薄弱点。"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content=reply,
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _no_summary_rewrite)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: learner_state_service,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: overlay_service,
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我刚做完案例题，帮我记录一下。",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "case-study-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    progress = learner_state_service.read_progress("student_demo")
    weak_points = list((progress.get("knowledge_map") or {}).get("weak_points") or [])
    assert "防火间距" in weak_points
    assert overlay_service.read_overlay("case-study-coach", "student_demo")["promotion_candidates"] == []
    assert any(
        event.memory_kind == "overlay_promotion"
        and (event.payload_json.get("payload") or {}).get("topic") == "防火间距"
        for event in learner_state_service.list_memory_events("student_demo", limit=20)
    )

    _session, second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "回顾一下之前记录的防火间距薄弱点。",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "case-study-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    assert len(captured_contexts) >= 2
    second_context = captured_contexts[-1]
    assert "防火间距" in str(second_context["user_message"])
    assert "overlay_promotion" in str(second_context["user_message"])
    assert "learner_progress" in str(second_context["memory_context"])
    assert "memory" in dict(second_context["metadata"]).get("candidate_sources", [])


@pytest.mark.asyncio
async def test_turn_runtime_injects_tutorbot_default_knowledge_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["enabled_tools"] = context.enabled_tools
            captured["knowledge_bases"] = context.knowledge_bases
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="知识链已启用",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请分析这道建筑案例题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_profile": "tutorbot",
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    assert captured["enabled_tools"] == ["rag"]
    assert captured["knowledge_bases"] == ["construction-exam"]

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["tools"] == ["rag"]
    assert detail["preferences"]["knowledge_bases"] == ["construction-exam"]
