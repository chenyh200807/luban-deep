from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _SourceEmittingTutorBotManager:
    def build_chat_session_key(self, bot_id: str, conversation_id: str, *, user_id: str | None = None) -> str:
        return f"{bot_id}:{conversation_id}:{user_id or 'anon'}"

    def _infer_conversation_title(self, _message: str) -> str:
        return "测试会话"

    async def ensure_bot_running(self, _bot_id: str, *, config=None) -> None:
        return None

    async def send_message(self, **kwargs) -> str:
        on_tool_result = kwargs["on_tool_result"]
        await on_tool_result(
            "rag",
            "屋面防水等级应根据工程重要性确定。\n\n设防要求应结合渗漏后果判断。",
            {
                "sources": [
                    {
                        "source_type": "textbook",
                        "title": "2026 建筑实务教材",
                        "metadata": {
                            "source_id": "book_2026_001",
                            "source_span": {"chapter": "1", "section": "1.4"},
                        },
                        "rag_content": "屋面防水等级应根据工程重要性确定。",
                    },
                    {
                        "source_type": "standard",
                        "title": "屋面工程技术规范",
                        "standard_code": "GB 50345-2012",
                        "article_code": "3.0.1",
                        "rag_content": "设防要求应结合渗漏后果判断。",
                    }
                ]
            },
        )
        return "屋面防水等级应根据工程重要性确定。\n\n设防要求应结合渗漏后果判断。"


class _CapturingSourceEmittingTutorBotManager(_SourceEmittingTutorBotManager):
    def __init__(self) -> None:
        self.session_metadata: dict[str, object] = {}

    async def send_message(self, **kwargs) -> str:
        self.session_metadata = dict(kwargs["session_metadata"])
        return await super().send_message(**kwargs)


@pytest.mark.asyncio
async def test_tutorbot_result_appends_paper_style_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ANSWER_CITATIONS_ENABLED", "true")
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: _SourceEmittingTutorBotManager(),
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-citations",
        user_message="讲一下屋面防水等级",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_event = next(event for event in stream._history if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert response == "屋面防水等级应根据工程重要性确定。\n\n设防要求应结合渗漏后果判断。"
    assert "〔1〕" not in response
    assert "依据" not in response
    assert result_event.metadata["citation_bundle"]["footer_text"].startswith("依据\n〔1〕2026 建筑实务教材")
    assert result_event.metadata["citation_bundle"]["citation_state"] in {"supported", "partial"}
    content = "".join(
        str(event.content or "")
        for event in stream._history
        if event.type == StreamEventType.CONTENT
    )
    assert content == response


@pytest.mark.asyncio
async def test_tutorbot_citation_mode_applies_runtime_default_rag_grounding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ANSWER_CITATIONS_ENABLED", "true")
    manager = _CapturingSourceEmittingTutorBotManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-default-citation-grounding",
        user_message="请说明屋面防水构造的作用，并指出答题采分点。",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "smart",
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    assert manager.session_metadata["default_tools"] == ["rag"]
    assert manager.session_metadata["knowledge_bases"] == ["construction-exam"]
    assert manager.session_metadata["default_kb"] == "construction-exam"
    assert manager.session_metadata["answer_citations_required"] is True
