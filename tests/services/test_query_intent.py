from __future__ import annotations

import pytest

from deeptutor.services.query_intent import (
    build_grounding_decision,
    build_grounding_decision_from_metadata,
    has_grounded_construction_exam_kb,
    looks_like_construction_exam_knowledge_query,
    query_requires_current_info,
    query_uses_learner_state_authority,
)


def test_has_grounded_construction_exam_kb_recognizes_aliases() -> None:
    assert has_grounded_construction_exam_kb(default_kb="construction-exam") is True
    assert (
        has_grounded_construction_exam_kb(
            knowledge_bases=["demo"],
            kb_aliases=["construction_exam_tutor"],
        )
        is True
    )
    assert has_grounded_construction_exam_kb(knowledge_bases=["demo"]) is False


def test_build_grounding_decision_forces_retrieval_first_for_grounded_followup() -> None:
    decision = build_grounding_decision(
        query="这道题我为什么错了，结合教材再解释一下",
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
        followup_question=True,
        answer_type="knowledge_explainer",
    )

    assert decision.grounded_construction_exam_runtime is True
    assert decision.should_force_retrieval_first is True
    assert "force_retrieval_first" in decision.reasons


def test_build_grounding_decision_from_metadata_prefetches_current_info_query() -> None:
    decision = build_grounding_decision_from_metadata(
        query="2026年教材变化有哪些更新",
        runtime_metadata={
            "default_kb": "construction-exam",
            "knowledge_bases": ["construction-exam"],
            "current_info_required": True,
        },
        rag_enabled=True,
        tutorbot_context=True,
        exact_question_candidate=False,
        practice_generation_request=False,
    )

    assert decision.current_info_required is True
    assert decision.textbook_delta_query is True
    assert decision.should_prefetch_grounded_rag is True


def test_build_grounding_decision_prefetches_exact_question_candidate() -> None:
    decision = build_grounding_decision(
        query="背景资料：某旧城改造工程。问题：4. 计算项目成本。",
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
        exact_question_candidate=True,
    )

    assert decision.should_prefetch_grounded_rag is True
    assert "prefetch_grounded_rag" in decision.reasons


def test_build_grounding_decision_marks_exam_schedule_queries_current_info() -> None:
    decision = build_grounding_decision(
        query="2026一建考试时间",
        rag_enabled=True,
        tutorbot_context=True,
    )

    assert decision.current_info_required is True
    assert "current_info_required" in decision.reasons


@pytest.mark.parametrize(
    "query",
    [
        "当前政策有哪些变化",
        "今年一建报名时间",
        "最近报名时间",
        "最近考试安排",
        "最近住建部新规",
        "2026年教材变化有哪些更新",
    ],
)
def test_build_grounding_decision_keeps_public_current_info_queries(query: str) -> None:
    decision = build_grounding_decision(
        query=query,
        rag_enabled=True,
        tutorbot_context=True,
    )

    assert decision.current_info_required is True
    assert "current_info_required" in decision.reasons


@pytest.mark.parametrize(
    "query",
    [
        "我最近学的怎么样",
        "我最近学得怎么样",
        "最近学习状态怎么样",
        "我当前薄弱点是什么",
        "我今年学习进度怎么样",
        "请根据我的学习记录和最近进度安排下一步学习",
    ],
)
def test_build_grounding_decision_does_not_treat_personal_learning_status_as_current_info(
    query: str,
) -> None:
    decision = build_grounding_decision(
        query=query,
        rag_enabled=True,
        tutorbot_context=True,
    )

    assert decision.current_info_required is False
    assert "current_info_required" not in decision.reasons
    assert decision.should_prefetch_grounded_rag is False


def test_build_grounding_decision_does_not_force_retrieval_for_long_personal_learning_status() -> None:
    decision = build_grounding_decision(
        query="请根据我的学习记录和最近进度总结掌握情况，并给我下一步学习建议、薄弱点复盘和今天训练安排",
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
    )

    assert decision.current_info_required is False
    assert decision.should_force_retrieval_first is False
    assert decision.should_prefetch_grounded_rag is False
    assert "force_retrieval_first" not in decision.reasons


@pytest.mark.parametrize(
    "query",
    ["今天学什么", "下一步怎么做", "请根据我的学习记录安排今天学什么", "给我安排训练建议"],
)
def test_build_grounding_decision_keeps_study_assistant_internal_with_current_info_hint(
    query: str,
) -> None:
    decision = build_grounding_decision(
        query=query,
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
        current_info_required_hint=True,
    )

    assert decision.current_info_required is False
    assert decision.should_force_retrieval_first is False
    assert decision.should_prefetch_grounded_rag is False


@pytest.mark.parametrize("query", ["我学不动了", "最近备考很焦虑", "压力好大，想放弃"])
def test_build_grounding_decision_keeps_learning_support_internal_with_current_info_hint(
    query: str,
) -> None:
    decision = build_grounding_decision(
        query=query,
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
        current_info_required_hint=True,
    )

    assert decision.current_info_required is False
    assert decision.should_force_retrieval_first is False
    assert decision.should_prefetch_grounded_rag is False


@pytest.mark.parametrize(
    "query",
    [
        "给零基础学员一份一建学习建议",
        "我想给零基础学员一份一建学习建议",
        "我想了解2026年一建备考趋势和复习建议",
        "请结合2026年一建备考趋势制定复习建议",
    ],
)
def test_non_personal_study_advice_can_use_external_grounding_when_requested(
    query: str,
) -> None:
    decision = build_grounding_decision(
        query=query,
        default_kb="construction-exam",
        knowledge_bases=["construction-exam"],
        rag_enabled=True,
        tutorbot_context=True,
        current_info_required_hint=True,
    )

    assert decision.current_info_required is True
    assert decision.should_prefetch_grounded_rag is True
    assert query_uses_learner_state_authority(query) is False


@pytest.mark.parametrize("query", ["联网查询我的学习记录", "联网查我最近学的怎么样"])
def test_personal_learning_status_keeps_internal_authority_even_with_web_search_words(
    query: str,
) -> None:
    assert query_requires_current_info(query) is False


def test_build_grounding_decision_marks_explicit_web_search_command_current_info() -> None:
    decision = build_grounding_decision(
        query="你不是能联网的吗，联网查询",
        rag_enabled=True,
        tutorbot_context=True,
    )

    assert decision.current_info_required is True
    assert "current_info_required" in decision.reasons


@pytest.mark.parametrize(
    "query",
    [
        "请说明屋面防水构造的作用，并指出答题采分点。",
        "一建建筑实务里钢筋保护层怎么考？",
    ],
)
def test_construction_exam_knowledge_query_detection(query: str) -> None:
    assert looks_like_construction_exam_knowledge_query(query) is True


@pytest.mark.parametrize("query", ["你好", "谢谢", "我学不动了"])
def test_social_or_learning_support_query_is_not_construction_exam_knowledge(query: str) -> None:
    assert looks_like_construction_exam_knowledge_query(query) is False
