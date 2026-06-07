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
