from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _FakeTutorBotManager:
    sent_messages = 0

    def build_chat_session_key(self, bot_id: str, conversation_id: str, *, user_id: str | None = None) -> str:
        return f"{bot_id}:{conversation_id}:{user_id or 'anon'}"

    def _infer_conversation_title(self, _message: str) -> str:
        return "测试会话"

    async def ensure_bot_running(self, _bot_id: str, *, config=None) -> None:
        return None

    async def send_message(self, **kwargs) -> str:
        self.sent_messages += 1
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
    assert "2025真题" in result_payload["response"]
    assert "查看这一类真题目录" in result_payload["response"]
    assert "标准答案" not in result_payload["response"]
    assert result_payload["exact_question_blocked_reason"] == "low_information_exam_query"
    assert result_payload["exact_fast_path_hit"] is False
    assert manager.sent_messages == 0


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
