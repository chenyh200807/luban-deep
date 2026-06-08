"""General-knowledge compiled teaching context for M34.

This composes existing authorities only:
canonical text resolution -> canonical knowledge runtime. It never mints an
answer key, never writes learner truth, and falls open on low-signal input.
"""
from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading import canonical_resolution as _CR
from deeptutor.services.construction_grading.canonical_knowledge_runtime import (
    resolve_canonical_knowledge,
)

AUTHORITY = "luban_general_knowledge_context"


def _anchor_candidates(leaf_code: str) -> list[str]:
    """Return a leaf code followed by prefix ancestors, longest first."""
    code = str(leaf_code or "").strip()
    if not code:
        return []
    parts = code.split("-")
    return ["-".join(parts[:idx]) for idx in range(len(parts), 0, -1)]


def resolve_general_knowledge_context(
    question_text: str,
    *,
    learner_context: dict[str, Any] | None = None,
    per_source: int = 6,
) -> dict[str, Any] | None:
    """Resolve free text into a teaching-tier four-source pack, or None to fall open."""
    text = str(question_text or "").strip()
    if not text:
        return None

    leaf = _CR.to_canonical(text)
    if not leaf:
        return None

    focused_context = dict(learner_context or {})
    focused_context.setdefault("question_text", text)
    for anchor in _anchor_candidates(leaf):
        pack = resolve_canonical_knowledge(
            anchor,
            learner_context=focused_context,
            per_source=per_source,
        )
        if pack:
            return {
                "authority": AUTHORITY,
                "mode": "general_knowledge_teaching_context",
                "classified_leaf": leaf,
                "leaf_name_path": _CR.name_path(leaf),
                "resolved_anchor": anchor,
                "tier": pack.get("tier", "teaching_context_not_answer_key"),
                "official_score_allowed": False,
                "llm_may_decide_correctness": False,
                "canonical_taxonomy_version": pack.get("canonical_taxonomy_version"),
                "selected_counts": pack.get("selected_counts"),
                "sources": pack.get("sources") or {},
                "graph_neighbors": pack.get("graph_neighbors") or {},
                "remediation": pack.get("remediation"),
                "writeback_performed": False,
            }
    return None


__all__ = ["AUTHORITY", "resolve_general_knowledge_context"]
