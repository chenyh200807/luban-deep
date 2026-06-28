"""M4(i) 方案②: deterministic canonical re-present of an active single MCQ.

When the learner asks to re-show / reshuffle the active question, the free-text
LLM would emit a divergent option surface (letters reshuffled) that the
state_snapshot — and the prose grader — never capture, so a later letter answer
is graded against the original surface (倒诬). TutorBot must instead re-present
the question deterministically from the single authority
(active_object.state_snapshot, original order), never calling the free LLM.

Safety belt: answers ("我选B"), explanations ("为什么选B"), and new-question
requests ("换一道") carry no re-present marker, so they must still flow through
the normal LLM path unchanged.
"""

from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _ReshuffleManager:
    """send_message returns a DIVERGENT reshuffled surface — proves the
    short-circuit fired only if this text never reaches the learner."""

    def __init__(self) -> None:
        self.sent_messages = 0

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
        # The divergent surface a free LLM would emit (注册证书有效期: 原序 B=3年).
        return (
            "好的，打乱后：\n"
            "- A. 5年\n- B. 1年\n- C. 3年\n- D. 4年\n"  # 3年 moved to C — the bug surface
        )


def _mcq_active_object() -> dict[str, object]:
    return {
        "object_type": "single_question",
        "object_id": "q_1",
        "state_snapshot": {
            "question_id": "q_1",
            "question": "一级建造师注册证书的有效期是几年？",
            "question_type": "choice",
            "options": {"A": "1年", "B": "3年", "C": "4年", "D": "5年"},
            "user_answer": "",
            "is_correct": None,
            "multi_select": False,
            "items": [],
        },
    }


def _build_context(user_message: str) -> UnifiedContext:
    return UnifiedContext(
        session_id="s-canonical-represent",
        user_message=user_message,
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        metadata={"active_object": _mcq_active_object()},
        language="zh",
    )


def _result_payload(stream: StreamBus) -> dict:
    result_events = [e for e in stream._history if e.type == StreamEventType.RESULT]
    assert result_events, "expected a result event"
    return result_events[-1].metadata


@pytest.mark.asyncio
async def test_reshuffle_request_short_circuits_to_canonical_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ReshuffleManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    await TutorBotCapability().run(
        _build_context("把这道题的选项内容不变，只把ABCD标号打乱顺序重新展示给我"),
        stream,
    )

    # 1. The free LLM was never invoked → no divergent surface.
    assert manager.sent_messages == 0

    payload = _result_payload(stream)
    response = str(payload["response"])

    # 2. Re-presented from canonical state_snapshot (ORIGINAL order): B is still 3年.
    assert "一级建造师注册证书的有效期是几年" in response
    assert "A. 1年" in response
    assert "B. 3年" in response
    assert response.index("A. 1年") < response.index("B. 3年") < response.index("C. 4年") < response.index("D. 5年")

    # 3. The divergent LLM surface (B=1年 / 3年 at C) never appears.
    assert "B. 1年" not in response

    # 4. Reveal flags stay closed.
    assert payload["reveal_answers"] is False
    assert payload["reveal_explanations"] is False


@pytest.mark.asyncio
async def test_answer_submission_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ReshuffleManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    stream = StreamBus()
    await TutorBotCapability().run(_build_context("我选B"), stream)
    # No re-present marker → short-circuit does not fire → normal path runs.
    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_explanation_request_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ReshuffleManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    stream = StreamBus()
    await TutorBotCapability().run(_build_context("为什么选B"), stream)
    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_new_question_request_still_goes_through_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ReshuffleManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    stream = StreamBus()
    await TutorBotCapability().run(_build_context("换一道题"), stream)
    # New-question intent must NOT be re-presented as the old question.
    assert manager.sent_messages == 1
