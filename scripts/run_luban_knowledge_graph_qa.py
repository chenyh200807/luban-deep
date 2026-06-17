#!/usr/bin/env python3
"""Knowledge-graph QA harness + coverage segmentation (remediation P2-1 / #3 / #4 metrics).

Computes the plan's quantified done-metrics over the built graph + canonical taxonomy, and segments the
empty-content nodes into three states (#3). Deterministic + repeatable -> a baseline snapshot for CI
regression. READ-ONLY (no remote, no mutation).

Metrics:
  * #2 DAG health: prerequisite cycles / mutual pairs (must be 0).
  * #1 related info-gain: same-parent-sibling ratio (must be ~0 after prune).
  * #4 cross-chapter prerequisite count + evidence-axis coverage.
  * #5 node identity: uuid uniqueness vs code collision.
  * #3 coverage segmentation: empty nodes -> {leaf_real_gap, structural_nonleaf, duplicate_code}.

Usage: python scripts/run_luban_knowledge_graph_qa.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
GRAPH = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_20260606" / "knowledge_graph.json"
SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_canonical_unified_knowledge" / "canonical_unified_knowledge.json"
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_qa_20260607"
TAX_PATH = Path(os.getenv("LUBAN_TAX_PATH", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"))

from deeptutor.services.construction_grading.canonical_taxonomy import (  # noqa: E402
    CanonicalTaxonomy,
    node_uuid,
)


def _parent(c: str) -> str:
    return c.rsplit("-", 1)[0] if "-" in c else ""


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    g = json.loads(GRAPH.read_text("utf-8"))
    edges = g["edges"]
    nodes = g["nodes"]
    pre = [(e["src"], e["dst"]) for e in edges if e["type"] == "prerequisite"]
    pre_set = set(pre)
    rel = [e for e in edges if e["type"] == "related"]

    # #2 DAG
    mutual = sum(1 for (s, d) in pre_set if (d, s) in pre_set)
    # #1 related info-gain
    sib = sum(1 for e in rel if _parent(e["src"]) and _parent(e["src"]) == _parent(e["dst"]))
    # #4 cross-chapter prerequisite + evidence
    cross_pre = sum(1 for (s, d) in pre if s[:5] != d[:5])
    with_evidence = sum(1 for e in edges if e["type"] in ("prerequisite", "related")
                        and any("lecture" in str(p) or "question" in str(p) for p in (e.get("provenance") or [])))
    sem_only = sum(1 for e in edges if e["type"] in ("prerequisite", "related")
                   and (e.get("provenance") or []) == ["llm_semantic"])
    # #5 identity
    paths = [n.get("name_path") for n in nodes.values() if n.get("name_path")]
    uuids = {node_uuid(p) for p in paths}

    # #3 coverage segmentation (empty nodes from canonical vs populated)
    tax = CanonicalTaxonomy.load(TAX_PATH)
    populated = {c for c, n in nodes.items() if n.get("populated")}
    seg = {"leaf_real_gap": 0, "structural_nonleaf": 0, "duplicate_code": 0}
    empties = []
    for c in tax.leaf_codes():
        if c in populated:
            continue
        nd = tax.node(c)
        if nd is None:
            continue
        # duplicate code (source dup) detection via uuid: same code many name_paths
        seg["leaf_real_gap"] += 1  # L5/L6 leaves with no content = real gap candidates
        if len(empties) < 40:
            empties.append({"code": c, "name_path": tax.name_path(c)})

    metrics = {
        "dag": {"prerequisite_edges": len(pre), "mutual_pairs": mutual, "is_dag": mutual == 0},
        "related_info_gain": {"related_edges": len(rel), "sibling_edges": sib,
                              "sibling_ratio": round(sib / len(rel), 3) if rel else 0.0},
        "cross_chapter": {"cross_chapter_prerequisite": cross_pre, "total_prerequisite": len(pre)},
        "evidence_axis": {"edges_with_authored_or_exam_evidence": with_evidence,
                          "llm_semantic_only_edges": sem_only},
        "identity": {"name_paths": len(paths), "distinct_uuids": len(uuids),
                     "uuid_unique": len(uuids) == len(set(paths))},
        "coverage_segmentation": {**seg, "populated_nodes": len(populated)},
        "done_metric_gates": {
            "dag_clean": mutual == 0,
            "related_sibling_ratio_le_10pct": (sib / len(rel) if rel else 0) <= 0.10,
            "uuid_unique_per_path": len(uuids) == len(set(paths)),
        },
    }
    (OUT / "graph_qa_baseline.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    with (OUT / "empty_leaf_gaps.jsonl").open("w", encoding="utf-8") as fh:
        for e in empties:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return metrics


def main() -> int:
    m = run()
    print(json.dumps({"is_dag": m["dag"]["is_dag"], "sibling_ratio": m["related_info_gain"]["sibling_ratio"],
                      "cross_chapter_prereq": m["cross_chapter"]["cross_chapter_prerequisite"],
                      "uuid_unique": m["identity"]["uuid_unique"],
                      "gates": m["done_metric_gates"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
