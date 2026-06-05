"""Tests for derive_question_lifecycle_scene (Plan §5.1 Single Decider Rule).

This is the implementation-point of scene authority for Tasks 3-5. ChatOrchestrator
(Task 0.7) may later escalate scene decision to a single earlier point, but for now
the derivation function lives next to the lifecycle builder and is consumed by
deep_question entry / question_followup / TutorBot loop with identical semantics.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any

import pytest

from deeptutor.services.question_lifecycle_skills import (
    derive_question_lifecycle_scene,
    is_low_information_exam_query,
    looks_like_free_text_mcq_grading_request,
    resolve_question_lifecycle_scene_decision,
)


@dataclass
class _FakeContext:
    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _mcq_followup_context(answered: bool = False) -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question_type": "mcq",
        "question": "下列哪个选项正确？",
        "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    }


def test_no_active_object_practice_intent_returns_practice_generation():
    ctx = _FakeContext(user_message="再出 3 题")
    assert derive_question_lifecycle_scene(ctx) == "practice_generation"


def test_training_by_question_count_returns_practice_generation():
    ctx = _FakeContext(user_message="用 3 道题训练项目质量计划管理")
    assert derive_question_lifecycle_scene(ctx) == "practice_generation"


@pytest.mark.parametrize(
    "message",
    [
        "用一道真题场景理解基础和地基的",
        "用一道真题场景理解项目质量计划管理",
        "通过一道真题场景讲一下地基处理",
    ],
)
def test_real_exam_scenario_learning_returns_question_review(message: str):
    ctx = _FakeContext(user_message=message)
    assert derive_question_lifecycle_scene(ctx) == "question_review"


def test_mastery_check_training_intent_wins_over_learning_report_phrase():
    ctx = _FakeContext(user_message="项目质量计划管理这个点，帮我检验一下掌握情况")
    assert derive_question_lifecycle_scene(ctx) == "practice_generation"


def test_active_object_with_submission_returns_mcq_grading():
    ctx = _FakeContext(
        user_message="B",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


def test_active_question_set_with_batch_submission_returns_mcq_grading():
    ctx = _FakeContext(
        user_message="第1题：C；第2题：A；第3题：B",
        metadata={
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {"question_id": "q_1", "question": "题1", "question_type": "choice", "correct_answer": "C"},
                    {"question_id": "q_2", "question": "题2", "question_type": "choice", "correct_answer": "A"},
                    {"question_id": "q_3", "question": "题3", "question_type": "choice", "correct_answer": "D"},
                ],
            }
        },
    )

    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


def test_active_object_without_submission_returns_question_review():
    ctx = _FakeContext(
        user_message="这道题怎么做",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "question_review"


def test_active_object_case_question_with_submission_returns_case_grading():
    case_ctx = {
        "question_id": "q1",
        "question_type": "case",
        "question": "案例题：分析该施工方案的不妥之处...",
    }
    ctx = _FakeContext(
        user_message="施工单位应组织专家论证危大工程方案",
        metadata={"question_followup_context": case_ctx},
    )
    assert derive_question_lifecycle_scene(ctx) == "case_grading"


def test_free_text_case_answer_review_returns_case_grading():
    ctx = _FakeContext(
        user_message="【案例题】背景资料：施工现场临时用电。我的答案：先验收。请批改估分。"
    )
    assert derive_question_lifecycle_scene(ctx) == "case_grading"


def test_free_text_mcq_answer_review_returns_mcq_grading():
    ctx = _FakeContext(user_message="这道单选题我选B，对吗？题干：施工现场临时用电组织设计应由谁编制？")
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


def test_learning_evidence_story_intent():
    ctx = _FakeContext(user_message="我最近哪里错")
    assert derive_question_lifecycle_scene(ctx) == "learning_evidence_story"


@pytest.mark.parametrize(
    "message",
    [
        "我最近学的怎么样",
        "我最近学得怎么样",
        "最近学习情况怎么样",
        "我的学情怎么样",
        "我当前薄弱点是什么",
        "我今年学习进度怎么样",
        "请根据我的学习记录和最近进度总结掌握情况",
        "我最近的错题集中在哪些知识点",
    ],
)
def test_personal_learning_status_intent_returns_learning_evidence_story(message: str):
    ctx = _FakeContext(user_message=message)
    assert derive_question_lifecycle_scene(ctx) == "learning_evidence_story"


def test_study_assistant_intent():
    ctx = _FakeContext(user_message="今天学什么")
    assert derive_question_lifecycle_scene(ctx) == "study_assistant"


def test_free_text_mcq_grading_requires_question_signal():
    ctx = _FakeContext(user_message="我选哪个老师的课程比较合适？")
    assert derive_question_lifecycle_scene(ctx) is None


def test_learning_support_intent():
    ctx = _FakeContext(user_message="我学不动了")
    assert derive_question_lifecycle_scene(ctx) == "learning_support"


def test_empty_message_returns_none():
    ctx = _FakeContext(user_message="")
    assert derive_question_lifecycle_scene(ctx) is None


def test_unrelated_chat_returns_none():
    ctx = _FakeContext(user_message="你好")
    assert derive_question_lifecycle_scene(ctx) is None


def test_topic_qualified_real_exam_review_returns_question_review():
    """Topic words between "一道" and "真题" still mean a real-question review."""
    ctx = _FakeContext(user_message="分析一道验槽方法真题")
    assert derive_question_lifecycle_scene(ctx) == "question_review"


@pytest.mark.parametrize("message", ["解析一道防水真题", "分析一道钢筋保护层真题"])
def test_explicit_real_exam_review_action_is_not_low_information_query(message: str):
    ctx = _FakeContext(user_message=message)

    assert is_low_information_exam_query(message) is False
    assert derive_question_lifecycle_scene(ctx) == "question_review"


@pytest.mark.parametrize(
    "message",
    [
        "2025真题",
        "历年真题",
        "防水真题",
        "2025真题有哪些",
        "2025真题答案",
        "2025真题带答案",
        "讲解2025年真题",
        "讲解2025真题答案",
        "2025真题第15题",
        "解析2025年真题第15题",
        "分析一道2025真题",
        "讲解一道历年真题",
        "解析2025真题第15题",
        "2025年一建建筑实务防水那道真题，直接告诉我答案，我在小程序刷题，别让我再复制题干。",
        "2021屋面案例第4问答案发我，快点，我在刷题页面。",
    ],
)
def test_low_information_exam_query_is_not_question_review(message: str):
    ctx = _FakeContext(user_message=message)

    assert is_low_information_exam_query(message) is True
    assert derive_question_lifecycle_scene(ctx) is None


@pytest.mark.parametrize(
    "message",
    [
        "查看这一类真题目录或考点范围",
        "查看这一类真题目录或考点范围、2025年真题",
        "查看2025年真题考点范围",
    ],
)
def test_explicit_exam_catalog_followup_is_not_blocked_as_low_information(message: str):
    ctx = _FakeContext(user_message=message)

    assert is_low_information_exam_query(message) is False
    assert derive_question_lifecycle_scene(ctx) == "exam_catalog_query"


@pytest.mark.asyncio
async def test_clarification_option_number_resolves_to_exam_catalog_query():
    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(
            user_message="1",
            metadata={
                "active_object": {
                    "object_type": "question_lifecycle_clarification",
                    "state_snapshot": {
                        "topic": "2025年真题",
                        "options": [
                            {
                                "key": "1",
                                "intent": "exam_catalog_query",
                                "label": "查看这一类真题目录或考点范围",
                            }
                        ],
                    },
                }
            },
        )
    )

    assert decision.scene == "exam_catalog_query"
    assert decision.required_anchor_status == "satisfied"
    assert decision.business_gate_result == "resolved_clarification_option"
    assert decision.selected_skill_names == (
        "construction-exam-tutor",
        "construction-study-assistant",
    )


@pytest.mark.asyncio
async def test_low_information_exam_query_business_gate_overrides_llm_review_candidate(monkeypatch):
    async def _fake_complete(**kwargs):
        assert "题目生命周期语义候选" in kwargs["system_prompt"]
        return '{"scene":"question_review","confidence":0.91,"reason":"模型误以为用户要讲评真题"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message="2025真题")
    )

    assert decision.scene is None
    assert decision.source == "llm"
    assert decision.confidence == pytest.approx(1.0)
    assert decision.required_anchor_status == "missing_question_anchor"
    assert decision.exact_question_blocked_reason == "low_information_exam_query"
    assert decision.needs_clarification is True
    assert decision.llm_scene_candidate == {
        "scene": "question_review",
        "confidence": pytest.approx(0.91),
        "reason": "模型误以为用户要讲评真题",
    }
    assert decision.business_gate_result == "blocked_low_information_exam_query"


@pytest.mark.asyncio
async def test_low_information_case_answer_request_business_gate_overrides_llm_generation_candidate(monkeypatch):
    async def _fake_complete(**kwargs):
        assert "题目生命周期语义候选" in kwargs["system_prompt"]
        return '{"scene":"practice_generation","confidence":0.91,"reason":"模型误以为用户要出题"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message="2021屋面案例第4问答案发我，快点，我在刷题页面。")
    )

    assert decision.scene is None
    assert decision.required_anchor_status == "missing_question_anchor"
    assert decision.exact_question_blocked_reason == "low_information_exam_query"
    assert decision.needs_clarification is True
    assert decision.business_gate_result == "blocked_low_information_exam_query"


@pytest.mark.asyncio
async def test_unanchored_mcq_answer_returns_clarification_decision():
    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message="我选B")
    )

    assert decision.scene is None
    assert decision.required_anchor_status == "missing_active_question"
    assert decision.exact_question_blocked_reason == "unanchored_answer_submission"
    assert decision.needs_clarification is True


@pytest.mark.asyncio
async def test_embedded_compact_mcq_with_answer_submission_is_anchored_grading():
    message = (
        "根据JGJ59，《模板支架检查评分表》保证项目有（ ）。"
        "A施工方案 B支架构造 C底座与托撑 D构配件材质 E支架稳定。"
        "我选ABCE对吗？"
    )

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message=message),
        enable_llm=False,
    )

    assert derive_question_lifecycle_scene(_FakeContext(user_message=message)) == "mcq_grading"
    assert looks_like_free_text_mcq_grading_request(message) is True
    assert decision.scene == "mcq_grading"
    assert decision.exact_question_blocked_reason == ""
    assert decision.needs_clarification is False


@pytest.mark.parametrize("terminal", ["？", "?", "！", "!"])
@pytest.mark.asyncio
async def test_embedded_mcq_options_after_terminal_mark_is_anchored_grading(terminal):
    message = (
        f"压型金属板采用轻型屋面时，屋面最小坡度宜为多少{terminal}"
        "A. 5% B. 1% C. 2% D. 3%，我选A，对吗？"
    )

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message=message),
        enable_llm=False,
    )

    assert derive_question_lifecycle_scene(_FakeContext(user_message=message)) == "mcq_grading"
    assert looks_like_free_text_mcq_grading_request(message) is True
    assert decision.scene == "mcq_grading"
    assert decision.exact_question_blocked_reason == ""
    assert decision.needs_clarification is False


@pytest.mark.asyncio
async def test_llm_scene_proposal_failure_degrades_without_blocking(monkeypatch):
    async def _fake_complete(**_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(user_message="拿一道钢筋保护层题给我讲透")
    )

    assert decision.scene is None
    assert decision.source == "llm"
    assert decision.business_gate_result == "llm_unavailable"
    assert decision.confidence == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_deterministic_active_submission_suppresses_llm_candidate(monkeypatch):
    async def _fake_complete(**_kwargs):
        raise AssertionError("LLM must not run when active submission evidence is sufficient")

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(
            user_message="我选B",
            metadata={"question_followup_context": _mcq_followup_context()},
        )
    )

    assert decision.scene == "mcq_grading"
    assert decision.source == "deterministic"
    assert decision.business_gate_result == "passed"


@pytest.mark.asyncio
async def test_free_text_mcq_answer_with_embedded_question_is_not_unanchored():
    decision = await resolve_question_lifecycle_scene_decision(
        _FakeContext(
            user_message=(
                "海洋环境下，引起混凝土内钢筋锈蚀的主要因素是（ ）。"
                "A.混凝土硬化 B.反复冻融 C.氯盐 D.硫酸盐。我选A，对吗？"
            ),
            metadata={},
        )
    )

    assert decision.scene == "mcq_grading"
    assert decision.required_anchor_status == "satisfied"
    assert decision.exact_question_blocked_reason == ""
    assert decision.needs_clarification is False


@pytest.mark.asyncio
async def test_llm_scene_proposal_fills_semantic_practice_generation_gap(monkeypatch):
    async def _fake_complete(**kwargs):
        assert "scene" in kwargs["prompt"]
        return '{"scene":"practice_generation","confidence":0.91,"reason":"用户想通过练习检验掌握"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    ctx = _FakeContext(user_message="项目质量计划管理这个点，帮我练到会")

    assert derive_question_lifecycle_scene(ctx) is None
    decision = await resolve_question_lifecycle_scene_decision(ctx)

    assert decision.scene == "practice_generation"
    assert decision.source == "llm"
    assert decision.confidence == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_llm_scene_proposal_fills_semantic_question_review_gap(monkeypatch):
    async def _fake_complete(**kwargs):
        assert "allowed_scenes" in kwargs["prompt"]
        return '{"scene":"question_review","confidence":0.88,"reason":"用户想讲解一道已有题"}'

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_complete)

    ctx = _FakeContext(user_message="拿一道钢筋保护层题给我讲透")

    assert derive_question_lifecycle_scene(ctx) is None
    decision = await resolve_question_lifecycle_scene_decision(ctx)

    assert decision.scene == "question_review"
    assert decision.source == "llm"


def test_scene_derivation_import_does_not_require_skill_loader_dependency():
    """Pure scene routing must not import TutorBot's optional skill loader."""
    code = textwrap.dedent(
        """
        import builtins
        from types import SimpleNamespace

        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("deeptutor.tutorbot.agent."):
                raise ModuleNotFoundError(name)
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from deeptutor.services.question_lifecycle_skills import derive_question_lifecycle_scene

        ctx = SimpleNamespace(user_message="分析一道验槽方法真题", metadata={})
        assert derive_question_lifecycle_scene(ctx) == "question_review"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_mixed_turn_submission_takes_priority_over_generation_intent():
    """Plan §5.1 mixed-turn priority: active-object submission always wins."""
    ctx = _FakeContext(
        user_message="B，再出 3 题",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


# ---------------------------------------------------------------------------
# attach_question_lifecycle_scene_to_context — idempotent metadata attach
# ---------------------------------------------------------------------------

from deeptutor.services.question_lifecycle_skills import (
    attach_question_lifecycle_scene_to_context,
)


def test_attach_writes_scene_and_skill_names_to_metadata():
    ctx = _FakeContext(user_message="再出 3 题")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "practice_generation"
    assert ctx.metadata["question_lifecycle_scene"] == "practice_generation"
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]


def test_attach_honors_existing_orchestrator_decision():
    """Plan §5.1: if scene already set by upstream, do not overwrite."""
    ctx = _FakeContext(
        user_message="再出 3 题",
        metadata={"question_lifecycle_scene": "study_assistant"},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "study_assistant"
    assert ctx.metadata["question_lifecycle_scene"] == "study_assistant"
    # skill_names projection still updates to match the scene that won
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-study-assistant",
    ]


def test_attach_honors_explicit_none_from_upstream():
    """Upstream may set scene=None to mean 'definitely chat fallback'."""
    ctx = _FakeContext(
        user_message="再出 3 题",
        metadata={"question_lifecycle_scene": None},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene is None
    assert ctx.metadata["question_lifecycle_scene"] is None
    assert ctx.metadata["question_lifecycle_skill_names"] == []


def test_attach_with_no_metadata_attribute_returns_none():
    class NoMeta:
        user_message = "再出 3 题"
    assert attach_question_lifecycle_scene_to_context(NoMeta()) is None


def test_attach_with_unknown_scene_writes_empty_skill_names():
    """Per plan §6.5 v2-5: low-confidence chat fallback writes scene=None, [] skills."""
    ctx = _FakeContext(user_message="你好世界")
    attach_question_lifecycle_scene_to_context(ctx)
    assert ctx.metadata["question_lifecycle_scene"] is None
    assert ctx.metadata["question_lifecycle_skill_names"] == []
