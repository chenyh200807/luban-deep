"""Tests for the taxonomy-frozen-v1.1 coverage expansion pipeline."""
from __future__ import annotations

from typing import Any

from scripts.run_luban_taxonomy_coverage_expansion_v11 import (
    apply_candidates,
    derive_gap_prefixes,
    merge_key,
    mint_leaf,
    propose_placement,
    signal_bigrams,
    strict_term_hits,
    validate_tree,
)


def _pack(leaf_ids: list[str]) -> dict[str, Any]:
    return {"runtime_token_pack_units": [{"leaf_id": leaf_id} for leaf_id in leaf_ids]}


def _taxonomy() -> dict[str, Any]:
    return {
        "meta": {"frozen": "taxonomy-frozen-v1-20260612"},
        "stats": {"total_node_count": 3, "leaf_count": 1},
        "outline_structure": [
            {
                "code": "1A412010",
                "name": "结构工程材料",
                "level": 3,
                "children": [
                    {
                        "code": "1A412011",
                        "name": "建筑钢材的性能与应用",
                        "level": 4,
                        "children": [
                            {"code": "1A412011-B001", "name": "钢材力学性能", "level": 5, "children": []}
                        ],
                    }
                ],
            }
        ],
    }


def test_merge_key_strips_regulation_suffixes() -> None:
    assert merge_key("危险性较大的分部分项工程安全管理的有关规定") == "危险性较大的分部分项工程安全管理"
    assert merge_key("建筑设计与构造") == "建筑设计与构造"


def test_signal_bigrams_drop_generic_construction_words() -> None:
    assert "施工" not in signal_bigrams("基坑支护工程施工")
    assert "测量" in signal_bigrams("施工测量")


def test_strict_term_hits_flags_axis_terms() -> None:
    assert strict_term_hits("双代号网络图绘制") == ["网络计划", "双代号"] or "双代号" in strict_term_hits(
        "双代号网络图绘制"
    )
    assert strict_term_hits("水泥的性能和应用") == []


def test_derive_gap_prefixes_is_exam_minus_pack() -> None:
    gap, pack_prefixes = derive_gap_prefixes({"1A411001", "1A412010"}, _pack(["1A412010-B001", "1A412010-B002"]))
    assert gap == ["1A411001"]
    assert pack_prefixes == ["1A412010"]


def test_propose_placement_rejects_generic_bigram_same_code_match() -> None:
    taxonomy = _taxonomy()
    from scripts.run_luban_taxonomy_coverage_expansion_v11 import index_canonical

    index = index_canonical(taxonomy)
    # exam concept at 1A412011 is NOT 钢材 — generic 建筑 bigram must not glue them together
    concept = {"node_code": "1A412011", "name": "建筑物分类与构成体系", "exam_text": "建筑物分类", "keywords": []}
    evidence = {"lane": "textbook", "chunk_id": "1A412010_001_0001"}
    placement = propose_placement(concept, evidence, index)
    assert placement["method"] != "same_code_name_match"
    assert placement["parent_code"] == "1A412010"


def test_apply_mints_leaf_updates_meta_and_validates() -> None:
    taxonomy = _taxonomy()
    candidates = {
        "candidates": [
            {
                "leaf_code": "1A414011-E01",
                "node_code": "1A414011",
                "name": "水泥的性能和应用",
                "keywords": ["水化热"],
                "years": [2021],
                "lane": "textbook",
                "evidence": {
                    "lane": "textbook",
                    "chunk_id": "1A412010_043_0074",
                    "source_file": "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
                    "page_num": 43,
                },
                "placement": {"parent_code": "1A412010", "parent_name": "结构工程材料"},
            }
        ],
        "unfilled": [{"node_code": "1A432051", "name": "建设工程项目管理", "reason": "no_evidence"}],
    }
    result = apply_candidates(taxonomy=taxonomy, candidates_payload=candidates)
    assert result["errors"] == []
    assert result["minted"] == ["1A414011-E01"]
    assert result["validation"]["duplicates"] == []
    meta = taxonomy["meta"]
    assert meta["frozen"] == "taxonomy-frozen-v1.1-20260613"
    assert meta["coverage_expansion"] == "coverage_expansion_20260613"
    assert meta["coverage_expansion_unfilled"][0]["node_code"] == "1A432051"
    minted = taxonomy["outline_structure"][0]["children"][-1]
    assert minted["code"] == "1A414011-E01"
    assert minted["parent_code"] == "1A412010"
    assert minted["level"] == 4
    assert minted["source_evidence"][0]["chunk_id"] == "1A412010_043_0074"
    assert "source_lane" not in minted["source_evidence"][0]  # textbook lane stays implicit
    assert taxonomy["stats"]["total_node_count"] == 4
    assert taxonomy["stats"]["leaf_count"] == 2


def test_apply_blocks_on_duplicate_or_bad_parent() -> None:
    taxonomy = _taxonomy()
    bad = {
        "candidates": [
            {
                "leaf_code": "1A412011-B001",  # already exists
                "node_code": "1A412011",
                "name": "x",
                "keywords": [],
                "years": [],
                "lane": "textbook",
                "evidence": {"lane": "textbook", "chunk_id": "c", "source_file": "f", "page_num": 1},
                "placement": {"parent_code": "1A412010"},
            },
            {
                "leaf_code": "1A999999-E01",
                "node_code": "1A999999",
                "name": "y",
                "keywords": [],
                "years": [],
                "lane": "textbook",
                "evidence": {"lane": "textbook", "chunk_id": "c", "source_file": "f", "page_num": 1},
                "placement": {"parent_code": "1A412011-B001"},  # a leaf, not a valid parent
            },
        ],
        "unfilled": [],
    }
    result = apply_candidates(taxonomy=taxonomy, candidates_payload=bad)
    assert len(result["errors"]) == 2
    # blocked apply must not have mutated the frozen tag
    assert taxonomy["meta"]["frozen"] == "taxonomy-frozen-v1-20260612"


def test_mint_leaf_standard_lane_carries_article_provenance() -> None:
    parent = {"node": {"code": "1A412010", "name": "结构工程材料", "level": 3, "children": []}}
    candidate = {
        "leaf_code": "1A432012-E01",
        "node_code": "1A432012",
        "name": "建筑材料分类和分级",
        "keywords": ["燃烧性能"],
        "years": [2021],
        "evidence": {
            "lane": "standard",
            "chunk_id": "STD_GB50354_2005_C02_A04",
            "source_file": "标准文件/20、GB50354-2005.json",
            "page_num": None,
            "standard_code": "GB 50354-2005",
            "article_id": "2.0.4",
        },
    }
    leaf = mint_leaf(candidate, parent)
    record = leaf["source_evidence"][0]
    assert record["source_lane"] == "standard"
    assert record["standard_code"] == "GB 50354-2005"
    assert record["article_id"] == "2.0.4"
    assert leaf["gap_fill"]["revision"] == "coverage_expansion_20260613"


def test_validate_tree_counts_duplicates() -> None:
    taxonomy = _taxonomy()
    taxonomy["outline_structure"][0]["children"].append({"code": "1A412011", "name": "dup", "children": []})
    report = validate_tree(taxonomy)
    assert report["duplicates"] == ["1A412011"]
