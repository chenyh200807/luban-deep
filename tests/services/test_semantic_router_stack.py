from __future__ import annotations

import pytest

from deeptutor.services.semantic_router import (
    apply_active_object_transition,
    build_active_object_from_question_context,
    resolve_question_semantic_routing,
)
from deeptutor.services.question_followup import (
    looks_like_question_followup,
    resolve_submission_attempt,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


def _question_active_object(question_id: str, prompt: str, correct_answer: str) -> dict[str, object]:
    active_object = build_active_object_from_question_context(
        {
            "question_id": question_id,
            "question": prompt,
            "question_type": "choice",
            "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
            "correct_answer": correct_answer,
        },
        source_turn_id=f"turn-{question_id}",
    )
    assert active_object is not None
    return active_object


def test_apply_active_object_transition_pushes_previous_active_into_stack_on_switch() -> None:
    previous_active_object = _question_active_object("q_old", "旧题", "A")
    next_active_object = _question_active_object("q_new", "新题", "B")

    transitioned_active_object, transitioned_stack = apply_active_object_transition(
        previous_active_object=previous_active_object,
        previous_suspended_object_stack=[],
        turn_semantic_decision={
            "relation_to_active_object": "switch_to_new_object",
            "next_action": "route_to_generation",
            "target_object_ref": {"object_type": "single_question", "object_id": "q_new"},
            "allowed_patch": ["set_active_object"],
            "confidence": 1.0,
            "reason": "生成了新的题目对象。",
        },
        resolved_active_object=next_active_object,
    )

    assert transitioned_active_object is not None
    assert transitioned_active_object["object_id"] == "q_new"
    assert [item["object_id"] for item in transitioned_stack] == ["q_old"]


@pytest.mark.asyncio
async def test_semantic_router_resumes_suspended_candidate_when_previous_marker_points_to_stack() -> None:
    active_object = _question_active_object("q_current", "当前题", "D")
    suspended_object = _question_active_object("q_previous", "上一题", "A")

    async def fake_interpret(
        _message: str,
        question_context: dict[str, object] | None,
    ) -> dict[str, object] | None:
        question_id = str((question_context or {}).get("question_id") or "")
        if question_id == "q_current":
            return {
                "intent": "unrelated",
                "confidence": 0.6,
                "preserve_other_answers": False,
                "answers": [],
                "reason": "当前 active question 不匹配。",
            }
        if question_id == "q_previous":
            return {
                "intent": "answer_questions",
                "confidence": 0.92,
                "preserve_other_answers": False,
                "answers": [{"index": 1, "question_id": "q_previous", "user_answer": "A"}],
                "reason": "用户在回答上一题。",
            }
        return None

    routing = await resolve_question_semantic_routing(
        user_message="不是这题，是上一题，我选A",
        metadata={
            "active_object": active_object,
            "suspended_object_stack": [suspended_object],
        },
        history_context="",
        interpret_followup_action=fake_interpret,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )

    assert routing.active_object is not None
    assert routing.active_object["object_id"] == "q_previous"
    assert [item["object_id"] for item in routing.suspended_object_stack] == ["q_current"]
    assert routing.turn_semantic_decision["relation_to_active_object"] == "switch_to_new_object"
    assert routing.turn_semantic_decision["next_action"] == "route_to_grading"
    assert "resume_suspended_object" in routing.turn_semantic_decision["allowed_patch"]
