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
                # Heading-anchored so the leaf slices legitimately. A headingless
                # chunk now quarantines for every lane (no whole-chunk fallback),
                # so the compile path must be exercised via a real heading anchor.
                "content_markdown": "### 建筑分类\n\n建筑分类按使用性质划分。民用建筑包括居住建筑和公共建筑。",
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
    assert book_unit["review_source"] == "frozen_v1_full_compile_per_leaf"

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


def test_fail_closed_gate_blocks_whole_identical_intra_chunk_group() -> None:
    """造一个同 chunk 同 payload 的污染对, 验证 fail-closed 门 BLOCK 整组 (无可信正主)。

    v2 加严: 不再默认保留第一个当 owner — 切分器已保证每个 leaf 拿到自己的 span,
    残留全 payload 相同 = 切分器分不开它们, 没有可信 owner -> 全 block。"""
    from scripts.run_luban_rich_leaf_frozen_full_compile import enforce_no_intra_chunk_pollution

    shared_ctx = {"concepts": ["焊缝夹渣的成因与防治。"]}
    units = [
        {"leaf_id": "L-A", "unit_id": "u1", "compiled_context": dict(shared_ctx), "source_ref": {"chunk_id": "C9"}},
        {"leaf_id": "L-B", "unit_id": "u2", "compiled_context": dict(shared_ctx), "source_ref": {"chunk_id": "C9"}},
    ]
    clean, blocked = enforce_no_intra_chunk_pollution(units)

    assert clean == []  # no presumptive owner kept
    assert {b["leaf_id"] for b in blocked} == {"L-A", "L-B"}
    for b in blocked:
        assert b["status"] == "blocked_intra_chunk_pollution"
        assert b["quarantine_bucket"] == "fail_closed_collision"
        assert sorted(b["colliding_leaf_ids"]) == ["L-A", "L-B"]


def test_fail_closed_gate_uses_full_payload_not_truncated_hash() -> None:
    """v2: 指纹用完整 payload, 不截断前 600 字。两个 leaf concepts 头部相同 (>600 字)
    但尾部 rules 不同 -> 完整 payload 不同 -> 门必须放行 (v1 截断指纹会误 block)。"""
    from scripts.run_luban_rich_leaf_frozen_full_compile import enforce_no_intra_chunk_pollution

    long_head = ["焊缝" * 200 + "。"]  # identical >600-char concepts prefix
    units = [
        {
            "leaf_id": "L-A",
            "unit_id": "u1",
            "compiled_context": {"concepts": list(long_head), "rules": ["RULE-A"]},
            "source_ref": {"chunk_id": "C9"},
        },
        {
            "leaf_id": "L-B",
            "unit_id": "u2",
            "compiled_context": {"concepts": list(long_head), "rules": ["RULE-B"]},
            "source_ref": {"chunk_id": "C9"},
        },
    ]
    clean, blocked = enforce_no_intra_chunk_pollution(units)
    assert len(clean) == 2  # distinct full payloads -> not blocked
    assert blocked == []


def test_fail_closed_gate_passes_distinct_payloads() -> None:
    """同 chunk 但内容不同 (per-leaf 切分成功) -> 门放行, 不误杀。"""
    from scripts.run_luban_rich_leaf_frozen_full_compile import enforce_no_intra_chunk_pollution

    units = [
        {"leaf_id": "L-A", "unit_id": "u1", "compiled_context": {"concepts": ["门的设置规定。"]}, "source_ref": {"chunk_id": "C9"}},
        {"leaf_id": "L-B", "unit_id": "u2", "compiled_context": {"concepts": ["天窗的设置规定。"]}, "source_ref": {"chunk_id": "C9"}},
    ]
    clean, blocked = enforce_no_intra_chunk_pollution(units)
    assert len(clean) == 2
    assert blocked == []


def test_quarantine_bucket_classification() -> None:
    from scripts.run_luban_rich_leaf_frozen_full_compile import _quarantine_bucket

    # C class: abstract over-subdivided code.
    assert _quarantine_bucket("1A411000-E01", "建筑设计与构造", "结构作用的规定") == "over_subdivided"
    # A class: leaf name core absent from chunk -> mislink.
    assert _quarantine_bucket("1A411011-B016", "屋面防水", "焊缝夹渣的成因") == "mislink"
    # B residual: core present but no distinct subsection sliceable.
    assert _quarantine_bucket("1A411011-B020", "天窗", "天窗的设置规定与门的设置规定混排") == "unsliceable"


# ---------------------------------------------------------------------------
# v2 加严: span-scoped card filtering (co-located leaves 不再共享整 chunk 的卡)
# ---------------------------------------------------------------------------

_MULTI_LEAF_CARD_MD = """### 1.2.4 门和窗基本构造要求

#### 2. 门的设置规定

（1）新建住宅建筑户门通行净宽不应小于 0.90m。

#### 4. 天窗的设置规定

（1）采光天窗应采用防破碎坠落的透光材料。
"""


def test_compile_context_span_scoped_filters_foreign_cards() -> None:
    """同 chunk 的 knowledge_cards 是 chunk 级注解; span_scoped 切片时必须按内容重叠
    过滤, 否则每个 co-located leaf 都背上整 chunk 的卡 (第二条静默污染通道)。"""
    from scripts.luban_rich_leaf_subsection import slice_leaf_subsection
    from scripts.run_luban_rich_leaf_v23_residual_source_repair import _compile_context

    chunk = {
        "content_markdown": _MULTI_LEAF_CARD_MD,
        "knowledge_cards": [
            {"card_title": "住宅户门净宽要求", "card_content": "新建住宅建筑户门通行净宽不应小于 0.90m。"},
            {"card_title": "天窗透光材料", "card_content": "采光天窗应采用防破碎坠落的透光材料。"},
        ],
    }
    door = slice_leaf_subsection(
        _MULTI_LEAF_CARD_MD, "门的设置规定", chunk_hosts_multiple_leaves=True,
        sibling_cores=("天窗的设置规定",),
    )
    assert door is not None
    ctx = _compile_context(door.text, chunk, "C", span_scoped=True)
    titles = [json.loads(tc)["title"] for tc in ctx.get("teaching_cards") or []]
    assert "住宅户门净宽要求" in titles
    assert "天窗透光材料" not in titles  # foreign card dropped


def test_span_scoped_card_attribution_uses_title_not_only_content() -> None:
    """E 加固 (Codex Conditional GO): card_content 改写后偏离 span, 但 card_title 是
    span 主题原话 -> 必须靠 title 命中而保留 (减少过度丢 paraphrase card); 同时 foreign
    card (title+content 都不命中本 span) 仍被丢 (fail-closed 方向不变)。"""
    from scripts.luban_rich_leaf_subsection import slice_leaf_subsection
    from scripts.run_luban_rich_leaf_v23_residual_source_repair import _compile_context

    chunk = {
        "content_markdown": _MULTI_LEAF_CARD_MD,
        "knowledge_cards": [
            # CONTENT heavily reworded away from the 门 span prose, but TITLE matches it.
            {"card_title": "门的设置规定", "card_content": "入户开口尺寸须满足通行与无障碍的综合要求。"},
            # foreign: neither title nor content matches the 门 span.
            {"card_title": "天窗透光材料", "card_content": "采光天窗应采用防破碎坠落的透光材料。"},
        ],
    }
    door = slice_leaf_subsection(
        _MULTI_LEAF_CARD_MD, "门的设置规定", chunk_hosts_multiple_leaves=True,
        sibling_cores=("天窗的设置规定",),
    )
    assert door is not None
    ctx = _compile_context(door.text, chunk, "C", span_scoped=True)
    titles = [json.loads(tc)["title"] for tc in ctx.get("teaching_cards") or []]
    assert "门的设置规定" in titles  # retained via TITLE overlap despite drifted content
    assert "天窗透光材料" not in titles  # foreign card still dropped


def test_span_scoped_exam_pattern_attributed_by_grading_keywords() -> None:
    """E 加固: generated_question 改写偏离 span, 但 grading_keywords (采分点原话) 命中
    span -> exam_pattern 仍归属本 leaf, 不被过度丢弃。"""
    from scripts.luban_rich_leaf_subsection import slice_leaf_subsection
    from scripts.run_luban_rich_leaf_v23_residual_source_repair import _compile_context

    chunk = {
        "content_markdown": _MULTI_LEAF_CARD_MD,
        "knowledge_cards": [],
        "assessment": {
            "generated_question": "简述相关条目的合规判定流程。",  # drifted from span
            "grading_keywords": ["新建住宅建筑户门通行净宽不应小于"],  # verbatim span text
        },
    }
    door = slice_leaf_subsection(
        _MULTI_LEAF_CARD_MD, "门的设置规定", chunk_hosts_multiple_leaves=True,
        sibling_cores=("天窗的设置规定",),
    )
    assert door is not None
    ctx = _compile_context(door.text, chunk, "C", span_scoped=True)
    assert ctx.get("exam_patterns")  # kept via grading_keywords overlap


def test_compile_context_whole_chunk_keeps_all_cards() -> None:
    """1:1 leaf↔chunk (span_scoped=False) 不过滤, 全卡保留 (无回归)。"""
    from scripts.run_luban_rich_leaf_v23_residual_source_repair import _compile_context

    chunk = {
        "content_markdown": "建筑分类按使用性质划分。",
        "knowledge_cards": [
            {"card_title": "A", "card_content": "民用建筑分居住与公共两类。"},
            {"card_title": "B", "card_content": "工业建筑用于生产。"},
        ],
    }
    ctx = _compile_context("建筑分类按使用性质划分。", chunk, "C", span_scoped=False)
    titles = [json.loads(tc)["title"] for tc in ctx.get("teaching_cards") or []]
    assert titles == ["A", "B"]


def test_lecture_lane_does_not_fall_back_to_whole_chunk(tmp_path: Path) -> None:
    """讲义 lane 切不出子段时必须 quarantine, 不回退整 chunk (统一单点规则, 删第二套)。"""
    from scripts.run_luban_rich_leaf_frozen_full_compile import build_frozen_full_compile

    taxonomy = {
        "meta": {"frozen": "taxonomy-frozen-v1-20260612"},
        "stats": {"total_nodes": 2},
        "outline_structure": [
            {
                "code": "1A435000",
                "name": "成本管理",
                "children": [
                    {
                        "code": "1A435000-B009",
                        "name": "纯通用名要求",  # non-discriminative -> slicer abstains
                        "keywords": ["成本"],
                        "source_evidence": [
                            {
                                "chunk_id": None,
                                "page_num": None,
                                "source_file": "讲义/成本单元_v8/page_1_1.json",
                                "source_lane": "lecture",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    lecture_dir = tmp_path / "讲义" / "成本单元_v8"
    lecture_dir.mkdir(parents=True)
    (lecture_dir / "page_1_1.json").write_text(
        json.dumps(
            [{"chunk_id": "LEC1", "content_markdown": "成本控制的混排内容，没有可切的子标题。", "source_meta": {"page_num": 1}}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # A non-empty book file is required (empty book_files -> no_book_chunks_loaded
    # blocker short-circuits before any lane runs).
    book_path = tmp_path / "BOOK_A.json"
    book_path.write_text(
        json.dumps({"content_blocks": [{"chunk_id": "UNUSED", "content_markdown": "占位。"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = build_frozen_full_compile(
        taxonomy=taxonomy, book_files=[book_path], source_root=tmp_path, base_pack=None
    )
    # No whole-chunk fallback unit; the unsliceable lecture leaf is quarantined.
    assert report["summary"]["compiled_unit_count"] == 0
    assert report["summary"]["quarantine_count"] == 1
    assert report["quarantine"][0]["leaf_id"] == "1A435000-B009"
