"""Canonical unified knowledge runtime — four-source teaching context for a turn (TEACHING tier).

Loads the tracked, verify-gated unified bundle (``runtime_supply/v_canonical_unified_knowledge``) and
resolves a canonical node into "how the TEXTBOOK states it + what the STANDARD mandates + how the
LECTURE explains it + how it has been TESTED" — the four sources, pinned to the one canonical spine.

Authority discipline: this is TEACHING context, never an answer key. The textbook portion references
already verbatim-signed records; standards/lectures are teaching-tier; questions are the assessment
side. ``official_score_allowed`` is structurally False — official scoring stays on the verbatim signed
textbook lane. Tamper / missing supply -> None (caller falls open).
"""
from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading import knowledge_unification as _KU

_log = logging.getLogger(__name__)

AUTHORITY = "luban_canonical_knowledge"
_SUPPLY_DIR = Path(__file__).parent / "runtime_supply" / "v_canonical_unified_knowledge"
_BUNDLE_NAME = "canonical_unified_knowledge.json"
_GRAPH_DIR = Path(__file__).parent / "runtime_supply" / "v_canonical_knowledge_graph"
_GRAPH_NAME = "graph_adjacency.json"
_DEFAULT_PER_SOURCE = 6  # cap each source to its most-relevant N for one turn


@lru_cache(maxsize=1)
def _load_graph() -> dict[str, Any] | None:
    """Load + verify the compact prerequisite/related adjacency (teaching tier). None on any problem."""
    import hashlib
    import json
    p = _GRAPH_DIR / _GRAPH_NAME
    if not p.exists():
        return None
    try:
        b = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    m = b.get("manifest") or {}
    if m.get("official_score_allowed") is not False or m.get("tier") != "teaching_context_not_answer_key":
        return None
    body = {"adjacency": b.get("adjacency"), "has_content": b.get("has_content"), "name_path": b.get("name_path")}
    if hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest() != m.get("content_hash"):
        _log.warning("knowledge-graph adjacency failed verify -> unavailable")
        return None
    return b


def _graph_neighbors(node: str) -> dict[str, list[dict[str, str]]]:
    """Content-gated, DAG-safe prerequisite/related neighbors of a node for teaching context (#6).
    Returns only has_content neighbors with their name_path; empty if graph supply unavailable."""
    g = _load_graph()
    if not g:
        return {}
    has_content = set(g.get("has_content") or [])
    name_path = g.get("name_path") or {}
    adj = (g.get("adjacency") or {}).get(node) or {}
    out: dict[str, list[dict[str, str]]] = {}
    for rel in ("prerequisite", "related"):
        items = [{"node_code": c, "name_path": name_path.get(c, c)}
                 for c in (adj.get(rel) or []) if c in has_content]
        if items:
            out[rel] = items[:8]
    return out


@lru_cache(maxsize=1)
def _load() -> dict[str, Any] | None:
    """Load + verify the tracked unified bundle once. None on any problem (caller falls open)."""
    import json
    bp = _SUPPLY_DIR / _BUNDLE_NAME
    if not bp.exists():
        return None
    try:
        bundle = json.loads(bp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not _KU.verify_unified_bundle(bundle):
        _log.warning("canonical unified bundle failed verify -> unavailable")
        return None
    return bundle


def _subtree_items(bundle: dict[str, Any], node: str, source: str) -> list[dict[str, Any]]:
    """All items of ``source`` for canonical ``node`` and its descendants (anchor or leaf)."""
    out: list[dict[str, Any]] = []
    for code, n in (bundle.get("nodes") or {}).items():
        if code == node or str(code).startswith(node + "-"):
            out.extend((n.get("sources") or {}).get(source, []))
    return out


def _focus(items: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    """Relevance-focus a source's items to the turn (reuses the deterministic lexical ranker)."""
    from deeptutor.services.construction_grading.compiled_registry_resolver import _relevance_tokens
    if limit <= 0 or len(items) <= limit:
        return items
    q = _relevance_tokens(query)
    if not q:
        return items[:limit]
    return sorted(items, key=lambda it: -len(q & _relevance_tokens(str(it.get("text_preview") or ""))))[:limit]


def available_nodes() -> list[str]:
    bundle = _load()
    return sorted((bundle.get("nodes") or {}).keys()) if bundle else []


def resolve_canonical_knowledge(
    node_code: str,
    *,
    learner_context: dict[str, Any] | None = None,
    per_source: int = _DEFAULT_PER_SOURCE,
) -> dict[str, Any] | None:
    """Resolve a canonical node into a four-source TEACHING pack (or None to fall open).

    Returns textbook + standard + lecture + question items for the node's subtree, each relevance-focused
    to the turn's question text. TEACHING tier only: ``official_score_allowed`` is always False.
    """
    node = str(node_code or "").strip()
    if not node:
        return None
    bundle = _load()
    if not bundle:
        return None
    lc = learner_context or {}
    query = " ".join(str(lc.get(k) or "") for k in
                     ("question_stem", "stem", "question_text", "question", "user_answer")).strip()
    sources: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total: dict[str, int] = {}
    for src in ("textbook", "standard", "lecture", "question"):
        items = _subtree_items(bundle, node, src)
        total[src] = len(items)
        focused = _focus(items, query, per_source)
        sources[src] = focused
        counts[src] = len(focused)
    if not any(counts.values()):
        return None
    return {
        "authority": AUTHORITY,
        "mode": "canonical_unified_knowledge_node",
        "node_code": node,
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,   # structural — official scoring stays verbatim-only
        "canonical_taxonomy_version": bundle["manifest"].get("canonical_taxonomy_version"),
        "selected_counts": counts,
        "node_source_totals": total,
        "sources": sources,
        "graph_neighbors": _graph_neighbors(node),  # #6: prerequisite/related concepts (teaching only)
        "llm_may_decide_correctness": False,
        "writeback_performed": False,
    }


__all__ = ["AUTHORITY", "available_nodes", "resolve_canonical_knowledge"]
