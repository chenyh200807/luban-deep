from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus
import deeptutor.services.tutorbot.manager as tutorbot_manager


class _FakeTutorBotManager:
    sent_messages = 0

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_chat_session_key(self, bot_id: str, conversation_id: str, *, user_id: str | None = None) -> str:
        return f"{bot_id}:{conversation_id}:{user_id or 'anon'}"

    def _infer_conversation_title(self, _message: str) -> str:
        return "测试会话"

    async def ensure_bot_running(self, _bot_id: str, *, config=None) -> None:
        return None

    async def send_message(self, **kwargs) -> str:
        self.sent_messages += 1
        self.calls.append(dict(kwargs))
        return (
            "第1题：下列关于施工缝处理正确的是？\n"
            "A. 任意留设\n"
            "B. 按设计和规范处理\n"
            "C. 不需要清理\n"
            "D. 只能留在跨中\n"
            "答案：B\n"
            "解析：施工缝应按设计和规范处理。"
        )


@pytest.mark.asyncio
async def test_tutorbot_does_not_turn_free_text_mcq_into_submitable_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: _FakeTutorBotManager(),
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-free-text",
        user_message="讲一下施工缝，顺便举个选择题例子",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_metadata = result_events[-1].metadata
    assert "presentation" not in result_metadata
    assert "question_followup_context" not in result_metadata
    assert "active_object" not in result_metadata


@pytest.mark.asyncio
async def test_tutorbot_bridge_keeps_raw_user_content_out_of_prompt_envelope_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeTutorBotManager()
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: manager,
    )

    raw_message = "防水卷材搭接宽度怎么记？"
    prompt_envelope = (
        "## 参考证据\n"
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
        "### 局部工作记忆投影\n"
        "这里是注入给 LLM 的内部工作记忆。\n\n"
        "## 当前用户问题\n"
        f"{raw_message}"
    )
    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-envelope",
        user_message=prompt_envelope,
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={"raw_user_message": raw_message},
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    call = manager.calls[-1]
    assert str(call["content"]).startswith("## 参考证据")
    assert call["raw_user_content"] == raw_message
    assert "raw_user_message" not in call["session_metadata"]


@pytest.mark.asyncio
async def test_tutorbot_result_propagates_compiled_knowledge_shadow_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "llm_may_decide_correctness": False,
        "confidence": {"status": "high", "source_category_count": 2},
        "leaf_name_path": "建筑工程技术 > 建筑高度分类",
        "sources": {"textbook": [{"text_preview": "27m"}], "lecture": [{"text_preview": "高层住宅"}]},
    }

    class FakeManager(_FakeTutorBotManager):
        async def send_message(self, **kwargs) -> str:
            session_metadata = kwargs["session_metadata"]
            assert session_metadata["general_knowledge_context"] is True
            session_metadata["luban_general_knowledge_context"] = pack
            session_metadata["luban_general_knowledge_context_status"] = "attached"
            return "高层住宅大于 27m。"

    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: FakeManager(),
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-tutorbot-compiled-shadow",
        user_message="高层住宅的建筑高度是怎么界定的？",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "smart",
            "general_knowledge_context": True,
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    assert result_payload["luban_general_knowledge_context"] == pack
    assert result_payload["luban_general_knowledge_context_status"] == "attached"


def test_tutorbot_general_knowledge_shadow_opt_in_does_not_attach_with_active_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_resolve(*args, **kwargs):
        raise AssertionError("resolver must not run while active question context exists")

    monkeypatch.setattr(
        tutorbot_manager,
        "resolve_general_knowledge_context",
        _fail_resolve,
        raising=False,
    )
    metadata = {
        "general_knowledge_context": True,
        "active_object": {
            "object_type": "single_question",
            "object_id": "q_active",
            "state_snapshot": {
                "question_id": "q_active",
                "question": "既有题对象",
            },
        },
    }

    tutorbot_manager._attach_general_knowledge_context(
        content="高层住宅的建筑高度是怎么界定的？",
        runtime_metadata=metadata,
    )

    assert "luban_general_knowledge_context" not in metadata
    assert "luban_general_knowledge_context_status" not in metadata


@pytest.mark.asyncio
async def test_tutorbot_low_information_exam_query_returns_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeTutorBotManager()
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: manager,
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-low-info-exam-query",
        user_message="2025真题",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={
            "exact_question_blocked_reason": "low_information_exam_query",
            "question_lifecycle_decision": {
                "scene": None,
                "decision_source": "deterministic",
                "scene_confidence": 1.0,
                "reason": "low-information exam query needs clarification",
                "required_anchor_status": "missing_question_anchor",
                "exact_question_blocked_reason": "low_information_exam_query",
                "selected_skill_names": [],
                "needs_clarification": True,
            },
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    # 去毒(2026-06-22 meta-leak 修复):low_info 澄清不再逐字回显学生原句、不再泄露内部机制
    assert "2025真题" not in result_payload["response"]
    assert "题卡" not in result_payload["response"]
    assert "传给 TutorBot" not in result_payload["response"]
    assert "就是在编" not in result_payload["response"]
    # 仍是可继续的澄清:引导学生给题干/选项
    assert "题干" in result_payload["response"] and "选项" in result_payload["response"]
    assert "标准答案" not in result_payload["response"]
    assert result_payload["exact_question_blocked_reason"] == "low_information_exam_query"
    assert result_payload["exact_fast_path_hit"] is False
    assert manager.sent_messages == 0


@pytest.mark.asyncio
async def test_tutorbot_low_information_clarification_does_not_echo_raw_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeTutorBotManager()
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: manager,
    )

    stream = StreamBus()
    raw_message = "2021屋面案例第4问答案发我，快点，我在刷题页面。"
    context = UnifiedContext(
        session_id="s-low-info-augmented-message",
        user_message=(
            "## 参考证据\n"
            "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
            "### 局部工作记忆投影\n"
            "上一轮屋面女儿墙节点批改内容。\n\n"
            "## 当前用户问题\n"
            f"{raw_message}"
        ),
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={
            "raw_user_message": raw_message,
            "exact_question_blocked_reason": "low_information_exam_query",
            "question_lifecycle_decision": {
                "scene": None,
                "decision_source": "deterministic",
                "scene_confidence": 1.0,
                "reason": "low-information case answer request needs clarification",
                "required_anchor_status": "missing_question_anchor",
                "exact_question_blocked_reason": "low_information_exam_query",
                "selected_skill_names": [],
                "needs_clarification": True,
            },
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    # 去毒(2026-06-22 meta-leak 修复):澄清绝不逐字回显学生原句(旧行为=把整句当 {topic}
    # 嵌入"我知道你是想直接要…"=meta 泄露主源),也不泄露增强证据/内部机制。
    assert raw_message not in result_payload["response"]
    assert "答案发我" not in result_payload["response"]
    assert "题卡" not in result_payload["response"]
    assert "参考证据" not in result_payload["response"]
    assert "局部工作记忆投影" not in result_payload["response"]
    assert manager.sent_messages == 0


@pytest.mark.asyncio
async def test_tutorbot_exact_authority_persists_natural_submission_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeManager:
        async def ensure_bot_running(self, bot_id: str, config=None) -> None:
            return None

        def build_chat_session_key(
            self,
            bot_id: str,
            conversation_id: str,
            user_id: str | None = None,
        ) -> str:
            return f"bot:{bot_id}:chat:{conversation_id}"

        def _infer_conversation_title(self, text: str) -> str:
            return text[:8]

        async def send_message(self, **kwargs) -> str:
            on_tool_result = kwargs.get("on_tool_result")
            if on_tool_result is not None:
                await on_tool_result(
                    "rag",
                    "题库命中模板支架保证项目原题",
                    {
                        "authority_applied": True,
                        "exact_question": {
                            "answer_kind": "mcq",
                            "stem": "模板支架检查评分表保证项目包括（ ）。",
                            "question_type": "multi_choice",
                            "correct_answer": "ABE",
                            "analysis": "模板支架检查评分表保证项目包括施工方案、支架构造、支架稳定。",
                            "options": [
                                {"key": "A", "value": "施工方案"},
                                {"key": "B", "value": "支架构造"},
                                {"key": "C", "value": "底座与托撑"},
                                {"key": "D", "value": "构配件材质"},
                                {"key": "E", "value": "支架稳定"},
                            ],
                        },
                    },
                )
            return "标准答案：ABE。你只勾施工方案、支架构造、支架稳定，可以拿满。"

    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: FakeManager(),
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-exact-natural-submission",
        user_message=(
            "五个候选是施工方案、支架构造、底座与托撑、构配件材质、支架稳定。"
            "我只勾施工方案+支架构造+支架稳定，能拿满吗？"
        ),
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={"billing_context": {"user_id": "u1", "source": "wx_miniprogram"}},
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    question_context = result_payload["question_followup_context"]
    assert result_payload["authority_applied"] is True
    assert question_context["reveal_answers"] is True
    assert question_context["user_answer"] == "ABE"
    assert question_context["is_correct"] is True
    assert question_context["items"][0]["user_answer"] == "ABE"
    assert question_context["items"][0]["is_correct"] is True
    assert result_payload["active_object"]["object_type"] == "single_question"


@pytest.mark.asyncio
async def test_tutorbot_exam_catalog_query_answers_directory_without_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeTutorBotManager()
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: manager,
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-exam-catalog-query",
        user_message="1",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={
            "question_lifecycle_scene": "exam_catalog_query",
            "question_lifecycle_clarification": {
                "topic": "2025年真题",
                "reason": "low_information_exam_query",
                "options": [],
            },
            "question_lifecycle_decision": {
                "scene": "exam_catalog_query",
                "decision_source": "deterministic",
                "scene_confidence": 1.0,
                "required_anchor_status": "satisfied",
                "selected_skill_names": [
                    "construction-exam-tutor",
                    "construction-study-assistant",
                ],
                "needs_clarification": False,
                "business_gate_result": "resolved_clarification_option",
            },
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    assert "2025年真题" in result_payload["response"]
    assert "考点范围" in result_payload["response"]
    assert "不直接编造某一道题的标准答案" in result_payload["response"]
    assert result_payload["question_lifecycle_scene"] == "exam_catalog_query"
    assert result_payload["execution_path"] == "tutorbot_exam_catalog_query"
    assert manager.sent_messages == 0


@pytest.mark.asyncio
async def test_tutorbot_regular_result_exports_lifecycle_decision_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeTutorBotManager()
    monkeypatch.setattr(
        tutorbot_capability,
        "get_tutorbot_manager",
        lambda: manager,
    )

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-lifecycle-regular",
        user_message="我最近哪里错",
        config_overrides={
            "bot_id": "construction-exam-coach",
            "chat_mode": "fast",
        },
        metadata={
            "question_lifecycle_scene": "learning_evidence_story",
            "decision_source": "deterministic",
            "scene_confidence": 1.0,
            "required_anchor_status": "satisfied",
            "selected_skill_names": [
                "construction-exam-tutor",
                "construction-learning-evidence-story",
            ],
            "question_lifecycle_decision": {
                "scene": "learning_evidence_story",
                "decision_source": "deterministic",
                "scene_confidence": 1.0,
                "required_anchor_status": "satisfied",
                "selected_skill_names": [
                    "construction-exam-tutor",
                    "construction-learning-evidence-story",
                ],
                "llm_scene_candidate": {
                    "scene": "learning_evidence_story",
                    "confidence": 0.82,
                },
                "business_gate_result": "passed",
            },
            "llm_scene_candidate": {
                "scene": "learning_evidence_story",
                "confidence": 0.82,
            },
            "business_gate_result": "passed",
        },
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    result_events = [event for event in stream._history if event.type == StreamEventType.RESULT]
    assert result_events
    result_payload = result_events[-1].metadata
    assert result_payload["question_lifecycle_scene"] == "learning_evidence_story"
    assert result_payload["question_lifecycle_decision"]["scene"] == "learning_evidence_story"
    assert result_payload["decision_source"] == "deterministic"
    assert result_payload["required_anchor_status"] == "satisfied"
    assert result_payload["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-learning-evidence-story",
    ]
    assert result_payload["llm_scene_candidate"] == {
        "scene": "learning_evidence_story",
        "confidence": 0.82,
    }
    assert result_payload["business_gate_result"] == "passed"
    assert manager.sent_messages == 1


def test_grading_to_brain_result_payload_is_public_projection_source_pin() -> None:
    """泄漏面契约（与练题入口同口径）：TutorBot result_payload 不得直拷
    personalization_context / learning_training_intent；next_best_action 必须
    经 public_grading_to_brain_meta 投影（intent/evidence_refs 不出端）。"""
    import inspect

    import deeptutor.capabilities.tutorbot as tutorbot_module

    src = inspect.getsource(tutorbot_module)
    copy_block_start = src.index("grading_to_brain_loop")
    copy_block = src[copy_block_start: copy_block_start + 2000]
    assert '"personalization_context",' not in copy_block
    assert '"learning_training_intent",' not in copy_block
    assert "public_grading_to_brain_meta" in copy_block


def test_public_grading_to_brain_meta_strips_internal_authority_fields() -> None:
    from deeptutor.services.construction_grading.writeback import public_grading_to_brain_meta

    projected = public_grading_to_brain_meta({
        "next_best_action": {
            "title": "先练屋面与防水工程施工",
            "target": "屋面与防水工程施工 · 采分点遗漏",
            "why_this_now": "真实错因图已把该薄弱点连接到下一轮训练。",
            "materials": ["教材：相关章节", ""],
            "success_measure": "复测命中目标采分点",
            "action_type": "retest_or_targeted_practice",
            "prescription_authority": "training_intent",
            "training_intent_id": "ti_secret",
            "evidence_refs": ["evt_1"],
            "intent": {"user_id": "stu_1"},
        },
        "personalization_context": {"user_id": "stu_1"},
        "learning_training_intent": {"training_intent_id": "ti_secret"},
        "grading_to_brain_loop": {"event_id": "evt_1"},
        "learning_evidence_event_id": "evt_1",
    })

    assert "personalization_context" not in projected
    assert "learning_training_intent" not in projected
    nba = projected["next_best_action"]
    assert nba["title"] and nba["target"]
    assert "intent" not in nba
    assert "evidence_refs" not in nba
    assert "training_intent_id" not in nba
    assert projected["learning_evidence_event_id"] == "evt_1"
