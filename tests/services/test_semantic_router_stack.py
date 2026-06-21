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


@pytest.mark.asyncio
async def test_floating_followup_does_not_resume_suspended_without_back_reference() -> None:
    # 断裂链②C2 / 浮知识 (学生军团 Phase A 黄金复现器 H2): 一道题答完后被挂起; 学员问一个
    # 延伸知识问(不显式回切、非作答),被松匹配成挂起题的 ask_followup。当前会被提升为
    # switch_to_new_object + route_to_followup_explainer → 触发 _is_unresolved_switch_followup
    # 拒答("你想回到/切换到的那道题…没能定位到")。延伸知识问应当作开放追问、不重新激活挂起题,
    # 即不得产生 unresolved-switch 拒答签名。
    active_object = _question_active_object("q_current", "当前题(弱匹配)", "D")
    suspended_object = _question_active_object("q_prev_scaffold", "脚手架题", "A")

    async def fake_interpret(_message, question_context):
        qid = str((question_context or {}).get("question_id") or "")
        if qid == "q_current":
            return {"intent": "unrelated", "confidence": 0.5, "answers": [], "reason": "当前题不匹配"}
        if qid == "q_prev_scaffold":
            return {"intent": "ask_followup", "confidence": 0.9, "answers": [], "reason": "像在追问脚手架题"}
        return None

    routing = await resolve_question_semantic_routing(
        user_message="那悬挑脚手架的高度怎么算？有什么特殊要求？",  # 无"上一题/刚才那题"等回切标记
        metadata={"active_object": active_object, "suspended_object_stack": [suspended_object]},
        history_context="",
        interpret_followup_action=fake_interpret,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )

    decision = routing.turn_semantic_decision or {}
    assert not (
        str(decision.get("relation_to_active_object")) == "switch_to_new_object"
        and str(decision.get("next_action")) == "route_to_followup_explainer"
    ), f"延伸知识问被误提升为切题拒答签名: {decision}"
    if routing.active_object is not None:
        assert routing.active_object.get("object_id") != "q_prev_scaffold", "延伸知识问不应把挂起题设为新active"


@pytest.mark.asyncio
async def test_cached_explanation_action_re_resolves_with_history_to_other_question() -> None:
    """Stage C activation (2026-06-21): an explanation turn that references a DIFFERENT
    historical question ("回到我最开始做错的那道题").

    The followup action is resolved upstream (turn_runtime) BEFORE conversation history
    is built, so it only saw the active set → ask_followup (binds to the stale active
    object). Where the canonical history IS available (this router), a cached
    NON-submission action must be DROPPED and re-resolved with history so the relation
    authority can upgrade to ask_other_question → unresolved-switch → context-continuous
    main LLM. Submissions keep their deterministic cache (never re-routed to main LLM).
    """
    from deeptutor.services.semantic_router import is_unresolved_switch_followup

    active_object = _question_active_object("q_current", "结构找坡题", "C")

    calls = {"n": 0}

    # NOTE: history reaches the classifier via the production lambda closure
    # (semantic_router.py — history_context=history_context); that wiring is covered by
    # test_resolve_turn_semantic_decision_maps_llm_answer_to_grading. Here we inject the
    # callable directly to assert the cache-drop + re-resolution behavior.
    async def fake_interpret(_message, question_context, *, history_context=""):
        calls["n"] += 1
        return {
            "intent": "ask_other_question",
            "confidence": 0.9,
            "preserve_other_answers": False,
            "answers": [],
            "reason": "用户回指对话更早的另一道题，不是当前 active。",
        }

    routing = await resolve_question_semantic_routing(
        user_message="回到我最开始做错的那道题，正确答案为什么是那个",
        metadata={
            "active_object": active_object,
            # cached upstream (no-history) explanation action that binds to active:
            "question_followup_action": {
                "intent": "ask_followup",
                "confidence": 0.8,
                "answers": [],
                "reason": "stale no-history cache",
            },
        },
        history_context=(
            "Assistant: 第1题 种植平屋面坡度不应小于（2%）\n"
            "Assistant: 第2题 结构找坡最小坡度（3%）"
        ),
        interpret_followup_action=fake_interpret,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )

    assert calls["n"] >= 1, "non-submission cache must be dropped and re-resolved with history"
    decision = routing.turn_semantic_decision
    assert decision["relation_to_active_object"] == "switch_to_new_object"
    assert decision["next_action"] == "route_to_followup_explainer"
    assert is_unresolved_switch_followup(decision)


@pytest.mark.asyncio
async def test_cached_submission_action_is_not_dropped_or_rerouted() -> None:
    """Negative guard: a cached SUBMISSION (grading) action must NOT be dropped/re-resolved
    — grading stays on the structured deterministic path and is never sent to the main LLM."""
    active_object = _question_active_object("q_current", "结构找坡题", "C")

    calls = {"n": 0}

    async def fake_interpret(_message, question_context, *, history_context=""):
        calls["n"] += 1
        return {"intent": "ask_other_question", "confidence": 0.9, "answers": [], "reason": "should-not-run"}

    routing = await resolve_question_semantic_routing(
        user_message="我选B",
        metadata={
            "active_object": active_object,
            "question_followup_action": {
                "intent": "answer_questions",
                "confidence": 0.95,
                "answers": [{"index": 1, "question_id": "q_current", "user_answer": "B"}],
                "reason": "submission",
            },
        },
        history_context="Assistant: 第1题...\nAssistant: 第2题...",
        interpret_followup_action=fake_interpret,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )

    assert calls["n"] == 0, "cached submission action must NOT be dropped/re-resolved"
    decision = routing.turn_semantic_decision
    assert decision["next_action"] == "route_to_grading"
