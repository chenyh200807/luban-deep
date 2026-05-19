from __future__ import annotations

from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def _group(plan, name: str):
    return plan.source_groups[name]


def test_build_retrieval_plan_for_standard_clause() -> None:
    plan = build_retrieval_plan(
        query="GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
        include_questions_default=True,
    )

    assert plan.intent == "standard_clause"
    assert plan.query_shape == "standard_like"
    assert _group(plan, "standard").enabled is True
    assert _group(plan, "standard_code_exact").enabled is True
    assert _group(plan, "questions_bank").enabled is False
    assert "standard_code" in plan.reasons


def test_build_retrieval_plan_for_weak_point_review() -> None:
    plan = build_retrieval_plan(
        query="我老是案例题采分点漏写怎么办",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    assert plan.intent == "weak_point_review"
    assert _group(plan, "compiled_learning_truth").enabled is True
    assert _group(plan, "questions_bank").enabled is True
    assert _group(plan, "standard").enabled is True
    assert "weak_point_terms" in plan.reasons
    assert "compiled_learning_truth" in plan.authority_order


def test_build_retrieval_plan_ignores_nested_compiled_truth_payload() -> None:
    plan = build_retrieval_plan(
        query="我老是案例题采分点漏写怎么办",
        include_questions_default=True,
        routing_metadata={
            "compiled_learning_truth": {
                "subject": "construction_exam_learning_truth",
                "weak_points": [{"concept_id": "1A432000"}],
            }
        },
    )

    assert plan.intent == "weak_point_review"
    assert _group(plan, "compiled_learning_truth").enabled is False


def test_build_retrieval_plan_for_exact_question_keeps_exact_first() -> None:
    plan = build_retrieval_plan(
        query="单选题：确定屋面防水工程的防水等级应根据什么 A 建筑物类别 B 建筑物用途",
        include_questions_default=True,
        question_type="single_choice",
    )

    assert plan.intent == "training_question_needed"
    assert _group(plan, "questions_bank").enabled is True
    assert plan.authority_order.index("exact_question") < plan.authority_order.index("compiled_learning_truth")


def test_build_retrieval_plan_does_not_select_compiled_truth_for_standard_clause() -> None:
    plan = build_retrieval_plan(
        query="GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    assert plan.intent == "standard_clause"
    assert _group(plan, "standard_code_exact").enabled is True
    assert _group(plan, "compiled_learning_truth").enabled is False


def test_build_retrieval_plan_for_next_training_selects_compiled_truth() -> None:
    plan = build_retrieval_plan(
        query="下一题给我练专家论证",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    assert plan.intent == "next_training"
    assert _group(plan, "compiled_learning_truth").enabled is True
