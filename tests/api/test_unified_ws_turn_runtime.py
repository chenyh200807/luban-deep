from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key
from deeptutor.services.session.turn_runtime import (
    TurnRuntimeManager,
    _LiveSubscriber,
    _TurnExecution,
)


async def _noop_refresh(**_kwargs):
    return None


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
    assert detail["preferences"] == {
        "archived": False,
        "capability": "chat",
        "chat_mode": get_default_chat_mode(),
        "tools": [],
        "knowledge_bases": [],
        "language": "en",
    }

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
    assert detail["preferences"]["capability"] == "chat"
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
        def capture_points(self, user_id: str, amount: int = 20, reason: str = "capture"):
            captured["user_id"] = user_id
            captured["amount"] = amount
            captured["reason"] = reason
            return {"captured": amount}

        def record_chat_learning(self, user_id: str, *, query: str, assistant_content: str):
            captured["learning_user_id"] = user_id
            captured["learning_query"] = query
            captured["learning_content"] = assistant_content
            return {"today_done": 1}

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

    _, turn = await runtime.start_turn(
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
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert [event["type"] for event in events] == ["session", "content", "done"]
    assert captured == {
        "user_id": "student_demo",
        "amount": 20,
        "reason": "capture",
        "learning_user_id": "student_demo",
        "learning_query": "考我一道题",
        "learning_content": "这是一次会扣分的回复。",
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

    assert captured["memory_context"] == "## Memory\n## Preferences\n- Prefer concise answers."
    assert captured["conversation_history"] == []
    assert captured["conversation_context_text"] == "Recent chat summary"
    assert refresh_calls[0]["assistant_message"] == "Stored reply"


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
                "user_id": "",
                "status": "in_progress",
                "current_index": 1,
                "summary": "当前正在学流水施工与网络计划。",
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

    _session, turn = await runtime.start_turn(
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
    assert "active_plan" in captured["metadata"]["loaded_sources"]
    assert "网络计划关键线路" in captured["user_message"]
    assert "当前用户问题" in captured["user_message"]


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
    assert refresh_calls[0]["user_id"] == "student_demo"
    assert refresh_calls[0]["assistant_message"] == "User scoped reply"
    assert refresh_calls[0]["source_bot_id"] == "construction-exam-coach"


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
