"""Single-authority builder for the RAG evidence bundle.

``evidence_bundle`` is the structured trace of one RAG retrieval — the sources, content,
retrieval plan, ranking trace, exact-question match and retrieval status — surfaced to
every downstream reader (the KB-maintenance contract validator, the tutorbot/builtin trace
summarizers, the open-world grading-grounding renderer, the question-generation coordinator).

Before this module it was assembled INLINE at four divergent sites (the kbv5 pipeline, the
supabase pipeline's ``_build_evidence_bundle`` + post-mutations, the ``RAGService`` fallback
for lanes that emit none, and the historical-question result) with NO single authority —
four drifting shapes that could not be registered or field-pinned. This module is the single
producer + single schema authority: every lane calls :func:`build_evidence_bundle`, which
emits ONE canonical shape.

Shape (register-before-use, schema-governance):
  - The TOP-LEVEL fields are the cross-consumer contract (the fields actually read across
    modules + carried into the boundary trace summary). They are field-pinned as T2
    ``rag_evidence_bundle.v1`` in contracts/schema_registry.yaml.
  - ``trace`` is the single bucket for LANE-SPECIFIC diagnostics (kbv5 embed/latency, supabase
    query-rewrite/timings, historical canonical-question context, …). These are NOT
    cross-consumer contract — no reader depends on them — so they live in one named bucket
    instead of as scattered, drifting top-level keys. Collapsing the divergence into ``trace``
    preserves every diagnostic (no data loss) while keeping the contract clean and pinnable.

Lane coverage (single authority): the kbv5, supabase and historical-question lanes each call
:func:`build_evidence_bundle` directly. The llamaindex lane (and the supabase empty-query
early return) emit a result with NO bundle on purpose — ``RAGService.search`` then synthesizes
one through this same builder (the fallback path). So every result that reaches a consumer
carries a builder-produced bundle; the service fallback IS llamaindex's bundle builder. (We do
NOT add a separate builder call inside the llamaindex pipeline: it would duplicate the fallback
for no live caller — ``pipeline.search`` is only reached via ``RAGService.search``.)

Deterministic and pure: no LLM, no network, no DB.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# Canonical schema id for register-before-use (schema-governance P2#8): this module is the
# single producer + single schema authority for the RAG evidence bundle. Registered as T2
# runtime-canonical (field-pinned) in contracts/schema_registry.yaml.
SCHEMA_ID = "rag_evidence_bundle.v1"


@dataclass(frozen=True)
class EvidenceBundle:
    """The canonical RAG retrieval evidence bundle — one shape across every lane.

    Top-level fields = the cross-consumer contract. ``trace`` = lane-specific diagnostics
    (one bucket, never contract). The field set here is the pinned authority — a drift
    (producer adds/renames a field without updating the registry, or vice versa) fails the
    field-parity test in tests/scripts/test_schema_registry.py.
    """

    bundle_id: str
    query: str
    provider: str
    kb_name: str
    content_blocks: list[Any]
    sources: list[dict[str, Any]]
    exact_question: dict[str, Any]
    retrieval_plan: dict[str, Any]
    ranking_trace: dict[str, Any]
    retrieval_empty: bool
    query_shape: str = ""
    retrieval_status: str = "ok"
    retrieval_degraded: bool = False
    warning_count: int = 0
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "query": self.query,
            "provider": self.provider,
            "kb_name": self.kb_name,
            "content_blocks": list(self.content_blocks),
            "sources": list(self.sources),
            "exact_question": dict(self.exact_question),
            "retrieval_plan": dict(self.retrieval_plan),
            "ranking_trace": dict(self.ranking_trace),
            "retrieval_empty": self.retrieval_empty,
            "query_shape": self.query_shape,
            "retrieval_status": self.retrieval_status,
            "retrieval_degraded": self.retrieval_degraded,
            "warning_count": self.warning_count,
            "trace": dict(self.trace),
        }


def evidence_bundle_id(provider: str, kb_name: str, query: str) -> str:
    """Deterministic, provider-distinct bundle id.

    Unifies the three prior drifted algorithms (``kb:query:kbv5`` / ``kb:query`` / empty
    string for the fallback+historical lanes). ``bundle_id`` is observability metadata only
    (no stable-key consumer in the Python tree), so unifying it is behavior-safe; the old
    values were already inconsistent and empty for the most common lane.
    """
    return hashlib.sha256(f"{provider}:{kb_name}:{query}".encode("utf-8")).hexdigest()[:16]


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_source_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["document_id"] = _first_text(
        normalized.get("document_id"),
        normalized.get("doc_id"),
        normalized.get("source_id"),
    )
    normalized["source"] = _first_text(
        normalized.get("source"),
        normalized.get("source_path"),
        normalized.get("title"),
        normalized.get("source_id"),
    )
    normalized["authority"] = normalized.get("authority")
    if normalized["authority"] in (None, ""):
        normalized["authority"] = {}
    normalized["subject"] = _first_text(
        normalized.get("subject"),
        normalized.get("chapter_name"),
        normalized.get("chapter"),
        normalized.get("node_code"),
        normalized.get("taxonomy_path"),
        normalized.get("source_type"),
    )
    return normalized


def _normalize_source_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_source_item(item) for item in items if isinstance(item, dict)]


def build_evidence_bundle(
    *,
    query: str,
    provider: str,
    kb_name: str,
    content_blocks: list[Any],
    sources: list[dict[str, Any]],
    exact_question: dict[str, Any] | None = None,
    retrieval_plan: dict[str, Any] | None = None,
    ranking_trace: dict[str, Any] | None = None,
    query_shape: str = "",
    retrieval_warnings: list[Any] | None = None,
    retrieval_status: str | None = None,
    retrieval_empty: bool | None = None,
    trace: dict[str, Any] | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the canonical evidence bundle dict for any RAG lane (single authority).

    ``retrieval_status``/``retrieval_degraded``/``warning_count`` derive from
    ``retrieval_warnings`` by default; ``retrieval_status`` may be overridden for lanes with a
    specific status string (e.g. the historical-question ``provider_failed_…`` status).
    ``retrieval_empty`` defaults to ``not sources`` and may be overridden. Lane-specific
    diagnostics go in ``trace``.
    """
    warnings = list(retrieval_warnings or [])
    src = list(sources or [])
    degraded = bool(warnings)
    if retrieval_status is not None:
        status = str(retrieval_status)
    elif warnings:
        status = "partial"
    else:
        status = "ok"
    # Self-defending contract: a bundle carrying warnings IS degraded, so a "healthy" ``ok``
    # status is incoherent with it. Reconcile rather than emit a self-contradictory bundle
    # (guards against a future override caller passing status="ok" alongside warnings).
    if degraded and status == "ok":
        status = "partial"
    empty = (not bool(src)) if retrieval_empty is None else bool(retrieval_empty)
    return EvidenceBundle(
        bundle_id=(bundle_id if bundle_id is not None else evidence_bundle_id(provider, kb_name, query)),
        query=query,
        provider=provider,
        kb_name=kb_name,
        content_blocks=list(content_blocks or []),
        sources=_normalize_source_items(src),
        exact_question=dict(exact_question or {}),
        retrieval_plan=dict(retrieval_plan or {}),
        ranking_trace=dict(ranking_trace or {}),
        retrieval_empty=empty,
        query_shape=str(query_shape or ""),
        retrieval_status=status,
        retrieval_degraded=degraded,
        warning_count=len(warnings),
        trace=dict(trace or {}),
    ).to_dict()


__all__ = ["SCHEMA_ID", "EvidenceBundle", "build_evidence_bundle", "evidence_bundle_id"]
