from __future__ import annotations

import asyncio
import sys
import types
from types import MethodType
from types import SimpleNamespace

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = SimpleNamespace(  # type: ignore[attr-defined]
    info=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
    debug=lambda *args, **kwargs: None,
    exception=lambda *args, **kwargs: None,
)
sys.modules.setdefault("loguru", fake_loguru)

from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key
from deeptutor.services.tutorbot.manager import BotConfig, TutorBotManager
from deeptutor.tutorbot.session.manager import Session
from deeptutor.tutorbot.session.sqlite_adapter import SQLiteSessionAdapter


def test_tutorbot_sqlite_adapter_persists_metadata_and_raw_messages(tmp_path) -> None:
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
    assert restored.messages[1]["tool_calls"][0]["function"]["name"] == "rag"
    assert restored.messages[2]["tool_call_id"] == "call_1"
    assert restored.messages[-1]["content"] == "最终答案"

    row = asyncio.run(store.get_session(f"tutorbot:{key}"))
    assert row is not None
    assert row["title"] == "案例题会话"
    assert row["preferences"]["bot_id"] == "construction-exam-coach"
    assert row["preferences"]["conversation_id"] == "c1"
    assert row["preferences"]["user_id"] == "u1"


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
