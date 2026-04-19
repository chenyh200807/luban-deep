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
async def test_agentic_chat_pipeline_uses_compact_response_for_construction_exam_tutor_smart_mode(
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
        raise AssertionError("construction_exam_tutor smart mode should use compact path")

    compact_calls: list[str] = []

    async def _fake_smart_stage(*_args, **_kwargs):
        compact_calls.append("smart")
        return "这是 construction exam smart 单轮回答。", {"label": "Smart response"}

    monkeypatch.setattr(pipeline, "_stage_thinking", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_acting", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_observing", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_responding", _fail_stage)
    monkeypatch.setattr(pipeline, "_stage_smart_responding", _fake_smart_stage)

    bus = StreamBus()
    context = UnifiedContext(
        user_message="什么是流水施工？",
        enabled_tools=[],
        config_overrides={
            "chat_mode": "smart",
            "interaction_hints": {
                "profile": "construction_exam_tutor",
                "teaching_mode": "smart",
                "subject_domain": "construction_exam",
            },
        },
        language="zh",
    )

    await pipeline.run(context, bus)

    result_event = next(event for event in bus._history if event.type.value == "result")
    assert compact_calls == ["smart"]
    assert result_event.metadata["chat_mode"] == "smart"
    assert result_event.metadata["response"] == "这是 construction exam smart 单轮回答。"


def test_agentic_chat_pipeline_teaching_overlay_preserves_concrete_case_anchor_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        user_message="你用盖一栋6层住宅楼举个例子讲讲。",
        config_overrides={
            "chat_mode": "smart",
            "interaction_hints": {
                "profile": "construction_exam_tutor",
                "teaching_mode": "smart",
                "subject_domain": "construction_exam",
            },
        },
        language="zh",
    )

    overlay = pipeline._teaching_mode_overlay(context)

    assert "后续讲解默认沿用该锚点原词" in overlay
    assert "不要自行缩写、泛化或换称呼" in overlay


def test_agentic_chat_pipeline_responding_prompt_preserves_concrete_case_anchor_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    pipeline = AgenticChatPipeline(language="zh")

    prompt = pipeline._responding_system_prompt([])

    assert "如果用户当前问题里给了具体案例锚点或对象原词" in prompt
    assert "默认沿用该原词" in prompt


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


@pytest.mark.asyncio
async def test_agentic_chat_pipeline_smart_responding_streams_chunks_when_teaching_contract_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    pipeline = AgenticChatPipeline(language="zh")

    async def _fake_stream_messages(_messages, max_tokens: int):
        assert max_tokens == 1800
        yield "第一段。"
        yield "第二段。"

    monkeypatch.setattr(pipeline, "_stream_messages", _fake_stream_messages)
    monkeypatch.setattr(
        pipeline,
        "_complete_validated_response",
        AsyncMock(side_effect=AssertionError("teaching contract should no longer force buffered response")),
    )

    bus = StreamBus()
    context = UnifiedContext(
        user_message="什么是流水步距？",
        config_overrides={
            "chat_mode": "smart",
            "interaction_hints": {
                "profile": "tutorbot",
                "entry_role": "tutorbot",
                "subject_domain": "construction_exam",
                "teaching_mode": "fast",
            },
        },
        language="zh",
    )

    content, _trace = await pipeline._stage_smart_responding(
        context,
        "knowledge_explainer",
        bus,
    )

    content_events = [event for event in bus._history if event.type.value == "content"]
    assert content == "第一段。第二段。"
    assert [event.content for event in content_events] == ["第一段。", "第二段。"]
    assert pipeline._complete_validated_response.await_count == 0


@pytest.mark.asyncio
async def test_agentic_chat_pipeline_exact_authority_path_still_buffers_final_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    pipeline = AgenticChatPipeline(language="zh")

    async def _unexpected_stream_messages(_messages, _max_tokens: int):
        raise AssertionError("exact authority path should stay buffered")
        yield ""

    monkeypatch.setattr(pipeline, "_stream_messages", _unexpected_stream_messages)
    monkeypatch.setattr(pipeline, "_complete_messages", AsyncMock(return_value="权威标准答案。"))
    monkeypatch.setattr(
        pipeline,
        "_should_buffer_authoritative_response",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        pipeline,
        "_apply_exact_question_authority",
        AsyncMock(return_value="权威标准答案。"),
    )

    bus = StreamBus()
    context = UnifiedContext(
        user_message="请按原题标准答案作答。",
        config_overrides={},
        language="zh",
    )

    content, _trace = await pipeline._stage_responding(
        context,
        [],
        "knowledge_explainer",
        "",
        "已有依据",
        [],
        bus,
    )

    content_events = [event for event in bus._history if event.type.value == "content"]
    assert content == "权威标准答案。"
    assert [event.content for event in content_events] == ["权威标准答案。"]
    assert pipeline._complete_messages.await_count == 1
