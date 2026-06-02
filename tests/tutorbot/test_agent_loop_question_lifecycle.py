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


def test_citation_required_active_question_grading_does_not_prefetch_grounded_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="我选B",
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "answer_citations_required": True,
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


def test_citation_required_construction_exam_prefetches_default_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="请说明屋面防水构造的作用，并指出答题采分点。",
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "answer_citations_required": True,
            },
        )
        is True
    )


def test_citation_required_social_chat_does_not_prefetch_default_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="你好",
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "answer_citations_required": True,
            },
        )
        is False
    )


def test_citation_required_non_construction_bot_does_not_prefetch_default_rag() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message="请说明屋面防水构造的作用。",
            runtime_metadata={
                "bot_id": "general-chat",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "answer_citations_required": True,
            },
        )
        is False
    )
