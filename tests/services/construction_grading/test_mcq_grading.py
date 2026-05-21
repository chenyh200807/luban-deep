from __future__ import annotations

from deeptutor.services.construction_grading.mcq import grade_mcq_submission


def test_grade_mcq_uses_question_bank_evidence_and_option_reasoning() -> None:
    row = {
        "id": 12233,
        "question_type": "multi_choice",
        "question_stem": "钢结构焊接连接的优点包括哪些？",
        "options": [
            {"key": "A", "value": "节约钢材"},
            {"key": "B", "value": "构造简单"},
            {"key": "C", "value": "自动化作业"},
            {"key": "D", "value": "现场加工灵活"},
            {"key": "E", "value": "焊缝内部缺陷易检查"},
        ],
        "correct_answer": "ABCD",
        "analysis": "【选项分析】E项错误：焊缝内部缺陷难检查，需探伤。",
        "option_reasoning": {
            "A": {"status": "correct", "explanation": "焊接可减少连接件，节省材料"},
            "B": {"status": "correct", "explanation": "焊缝连接构造简单"},
            "C": {"status": "correct", "explanation": "支持自动化焊接"},
            "D": {"status": "correct", "explanation": "现场加工灵活"},
            "E": {
                "status": "wrong",
                "error_type": "fact_error",
                "explanation": "焊缝内部缺陷难检查，需探伤",
            },
        },
        "trap_type": "注意！焊接连接不易检查，必须进行无损检测。",
        "testing_focus": "钢结构焊接连接有哪些优点",
        "grading_keywords": ["焊接", "节约钢材", "构造简单"],
        "node_code": "1A413000",
        "source_meta": {"source": "2017年一级建造师《建筑实务》考试真题及答案解析"},
    }

    result = grade_mcq_submission(row, "ACE")

    assert result.is_correct is False
    assert result.correct_answer == "ABCD"
    assert result.selected_options == ["A", "C", "E"]
    assert result.missed_options == ["B", "D"]
    assert result.extra_options == ["E"]
    assert any(ref.field == "option_reasoning" for ref in result.evidence_refs)
    assert any(event.error_code == "M07" and "E" in event.evidence for event in result.error_events)
    assert any(event.error_code == "M06" and "B" in event.evidence for event in result.error_events)
    assert result.next_training_signal["focus"] == "钢结构焊接连接有哪些优点"


def test_grade_mcq_correct_answer_accepts_json_payload() -> None:
    row = {
        "id": "q1",
        "question_type": "single_choice",
        "options": {"A": "正确", "B": "错误"},
        "correct_answer": ["B"],
        "analysis": "B 正确。",
    }

    result = grade_mcq_submission(row, "B")

    assert result.is_correct is True
    assert result.score_awarded == result.max_score == 1.0
    assert result.error_events == []


# ─────────────────────────────────────────────────────────────────────────────
# Batch D.1 — grade_mcq_submission 优先级：grading_key > questions_bank > llm_judge
# plan §Phase 3 Step 3.4 / §goal Batch D.1
# ─────────────────────────────────────────────────────────────────────────────


def test_grade_choice_prefers_grading_key_over_questions_bank() -> None:
    from deeptutor.services.construction_grading.mcq import grade_mcq_submission

    row = {
        "id": "qb_legacy_1",
        "correct_answer": "C",  # questions_bank 错误答案，应该被 grading_key 覆盖
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
    }
    grading_key = {"correct_answer": "B", "scoring_points": ["p1"]}
    result = grade_mcq_submission(row, user_answer="B", grading_key=grading_key)
    assert result.is_correct is True
    assert result.correct_answer == "B"
    assert result.next_training_signal["grading_source"] == "grading_key"


def test_grade_choice_falls_back_to_questions_bank_when_no_grading_key() -> None:
    from deeptutor.services.construction_grading.mcq import grade_mcq_submission

    row = {
        "id": "qb_legacy_2",
        "correct_answer": "B",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
    }
    result = grade_mcq_submission(row, user_answer="B", grading_key=None)
    assert result.is_correct is True
    assert result.next_training_signal["grading_source"] == "questions_bank"


def test_grade_choice_falls_back_to_llm_judge_when_grading_key_and_bank_absent() -> None:
    from deeptutor.services.construction_grading.mcq import grade_mcq_submission

    row = {"id": "ai_q_1", "options": {"A": "a", "B": "b"}}
    # 既无 grading_key.correct_answer，也无 row.correct_answer
    result = grade_mcq_submission(row, user_answer="A", grading_key=None)
    assert result.is_correct is False
    assert result.next_training_signal["grading_source"] == "llm_judge"
