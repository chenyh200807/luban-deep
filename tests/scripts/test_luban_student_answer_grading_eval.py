from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_luban_student_answer_grading_eval",
    REPO / "scripts" / "run_luban_student_answer_grading_eval.py",
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def test_parse_student_answer_md_extracts_student_answer(tmp_path):
    path = tmp_path / "samples.md"
    path.write_text(
        """# x
### Q2023-03｜项目质量计划

#### 样本元数据

- 样本ID：`Q2023-03__S06`
- 学生ID：`S06`
- ability_label：`low`
- answer_quality_label：`weak`
- 中文标签：基础薄弱
- 预估得分区间：30%-42%

#### 题目

- 年份：2023
- 来源 chunk：`EXAM_1A434000_P0015_01`

【背景资料】背景

【问题】
1. 问题一？

#### 回答

作答：
问题1：学生答案。

#### 本题水平判断

- 学生归类：基础薄弱
""",
        encoding="utf-8",
    )
    samples = mod.parse_student_answer_md(path)
    assert len(samples) == 1
    sample = samples[0]
    assert sample["sample_id"] == "Q2023-03__S06"
    assert sample["student_id"] == "S06"
    assert sample["score_range"] == [30, 42]
    assert sample["source_chunks"] == ["EXAM_1A434000_P0015_01"]
    assert sample["student_answer"].startswith("问题1：学生答案。")


def test_score_range_hit():
    assert mod._score_range_hit(35, [30, 42]) is True
    assert mod._score_range_hit(55, [30, 42]) is False
    assert mod._score_range_hit(None, [30, 42]) is None


def test_normalize_grading_payload_accepts_common_live_model_keys():
    normalized = mod.normalize_grading_payload(
        {
            "score_percentage": 80,
            "points": [{"sub_no": "1", "status": "hit"}],
            "deductions": ["漏答第2问"],
            "error_tags": ["漏列采分点"],
            "learning_evidence": {"weaknesses": ["桩基检测"]},
            "next_action": {"focus": "检测方法"},
            "evidence_refs": ["ref1"],
        }
    )
    assert normalized["score_pct"] == 80
    assert normalized["point_results"] == [{"sub_no": "1", "status": "hit"}]
    assert normalized["deduction_reasons"] == ["漏答第2问"]
    assert normalized["misconception_tags"] == ["漏列采分点"]
    assert normalized["learning_evidence_event"] == {"weaknesses": ["桩基检测"]}
    assert normalized["next_review_action"] == {"focus": "检测方法"}
    assert normalized["citations"] == ["ref1"]


def test_compact_scoring_artifact_is_point_shaped():
    artifact = mod.build_compact_scoring_artifact(
        {
            "source_chunks": ["EXAM_X"],
            "gold_points": [
                {
                    "sub_no": "1",
                    "score": 2.0,
                    "question": "指出不妥。",
                    "gold_answer": "项目质量计划应在项目策划过程中编制。应动态管理。",
                }
            ],
        }
    )
    assert artifact["artifact_schema"] == "compact_scoring_artifact.v1"
    assert artifact["source_chunks"] == ["EXAM_X"]
    assert artifact["points"][0]["sub_no"] == "1"
    assert artifact["points"][0]["expected_points"]
    assert artifact["points"][0]["deduction_shape"]["must_emit_next_action"] is True


def test_parse_arm_list_rejects_unknown_arm():
    assert mod.parse_arm_list("kbv5_clean_grader,runtime_slim_grader") == [
        "kbv5_clean_grader",
        "runtime_slim_grader",
    ]
    try:
        mod.parse_arm_list("missing_arm")
    except ValueError as exc:
        assert "missing_arm" in str(exc)
    else:
        raise AssertionError("unknown arm should fail")


def test_build_gold_reference_for_real_source_chunk():
    sample = {
        "year": 2023,
        "source_chunks": ["EXAM_1A434000_P0015_01"],
    }
    reference = mod.build_gold_reference(sample)
    assert len(reference["gold_points"]) >= 4
    assert any("项目质量计划" in point["gold_answer"] for point in reference["gold_points"])
