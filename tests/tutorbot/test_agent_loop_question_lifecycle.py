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


def test_lifecycle_clarification_object_does_not_disable_new_mcq_rag_prefetch() -> None:
    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message=(
                "根据JGJ59，《模板支架检查评分表》保证项目有（ ）。"
                "A施工方案 B支架构造 C底座与托撑 D构配件材质 E支架稳定。我选ABCE对吗？"
            ),
            runtime_metadata={
                "bot_id": "construction-exam-coach",
                "default_tools": ["rag"],
                "default_kb": "construction-exam",
                "question_lifecycle_scene": "mcq_grading",
                "active_object": {
                    "object_type": "question_lifecycle_clarification",
                    "state_snapshot": {
                        "topic": "2025年真题",
                        "reason": "low_information_exam_query",
                    },
                },
            },
        )
        is True
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


def test_default_grounded_construction_concepts_prefetch_without_citation_flag() -> None:
    metadata = {
        "bot_id": "construction-exam-coach",
        "default_tools": ["rag"],
        "default_kb": "construction-exam",
        "knowledge_bases": ["construction-exam"],
        "effective_response_mode": "deep",
    }

    for user_message in ("建筑构造是什么？", "怎么做防水工程"):
        assert (
            AgentLoop._should_prefetch_grounded_rag(
                current_message=user_message,
                runtime_metadata=metadata,
            )
            is True
        )


def test_fast_default_grounded_construction_concepts_prefetch_without_citation_flag() -> None:
    metadata = {
        "bot_id": "construction-exam-coach",
        "default_tools": ["rag"],
        "default_kb": "construction-exam",
        "knowledge_bases": ["construction-exam"],
        "effective_response_mode": "fast",
    }

    for user_message in ("建筑构造是什么？", "怎么做防水工程"):
        assert (
            AgentLoop._should_prefetch_grounded_rag(
                current_message=user_message,
                runtime_metadata=metadata,
            )
            is True
        )


def test_rag_prefetch_uses_current_user_question_from_internal_context_wrapper() -> None:
    wrapped_message = (
        "## 参考证据\n"
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
        "### 局部工作记忆投影\n"
        "旧答案：楼地面应满足的功能有 ABCD。\n\n"
        "## 当前用户问题\n"
        "请解释楼地面基本构造要求，必须引用2026建筑实务教材依据。"
    )
    metadata = {
        "bot_id": "construction-exam-coach",
        "default_tools": ["rag"],
        "default_kb": "construction-exam",
        "answer_citations_required": True,
    }

    assert (
        AgentLoop._should_prefetch_grounded_rag(
            current_message=wrapped_message,
            runtime_metadata=metadata,
        )
        is True
    )
    preview = AgentLoop._build_rag_preview_args(wrapped_message, metadata)
    assert preview["query"] == "请解释楼地面基本构造要求，必须引用2026建筑实务教材依据。"
    assert preview["kb_name"] == "construction-exam"


def test_web_search_prefetch_uses_current_user_question_from_internal_context_wrapper() -> None:
    wrapped_message = (
        "## 参考证据\n"
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
        "## 当前用户问题\n"
        "请联网查询2026一建考试时间，并简要回答。"
    )

    preview = AgentLoop._build_web_search_preview_args(wrapped_message)

    assert preview == {"query": "2026一建考试时间", "count": 5}


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
