from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.chat.chat_agent import ChatAgent


@pytest.mark.asyncio
async def test_chat_agent_fast_rag_forwards_compiled_learning_truth() -> None:
    captured: dict[str, Any] = {}

    class FakeRegistry:
        async def execute(self, name: str, **kwargs: Any) -> SimpleNamespace:
            captured["name"] = name
            captured["kwargs"] = dict(kwargs)
            return SimpleNamespace(content="命中学员弱点", sources=[], success=True)

    agent = ChatAgent.__new__(ChatAgent)
    agent._tool_registry = FakeRegistry()
    agent.logger = SimpleNamespace(info=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None)

    context, sources = await agent.retrieve_context(
        message="我老是案例题采分点漏写怎么办",
        kb_name="construction-exam",
        enable_rag=True,
        compiled_learning_truth={"subject": "construction_exam_learning_truth"},
        retrieval_query="案例题采分点漏写",
    )

    assert "命中学员弱点" in context
    assert sources["rag"]
    assert captured["name"] == "rag"
    assert captured["kwargs"]["compiled_learning_truth"] == {
        "subject": "construction_exam_learning_truth"
    }
    assert captured["kwargs"]["query"] == "案例题采分点漏写"
    assert captured["kwargs"]["routing_metadata"]["compiled_learning_truth_available"] is True
