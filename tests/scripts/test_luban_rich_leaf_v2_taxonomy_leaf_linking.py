from __future__ import annotations


def test_v2_taxonomy_leaf_linking_uses_canonical_candidates_only() -> None:
    from scripts.run_luban_rich_leaf_v2_taxonomy_leaf_linking import run_taxonomy_leaf_linking

    runtime_token_pack = {
        "schema": "luban_rich_leaf_runtime_token_pack.v2",
        "runtime_token_pack_units": [
            {
                "unit_id": "unit_1",
                "candidate_id": "candidate_1",
                "relative_path": "教材/防水卷材.json",
                "source_lane": "source_truth",
                "compiled_context": {
                    "concepts": ["防水卷材"],
                    "rules": ["SBS 卷材适用于较低气温环境的建筑防水"],
                },
                "source_ref": {"excerpt": "SBS 卷材适用于较低气温环境的建筑防水。"},
            }
        ],
    }
    taxonomy_index = {
        "manifest": {"schema_version": "luban_canonical_taxonomy_index.v1", "content_hash": "hash_1"},
        "leaves": [
            {"code": "1A412012-01-a", "name_path": "建筑材料 > 防水材料 > 防水卷材", "keywords": ["防水卷材", "SBS 卷材"]},
            {"code": "1A412012-01-a", "name_path": "建筑材料 > 防水材料 > 防水卷材", "keywords": ["防水卷材"]},
            {"code": "1A411011-01-a", "name_path": "建筑设计 > 建筑高度分类", "keywords": ["高层住宅"]},
        ],
    }

    report = run_taxonomy_leaf_linking(
        runtime_token_pack=runtime_token_pack,
        taxonomy_index=taxonomy_index,
        top_k=3,
    )

    assert report["verdict"] == "PASS_TAXONOMY_LEAF_LINKING_SHADOW_CANDIDATES"
    assert report["summary"]["link_count"] == 1
    assert report["summary"]["taxonomy_leaf_row_count"] == 3
    assert report["summary"]["taxonomy_leaf_count"] == 2
    assert report["summary"]["taxonomy_duplicate_row_count"] == 1
    assert report["taxonomy_leaf_links"][0]["candidate_leaf_links"][0]["leaf_id"] == "1A412012-01-a"
    assert report["taxonomy_leaf_links"][0]["status"] == "linked_shadow_candidate"
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
