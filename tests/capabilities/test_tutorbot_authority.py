from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _FakeTutorBotManager:
    def build_chat_session_key(self, bot_id: str, conversation_id: str, *, user_id: str | None = None) -> str:
        return f"{bot_id}:{conversation_id}:{user_id or 'anon'}"

    def _infer_conversation_title(self, _message: str) -> str:
        return "测试会话"

    async def ensure_bot_running(self, _bot_id: str, *, config=None) -> None:
        return None

    async def send_message(self, **kwargs) -> str:
        return (
            "第1题：下列关于施工缝处理正确的是？\n"
            "A. 任意留设\n"
            "B. 按设计和规范处理\n"
            "C. 不需要清理\n"
            "D. 只能留在跨中\n"
            "答案：B\n"
            "解析：施工缝应按设计和规范处理。"
        )


@pytest.mark.asyncio
async def test_tutorbot_does_not_turn_free_text_mcq_into_submitable_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: _FakeTutorBotManager(),
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-free-text",
        user_message="讲一下施工缝，顺便举个选择题例子",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_metadata = result_events[-1].metadata
    assert "presentation" not in result_metadata
    assert "question_followup_context" not in result_metadata
    assert "active_object" not in result_metadata
