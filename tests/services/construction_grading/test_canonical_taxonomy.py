"""Canonical taxonomy loader + deterministic classifier (Luban knowledge unification spine).

Hermetic: builds a tiny L1-L6 tree in a temp file. Proves anchor-by-code + refine-by-keyword,
cross-area false-positive avoidance, and the unclassified tail.
"""
from __future__ import annotations

import json

from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

_TREE = {
    "outline_structure": [
        {"code": "1A410000", "name": "建筑工程技术", "level": 1, "children": [
            {"code": "1A412000", "name": "材料", "level": 3, "children": [
                {"code": "1A412010", "name": "水泥", "level": 4, "children": [
                    {"code": "1A412010-01", "name": "通用硅酸盐水泥", "level": 5,
                     "keywords": ["硅酸盐水泥", "普通水泥"], "children": [
                        {"code": "1A412010-01-a", "name": "水泥代号", "level": 6,
                         "keywords": ["代号", "P.O", "P.II"]}]},
                ]},
            ]},
            {"code": "1A413000", "name": "施工技术", "level": 3, "children": [
                {"code": "1A413030", "name": "地基与基础", "level": 4, "children": [
                    {"code": "1A413030-01", "name": "强夯法", "level": 5,
                     "keywords": ["强夯", "夯锤", "夯击能"]}]},
            ]},
        ]},
    ]
}


def _tax(tmp_path):
    p = tmp_path / "tax.json"
    p.write_text(json.dumps(_TREE, ensure_ascii=False), "utf-8")
    return CanonicalTaxonomy.load(p)


def test_load_and_leaves(tmp_path):
    t = _tax(tmp_path)
    leaves = set(t.leaf_codes())
    assert leaves == {"1A412010-01-a", "1A413030-01"}  # childless nodes with keywords; parents are not targets
    assert "水泥" in t.name_path("1A412010-01")


def test_anchor_plus_keyword_refines_within_subtree(tmp_path):
    t = _tax(tmp_path)
    # native code 1A412010 (L4 水泥) anchors; keyword refines to the 代号 L6 leaf
    c = t.classify("通用硅酸盐水泥的代号 P.O 表示普通", native_code="1A412010")
    assert c.leaf_code == "1A412010-01-a" and c.method == "anchor+keyword" and c.keyword_hits >= 2


def test_anchor_prevents_cross_area_false_positive(tmp_path):
    t = _tax(tmp_path)
    # text mentions 强夯 (a 施工 keyword) but the unit is anchored to the 水泥 subtree -> stays in 水泥,
    # never leaks into 1A413030-01 强夯.
    c = t.classify("水泥相关，顺带提到强夯", native_code="1A412010")
    assert c.leaf_code.startswith("1A412010")


def test_global_keyword_when_no_anchor(tmp_path):
    t = _tax(tmp_path)
    c = t.classify("强夯处理地基夯锤质量", native_code="")  # no/invalid code -> global keyword
    assert c.leaf_code == "1A413030-01" and c.method == "keyword"


def test_unclassified_tail(tmp_path):
    t = _tax(tmp_path)
    c = t.classify("完全无关的外星语内容", native_code="9Z999999")
    assert c.leaf_code == "" and c.method == "unclassified" and c.confidence == 0.0
