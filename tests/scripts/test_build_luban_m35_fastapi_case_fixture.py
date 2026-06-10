import json
import subprocess
from pathlib import Path


SCRIPT = "scripts/build_luban_m35_fastapi_case_fixture.py"


def test_builds_fixture_from_student_arranged_markdown(tmp_path):
    source = tmp_path / "cases.md"
    source.write_text(
        """# cases

## 按学生分卷

## 学生01｜满分型｜高水平｜预估 92%-100%

### Q2023-01｜质量检测

#### 样本元数据

- 样本ID：`Q2023-01__S01`
- 学生ID：`S01`
- ability_label：`high`
- answer_quality_label：`excellent`
- 预估得分区间：92%-100%

#### 题目

- 年份：2023
- 来源 chunk：`EXAM_A`

【背景资料】题干一。

【问题】
1. 问题一？

#### 回答

作答：
问题1：答案一。

#### 本题水平判断

---

### Q2023-02｜网络计划

#### 样本元数据

- 样本ID：`Q2023-02__S01`
- 学生ID：`S01`
- ability_label：`high`
- answer_quality_label：`excellent`
- 预估得分区间：92%-100%

#### 题目

- 年份：2023
- 来源 chunk：`EXAM_B`

【背景资料】题干二。

【问题】
1. 问题二？

#### 回答

作答：
问题1：答案二。

#### 本题水平判断

---

## 学生02｜高分型｜高水平｜预估 82%-90%

### Q2023-01｜质量检测

#### 样本元数据

- 样本ID：`Q2023-01__S02`
- 学生ID：`S02`
- ability_label：`high`
- answer_quality_label：`good`
- 预估得分区间：82%-90%

#### 题目

- 年份：2023
- 来源 chunk：`EXAM_A`

【背景资料】题干一。

【问题】
1. 问题一？

#### 回答

作答：
问题1：学生二答案一。

#### 本题水平判断

---
""",
        encoding="utf-8",
    )
    output = tmp_path / "fixture"

    subprocess.run(
        [
            "python",
            SCRIPT,
            "--source",
            str(source),
            "--output-dir",
            str(output),
            "--target-question-count",
            "20",
            "--target-answer-count",
            "100",
        ],
        check=True,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (output / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert manifest["schema_version"] == "luban_m35_fastapi_case_fixture.v1"
    assert manifest["source_status"] == "SOURCE_LIMIT"
    assert manifest["requested_question_count"] == 20
    assert manifest["actual_question_count"] == 2
    assert manifest["actual_answer_count"] == 3
    assert [question["question_id"] for question in manifest["questions"]] == [
        "Q2023-01",
        "Q2023-02",
    ]
    assert rows[0]["answer_id"] == "Q2023-01__S01"
    assert rows[0]["question_id"] == "Q2023-01"
    assert rows[0]["label_authority"] == "estimated_metadata_only"
    assert rows[0]["gold_score"] is None
    assert "答案一" in rows[0]["student_answer"]


def test_can_split_case_into_subquestion_level_fixture(tmp_path):
    source = tmp_path / "cases.md"
    source.write_text(
        """# cases

## 学生01｜满分型｜高水平｜预估 92%-100%

### Q2023-01｜质量检测

#### 样本元数据

- 样本ID：`Q2023-01__S01`
- 学生ID：`S01`
- ability_label：`high`
- answer_quality_label：`excellent`
- 预估得分区间：92%-100%

#### 题目

【背景资料】共同背景。

【问题】
1. 指出不妥之一。
2. 写出正确做法。

#### 回答

作答：
问题1：不妥是甲。
问题2：正确做法是乙。

#### 本题水平判断

---
""",
        encoding="utf-8",
    )
    output = tmp_path / "fixture"

    subprocess.run(
        [
            "python",
            SCRIPT,
            "--source",
            str(source),
            "--output-dir",
            str(output),
            "--target-question-count",
            "2",
            "--target-answer-count",
            "2",
            "--split-subquestions",
        ],
        check=True,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (output / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert manifest["source_status"] == "OK"
    assert [question["question_id"] for question in manifest["questions"]] == [
        "Q2023-01__P01",
        "Q2023-01__P02",
    ]
    assert "共同背景" in manifest["questions"][0]["stem"]
    assert "指出不妥之一" in manifest["questions"][0]["stem"]
    assert rows[0]["answer_id"] == "Q2023-01__P01__S01"
    assert rows[0]["student_answer"] == "不妥是甲。"
    assert rows[1]["student_answer"] == "正确做法是乙。"
