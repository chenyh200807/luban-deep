from __future__ import annotations

from deeptutor.services.source_compiler.answer_rubric_extractor import (
    compile_answer_derived_rubric_candidate,
    iter_case_study_answer_records,
)


def test_iter_case_study_records_reads_nested_exam_exercises() -> None:
    payload = {
        "chunks": [
            {
                "chunk_id": "chunk1",
                "taxonomy": {"node_code": "1A413000"},
                "source_meta": {"exam_year": 2022},
                "exercises": [
                    {"type": "single_choice", "question_data": {"stem": "choice"}},
                    {
                        "type": "case_study",
                        "predicted_node": "1A413050",
                        "question_data": {
                            "stem": "case stem",
                            "correct_answer": "A: 限制；B: 禁止",
                            "score": 2,
                        },
                    },
                ],
            }
        ]
    }

    records = iter_case_study_answer_records(payload, source_path="题库/a.json")

    assert len(records) == 1
    assert records[0]["node_code"] == "1A413050"
    assert records[0]["exam_year"] == 2022
    assert records[0]["source_index"] == "0.1"


def test_answer_rubric_extractor_splits_explicit_subquestion_scores() -> None:
    row = {
        "question_type": "case_study",
        "source_chunk_id": "chunk1",
        "source_index": "0.0",
        "node_code": "1A413050",
        "stem": "案例题",
        "score": 5,
        "correct_answer": (
            "【参考答案】\n"
            "1. (本小题5.0分)\n"
            "(1) 还包括：复打法、反插法。（2.0分）\n"
            "(2) 还包括的内容：\n"
            "① 边锤击边拔管，并继续浇筑混凝土；（1.0分）\n"
            "② 下钢筋笼，继续浇筑混凝土及拔管；（1.0分）\n"
            "③ 成桩。（1.0分）"
        ),
    }

    candidate = compile_answer_derived_rubric_candidate(
        row,
        run_id="pytest",
        source_path="题库/a.json",
        compiled_at="now",
    )

    assert candidate is not None
    assert candidate["point_count"] == 4
    assert [point["max_score"] for point in candidate["scoring_points"]] == [2.0, 1.0, 1.0, 1.0]
    assert candidate["overall_confidence"] == "A-"
    assert candidate["writeback_policy"] == "shadow_only_review_required"


def test_answer_rubric_extractor_splits_blank_fill_answer_with_equal_score() -> None:
    row = {
        "question_type": "case_study",
        "source_chunk_id": "chunk1",
        "source_index": "0.0",
        "score": 3,
        "correct_answer": "A: 限制；B: 禁止；C: 不得用于25米及以上的建设工程",
    }

    candidate = compile_answer_derived_rubric_candidate(
        row,
        run_id="pytest",
        source_path="题库/a.json",
        compiled_at="now",
    )

    assert candidate is not None
    assert candidate["point_count"] == 3
    assert [point["match_type"] for point in candidate["scoring_points"]] == ["blank_fill", "blank_fill", "blank_fill"]
    assert [point["max_score"] for point in candidate["scoring_points"]] == [1.0, 1.0, 1.0]
    assert candidate["overall_confidence"] == "A-"
