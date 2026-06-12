from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_rich_leaf_leaf_evidence_recompile import (
    build_leaf_evidence_recompile,
)


def _pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "v2.4_test",
        "classification": {
            "candidate_only": True, "review_only": True, "runtime_install_allowed": False,
            "production_default": False, "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False, "official_score_allowed": False,
            "installed_runtime_supply": False, "production_write_count": 0, "release_truth_claimed": False,
        },
        "runtime_token_pack_units": [
            {
                "unit_id": "u1", "leaf_id": "1A412010-B103",
                "leaf_name_path": "结构工程材料 > 石材",
                "compiled_context": {"concepts": ["旧轴内容"]},
                "source_ref": {"record_id": "old", "source_path": "old", "source_lane": "textbook", "span_hash": "old"},
            },
            {
                "unit_id": "u2", "leaf_id": "GONE-1",
                "leaf_name_path": "x > 不存在的叶子",
                "quarantine_candidate": True,
                "compiled_context": {"concepts": ["留守内容"]},
                "source_ref": {"record_id": "r", "source_path": "r", "source_lane": "lecture", "span_hash": "h"},
            },
        ],
    }


def _taxonomy() -> dict:
    return {
        "outline_structure": [
            {
                "code": "1A412010", "name": "结构工程材料", "level": 3,
                "children": [
                    {
                        "code": "1A412010-B103", "name": "石材", "level": 4,
                        "keywords": ["天然石材", "勒脚"],
                        "source_evidence": [{"chunk_id": "ck1", "page_num": 51, "source_file": "book.json"}],
                        "children": [],
                    }
                ],
            }
        ]
    }


def _book(tmp_path: Path) -> Path:
    book = {
        "content_blocks": [
            {
                "chunk_id": "ck1",
                "source_meta": {"page_num": 51},
                "content_markdown": "### 石材\n\n天然石材抗压强度高，多用于基础、勒脚部位。",
                "knowledge_cards": [{"card_title": "石材特性", "card_content": "天然石材抗压强度高，常用于勒脚。"}],
                "assessment": {"generated_question": "石材用途？", "grading_keywords": ["勒脚"]},
            }
        ]
    }
    p = tmp_path / "book.json"
    p.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return p


def test_recompile_from_leaf_evidence(tmp_path: Path) -> None:
    book = _book(tmp_path)
    report = build_leaf_evidence_recompile(
        runtime_token_pack=_pack(),
        taxonomy=_taxonomy(),
        book_files=[book],
        source_root=tmp_path,
    )
    assert report["verdict"] == "PASS_LEAF_EVIDENCE_RECOMPILE"
    pack = report["recompiled_runtime_token_pack"]
    u1 = next(u for u in pack["runtime_token_pack_units"] if u["unit_id"] == "u1")
    ctx = json.dumps(u1["compiled_context"], ensure_ascii=False)
    assert "天然石材" in ctx and "旧轴内容" not in ctx
    assert u1["source_ref"]["chunk_id"] == "ck1"
    assert u1["review_source"] == "leaf_evidence_recompile_candidate"
    # 无新叶子的 unit 原样保留
    u2 = next(u for u in pack["runtime_token_pack_units"] if u["unit_id"] == "u2")
    assert u2["compiled_context"] == {"concepts": ["留守内容"]}
    assert report["summary"]["recompiled_unit_count"] == 1
    assert report["summary"]["skipped_unit_count"] == 1
    assert pack["version"] != "v2.4_test"


def test_recompile_blocks_on_missing_chunk(tmp_path: Path) -> None:
    book = _book(tmp_path)
    taxonomy = _taxonomy()
    taxonomy["outline_structure"][0]["children"][0]["source_evidence"][0]["chunk_id"] = "missing"
    report = build_leaf_evidence_recompile(
        runtime_token_pack=_pack(), taxonomy=taxonomy, book_files=[book], source_root=tmp_path,
    )
    rows = {r["unit_id"]: r for r in report["rows"]}
    assert rows["u1"]["status"] == "evidence_chunk_missing"
    assert report["summary"]["recompiled_unit_count"] == 0


def test_recompile_safety(tmp_path: Path) -> None:
    report = build_leaf_evidence_recompile(
        runtime_token_pack=_pack(), taxonomy=_taxonomy(), book_files=[_book(tmp_path)], source_root=tmp_path,
    )
    for payload in (report, report["recompiled_runtime_token_pack"]):
        assert payload["classification"]["candidate_only"] is True
        assert payload["classification"]["runtime_install_allowed"] is False
        assert payload["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
