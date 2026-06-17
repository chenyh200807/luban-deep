from __future__ import annotations

import json
from pathlib import Path


def _taxonomy() -> dict:
    return {
        "meta": {"frozen": "taxonomy-frozen-v1-20260612"},
        "stats": {"total_nodes": 6},
        "outline_structure": [
            {
                "code": "1A410000",
                "name": "建筑工程技术",
                "children": [
                    {
                        "code": "1A411011-B001",
                        "name": "建筑分类",
                        "keywords": ["建筑分类"],
                        "source_evidence": [
                            {
                                "chunk_id": "C1",
                                "page_num": 2,
                                "source_file": "BOOK_A.json",
                                "source_lane": "textbook",
                            }
                        ],
                    },
                    {
                        "code": "1A411011-B002",
                        "name": "缺链叶",
                        "keywords": ["缺链"],
                        "source_evidence": [
                            {
                                "chunk_id": "C_MISSING",
                                "page_num": 9,
                                "source_file": "BOOK_A.json",
                                "source_lane": "textbook",
                            }
                        ],
                    },
                    {
                        "code": "1A435000-G02",
                        "name": "价值工程原理",
                        "keywords": ["价值工程"],
                        "source_evidence": [
                            {
                                "chunk_id": None,
                                "page_num": None,
                                "source_file": "讲义(成本管理单元 rtp22_aaaa1111bbbb2222)",
                                "source_lane": "lecture",
                            }
                        ],
                    },
                    {
                        "code": "1A411011-B003",
                        "name": "无证据叶",
                        "keywords": [],
                    },
                ],
            }
        ],
    }


def _book_file(tmp_path: Path) -> Path:
    book = {
        "content_blocks": [
            {
                "chunk_id": "C1",
                "content_markdown": "建筑分类按使用性质划分。民用建筑包括居住建筑和公共建筑。",
                "source_meta": {"page_num": 2},
                "knowledge_cards": [{"card_title": "建筑分类", "card_content": "民用建筑分居住与公共两类。"}],
                "assessment": {"generated_question": "建筑如何分类？", "grading_keywords": ["民用建筑"]},
            }
        ]
    }
    path = tmp_path / "BOOK_A.json"
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return path


def _base_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp22_aaaa1111bbbb2222",
                "leaf_id": "OLD-1",
                "compiled_context": {"concepts": ["价值工程=功能/成本。"]},
                "source_ref": {
                    "record_id": "讲义/x/page_1_1.json#chunk:LEC1",
                    "source_path": "讲义/x/page_1_1.json",
                    "source_lane": "lecture",
                    "chunk_id": "LEC1",
                    "page_num": 1,
                    "file_sha256": "deadbeef",
                    "span_hash": "spanhash",
                },
                "relative_path": "讲义/x/page_1_1.json",
            }
        ],
    }


def test_frozen_full_compile_builds_units_per_evidence_leaf(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import build_frozen_full_compile

    _book_file(tmp_path)
    report = build_frozen_full_compile(
        taxonomy=_taxonomy(),
        book_files=[tmp_path / "BOOK_A.json"],
        source_root=tmp_path,
        base_pack=_base_pack(),
    )

    assert report["verdict"] == "PASS_FROZEN_FULL_COMPILE"
    assert report["summary"]["evidence_leaf_count"] == 3
    assert report["summary"]["compiled_unit_count"] == 2
    assert report["summary"]["unresolved_count"] == 1

    pack = report["runtime_token_pack"]
    assert pack["schema"] == "luban_rich_leaf_runtime_token_pack.v2.3"
    assert pack["version"] == "v3.0_frozen_v1_full_compile"
    assert pack["status"] == "candidate_ready_for_shadow_ab_full_accounted"
    assert pack["classification"]["candidate_only"] is True
    assert pack["classification"]["runtime_install_allowed"] is False
    assert pack["safety"]["production_write_count"] == 0
    assert pack["frozen_axis"]["frozen"] == "taxonomy-frozen-v1-20260612"

    units = {u["leaf_id"]: u for u in pack["runtime_token_pack_units"]}
    book_unit = units["1A411011-B001"]
    assert book_unit["unit_id"].startswith("rtpf1_")
    assert book_unit["leaf_name_path"] == "建筑工程技术 > 建筑分类"
    assert book_unit["source_ref"]["chunk_id"] == "C1"
    assert book_unit["source_ref"]["page_num"] == 2
    assert book_unit["source_ref"]["file_sha256"]
    assert book_unit["source_ref"]["span_hash"]
    assert book_unit["compiled_context"]["concepts"]
    assert book_unit["compiled_context"]["teaching_cards"]
    assert book_unit["review_source"] == "frozen_v1_full_compile"

    carry_unit = units["1A435000-G02"]
    assert carry_unit["review_source"] == "frozen_v1_base_pack_carryover"
    assert carry_unit["carryover_base_unit_id"] == "rtp22_aaaa1111bbbb2222"
    assert carry_unit["source_ref"]["chunk_id"] == "LEC1"
    assert carry_unit["source_lane"] == "lecture"


def test_frozen_full_compile_unit_ids_are_deterministic(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import _unit_id

    assert _unit_id("1A411011-B001") == _unit_id("1A411011-B001")
    assert _unit_id("1A411011-B001") != _unit_id("1A411011-B002")
    assert _unit_id("1A411011-B001").startswith("rtpf1_")


def test_frozen_full_compile_blocks_on_unfrozen_taxonomy(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import build_frozen_full_compile

    taxonomy = _taxonomy()
    taxonomy["meta"] = {}
    _book_file(tmp_path)
    report = build_frozen_full_compile(
        taxonomy=taxonomy,
        book_files=[tmp_path / "BOOK_A.json"],
        source_root=tmp_path,
        base_pack=None,
    )

    assert report["verdict"] == "BLOCKED_FROZEN_FULL_COMPILE"
    assert any(b.startswith("taxonomy_not_frozen_v1") for b in report["blockers"])
    assert report["runtime_token_pack"] is None


def test_frozen_full_compile_resolves_lecture_page_files(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import _resolve_lecture_page_files

    lecture_dir = tmp_path / "讲义" / "2025.3.22佑森《招投标》专用讲义，版权所有，侵权必究_v8"
    lecture_dir.mkdir(parents=True)
    (lecture_dir / "page_27_27.json").write_text("[]", encoding="utf-8")

    resolved = _resolve_lecture_page_files("讲义/2025.3.22佑森《招投标》专用讲义_v8/page_27_27.json", tmp_path)
    assert len(resolved) == 1
    assert resolved[0].name == "page_27_27.json"


def test_frozen_full_compile_cli_writes_report_and_pack(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import main

    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(json.dumps(_taxonomy(), ensure_ascii=False), encoding="utf-8")
    book_path = _book_file(tmp_path)
    base_pack_path = tmp_path / "base_pack.json"
    base_pack_path.write_text(json.dumps(_base_pack(), ensure_ascii=False), encoding="utf-8")
    out_report = tmp_path / "out" / "report.json"
    out_pack = tmp_path / "out" / "pack.json"

    exit_code = main(
        [
            "--taxonomy",
            str(taxonomy_path),
            "--book-file",
            str(book_path),
            "--source-root",
            str(tmp_path),
            "--base-pack",
            str(base_pack_path),
            "--output-report",
            str(out_report),
            "--output-pack",
            str(out_pack),
        ]
    )

    assert exit_code == 0
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS_FROZEN_FULL_COMPILE"
    assert report["runtime_token_pack_path"] == str(out_pack)
    pack = json.loads(out_pack.read_text(encoding="utf-8"))
    assert pack["summary"]["unit_count"] == 2
