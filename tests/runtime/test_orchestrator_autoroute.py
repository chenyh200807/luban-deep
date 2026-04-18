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
async def test_orchestrator_autoroutes_natural_one_question_phrase_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s1-natural",
        user_message="给我一道题测试一下这个知识点",
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
async def test_orchestrator_keeps_learning_strategy_request_in_chat_even_if_effective_message_contains_practice_words() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    raw_message = "我现在最大问题不是听不懂，是记不住，做题时规范数字和条件全串了。给我一个今晚就能执行的冲刺学习法。"
    context = UnifiedContext(
        session_id="s-learning-plan",
        user_message="## 参考上下文\n给我一道题测试一下这个知识点\n\n## 当前用户问题\n" + raw_message,
        config_overrides={},
        metadata={"raw_user_message": raw_message},
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["capability"] == "auto"


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
async def test_orchestrator_hides_answers_by_default_when_generation_hint_omits_reveal_policy() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s1-default-hide",
        user_message="出道题",
        config_overrides={},
        metadata={
            "interaction_hints": {
                "profile": "tutorbot",
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False


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
async def test_orchestrator_autoroutes_batch_submission_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-batch-followup",
        user_message="第1题：C；第2题：A；第3题：B",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "choice",
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "choice",
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "choice",
                        "correct_answer": "D",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert graded["items"][0]["user_answer"] == "C"
    assert graded["items"][0]["is_correct"] is True
    assert graded["items"][2]["user_answer"] == "B"
    assert graded["items"][2]["is_correct"] is False


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_compact_batch_letters_using_question_context() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-compact-batch-followup",
        user_message="ACD",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_compact",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "single_choice",
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "single_choice",
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "single_choice",
                        "correct_answer": "B",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert [item["user_answer"] for item in graded["items"]] == ["A", "C", "D"]


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_compact_numbered_batch_using_question_context() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-compact-numbered-batch-followup",
        user_message="1a2c3d",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_compact_numbered",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "single_choice",
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "single_choice",
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "single_choice",
                        "correct_answer": "B",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert [item["user_answer"] for item in graded["items"]] == ["A", "C", "D"]


@pytest.mark.asyncio
async def test_orchestrator_autoroutes_batch_correction_using_existing_answers() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-batch-correction-followup",
        user_message="第2题改成C，其他不变",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_correction",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "single_choice",
                        "correct_answer": "A",
                        "user_answer": "A",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "single_choice",
                        "correct_answer": "C",
                        "user_answer": "B",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "single_choice",
                        "correct_answer": "D",
                        "user_answer": "D",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert [item["user_answer"] for item in graded["items"]] == ["A", "C", "D"]


@pytest.mark.asyncio
async def test_orchestrator_prefers_llm_followup_action_before_regex_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _fake_interpret(*_args, **_kwargs):
        return {
            "intent": "revise_answers",
            "confidence": 0.98,
            "preserve_other_answers": True,
            "answers": [
                {
                    "index": 1,
                    "question_id": "q_1",
                    "user_answer": "C",
                }
            ],
            "reason": "用户是在基于现有题组修改第一题答案，其他答案保持不变。",
        }

    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.interpret_question_followup_action",
        _fake_interpret,
    )

    context = UnifiedContext(
        session_id="s-llm-first-followup",
        user_message="第一题我改C，别的不动",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_llm_first",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "single_choice",
                        "correct_answer": "C",
                        "user_answer": "A",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "single_choice",
                        "correct_answer": "B",
                        "user_answer": "B",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "single_choice",
                        "correct_answer": "D",
                        "user_answer": "D",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert [item["user_answer"] for item in graded["items"]] == ["C", "B", "D"]
    assert context.metadata["question_followup_action"]["intent"] == "revise_answers"


@pytest.mark.asyncio
async def test_orchestrator_keeps_regex_as_fallback_when_llm_returns_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _fake_interpret(*_args, **_kwargs):
        return {
            "intent": "unknown",
            "confidence": 0.21,
            "preserve_other_answers": False,
            "answers": [],
            "reason": "无法从模型判定中得到可靠结构化答案。",
        }

    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.interpret_question_followup_action",
        _fake_interpret,
    )

    context = UnifiedContext(
        session_id="s-regex-fallback-followup",
        user_message="ACD",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_compact_regex_fallback",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "single_choice",
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "single_choice",
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "single_choice",
                        "correct_answer": "D",
                    },
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    graded = context.metadata["question_followup_context"]
    assert [item["user_answer"] for item in graded["items"]] == ["A", "C", "D"]


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
