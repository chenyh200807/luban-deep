from __future__ import annotations

import json

from scripts.run_luban_taxonomy_dedup_rehome_candidate import (
    build_taxonomy_dedup_rehome_candidate,
)


def _taxonomy() -> dict:
    return {
        "meta": {"version": "V25.0 SLIM"},
        "stats": {},
        "outline_structure": [
            {
                "code": "1A413060",
                "name": "装饰装修工程施工",
                "level": 3,
                "children": [
                    {
                        "code": "1A413061",
                        "name": "轻质隔墙工程施工",
                        "level": 4,
                        "children": [
                            # Rule A: identical siblings to merge
                            {"code": "1A413061-01", "name": "轻质隔墙施工要点", "keywords": ["甲"], "children": []},
                            {"code": "1A413061-01", "name": "轻质隔墙施工要点", "keywords": ["乙"], "children": []},
                            # Rule B: same code, different name
                            {"code": "1A413061-01", "name": "完全不同的叶子", "children": []},
                            # Rule C: misplaced subtrees
                            {
                                "code": "1A413061-04",
                                "name": "劳务分包管理流程",
                                "children": [{"code": "1A413061-04-b", "name": "资格预审内容", "children": []}],
                            },
                            {"code": "1A413061-08", "name": "节能与能源利用要点", "children": []},
                            {
                                "code": "1A413061-07",
                                "name": "绿色施工信息化系统应用",
                                "children": [{"code": "1A413061-07-d", "name": "项目管理信息系统子系统", "children": []}],
                            },
                        ],
                    },
                ],
            },
            {
                "code": "1A438000",
                "name": "施工资源管理",
                "level": 2,
                "children": [
                    {"code": "1A438030", "name": "劳动用工管理", "children": []},
                ],
            },
            {
                "code": "1A437000",
                "name": "绿色建造及施工现场环境管理",
                "level": 2,
                "children": [
                    {"code": "1A437010", "name": "绿色建造及信息化技术应用管理", "children": []},
                    {"code": "1A437020", "name": "绿色施工及环境保护", "children": []},
                ],
            },
        ],
    }


def test_dedup_rehome_full_pipeline() -> None:
    report = build_taxonomy_dedup_rehome_candidate(taxonomy=_taxonomy())
    assert report["verdict"] == "PASS_TAXONOMY_DEDUP_REHOME_CANDIDATE"

    # Rule A: identical siblings merged, keywords unioned
    assert report["summary"]["merged_identical_sibling_count"] == 1
    candidate = report["candidate_taxonomy"]
    roots = candidate["outline_structure"]
    qiang = roots[0]["children"][0]
    same_named = [c for c in qiang["children"] if c["name"] == "轻质隔墙施工要点"]
    assert len(same_named) == 1
    assert sorted(same_named[0]["keywords"]) == ["乙", "甲"]

    # Rule C: three subtrees moved to their semantic parents
    moves = {m["name"]: m for m in report["rehomed_subtrees"]}
    assert moves["劳务分包管理流程"]["new_parent"] == "1A438030"
    assert moves["节能与能源利用要点"]["new_parent"] == "1A437020"
    assert moves["绿色施工信息化系统应用"]["new_parent"] == "1A437010"
    labour_parent = next(n for n in roots if n["code"] == "1A438000")["children"][0]
    assert any(c["name"] == "劳务分包管理流程" for c in labour_parent["children"])
    # moved nodes are no longer under 1A413061
    assert not any(c["name"] == "劳务分包管理流程" for c in qiang["children"])

    # Rule B: collision recoded with stable suffix
    recoded = {r["name"]: r for r in report["recoded_collisions"]}
    assert "完全不同的叶子" in recoded
    assert recoded["完全不同的叶子"]["old_code"] == "1A413061-01"
    assert recoded["完全不同的叶子"]["new_code"].startswith("1A413061-01x")

    # remap table covers both recodes and rehomes
    kinds = {e["kind"] for e in report["remap_table"]}
    assert kinds == {"recode", "rehome"}

    # no duplicate (code,different name) remains
    seen: dict[str, str] = {}
    def walk(node):
        code, name = node.get("code"), node.get("name")
        if code:
            assert seen.setdefault(code, name) == name, f"collision survived: {code}"
        for ch in node.get("children") or []:
            walk(ch)
    for r in roots:
        walk(r)


def test_dedup_rehome_preserves_canonical_input_and_safety() -> None:
    taxonomy = _taxonomy()
    snapshot = json.dumps(taxonomy, ensure_ascii=False, sort_keys=True)
    report = build_taxonomy_dedup_rehome_candidate(taxonomy=taxonomy)
    assert json.dumps(taxonomy, ensure_ascii=False, sort_keys=True) == snapshot
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "canonical_taxonomy_overwrite" in report["not_exercised"]
    assert report["candidate_taxonomy"]["meta"]["candidate_only"] is True
