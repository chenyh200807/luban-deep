from __future__ import annotations

import asyncio
import contextlib
import sys
import types
from types import MethodType, SimpleNamespace

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

from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key
import deeptutor.services.tutorbot.manager as tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig, TutorBotManager
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

    restored = asyncio.run(adapter.get_or_create(key))
    assert restored.metadata["bot_id"] == "construction-exam-coach"
    assert restored.metadata["conversation_id"] == "c1"
    # 引擎镜像行不得携带用户身份戳 / 客户端 source（2026-07 双会话根因）：
    # user_id / source 每 turn 由 capability 重新注入，持久化副本必须剥离。
    assert "user_id" not in restored.metadata
    assert restored.metadata["source"] == "tutorbot"
    assert restored.metadata["title"] == "案例题会话"
    assert [item["role"] for item in restored.messages] == ["user", "assistant"]
    assert [item["content"] for item in restored.messages] == ["第一问", "最终答案"]

    row = asyncio.run(store.get_session(f"tutorbot:{key}"))
    assert row is not None
    assert row["title"] == "案例题会话"
    assert row["preferences"]["bot_id"] == "construction-exam-coach"
    assert row["preferences"]["conversation_id"] == "c1"
    assert "user_id" not in row["preferences"]


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

    restored = asyncio.run(adapter.get_or_create(key))
    assert [item["content"] for item in restored.messages] == [
        "建筑构造是什么？",
        "现在我来给你一个完整的解释。",
    ]


def test_tutorbot_sqlite_adapter_persists_raw_user_message_not_prompt_envelope(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    adapter = SQLiteSessionAdapter(store)
    key = "bot:construction-exam-coach:user:u1:chat:c1"
    envelope = (
        "## 参考证据\n"
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
        "### 局部工作记忆投影\n"
        "这里是注入给 LLM 的内部工作记忆。\n\n"
        "## 当前用户问题\n"
        "防水卷材搭接宽度怎么记？"
    )

    session = Session(
        key=key,
        metadata={
            "bot_id": "construction-exam-coach",
            "conversation_id": "c1",
            "user_id": "u1",
            "source": "wx_miniprogram",
            "title": "防水答疑",
        },
        messages=[
            {
                "role": "user",
                "content": envelope,
                "raw_user_message": "防水卷材搭接宽度怎么记？",
            },
            {"role": "assistant", "content": "先按材料和施工方法区分。"},
        ],
    )

    adapter.save(session)
    adapter.invalidate(key)

    restored = asyncio.run(adapter.get_or_create(key))
    assert [item["content"] for item in restored.messages] == [
        "防水卷材搭接宽度怎么记？",
        "先按材料和施工方法区分。",
    ]
    rows = asyncio.run(store.get_messages(f"tutorbot:{key}"))
    assert rows[0]["content"] == "防水卷材搭接宽度怎么记？"
    assert "参考证据" not in rows[0]["content"]


def test_tutorbot_sqlite_adapter_load_failure_is_not_treated_as_missing_session(tmp_path) -> None:
    class BrokenStore:
        async def get_session(self, _session_id: str):
            raise RuntimeError("sqlite unavailable")

        async def get_messages(self, _session_id: str):
            return []

    adapter = SQLiteSessionAdapter(BrokenStore())

    with pytest.raises(RuntimeError, match="sqlite unavailable"):
        asyncio.run(adapter.get_or_create("bot:demo:user:u1:chat:c1"))


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
    key = "bot:demo:user:u1:chat:c1"

    # get_or_create now awaits its create-session ensure inline (single async
    # interface), so run it as a task and hold it inside create_session while a
    # concurrent save contends for the SAME per-session lock. The lock must
    # serialize both create paths → exactly one create_session, no duplicate.
    get_task = asyncio.create_task(adapter.get_or_create(key))
    await asyncio.wait_for(store.first_create_entered.wait(), timeout=0.1)
    create_calls_before_release = store.create_calls

    session = Session(key=key)
    session.messages.append({"role": "user", "content": "hello"})
    adapter.save(session)  # _save_async spawned; blocks on the held lock
    await asyncio.sleep(0)

    store.release_create.set()
    loaded = await get_task
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert create_calls_before_release == 1
    # save ran after the ensure released the lock; it saw the ensured row and
    # did NOT create a second one.
    assert store.create_calls == 1
    assert not [result for result in results if isinstance(result, RuntimeError)]
    assert loaded.key == key


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

    restored = asyncio.run(adapter.get_or_create(key))
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

    restored = asyncio.run(adapter.get_or_create(key))

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

    restored = asyncio.run(adapter.get_or_create(key))

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

        async def get_or_create(self, key: str) -> Session:
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
async def test_tutorbot_manager_strips_stale_case_grading_receipt_from_non_case_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = get_langfuse_observability()
    manager = TutorBotManager()
    captured_update: dict[str, object] = {}

    def _capture_update_observation(*args, **kwargs) -> None:
        captured_update["metadata"] = kwargs.get("metadata")

    monkeypatch.setattr(observability, "update_observation", _capture_update_observation)

    stale_receipt = {
        "v1_case_graded": True,
        "score_authority": "rubric_scored_v1",
        "grading_to_brain_loop": {"writeback_count": 1},
        "learning_evidence_event_id": "evt-old",
    }

    class _FakeSessions:
        def __init__(self) -> None:
            self._session = Session(
                key="bot:demo:user:u1:chat:c1",
                metadata=dict(stale_receipt),
            )

        async def get_or_create(self, key: str) -> Session:
            self._session.key = key
            return self._session

        def save(self, session: Session) -> None:
            self._session = session

    fake_sessions = _FakeSessions()

    class _FakeAgentLoop:
        def __init__(self) -> None:
            self.sessions = fake_sessions

        async def process_direct(self, *args, **kwargs) -> str:
            metadata = kwargs.get("metadata")
            if isinstance(metadata, dict):
                metadata["question_lifecycle_scene"] = None
                metadata["execution_path"] = "tutorbot_kb_first_full_agent_policy"
            return "已按你的正式提交做了摘要，没有重新判分。"

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
        }
        response = await manager.send_message(
            "demo-bot",
            "总结我正式提交过的案例答案，别重新判分。",
            chat_id="c1",
            session_metadata=session_metadata,
        )
    finally:
        pending_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pending_task

    assert response == "已按你的正式提交做了摘要，没有重新判分。"
    for container in (
        session_metadata,
        fake_sessions._session.metadata,
        captured_update["metadata"],
    ):
        assert isinstance(container, dict)
        for key in stale_receipt:
            assert key not in container


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

        async def get_or_create(self, key: str) -> Session:
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


def _session_columns(db_path, session_id: str) -> tuple[str, str, str] | None:
    """Terminal-state read of (owner_key, source, preferences_json) straight from SQLite."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT owner_key, source, preferences_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return row


def test_tutorbot_engine_mirror_row_is_not_a_user_conversation(tmp_path) -> None:
    """复现生产双会话 bug 的确定性时序（2026-07 BI 会话数翻倍根因）。

    一次移动端发送 = ① turn_runtime.ensure_session 建 canonical 会话行
    （owner_key=user:...，source=wx_miniprogram）+ ② TutorBot 引擎经
    SQLiteSessionAdapter 落 bot-side 镜像行 tutorbot:bot:...:chat:<conv_id>。
    修复前镜像行同样被打上用户 owner_key + 客户端 source，导致
    list_sessions_by_owner / BI 会员 scoping 把它当成第二个用户会话。
    业务事实：一次用户对话 = sessions 表恰一条用户会话；引擎镜像行是
    引擎私有历史，不得携带用户身份戳。
    """
    db_path = tmp_path / "chat_history.db"
    store = SQLiteSessionStore(db_path=db_path)
    user_id = "6cf455b1-a164-4858-bf3c-775974ab780e"
    owner_key = build_user_owner_key(user_id)
    conversation_id = "unified_1783406312729_d4cf4350"

    # ① WS turn 开始：turn_runtime 建 canonical 会话行（唯一用户会话权威）
    asyncio.run(store.ensure_session(conversation_id, owner_key=owner_key))
    asyncio.run(
        store.update_session_preferences(
            conversation_id,
            {"source": "wx_miniprogram", "user_id": user_id, "bot_id": "construction-exam-coach"},
        )
    )

    # ② 同一 turn 内：TutorBot 引擎 get_or_create（先建空行）+ save（补 metadata）
    adapter = SQLiteSessionAdapter(store)
    key = f"bot:construction-exam-coach:user:{user_id}:chat:{conversation_id}"
    engine_session = asyncio.run(adapter.get_or_create(key))
    engine_session.metadata = {
        "bot_id": "construction-exam-coach",
        "conversation_id": conversation_id,
        "session_id": conversation_id,
        "user_id": user_id,
        "source": "wx_miniprogram",
        "title": "一建建筑实务第一章考点",
        "archived": False,
    }
    engine_session.messages = [
        {"role": "user", "content": "一建建筑实务第一章考点"},
        {"role": "assistant", "content": "第一章核心考点如下……"},
    ]
    adapter.save(engine_session)

    # 终态断言：该用户的 wx_miniprogram 会话恰 1 条（canonical），无第二条
    rows = asyncio.run(
        store.list_sessions_by_owner(
            owner_key, source="wx_miniprogram", archived=False, limit=50, offset=0
        )
    )
    assert [row["id"] for row in rows] == [conversation_id]

    # 镜像行仍存在（引擎历史不受影响），但结构上不是用户会话：
    # 无 owner_key、source 为引擎源、preferences 不携带用户身份
    mirror = _session_columns(db_path, f"tutorbot:{key}")
    assert mirror is not None
    mirror_owner, mirror_source, mirror_prefs = mirror
    assert (mirror_owner or "") == ""
    assert mirror_source == "tutorbot"
    assert '"user_id"' not in (mirror_prefs or "")

    # 引擎自身历史读写不受影响
    adapter.invalidate(key)
    restored = asyncio.run(adapter.get_or_create(key))
    assert [item["content"] for item in restored.messages] == [
        "一建建筑实务第一章考点",
        "第一章核心考点如下……",
    ]


def test_tutorbot_engine_mirror_stays_engine_owned_across_repeat_saves(tmp_path) -> None:
    """multi-writer 生命周期防回归：第二次 save（update_session_preferences 路径）
    不得把镜像行的 source 翻回客户端 source、也不得从 metadata 派生回 owner_key。"""
    db_path = tmp_path / "chat_history.db"
    store = SQLiteSessionStore(db_path=db_path)
    adapter = SQLiteSessionAdapter(store)
    user_id = "u-repeat"
    key = f"bot:construction-exam-coach:user:{user_id}:chat:conv_repeat"

    engine_session = asyncio.run(adapter.get_or_create(key))
    engine_session.metadata = {
        "bot_id": "construction-exam-coach",
        "conversation_id": "conv_repeat",
        "user_id": user_id,
        "source": "wx_miniprogram",
        "title": "重复保存",
        "archived": False,
    }
    engine_session.messages = [{"role": "user", "content": "第一问"}]
    adapter.save(engine_session)

    engine_session.messages.append({"role": "assistant", "content": "解析"})
    adapter.save(engine_session)

    mirror = _session_columns(db_path, f"tutorbot:{key}")
    assert mirror is not None
    mirror_owner, mirror_source, mirror_prefs = mirror
    assert (mirror_owner or "") == ""
    assert mirror_source == "tutorbot"
    assert '"user_id"' not in (mirror_prefs or "")


def test_tutorbot_engine_mirror_reused_after_stock_demotion(tmp_path) -> None:
    """迁移身份断言：存量镜像行被 demote（剥 owner_key/user_id、source→tutorbot）后，
    get_or_create(session_key) 仍命中同一行——匹配只按主键 id=tutorbot:<key>
    （sqlite_adapter._load → store.get_session），不依赖任何被剥元数据。
    若匹配依赖身份戳，迁移会诱发新一轮双写（新建第二条镜像行）。"""
    from pathlib import Path as _Path
    import sqlite3 as _sqlite3
    import subprocess
    import sys as _sys

    db_path = tmp_path / "chat_history.db"
    store = SQLiteSessionStore(db_path=db_path)
    user_id = "u-stock"
    key = f"bot:construction-exam-coach:user:{user_id}:chat:conv_stock"
    mirror_id = f"tutorbot:{key}"

    # 造一条 legacy 形状的存量镜像行（身份戳齐全，等价于旧代码产物）
    asyncio.run(
        store.create_session(
            session_id=mirror_id,
            owner_key=build_user_owner_key(user_id),
            source="wx_miniprogram",
            title="存量镜像",
        )
    )
    asyncio.run(
        store.update_session_preferences(
            mirror_id,
            {"source": "wx_miniprogram", "user_id": user_id, "conversation_id": "conv_stock"},
        )
    )
    asyncio.run(
        store.add_message(
            session_id=mirror_id,
            role="user",
            content="存量第一问",
            capability="tutorbot",
            events=[{"_tutorbot_message": {"role": "user", "content": "存量第一问"}}],
        )
    )

    # 跑存量迁移脚本 --apply
    script = _Path(__file__).resolve().parents[3] / "scripts" / "demote_tutorbot_mirror_sessions.py"
    result = subprocess.run(
        [_sys.executable, str(script), "--db-path", str(db_path), "--apply"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "demoted: 1" in result.stdout

    # 迁移后 get_or_create 必须命中同一行：历史消息完整恢复（证明没有新建空行）
    adapter = SQLiteSessionAdapter(store)
    restored = asyncio.run(adapter.get_or_create(key))
    assert [item["content"] for item in restored.messages] == ["存量第一问"]

    # 且 sessions 表行数不变（没有第二条镜像行被创建）
    conn = _sqlite3.connect(str(db_path))
    try:
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        mirror_rows = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE id LIKE 'tutorbot:%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert total == 1
    assert mirror_rows == 1

    # 续写一轮后仍保持 demoted 且仍是同一行
    restored.metadata = {
        "bot_id": "construction-exam-coach",
        "conversation_id": "conv_stock",
        "user_id": user_id,
        "source": "wx_miniprogram",
        "title": "存量镜像",
        "archived": False,
    }
    restored.messages.append({"role": "assistant", "content": "续答"})
    adapter.save(restored)

    mirror = _session_columns(db_path, mirror_id)
    assert mirror is not None
    mirror_owner, mirror_source, _mirror_prefs = mirror
    assert (mirror_owner or "") == ""
    assert mirror_source == "tutorbot"
    conn = _sqlite3.connect(str(db_path))
    try:
        total_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    finally:
        conn.close()
    assert total_after == 1
