from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, TYPE_CHECKING

from .context_pack import BLOCK_ORDER, ContextBlockType, ContextCandidate, ContextPack, ContextPackBlock

if TYPE_CHECKING:
    from .context_router import ContextRouteDecision


@dataclass(frozen=True, slots=True)
class ContextBudget:
    total_tokens: int
    block_budgets: Mapping[ContextBlockType, int]
    source_budgets: Mapping[str, int]
    source_priority: Mapping[str, int] = field(default_factory=dict)
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def block_budget(self, block: ContextBlockType) -> int:
        return max(0, int(self.block_budgets.get(block, 0) or 0))

    def source_budget(self, source_bucket: str) -> int:
        if source_bucket in self.source_budgets:
            return max(0, int(self.source_budgets[source_bucket] or 0))
        return max(0, int(self.total_tokens))

    def source_rank(self, source_bucket: str) -> int:
        if source_bucket in self.source_priority:
            return int(self.source_priority[source_bucket] or 0)
        return len(self.source_priority) + 100


@dataclass(frozen=True, slots=True)
class CandidateScore:
    source_rank: int
    authority: int
    relevance: int
    recency: int
    anchor_alignment: int
    conflict_risk: int
    token_cost: int
    candidate_id: str

    def sort_key(self) -> tuple[int, int, int, int, int, int, int, str]:
        return (
            self.source_rank,
            -self.authority,
            -self.relevance,
            -self.recency,
            -self.anchor_alignment,
            self.conflict_risk,
            self.token_cost,
            self.candidate_id,
        )


def _score_candidate(candidate: ContextCandidate, budget: ContextBudget) -> CandidateScore:
    return CandidateScore(
        source_rank=budget.source_rank(candidate.source_bucket),
        authority=int(candidate.authority or 0),
        relevance=int(candidate.relevance or 0),
        recency=int(candidate.recency or 0),
        anchor_alignment=int(candidate.anchor_alignment or 0),
        conflict_risk=int(candidate.conflict_risk or 0),
        token_cost=max(0, int(candidate.token_cost or 0)),
        candidate_id=str(candidate.candidate_id or ""),
    )


def _group_candidates(candidates: Sequence[ContextCandidate]) -> dict[ContextBlockType, list[ContextCandidate]]:
    grouped: dict[ContextBlockType, list[ContextCandidate]] = {block: [] for block in BLOCK_ORDER}
    for candidate in candidates:
        grouped.setdefault(candidate.block, []).append(candidate)
    return grouped


def pack_context_candidates(
    candidates: Sequence[ContextCandidate],
    budget: ContextBudget,
    *,
    route: "ContextRouteDecision | None" = None,
) -> ContextPack:
    grouped = _group_candidates(candidates)
    block_remaining: dict[ContextBlockType, int] = {
        block: budget.block_budget(block) for block in BLOCK_ORDER
    }
    source_remaining: dict[str, int] = {str(key): max(0, int(value or 0)) for key, value in budget.source_budgets.items()}
    total_remaining = max(0, int(budget.total_tokens or 0))

    selected_by_block: dict[ContextBlockType, list[ContextCandidate]] = {block: [] for block in BLOCK_ORDER}
    rejected_by_block: dict[ContextBlockType, list[dict[str, Any]]] = {block: [] for block in BLOCK_ORDER}
    selected: list[ContextCandidate] = []
    dropped: list[ContextCandidate] = []

    for block in BLOCK_ORDER:
        ordered_candidates = sorted(
            grouped.get(block, []),
            key=lambda item: _score_candidate(item, budget).sort_key(),
        )
        for candidate in ordered_candidates:
            token_cost = max(0, int(candidate.token_cost or 0))
            source_budget = source_remaining.get(candidate.source_bucket, budget.source_budget(candidate.source_bucket))
            fits = (
                token_cost > 0
                and token_cost <= total_remaining
                and token_cost <= block_remaining[block]
                and token_cost <= source_budget
            )
            score = _score_candidate(candidate, budget)
            if not fits:
                dropped.append(candidate)
                rejected_by_block[block].append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "source_bucket": candidate.source_bucket,
                        "token_cost": token_cost,
                        "reason": "budget_exhausted",
                        "score": score.sort_key(),
                    }
                )
                continue

            selected.append(candidate)
            selected_by_block[block].append(candidate)
            block_remaining[block] -= token_cost
            source_remaining[candidate.source_bucket] = source_budget - token_cost
            total_remaining -= token_cost

    blocks: dict[ContextBlockType, ContextPackBlock] = {}
    for block in BLOCK_ORDER:
        used_tokens = sum(int(item.token_cost or 0) for item in selected_by_block[block])
        blocks[block] = ContextPackBlock(
            block=block,
            token_budget=budget.block_budget(block),
            used_tokens=used_tokens,
            remaining_tokens=max(0, block_remaining[block]),
            selected_candidates=tuple(selected_by_block[block]),
            rejected_candidates=tuple(rejected_by_block[block]),
        )

    used_total = sum(int(item.token_cost or 0) for item in selected)
    consumed_source_budgets = {
        bucket: max(0, int(budget.source_budgets.get(bucket, budget.total_tokens)) - int(remaining))
        for bucket, remaining in source_remaining.items()
    }
    trace_metadata = {
        **dict(budget.trace_metadata),
        "context_route": route.primary_route.value if route is not None else None,
        "task_anchor_type": route.task_anchor_type.value if route is not None else None,
        "route_reasons": [reason.value for reason in route.route_reasons] if route is not None else [],
        "token_budget_total": int(budget.total_tokens or 0),
        "token_budget_used": used_total,
        "token_budget_remaining": max(0, total_remaining),
        "token_budget_by_block": {block.value: blocks[block].used_tokens for block in BLOCK_ORDER},
        "token_budget_by_source": consumed_source_budgets,
        "candidate_sources": sorted({candidate.source_bucket for candidate in candidates if candidate.source_bucket}),
        "loaded_sources": sorted({candidate.source_bucket for candidate in selected if candidate.source_bucket}),
        "excluded_sources": sorted({candidate.source_bucket for candidate in dropped if candidate.source_bucket}),
        "selected_candidate_ids": [candidate.candidate_id for candidate in selected],
        "dropped_candidate_ids": [candidate.candidate_id for candidate in dropped],
    }

    return ContextPack(
        route=route,
        budget=budget,
        anchor_block=blocks[ContextBlockType.ANCHOR],
        session_block=blocks[ContextBlockType.SESSION],
        learner_block=blocks[ContextBlockType.LEARNER],
        evidence_block=blocks[ContextBlockType.EVIDENCE],
        selected_candidates=tuple(selected),
        dropped_candidates=tuple(dropped),
        trace_metadata=trace_metadata,
    )


__all__ = [
    "CandidateScore",
    "ContextBudget",
    "pack_context_candidates",
]
