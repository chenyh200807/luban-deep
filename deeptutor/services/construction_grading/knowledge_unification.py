"""Knowledge unification — pin all content sources to canonical leaves and aggregate per node.

Phase 1 of the unified Luban knowledge system: every content unit from the four sources (textbook
cards, GB/JGJ standards, lecture notes, question bank) is classified onto a CANONICAL taxonomy leaf
(see ``canonical_taxonomy``) and aggregated per node, preserving each source's AUTHORITY TIER:

  * ``textbook_verbatim``  — verbatim-signed 2026 教材 (answer-key-grade provenance)
  * ``standard_verbatim``  — GB/JGJ regulation origin_text (external mandatory-code authority)
  * ``lecture_teaching``   — 佑森 讲义 (teaching context, NOT an answer key)
  * ``question_assessment``— 题库 stems (the assessment side; never a knowledge source)

The result is a node-keyed map: for any canonical leaf you get "how the textbook states it + what the
code mandates + how the lecture explains it + how it has been tested". This module is PURE (takes the
loaded taxonomy + a flat list of ``Unit``s); the source-specific file loaders live in the runner.

This is UNIFICATION (attach + aggregate + index), not re-signing — textbook records keep their existing
verbatim signatures; standards verbatim signing is a separate follow-up lane.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

TIER_TEXTBOOK = "textbook_verbatim"
TIER_STANDARD = "standard_verbatim"
TIER_LECTURE = "lecture_teaching"
TIER_QUESTION = "question_assessment"

# which sources are knowledge (teaching/authority) vs the assessment side.
_KNOWLEDGE_SOURCES = ("textbook", "standard", "lecture")


@dataclass(frozen=True)
class Unit:
    """One content unit from a source, in a common shape ready to classify."""
    source: str            # textbook | standard | lecture | question
    unit_id: str
    native_code: str       # the source's own node_code (may be from a different code system, or "")
    authority_tier: str
    text: str
    provenance: dict[str, Any] = field(default_factory=dict)


def _empty_node() -> dict[str, list[dict[str, Any]]]:
    return {"textbook": [], "standard": [], "lecture": [], "question": []}


def unify(tax: CanonicalTaxonomy, units: list[Unit]) -> dict[str, Any]:
    """Classify every unit onto a canonical leaf and aggregate per node. Returns the unified map +
    per-source classification stats + the unclassified backlog (the LLM tail)."""
    nodes: dict[str, dict[str, list[dict[str, Any]]]] = {}
    stats: dict[str, dict[str, int]] = {}
    unclassified: list[dict[str, Any]] = []

    for u in units:
        c = tax.classify(u.text, native_code=u.native_code)
        s = stats.setdefault(u.source, {"anchor+keyword": 0, "keyword": 0, "anchor_only": 0, "unclassified": 0})
        s[c.method] = s.get(c.method, 0) + 1
        if not c.leaf_code:
            unclassified.append({"source": u.source, "unit_id": u.unit_id,
                                 "native_code": u.native_code, "text_preview": u.text[:120]})
            continue
        nodes.setdefault(c.leaf_code, _empty_node())[u.source].append({
            "unit_id": u.unit_id, "authority_tier": u.authority_tier,
            "method": c.method, "confidence": c.confidence, "keyword_hits": c.keyword_hits,
            "provenance": u.provenance, "text_preview": u.text[:160],
        })

    return {"nodes": nodes, "stats": stats, "unclassified": unclassified,
            "coverage": _coverage(tax, nodes)}


def _coverage(tax: CanonicalTaxonomy, nodes: dict[str, dict[str, list]]) -> dict[str, Any]:
    """Per-leaf coverage buckets at canonical granularity."""
    with_knowledge = {c for c, n in nodes.items() if any(n[s] for s in _KNOWLEDGE_SOURCES)}
    with_question = {c for c, n in nodes.items() if n["question"]}
    with_textbook = {c for c, n in nodes.items() if n["textbook"]}
    with_standard = {c for c, n in nodes.items() if n["standard"]}
    with_lecture = {c for c, n in nodes.items() if n["lecture"]}
    return {
        "canonical_leaves_total": len(tax.leaf_codes()),
        "leaves_populated": len(nodes),
        "leaves_with_textbook": len(with_textbook),
        "leaves_with_standard": len(with_standard),
        "leaves_with_lecture": len(with_lecture),
        "leaves_with_question": len(with_question),
        "leaves_question_with_knowledge": len(with_question & with_knowledge),
        "leaves_question_no_knowledge": sorted(with_question - with_knowledge),
        "leaves_knowledge_no_question": len(with_knowledge - with_question),
    }


def build_unified_bundle(tax: CanonicalTaxonomy, result: dict[str, Any]) -> dict[str, Any]:
    """Shape the unify() result into a node-keyed bundle with human-readable name paths + per-node
    source counts (the artifact runtime/reporting consume). Aggregation only — no signing here."""
    nodes_out: dict[str, Any] = {}
    for code, agg in result["nodes"].items():
        nodes_out[code] = {
            "name_path": tax.name_path(code),
            "counts": {s: len(agg[s]) for s in ("textbook", "standard", "lecture", "question")},
            "sources": agg,
        }
    return {"schema": "luban_canonical_unified_knowledge.v1", "nodes": nodes_out,
            "coverage": result["coverage"], "stats": result["stats"],
            "unclassified_count": len(result["unclassified"])}


__all__ = ["Unit", "unify", "build_unified_bundle",
           "TIER_TEXTBOOK", "TIER_STANDARD", "TIER_LECTURE", "TIER_QUESTION"]
