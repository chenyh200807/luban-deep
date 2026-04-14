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
async def test_orchestrator_respects_interaction_hint_for_question_type() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s1-hints",
        user_message="考我一道流水施工的题",
        config_overrides={},
        metadata={
            "interaction_hints": {
                "preferred_question_type": "written",
                "suppress_answer_reveal_on_generate": True,
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["question_type"] == "written"
    assert context.config_overrides["reveal_answers"] is False
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["question_type"] == "written"


@pytest.mark.asyncio
async def test_orchestrator_prioritizes_explicit_case_type_over_default_choice_hint() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s1-case",
        user_message="围绕流水施工给我出一道案例题，先别给答案",
        config_overrides={},
        metadata={
            "interaction_hints": {
                "preferred_question_type": "choice",
                "suppress_answer_reveal_on_generate": True,
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["question_type"] == "written"
    assert context.config_overrides["reveal_answers"] is False
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["question_type"] == "written"


@pytest.mark.asyncio
async def test_orchestrator_infers_question_count_from_user_message() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-count",
        user_message="围绕地基基础给我来3道选择题",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["num_questions"] == 3
    assert context.config_overrides["question_type"] == "choice"


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


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_judgment_submission_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-judge",
        user_message="我答：错。批改。",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_1",
                "question": "下面判断题：流水步距反映相邻专业队投入的时间间隔。对还是错？",
                "question_type": "choice",
                "options": {"A": "对", "B": "错"},
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


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_question_followup_without_revealing_answer() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-followup",
        user_message="先别给答案，只问我第1问。",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_case_1",
                "question": "案例背景：......\n第1问：请判断工序安排是否合理。\n第2问：说明理由。",
                "question_type": "written",
                "reveal_answers": False,
                "reveal_explanations": False,
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"


@pytest.mark.asyncio
async def test_orchestrator_treats_continue_issue_as_new_practice_request() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-continue-practice",
        user_message="继续出",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_1",
                "question": "变形缝止水带施工中，哪项做法正确？",
                "question_type": "choice",
                "correct_answer": "C",
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["question_type"] == "choice"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["question_type"] == "choice"
