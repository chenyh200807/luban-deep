from __future__ import annotations

from deeptutor.services.query_intent import (
    build_grounding_decision,
    build_grounding_decision_from_metadata,
    has_grounded_construction_exam_kb,
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
