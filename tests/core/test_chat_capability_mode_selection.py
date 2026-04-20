from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from deeptutor.capabilities.chat import ChatCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.stream_bus import StreamBus


def test_chat_capability_promotes_fast_mode_for_knowledge_explainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.capabilities.chat.get_default_chat_mode",
        lambda: "fast",
    )
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    context = UnifiedContext(
        user_message="什么是流水步距，怎么区分流水步距和流水节拍？",
        config_overrides={},
        language="zh",
    )

    assert ChatCapability._should_promote_fast_mode(context, "fast") is True


def test_chat_capability_keeps_explicit_fast_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.capabilities.chat.get_default_chat_mode",
        lambda: "fast",
    )
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    context = UnifiedContext(
        user_message="什么是流水步距，怎么区分流水步距和流水节拍？",
        config_overrides={"chat_mode": "fast"},
        metadata={"chat_mode_explicit": True},
        language="zh",
    )

    assert ChatCapability._should_promote_fast_mode(context, "fast") is False


def test_agentic_chat_pipeline_auto_enables_rag_when_knowledge_base_is_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

        def build_prompt_text(self, _enabled_tools, **_kwargs):
            return ""

        def build_prompt_text(self, _enabled_tools, **_kwargs):
            return ""

        def build_prompt_text(self, _enabled_tools, **_kwargs):
            return ""

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        user_message="什么是流水步距，怎么区分流水步距和流水节拍？",
        enabled_tools=[],
        knowledge_bases=["demo-kb"],
        config_overrides={},
        language="zh",
    )

    resolved = pipeline.resolve_enabled_tools(
        context,
        answer_type="knowledge_explainer",
        mode="fast",
    )

    assert "rag" in resolved


def test_agentic_chat_pipeline_does_not_auto_enable_reason_in_deep_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

        def build_prompt_text(self, _enabled_tools, **_kwargs):
            return ""

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        user_message="这道案例题怎么解？请分步分析。",
        enabled_tools=[],
        knowledge_bases=["demo-kb"],
        config_overrides={},
        language="zh",
    )

    resolved = pipeline.resolve_enabled_tools(
        context,
        answer_type="problem_solving",
        mode="deep",
    )

    assert "rag" in resolved
    assert "reason" not in resolved


def test_agentic_chat_pipeline_keeps_user_selected_reason_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        user_message="这道案例题怎么解？请分步分析。",
        enabled_tools=["reason"],
        knowledge_bases=["demo-kb"],
        config_overrides={},
        language="zh",
    )

    resolved = pipeline.resolve_enabled_tools(
        context,
        answer_type="problem_solving",
        mode="deep",
    )

    assert "rag" in resolved
    assert "reason" in resolved


@pytest.mark.asyncio
async def test_agentic_chat_pipeline_uses_compact_response_for_smart_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")

    async def _fail_stage(*_args, **_kwargs):
        raise AssertionError("smart compact path should skip multi-stage reasoning")

    compact_calls: list[str] = []

    async def _fake_smart_stage(*_args, **_kwargs):
        compact_calls.append("smart")
        return "这是 smart 单轮回答。", {"label": "Smart response"}

    monkeypatch.setattr(pipeline, "_stage_thinking", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_acting", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_observing", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_responding", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_smart_responding", _fake_smart_stage)

    bus = StreamBus()
    context = UnifiedContext(
        user_message="什么是流水步距？",
        enabled_tools=[],
        config_overrides={
            "chat_mode": "smart",
            "interaction_hints": {
                "profile": "tutorbot",
                "entry_role": "tutorbot",
                "teaching_mode": "smart",
            },
        },
        language="zh",
    )

    await pipeline.run(context, bus)

    result_event = next(event for event in bus._history if event.type.value == "result")
    assert compact_calls == ["smart"]
    assert result_event.metadata["chat_mode"] == "smart"
    assert result_event.metadata["response"] == "这是 smart 单轮回答。"


@pytest.mark.asyncio
async def test_smart_responding_prompt_preserves_explicit_anchor_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")
    captured: dict[str, str] = {}

    def _capture_build_messages(*, context, system_prompt, user_content):
        captured["user_content"] = user_content
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]

    async def _fake_stream_messages(_messages, max_tokens):
        yield "示例回答"

    monkeypatch.setattr(pipeline, "_build_messages", _capture_build_messages)
    monkeypatch.setattr(pipeline, "_responding_system_prompt", lambda _tool_traces: "")
    monkeypatch.setattr(pipeline, "_stream_messages", _fake_stream_messages)

    bus = StreamBus()
    context = UnifiedContext(
        user_message="你用盖一栋6层住宅楼举个例子讲讲，最好让我一下子能形成画面感。",
        enabled_tools=[],
        config_overrides={
            "chat_mode": "smart",
            "interaction_profile": "tutorbot",
            "interaction_hints": {
                "profile": "tutorbot",
                "entry_role": "tutorbot",
                "teaching_mode": "smart",
            },
        },
        language="zh",
    )

    content, _trace_meta = await pipeline._stage_smart_responding(
        context=context,
        answer_type="knowledge_explainer",
        stream=bus,
    )

    assert content == "示例回答"
    assert "6层住宅楼" in captured["user_content"]
    assert "不要改写成更泛的近义说法" in captured["user_content"]


@pytest.mark.asyncio
async def test_chat_capability_fast_mode_ignores_web_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, language: str = "zh") -> None:
            self.language = language

        def _infer_answer_type(self, _message: str) -> str:
            return "knowledge_explainer"

        def resolve_enabled_tools(self, *_args, **_kwargs) -> list[str]:
            return ["rag", "web_search"]

    class FakeChatAgent:
        def __init__(self, language: str = "zh") -> None:
            self.language = language

        async def process(self, **kwargs):
            captured.update(kwargs)

            async def _result():
                yield {
                    "type": "complete",
                    "sources": {"rag": [], "web": []},
                    "truncated_history": [],
                }

            return _result()

    monkeypatch.setattr("deeptutor.capabilities.chat.AgenticChatPipeline", FakePipeline)
    monkeypatch.setattr("deeptutor.capabilities.chat.ChatAgent", FakeChatAgent)

    capability = ChatCapability()
    bus = StreamBus()
    context = UnifiedContext(
        user_message="屋面防水等级怎么划分？",
        enabled_tools=["web_search"],
        knowledge_bases=["construction-exam"],
        config_overrides={"chat_mode": "fast"},
        metadata={"chat_mode_explicit": True},
        language="zh",
    )

    await capability.run(context, bus)

    assert captured["kb_name"] == "construction-exam"
    assert captured["enable_rag"] is True
    assert captured["enable_web_search"] is False


@pytest.mark.asyncio
async def test_agentic_chat_pipeline_skips_compact_response_for_grounded_tutorbot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        def get(self, name: str):
            return SimpleNamespace(name=name)

    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_tool_registry",
        lambda: FakeRegistry(),
    )

    pipeline = AgenticChatPipeline(language="zh")

    async def _unexpected_smart_stage(*_args, **_kwargs):
        raise AssertionError("grounded tutorbot must not use compact smart response")

    monkeypatch.setattr(pipeline, "_stage_smart_responding", _unexpected_smart_stage)
    monkeypatch.setattr(pipeline, "_stage_thinking", AsyncMock(return_value="需要先做知识召回。"))
    monkeypatch.setattr(pipeline, "_stage_acting", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "_stage_observing", AsyncMock(return_value=""))
    monkeypatch.setattr(
        pipeline,
        "_stage_responding",
        AsyncMock(return_value=("这是经过知识链的回答。", {"label": "Responding"})),
    )

    bus = StreamBus()
    context = UnifiedContext(
        user_message="这道建筑案例题请按真题标准作答。",
        enabled_tools=[],
        knowledge_bases=["construction-exam"],
        config_overrides={
            "chat_mode": "smart",
            "interaction_profile": "tutorbot",
            "interaction_hints": {
                "profile": "tutorbot",
                "entry_role": "tutorbot",
                "subject_domain": "construction_exam",
                "teaching_mode": "smart",
            },
        },
        metadata={
            "bot_id": "construction-exam-coach",
        },
        language="zh",
    )

    await pipeline.run(context, bus)

    assert pipeline._stage_thinking.await_count == 1
    assert pipeline._stage_acting.await_count == 1
    assert pipeline._stage_responding.await_count == 1
