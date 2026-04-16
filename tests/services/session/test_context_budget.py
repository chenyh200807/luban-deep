from __future__ import annotations

from deeptutor.services.session.context_budget import ContextBudget, pack_context_candidates
from deeptutor.services.session.context_pack import ContextBlockType, ContextCandidate
from deeptutor.services.session.context_router import (
    ContextRouteDecision,
    ContextRouteLabel,
    ContextRouteReason,
    TaskAnchorType,
)


def test_pack_context_candidates_greedy_selection_respects_block_and_source_budgets() -> None:
    budget = ContextBudget(
        total_tokens=70,
        block_budgets={
            ContextBlockType.ANCHOR: 15,
            ContextBlockType.SESSION: 20,
            ContextBlockType.LEARNER: 15,
            ContextBlockType.EVIDENCE: 20,
        },
        source_budgets={
            "current_question": 15,
            "session_history": 20,
            "learner_card": 15,
            "rag": 20,
        },
        source_priority={
            "current_question": 0,
            "session_history": 1,
            "learner_card": 2,
            "rag": 3,
        },
        trace_metadata={"trace_id": "trace-1"},
    )
    route = ContextRouteDecision(
        primary_route=ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP,
        task_anchor_type=TaskAnchorType.ACTIVE_QUESTION,
        route_reasons=(ContextRouteReason.ACTIVE_QUESTION_PRESENT,),
    )
    candidates = [
        ContextCandidate(
            candidate_id="anchor-1",
            block=ContextBlockType.ANCHOR,
            source_bucket="current_question",
            content="A",
            token_cost=12,
            authority=9,
            relevance=9,
            recency=9,
            anchor_alignment=10,
            conflict_risk=0,
        ),
        ContextCandidate(
            candidate_id="anchor-2",
            block=ContextBlockType.ANCHOR,
            source_bucket="current_question",
            content="B",
            token_cost=12,
            authority=8,
            relevance=8,
            recency=8,
            anchor_alignment=9,
            conflict_risk=0,
        ),
        ContextCandidate(
            candidate_id="session-1",
            block=ContextBlockType.SESSION,
            source_bucket="session_history",
            content="C",
            token_cost=10,
            authority=7,
            relevance=7,
            recency=8,
            anchor_alignment=3,
            conflict_risk=0,
        ),
        ContextCandidate(
            candidate_id="learner-1",
            block=ContextBlockType.LEARNER,
            source_bucket="learner_card",
            content="D",
            token_cost=8,
            authority=8,
            relevance=6,
            recency=7,
            anchor_alignment=2,
            conflict_risk=0,
        ),
        ContextCandidate(
            candidate_id="evidence-1",
            block=ContextBlockType.EVIDENCE,
            source_bucket="rag",
            content="E",
            token_cost=16,
            authority=10,
            relevance=10,
            recency=9,
            anchor_alignment=1,
            conflict_risk=0,
        ),
    ]

    pack = pack_context_candidates(candidates, budget, route=route)

    assert [item.candidate_id for item in pack.anchor_block.selected_candidates] == ["anchor-1"]
    assert [item.candidate_id for item in pack.session_block.selected_candidates] == ["session-1"]
    assert [item.candidate_id for item in pack.learner_block.selected_candidates] == ["learner-1"]
    assert [item.candidate_id for item in pack.evidence_block.selected_candidates] == ["evidence-1"]
    assert [item["candidate_id"] for item in pack.anchor_block.rejected_candidates] == ["anchor-2"]
    assert "anchor-2" in pack.trace_metadata["dropped_candidate_ids"]
    assert pack.trace_metadata["token_budget_total"] == 70
    assert pack.trace_metadata["token_budget_used"] == 46
    assert pack.trace_metadata["token_budget_by_source"]["current_question"] == 12
    assert pack.trace_metadata["loaded_sources"] == [
        "current_question",
        "learner_card",
        "rag",
        "session_history",
    ]


def test_pack_context_candidates_drops_oversized_candidate() -> None:
    budget = ContextBudget(
        total_tokens=12,
        block_budgets={ContextBlockType.EVIDENCE: 12},
        source_budgets={"rag": 12},
        source_priority={"rag": 0},
    )
    candidates = [
        ContextCandidate(
            candidate_id="too-big",
            block=ContextBlockType.EVIDENCE,
            source_bucket="rag",
            content="long",
            token_cost=20,
            authority=10,
            relevance=10,
            recency=10,
            anchor_alignment=0,
            conflict_risk=0,
        )
    ]

    pack = pack_context_candidates(candidates, budget)

    assert not pack.evidence_block.selected_candidates
    assert pack.dropped_candidates[0].candidate_id == "too-big"
    assert pack.trace_metadata["token_budget_used"] == 0
