import json
import subprocess
from pathlib import Path


SCRIPT = "scripts/build_luban_m35_fastapi_mcq_fixture.py"


def test_builds_multiselect_fixture_with_answer_variants(tmp_path):
    source_dir = tmp_path / "题库"
    year_dir = source_dir / "2025年一级建造师《建筑实务》考试真题及答案解析"
    year_dir.mkdir(parents=True)
    payload = {
        "chunks": [
            {
                "chunk_id": "C1",
                "content_type": "exercise",
                "exercises": [
                    {
                        "type": "multiple_choice",
                        "question_data": {
                            "stem": "关于钢化玻璃特性的说法，正确的有(  )。\nA. 可切割\nB. 可自爆\nC. 碎后易伤人\nD. 热稳定性差\nE. 机械强度高",
                            "options": [
                                {"key": "A", "value": "可切割"},
                                {"key": "B", "value": "可自爆"},
                                {"key": "C", "value": "碎后易伤人"},
                                {"key": "D", "value": "热稳定性差"},
                                {"key": "E", "value": "机械强度高"},
                            ],
                            "correct_answer": "BE",
                            "analysis": "钢化玻璃机械强度高，可发生自爆。",
                            "score": 2.0,
                        },
                    }
                ],
            }
        ]
    }
    (year_dir / "FINAL_CLEANED_EXAM_V2025.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "fixture"

    subprocess.run(
        [
            "python",
            SCRIPT,
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output),
            "--target-question-count",
            "1",
        ],
        check=True,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (output / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert manifest["schema_version"] == "luban_m35_fastapi_mcq_fixture.v1"
    assert manifest["source_status"] == "OK"
    assert manifest["actual_question_count"] == 1
    assert manifest["actual_answer_count"] == 5
    assert manifest["questions"][0]["question_id"] == "MCQ-2025-C1-001"
    assert rows[0]["answer_id"] == "MCQ-2025-C1-001__correct"
    assert rows[0]["student_answer"] == "BE"
    assert rows[0]["gold_score"] == 2.0
    assert rows[1]["variant"] == "missing_one"
    assert rows[1]["label_authority"] == "generated_from_official_mcq_key"
