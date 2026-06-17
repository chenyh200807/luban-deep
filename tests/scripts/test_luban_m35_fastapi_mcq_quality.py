import json
import subprocess


SCRIPT = "scripts/run_luban_m35_fastapi_mcq_quality.py"


def test_mcq_quality_replays_official_key_variants(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "manifest.json").write_text(
        json.dumps(
            {
                "source": "official-json",
                "actual_question_count": 1,
                "label_authority": "generated_from_official_mcq_key",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "answer_id": "Q1__correct",
            "question_id": "Q1",
            "student_answer": "BE",
            "variant": "correct",
            "gold_score": 2.0,
            "correct_answer": "BE",
            "scoring_points": [
                {"point_id": "OPT_B", "max_score": 1.0},
                {"point_id": "OPT_E", "max_score": 1.0},
            ],
            "scoring_protocol": {"correct_answer": "BE", "wrong_options": ["A", "C", "D"]},
        },
        {
            "answer_id": "Q1__missing_one",
            "question_id": "Q1",
            "student_answer": "B",
            "variant": "missing_one",
            "gold_score": 0.5,
            "correct_answer": "BE",
            "scoring_points": [
                {"point_id": "OPT_B", "max_score": 1.0},
                {"point_id": "OPT_E", "max_score": 1.0},
            ],
            "scoring_protocol": {
                "correct_answer": "BE",
                "wrong_options": ["A", "C", "D"],
                "partial_credit_per_selected_correct_option": 0.5,
            },
        },
        {
            "answer_id": "Q1__overselect",
            "question_id": "Q1",
            "student_answer": "ABE",
            "variant": "overselect",
            "gold_score": 0.0,
            "correct_answer": "BE",
            "scoring_points": [
                {"point_id": "OPT_B", "max_score": 1.0},
                {"point_id": "OPT_E", "max_score": 1.0},
            ],
            "scoring_protocol": {"correct_answer": "BE", "wrong_options": ["A", "C", "D"]},
        },
    ]
    (fixture / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    subprocess.run(["python", SCRIPT, "--fixture", str(fixture), "--output", str(output)], check=True)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metrics"]["exact_score_accuracy"] == 1.0
    assert payload["metrics"]["score_mae"] == 0.0
    assert payload["metrics"]["mismatch_count"] == 0
    assert payload["authority"]["quality_claim_allowed"] is True
    assert payload["authority"]["official_score_allowed"] is False
    assert payload["safety"]["provider_call_count"] == 0
