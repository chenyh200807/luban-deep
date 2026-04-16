from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .context_budget import ContextBudget
    from .context_router import ContextRouteDecision


class ContextBlockType(str, Enum):
    ANCHOR = "anchor"
    SESSION = "session"
    LEARNER = "learner"
    EVIDENCE = "evidence"


BLOCK_ORDER: tuple[ContextBlockType, ...] = (
    ContextBlockType.ANCHOR,
    ContextBlockType.SESSION,
    ContextBlockType.LEARNER,
    ContextBlockType.EVIDENCE,
)


@dataclass(frozen=True, slots=True)
class ContextCandidate:
    candidate_id: str
    block: ContextBlockType
    source_bucket: str
    content: str
    token_cost: int
    authority: int = 0
    relevance: int = 0
    recency: int = 0
    anchor_alignment: int = 0
    conflict_risk: int = 0
    source_type: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextPackBlock:
    block: ContextBlockType
    token_budget: int
    used_tokens: int
    remaining_tokens: int
    selected_candidates: tuple[ContextCandidate, ...] = ()
    rejected_candidates: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ContextPack:
    route: "ContextRouteDecision | None"
    budget: "ContextBudget"
    anchor_block: ContextPackBlock
    session_block: ContextPackBlock
    learner_block: ContextPackBlock
    evidence_block: ContextPackBlock
    selected_candidates: tuple[ContextCandidate, ...]
    dropped_candidates: tuple[ContextCandidate, ...]
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def blocks(self) -> tuple[ContextPackBlock, ...]:
        return (
            self.anchor_block,
            self.session_block,
            self.learner_block,
            self.evidence_block,
        )


__all__ = [
    "BLOCK_ORDER",
    "ContextBlockType",
    "ContextCandidate",
    "ContextPack",
    "ContextPackBlock",
]
