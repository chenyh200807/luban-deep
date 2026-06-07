"""Luban knowledge graph — typed-edge assembler + topic mapping (Phase 2).

Hermetic: tiny canonical tree + hand-built edges.
"""
from __future__ import annotations

import json

from deeptutor.services.construction_grading import knowledge_graph as KG
from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

_TREE = {"outline_structure": [
    {"code": "1A412000", "name": "材料", "level": 3, "children": [
        {"code": "1A412010", "name": "水泥", "level": 4, "children": [
            {"code": "1A412010-01", "name": "硅酸盐水泥", "level": 5, "keywords": ["硅酸盐水泥"]}]}]},
    {"code": "1A413040", "name": "主体结构", "level": 4, "children": [
        {"code": "1A413040-01", "name": "混凝土结构", "level": 5, "keywords": ["混凝土结构", "主体结构"]}]},
]}


def _tax(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(_TREE, ensure_ascii=False), "utf-8")
    return CanonicalTaxonomy.load(p)


def test_map_topic_prefers_embedded_code(tmp_path):
    t = _tax(tmp_path)
    # desc carries an explicit code -> mapped to its canonical anchor
    assert KG.map_topic_to_canonical(t, "建筑工程材料", "需基于材料特性（1A412010）") == "1A412010"
    # no code -> classify by keyword
    assert KG.map_topic_to_canonical(t, "混凝土结构主体", "") == "1A413040-01"
    # nothing resolves
    assert KG.map_topic_to_canonical(t, "外星语", "") == ""


def test_normalize_relation():
    assert KG.normalize_relation("Prerequisite") == "prerequisite"
    assert KG.normalize_relation("preceding") == "preceding"
    assert KG.normalize_relation("weird-thing") == "related"  # unknown -> related


def test_hierarchy_edges(tmp_path):
    t = _tax(tmp_path)
    nodes = {"1A412010", "1A412010-01", "1A413040", "1A413040-01"}
    es = KG.hierarchy_edges(t, nodes)
    pairs = {(e["src"], e["dst"]) for e in es}
    assert ("1A412010", "1A412010-01") in pairs
    assert ("1A413040", "1A413040-01") in pairs
    assert all(e["type"] == KG.REL_HIERARCHY for e in es)


def test_assemble_dedups_and_drops_invalid():
    nodes = {"a": {}, "b": {}}
    edges = [
        {"src": "a", "dst": "b", "type": "prerequisite", "provenance": "lec1", "confidence": 0.6},
        {"src": "a", "dst": "b", "type": "prerequisite", "provenance": "lec2", "confidence": 0.9},  # dup -> merge prov + max conf
        {"src": "a", "dst": "a", "type": "related"},                              # self-loop -> drop
        {"src": "a", "dst": "zzz", "type": "related"},                            # dangling -> drop
    ]
    g = KG.assemble_graph(nodes, edges)
    assert g["stats"]["edge_count"] == 1
    assert g["stats"]["edges_dropped"] == 2
    assert g["edges"][0]["provenance"] == ["lec1", "lec2"]  # provenance merged
    assert g["edges"][0]["confidence"] == 0.9  # strongest confidence kept
    assert g["stats"]["edges_by_type"] == {"prerequisite": 1}


def test_node_uuid_idempotent_and_disambiguating():
    from deeptutor.services.construction_grading.canonical_taxonomy import node_uuid
    # same path -> same uuid (idempotent across recompiles); different path -> different (disambiguated)
    assert node_uuid("A > B > 水泥") == node_uuid("A > B > 水泥")
    assert node_uuid("A > B > 水泥") != node_uuid("X > Y > 水泥")  # same leaf name, different branch
    assert node_uuid("A > B > 水泥").startswith("n_")


def test_prune_related_drops_siblings_and_merges_symmetric():
    edges = [
        {"src": "1A413061-01-a", "dst": "1A413061-01-b", "type": "related"},   # same parent -> drop
        {"src": "1A411011-01", "dst": "1A413030-02", "type": "related", "provenance": ["x"]},  # cross
        {"src": "1A413030-02", "dst": "1A411011-01", "type": "related", "provenance": ["y"]},  # reverse dup
        {"src": "1A411011", "dst": "1A411012", "type": "hierarchy"},            # untouched
    ]
    r = KG.prune_related(edges)
    rel = [e for e in r["edges"] if e["type"] == "related"]
    assert r["dropped_sibling"] == 1
    assert len(rel) == 1 and r["merged_symmetric"] == 1
    assert rel[0]["cross_chapter"] is True
    assert set(rel[0]["provenance"]) == {"x", "y"}  # symmetric provenance merged
    assert any(e["type"] == "hierarchy" for e in r["edges"])  # non-related passthrough


def test_enforce_prerequisite_dag_breaks_cycles_and_conflicts():
    edges = [
        {"src": "a", "dst": "b", "type": "prerequisite", "confidence": 0.6, "provenance": ["llm_semantic"]},
        {"src": "b", "dst": "a", "type": "prerequisite", "confidence": 0.9, "provenance": ["llm_semantic"]},  # mutual -> keep higher conf (b->a)
        {"src": "x-01", "dst": "x", "type": "prerequisite", "confidence": 0.8},  # points at ancestor -> drop
        {"src": "p", "dst": "q", "type": "prerequisite", "confidence": 0.7},
        {"src": "q", "dst": "p", "type": "prerequisite", "confidence": 0.7, "provenance": ["lecture:1"]},  # lecture wins
    ]
    r = KG.enforce_prerequisite_dag(edges)
    assert r["is_dag"] is True
    pre = [(e["src"], e["dst"]) for e in r["edges"] if e["type"] == "prerequisite"]
    assert ("b", "a") in pre and ("a", "b") not in pre   # higher confidence direction kept
    assert ("q", "p") in pre and ("p", "q") not in pre   # lecture-authored kept
    assert ("x-01", "x") not in pre                       # ancestor-pointing dropped
