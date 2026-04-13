from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.orchestrator import ChatOrchestrator


class _FakeCapability:
    async def run(self, context: UnifiedContext, bus) -> None:
        await bus.result(
            {
                "capability": context.active_capability or "auto",
                "question_type": context.config_overrides.get("question_type"),
                "user_answer": (context.metadata.get("question_followup_context", {}) or {}).get("user_answer"),
                "is_correct": (context.metadata.get("question_followup_context", {}) or {}).get("is_correct"),
            },
            source="fake",
        )


class _FakeRegistry:
    def __init__(self) -> None:
        self.captured: list[str] = []

    def get(self, name: str) -> Any:
        self.captured.append(name)
        return _FakeCapability()

    def list_capabilities(self) -> list[str]:
        return ["chat", "deep_question"]

    def get_manifests(self) -> list[dict[str, Any]]:
        return []


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_practice_request_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s1",
        user_message="考我一道流水施工的题",
        config_overrides={},
        metadata={},
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["question_type"] == "choice"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["question_type"] == "choice"


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_choice_submission_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s2",
        user_message="我选B",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_1",
                "question": "流水步距描述什么？",
                "question_type": "choice",
                "correct_answer": "B",
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["user_answer"] == "B"
    assert result.metadata["is_correct"] is True
