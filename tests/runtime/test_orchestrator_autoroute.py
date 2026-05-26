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
        return ["chat", "deep_question", "tutorbot"]

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
async def test_orchestrator_routes_training_by_question_count_as_practice_generation() -> None:
    """`用 3 道题训练 X` is a test-me request, not a question-review request."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-training-by-count",
        user_message="用 3 道题训练项目质量计划管理",
        config_overrides={"mode": "deep"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "practice_generation"
    assert context.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["num_questions"] == 3
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False


@pytest.mark.asyncio
async def test_orchestrator_blocks_topic_only_real_exam_query_before_exact_authority() -> None:
    """Topic-only exam queries need a choice, not an arbitrary exact-question answer."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-topic-only-real-exam",
        user_message="防水真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["question_lifecycle_scene"] is None
    assert context.metadata["question_lifecycle_decision"].items() >= {
        "required_anchor_status": "missing_question_anchor",
        "exact_question_blocked_reason": "low_information_exam_query",
        "needs_clarification": True,
        "business_gate_result": "blocked_low_information_exam_query",
    }.items()
    assert context.metadata["selected_skill_names"] == []


@pytest.mark.asyncio
async def test_orchestrator_routes_topic_qualified_more_practice_to_generation() -> None:
    """`再出3题练地下防水` is practice generation, not real-question review."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-topic-qualified-more-practice",
        user_message="再出3题练地下防水",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "practice_generation"
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]
    assert context.config_overrides["num_questions"] == 3
    assert context.config_overrides["topic"] == "再出3题练地下防水"
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_scene_proposal_for_semantic_practice_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _fake_complete(**kwargs):
        assert "题目生命周期语义候选" in kwargs["system_prompt"]
        return '{"scene":"practice_generation","confidence":0.89,"reason":"语义上是练题请求"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    context = UnifiedContext(
        session_id="s-llm-scene-practice",
        user_message="项目质量计划管理这个点，帮我练到会",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "practice_generation"
    assert context.metadata["question_lifecycle_scene_source"] == "llm"
    assert context.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_scene_proposal_for_semantic_question_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _fake_complete(**kwargs):
        assert "题目生命周期语义候选" in kwargs["system_prompt"]
        return '{"scene":"question_review","confidence":0.9,"reason":"语义上是题目讲评请求"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    context = UnifiedContext(
        session_id="s-llm-scene-review",
        user_message="拿一道钢筋保护层题给我讲透",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "question_review"
    assert context.metadata["question_lifecycle_scene_source"] == "llm"
    assert context.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]
    assert "force_generate_questions" not in context.config_overrides


@pytest.mark.asyncio
async def test_orchestrator_routes_short_acceptance_of_recent_practice_offer_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-accepted-offer",
        user_message="要",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "raw_user_message": "要",
            "conversation_context_text": (
                "Assistant: 记忆口诀强化\n"
                "主体结构七大类：砼砌钢，钢管型钢铝木全。\n"
                "需要我出同考点题目帮你巩固一下吗？"
            ),
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "s-accepted-offer",
                "scope": {"domain": "session", "session_id": "s-accepted-offer"},
                "state_snapshot": {
                    "session_id": "s-accepted-offer",
                    "title": "主体结构",
                    "compressed_summary": "用户在复习主体结构。",
                    "status": "idle",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-offer",
            },
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["topic"] == "继续出同考点题目帮我巩固一下"
    assert context.metadata["semantic_router_selected_capability"] == "deep_question"
    assert context.metadata["question_followup_action"]["intent"] == "generate_more_questions"


@pytest.mark.asyncio
async def test_orchestrator_uses_tutorbot_as_default_chat_engine_after_semantic_chat_decision() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-tutorbot-chat",
        user_message="这个口诀是什么意思？",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "raw_user_message": "这个口诀是什么意思？",
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "s-tutorbot-chat",
                "scope": {"domain": "session", "session_id": "s-tutorbot-chat"},
                "state_snapshot": {
                    "session_id": "s-tutorbot-chat",
                    "title": "主体结构",
                    "compressed_summary": "用户在复习主体结构。",
                    "status": "idle",
                },
                "version": 1,
                "entered_at": "",
                "last_touched_at": "",
                "source_turn_id": "turn-chat",
            },
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["semantic_router_selected_capability"] == "tutorbot"


@pytest.mark.asyncio
async def test_orchestrator_still_records_lifecycle_decision_with_active_context() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-active-context-support",
        user_message="我学不动了",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "active_object": {
                "object_type": "open_chat_topic",
                "object_id": "topic-1",
                "scope": {"domain": "session", "session_id": "s-active-context-support"},
                "state_snapshot": {"title": "主体结构", "status": "idle"},
                "version": 1,
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["question_lifecycle_scene"] == "learning_support"
    assert context.metadata["question_lifecycle_decision"]["scene"] == "learning_support"
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-learning-support",
    ]


@pytest.mark.asyncio
async def test_orchestrator_materializes_free_text_real_exam_review_before_explaining() -> None:
    """A request like "分析一道真题" must create a question object first.

    Production case 2026-05-24: routing this to TutorBot free text produced a
    generic answer-analysis without a stem/options anchor. The question
    lifecycle authority should route this through deep_question so the learner
    sees the concrete question before the answer explanation.
    """
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-real-exam-review",
        user_message="分析一道验槽方法真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "question_review"
    assert "force_generate_questions" not in context.config_overrides
    assert "reveal_answers" not in context.config_overrides
    assert "reveal_explanations" not in context.config_overrides
    assert "question_review_mode" not in context.config_overrides
    assert context.config_overrides["topic"] == "分析一道验槽方法真题"
    assert context.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]
    assert context.metadata["trace_metadata"]["question_lifecycle_scene"] == "question_review"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["capability"] == "auto"


@pytest.mark.asyncio
async def test_orchestrator_lifecycle_runs_before_preselected_tutorbot_for_question_review() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselected-tutorbot-review",
        active_capability="tutorbot",
        user_message="分析一道钢筋保护层真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "question_review"
    assert context.metadata["question_lifecycle_decision"]["decision_source"] == "deterministic"
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]


@pytest.mark.asyncio
async def test_orchestrator_allows_explicit_year_real_exam_review_after_low_info_gate() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-year-real-exam-review",
        active_capability="tutorbot",
        user_message="分析一道2025真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "question_review"
    assert context.metadata["required_anchor_status"] == "satisfied"
    assert context.metadata.get("exact_question_blocked_reason") is None
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]


@pytest.mark.asyncio
async def test_orchestrator_clears_stale_exact_question_block_when_anchor_is_present() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-clear-stale-block",
        active_capability="tutorbot",
        user_message="分析一道钢筋保护层真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "exact_question_blocked_reason": "low_information_exam_query",
            "trace_metadata": {"exact_question_blocked_reason": "low_information_exam_query"},
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "question_review"
    assert "exact_question_blocked_reason" not in context.metadata
    assert "exact_question_blocked_reason" not in context.metadata["trace_metadata"]


@pytest.mark.asyncio
async def test_orchestrator_marks_low_information_exam_query_without_exact_authority() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-low-info-exam-query",
        active_capability="tutorbot",
        user_message="2025真题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["question_lifecycle_scene"] is None
    assert context.metadata["question_lifecycle_decision"].items() >= {
        "scene": None,
        "scene_confidence": 1.0,
        "reason": "low-information exam query needs clarification",
        "required_anchor_status": "missing_question_anchor",
        "exact_question_blocked_reason": "low_information_exam_query",
        "needs_clarification": True,
        "business_gate_result": "blocked_low_information_exam_query",
    }.items()
    assert context.metadata["question_lifecycle_decision"]["selected_skill_names"] == []
    assert context.metadata["exact_question_blocked_reason"] == "low_information_exam_query"
    assert context.metadata["trace_metadata"]["exact_question_blocked_reason"] == "low_information_exam_query"


@pytest.mark.asyncio
async def test_preselected_deep_question_grades_submission_before_practice_generation() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselected-grading",
        active_capability="deep_question",
        user_message="我选A，请按建筑实务选择题帮我批改，并告诉我下一题该练什么",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_regulation_level",
                "question": "《建设工程安全生产管理条例》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "B",
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert "topic" not in context.config_overrides
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["user_answer"] == "A"
    assert result.metadata["is_correct"] is False


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
async def test_orchestrator_keeps_ordinary_concept_comparison_out_of_question_lifecycle() -> None:
    """Plain concept explanation should stay TutorBot/general chat, not question flow."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-ordinary-concept-comparison",
        user_message="横道图和网络图有什么区别",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["question_lifecycle_scene"] is None
    assert context.metadata["question_lifecycle_decision"].items() >= {
        "reason": "no deterministic scene and LLM proposal not applicable",
        "business_gate_result": "no_candidate",
    }.items()
    assert context.metadata["selected_skill_names"] == []


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
async def test_orchestrator_ignores_invalid_num_questions_override_for_practice_autoroute() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-count-invalid",
        user_message="围绕地基基础给我来3道选择题",
        config_overrides={"num_questions": "abc"},
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
async def test_orchestrator_requires_active_question_for_short_answer_submission() -> None:
    """A bare `我选B` without a current card cannot be graded out of thin air."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-short-answer-without-active-question",
        user_message="我选B",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "tutorbot"
    assert context.metadata["question_lifecycle_scene"] is None
    assert context.metadata["question_lifecycle_decision"].items() >= {
        "required_anchor_status": "missing_active_question",
        "exact_question_blocked_reason": "unanchored_answer_submission",
        "needs_clarification": True,
        "business_gate_result": "blocked_unanchored_answer_submission",
    }.items()


@pytest.mark.asyncio
async def test_orchestrator_grades_before_generation_in_mixed_answer_then_more_practice() -> None:
    """`我答B，再出3题` must grade first; follow-up generation is a later action."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-answer-then-more-practice",
        user_message="我答B，再出3题",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "question_followup_context": {
                "question_id": "q_1",
                "question": "地下防水工程卷材搭接宽度应符合哪项要求？",
                "question_type": "choice",
                "options": {"A": "50mm", "B": "80mm", "C": "100mm", "D": "150mm"},
                "correct_answer": "C",
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "mcq_grading"
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-mcq-grading",
    ]
    assert "force_generate_questions" not in context.config_overrides
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["user_answer"] == "B"
    assert result.metadata["is_correct"] is False


@pytest.mark.asyncio
async def test_orchestrator_keeps_numbered_batch_answers_as_grading() -> None:
    """Numbered answers like `q1 A, q3 C, q5 B` are batch grading submissions."""
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-numbered-batch-answers",
        user_message="q1 A, q3 C, q5 B",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第3题...\n第5题...",
                "question_type": "choice",
                "items": [
                    {"question_id": "q1", "question": "题1", "question_type": "choice", "correct_answer": "A"},
                    {"question_id": "q3", "question": "题3", "question_type": "choice", "correct_answer": "D"},
                    {"question_id": "q5", "question": "题5", "question_type": "choice", "correct_answer": "B"},
                ],
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["question_lifecycle_scene"] == "mcq_grading"
    assert context.metadata["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-mcq-grading",
    ]


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
    assert context.metadata["question_lifecycle_scene"] == "mcq_grading"
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


@pytest.mark.asyncio
async def test_orchestrator_treats_explicit_choice_type_as_generation_with_active_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _misleading_interpret(*_args, **_kwargs):
        return {
            "intent": "answer_questions",
            "confidence": 0.91,
            "answers": [{"index": 1, "question_id": "q_prev", "user_answer": "A"}],
            "reason": "模拟 LLM 把“选择题”误判成上一题答案。",
        }

    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.interpret_question_followup_action",
        _misleading_interpret,
    )

    context = UnifiedContext(
        session_id="s-choice-type-generation",
        user_message="选择题",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_prev",
                "question": "上一道题：楼梯平台净高下限是多少？",
                "question_type": "choice",
                "options": {"A": "2.0m", "B": "2.2m", "C": "2.4m", "D": "2.6m"},
                "correct_answer": "B",
            }
        },
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["question_type"] == "choice"
    assert context.metadata["question_followup_context"]["user_answer"] == ""
    assert context.metadata["question_followup_context"]["is_correct"] is None
    assert context.metadata["question_followup_action"]["intent"] == "generate_more_questions"
    assert context.metadata["turn_semantic_decision"]["next_action"] == "route_to_generation"
    result = next(event for event in events if event.type.value == "result")
    assert result.metadata["question_type"] == "choice"


@pytest.mark.asyncio
async def test_orchestrator_clears_previous_answer_when_explicit_generation_reuses_active_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _misleading_interpret(*_args, **_kwargs):
        return {
            "intent": "answer_questions",
            "confidence": 0.91,
            "answers": [{"index": 1, "question_id": "q_prev", "user_answer": "A"}],
        }

    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.interpret_question_followup_action",
        _misleading_interpret,
    )

    context = UnifiedContext(
        session_id="s-choice-type-generation-after-answer",
        user_message="选择题",
        config_overrides={},
        metadata={
            "question_followup_context": {
                "question_id": "q_prev",
                "question": "上一道题：楼梯平台净高下限是多少？",
                "question_type": "choice",
                "options": {"A": "2.0m", "B": "2.2m", "C": "2.4m", "D": "2.6m"},
                "correct_answer": "B",
                "user_answer": "A",
                "is_correct": False,
            }
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert context.metadata["question_followup_action"]["intent"] == "generate_more_questions"
    assert context.metadata["question_followup_context"]["user_answer"] == ""
    assert context.metadata["question_followup_context"]["is_correct"] is None
    assert context.metadata["active_object"]["state_snapshot"]["user_answer"] == ""
    assert context.metadata["active_object"]["state_snapshot"]["is_correct"] is None


@pytest.mark.asyncio
async def test_orchestrator_only_enables_lightweight_generation_for_explicit_question_only_request() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-lightweight-explicit",
        user_message="我现在学到网络计划了，但我特别容易把总时差和自由时差搞混。你先别长篇讲概念，先给我出3道很短的小题，我做完你再分析。",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_orchestrator_routes_plain_practice_request_to_lightweight_generation() -> None:
    # plan §Phase 1 Step 1.1 (A2/A3) — 普通"考我N道"练题请求应默认进入 lightweight。
    # 在引入 classify_practice_strategy 之前，本用例曾期望 lightweight=False；现在
    # 这种用户意图（无 heavy keyword、无要求 reveal、1<=N<=5）必须走轻量。
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-lightweight-normal",
        user_message="考我3道网络计划选择题。",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["lightweight_generation"] is True
    trace_meta = context.metadata.get("trace_metadata") or {}
    assert trace_meta.get("practice_generation.strategy") == "lightweight"
    assert trace_meta.get("practice_generation.question_count") == 3


@pytest.mark.asyncio
async def test_orchestrator_enables_lightweight_generation_for_single_question_without_answer_reveal() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-lightweight-single-no-answer",
        user_message="出一道建筑实务单选题，不要给答案。",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False
    assert context.config_overrides["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_orchestrator_preselected_deep_question_still_prepares_lightweight_generation_context() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-lightweight-preselected",
        user_message="出一道建筑实务单选题，不要给答案。",
        config_overrides={},
        metadata={"raw_user_message": "出一道建筑实务单选题，不要给答案。"},
        language="zh",
        active_capability="deep_question",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["reveal_answers"] is False
    assert context.config_overrides["reveal_explanations"] is False
    assert context.config_overrides["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_orchestrator_preselected_deep_question_uses_cached_generation_action_for_short_acceptance() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselected-acceptance",
        user_message="要",
        config_overrides={},
        metadata={
            "raw_user_message": "要",
            "question_followup_action": {
                "intent": "generate_more_questions",
                "topic": "继续出同考点题目帮我巩固一下",
            },
        },
        language="zh",
        active_capability="deep_question",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["topic"] == "继续出同考点题目帮我巩固一下"


@pytest.mark.asyncio
async def test_orchestrator_preselected_deep_question_overrides_schema_defaults_from_user_message() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselected-five",
        user_message="围绕安全生产管理条例给我5道建筑实务单选题。只出题，不要给答案，等我作答后再批改。",
        config_overrides={
            "mode": "custom",
            "topic": "",
            "num_questions": 1,
            "question_type": "",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
        metadata={
            "raw_user_message": "围绕安全生产管理条例给我5道建筑实务单选题。只出题，不要给答案，等我作答后再批改。",
            "interaction_hints": {
                "preferred_question_type": "choice",
                "suppress_answer_reveal_on_generate": True,
            },
        },
        language="zh",
        active_capability="deep_question",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["topic"] == context.user_message
    assert context.config_overrides["num_questions"] == 5
    assert context.config_overrides["question_type"] == "choice"
    assert context.config_overrides["reveal_answers"] is False
    # plan §Phase 1 Step 1.1b (A3) — lightweight 上限 3→5。
    # 5 道选择题 + "不要给答案 / 等我作答后再批改" 应默认 lightweight=True。
    assert context.config_overrides["lightweight_generation"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Batch A — plan §Phase 1 Step 1.1 测试矩阵 (review-2026-05-20)
# 验证 classify_practice_strategy 单一规约 + 上限 1<=N<=5 + heavy negative keywords。
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_practice_strategy_lightweight_for_plain_practice_requests() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    assert classify_practice_strategy(
        message="很好，再出3题",
        reveal_preference=None,
        mode="fast",
        num_questions=3,
        has_active_object=True,
    ) == "lightweight"

    assert classify_practice_strategy(
        message="再来三道类似的",
        reveal_preference=None,
        mode="fast",
        num_questions=3,
        has_active_object=True,
    ) == "lightweight"

    assert classify_practice_strategy(
        message="继续练我刚才错的点，5题",
        reveal_preference=None,
        mode="smart",
        num_questions=5,
        has_active_object=True,
    ) == "lightweight"

    # 显式"做完再分析" — reveal_preference=False
    assert classify_practice_strategy(
        message="给我3题，做完再分析",
        reveal_preference=False,
        mode="fast",
        num_questions=3,
        has_active_object=False,
    ) == "lightweight"


def test_classify_practice_strategy_heavy_for_explicit_explanation_demand() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    # 用户明确要求"每题详细解析" — 教学展示，不是练题
    assert classify_practice_strategy(
        message="给我3题并每题详细解析",
        reveal_preference=None,
        mode="fast",
        num_questions=3,
        has_active_object=False,
    ) == "heavy"

    # 用户明确要"完整评分标准 / rubric"
    assert classify_practice_strategy(
        message="出一套完整案例题并给评分标准",
        reveal_preference=None,
        mode="smart",
        num_questions=1,
        has_active_object=False,
    ) == "heavy"

    # 模拟卷 / 押题 / 命题依据 — heavy
    assert classify_practice_strategy(
        message="给我一套模拟真题",
        reveal_preference=None,
        mode="fast",
        num_questions=1,
        has_active_object=False,
    ) == "heavy"


def test_classify_practice_strategy_heavy_for_reveal_preference_true() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    # 用户明确要"显示答案" — 不是练题
    assert classify_practice_strategy(
        message="出3题并显示答案",
        reveal_preference=True,
        mode="fast",
        num_questions=3,
        has_active_object=False,
    ) == "heavy"


def test_classify_practice_strategy_heavy_when_count_out_of_bounds() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    # 超过 5 题 — 触发分页，本轮不走 lightweight
    assert classify_practice_strategy(
        message="再出6题",
        reveal_preference=None,
        mode="fast",
        num_questions=6,
        has_active_object=False,
    ) == "heavy"

    # 0 题或负数 — 异常 num_questions 退化为 heavy
    assert classify_practice_strategy(
        message="再出几道",
        reveal_preference=None,
        mode="fast",
        num_questions=0,
        has_active_object=False,
    ) == "heavy"


def test_classify_practice_strategy_heavy_in_deep_mode() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    # deep mode 默认 heavy
    assert classify_practice_strategy(
        message="再出3题",
        reveal_preference=None,
        mode="deep",
        num_questions=3,
        has_active_object=True,
    ) == "heavy"


def test_classify_practice_strategy_heavy_when_message_is_not_practice_request() -> None:
    from deeptutor.tutorbot.teaching_modes import classify_practice_strategy

    # 不像出题请求 — 不该被路由到 lightweight，让上游统一回到 heavy / chat
    assert classify_practice_strategy(
        message="你好",
        reveal_preference=None,
        mode="fast",
        num_questions=1,
        has_active_object=False,
    ) == "heavy"


@pytest.mark.asyncio
async def test_orchestrator_routes_hen_hao_zai_chu_3_ti_to_lightweight() -> None:
    # plan §Phase 0 Step 0.1 — 真实生产 trace f49977b5... 复现：
    # "很好，再出3题" 必须进入 lightweight，且 trace 字段写入 strategy=lightweight。
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-trace-f4997",
        user_message="很好，再出3题",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["lightweight_generation"] is True
    assert context.config_overrides["num_questions"] == 3
    trace_meta = context.metadata.get("trace_metadata") or {}
    assert trace_meta.get("practice_generation.strategy") == "lightweight"
    assert trace_meta.get("practice_generation.question_count") == 3


@pytest.mark.asyncio
async def test_orchestrator_routes_5_question_practice_to_lightweight() -> None:
    # plan §Phase 1 Step 1.1b (A3) — 5 题也属于 lightweight 上限。
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-five-practice",
        user_message="再来5道类似的",
        config_overrides={},
        metadata={},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert context.config_overrides["lightweight_generation"] is True
    assert context.config_overrides["num_questions"] == 5
    trace_meta = context.metadata.get("trace_metadata") or {}
    assert trace_meta.get("practice_generation.strategy") == "lightweight"


@pytest.mark.asyncio
async def test_orchestrator_routes_home_dashboard_starter_assessment_to_deep_question() -> None:
    # 真实生产 trace 38f1770e... 复现：
    # home dashboard 的「先做一次摸底测评」不能落到普通 TutorBot 文本出题，
    # 否则 presentation parser 会生成无 hidden grading_key 的可提交题卡。
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    prompt_intent = {
        "source": "home_dashboard",
        "training_intent_id": "lti_starter",
        "training_mode": "mixed_review",
        "question_count": 3,
        "reason": "starter",
    }
    context = UnifiedContext(
        session_id="s-home-starter",
        user_message="先做一次摸底测评",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "learning_prompt_intent": prompt_intent,
        },
        metadata={"raw_user_message": "先做一次摸底测评"},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.config_overrides["force_generate_questions"] is True
    assert context.config_overrides["num_questions"] == 3
    assert context.config_overrides["learning_training_intent"] == prompt_intent
    assert context.config_overrides["lightweight_generation"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Batch A — plan §Phase 0 Step 0.2 (A4) — cancellation propagation
# 覆盖：正常完成 / outer cancel / GeneratorExit 三条路径，
# 保证 turn timeout 之后内部 capability task 不再烧 LLM。
# ─────────────────────────────────────────────────────────────────────────────


import asyncio as _asyncio
import contextlib as _contextlib


class _SlowFakeCapability:
    """Capability that emits one event then sleeps long, simulating slow LLM stream."""

    def __init__(self, sleep_seconds: float = 5.0) -> None:
        self.sleep_seconds = sleep_seconds
        self.started = _asyncio.Event()
        self.finished = _asyncio.Event()
        self.cancelled = _asyncio.Event()

    async def run(self, context: UnifiedContext, bus) -> None:
        self.started.set()
        try:
            from deeptutor.core.stream import StreamEvent, StreamEventType

            await bus.emit(
                StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="slow_fake",
                    content="thinking",
                )
            )
            await _asyncio.sleep(self.sleep_seconds)
            await bus.result({"capability": "slow_fake"}, source="slow_fake")
        except _asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.finished.set()


class _SlowRegistry:
    def __init__(self, capability: _SlowFakeCapability) -> None:
        self.capability = capability
        self.captured: list[str] = []

    def get(self, name: str) -> Any:
        self.captured.append(name)
        return self.capability

    def list_capabilities(self) -> list[str]:
        return ["chat", "deep_question", "tutorbot"]

    def get_manifests(self) -> list[dict[str, Any]]:
        return []


@pytest.mark.asyncio
async def test_orchestrator_handle_completes_normally_without_cancel_flag() -> None:
    # 正常完成路径 — cancel_propagated 不应被置位。
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-cancel-normal",
        user_message="你好",
        config_overrides={},
        metadata={},
        language="zh",
    )

    events = [event async for event in orchestrator.handle(context)]

    assert any(event.type.value == "result" for event in events)
    assert not context.metadata.get("turn_cancel_propagated")


@pytest.mark.asyncio
async def test_orchestrator_handle_propagates_cancel_to_capability_task() -> None:
    # outer cancel — capability task 必须收到 CancelledError 并尽快收尾。
    # plan §Phase 0 Step 0.2 (A4) acceptance.
    slow = _SlowFakeCapability(sleep_seconds=10.0)
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _SlowRegistry(slow)  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-cancel-propagate",
        user_message="你好",
        config_overrides={},
        metadata={},
        language="zh",
    )

    capability_event_seen = _asyncio.Event()

    async def _consume() -> None:
        # 持续消费直到拿到 capability 发出的第一个事件（说明 _run task 已启动），
        # 再卡在长 sleep 等待外层 cancel。如果只卡在 SESSION event，generator
        # 内部还未到 `task = asyncio.create_task(_run())` 行，cancellation
        # 无法传播。
        async for event in orchestrator.handle(context):
            if event.source == "slow_fake":
                capability_event_seen.set()
                await _asyncio.sleep(60)

    consumer_task = _asyncio.create_task(_consume())
    try:
        await _asyncio.wait_for(slow.started.wait(), timeout=3.0)
        await _asyncio.wait_for(capability_event_seen.wait(), timeout=3.0)
        # 模拟 outer cancel — turn timeout / FastAPI client disconnect
        consumer_task.cancel()
        with _contextlib.suppress(_asyncio.CancelledError):
            await consumer_task
    finally:
        if not consumer_task.done():
            consumer_task.cancel()
            with _contextlib.suppress(BaseException):
                await consumer_task

    # capability task 必须被取消 (在 2s grace 窗口内)
    await _asyncio.wait_for(slow.cancelled.wait(), timeout=3.0)
    assert slow.cancelled.is_set()
    assert context.metadata.get("turn_cancel_propagated") is True


@pytest.mark.asyncio
async def test_orchestrator_handle_propagates_generator_exit_when_consumer_closes_iterator() -> None:
    # GeneratorExit — FastAPI 客户端断开会触发 generator.aclose()，必须同样取消 task。
    slow = _SlowFakeCapability(sleep_seconds=10.0)
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _SlowRegistry(slow)  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-cancel-genexit",
        user_message="你好",
        config_overrides={},
        metadata={},
        language="zh",
    )

    gen = orchestrator.handle(context)
    # 持续 anext 直到拿到 capability 发出的事件 — 确保 _run task 已创建。
    saw_capability_event = False
    deadline = _asyncio.get_event_loop().time() + 3.0
    try:
        while _asyncio.get_event_loop().time() < deadline:
            event = await _asyncio.wait_for(gen.__anext__(), timeout=2.0)
            if event.source == "slow_fake":
                saw_capability_event = True
                break
    except StopAsyncIteration:
        pass

    assert saw_capability_event, "capability never emitted before aclose"
    await _asyncio.wait_for(slow.started.wait(), timeout=2.0)
    # 主动 close generator — 模拟 FastAPI consumer disconnect
    await gen.aclose()

    # capability task 必须在 2s grace 内被取消
    await _asyncio.wait_for(slow.cancelled.wait(), timeout=3.0)
    assert slow.cancelled.is_set()
    assert context.metadata.get("turn_cancel_propagated") is True
