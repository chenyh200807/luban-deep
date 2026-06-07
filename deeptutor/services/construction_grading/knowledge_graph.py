"""Luban knowledge graph — typed edges over the canonical taxonomy spine (Phase 2).

The canonical taxonomy gives NODES (a tree); this module adds typed EDGES to make it a graph the tutor
and the kmap / syllabus_graph prototypes can traverse. Edge sources, provenance-first (no LLM guessing
in v1 — every edge traces to authored data):

  * ``hierarchy``  — parent_of / child_of, from the canonical tree itself (the backbone).
  * authored semantic edges from 佑森 lecture ``related_topics`` — each carries a ``relation_type``
    (prerequisite / preceding / related / ...) authored by the lecturer; the source is the lecture
    chunk's canonical node, the target is the related topic mapped onto a canonical node.

Pure assembler: ``assemble_graph`` dedups edges, drops self-loops and edges to unknown nodes, and
computes degree stats. Edge EXTRACTION (reading lectures, mapping topics) lives in the runner; the
mapping helper ``map_topic_to_canonical`` is here so it is unit-testable.
"""
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

REL_HIERARCHY = "hierarchy"          # parent_of (structural backbone)
# authored relation types carried verbatim from lecture related_topics (normalized to lowercase)
_KNOWN_RELS = {"prerequisite", "preceding", "related", "co_occurring", "part_of", "applies_to"}

_CODE_RE = re.compile(r"1A\d{4,}(?:-[0-9a-z]+)*")  # canonical-ish code embedded in a desc string


def map_topic_to_canonical(tax: CanonicalTaxonomy, topic: str, desc: str = "") -> str:
    """Map a lecture related-topic to a canonical node. Prefer an explicit code in ``desc`` (the
    lecturer often writes e.g. '材料特性（1A412000）'); else classify the topic text by keywords. Returns
    a canonical code (the embedded code's anchor if it maps into the tree) or '' if nothing resolves."""
    # a desc may carry several codes ("基于材料（1A412000）和构造（1A411011）"); prefer the most specific
    # (deepest-level) node that resolves, not just the first written.
    best_code, best_level = "", -1
    for m in _CODE_RE.findall(desc or ""):
        for cand in (m, m.split("-", 1)[0]):
            node = tax.node(cand)
            if node is not None and node.level > best_level:
                best_code, best_level = cand, node.level
    if best_code:
        return best_code
    c = tax.classify(str(topic or ""), native_code="")
    return c.leaf_code


def normalize_relation(rel: str) -> str:
    r = str(rel or "").strip().lower().replace("-", "_").replace(" ", "_")
    return r if r in _KNOWN_RELS else "related"


def assemble_graph(canonical_nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble nodes + typed edges into a graph. Dedups edges by (src,dst,type), drops self-loops and
    edges whose endpoints are not known nodes, and computes degree stats. Provenance is preserved
    (merged into a list per deduped edge)."""
    nodes = dict(canonical_nodes)
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    dropped = 0
    for e in edges:
        src, dst, rel = str(e.get("src") or ""), str(e.get("dst") or ""), str(e.get("type") or "")
        if not src or not dst or src == dst or src not in nodes or dst not in nodes:
            dropped += 1
            continue
        key = (src, dst, rel)
        conf = e.get("confidence")
        if key in seen:
            prov = e.get("provenance")
            if prov and prov not in seen[key]["provenance"]:
                seen[key]["provenance"].append(prov)
            if conf is not None and (seen[key].get("confidence") is None or conf > seen[key]["confidence"]):
                seen[key]["confidence"] = conf  # corroborated -> keep the strongest confidence
            continue
        seen[key] = {"src": src, "dst": dst, "type": rel,
                     "relation_detail": e.get("relation_detail"),
                     "confidence": conf,
                     "provenance": [e["provenance"]] if e.get("provenance") else []}
    edge_list = sorted(seen.values(), key=lambda x: (x["src"], x["dst"], x["type"]))

    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    for e in edge_list:
        out_deg[e["src"]] = out_deg.get(e["src"], 0) + 1
        in_deg[e["dst"]] = in_deg.get(e["dst"], 0) + 1
    by_type: dict[str, int] = {}
    for e in edge_list:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    return {
        "schema": "luban_canonical_knowledge_graph.v1",
        "nodes": nodes,
        "edges": edge_list,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edge_list),
            "edges_dropped": dropped,
            "edges_by_type": by_type,
            "max_out_degree": max(out_deg.values()) if out_deg else 0,
            "max_in_degree": max(in_deg.values()) if in_deg else 0,
            "isolated_nodes": sum(1 for n in nodes if n not in out_deg and n not in in_deg),
        },
    }


def hierarchy_edges(tax: CanonicalTaxonomy, node_codes: set[str]) -> list[dict[str, Any]]:
    """parent_of edges between known nodes from the canonical tree (the structural backbone)."""
    edges: list[dict[str, Any]] = []
    for code in node_codes:
        node = tax.node(code)
        if node is None:
            continue
        for child in tax._children.get(code, []):  # noqa: SLF001 — same package, intentional
            if child in node_codes:
                edges.append({"src": code, "dst": child, "type": REL_HIERARCHY,
                              "relation_detail": "parent_of", "provenance": "canonical_taxonomy"})
    return edges


__all__ = ["assemble_graph", "hierarchy_edges", "map_topic_to_canonical", "normalize_relation",
           "REL_HIERARCHY"]
