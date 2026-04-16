from __future__ import annotations

import pytest

from deeptutor.services.session.context_router import (
    ContextRouteInput,
    ContextRouteLabel,
    TaskAnchorType,
    decide_context_route,
)


@pytest.mark.parametrize(
    ("route_input", "expected_label", "expected_anchor"),
    [
        (
            ContextRouteInput(user_message="你好"),
            ContextRouteLabel.LOW_SIGNAL_SOCIAL,
            TaskAnchorType.NONE,
        ),
        (
            ContextRouteInput(user_message="继续", session_followup_hint=True),
            ContextRouteLabel.SESSION_FOLLOWUP,
            TaskAnchorType.SESSION,
        ),
        (
            ContextRouteInput(user_message="这个题为什么这样做", has_active_question=True),
            ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP,
            TaskAnchorType.ACTIVE_QUESTION,
        ),
        (
            ContextRouteInput(user_message="继续刚才的学习计划", has_active_plan=True),
            ContextRouteLabel.GUIDED_PLAN_CONTINUATION,
            TaskAnchorType.GUIDED_PLAN,
        ),
        (
            ContextRouteInput(user_message="把这个记到笔记里", notebook_references=("note-1",)),
            ContextRouteLabel.NOTEBOOK_FOLLOWUP,
            TaskAnchorType.NOTEBOOK,
        ),
        (
            ContextRouteInput(user_message="你记得我偏好什么讲法吗", memory_references=("m1",), personal_recall_hint=True),
            ContextRouteLabel.PERSONAL_RECALL,
            TaskAnchorType.PERSONAL,
        ),
        (
            ContextRouteInput(user_message="你上次建议我怎么学", history_references=("s1",)),
            ContextRouteLabel.CROSS_SESSION_RECALL,
            TaskAnchorType.CROSS_SESSION,
        ),
        (
            ContextRouteInput(user_message="请讲解一下这个概念"),
            ContextRouteLabel.GENERAL_LEARNING_QUERY,
            TaskAnchorType.GENERAL,
        ),
        (
            ContextRouteInput(user_message="为什么这个规范现在这样要求", explicit_grounding=True),
            ContextRouteLabel.TOOL_OR_GROUNDING_NEEDED,
            TaskAnchorType.GROUNDING,
        ),
    ],
)
def test_decide_context_route_covers_prd_labels(route_input, expected_label, expected_anchor) -> None:
    decision = decide_context_route(route_input)

    assert decision.primary_route == expected_label
    assert decision.task_anchor_type == expected_anchor
    assert decision.route_label == expected_label.value
    assert decision.route_reasons


def test_low_signal_social_has_priority_over_other_hints() -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message="你好，继续上次那个题",
            has_active_plan=True,
            notebook_references=("note-1",),
        )
    )

    assert decision.primary_route == ContextRouteLabel.LOW_SIGNAL_SOCIAL
    assert decision.task_anchor_type == TaskAnchorType.NONE


def test_current_override_prevents_cross_session_recall() -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message="别管上次，先回答我现在这句",
            has_active_question=True,
            history_references=("session_old",),
        )
    )

    assert decision.primary_route == ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP
    assert decision.task_anchor_type == TaskAnchorType.ACTIVE_QUESTION
    assert "current_override" in decision.secondary_flags


def test_static_interaction_hints_do_not_force_session_followup_or_grounding() -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message="请讲解一下这个概念",
            session_followup_hint=True,
            explicit_grounding=True,
        )
    )

    assert decision.primary_route == ContextRouteLabel.GENERAL_LEARNING_QUERY
    assert decision.task_anchor_type == TaskAnchorType.GENERAL


def test_static_hints_still_allow_real_followup_when_text_supports_it() -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message="继续刚才的学习计划",
            session_followup_hint=True,
            has_active_plan=True,
        )
    )

    assert decision.primary_route == ContextRouteLabel.GUIDED_PLAN_CONTINUATION
    assert decision.task_anchor_type == TaskAnchorType.GUIDED_PLAN


def test_plain_why_question_stays_general_without_grounding_cues() -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message="为什么这个概念这样理解",
            session_followup_hint=True,
            explicit_grounding=True,
        )
    )

    assert decision.primary_route == ContextRouteLabel.GENERAL_LEARNING_QUERY
    assert decision.task_anchor_type == TaskAnchorType.GENERAL


@pytest.mark.parametrize(
    "message",
    [
        "不是这个题，是上一题",
        "不是一建，是二建",
        "继续刚才这个学习页面",
        "还有多少点数",
    ],
)
def test_router_handles_red_team_shift_cases_without_invalid_route(message: str) -> None:
    decision = decide_context_route(
        ContextRouteInput(
            user_message=message,
            has_active_question=True,
            has_active_plan=True,
        )
    )

    assert decision.primary_route in {
        ContextRouteLabel.LOW_SIGNAL_SOCIAL,
        ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP,
        ContextRouteLabel.GUIDED_PLAN_CONTINUATION,
        ContextRouteLabel.GENERAL_LEARNING_QUERY,
        ContextRouteLabel.SESSION_FOLLOWUP,
    }
