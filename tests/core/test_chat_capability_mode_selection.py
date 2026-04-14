from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.capabilities.chat import ChatCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline


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
