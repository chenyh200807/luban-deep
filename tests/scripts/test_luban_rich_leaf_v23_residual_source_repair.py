from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_rich_leaf_v23_residual_source_repair import (
    build_v23_residual_source_repair,
)
from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash

STONE_SPAN = (
    "砌体结构中，常用的天然石材为无明显风化的花岗石、砂石和石灰石等。"
    "石材的抗压强度高，耐久性好，多用于房屋基础、勒脚部位。"
    "在有开采加工能力的地区，也可用于房屋的墙体，但是石材传热性高，"
    "用于采暖房屋的墙壁时，厚度需要很大，经济性较差。"
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


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "v2.3_full2026_accounted_shadow_candidate_20260612",
        "classification": _classification(),
        "safety": _safety(),
        "summary": {"leaf_scoped_runtime_unit_count": 2},
        "runtime_token_pack_units": [
            {
                "unit_id": "u_polluted",
                "leaf_id": "1A412014-02",
                "leaf_name_path": "结构工程材料 > 砌体材料的性能与应用 > 石材的性能与应用",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "compiled_context": {"concepts": ["地基基础应满足承载力要求。"]},
                "source_ref": {
                    "record_id": "标准文件/GB55003.json",
                    "source_path": "标准文件/GB55003.json",
                    "source_lane": "textbook",
                    "span_hash": "old",
                    "file_sha256": "old",
                },
                "relative_path": "标准文件/GB55003.json",
                "source_lane": "source_truth",
                "review_source": "deterministic_dedup_margin",
            },
            {
                "unit_id": "u_untouched",
                "leaf_id": "LEAF-OK",
                "leaf_name_path": "其他 > 正常叶子",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "compiled_context": {"concepts": ["正常内容"]},
                "source_ref": {"record_id": "r", "source_path": "r", "source_lane": "textbook", "span_hash": "h"},
            },
        ],
    }


def _work_orders() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_live_residual_work_orders.v1",
        "verdict": "PASS_LIVE_RESIDUAL_WORK_ORDERS_READY",
        "classification": _classification(),
        "safety": _safety(),
        "work_orders": [
            {
                "unit_id": "u_polluted",
                "leaf_id": "1A412014-02",
                "work_order_id": "wo_1",
                "work_order_type": "compiler_feedback_source_or_leaf_recheck",
            }
        ],
    }


def _taxonomy() -> dict:
    return {
        "children": [
            {
                "code": "1A412014",
                "name": "砌体材料的性能与应用",
                "children": [
                    {
                        "code": "1A412014-02",
                        "name": "石材的性能与应用",
                        "keywords": ["天然石材", "抗压强度", "耐久性", "传热性", "基础", "勒脚", "墙体", "经济性"],
                    }
                ],
            },
            {
                "code": "DUP-01",
                "name": "分支甲",
                "children": [{"code": "1A413061-07-d", "name": "屋顶透光部分面积限制", "keywords": ["屋顶透光"]}],
            },
            {
                "code": "DUP-02",
                "name": "分支乙",
                "children": [
                    {
                        "code": "1A413061-07-d",
                        "name": "项目管理信息系统子系统",
                        "keywords": ["成本管理", "进度管理"],
                    }
                ],
            },
        ]
    }


def _chunk_file(tmp_path: Path) -> Path:
    book = {
        "meta": {},
        "content_blocks": [
            {
                "chunk_id": "1A412010_051_0092",
                "source_meta": {"page_num": 51, "file_path": "教材.pdf"},
                "taxonomy": {"node_code": "1A412010", "topic": "石材"},
                "content_markdown": "### 石材\n\n" + STONE_SPAN,
                "knowledge_cards": [
                    {
                        "card_title": "石材特性与应用",
                        "card_content": "天然石材抗压强度高、耐久性好，常用于基础、勒脚；但传热性高，经济性差。",
                    }
                ],
                "assessment": {
                    "generated_question": "下列关于石材的说法错误的是？",
                    "grading_keywords": ["抗压强度高", "耐久性好", "传热性高", "经济性差"],
                },
            }
        ],
    }
    path = tmp_path / "book.json"
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return path


def _manifest(tmp_path: Path) -> dict:
    return {
        "schema": "luban_rich_leaf_v23_residual_repair_manifest.v1",
        "classification": _classification(),
        "repair_candidates": [
            {
                "unit_id": "u_polluted",
                "leaf_id": "1A412014-02",
                "leaf_name": "石材的性能与应用",
                "chunk_file": str(_chunk_file(tmp_path)),
                "chunk_id": "1A412010_051_0092",
                "source_relative_path": "2026教材/第二次加强/book.json",
                "span_text": STONE_SPAN,
                "investigation_note": "GB55003 地基基础 span 为 linker 非判别关键词误链。",
            }
        ],
    }


def test_repair_applies_quote_grounded_context(tmp_path: Path) -> None:
    pack = _runtime_token_pack()
    report = build_v23_residual_source_repair(
        runtime_token_pack=pack,
        work_orders=_work_orders(),
        manifest=_manifest(tmp_path),
        taxonomy=_taxonomy(),
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "PASS_V23_RESIDUAL_SOURCE_REPAIR_CANDIDATES"
    assert report["blockers"] == []
    patched = report["patched_runtime_token_pack"]
    assert patched["schema"] == "luban_rich_leaf_runtime_token_pack.v2.3"
    assert patched["status"] == "candidate_ready_for_shadow_ab_full_accounted"
    assert patched["version"] != pack["version"]
    assert patched["classification"]["residual_repair_patch"] is True
    unit = next(u for u in patched["runtime_token_pack_units"] if u["unit_id"] == "u_polluted")
    assert "石材" in json.dumps(unit["compiled_context"], ensure_ascii=False)
    assert "地基基础" not in json.dumps(unit["compiled_context"], ensure_ascii=False)
    assert unit["source_ref"]["span_hash"] == source_span_hash(STONE_SPAN)
    assert unit["source_ref"]["chunk_id"] == "1A412010_051_0092"
    assert unit["review_source"] == "residual_source_repair_candidate"
    assert unit["candidate_only"] is True
    assert unit["runtime_install_allowed"] is False
    # 输入 pack 不可变
    assert pack["runtime_token_pack_units"][0]["source_ref"]["span_hash"] == "old"
    untouched = next(u for u in patched["runtime_token_pack_units"] if u["unit_id"] == "u_untouched")
    assert untouched["compiled_context"] == {"concepts": ["正常内容"]}


def test_repair_fail_closed_on_low_keyword_overlap(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    taxonomy = _taxonomy()
    taxonomy["children"][0]["children"][0]["keywords"] = ["完全无关甲", "完全无关乙", "完全无关丙"]
    report = build_v23_residual_source_repair(
        runtime_token_pack=_runtime_token_pack(),
        work_orders=_work_orders(),
        manifest=manifest,
        taxonomy=taxonomy,
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "BLOCKED_V23_RESIDUAL_SOURCE_REPAIR"
    assert any("keyword_overlap_below_threshold" in b for b in report["blockers"])
    assert report.get("patched_runtime_token_pack") is None


def test_repair_fail_closed_on_span_not_in_chunk(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["repair_candidates"][0]["span_text"] = "这段话不在 chunk 里。"
    report = build_v23_residual_source_repair(
        runtime_token_pack=_runtime_token_pack(),
        work_orders=_work_orders(),
        manifest=manifest,
        taxonomy=_taxonomy(),
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "BLOCKED_V23_RESIDUAL_SOURCE_REPAIR"
    assert any("span_text_not_found_in_chunk" in b for b in report["blockers"])


def test_repair_rejects_unit_not_in_work_orders(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["repair_candidates"][0]["unit_id"] = "u_untouched"
    manifest["repair_candidates"][0]["leaf_id"] = "LEAF-OK"
    report = build_v23_residual_source_repair(
        runtime_token_pack=_runtime_token_pack(),
        work_orders=_work_orders(),
        manifest=manifest,
        taxonomy=_taxonomy(),
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "BLOCKED_V23_RESIDUAL_SOURCE_REPAIR"
    assert any("unit_not_named_by_residual_work_orders" in b for b in report["blockers"])


def test_repair_emits_taxonomy_duplicate_code_work_order(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    chunk_file = manifest["repair_candidates"][0]["chunk_file"]
    pack = _runtime_token_pack()
    pack["runtime_token_pack_units"][0]["leaf_id"] = "1A413061-07-d"
    pack["runtime_token_pack_units"][0]["leaf_name_path"] = "分支乙 > 项目管理信息系统子系统"
    work_orders = _work_orders()
    work_orders["work_orders"][0]["leaf_id"] = "1A413061-07-d"
    book = json.loads(Path(chunk_file).read_text(encoding="utf-8"))
    book["content_blocks"][0]["content_markdown"] = "项目管理信息系统包括成本管理、进度管理子系统。"
    Path(chunk_file).write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    manifest["repair_candidates"][0].update(
        {
            "leaf_id": "1A413061-07-d",
            "leaf_name": "项目管理信息系统子系统",
            "span_text": "项目管理信息系统包括成本管理、进度管理子系统。",
        }
    )
    report = build_v23_residual_source_repair(
        runtime_token_pack=pack,
        work_orders=work_orders,
        manifest=manifest,
        taxonomy=_taxonomy(),
        min_keyword_overlap=0.6,
    )
    assert report["verdict"] == "PASS_V23_RESIDUAL_SOURCE_REPAIR_CANDIDATES"
    dup_orders = [w for w in report["follow_up_work_orders"] if w["work_order_type"] == "taxonomy_duplicate_code"]
    assert len(dup_orders) == 1
    assert dup_orders[0]["leaf_id"] == "1A413061-07-d"
    assert sorted(dup_orders[0]["conflicting_leaf_names"]) == ["屋顶透光部分面积限制", "项目管理信息系统子系统"]


def test_repair_preserves_safety_invariants(tmp_path: Path) -> None:
    report = build_v23_residual_source_repair(
        runtime_token_pack=_runtime_token_pack(),
        work_orders=_work_orders(),
        manifest=_manifest(tmp_path),
        taxonomy=_taxonomy(),
        min_keyword_overlap=0.6,
    )
    for payload in (report, report["patched_runtime_token_pack"]):
        assert payload["classification"]["candidate_only"] is True
        assert payload["classification"]["review_only"] is True
        assert payload["classification"]["runtime_install_allowed"] is False
        assert payload["classification"]["production_default"] is False
        assert payload["classification"]["release_truth_claimed"] is False
        assert payload["safety"]["production_write_count"] == 0
        assert payload["safety"]["canonical_truth_written"] is False
        assert payload["safety"]["official_score_allowed"] is False
    assert report["quality_claim_allowed"] is False
    assert "production_rag_runtime" in report["not_exercised"]
