from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "lecture_ab",
    REPO / "scripts" / "run_luban_lecture_answer_skill_pack_ab_eval.py",
)
lecture_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lecture_ab)


def _write_pack(root: Path) -> Path:
    pack = root / "pack"
    shard_dir = pack / "runtime_supply" / "shards"
    shard_dir.mkdir(parents=True)
    shard = {
        "manifest": {
            "namespace": "lecture_answer_method.test",
            "content_hash": "fake",
            "answer_unit_count": 2,
        },
        "answer_units": [
            {
                "unit_id": "lecture.test.0001",
                "lecture": "主体结构",
                "topic": "模板工程",
                "question_patterns": ["模板起拱"],
                "source_excerpt": "跨度不小于4m的梁板模板应起拱。",
                "source_ref": {
                    "source_chunk_id": "LEC_TEST_P0001_001",
                    "json_page_num": 5,
                },
                "answer_method": {
                    "must_mentions": ["跨度不小于4m", "起拱"],
                    "red_lines": ["后浇带模板及支架应独立设置"],
                    "trap_alerts": ["不要把模板起拱和拆模条件混答"],
                    "mnemonics": ["先跨度后起拱"],
                    "formula_or_thresholds": ["跨度不小于4m"],
                },
            },
            {
                "unit_id": "lecture.test.0002",
                "lecture": "流水施工",
                "topic": "无节奏流水",
                "question_patterns": ["无节奏流水施工工期计算"],
                "source_excerpt": "无节奏流水施工常用累加数列错位相减取大差法。",
                "source_ref": {
                    "source_chunk_id": "LEC_TEST_P0002_001",
                    "json_page_num": 6,
                },
                "answer_method": {
                    "must_mentions": ["累加数列", "错位相减", "取大差"],
                    "red_lines": [],
                    "trap_alerts": ["不要直接相加各施工过程持续时间"],
                    "mnemonics": ["累错取大"],
                    "formula_or_thresholds": [],
                },
            },
        ],
        "non_exam_exclusions": [],
    }
    (shard_dir / "test.json").write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "schema_version": "luban_lecture_answer_skill_pack.v1",
        "shards": [{"path": "shards/test.json", "topic": "test", "record_count": 2}],
    }
    (pack / "runtime_supply" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return pack


def test_ab_eval_scores_skill_pack_above_raw_baseline(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    out = tmp_path / "out"

    result = lecture_ab.run_eval(pack_root=pack, out_dir=out, max_cases=20)

    assert result["case_count"] == 2
    assert result["winner"] == "answer_skill_pack"
    assert result["arms"]["answer_skill_pack"]["avg_score"] > result["arms"]["raw_json_baseline"]["avg_score"]
    assert result["delta"]["avg_score"] > 0
    assert (out / "ab_eval_result.json").exists()
    assert (out / "AB_FINDING.md").exists()


def test_ab_eval_fails_if_ads_leak_into_answer(tmp_path: Path) -> None:
    unit = {
        "unit_id": "lecture.test.0003",
        "lecture": "主体结构",
        "topic": "广告污染",
        "question_patterns": ["广告污染"],
        "source_excerpt": "小佑题库 佑森在线 官方企微",
        "source_ref": {"source_chunk_id": "LEC_AD", "json_page_num": 99},
        "answer_method": {
            "must_mentions": [],
            "red_lines": [],
            "trap_alerts": [],
            "mnemonics": [],
            "formula_or_thresholds": [],
        },
    }

    answer = lecture_ab.render_raw_answer(unit)
    score = lecture_ab.score_answer(unit, answer)

    assert score["ad_pollution"] == 1
    assert score["score"] < 1.0
