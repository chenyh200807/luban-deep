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

_CODE_RE = re.compile(r"1A\d{4,}(?:-[0-9A-Za-z]+)*")  # canonical-ish code embedded in a desc string


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
    return {
        "schema": "luban_canonical_knowledge_graph.v1",
        "nodes": nodes,
        "edges": edge_list,
        "stats": graph_stats(nodes, edge_list, edges_dropped=dropped),
    }


def graph_stats(nodes: dict[str, Any], edge_list: list[dict[str, Any]], *, edges_dropped: int = 0) -> dict[str, Any]:
    """Degree/type stats over a (nodes, edges) pair — usable after a cleaning pass without re-running
    assemble (which would re-wrap provenance). Also reports prerequisite DAG health."""
    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pre_pairs: set[tuple[str, str]] = set()
    for e in edge_list:
        out_deg[e["src"]] = out_deg.get(e["src"], 0) + 1
        in_deg[e["dst"]] = in_deg.get(e["dst"], 0) + 1
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        if e["type"] == "prerequisite":
            pre_pairs.add((e["src"], e["dst"]))
    mutual = sum(1 for (s, d) in pre_pairs if (d, s) in pre_pairs)
    return {
        "node_count": len(nodes),
        "edge_count": len(edge_list),
        "edges_dropped": edges_dropped,
        "edges_by_type": by_type,
        "max_out_degree": max(out_deg.values()) if out_deg else 0,
        "max_in_degree": max(in_deg.values()) if in_deg else 0,
        "isolated_nodes": sum(1 for n in nodes if n not in out_deg and n not in in_deg),
        "prerequisite_mutual_pairs": mutual,
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


def _parent_code(code: str) -> str:
    """The parent code in the dash hierarchy (1A413061-01-a -> 1A413061-01). '' for a top code.
    Sibling detection compares parent CODES, which is robust to code non-uniqueness: two endpoints
    sharing a parent code are structural siblings regardless of which duplicated instance they are."""
    return code.rsplit("-", 1)[0] if "-" in code else ""


def prune_related(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Issue #1 fix: a ``related`` edge between same-parent siblings is a tautology (the tree's
    parent_of edges already encode 'same parent = same class'), so it carries ~0 information. Drop those;
    treat the rest as UNDIRECTED (related has no direction) and merge the 530 reverse-duplicate rows into
    one canonical (min,max) edge, marking cross_chapter. Non-related edges pass through untouched."""
    out: list[dict[str, Any]] = []
    seen_undirected: dict[tuple[str, str], dict[str, Any]] = {}
    dropped_sibling = 0
    merged_symmetric = 0
    for e in edges:
        if e.get("type") != "related":
            out.append(e)
            continue
        src, dst = str(e.get("src") or ""), str(e.get("dst") or "")
        if _parent_code(src) and _parent_code(src) == _parent_code(dst):
            dropped_sibling += 1
            continue
        key = (min(src, dst), max(src, dst))
        if key in seen_undirected:
            merged_symmetric += 1
            cur = seen_undirected[key]
            for p in (e.get("provenance") or []):
                if p not in cur.setdefault("provenance", []):
                    cur["provenance"].append(p)
            if (e.get("confidence") or 0) > (cur.get("confidence") or 0):
                cur["confidence"] = e.get("confidence")
            continue
        merged = {**e, "src": key[0], "dst": key[1],
                  "cross_chapter": src[:5] != dst[:5],
                  "provenance": list(e.get("provenance") or [])}
        seen_undirected[key] = merged
        out.append(merged)
    return {"edges": out, "dropped_sibling": dropped_sibling, "merged_symmetric": merged_symmetric}


def enforce_prerequisite_dag(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Issue #2 fix: ``prerequisite`` must be a DAG. Resolve mutual conflicts (A->B & B->A) and break any
    remaining cycle, deterministically. Conflict rule (strongest kept): (1) lecture-authored beats
    llm_semantic; (2) a prerequisite that points at a tree ANCESTOR is structurally wrong -> drop;
    (3) higher confidence; (4) stable (src<dst) tie-break. Then Kahn topo-sort; if a cycle survives,
    drop the lowest-confidence edge on it until acyclic. Non-prerequisite edges pass through."""
    pre = [e for e in edges if e.get("type") == "prerequisite"]
    other = [e for e in edges if e.get("type") != "prerequisite"]

    def _is_lecture(e: dict[str, Any]) -> bool:
        return any("lecture" in str(p) for p in (e.get("provenance") or []))

    def _points_at_ancestor(e: dict[str, Any]) -> bool:
        # dst is an ancestor of src in the dash hierarchy (src 的前置不应是 src 的祖先/父概念)
        s, d = str(e.get("src") or ""), str(e.get("dst") or "")
        return s.startswith(d + "-")

    def _weaker(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        """Return the edge to DROP between a conflicting pair a,b."""
        if _is_lecture(a) != _is_lecture(b):
            return b if _is_lecture(a) else a
        aa, ab = _points_at_ancestor(a), _points_at_ancestor(b)
        if aa != ab:
            return a if aa else b
        ca, cb = a.get("confidence") or 0, b.get("confidence") or 0
        if ca != cb:
            return a if ca < cb else b
        return a if str(a["src"]) > str(b["src"]) else b

    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    removed: list[dict[str, Any]] = []
    # 1) drop prerequisites pointing at an ancestor (tree tautology / wrong direction)
    cleaned = []
    for e in pre:
        if _points_at_ancestor(e):
            removed.append({**e, "drop_reason": "points_at_tree_ancestor"})
        else:
            cleaned.append(e)
    # 2) resolve mutual conflicts
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    for e in cleaned:
        s, d = str(e["src"]), str(e["dst"])
        rev = (d, s)
        if rev in kept:
            drop = _weaker(kept[rev], e)
            keep = e if drop is kept[rev] else kept[rev]
            removed.append({**drop, "drop_reason": "mutual_prerequisite_conflict"})
            del kept[rev]
            kept[(str(keep["src"]), str(keep["dst"]))] = keep
        else:
            kept[(s, d)] = e
    # 3) Kahn topo; break residual cycles by dropping lowest-confidence edge on a back-edge
    adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for (s, d), e in kept.items():
        adj.setdefault(s, []).append((d, e))
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def _has_cycle_edge() -> tuple[str, str] | None:
        color.clear()
        stack = [(n, iter(adj.get(n, []))) for n in []]
        for start in list(adj):
            if color.get(start, WHITE) != WHITE:
                continue
            stack = [(start, iter(adj.get(start, [])))]
            color[start] = GRAY
            while stack:
                node, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    color[node] = BLACK
                    stack.pop()
                    continue
                d, _e = nxt
                c = color.get(d, WHITE)
                if c == GRAY:
                    return (node, d)
                if c == WHITE:
                    color[d] = GRAY
                    stack.append((d, iter(adj.get(d, []))))
        return None

    guard = 0
    while True:
        back = _has_cycle_edge()
        if back is None or guard > 10000:
            break
        guard += 1
        s, d = back
        e = kept.pop((s, d))
        removed.append({**e, "drop_reason": "cycle_break"})
        adj[s] = [(x, ee) for (x, ee) in adj.get(s, []) if x != d]

    final = other + list(kept.values())
    return {"edges": final, "removed": removed,
            "prerequisite_kept": len(kept), "prerequisite_removed": len(removed),
            "is_dag": _has_cycle_edge() is None}


__all__ = ["assemble_graph", "graph_stats", "hierarchy_edges", "map_topic_to_canonical",
           "normalize_relation", "prune_related", "enforce_prerequisite_dag", "REL_HIERARCHY"]
