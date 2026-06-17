from __future__ import annotations

import json
from pathlib import Path

from scripts.backfill_2026_textbook_chunk_metadata import _row_plan, load_patches


def test_loads_textbook_metadata_patch_from_cleaned_book_json(tmp_path: Path) -> None:
    source = tmp_path / "book.json"
    source.write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A411011_001_0001",
                        "source_meta": {
                            "page_num": 1,
                            "original_anchor": "1.1 建筑物的构成与设计要求",
                            "source_name": "2026一建《建筑》电子版教材_9-166",
                        },
                        "taxonomy": {
                            "node_code": "1A411011",
                            "taxonomy_path": "建筑工程技术 > 建筑设计与构造 > 建筑设计 > 建筑物分类与构成",
                            "topic": "建筑物分类",
                        },
                        "content_markdown": "### 1.1 建筑物的构成与设计要求\n正文",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    patches = load_patches([source])
    patch = patches["1A411011_001_0001"]

    assert patch.title == "1.1 建筑物的构成与设计要求"
    assert patch.node_code == "1A411011"
    assert patch.metadata["source_table"] == "kb_chunks"
    assert patch.metadata["source_span"]["chapter"] == "第1章 建筑工程设计技术"
    assert patch.metadata["source_span"]["section"] == "建筑物的构成与设计要求"
    assert patch.metadata["source_span"]["knowledge_point"] == "建筑物分类"


def test_row_plan_fills_missing_metadata_without_overwriting_top_level_values(tmp_path: Path) -> None:
    source = tmp_path / "book.json"
    source.write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A413030_010_0001",
                        "source_meta": {"page_num": 10, "original_anchor": "3.5 屋面与防水工程施工"},
                        "taxonomy": {
                            "node_code": "1A413030",
                            "taxonomy_path": "建筑工程技术 > 建筑工程施工技术 > 屋面与防水工程施工",
                            "topic": "防水工程",
                        },
                        "content_markdown": "### 3.5 屋面与防水工程施工\n正文",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    patch = load_patches([source])["1A413030_010_0001"]

    plan = _row_plan(
        {
            "chunk_id": "1A413030_010_0001",
            "card_title": "防水工程",
            "node_code": "1A413030",
            "taxonomy_path": "建筑工程技术 > 建筑工程施工技术 > 屋面与防水工程施工",
            "page_num": 10,
            "source_doc": "2026教材 v3_production_core9-166",
            "metadata": {"topic": "防水工程"},
        },
        patch,
        force_metadata=False,
    )

    assert plan["conflicts"] == []
    assert plan["top_update"] == {}
    assert plan["metadata_update"]["source_id"] == "1A413030_010_0001"
    assert plan["metadata_update"]["source_span"]["section"] == "屋面与防水工程施工"


def test_row_plan_blocks_top_level_conflicts(tmp_path: Path) -> None:
    source = tmp_path / "book.json"
    source.write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A413030_010_0001",
                        "source_meta": {"page_num": 10},
                        "taxonomy": {"node_code": "1A413030", "taxonomy_path": "建筑工程技术 > 建筑工程施工技术"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    patch = load_patches([source])["1A413030_010_0001"]

    plan = _row_plan(
        {
            "chunk_id": "1A413030_010_0001",
            "card_title": "防水工程",
            "node_code": "1A411011",
            "taxonomy_path": "建筑工程技术 > 建筑工程施工技术",
            "page_num": 10,
            "source_doc": "2026教材 v3_production_core9-166",
            "metadata": {},
        },
        patch,
        force_metadata=False,
    )

    assert "node_code" in plan["conflicts"]
