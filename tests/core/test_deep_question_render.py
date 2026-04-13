from deeptutor.capabilities.deep_question import DeepQuestionCapability


def test_render_summary_markdown_hides_answers_by_default():
    capability = DeepQuestionCapability()
    markdown = capability._render_summary_markdown(
        {
            "results": [
                {
                    "qa_pair": {
                        "question": "流水步距的含义是什么？",
                        "options": {"A": "工期差", "B": "相邻专业队投入间隔"},
                        "correct_answer": "B",
                        "explanation": "它描述相邻专业队之间的节奏间隔。",
                    }
                }
            ]
        }
    )

    assert "流水步距的含义是什么？" in markdown
    assert "A. 工期差" in markdown
    assert "**Answer:**" not in markdown
    assert "**Explanation:**" not in markdown


def test_render_summary_markdown_can_show_answers_when_enabled():
    capability = DeepQuestionCapability()
    markdown = capability._render_summary_markdown(
        {
            "results": [
                {
                    "qa_pair": {
                        "question": "流水步距的含义是什么？",
                        "options": {"A": "工期差", "B": "相邻专业队投入间隔"},
                        "correct_answer": "B",
                        "explanation": "它描述相邻专业队之间的节奏间隔。",
                    }
                }
            ]
        },
        reveal_answers=True,
        reveal_explanations=True,
    )

    assert "**Answer:** B" in markdown
    assert "**Explanation:** 它描述相邻专业队之间的节奏间隔。" in markdown
