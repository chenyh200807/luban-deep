"""Knowledge unification — pin 4 sources to canonical leaves and aggregate (Phase 1 core).

Hermetic: tiny taxonomy + a handful of units across all four sources.
"""
from __future__ import annotations

import json

from deeptutor.services.construction_grading import knowledge_unification as KU
from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

_TREE = {"outline_structure": [
    {"code": "1A412000", "name": "材料", "level": 3, "children": [
        {"code": "1A412010", "name": "水泥", "level": 4, "children": [
            {"code": "1A412010-01", "name": "通用硅酸盐水泥", "level": 5,
             "keywords": ["硅酸盐水泥", "水泥代号"]}]}]},
    {"code": "1A413000", "name": "施工", "level": 3, "children": [
        {"code": "1A413030", "name": "地基", "level": 4, "children": [
            {"code": "1A413030-01", "name": "强夯法", "level": 5, "keywords": ["强夯", "夯锤"]}]}]},
]}


def _tax(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(_TREE, ensure_ascii=False), "utf-8")
    return CanonicalTaxonomy.load(p)


def _units():
    return [
        KU.Unit("textbook", "tb1", "1A412010", KU.TIER_TEXTBOOK, "硅酸盐水泥的水泥代号", {"chunk": "c1"}),
        KU.Unit("standard", "st1", "", KU.TIER_STANDARD, "通用硅酸盐水泥应符合规定", {"std": "GB175"}),
        KU.Unit("lecture", "lec1", "1A413030", KU.TIER_LECTURE, "强夯法夯锤质量讲解", {"topic": "地基"}),
        KU.Unit("question", "q1", "1A413030", KU.TIER_QUESTION, "强夯夯锤如何确定", {"year": 2024}),
        KU.Unit("question", "q2", "", KU.TIER_QUESTION, "完全无关外星语", {}),  # -> unclassified
    ]


def test_unify_aggregates_per_canonical_leaf(tmp_path):
    t = _tax(tmp_path)
    r = KU.unify(t, _units())
    nodes = r["nodes"]
    # 水泥 leaf gets textbook + standard; 强夯 leaf gets lecture + question
    assert nodes["1A412010-01"]["textbook"] and nodes["1A412010-01"]["standard"]
    assert nodes["1A413030-01"]["lecture"] and nodes["1A413030-01"]["question"]
    assert len(r["unclassified"]) == 1 and r["unclassified"][0]["unit_id"] == "q2"


def test_coverage_buckets(tmp_path):
    t = _tax(tmp_path)
    cov = KU.unify(t, _units())["coverage"]
    assert cov["leaves_with_textbook"] == 1
    assert cov["leaves_with_question"] == 1
    # the 强夯 leaf has a question AND lecture knowledge -> counted as covered
    assert cov["leaves_question_with_knowledge"] == 1
    assert cov["leaves_question_no_knowledge"] == []  # the unclassified question doesn't create a leaf


def test_build_unified_bundle_shape(tmp_path):
    t = _tax(tmp_path)
    r = KU.unify(t, _units())
    b = KU.build_unified_bundle(t, r)
    assert b["schema"] == "luban_canonical_unified_knowledge.v1"
    n = b["nodes"]["1A412010-01"]
    assert n["counts"]["textbook"] == 1 and n["counts"]["standard"] == 1
    assert "水泥" in n["name_path"]
    assert b["unclassified_count"] == 1
