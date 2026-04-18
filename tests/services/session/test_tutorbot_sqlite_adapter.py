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
async def test_tutorbot_manager_send_message_reuses_outer_usage_scope_for_external_turn() -> None:
    observability = get_langfuse_observability()
    manager = TutorBotManager()

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
            response = await manager.send_message(
                "demo-bot",
                "建筑构造是什么？",
                session_metadata={
                    "session_id": "mobile-session",
                    "turn_id": "turn-1",
                    "user_id": "u1",
                    "source": "wx_miniprogram",
                },
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
