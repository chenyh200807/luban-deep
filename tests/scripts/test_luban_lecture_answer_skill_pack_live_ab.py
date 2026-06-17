from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "lecture_live_ab",
    REPO / "scripts" / "run_luban_lecture_answer_skill_pack_live_ab.py",
)
lecture_live_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lecture_live_ab)


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


def test_live_ab_prompt_package_is_blinded_and_ad_clean(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    out = tmp_path / "out"

    result = lecture_live_ab.run_live_ab(
        pack_root=pack,
        out_dir=out,
        max_cases=2,
        run_live=False,
        provider_name="stub",
        env={},
        seed=11,
    )

    prompts = [
        json.loads(line)
        for line in (out / "prompt_package.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert result["mode"] == "deterministic_stub"
    assert len(prompts) == 4
    assert all("arm" not in row for row in prompts)
    assert all("raw_json_baseline" not in row["prompt"] for row in prompts)
    assert all("answer_skill_pack" not in row["prompt"] for row in prompts)
    assert all(not any(term in row["prompt"] for term in lecture_live_ab.AD_TERMS) for row in prompts)


def test_live_ab_live_mode_without_provider_key_fails_closed(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    out = tmp_path / "out"

    result = lecture_live_ab.run_live_ab(
        pack_root=pack,
        out_dir=out,
        max_cases=2,
        run_live=True,
        provider_name="deepseek",
        env={},
        seed=11,
    )

    assert result["verdict"] == "PROVIDER_UNAVAILABLE_NO_GO"
    assert result["provider_unavailable"] is True
    assert result["provider_call_count"] == 0
    assert (out / "prompt_package.jsonl").exists()
    assert (out / "LIVE_AB_FINDING.md").exists()


def test_live_ab_stub_scores_compiled_context_above_raw_context(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    out = tmp_path / "out"

    result = lecture_live_ab.run_live_ab(
        pack_root=pack,
        out_dir=out,
        max_cases=2,
        run_live=False,
        provider_name="stub",
        env={},
        seed=11,
    )

    assert result["winner"] == "answer_skill_pack"
    assert result["wins"]["answer_skill_pack"] >= 1
    assert result["arms"]["answer_skill_pack"]["avg_score"] > result["arms"]["raw_json_baseline"]["avg_score"]
    assert result["arms"]["answer_skill_pack"]["citation_rate"] == 1.0
    assert result["arms"]["raw_json_baseline"]["citation_rate"] == 1.0
    assert result["live_claim_allowed"] is False
    assert (out / "model_answers.jsonl").exists()
    assert (out / "judge_scores.jsonl").exists()
