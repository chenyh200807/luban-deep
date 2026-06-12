from __future__ import annotations

import json

from scripts.run_luban_taxonomy_skeleton_repair import build_taxonomy_skeleton_repair


def _taxonomy() -> dict:
    return {
        "meta": {"version": "book_derived"},
        "outline_structure": [
            {
                "code": "1A410000",
                "name": "建筑工程技术",
                "level": 1,
                "children": [
                    {
                        "code": "1A412010",
                        "name": "结构工程材料",
                        "level": 3,
                        "children": [
                            {"code": "1A412010-B001", "name": "石材", "level": 5, "source_evidence": [{"chunk_id": "c1"}], "children": []},
                        ],
                    },
                ],
            },
            # 平行重复分支（无叶子的世代拷贝）
            {
                "code": "1A412010",
                "name": "结构工程材料",
                "level": 3,
                "children": [
                    {"code": "1A412010-X", "name": "另一片叶子", "level": 5, "children": []},
                ],
            },
            # 语义合并: 1A413000 智能建造新技术 应并入 1A413070
            {"code": "1A413000", "name": "建筑工程施工技术", "level": 2, "children": []},
            {"code": "1A413000", "name": "智能建造新技术", "level": 2,
             "children": [{"code": "1A413000-S1", "name": "智能子项", "level": 3, "children": []}]},
            {"code": "1A413070", "name": "智能建造新技术", "level": 2, "children": []},
            # 异名撞 code → Rule B 重编
            {"code": "1A421020", "name": "建筑工程施工许可的相关管理规定", "level": 4, "children": []},
            {"code": "1A421020", "name": "安全生产及施工现场管理相关规定", "level": 2, "children": []},
        ],
    }


def test_skeleton_repair_full() -> None:
    report = build_taxonomy_skeleton_repair(taxonomy=_taxonomy())
    assert report["verdict"] == "PASS_TAXONOMY_SKELETON_REPAIR"
    cand = report["candidate_taxonomy"]
    roots = cand["outline_structure"]

    # 平行重复分支被深度合并: 只剩一个 1A412010, 两片叶子都在
    mat = [r for r in roots if r.get("code") == "1A412010"] + [
        ch for r in roots for ch in r.get("children") or [] if ch.get("code") == "1A412010"
    ]
    assert len(mat) == 1
    leaf_names = {c["name"] for c in mat[0]["children"]}
    assert leaf_names == {"石材", "另一片叶子"}
    # 带证据的叶子保留 provenance
    stone = next(c for c in mat[0]["children"] if c["name"] == "石材")
    assert stone["source_evidence"][0]["chunk_id"] == "c1"

    # 语义合并: 1A413000 智能建造新技术 的 children 进了 1A413070, 自身消失
    smart = next(r for r in roots if r.get("code") == "1A413070")
    assert any(c["name"] == "智能子项" for c in smart["children"])
    assert not any(r.get("code") == "1A413000" and r.get("name") == "智能建造新技术" for r in roots)

    # Rule B: 异名撞 code 重编
    recoded = {r["name"]: r for r in report["recoded_collisions"]}
    assert "安全生产及施工现场管理相关规定" in recoded

    # 全树无冲突
    seen = {}
    def walk(n):
        c = n.get("code")
        if c:
            assert seen.setdefault(c, n["name"]) == n["name"], c
        for ch in n.get("children") or []:
            walk(ch)
    for r in roots:
        walk(r)

    s = report["summary"]
    assert s["deep_merged_count"] >= 1
    assert s["semantic_merged_count"] == 1
    assert s["production_write_count"] == 0


def test_skeleton_repair_safety_and_immutability() -> None:
    taxonomy = _taxonomy()
    snap = json.dumps(taxonomy, sort_keys=True, ensure_ascii=False)
    report = build_taxonomy_skeleton_repair(taxonomy=taxonomy)
    assert json.dumps(taxonomy, sort_keys=True, ensure_ascii=False) == snap
    assert report["classification"]["candidate_only"] is True
    assert report["safety"]["production_write_count"] == 0
    assert "canonical_taxonomy_overwrite" in report["not_exercised"]
