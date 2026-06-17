from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.compiled_knowledge import lecture_answer_methods as lam


def _write_pack(root: Path) -> Path:
    pack = root / "pack"
    shard_dir = pack / "shards"
    shard_dir.mkdir(parents=True)
    shard = {
        "manifest": {
            "namespace": "lecture_answer_method.test",
            "content_hash": "fake",
            "answer_unit_count": 3,
        },
        "answer_units": [
            {
                "unit_id": "lecture.main.0001",
                "lecture": "主体结构",
                "lecture_slug": "main-structure",
                "topic": "模板工程",
                "question_patterns": ["模板起拱", "跨度不小于4m"],
                "source_excerpt": "跨度不小于4m的梁板模板应起拱。",
                "source_ref": {"source_chunk_id": "LEC_MAIN_P0001_001", "json_page_num": 5},
                "taxonomy": {"node_code": "1A415000", "node_name": "模板工程", "topic": "主体结构"},
                "answer_method": {
                    "must_mentions": ["跨度不小于4m", "起拱"],
                    "red_lines": ["后浇带模板及支架应独立设置"],
                    "trap_alerts": ["不要把模板起拱和拆模条件混答"],
                    "mnemonics": ["先跨度后起拱"],
                    "formula_or_thresholds": ["跨度不小于4m"],
                },
            },
            {
                "unit_id": "lecture.main.0002",
                "lecture": "主体结构",
                "lecture_slug": "main-structure",
                "topic": "钢筋工程",
                "question_patterns": ["钢筋连接", "钢筋隐蔽验收"],
                "source_excerpt": "钢筋隐蔽验收应检查连接方式和位置。",
                "source_ref": {"source_chunk_id": "LEC_MAIN_P0002_001", "json_page_num": 6},
                "taxonomy": {"node_code": "1A415000", "node_name": "钢筋工程", "topic": "主体结构"},
                "answer_method": {
                    "must_mentions": ["连接方式", "位置"],
                    "red_lines": ["隐蔽前必须验收"],
                    "trap_alerts": ["不要漏写隐蔽验收"],
                    "mnemonics": [],
                    "formula_or_thresholds": [],
                },
            },
            {
                "unit_id": "lecture.flow.0001",
                "lecture": "流水施工&网络计划",
                "lecture_slug": "schedule-network",
                "topic": "无节奏流水",
                "question_patterns": ["无节奏流水施工工期计算"],
                "source_excerpt": "无节奏流水施工常用累加数列错位相减取大差法。",
                "source_ref": {"source_chunk_id": "LEC_FLOW_P0001_001", "json_page_num": 7},
                "taxonomy": {"node_code": "1A420000", "node_name": "流水施工", "topic": "进度管理"},
                "answer_method": {
                    "must_mentions": ["累加数列", "错位相减", "取大差"],
                    "red_lines": [],
                    "trap_alerts": ["不要直接相加各施工过程持续时间"],
                    "mnemonics": ["累错取大"],
                    "formula_or_thresholds": [],
                },
            },
        ],
    }
    (shard_dir / "test.json").write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "schema_version": "luban_lecture_answer_skill_pack.v1",
        "scope": "all_lecture_release_candidate",
        "status": "release_candidate",
        "published": False,
        "shards": [{"path": "shards/test.json", "topic": "test", "record_count": 3}],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return pack


def test_resolves_exam_answer_method_context_with_citations(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path)

    pack = lam.resolve_lecture_answer_method_context(
        "模板起拱有哪些陷阱和红线？",
        pack_root=pack_root,
    )

    assert pack is not None
    assert pack["authority"] == "luban_lecture_answer_method_context"
    assert pack["tier"] == "teaching_answer_method_not_answer_key"
    assert pack["official_score_allowed"] is False
    assert pack["activation"]["band"] == "high"
    assert pack["selected_units"][0]["unit_id"] == "lecture.main.0001"
    assert [unit["unit_id"] for unit in pack["selected_units"]] == ["lecture.main.0001"]
    assert pack["selected_units"][0]["source_ref"] == {
        "chunk_id": "LEC_MAIN_P0001_001",
        "json_page_num": 5,
    }


def test_off_syllabus_falls_open(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path)

    assert lam.resolve_lecture_answer_method_context("今天天气和股票行情怎么样？", pack_root=pack_root) is None


def test_association_stays_source_bounded(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path)

    pack = lam.resolve_lecture_answer_method_context(
        "学模板起拱时应该联想到主体结构哪些相关考点？",
        pack_root=pack_root,
    )

    assert pack is not None
    assert pack["association"]["allowed"] is True
    related_ids = {row["unit_id"] for row in pack["association"]["related_units"]}
    assert "lecture.main.0002" in related_ids
    assert "lecture.flow.0001" not in related_ids


def test_grounding_renders_exam_method_without_ads(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path)
    pack = lam.resolve_lecture_answer_method_context("模板起拱怎么按考试答？", pack_root=pack_root)

    grounding = lam.format_lecture_answer_method_grounding(pack)

    assert "【讲义答题方法" in grounding
    assert "json_page_num=5" in grounding
    assert "chunk_id=LEC_MAIN_P0001_001" in grounding
    assert "跨度不小于4m" in grounding
    assert "小佑题库" not in grounding


def test_default_all8_bundle_resolves_short_core_exam_term() -> None:
    pack = lam.resolve_lecture_answer_method_context("模板起拱有哪些陷阱和红线？")

    assert pack is not None
    assert pack["activation"]["band"] == "high"
    assert pack["selected_units"][0]["lecture"] == "主体结构"
    assert pack["selected_units"][0]["source_ref"]["chunk_id"]
