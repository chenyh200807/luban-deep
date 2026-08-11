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
    """PR3-6c 后的新身份:legacy-object tolerance pin。question_lifecycle_clarification
    对象自 PR3-6c 起无 writer,但 store 存量老会话仍可能带着它(只删 writer 不做数据
    迁移)——读端必须继续容忍该对象且不误伤新题预取。保留原样,不删不改。"""
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


def test_blocked_reason_vetoes_prefetched_exact_authority_candidate() -> None:
    """PR3-6a 数据面守恒钉(loop.py _prefetched_exact_authority_candidate):撤话语面
    不撤数据面——blocked 轮即使预取到 exact 权威候选也必须被否决(返回 None),
    主 LLM 在 blocked 轮只有 history + prompt 提示可用,拿不到题库 exact 权威。"""
    exact_question = {
        "question_id": "q-2025-3",
        "question": "2025年真题第3题题干",
        "correct_answer": "B",
        "match_type": "exact",
        "answer_kind": "mcq",
    }
    assert (
        AgentLoop._prefetched_exact_authority_candidate(
            {
                "_prefetched_exact_question": dict(exact_question),
                "exact_question_blocked_reason": "low_information_exam_query",
            },
            current_message="2025年真题第3题答案",
        )
        is None
    )
    # 对照:无 blocked reason 时同一候选不被此闸否决(可能被其他闸处理,但不为 None
    # 的路径存在与否不在本钉范围——这里只断言 blocked 键是决定性差异)。
    unblocked = AgentLoop._prefetched_exact_authority_candidate(
        {"_prefetched_exact_question": dict(exact_question)},
        current_message="2025年真题第3题答案",
    )
    assert unblocked is not None


def test_progressive_skill_instruction_injects_clarification_hint(tmp_path) -> None:
    """PR3-6a 新增钉:runtime_metadata 带 exact_question_blocked_reason 时,
    _build_progressive_skill_instruction 输出必须含权威门提示段(含防编造指令);
    无 blocked reason 时不含。fast/deep 双模共享此函数,一处注入两模生效。"""
    from typing import Any

    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class FakeProvider(LLMProvider):
        async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
            return LLMResponse(content="已完成")

        def get_default_model(self) -> str:
            return "fake-model"

    loop = AgentLoop(MessageBus(), FakeProvider(), tmp_path)

    for response_mode in ("fast", "deep"):
        blocked_metadata = {
            "bot_id": "construction-exam-coach",
            "default_kb": "construction-exam",
            "effective_response_mode": response_mode,
            "exact_question_blocked_reason": "low_information_exam_query",
        }
        instruction = loop._build_progressive_skill_instruction(
            "2025年真题第3题答案",
            runtime_metadata=blocked_metadata,
        )
        assert "题目权威门提示" in instruction
        assert "绝不编造" in instruction

        clean_metadata = {
            "bot_id": "construction-exam-coach",
            "default_kb": "construction-exam",
            "effective_response_mode": response_mode,
        }
        clean_instruction = loop._build_progressive_skill_instruction(
            "建筑构造是什么？",
            runtime_metadata=clean_metadata,
        )
        assert "题目权威门提示" not in clean_instruction
