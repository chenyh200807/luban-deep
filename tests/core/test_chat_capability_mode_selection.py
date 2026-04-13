from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.capabilities.chat import ChatCapability
from deeptutor.core.context import UnifiedContext


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
