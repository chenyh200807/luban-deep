from __future__ import annotations

import pytest

from deeptutor.services import semantic_router


def _question_context() -> dict[str, object]:
    return {
        "question_id": "q_1",
        "question": "流水步距反映的是什么？",
        "question_type": "choice",
        "options": {"A": "工期", "B": "相邻专业队投入间隔"},
        "correct_answer": "B",
    }


def _guide_active_object() -> dict[str, object]:
    return {
        "object_type": "guide_page",
        "object_id": "plan_demo:page:1",
        "scope": {"domain": "guided_plan", "plan_id": "plan_demo", "page_index": 1},
        "state_snapshot": {
            "plan_id": "plan_demo",
            "status": "in_progress",
            "current_index": 1,
            "summary": "当前正在学习网络计划。",
            "current_page": {
                "page_index": 1,
                "knowledge_title": "网络计划关键线路",
                "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
            },
        },
        "version": 1,
        "entered_at": "",
        "last_touched_at": "",
        "source_turn_id": "turn-guide-1",
    }


def _open_chat_active_object() -> dict[str, object]:
    return {
        "object_type": "open_chat_topic",
        "object_id": "session-open-chat",
        "scope": {"domain": "session", "session_id": "session-open-chat", "source": "wx"},
        "state_snapshot": {
            "session_id": "session-open-chat",
            "title": "施工组织总设计",
            "compressed_summary": "用户一直在讨论施工组织总设计和网络计划。",
            "source": "wx",
            "status": "idle",
        },
        "version": 1,
        "entered_at": "",
        "last_touched_at": "",
        "source_turn_id": "turn-open-chat-1",
    }


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_maps_llm_answer_to_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        assert history_context == "recent"
        return {
            "intent": "answer_questions",
            "confidence": 0.91,
            "preserve_other_answers": False,
            "answers": [{"index": 1, "question_id": "q_1", "user_answer": "B"}],
            "reason": "用户正在回答当前题目。",
        }

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)

    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-1",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "我选B",
        active_object,
        history_context="recent",
    )

    assert action is not None
    assert decision is not None
    assert decision["relation_to_active_object"] == "answer_active_object"
    assert decision["next_action"] == "route_to_grading"
    assert decision["allowed_patch"] == ["update_answer_slot"]
    assert semantic_router.turn_semantic_decision_route(decision) == "deep_question"


@pytest.mark.asyncio
async def test_open_chat_short_acceptance_of_recent_practice_offer_routes_to_generation() -> None:
    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "要",
        _open_chat_active_object(),
        history_context=(
            "Assistant: 记忆口诀强化\n"
            "主体结构七大类：砼砌钢，钢管型钢铝木全。\n"
            "需要我出同考点题目帮你巩固一下吗？"
        ),
    )

    assert action is not None
    assert action["intent"] == "generate_more_questions"
    assert action["topic"] == "继续出同考点题目帮我巩固一下"
    assert decision is not None
    assert decision["relation_to_active_object"] == "continue_same_learning_flow"
    assert decision["next_action"] == "route_to_generation"
    assert semantic_router.turn_semantic_decision_route(decision) == "deep_question"


@pytest.mark.asyncio
async def test_open_chat_short_acceptance_without_recent_offer_stays_chat() -> None:
    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "要",
        _open_chat_active_object(),
        history_context="Assistant: 我们刚才在解释主体结构口诀。",
    )

    assert action is None
    assert decision is not None
    assert decision["next_action"] == "route_to_general_chat"
    assert semantic_router.turn_semantic_decision_route(decision) == "chat"


@pytest.mark.asyncio
async def test_open_chat_repeated_assistant_offer_routes_to_generation_when_offer_is_recent() -> None:
    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "需要我出同考点题目帮你巩固一下",
        _open_chat_active_object(),
        history_context=(
            "Assistant: 花 1 分钟把口诀过三遍，下次遇到直接套用。\n"
            "需要我出同考点题目帮你巩固一下吗？"
        ),
    )

    assert action is not None
    assert action["intent"] == "generate_more_questions"
    assert decision is not None
    assert decision["next_action"] == "route_to_generation"
    assert semantic_router.turn_semantic_decision_route(decision) == "deep_question"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_uses_deterministic_submission_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return None

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)

    active_object = semantic_router.build_active_object_from_question_context(
        {
            "question_id": "quiz_batch",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "choice",
                    "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "choice",
                    "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "choice",
                    "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                    "correct_answer": "D",
                },
            ],
        },
        source_turn_id="turn-batch",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "ACD",
        active_object,
    )

    assert decision is not None
    assert action is None
    assert decision["relation_to_active_object"] == "answer_active_object"
    assert decision["next_action"] == "route_to_grading"
    assert decision["allowed_patch"] == ["append_answer_slots"]


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_keeps_next_question_explanation_as_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return None

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)
    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-next-explain",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "下一题解析一下",
        active_object,
    )

    assert action is None
    assert decision is not None
    assert decision["relation_to_active_object"] == "ask_about_active_object"
    assert decision["next_action"] == "route_to_followup_explainer"
    assert decision["allowed_patch"] == ["no_state_change"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ["为什么不是B？一句话。", "B为什么不对？", "那A呢？", "那A呢？一句话"],
)
async def test_resolve_turn_semantic_decision_keeps_option_challenge_as_followup(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return None

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)
    active_object = semantic_router.build_active_object_from_question_context(
        {
            "question_id": "q_1",
            "question": "流水步距反映的是什么？",
            "question_type": "choice",
            "options": {"A": "工期", "B": "相邻专业队投入间隔"},
            "correct_answer": "B",
            "user_answer": "A",
            "is_correct": False,
        },
        source_turn_id="turn-option-challenge",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        message,
        active_object,
    )

    assert action is None
    assert decision is not None
    assert decision["relation_to_active_object"] == "ask_about_active_object"
    assert decision["next_action"] == "route_to_followup_explainer"
    assert decision["allowed_patch"] == ["no_state_change"]


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_keeps_option_challenge_from_llm_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def misleading_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return {
            "intent": "generate_more_questions",
            "confidence": 0.9,
            "answers": [],
            "reason": "模拟 LLM 把选项追问误判成继续出题。",
        }

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", misleading_interpret)
    active_object = semantic_router.build_active_object_from_question_context(
        {
            "question_id": "historical:roof_slope",
            "question": "压型金属板屋面最低坡度是多少？",
            "question_type": "choice",
            "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
            "correct_answer": "D",
            "user_answer": "B",
            "is_correct": False,
        },
        source_turn_id="turn-option-challenge-llm-generation",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "那C呢？一句话",
        active_object,
    )

    assert action is None
    assert decision is not None
    assert decision["relation_to_active_object"] == "ask_about_active_object"
    assert decision["next_action"] == "route_to_followup_explainer"
    assert decision["allowed_patch"] == ["no_state_change"]


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_routes_explicit_continue_practice_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return None

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)
    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-more-practice",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "继续出5道类似的",
        active_object,
    )

    assert action is not None
    assert action["intent"] == "generate_more_questions"
    assert action["answers"] == []
    assert decision is not None
    assert decision["relation_to_active_object"] == "continue_same_learning_flow"
    assert decision["next_action"] == "route_to_generation"
    assert decision["allowed_patch"] == ["set_active_object"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "选择题",
        "给我出简答题",
        "我想练习防水工程相关简答题",
    ],
)
async def test_resolve_turn_semantic_decision_prefers_explicit_generation_over_llm_submission(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return {
            "intent": "answer_questions",
            "confidence": 0.91,
            "answers": [{"index": 1, "question_id": "q_1", "user_answer": "A"}],
            "reason": "模拟 LLM 将“选择题”误判为上一题答案。",
        }

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)
    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-choice-request",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        message,
        active_object,
    )

    assert action is not None
    assert action["intent"] == "generate_more_questions"
    assert action["answers"] == []
    assert decision is not None
    assert decision["relation_to_active_object"] == "continue_same_learning_flow"
    assert decision["next_action"] == "route_to_generation"
    assert decision["allowed_patch"] == ["set_active_object"]


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_allows_temporary_detour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return {
            "intent": "unrelated",
            "confidence": 0.88,
            "preserve_other_answers": False,
            "answers": [],
            "reason": "用户在临时问会员问题。",
        }

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)

    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-detour",
    )

    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "我还有多少点数",
        active_object,
    )

    assert action is not None
    assert decision is not None
    assert decision["relation_to_active_object"] == "temporary_detour"
    assert decision["next_action"] == "route_to_general_chat"
    assert semantic_router.turn_semantic_decision_route(decision) == "chat"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_routes_active_guide_page_to_guide() -> None:
    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "继续刚才这个学习页面",
        _guide_active_object(),
    )

    assert action is None
    assert decision is not None
    assert decision["relation_to_active_object"] == "continue_same_learning_flow"
    assert decision["next_action"] == "route_to_guide"
    assert semantic_router.turn_semantic_decision_route(decision) == "chat"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_resumes_suspended_guide_page() -> None:
    async def _no_interpret(_message: str, _context: dict[str, object] | None) -> None:
        return None

    routing = await semantic_router.resolve_question_semantic_routing(
        user_message="回到刚才那个学习页面",
        metadata={
            "active_object": semantic_router.build_active_object_from_question_context(
                _question_context(),
                source_turn_id="turn-question",
            ),
            "suspended_object_stack": [_guide_active_object()],
        },
        history_context="",
        interpret_followup_action=_no_interpret,
        resolve_submission_attempt=semantic_router.resolve_submission_attempt,
        looks_like_question_followup=semantic_router.looks_like_question_followup,
        looks_like_practice_generation_request=semantic_router.looks_like_practice_generation_request,
    )

    assert routing.active_object is not None
    assert routing.active_object["object_type"] == "guide_page"
    assert routing.turn_semantic_decision["relation_to_active_object"] == "switch_to_new_object"
    assert routing.turn_semantic_decision["next_action"] == "route_to_guide"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_routes_open_chat_topic_to_chat() -> None:
    decision, action = await semantic_router.resolve_turn_semantic_decision(
        "继续刚才那个话题",
        _open_chat_active_object(),
    )

    assert action is None
    assert decision is not None
    assert decision["relation_to_active_object"] == "continue_same_learning_flow"
    assert decision["next_action"] == "route_to_general_chat"
    assert semantic_router.turn_semantic_decision_route(decision) == "chat"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_routes_starter_assessment_but_not_strategy_prompt() -> None:
    generation_decision, generation_action = await semantic_router.resolve_turn_semantic_decision(
        "帮我做一次入门摸底测试",
        _open_chat_active_object(),
    )

    assert generation_action is None
    assert generation_decision is not None
    assert generation_decision["next_action"] == "route_to_generation"
    assert semantic_router.turn_semantic_decision_route(generation_decision) == "deep_question"

    chat_decision, chat_action = await semantic_router.resolve_turn_semantic_decision(
        "请根据我的学习记录和最近进度，围绕施工组织设计安排下一步学习推进："
        "先判断我当前更适合知识讲解、例题带练、错因复盘还是少量自测；"
        "不要默认生成整套训练题。",
        _open_chat_active_object(),
    )

    assert chat_action is None
    assert chat_decision is not None
    assert chat_decision["next_action"] == "route_to_general_chat"
    assert semantic_router.turn_semantic_decision_route(chat_decision) == "chat"


@pytest.mark.asyncio
async def test_resolve_turn_semantic_decision_clarifies_low_confidence_grading_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_interpret(_message: str, _context: dict[str, object], *, history_context: str = ""):
        return {
            "intent": "answer_questions",
            "confidence": 0.2,
            "preserve_other_answers": False,
            "answers": [{"index": 1, "question_id": "q_1", "user_answer": "B"}],
            "reason": "模型低置信地猜测用户在作答。",
        }

    monkeypatch.setattr(semantic_router, "interpret_question_followup_action", fake_interpret)

    active_object = semantic_router.build_active_object_from_question_context(
        _question_context(),
        source_turn_id="turn-low-confidence",
    )

    decision, _action = await semantic_router.resolve_turn_semantic_decision(
        "这个吧",
        active_object,
    )

    assert decision is not None
    assert decision["relation_to_active_object"] == "uncertain"
    assert decision["next_action"] == "ask_clarifying_question"
