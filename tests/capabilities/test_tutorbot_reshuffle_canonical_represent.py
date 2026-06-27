"""Deterministic canonical re-presentation for explicit option-reshuffle requests.

判分倒诬 SEV anti-fabrication regression suite (动作3 选项②).

MCQ grading compares letters against the single surface authority
(active_object.state_snapshot.options, anchored at first presentation). When a
learner asks TutorBot to "把选项打乱重排 / 重新排列选项 / 换个顺序", the free-text
LLM would invent a NEW option order S2 WITHOUT rebuilding the snapshot or
re-projecting correct_answer. The learner then answers by S2 letters, grading
compares against the old surface letters -> 倒诬 (live: "你选错了，正确答案是B"
when the learner answered the presented surface C).

Fix (选项②): detect an explicit reshuffle/re-present request for an *active
unanswered MCQ* BEFORE the LLM, and re-present deterministically in CANONICAL
order (state_snapshot.options 原序, answer hidden) + a fixed note explaining why
order is fixed. The grading internals (answers_match / mcq.py) are untouched —
re-presenting deterministically keeps the snapshot and the presented surface
identical, so the anchor letter always matches what the learner sees.

Over-trigger is the primary risk: clarification ("A选项什么意思"), hints
("这题提示下"), answers ("我选B"), generation, and general chat MUST still flow
through the normal LLM path.
"""

from __future__ import annotations

import pytest

from deeptutor.capabilities import tutorbot as tutorbot_capability
from deeptutor.capabilities.tutorbot import TutorBotCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


class _FreeLlmManager:
    """send_message returns a re-ordered surface — proves the short-circuit
    fired only if this text never reaches the learner."""

    def __init__(self) -> None:
        self.sent_messages = 0
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
        # Free LLM re-ordering the surface (the divergent S2 we must prevent).
        return (
            "好的，给你换个顺序：\n"
            "A. 按勘察与设计方案\n"
            "B. 无需支护\n"
            "C. 随意\n"
            "D. 按经验"
        )


def _active_single_mcq(*, answered: bool = False) -> dict[str, object]:
    """A single active MCQ. Canonical option order is A/B/C/D as listed."""

    ctx: dict[str, object] = {
        "question_id": "q_active",
        "question": "深基坑支护方案应如何选择？",
        "question_type": "choice",
        "options": {
            "A": "无需支护",
            "B": "按经验",
            "C": "按勘察与设计方案",
            "D": "随意",
        },
        "correct_answer": "C",
        "explanation": "深基坑支护应依据勘察资料与设计方案确定。",
    }
    if answered:
        ctx["user_answer"] = "B"
        ctx["is_correct"] = False
    return ctx


def _build_context(*, user_message: str, followup_context: dict[str, object] | None) -> UnifiedContext:
    metadata: dict[str, object] = {}
    if followup_context is not None:
        metadata["question_followup_context"] = followup_context
    return UnifiedContext(
        session_id="s-reshuffle",
        user_message=user_message,
        config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "fast"},
        metadata=metadata,
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
    """把选项打乱重排 (active unanswered MCQ) -> deterministic CANONICAL order, no LLM."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="把选项打乱重排一下",
        followup_context=_active_single_mcq(),
    )

    await TutorBotCapability().run(context, stream)

    # 1. The free LLM was never invoked -> no divergent surface S2 generated.
    assert manager.sent_messages == 0

    payload = _result_payload(stream)
    response = str(payload["response"])

    # 2. Options re-presented in CANONICAL order (state_snapshot order A/B/C/D),
    #    NOT the LLM's re-ordered A=按勘察... surface.
    assert "A. 无需支护" in response
    assert "B. 按经验" in response
    assert "C. 按勘察与设计方案" in response
    assert "D. 随意" in response
    pos_a = response.index("A. 无需支护")
    pos_b = response.index("B. 按经验")
    pos_c = response.index("C. 按勘察与设计方案")
    pos_d = response.index("D. 随意")
    assert pos_a < pos_b < pos_c < pos_d, "options must stay in canonical order"

    # 3. Explanatory note: order is fixed for grading accuracy.
    assert "判分" in response and "原题" in response

    # 4. Answer/explanation stay hidden (reveal flags closed).
    assert "正确答案" not in response
    assert payload["reveal_answers"] is False
    assert payload["reveal_explanations"] is False
    # 5. Emitted via the registered terminal authority (not a raw stream.result).
    #    execution_path lives in the RESULT payload; call_kind rides the content
    #    frame metadata (see _emit_lifecycle_terminal_response).
    assert payload["execution_path"] == "tutorbot_canonical_represent"
    content_events = [
        e for e in stream._history if e.type == StreamEventType.CONTENT
    ]
    assert content_events, "expected a content event"
    assert any(
        (e.metadata or {}).get("call_kind") == "canonical_represent"
        for e in content_events
    )


@pytest.mark.asyncio
async def test_reshuffle_variants_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重新排列 / 换个顺序 / 调换 / 重排选项 all short-circuit (no LLM)."""

    for message in (
        "重新排列一下选项",
        "选项换个顺序给我",
        "把 ABCD 选项对调一下",
        "重排一下选项顺序",
    ):
        manager = _FreeLlmManager()
        monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
        stream = StreamBus()
        context = _build_context(
            user_message=message,
            followup_context=_active_single_mcq(),
        )
        await TutorBotCapability().run(context, stream)
        assert manager.sent_messages == 0, f"reshuffle variant should short-circuit: {message!r}"
        payload = _result_payload(stream)
        assert payload["execution_path"] == "tutorbot_canonical_represent", message


@pytest.mark.asyncio
async def test_clarification_question_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: A选项什么意思 (clarification) -> normal LLM path."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="A选项什么意思？",
        followup_context=_active_single_mcq(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_hint_request_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: 这题提示下 (hint) -> normal LLM path."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="这题提示下",
        followup_context=_active_single_mcq(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_answer_submission_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: 我选B (answer) -> normal path (not a reshuffle request)."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="我选B",
        followup_context=_active_single_mcq(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_already_answered_mcq_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: reshuffle request but MCQ already attempted -> normal path."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="把选项打乱重排一下",
        followup_context=_active_single_mcq(answered=True),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_no_active_mcq_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: reshuffle phrasing but no active MCQ -> normal path."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="把选项打乱重排一下",
        followup_context=None,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


@pytest.mark.asyncio
async def test_written_question_without_options_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """over-trigger 护栏: active question has no options (written) -> normal path."""

    manager = _FreeLlmManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="把选项重排一下",
        followup_context={
            "question_id": "q_written",
            "question": "简述深基坑支护方案的选择依据。",
            "question_type": "written",
        },
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1
