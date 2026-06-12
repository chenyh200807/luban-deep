from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_rich_leaf_batch_relink_candidates import (
    build_batch_relink_candidates,
)


def _classification() -> dict:
    return {
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "release_truth_claimed": False,
    }


def _safety() -> dict:
    return {
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "installed_runtime_supply": False,
        "production_write_count": 0,
        "release_truth_claimed": False,
    }


def _pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "v2.3.1_test",
        "classification": _classification(),
        "safety": _safety(),
        "runtime_token_pack_units": [
            {
                "unit_id": "u_bad",
                "leaf_id": "L-STONE",
                "leaf_name_path": "材料 > 石材的性能与应用",
                "candidate_only": True,
                "compiled_context": {"concepts": ["地基基础承载力。"]},
                "source_ref": {"record_id": "wrong.json", "source_path": "wrong.json", "source_lane": "lecture", "span_hash": "x"},
            },
            {
                "unit_id": "u_orphan",
                "leaf_id": "L-ORPHAN",
                "leaf_name_path": "材料 > 找不到证据的叶子",
                "candidate_only": True,
                "compiled_context": {"concepts": ["某种无证据内容。"]},
                "source_ref": {"record_id": "w2.json", "source_path": "w2.json", "source_lane": "lecture", "span_hash": "y"},
            },
        ],
    }


def _audit() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_pack_semantic_quality_audit.v1",
        "classification": _classification(),
        "safety": _safety(),
        "rows": [
            {"unit_id": "u_bad", "leaf_id": "L-STONE", "leaf_name_path": "材料 > 石材的性能与应用", "semantic_tier": "pollution_suspect"},
            {"unit_id": "u_orphan", "leaf_id": "L-ORPHAN", "leaf_name_path": "材料 > 找不到证据的叶子", "semantic_tier": "pollution_suspect"},
        ],
    }


def _taxonomy() -> dict:
    return {
        "children": [
            {"code": "L-STONE", "name": "石材的性能与应用", "keywords": ["天然石材", "抗压强度", "勒脚"]},
            {"code": "L-ORPHAN", "name": "找不到证据的叶子", "keywords": ["量子加固", "反重力砌筑"]},
        ]
    }


def _book(tmp_path: Path) -> Path:
    book = {
        "meta": {},
        "content_blocks": [
            {
                "chunk_id": "chunk_stone",
                "source_meta": {"page_num": 51},
                "taxonomy": {"node_code": "1A412010"},
                "content_markdown": "天然石材的抗压强度高，多用于基础、勒脚部位。",
                "knowledge_cards": [{"card_title": "石材", "card_content": "天然石材抗压强度高，常用于勒脚。"}],
                "assessment": {"generated_question": "石材用途？", "grading_keywords": ["勒脚"]},
            },
            {
                "chunk_id": "chunk_other",
                "source_meta": {"page_num": 99},
                "taxonomy": {"node_code": "1A437000"},
                "content_markdown": "项目管理信息系统包括成本管理子系统。",
                "knowledge_cards": [],
                "assessment": {},
            },
        ],
    }
    path = tmp_path / "book.json"
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return path


def test_batch_relink_repairs_strong_candidate_and_reports_unresolved(tmp_path: Path) -> None:
    book = _book(tmp_path)
    report = build_batch_relink_candidates(
        runtime_token_pack=_pack(),
        audit=_audit(),
        taxonomy=_taxonomy(),
        book_files=[book],
        source_root=tmp_path,
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "PASS_BATCH_RELINK_CANDIDATES_WITH_UNRESOLVED"
    assert report["summary"]["relinked_unit_count"] == 1
    assert report["summary"]["unresolved_unit_count"] == 1

    patched = report["patched_runtime_token_pack"]
    unit = next(u for u in patched["runtime_token_pack_units"] if u["unit_id"] == "u_bad")
    assert unit["source_ref"]["chunk_id"] == "chunk_stone"
    assert unit["review_source"] == "batch_relink_candidate"
    assert "石材" in json.dumps(unit["compiled_context"], ensure_ascii=False)
    assert patched["version"] != "v2.3.1_test"
    assert patched["patch_lineage"]["base_version"] == "v2.3.1_test"

    unresolved = report["unresolved_work_orders"]
    assert unresolved[0]["unit_id"] == "u_orphan"
    assert unresolved[0]["work_order_type"] == "batch_relink_unresolved_source_gap"
    assert unresolved[0]["reason"] == "no_candidate_chunk_above_threshold"


def test_batch_relink_flags_ambiguous_runner_up(tmp_path: Path) -> None:
    book_payload = json.loads(_book(tmp_path).read_text(encoding="utf-8"))
    clone = dict(book_payload["content_blocks"][0])
    clone = json.loads(json.dumps(clone, ensure_ascii=False))
    clone["chunk_id"] = "chunk_stone_clone"
    book_payload["content_blocks"].append(clone)
    path = tmp_path / "book2.json"
    path.write_text(json.dumps(book_payload, ensure_ascii=False), encoding="utf-8")

    report = build_batch_relink_candidates(
        runtime_token_pack=_pack(),
        audit=_audit(),
        taxonomy=_taxonomy(),
        book_files=[path],
        source_root=tmp_path,
        min_keyword_overlap=0.6,
    )
    relinked = next(r for r in report["relinked"] if r["unit_id"] == "u_bad")
    assert relinked["ambiguous_runner_up"] is True


def test_batch_relink_preserves_safety_and_input_pack(tmp_path: Path) -> None:
    pack = _pack()
    report = build_batch_relink_candidates(
        runtime_token_pack=pack,
        audit=_audit(),
        taxonomy=_taxonomy(),
        book_files=[_book(tmp_path)],
        source_root=tmp_path,
        min_keyword_overlap=0.6,
    )
    assert pack["runtime_token_pack_units"][0]["source_ref"]["span_hash"] == "x"
    for payload in (report, report["patched_runtime_token_pack"]):
        assert payload["classification"]["candidate_only"] is True
        assert payload["classification"]["runtime_install_allowed"] is False
        assert payload["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "production_rag_runtime" in report["not_exercised"]
