from __future__ import annotations

from deeptutor.capabilities.deep_question import _render_deterministic_reference_feedback


def _wall_context(**overrides):
    context = {
        "question_id": "q_wall",
        "question": "地下连续墙施工质量控制，下列说法正确的有？",
        "question_type": "choice",
        "options": {
            "A": "槽段长度8-10m",
            "B": "导墙高度1.0m",
            "C": "现浇钢筋混凝土导墙",
            "D": "导管法连续浇筑混凝土",
            "E": "设计强度后墙底注浆",
        },
        "correct_answer": "CDE",
        "explanation": "A 错误；地下连续墙单元槽段长度宜为 4～6m。B 错误；导墙高度应≥1.2m。",
        "user_answer": "ACDE",
        "is_correct": False,
        "reveal_answers": True,
        "reveal_explanations": True,
    }
    context.update(overrides)
    return context


def test_brief_reference_feedback_answers_wrong_cause_intent() -> None:
    response = _render_deterministic_reference_feedback(
        _wall_context(),
        user_message="错因是什么？10个字以内。",
    )

    assert response.startswith("误选槽段长度8-10")


def test_brief_reference_feedback_answers_specific_value_challenge() -> None:
    response = _render_deterministic_reference_feedback(
        _wall_context(user_answer="CDE", is_correct=True),
        user_message="那1.0m到底行不行？10字以内。",
    )

    assert "正确答案是" in response
    assert "导墙高度应≥1.2m" in response


def test_brief_reference_feedback_answers_missing_selection_check() -> None:
    response = _render_deterministic_reference_feedback(
        {
            "question_id": "q_template_support",
            "question": "模板支架检查评分表保证项目包括哪些？",
            "question_type": "choice",
            "options": {
                "A": "施工方案",
                "B": "支架构造",
                "C": "底座与托撑",
                "D": "构配件材质",
                "E": "支架稳定",
            },
            "correct_answer": "ABE",
            "explanation": "保证项目包括施工方案、支架构造、支架稳定。",
            "user_answer": "ABE",
            "is_correct": True,
            "reveal_answers": True,
            "reveal_explanations": True,
        },
        user_message="一句话说我到底漏没漏。",
    )

    assert response == "没漏，ABE都选对。"


def test_reference_feedback_targets_indexed_question_set_item() -> None:
    response = _render_deterministic_reference_feedback(
        {
            "question_id": "quiz_generated",
            "question": "第1题...\n第2题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "第1题",
                    "question_type": "single_choice",
                    "options": {"A": "违法分包", "B": "合法分包"},
                    "correct_answer": "A",
                    "explanation": "主体结构不得分包。",
                },
                {
                    "question_id": "q_2",
                    "question": "第2题",
                    "question_type": "single_choice",
                    "options": {"A": "不支付", "B": "验收合格可参照合同支付"},
                    "grading_key": {"correct_answer": "B"},
                    "user_answer": "A",
                    "is_correct": False,
                    "explanation": "合同无效但工程验收合格时可参照合同约定支付工程款。",
                },
            ],
        },
        user_message="现在公布第2题答案和解析，不要批第1题。",
    )

    assert "验收合格可参照合同支付" in response
    assert "主体结构不得分包" not in response
