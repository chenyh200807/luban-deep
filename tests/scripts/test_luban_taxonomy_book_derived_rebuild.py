from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_taxonomy_book_derived_rebuild import (
    _extract_headings,
    _normalize_heading,
    build_book_derived_taxonomy_rebuild,
)


def _taxonomy() -> dict:
    return {
        "meta": {"version": "V25.0 SLIM"},
        "outline_structure": [
            {
                "code": "1A412010",
                "name": "结构工程材料",
                "level": 3,
                "children": [
                    {
                        "code": "1A412014",
                        "name": "砌体材料的性能与应用",
                        "level": 4,
                        "children": [
                            {
                                "code": "1A412014-02",
                                "name": "石材的性能与应用",
                                "level": 5,
                                "keywords": ["天然石材", "勒脚"],
                                "children": [],
                            },
                            {"code": "1A412014-09", "name": "凭空捏造的叶子", "level": 5, "children": []},
                        ],
                    },
                ],
            },
            {"code": "1A432000", "name": "招标投标管理", "level": 3, "children": []},
        ],
    }


def _book(tmp_path: Path) -> Path:
    book = {
        "content_blocks": [
            {
                "chunk_id": "1A412014_051_0092",
                "source_meta": {"page_num": 51},
                "content_markdown": "### 2.1.4 砌体材料\n\n#### 1）石材\n\n砌体结构中常用天然石材，多用于基础、勒脚部位。\n\n**2）砌块**\n\n砌块内容。",
                "knowledge_cards": [{"card_title": "石材特性", "card_content": "x", "keywords": ["天然石材", "抗压强度"]}],
                "assessment": {"grading_keywords": ["勒脚"]},
            },
            {
                # 前缀不在 L1-L4，应回退到 1A432000
                "chunk_id": "1A432002_010_0010",
                "source_meta": {"page_num": 10},
                "content_markdown": "#### 联合体投标\n\n联合体投标规定内容。",
                "knowledge_cards": [],
                "assessment": {},
            },
        ]
    }
    p = tmp_path / "book.json"
    p.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return p


def test_normalize_heading_strips_numbering() -> None:
    assert _normalize_heading("2.1.4 砌体材料") == "砌体材料"
    assert _normalize_heading("1）石材") == "石材"
    assert _normalize_heading("（3）项目管理信息系统") == "项目管理信息系统"
    assert _normalize_heading("**2）砌块**") == "砌块"
    assert _normalize_heading("第2章 主要建筑工程材料") == "主要建筑工程材料"


def test_extract_headings_from_markdown() -> None:
    md = "### 2.1 标题甲\n\n正文。\n\n#### 1）标题乙\n\n**3）标题丙**\n\n- **不是标题** 后面还有字\n"
    names = [h["name"] for h in _extract_headings(md)]
    assert names == ["标题甲", "标题乙", "标题丙"]


def test_rebuild_produces_grounded_unique_leaves(tmp_path: Path) -> None:
    report = build_book_derived_taxonomy_rebuild(
        taxonomy=_taxonomy(),
        book_files=[_book(tmp_path)],
    )
    assert report["verdict"] == "PASS_BOOK_DERIVED_TAXONOMY_REBUILD"
    cand = report["candidate_taxonomy"]

    # 新叶子挂在锚点下，code 构造唯一，带 provenance
    anchor = cand["outline_structure"][0]["children"][0]
    assert anchor["code"] == "1A412014"
    leaves = anchor["children"]
    names = [leaf["name"] for leaf in leaves]
    assert "石材" in names and "砌块" in names
    stone = next(leaf for leaf in leaves if leaf["name"] == "石材")
    assert stone["code"].startswith("1A412014-B")
    assert stone["source_evidence"][0]["chunk_id"] == "1A412014_051_0092"
    assert stone["source_evidence"][0]["page_num"] == 51
    assert "天然石材" in stone["keywords"]

    # 旧 L5/L6 已被替换：捏造叶子不在新树中
    assert "凭空捏造的叶子" not in json.dumps(cand, ensure_ascii=False)

    # 前缀回退：1A432002 chunk 挂到 1A432000
    fallback_parent = cand["outline_structure"][1]
    assert any(leaf["name"] == "联合体投标" for leaf in fallback_parent["children"])

    # 全树 code 唯一
    seen = set()
    def walk(node):
        assert node["code"] not in seen
        seen.add(node["code"])
        for ch in node.get("children") or []:
            walk(ch)
    for r in cand["outline_structure"]:
        walk(r)


def test_rebuild_reconciles_old_leaves(tmp_path: Path) -> None:
    report = build_book_derived_taxonomy_rebuild(
        taxonomy=_taxonomy(),
        book_files=[_book(tmp_path)],
    )
    recon = {r["old_name"]: r for r in report["old_leaf_reconciliation"]}
    # 旧叶子「石材的性能与应用」应映射到新叶子「石材」(名称包含关系)
    assert recon["石材的性能与应用"]["status"] == "mapped"
    assert recon["石材的性能与应用"]["new_code"].startswith("1A412014-B")
    # 捏造叶子无处可映射 → unmapped(候删清单)
    assert recon["凭空捏造的叶子"]["status"] == "unmapped"
    assert report["summary"]["old_leaf_mapped_count"] == 1
    assert report["summary"]["old_leaf_unmapped_count"] == 1


def test_rebuild_safety_and_input_immutability(tmp_path: Path) -> None:
    taxonomy = _taxonomy()
    snapshot = json.dumps(taxonomy, sort_keys=True, ensure_ascii=False)
    report = build_book_derived_taxonomy_rebuild(taxonomy=taxonomy, book_files=[_book(tmp_path)])
    assert json.dumps(taxonomy, sort_keys=True, ensure_ascii=False) == snapshot
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "canonical_taxonomy_overwrite" in report["not_exercised"]
