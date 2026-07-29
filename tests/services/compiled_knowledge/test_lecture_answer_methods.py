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


# --------------------------------------------------------------------------------------
# 路由锚收权(2026-07-29 生产事故回归): 数字碎片与答案内容不得建立激活
# --------------------------------------------------------------------------------------
def _write_polluted_pack(root: Path) -> Path:
    """复刻生产污染形状: 编译器把 must_mentions 的数值碎片泄进 question_patterns。"""
    pack = root / "pack"
    shard_dir = pack / "shards"
    shard_dir.mkdir(parents=True)
    shard = {
        "answer_units": [
            {
                "unit_id": "lecture.survey.0001",
                "lecture": "第三章",
                "lecture_slug": "chapter-3",
                "topic": "变形监测点设置要求",
                "question_patterns": ["变形监测点设置要求", "闭合环", "20m", "3个", "15m"],
                "source_excerpt": "变形监测点应布置在闭合环及受力较大处。",
                "source_ref": {"source_chunk_id": "LEC_1A413010_P0007_001", "json_page_num": 7},
                "taxonomy": {"node_code": "1A413010", "node_name": "施工测量", "topic": "施工测量"},
                "answer_method": {
                    "must_mentions": ["闭合环", "20m", "3个", "15m"],
                    "red_lines": [],
                    "trap_alerts": [],
                    "mnemonics": [],
                    "formula_or_thresholds": ["≥3个观测点"],
                },
            },
        ],
    }
    (shard_dir / "test.json").write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "schema_version": "luban_lecture_answer_skill_pack.v1",
        "shards": [{"path": "shards/test.json", "topic": "test", "record_count": 1}],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return pack


def test_numeric_fragment_tokens_never_activate_unit(tmp_path: Path) -> None:
    """生产事故 unified_1785314628533_23c29374: 题面流速 2.0m/s/1.5m/s 归一化后包含
    "20m"/"15m"，撞上变形监测讲义泄漏进 question_patterns 的阈值碎片，把无关讲义以
    high 档注入临时用水案例题。数字/单位碎片(无≥2汉字)不得参与路由。"""

    pack_root = _write_polluted_pack(tmp_path)
    query = (
        "在对现场临时用水管理检查时发现，主供水管实测水流速度1.5 m/s，达不到设计流速2.0m/s，"
        "满足不了设计总用水量的要求。计算更换主供水管的直径。"
    )

    assert lam.resolve_lecture_answer_method_context(query, pack_root=pack_root) is None


def test_answer_content_tokens_cannot_establish_activation(tmp_path: Path) -> None:
    """锚门: 只命中 must_mentions(答案内容)而无任何考点级锚时，不得激活——内容字段
    只能细化已锚定的匹配，不能建立匹配。"""

    pack_root = _write_pack(tmp_path)
    # 只含 must_mentions 词("连接方式"/"位置")，不含任何 lecture/topic/pattern 锚。
    assert (
        lam.resolve_lecture_answer_method_context("连接方式和位置怎么写？", pack_root=pack_root)
        is None
    )


def test_anchored_unit_still_activates_with_detail_refinement(tmp_path: Path) -> None:
    """对照: 锚(题型模式)命中后激活照常，且 detail token 命中确实加分——
    带 detail 短语的查询分数必须严格高于纯锚查询(防止 detail 求和被静默删除)。"""

    pack_root = _write_polluted_pack(tmp_path)
    idx = lam._load_index(pack_root)
    assert idx is not None
    unit = idx["units"][0]
    anchor_q = "变形监测点设置要求怎么答？"
    detail_q = "变形监测点设置要求怎么答？是不是≥3个观测点？"
    base = lam._unit_score(lam._norm(anchor_q), unit, lam._query_intents(anchor_q))
    refined = lam._unit_score(lam._norm(detail_q), unit, lam._query_intents(detail_q))
    assert base > 0
    assert refined > base

    pack = lam.resolve_lecture_answer_method_context(anchor_q, pack_root=pack_root)
    assert pack is not None
    assert pack["selected_units"][0]["unit_id"] == "lecture.survey.0001"


def test_generic_two_char_anchor_cannot_lift_unit_into_selection(tmp_path: Path) -> None:
    """Review B1 回归: 编译器把参与方枚举("设计")泄进 question_patterns 时，
    含"设计+计算"的案例题面不得把该 unit 抬过 0.34 入选线掺进注入 payload。"""

    pack = tmp_path / "pack"
    shard_dir = pack / "shards"
    shard_dir.mkdir(parents=True)
    shard = {
        "answer_units": [
            {
                "unit_id": "lecture.pit.0001",
                "lecture": "地基基础",
                "lecture_slug": "foundation",
                "topic": "基坑验槽程序与内容",
                "question_patterns": ["基坑验槽", "设计"],
                "source_excerpt": "验槽应由建设、勘察、设计、施工、监理共同进行。",
                "source_ref": {"source_chunk_id": "LEC_PIT_P0001_001", "json_page_num": 3},
                "taxonomy": {"node_code": "1A414000", "node_name": "地基基础", "topic": "地基基础"},
                "answer_method": {
                    "must_mentions": ["共同验槽"],
                    "red_lines": [],
                    "trap_alerts": [],
                    "mnemonics": [],
                    "formula_or_thresholds": ["承载力检验"],
                },
            },
        ],
    }
    (shard_dir / "test.json").write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "schema_version": "luban_lecture_answer_skill_pack.v1",
        "shards": [{"path": "shards/test.json", "topic": "test", "record_count": 1}],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    query = "主供水管达不到设计流速，计算更换主供水管的直径。"
    assert lam.resolve_lecture_answer_method_context(query, pack_root=pack) is None
    # 对照: 真正问基坑验槽时照常激活。
    assert lam.resolve_lecture_answer_method_context("基坑验槽程序有哪些？", pack_root=pack) is not None
