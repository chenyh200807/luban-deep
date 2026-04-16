from __future__ import annotations

from deeptutor.services.session.context_budget import ContextBudget, pack_context_candidates
from deeptutor.services.session.context_pack import ContextBlockType, ContextCandidate
from deeptutor.services.session.context_router import (
    ContextRouteDecision,
    ContextRouteLabel,
    ContextRouteReason,
    TaskAnchorType,
)
from deeptutor.services.session.context_trace import (
    build_context_trace_summary,
    resolve_escalation_level,
    resolve_target_escalation_level,
)


def test_resolve_escalation_level_matches_progressive_loading_contract() -> None:
    assert resolve_escalation_level(loaded_sources=["current_question", "session_history"]) == 1
    assert resolve_escalation_level(loaded_sources=["current_question", "active_plan"]) == 2
    assert resolve_escalation_level(loaded_sources=["history"]) == 3
    assert resolve_escalation_level(loaded_sources=[], route_label="general_learning_query") == 1
    assert resolve_escalation_level(loaded_sources=["history"], fallback_path="legacy") == 0
    assert resolve_target_escalation_level(route_label="general_learning_query") == 1
    assert resolve_target_escalation_level(route_label="guided_plan_continuation") == 2
    assert resolve_target_escalation_level(route_label="cross_session_recall") == 3


def test_build_context_trace_summary_includes_block_level_debug_details() -> None:
    budget = ContextBudget(
        total_tokens=40,
        block_budgets={
            ContextBlockType.ANCHOR: 12,
            ContextBlockType.SESSION: 12,
            ContextBlockType.LEARNER: 8,
            ContextBlockType.EVIDENCE: 8,
        },
        source_budgets={
            "current_question": 12,
            "session_history": 12,
            "history": 8,
        },
        source_priority={
            "current_question": 0,
            "session_history": 1,
            "history": 2,
        },
    )
    route = ContextRouteDecision(
        primary_route=ContextRouteLabel.CROSS_SESSION_RECALL,
        task_anchor_type=TaskAnchorType.CROSS_SESSION,
        route_reasons=(ContextRouteReason.CROSS_SESSION_REFERENCE_PRESENT,),
    )
    pack = pack_context_candidates(
        [
            ContextCandidate(
                candidate_id="anchor-1",
                block=ContextBlockType.ANCHOR,
                source_bucket="current_question",
                source_type="active_question_context",
                source_id="q1",
                content="当前问题",
                token_cost=8,
                authority=10,
                relevance=10,
                recency=10,
                anchor_alignment=10,
            ),
            ContextCandidate(
                candidate_id="session-1",
                block=ContextBlockType.SESSION,
                source_bucket="session_history",
                source_type="session_history",
                source_id="s1",
                content="会话摘要",
                token_cost=10,
                authority=8,
                relevance=8,
                recency=9,
                anchor_alignment=8,
            ),
            ContextCandidate(
                candidate_id="history-1",
                block=ContextBlockType.EVIDENCE,
                source_bucket="history",
                source_type="history",
                source_id="old-session",
                content="历史命中",
                token_cost=6,
                authority=6,
                relevance=8,
                recency=5,
                anchor_alignment=4,
                metadata={"title": "旧会话"},
            ),
        ],
        budget,
        route=route,
    )

    trace = build_context_trace_summary(pack, fallback_path="")

    assert trace["escalation_level"] == 3
    assert trace["target_escalation_level"] == 3
    assert trace["blocks"]["anchor"]["selected_candidates"][0]["candidate_id"] == "anchor-1"
    assert trace["blocks"]["evidence"]["selected_candidates"][0]["metadata"]["title"] == "旧会话"
    assert trace["blocks"]["session"]["token_budget"] == 12
