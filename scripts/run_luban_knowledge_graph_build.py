#!/usr/bin/env python3
"""Build the Luban knowledge graph (Phase 2): typed edges over the canonical taxonomy spine.

Nodes = canonical nodes that carry content (from the unified bundle), enriched with four-source counts.
Edges (provenance-first, no LLM guessing in v1):
  * hierarchy (parent_of) from the canonical tree — the backbone,
  * authored semantic edges (prerequisite / preceding / related / ...) from 佑森 lecture
    ``related_topics`` — source = the lecture chunk's canonical node, target = the related topic mapped
    onto a canonical node.

Outputs (artifacts + a Supabase edge-table dry-run; NO remote write):
  * knowledge_graph.json — nodes + typed edges + stats (feeds kmap / syllabus_graph)
  * graph_edges_rows.jsonl + edges_schema.sql — canonical-keyed edge rows for the Supabase graph layer.

Usage:
  python scripts/run_luban_knowledge_graph_build.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import sys
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_20260606"
SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_canonical_unified_knowledge" / "canonical_unified_knowledge.json"
# optional LLM-mined semantic edges (prerequisite/related) to merge on top of authored edges.
SEMANTIC_EDGES = Path(os.getenv("LUBAN_SEMANTIC_EDGES",
                                str(_REPO / "tmp" / "unify_workflow" / "semantic_edges.json")))
# expert-curated cross-chapter prerequisite seed (remediation #4), versioned with the code.
CURRICULUM_SEED = _REPO / "deeptutor" / "services" / "construction_grading" / "curriculum_prerequisites.json"
DATA = Path(os.getenv("LUBAN_DATA_DIR", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026"))
TAX_PATH = Path(os.getenv("LUBAN_TAX_PATH", str(DATA / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json")))

from deeptutor.services.construction_grading import knowledge_graph as KG  # noqa: E402
from deeptutor.services.construction_grading.canonical_taxonomy import (
    CanonicalTaxonomy,  # noqa: E402
)


def _ancestors(tax: CanonicalTaxonomy, code: str) -> list[str]:
    """Walk up the canonical code chain (L6 -> L5 -> L4 ...) for hierarchy connectivity."""
    out, cur = [], code
    while "-" in cur:
        cur = cur.rsplit("-", 1)[0]
        if tax.node(cur) is not None:
            out.append(cur)
    return out


def _lecture_edges(tax: CanonicalTaxonomy) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for topic_dir in sorted(glob.glob(str(DATA / "讲义" / "*"))):
        if not Path(topic_dir).is_dir():
            continue
        for f in [x for x in glob.glob(topic_dir + "/*.json") if "/page_" not in x]:
            try:
                d = json.loads(Path(f).read_text("utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"WARN: skipping unreadable lecture {f}: {type(exc).__name__}", file=sys.stderr)
                continue
            for ch in (d if isinstance(d, list) else []):
                if not isinstance(ch, dict):
                    continue
                tax_node = str((ch.get("taxonomy") or {}).get("node_code") or "")
                src = tax.classify(str(ch.get("content_markdown") or ""), native_code=tax_node).leaf_code
                if not src:
                    continue
                for rt in ch.get("related_topics") or []:
                    if not isinstance(rt, dict):
                        continue
                    dst = KG.map_topic_to_canonical(tax, str(rt.get("topic") or ""), str(rt.get("desc") or ""))
                    if not dst:
                        continue
                    edges.append({
                        "src": src, "dst": dst,
                        "type": KG.normalize_relation(str(rt.get("relation_type") or "")),
                        "relation_detail": str(rt.get("desc") or "")[:120],
                        "provenance": f"lecture:{ch.get('chunk_id')}",
                    })
    return edges


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    tax = CanonicalTaxonomy.load(TAX_PATH)
    bundle = json.loads(SUPPLY.read_text("utf-8"))

    # nodes = populated canonical nodes + their ancestors (backbone connectivity)
    populated = dict(bundle.get("nodes") or {})
    node_codes: set[str] = set(populated)
    for code in list(populated):
        node_codes.update(_ancestors(tax, code))
    nodes: dict[str, dict[str, Any]] = {}
    for code in node_codes:
        n = populated.get(code) or {}
        nodes[code] = {
            "name_path": n.get("name_path") or tax.name_path(code),
            "counts": n.get("counts") or {"textbook": 0, "standard": 0, "lecture": 0, "question": 0},
            "level": (tax.node(code).level if tax.node(code) else None),
            "populated": code in populated,
        }

    lec_edges = _lecture_edges(tax)
    # expert-curated cross-chapter prerequisite seed (#4): high-precision, finite, DAG-by-construction.
    seed_edges: list[dict[str, Any]] = []
    if CURRICULUM_SEED.exists():
        for e in json.loads(CURRICULUM_SEED.read_text("utf-8")).get("edges", []):
            if tax.node(e.get("src")) is not None and tax.node(e.get("dst")) is not None:
                seed_edges.append({"src": e["src"], "dst": e["dst"], "type": "prerequisite",
                                   "relation_detail": str(e.get("note") or "")[:120],
                                   "confidence": 0.95, "provenance": "curriculum_seed"})
    # LLM-mined semantic edges (optional): tag provenance so they're distinguishable from authored ones.
    sem_edges: list[dict[str, Any]] = []
    if SEMANTIC_EDGES.exists():
        for e in json.loads(SEMANTIC_EDGES.read_text("utf-8")):
            sem_edges.append({"src": str(e.get("src") or ""), "dst": str(e.get("dst") or ""),
                              "type": KG.normalize_relation(str(e.get("type") or "")),
                              "relation_detail": str(e.get("reason") or "")[:120],
                              "confidence": e.get("confidence"), "provenance": "llm_semantic"})
    # edge endpoints must be nodes too (else assemble drops them)
    for e in lec_edges + sem_edges + seed_edges:
        for code in (e["src"], e["dst"]):
            if code not in nodes and tax.node(code) is not None:
                nodes[code] = {"name_path": tax.name_path(code),
                               "counts": {"textbook": 0, "standard": 0, "lecture": 0, "question": 0},
                               "level": tax.node(code).level, "populated": False}
    edges = KG.hierarchy_edges(tax, set(nodes)) + lec_edges + sem_edges + seed_edges
    graph = KG.assemble_graph(nodes, edges)

    # CLEANING PASS (remediation #1 + #2): drop tautological same-parent related + symmetric-dedup;
    # enforce prerequisite DAG (resolve mutual conflicts + break cycles). Deterministic.
    pruned = KG.prune_related(graph["edges"])
    dag = KG.enforce_prerequisite_dag(pruned["edges"])
    clean_edges = dag["edges"]
    # stamp each node with a stable content-derived uuid (#5: identity decoupled from non-unique code)
    from deeptutor.services.construction_grading.canonical_taxonomy import node_uuid
    for code, n in graph["nodes"].items():
        n["uuid"] = node_uuid(n.get("name_path") or code)
    graph["edges"] = clean_edges
    graph["stats"] = KG.graph_stats(graph["nodes"], clean_edges)
    graph["stats"]["cleaning"] = {
        "related_siblings_dropped": pruned["dropped_sibling"],
        "related_symmetric_merged": pruned["merged_symmetric"],
        "prerequisite_removed": dag["prerequisite_removed"],
        "prerequisite_is_dag": dag["is_dag"],
    }

    (OUT / "knowledge_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "prerequisite_dag_removed.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in dag["removed"]), "utf-8")
    _emit_supabase_edges(graph)
    _persist_runtime_adjacency(graph)
    return {"nodes": graph["stats"]["node_count"], "edges": graph["stats"]["edge_count"],
            "edges_by_type": graph["stats"]["edges_by_type"],
            "lecture_authored_edges": len(lec_edges), "llm_semantic_edges": len(sem_edges),
            "curriculum_seed_edges": len(seed_edges),
            "cleaning": graph["stats"]["cleaning"],
            "prerequisite_mutual_pairs": graph["stats"]["prerequisite_mutual_pairs"],
            "isolated_nodes": graph["stats"]["isolated_nodes"]}


_EDGES_SCHEMA = """\
create table if not exists luban_canonical_knowledge_edges (
  src text not null,
  dst text not null,
  type text not null,
  relation_detail text,
  provenance jsonb,
  primary key (src, dst, type)
);
create index if not exists idx_lkge_src on luban_canonical_knowledge_edges (src);
create index if not exists idx_lkge_dst on luban_canonical_knowledge_edges (dst);
"""


_ADJ_SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_canonical_knowledge_graph"


def _persist_runtime_adjacency(graph: dict[str, Any]) -> None:
    """Persist a compact, verify-gated prerequisite/related adjacency the tutor can consume (#6).
    TEACHING tier (official_score_allowed False); content node flags carried so the runtime can gate to
    has_content nodes. content_hash for tamper detection — never an answer-key authority."""
    import hashlib
    adjacency: dict[str, dict[str, list[str]]] = {}
    for e in graph["edges"]:
        if e["type"] not in ("prerequisite", "related"):
            continue
        adjacency.setdefault(e["src"], {}).setdefault(e["type"], []).append(e["dst"])
        if e["type"] == "related":  # related is undirected -> both directions
            adjacency.setdefault(e["dst"], {}).setdefault("related", []).append(e["src"])
    has_content = {c for c, n in graph["nodes"].items() if (n.get("counts") or {}) and
                   sum((n.get("counts") or {}).values()) > 0}
    name_path = {c: n.get("name_path") for c, n in graph["nodes"].items()}
    body = {"adjacency": {k: {t: sorted(set(v)) for t, v in d.items()} for k, d in adjacency.items()},
            "has_content": sorted(has_content), "name_path": name_path}
    content_hash = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    bundle = {"manifest": {"namespace": "canonical_knowledge_graph", "status": "release_candidate",
                           "published": False, "tier": "teaching_context_not_answer_key",
                           "official_score_allowed": False, "content_hash": content_hash,
                           "node_count": len(name_path), "edge_nodes": len(adjacency)}, **body}
    _ADJ_SUPPLY.mkdir(parents=True, exist_ok=True)
    (_ADJ_SUPPLY / "graph_adjacency.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")


def _emit_supabase_edges(graph: dict[str, Any]) -> None:
    with (OUT / "graph_edges_rows.jsonl").open("w", encoding="utf-8") as fh:
        for e in graph["edges"]:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (OUT / "edges_schema.sql").write_text(_EDGES_SCHEMA, "utf-8")


def main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
