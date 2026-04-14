from deeptutor.agents.question.agents.followup_agent import FollowupAgent


def test_render_question_context_includes_question_set_items() -> None:
    rendered = FollowupAgent._render_question_context(
        {
            "question_id": "question_set",
            "question": "第1题、第2题批改",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "第1题题干",
                    "question_type": "choice",
                    "options": {"A": "甲", "B": "乙"},
                    "user_answer": "A",
                    "correct_answer": "B",
                    "explanation": "第1题解析",
                },
                {
                    "question_id": "q_2",
                    "question": "第2题题干",
                    "question_type": "choice",
                    "options": {"A": "丙", "B": "丁"},
                    "user_answer": "B",
                    "correct_answer": "B",
                    "explanation": "第2题解析",
                },
            ],
        },
        reveal_reference_material=True,
    )

    assert "Question set items:" in rendered
    assert "Item 1 ID: q_1" in rendered
    assert "Item 2 ID: q_2" in rendered
    assert "Reference answer: B" in rendered
    assert "第2题解析" in rendered
