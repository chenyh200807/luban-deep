from __future__ import annotations

from deeptutor.services.source_compiler.scoring_point_recall_calibration import (
    align_question_node,
    build_backfill_assets,
    build_kb_term_index,
    build_parent_child_index,
    classify_miss_row,
    extract_gold_terms,
    expanded_node_scope,
    merge_backfill_assets,
    measure_case_recall,
)


def test_extract_gold_terms_splits_distinctive_list_terms() -> None:
    point = {
        "label": "必须写出'施工总进度计划表(图)''开、竣工日期及工期一览表''资源需要量及供应平衡表'等规范术语原文",
        "official_basis": "施工总进度计划的内容包括:编制说明,施工总进度计划表(图),分期(分批)实施工程的开、竣工日期及工期一览表,资源需要量及供应平衡表等。",
        "point_type": "text_term",
    }

    terms = extract_gold_terms(point)

    assert "施工总进度计划表(图)" in terms
    assert "分期(分批)实施工程的开竣工日期及工期一览表" in terms
    assert "资源需要量及供应平衡表" in terms
    assert "内容" not in terms


def test_parent_node_expands_to_child_asset_nodes() -> None:
    parent_child = build_parent_child_index(
        [
            {"taxonomy": {"node_code": "1A431000", "parent_code": "1A430000"}},
            {"taxonomy": {"node_code": "1A432000", "parent_code": "1A430000"}},
            {"taxonomy": {"node_code": "1A432001", "parent_code": "1A432000"}},
        ]
    )

    aligned = align_question_node("1A430000", asset_nodes={"1A431000", "1A432001"}, parent_child=parent_child)

    assert aligned.status == "expanded_parent"
    assert aligned.asset_nodes == ["1A431000", "1A432001"]


def test_na_question_node_is_coverage_gap_not_recall_denominator() -> None:
    aligned = align_question_node("NA", asset_nodes={"1A433000"}, parent_child={})

    assert aligned.status == "coverage_gap_na"
    assert aligned.asset_nodes == []


def test_measure_case_recall_matches_terms_in_required_terms_or_quotes() -> None:
    case = {
        "case_id": "QX",
        "question_node": "1A436000",
        "gold_scoring_points": [
            {
                "point_id": "P1",
                "label": "必须写出'操作平台'和'防护栏杆'",
                "official_basis": "应设置操作平台;水平通道两侧应设置防护栏杆。",
                "point_type": "text_term",
            }
        ],
    }
    assets_by_node = {
        "1A436000": [
            {"point_id": "sp1", "required_terms": ["操作平台"], "provenance": {"quote": "操作平台"}},
            {"point_id": "sp2", "required_terms": ["水平通道两侧应设置防护栏杆"], "provenance": {"quote": "水平通道两侧应设置防护栏杆"}},
        ]
    }

    result = measure_case_recall(case, assets_by_node=assets_by_node, parent_child={})

    assert result["summary"]["term_total"] == 2
    assert result["summary"]["term_hit"] == 2
    assert result["summary"]["term_recall"] == 1.0


def test_generic_short_terms_are_removed_from_gold_denominator() -> None:
    point = {
        "point_type": "text_term",
        "label": "必须写出'内容''措施''钢丝绳''甲醛'",
        "official_basis": "内容、措施、钢丝绳、甲醛。",
        "required_terms_v1_5": ["内容", "措施", "钢丝绳", "甲醛"],
    }

    assert extract_gold_terms(point) == ["钢丝绳", "甲醛"]


def test_expanded_node_scope_includes_siblings_and_inferred_parent_for_missing_leaf() -> None:
    parent_child = build_parent_child_index(
        [
            {"taxonomy": {"node_code": "1A413030", "parent_code": "1A413000"}},
            {"taxonomy": {"node_code": "1A413050", "parent_code": "1A413000"}},
            {"taxonomy": {"node_code": "1A436000", "parent_code": "1A430000"}},
        ]
    )

    exact_scope = expanded_node_scope("1A413030", asset_nodes={"1A413030", "1A413050"}, parent_child=parent_child)
    missing_leaf_scope = expanded_node_scope("1A413040", asset_nodes={"1A413030", "1A413050"}, parent_child=parent_child)

    assert exact_scope.status == "expanded_sibling_scope"
    assert exact_scope.asset_nodes == ["1A413030", "1A413050"]
    assert missing_leaf_scope.status == "expanded_inferred_parent_scope"
    assert missing_leaf_scope.asset_nodes == ["1A413030", "1A413050"]


def test_miss_classification_distinguishes_kb_present_from_non_textbook() -> None:
    kb_index = build_kb_term_index(
        [
            {
                "chunk_id": "c1",
                "content_markdown": "施工现场应设置连续的安全绳。",
                "taxonomy": {"node_code": "1A436000"},
                "source_meta": {"page_num": 8},
            }
        ]
    )
    absent_asset_row = {
        "gold_term": "连续的安全绳",
        "all_kb_hit": False,
        "all_kb_matches": [],
    }
    non_textbook_row = {
        "gold_term": "虚工作",
        "all_kb_hit": False,
        "all_kb_matches": [],
    }

    assert classify_miss_row(absent_asset_row, kb_index)["class"] == "asset_absent_but_in_kb"
    assert classify_miss_row(non_textbook_row, kb_index)["class"] == "gold_non_textbook"


def test_backfill_asset_uses_textbook_clause_not_bare_gold_term() -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "content_markdown": "水平通道两侧应设置防护栏杆；当利用钢梁作为水平通道时，应在钢梁一侧设置连续的安全绳，安全绳宜采用钢丝绳。",
            "taxonomy": {"node_code": "1A436000"},
            "source_meta": {"page_num": 122},
        }
    ]
    candidates = [
        {
            "case_id": "Q2-1A436000-罚则",
            "gold_point_id": "P3",
            "gold_term": "连续的安全绳",
            "candidate_chunk_id": "c1",
            "candidate_node_code": "1A436000",
            "candidate_page_num": 122,
        }
    ]

    assets = build_backfill_assets(candidates, chunks)

    assert len(assets) == 1
    asset = assets[0]
    assert asset["backfill_source"] == "golden_driven_Q2-1A436000-罚则_P3"
    assert asset["required_terms"] != ["连续的安全绳"]
    assert "连续的安全绳" in asset["provenance"]["quote"]
    assert asset["required_terms"][0] in chunks[0]["content_markdown"]


def test_backfill_asset_maps_normalized_term_back_to_textbook_clause() -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "content_markdown": "同一连接区段内纵向受力钢筋接头面积百分率不宜超过 50%。",
            "taxonomy": {"node_code": "1A434000"},
            "source_meta": {"page_num": 66},
        }
    ]
    candidates = [
        {
            "case_id": "Q12-1A412000-罚则",
            "gold_point_id": "P2",
            "gold_term": "不宜超过50%",
            "candidate_chunk_id": "c1",
            "candidate_node_code": "1A434000",
            "candidate_page_num": 66,
            "candidate_quote": "同一连接区段内纵向受力钢筋接头面积百分率不宜超过 50%。",
        }
    ]

    assets = build_backfill_assets(candidates, chunks)

    assert len(assets) == 1
    assert "不宜超过 50%" in assets[0]["required_terms"][0]
    assert assets[0]["required_terms"][0] in chunks[0]["content_markdown"]


def test_backfill_asset_uses_full_chunk_when_candidate_quote_is_truncated() -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "content_markdown": "钢筋连接质量控制：同一连接区段内纵向受力钢筋接头面积百分率不宜超过 50%。",
            "taxonomy": {"node_code": "1A434000"},
            "source_meta": {"page_num": 66},
        }
    ]
    candidates = [
        {
            "case_id": "Q12-1A412000-罚则",
            "gold_point_id": "P2",
            "gold_term": "不宜超过50%",
            "candidate_chunk_id": "c1",
            "candidate_quote": "钢筋连接质量控制：同一连接区段内纵向受力钢",
        }
    ]

    assets = build_backfill_assets(candidates, chunks)

    assert len(assets) == 1
    assert "不宜超过 50%" in assets[0]["required_terms"][0]


def test_backfill_assets_improve_recall_without_changing_original_assets() -> None:
    case = {
        "case_id": "QX",
        "question_node": "1A436000",
        "gold_scoring_points": [
            {
                "point_id": "P1",
                "label": "必须写出'连续的安全绳'",
                "official_basis": "应设置连续的安全绳。",
                "point_type": "text_term",
                "required_terms_v1_5": ["连续的安全绳"],
            }
        ],
    }
    natural_assets = {"1A436000": []}
    backfill_assets = [
        {
            "point_id": "bf1",
            "node_code": "1A436000",
            "chunk_id": "c1",
            "point_type": "text_term",
            "anchor_source": "textbook_backfill",
            "required_terms": ["应在钢梁一侧设置连续的安全绳"],
            "provenance": {"quote": "应在钢梁一侧设置连续的安全绳"},
        }
    ]

    natural = measure_case_recall(case, assets_by_node=natural_assets, parent_child={})
    merged = measure_case_recall(case, assets_by_node=merge_backfill_assets(natural_assets, backfill_assets), parent_child={})

    assert natural["summary"]["term_hit"] == 0
    assert merged["summary"]["term_hit"] == 1
