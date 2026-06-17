from __future__ import annotations

import asyncio
import contextlib
import sys
import types
from types import MethodType
from types import SimpleNamespace

import pytest

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
    info=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
    debug=lambda *args, **kwargs: None,
    exception=lambda *args, **kwargs: None,
)
sys.modules.setdefault("loguru", fake_loguru)

fake_tiktoken = types.ModuleType("tiktoken")
fake_tiktoken.get_encoding = lambda _name: SimpleNamespace(encode=lambda text: list(str(text or "")))  # type: ignore[attr-defined]
sys.modules.setdefault("tiktoken", fake_tiktoken)

from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key
import deeptutor.services.tutorbot.manager as tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig, TutorBotManager
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.tutorbot.session.manager import Session
from deeptutor.tutorbot.session.sqlite_adapter import SQLiteSessionAdapter


def test_tutorbot_sqlite_adapter_persists_metadata_and_stable_messages(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"

    session = Session(
        key=key,
        metadata={
            "bot_id": "construction-exam-coach",
            "conversation_id": "c1",
            "user_id": "u1",
            "source": "wx_miniprogram",
            "title": "案例题会话",
            "archived": False,
        },
        messages=[
            {"role": "user", "content": "第一问"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "rag", "arguments": "{\"query\":\"防水等级\"}"},
                    }
                ],
            },
            {"role": "tool", "content": "知识库命中", "tool_call_id": "call_1", "name": "rag"},
            {"role": "assistant", "content": "最终答案"},
        ],
    )

    adapter.save(session)
    adapter.invalidate(key)

    restored = adapter.get_or_create(key)
    assert restored.metadata["bot_id"] == "construction-exam-coach"
    assert restored.metadata["conversation_id"] == "c1"
    assert restored.metadata["user_id"] == "u1"
    assert restored.metadata["source"] == "wx_miniprogram"
    assert restored.metadata["title"] == "案例题会话"
    assert [item["role"] for item in restored.messages] == ["user", "assistant"]
    assert [item["content"] for item in restored.messages] == ["第一问", "最终答案"]

    row = asyncio.run(store.get_session(f"tutorbot:{key}"))
    assert row is not None
    assert row["title"] == "案例题会话"
    assert row["preferences"]["bot_id"] == "construction-exam-coach"
    assert row["preferences"]["conversation_id"] == "c1"
    assert row["preferences"]["user_id"] == "u1"


def test_tutorbot_general_knowledge_context_respects_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_resolve(*args, **kwargs):
        raise AssertionError("resolver should not run when kill switch is off")

    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", "false")
    monkeypatch.setattr(tutorbot_manager, "resolve_general_knowledge_context", _fail_resolve)
    metadata = {"user_id": "qa_user_1", "conversation_context_text": "已有上下文"}

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert metadata["conversation_context_text"] == "已有上下文"
    assert metadata["luban_general_knowledge_context_status"] == "killed_by_switch"
    assert "luban_general_knowledge_context" not in metadata


def test_tutorbot_general_knowledge_context_respects_optional_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_resolve(*args, **kwargs):
        raise AssertionError("resolver should not run outside configured cohort")

    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", "qa_,operator_")
    monkeypatch.setattr(tutorbot_manager, "resolve_general_knowledge_context", _fail_resolve)
    metadata = {"user_id": "real_user_1"}

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert metadata["luban_general_knowledge_context_status"] == "cohort_miss"
    assert "luban_general_knowledge_context" not in metadata


def test_tutorbot_general_knowledge_context_defaults_to_shadow_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_resolve(*args, **kwargs):
        raise AssertionError("resolver should not run without explicit shadow opt-in")

    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", raising=False)
    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", raising=False)
    monkeypatch.setattr(tutorbot_manager, "resolve_general_knowledge_context", _fail_resolve)
    metadata = {"user_id": "real_user_1"}

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert metadata["luban_general_knowledge_context_status"] == "shadow_not_enabled"
    assert "luban_general_knowledge_context" not in metadata


def test_tutorbot_general_knowledge_context_allows_explicit_shadow_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "confidence": {"status": "high"},
        "sources": {"textbook": [{"text_preview": "建筑高度大于27m的住宅为高层住宅"}]},
    }

    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", raising=False)
    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", raising=False)
    monkeypatch.setattr(tutorbot_manager, "resolve_general_knowledge_context", lambda *args, **kwargs: pack)
    monkeypatch.setattr(tutorbot_manager, "format_general_knowledge_grounding", lambda _pack: "compiled grounding")
    metadata = {"user_id": "real_user_1", "general_knowledge_context": True}

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert metadata["luban_general_knowledge_context"] == pack
    assert metadata["conversation_context_text"] == "compiled grounding"


def test_tutorbot_general_knowledge_context_ignores_open_chat_topic_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "confidence": {"status": "high"},
        "sources": {"textbook": [{"text_preview": "建筑高度大于27m的住宅为高层住宅"}]},
    }

    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", raising=False)
    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", raising=False)
    monkeypatch.setattr(tutorbot_manager, "resolve_general_knowledge_context", lambda *args, **kwargs: pack)
    monkeypatch.setattr(tutorbot_manager, "format_general_knowledge_grounding", lambda _pack: "compiled grounding")
    metadata = {
        "user_id": "real_user_1",
        "general_knowledge_context": True,
        "active_object": {
            "object_type": "open_chat_topic",
            "state_snapshot": {"title": "高层住宅"},
        },
    }

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert metadata["luban_general_knowledge_context"] == pack
    assert metadata["conversation_context_text"] == "compiled grounding"


def test_tutorbot_sqlite_adapter_repeated_save_does_not_duplicate_final_answer(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"

    session = Session(
        key=key,
        messages=[
            {"role": "user", "content": "建筑构造是什么？"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "rag", "arguments": "{\"query\":\"建筑构造\"}"},
                    }
                ],
            },
            {"role": "tool", "content": "知识库命中", "tool_call_id": "call_1", "name": "rag"},
            {"role": "assistant", "content": "现在我来给你一个完整的解释。"},
        ],
    )

    adapter.save(session)
    adapter.save(session)
    adapter.invalidate(key)

    restored = adapter.get_or_create(key)
    assert [item["content"] for item in restored.messages] == [
        "建筑构造是什么？",
        "现在我来给你一个完整的解释。",
    ]


def test_tutorbot_sqlite_adapter_load_failure_is_not_treated_as_missing_session(tmp_path) -> None:
    class BrokenStore:
        def _get_session_sync(self, _session_id: str):
            raise RuntimeError("sqlite unavailable")

        def _get_messages_sync(self, _session_id: str):
            return []

    adapter = SQLiteSessionAdapter(BrokenStore())

    with pytest.raises(RuntimeError, match="sqlite unavailable"):
        adapter.get_or_create("bot:demo:user:u1:chat:c1")


@pytest.mark.asyncio
async def test_tutorbot_sqlite_adapter_save_uses_spawn_task_on_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    class Store:
        pass

    spawned: dict[str, object] = {}

    def fake_spawn_task(coro, *, name=None, on_error=None):
        spawned["name"] = name
        spawned["on_error"] = on_error
        task = asyncio.create_task(coro)
        return task

    async def fake_save_async(_session: Session) -> None:
        spawned["saved"] = True

    monkeypatch.setattr(
        "deeptutor.tutorbot.session.sqlite_adapter.spawn_task",
        fake_spawn_task,
    )
    adapter = SQLiteSessionAdapter(Store())
    monkeypatch.setattr(adapter, "_save_async", fake_save_async)

    adapter.save(Session(key="bot:demo:user:u1:chat:c1"))
    await asyncio.sleep(0)

    assert spawned["name"] == "tutorbot.sqlite.save:bot:demo:user:u1:chat:c1"
    assert spawned["saved"] is True


@pytest.mark.asyncio
async def test_tutorbot_sqlite_adapter_ensure_and_save_share_session_create_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RacingStore:
        def __init__(self) -> None:
            self.sessions: dict[str, dict] = {}
            self.create_calls = 0
            self.first_create_entered = asyncio.Event()
            self.release_create = asyncio.Event()

        def _get_session_sync(self, _session_id: str):
            return None

        def _get_messages_sync(self, _session_id: str):
            return []

        async def get_session(self, session_id: str):
            return self.sessions.get(session_id)

        async def create_session(self, *, session_id: str, **kwargs):
            self.create_calls += 1
            if self.create_calls == 1:
                self.first_create_entered.set()
            await self.release_create.wait()
            if session_id in self.sessions:
                raise RuntimeError("duplicate session create")
            self.sessions[session_id] = {"id": session_id, **kwargs}

        async def update_session_preferences(self, *_args, **_kwargs):
            return None

        async def get_messages(self, _session_id: str):
            return []

        async def add_message(self, *_args, **_kwargs):
            return None

    tasks: list[asyncio.Task] = []

    def fake_spawn_task(coro, *, name=None, on_error=None):
        task = asyncio.create_task(coro, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(
        "deeptutor.tutorbot.session.sqlite_adapter.spawn_task",
        fake_spawn_task,
    )
    store = RacingStore()
    adapter = SQLiteSessionAdapter(store)

    session = adapter.get_or_create("bot:demo:user:u1:chat:c1")
    session.messages.append({"role": "user", "content": "hello"})
    adapter.save(session)
    await asyncio.wait_for(store.first_create_entered.wait(), timeout=0.1)
    await asyncio.sleep(0)
    create_calls_before_release = store.create_calls
    store.release_create.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert create_calls_before_release == 1
    assert not [result for result in results if isinstance(result, RuntimeError)]


def test_tutorbot_sqlite_adapter_rewrites_legacy_noisy_session_before_appending(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"
    session_id = f"tutorbot:{key}"

    asyncio.run(
        store.create_session(
            title="案例题会话",
            session_id=session_id,
            owner_key=build_user_owner_key("u1"),
            source="wx_miniprogram",
            archived=False,
        )
    )
    legacy_messages = [
        {"role": "user", "content": "第一问", "timestamp": "t1"},
        {"role": "assistant", "content": "我先查一下。", "timestamp": "t2"},
        {"role": "tool", "content": "知识库命中", "tool_call_id": "call_1", "name": "rag", "timestamp": "t3"},
        {"role": "assistant", "content": "第一问答案", "timestamp": "t4"},
    ]
    for message in legacy_messages:
        asyncio.run(
            store.add_message(
                session_id=session_id,
                role=message["role"],
                content=message["content"],
                capability="tutorbot",
                events=[{"_tutorbot_message": dict(message)}],
            )
        )

    session = Session(
        key=key,
        metadata={
            "bot_id": "construction-exam-coach",
            "conversation_id": "c1",
            "user_id": "u1",
            "source": "wx_miniprogram",
            "title": "案例题会话",
        },
        messages=legacy_messages
        + [
            {"role": "user", "content": "第二问", "timestamp": "t5"},
            {"role": "assistant", "content": "第二问答案", "timestamp": "t6"},
        ],
    )

    adapter.save(session)
    adapter.invalidate(key)

    restored = adapter.get_or_create(key)
    assert [item["role"] for item in restored.messages] == ["user", "assistant", "user", "assistant"]
    assert [item["content"] for item in restored.messages] == ["第一问", "第一问答案", "第二问", "第二问答案"]


def test_tutorbot_sqlite_adapter_normalizes_none_content_from_stored_tutorbot_messages(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"
    session_id = f"tutorbot:{key}"

    asyncio.run(
        store.create_session(
            title="案例题会话",
            session_id=session_id,
            owner_key=build_user_owner_key("u1"),
            source="wx_miniprogram",
            archived=False,
        )
    )
    asyncio.run(
        store.add_message(
            session_id=session_id,
            role="assistant",
            content="",
            capability="tutorbot",
            events=[
                {
                    "_tutorbot_message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "rag", "arguments": "{\"query\":\"防水等级\"}"},
                            }
                        ],
                    }
                }
            ],
        )
    )
    asyncio.run(
        store.add_message(
            session_id=session_id,
            role="tool",
            content="",
            capability="tutorbot",
            events=[
                {
                    "_tutorbot_message": {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "name": "rag",
                        "content": None,
                    }
                }
            ],
        )
    )

    restored = adapter.get_or_create(key)

    assert restored.messages[0]["content"] == ""
    assert restored.messages[1]["content"] == ""


def test_tutorbot_sqlite_adapter_normalizes_multimodal_content_and_drops_reasoning(
    tmp_path,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"
    session_id = f"tutorbot:{key}"

    asyncio.run(
        store.create_session(
            title="案例题会话",
            session_id=session_id,
            owner_key=build_user_owner_key("u1"),
            source="wx_miniprogram",
            archived=False,
        )
    )
    asyncio.run(
        store.add_message(
            session_id=session_id,
            role="assistant",
            content="",
            capability="tutorbot",
            events=[
                {
                    "_tutorbot_message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "看这张图"},
                            {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
                            {"content": "再判断防水等级"},
                        ],
                        "reasoning_content": "private chain of thought",
                    }
                }
            ],
        )
    )

    restored = adapter.get_or_create(key)

    assert restored.messages == [
        {
            "role": "assistant",
            "content": "看这张图 [image] 再判断防水等级",
        }
    ]


def test_tutorbot_manager_reads_conversations_from_sqlite(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    session_id = "tutorbot:bot:construction-exam-coach:user:u1:chat:c1"
    asyncio.run(
        store.create_session(
            title="案例题会话",
            session_id=session_id,
            owner_key=build_user_owner_key("u1"),
            source="wx_miniprogram",
            archived=False,
        )
    )
    asyncio.run(
        store.update_session_preferences(
            session_id,
            {
                "bot_id": "construction-exam-coach",
                "conversation_id": "c1",
                "user_id": "u1",
                "source": "wx_miniprogram",
                "title": "案例题会话",
            },
        )
    )
    asyncio.run(store.add_message(session_id, "user", "背景资料"))
    asyncio.run(store.add_message(session_id, "assistant", "标准答案"))

    other_id = "tutorbot:bot:other-bot:user:u1:chat:other"
    asyncio.run(
        store.create_session(
            title="Other",
            session_id=other_id,
            owner_key=build_user_owner_key("u1"),
            source="wx_miniprogram",
            archived=False,
        )
    )
    asyncio.run(
        store.update_session_preferences(
            other_id,
            {
                "bot_id": "other-bot",
                "conversation_id": "other",
                "user_id": "u1",
            },
        )
    )
    asyncio.run(store.add_message(other_id, "assistant", "other answer"))

    manager = TutorBotManager()
    manager._session_store = store
    manager._discover_bot_ids = MethodType(lambda self: ["construction-exam-coach"], manager)
    manager._load_bot_config = MethodType(
        lambda self, bot_id: BotConfig(name="Construction Exam Coach"),
        manager,
    )

    conversations = manager.list_bot_conversations(
        "construction-exam-coach",
        user_id="u1",
        archived=False,
        limit=20,
    )
    assert len(conversations) == 1
    assert conversations[0]["id"] == "c1"
    assert conversations[0]["title"] == "案例题会话"
    assert conversations[0]["last_message"] == "标准答案"

    messages = manager.get_bot_conversation_messages(
        "construction-exam-coach",
        user_id="u1",
        conversation_id="c1",
    )
    assert messages is not None
    assert [item["content"] for item in messages] == ["背景资料", "标准答案"]

    assert manager.update_bot_conversation_archive(
        "construction-exam-coach",
        user_id="u1",
        conversation_id="c1",
        archived=True,
    )
    archived = manager.list_bot_conversations(
        "construction-exam-coach",
        user_id="u1",
        archived=True,
        limit=20,
    )
    assert len(archived) == 1
    assert archived[0]["id"] == "c1"

    recent = manager.get_recent_active_bots(limit=5)
    assert recent[0]["bot_id"] == "construction-exam-coach"
    assert recent[0]["last_message"] == "标准答案"

    assert manager.delete_bot_conversation(
        "construction-exam-coach",
        user_id="u1",
        conversation_id="c1",
    )
    assert manager.get_bot_conversation_messages(
        "construction-exam-coach",
        user_id="u1",
        conversation_id="c1",
    ) is None


@pytest.mark.asyncio
async def test_tutorbot_manager_send_message_reuses_outer_usage_scope_for_external_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = get_langfuse_observability()
    manager = TutorBotManager()
    captured_update: dict[str, object] = {}

    def _capture_update_observation(*args, **kwargs) -> None:
        captured_update["metadata"] = kwargs.get("metadata")

    monkeypatch.setattr(observability, "update_observation", _capture_update_observation)

    class _FakeSessions:
        def __init__(self) -> None:
            self._session = Session(key="bot:demo:user:u1:chat:c1", metadata={})

        def get_or_create(self, key: str) -> Session:
            self._session.key = key
            return self._session

        def save(self, session: Session) -> None:
            self._session = session

    class _FakeAgentLoop:
        def __init__(self) -> None:
            self.sessions = _FakeSessions()

        async def process_direct(self, *args, **kwargs) -> str:
            metadata = kwargs.get("metadata")
            if isinstance(metadata, dict):
                metadata["skill_stack"] = ["construction-exam-tutor"]
                metadata["skill_trace"] = [
                    {
                        "name": "construction-exam-tutor",
                        "kind": "construction_default",
                        "status": "loaded",
                        "source": "builtin",
                    }
                ]
                metadata["loader_source"] = {"construction-exam-tutor": "builtin"}
                metadata["skill_source_status"] = {
                    "complete": True,
                    "missing_skills": [],
                    "missing_assets": [],
                }
                metadata["llm_stream_telemetry"] = {
                    "call_count": 1,
                    "calls": [
                        {
                            "call_site": "fast_policy",
                            "provider_name": "openai",
                            "stream_content_chunk_count": 2,
                            "stage_timings_ms": {
                                "provider_stream_create": 10.0,
                                "provider_first_content_delta": 25.0,
                                "provider_stream_read": 80.0,
                            },
                        }
                    ],
                }
            observability.record_usage(
                usage_details={"input": 100.0, "output": 20.0, "total": 120.0},
                cost_details={"input": 0.0, "output": 0.0, "total": 0.001},
                source="provider",
                model="deepseek-v3.2",
            )
            return "TutorBot reply"

    pending_task = asyncio.create_task(asyncio.sleep(60))
    manager._bots["demo-bot"] = SimpleNamespace(
        bot_id="demo-bot",
        running=True,
        tasks=[pending_task],
        agent_loop=_FakeAgentLoop(),
        channel_manager=None,
        channel_bindings={},
    )

    try:
        with observability.usage_scope(
            scope_id="outer-turn",
            session_id="mobile-session",
            turn_id="turn-1",
            capability="tutorbot",
        ):
            session_metadata = {
                "session_id": "mobile-session",
                "turn_id": "turn-1",
                "user_id": "u1",
                "source": "wx_miniprogram",
            }
            response = await manager.send_message(
                "demo-bot",
                "建筑构造是什么？",
                session_metadata=session_metadata,
            )
            summary = observability.get_current_usage_summary()
    finally:
        pending_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pending_task

    assert response == "TutorBot reply"
    assert summary is not None
    assert summary["total_tokens"] == 120
    assert summary["measured_calls"] == 1
    assert summary["usage_sources"]["provider"] == 1
    metadata_keys = list(captured_update["metadata"].keys())
    assert metadata_keys.index("skill_stack") < 20
    assert metadata_keys.index("skill_trace") < 20
    assert captured_update["metadata"]["skill_trace"][0]["name"] == "construction-exam-tutor"
    assert captured_update["metadata"]["skill_stack"] == ["construction-exam-tutor"]
    assert captured_update["metadata"]["llm_stream_telemetry"]["calls"][0]["call_site"] == "fast_policy"
    assert session_metadata["llm_stream_telemetry"]["calls"][0]["stage_timings_ms"][
        "provider_first_content_delta"
    ] == 25.0


@pytest.mark.asyncio
async def test_tutorbot_manager_injects_high_confidence_general_knowledge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = TutorBotManager()
    captured_metadata: dict[str, object] = {}
    pack = {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "leaf_name_path": "建筑工程技术 > 建筑高度分类",
        "confidence": {"status": "high", "policy": "query_path_source_alignment_v1"},
        "sources": {"textbook": [{"text_preview": "建筑高度大于27m的住宅为高层住宅"}]},
    }

    def _fake_resolve(question_text, *, learner_context=None, per_source=6):
        assert question_text == "高层住宅的建筑高度是怎么界定的？"
        assert learner_context["question_text"] == question_text
        return pack

    monkeypatch.setattr(
        tutorbot_manager,
        "resolve_general_knowledge_context",
        _fake_resolve,
        raising=False,
    )
    monkeypatch.setattr(
        tutorbot_manager,
        "format_general_knowledge_grounding",
        lambda resolved: "【编译教学上下文】建筑高度大于27m的住宅为高层住宅",
        raising=False,
    )

    class _FakeSessions:
        def __init__(self) -> None:
            self._session = Session(key="bot:demo:user:u1:chat:c1", metadata={})

        def get_or_create(self, key: str) -> Session:
            self._session.key = key
            return self._session

        def save(self, session: Session) -> None:
            self._session = session

    class _FakeAgentLoop:
        def __init__(self) -> None:
            self.sessions = _FakeSessions()

        async def process_direct(self, *args, **kwargs) -> str:
            captured_metadata.update(kwargs.get("metadata") or {})
            return "TutorBot reply"

    pending_task = asyncio.create_task(asyncio.sleep(60))
    manager._bots["demo-bot"] = SimpleNamespace(
        bot_id="demo-bot",
        running=True,
        tasks=[pending_task],
        agent_loop=_FakeAgentLoop(),
        channel_manager=None,
        channel_bindings={},
    )

    try:
        session_metadata = {
            "session_id": "mobile-session",
            "turn_id": "turn-1",
            "user_id": "u1",
            "source": "wx_miniprogram",
            "general_knowledge_context": True,
            "conversation_context_text": "已有对话上下文",
        }
        response = await manager.send_message(
            "demo-bot",
            "高层住宅的建筑高度是怎么界定的？",
            chat_id="c1",
            session_metadata=session_metadata,
        )
    finally:
        pending_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pending_task

    assert response == "TutorBot reply"
    assert captured_metadata["luban_general_knowledge_context"] == pack
    assert session_metadata["luban_general_knowledge_context"] == pack
    assert "已有对话上下文" in str(captured_metadata["conversation_context_text"])
    assert "【编译教学上下文】" in str(captured_metadata["conversation_context_text"])
