from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CitationState = Literal["supported", "partial", "no_public_source", "degraded"]
CitationSurface = Literal["student", "reviewer", "internal"]
CitationVisibility = Literal["public", "private"]


@dataclass(frozen=True)
class CitationPolicy:
    surface: CitationSurface = "student"
    require_footer: bool = True
    max_public_refs: int = 8
    min_claim_ref_score: float = 0.18
    max_public_quote_chars: int = 180


@dataclass(frozen=True)
class CitationSourceRef:
    citation_id: str
    marker: str
    source_type: str
    title: str
    locator: str
    source_id: str = ""
    source_table: str = ""
    stable_id: str = ""
    source_span: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    quote_hash: str = ""
    public_quote: str = ""
    visibility: CitationVisibility = "public"
    authority_rank: int = 0
    evidence_level: str = ""

    @property
    def is_public(self) -> bool:
        return self.visibility == "public"

    def to_public_dict(self) -> dict[str, Any]:
        if not self.is_public:
            return {}
        return {
            "citation_id": self.citation_id,
            "marker": self.marker,
            "source_type": self.source_type,
            "title": self.title,
            "locator": self.locator,
            "source_id": self.source_id,
            "source_table": self.source_table,
            "stable_id": self.stable_id,
            "source_span": dict(self.source_span),
            "content_hash": self.content_hash,
            "quote_hash": self.quote_hash,
            "public_quote": self.public_quote,
            "authority_rank": self.authority_rank,
            "evidence_level": self.evidence_level,
        }


@dataclass(frozen=True)
class CitedClaim:
    claim_id: str
    text: str
    citation_ids: list[str]
    confidence: float


@dataclass(frozen=True)
class CitationBundle:
    citation_state: CitationState
    refs: list[CitationSourceRef]
    claims: list[CitedClaim]
    footer_text: str

    @classmethod
    def no_public_source(cls) -> "CitationBundle":
        return cls(
            citation_state="no_public_source",
            refs=[],
            claims=[],
            footer_text=(
                "依据\n"
                "本轮未使用可公开引用的教材、规范、题库或学习证据；"
                "以上内容仅为通用对话说明，不进入学习事实或评分依据。"
            ),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "citation_state": self.citation_state,
            "refs": [item for ref in self.refs if (item := ref.to_public_dict())],
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "citation_ids": list(claim.citation_ids),
                    "confidence": claim.confidence,
                }
                for claim in self.claims
            ],
            "footer_text": self.footer_text,
        }


@dataclass(frozen=True)
class CitedAnswer:
    response: str
    bundle: CitationBundle
