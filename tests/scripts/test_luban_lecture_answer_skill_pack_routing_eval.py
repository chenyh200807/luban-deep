from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "lecture_routing_eval",
    REPO / "scripts" / "run_luban_lecture_answer_skill_pack_routing_eval.py",
)
lecture_routing_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lecture_routing_eval)


def _write_pack(root: Path) -> Path:
    pack = root / "pack"
    shard_dir = pack / "runtime_supply" / "shards"
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
        "shards": [{"path": "shards/test.json", "topic": "test", "record_count": 3}],
    }
    (pack / "runtime_supply" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return pack


def test_exam_question_has_high_activation_and_quality(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    index = lecture_routing_eval.build_routing_index(pack)

    result = lecture_routing_eval.evaluate_query(index, "模板起拱有哪些陷阱和红线？")

    assert result["activation_band"] == "high"
    assert result["should_activate"] is True
    assert result["quality_band"] == "high"
    assert result["top_units"][0]["unit_id"] == "lecture.main.0001"
    assert result["capability_hits"]["trap_red_line"] is True
    assert result["source_grounded"] is True


def test_off_syllabus_query_does_not_activate(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    index = lecture_routing_eval.build_routing_index(pack)

    result = lecture_routing_eval.evaluate_query(index, "今天天气和股票行情怎么样？")

    assert result["activation_band"] == "none"
    assert result["should_activate"] is False
    assert result["quality_band"] == "not_applicable"
    assert result["association_allowed"] is False


def test_generic_exam_answer_does_not_require_mnemonic(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    index = lecture_routing_eval.build_routing_index(pack)

    result = lecture_routing_eval.evaluate_query(index, "钢筋连接怎么按一建建筑实务考试答？")

    assert result["should_activate"] is True
    assert result["top_units"][0]["unit_id"] == "lecture.main.0002"
    assert result["top_units"][0]["capabilities"]["mnemonic"] is False
    assert result["quality_band"] == "high"


def test_association_is_source_bounded_to_related_lecture_units(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    index = lecture_routing_eval.build_routing_index(pack)

    result = lecture_routing_eval.evaluate_query(index, "学模板起拱时应该联想到主体结构哪些相关考点？")

    assert result["should_activate"] is True
    assert result["association_allowed"] is True
    related_ids = {row["unit_id"] for row in result["related_units"]}
    assert "lecture.main.0002" in related_ids
    assert "lecture.flow.0001" not in related_ids
    assert all(row["source_ref"]["chunk_id"] for row in result["related_units"])
