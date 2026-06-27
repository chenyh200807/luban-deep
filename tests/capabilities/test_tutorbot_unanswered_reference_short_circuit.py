"""Deterministic short-circuit for unanswered-question references.

SEV anti-cheat regression suite. When a learner references a still-unanswered
question inside a multi-question batch ("第2题怎么做" while Q2 has no attempt),
TutorBot must NOT call the free-text LLM agent loop (which would solve Q2 from
model knowledge and leak the answer). Instead it must deterministically
re-present the referenced question stem + options (answer hidden, sourced from
question_followup_context, never grading_key) plus a fixed nudge.

The safety belt: questions the learner already attempted, concessions
("我不会了"), and topic switches must still flow through the normal LLM path.
"""

from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _LeakingManager:
    """send_message returns a fully solved Q2 — proves the short-circuit fired
    only if this text never reaches the learner."""

    sent_messages = 0

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_chat_session_key(
        self, bot_id: str, conversation_id: str, *, user_id: str | None = None
    ) -> str:
        return f"{bot_id}:{conversation_id}:{user_id or 'anon'}"

    def _infer_conversation_title(self, _message: str) -> str:
        return "测试会话"

    async def ensure_bot_running(self, _bot_id: str, *, config=None) -> None:
        return None

    async def send_message(self, **kwargs) -> str:
        self.sent_messages += 1
        self.calls.append(dict(kwargs))
        # Free-text LLM solving Q2 from its own knowledge — the leak we block.
        return (
            "第2题的正确答案是 C。\n"
            "解析：根据规范，深基坑支护应采用方案 C，因为……\n"
            "答案：C"
        )


def _two_question_followup_context() -> dict[str, object]:
    """A batch of two MCQs. Q1 is attempted (user_answer=B), Q2 is NOT."""

    return {
        "question_id": "question_set",
        "question": "一组施工选择题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第一题：施工缝处理正确的是？",
                "question_type": "choice",
                "options": {"A": "任意留设", "B": "按规范处理", "C": "不清理", "D": "跨中"},
                "correct_answer": "B",
                "explanation": "施工缝应按设计和规范处理。",
                "user_answer": "B",
                "is_correct": True,
            },
            {
                "question_id": "q_2",
                "question": "第二题：深基坑支护方案应如何选择？",
                "question_type": "choice",
                "options": {
                    "A": "无需支护",
                    "B": "按经验",
                    "C": "按勘察与设计方案",
                    "D": "随意",
                },
                "correct_answer": "C",
                "explanation": "深基坑支护应依据勘察资料与设计方案确定。",
            },
        ],
    }


def _build_context(*, user_message: str, followup_context: dict[str, object]) -> UnifiedContext:
    return UnifiedContext(
        session_id="s-unanswered-ref",
        user_message=user_message,
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        metadata={"question_followup_context": followup_context},
        language="zh",
    )


def _result_payload(stream: StreamBus) -> dict:
    result_events = [e for e in stream._history if e.type == StreamEventType.RESULT]
    assert result_events, "expected a result event"
    return result_events[-1].metadata


@pytest.mark.asyncio
async def test_unanswered_reference_short_circuits_before_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第2题怎么做 (Q2 unanswered) -> deterministic stem+nudge, no LLM call, no answer."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="第2题怎么做？",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    # 1. The LLM agent loop was never invoked.
    assert manager.sent_messages == 0

    payload = _result_payload(stream)
    response = str(payload["response"])

    # 2. The referenced question's stem + options are deterministically re-presented.
    assert "深基坑支护方案应如何选择" in response
    assert "C. 按勘察与设计方案" in response

    # 3. NO answer / explanation for Q2 leaked (answer lives in grading_key, hidden).
    assert "按勘察与设计方案" in response  # option text is fine, it's the prompt surface
    assert "正确答案是 C" not in response
    assert "答案：C" not in response
    assert "解析：" not in response
    # The fixed nudge invites the learner to attempt first.
    assert "你还没作答" in response or "初步思路" in response

    # 4. Reveal flags stay closed.
    assert payload["reveal_answers"] is False
    assert payload["reveal_explanations"] is False


@pytest.mark.asyncio
async def test_attempted_question_explanation_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """安全带: 第1题为什么选B (Q1 already answered) -> should_block=False -> normal LLM path."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="第1题为什么选B？",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    # Q1 has a learner attempt -> not blocked -> LLM must run (can explain).
    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_concession_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """安全带: 我不会了，直接给答案吧 (concession) -> not blocked -> normal LLM reveal path."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="第2题我不会了，直接给答案吧",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    # Concession marker present -> should_block False -> LLM runs (reveal allowed).
    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_topic_switch_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """安全带: 换个话题，讲讲钢筋吧 (not a question reference) -> no short-circuit."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="换个话题，讲讲钢筋吧",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    # No "第N题" reference -> requested_question_item_index None -> not short-circuited.
    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_no_followup_context_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """安全带: plain chat with no active question batch -> normal LLM path."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = UnifiedContext(
        session_id="s-plain-chat",
        user_message="第2题怎么做？",  # references "第2题" but no batch context exists
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        language="zh",
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1
