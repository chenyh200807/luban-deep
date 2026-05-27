from deeptutor.tutorbot.agent.loop import AgentLoop


def test_active_question_grading_does_not_prefetch_grounded_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="我选B",
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "question_lifecycle_scene": "mcq_grading",
                "question_followup_context": {
                    "question_id": "quiz_3",
                    "question": "第1题...\n第2题...",
                    "question_type": "choice",
                    "items": [
                        {"question_id": "q_1", "question": "题1", "correct_answer": "A"},
                        {"question_id": "q_2", "question": "题2", "correct_answer": "B"},
                    ],
                },
            },
        )
        is False
    )


def test_free_text_question_review_still_prefetches_grounded_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="分析一道钢筋保护层真题",
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "question_lifecycle_scene": "question_review",
            },
        )
        is True
    )
