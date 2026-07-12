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


class _MnemonicManager(_LeakingManager):
    async def send_message(self, **kwargs) -> str:
        self.sent_messages += 1
        self.calls.append(dict(kwargs))
        return "记忆口诀：防水先排后防，坡度厚度看规范，年限条件分清楚。"


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


def _unattempted_two_question_followup_context() -> dict[str, object]:
    context = _two_question_followup_context()
    for item in context["items"]:
        if isinstance(item, dict):
            item.pop("user_answer", None)
            item.pop("is_correct", None)
    return context


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
async def test_indexed_explicit_reveal_for_unanswered_question_short_circuits_before_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第2题答案是什么 (Q2 unanswered) -> still blocked before the LLM can leak."""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="第2题答案是什么？",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0

    payload = _result_payload(stream)
    response = str(payload["response"])

    assert "深基坑支护方案应如何选择" in response
    assert "C. 按勘察与设计方案" in response
    assert "正确答案是 C" not in response
    assert "答案：C" not in response
    assert "解析：" not in response


@pytest.mark.asyncio
async def test_indexed_mnemonic_for_unanswered_question_short_circuits_before_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第2题记忆口诀 still points at the unanswered item, so it cannot use free LLM."""

    manager = _MnemonicManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message="第2题记忆口诀",
        followup_context=_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0

    payload = _result_payload(stream)
    response = str(payload["response"])

    assert "深基坑支护方案应如何选择" in response
    assert "记忆口诀" not in response
    assert "正确答案是 C" not in response
    assert "答案：C" not in response
    assert "解析：" not in response


@pytest.mark.asyncio
async def test_unanswered_question_set_mnemonic_request_goes_through_tutorbot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记忆口诀 is learning support, not unanswered-answer reveal."""

    manager = _MnemonicManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    followup_context = _unattempted_two_question_followup_context()
    context = _build_context(
        user_message="给我整理一建建筑实务记忆口诀",
        followup_context=followup_context,
    )
    context.metadata["active_object"] = {
        "object_type": "question_set",
        "object_id": "question_set",
        "state_snapshot": followup_context,
    }

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1
    assert manager.calls[0]["session_metadata"]["active_object"] == {}
    assert manager.calls[0]["session_metadata"]["question_followup_context"] == {}
    assert manager.calls[0]["session_metadata"]["followup_question_context"] == {}
    assert manager.calls[0]["session_metadata"]["_prefetched_exact_question"] == {}
    assert manager.calls[0]["session_metadata"]["question_context_redacted_for_safe_study_aid"] is True

    payload = _result_payload(stream)
    response = str(payload["response"])

    assert "记忆口诀" in response
    assert "这道题先自己推一推" not in response
    assert "解题思路" not in response


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


# ---------------------------------------------------------------------------
# WP3 (2026-07-12) — anti-peek 短路从"独立重判者"降级为"canonical 裁决的执行器"。
#
# 生产活体 (2026-07-08, owner 23edde9e): 用户三发"给我整理记忆口诀", LLM followup
# 判定器给出正确裁决 (route_to_followup_explainer / temporary_detour→general_chat,
# drove_route=true), 但 terminal 短路不读已持久化的 turn_semantic_decision, 用默认-
# block 关键词谓词重判翻案 → 0 秒 canned "这道题先自己推一推…" 逐字打回。
#
# Stage A (default-on): ①窄隐式求助兜底表命中 → 无条件开火 (SEV 护栏不依赖 LLM,
# 同时就是 LLM-down 兜底); ②未命中时读 canonical turn_semantic_decision, 判
# temporary_detour→route_to_general_chat 且 drove_route=true → 不开火, 复用 #417
# 的 session_metadata redaction 后 fall-through 主 LLM; ③其余走 legacy 分支不变。
# Stage B (flag DEEPTUTOR_ANTIPEEK_CANONICAL_FACET_ENABLED, 默认关): followup 判定
# 器输出布尔 facet seeks_active_answer_help; false→放行+redact (白名单旁路),
# true→开火。
# ---------------------------------------------------------------------------


class _GeneralChatManager(_LeakingManager):
    async def send_message(self, **kwargs) -> str:
        self.sent_messages += 1
        self.calls.append(dict(kwargs))
        return "好的，我们聊聊装配式建筑：它是把构件在工厂预制、现场装配的建造方式……"


def _detour_context(
    *,
    user_message: str,
    followup_context: dict[str, object],
    relation: str = "temporary_detour",
    next_action: str = "route_to_general_chat",
    router_mode: str = "primary",
    facet: bool | None = None,
    include_decision: bool = True,
) -> UnifiedContext:
    context = _build_context(user_message=user_message, followup_context=followup_context)
    context.metadata["active_object"] = {
        "object_type": "question_set",
        "object_id": "question_set",
        "state_snapshot": followup_context,
    }
    if include_decision:
        decision: dict[str, object] = {
            "relation_to_active_object": relation,
            "next_action": next_action,
            "allowed_patch": "no_state_change",
            "confidence": 0.85,
            "reason": "LLM 判定当前输入为临时跑题/学习辅助，不消费当前题答案。",
            "target_object_ref": {"object_type": "question_set", "object_id": "question_set"},
        }
        if facet is not None:
            decision["seeks_active_answer_help"] = facet
        context.metadata["turn_semantic_decision"] = decision
    context.metadata["semantic_router_mode"] = router_mode
    return context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_message",
    ["换个话题聊聊装配式建筑", "帮我列本周复习计划"],
)
async def test_canonical_detour_decision_releases_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str,
) -> None:
    """Stage A(b): canonical 裁决判 temporary_detour→general_chat 且 drove_route=true
    时, 短路不得重判翻案 —— 放行主 LLM, 并复用 #417 redaction 清掉题目上下文。"""

    manager = _GeneralChatManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _detour_context(
        user_message=user_message,
        followup_context=_unattempted_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    # canonical 裁决被消费: 不落 canned reprompt, 主 LLM 跑了。
    assert manager.sent_messages == 1
    payload = _result_payload(stream)
    assert payload.get("execution_path") != "tutorbot_unanswered_reference_reprompt"
    assert "这道题先自己推一推" not in str(payload["response"])

    # 放行必须伴随 redaction (题目上下文不给自由 LLM)。
    session_metadata = manager.calls[0]["session_metadata"]
    assert session_metadata["question_context_redacted_for_safe_study_aid"] is True
    assert session_metadata["active_object"] == {}
    assert session_metadata["question_followup_context"] == {}
    assert session_metadata["anti_peek_release_reason"] == "canonical_detour_general_chat"


@pytest.mark.asyncio
async def test_detour_decision_without_drove_route_keeps_legacy_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """drove_route=false (semantic_router_mode != primary) 的 detour 裁决只是
    bookkeeping, 不得放行 —— 短路照 legacy 开火。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _detour_context(
        user_message="帮我列本周复习计划",
        followup_context=_unattempted_two_question_followup_context(),
        router_mode="question_lifecycle",
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


@pytest.mark.asyncio
async def test_no_canonical_decision_keeps_legacy_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 canonical 裁决 (LLM-down / 未注入) 时 legacy 分支 bit 不变: 照常开火。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _detour_context(
        user_message="帮我列本周复习计划",
        followup_context=_unattempted_two_question_followup_context(),
        include_decision=False,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_message",
    ["给点提示", "提示一下", "还是不会", "这题怎么想", "怎么思考", "第2题怎么做"],
)
async def test_narrow_implicit_help_fires_without_llm(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str,
) -> None:
    """SEV counterexample: 窄隐式求助兜底表命中 → 确定性开火, LLM 零调用, 零泄答案。
    这是 06-30 红队证实会泄露的形态, 护栏不依赖 LLM。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message=user_message,
        followup_context=_unattempted_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"
    response = str(payload["response"])
    assert "正确答案是 C" not in response
    assert "答案：C" not in response
    assert payload["reveal_answers"] is False


@pytest.mark.asyncio
async def test_narrow_implicit_help_beats_canonical_detour_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEV 护栏优先级: 即使 canonical 裁决(错误地)判了 detour→general_chat,
    窄兜底表命中仍无条件开火 —— 护栏不被 LLM 裁决解除。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _detour_context(
        user_message="给点提示",
        followup_context=_unattempted_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


@pytest.mark.asyncio
@pytest.mark.parametrize("user_message", ["公布答案", "我放弃这题"])
async def test_explicit_reveal_and_concession_still_released(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str,
) -> None:
    """SEV counterexample: 显式要答案 / concession 是学员主动解锁 —— 照常放行
    (should_block=False), 不被兜底表/canonical 层拦截。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    context = _build_context(
        user_message=user_message,
        followup_context=_unattempted_two_question_followup_context(),
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1


# ------------------------- Stage B (flag ON fixtures) -------------------------


def _enable_facet_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tutorbot_capability, "antipeek_canonical_facet_enabled", lambda: True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_message",
    [
        "给我整理记忆口诀",
        "帮我总结主体结构高频考点",
        "给我讲讲大体积混凝土温控知识点",
        "换个话题",
        "帮我列复习计划",
    ],
)
async def test_facet_false_releases_owner_pain_forms_without_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str,
) -> None:
    """Stage B: flag ON 且 facet=false → 全放行+redact; 白名单 (_SAFE_STUDY_AID_MARKERS)
    不再被消费 (canonical facet 是唯一放行判据)。"""

    manager = _MnemonicManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    def _whitelist_must_not_be_consumed(_message: str) -> bool:
        raise AssertionError("_SAFE_STUDY_AID_MARKERS whitelist must not be consumed when facet governs")

    monkeypatch.setattr(
        tutorbot_capability,
        "looks_like_safe_study_aid_request",
        _whitelist_must_not_be_consumed,
    )

    stream = StreamBus()
    context = _detour_context(
        user_message=user_message,
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=False,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1
    payload = _result_payload(stream)
    assert payload.get("execution_path") != "tutorbot_unanswered_reference_reprompt"
    session_metadata = manager.calls[0]["session_metadata"]
    assert session_metadata["question_context_redacted_for_safe_study_aid"] is True
    assert session_metadata["active_object"] == {}
    assert session_metadata["question_followup_context"] == {}
    assert session_metadata["anti_peek_release_reason"] == "canonical_facet_no_answer_help"


@pytest.mark.asyncio
async def test_facet_true_fires_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage B: flag ON 且 facet=true → LLM 判定本轮在向老师索取当前未答题的解答帮助
    → 开火。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    stream = StreamBus()
    context = _detour_context(
        user_message="这题的突破口在哪里",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=True,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


@pytest.mark.asyncio
async def test_facet_missing_with_flag_on_fires_narrow_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-down 兜底: flag ON 但 facet=None (interpret 返回 None / 判定器挂了),
    "给点提示" 仍确定性开火 —— SEV 护栏不依赖 LLM 在场。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    stream = StreamBus()
    context = _detour_context(
        user_message="给点提示",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=None,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


@pytest.mark.asyncio
async def test_flag_off_ignores_facet_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """flag OFF (默认) 时 facet 字段即使在场也不参与 —— 行为与 legacy bit 一致
    (除 Stage A 的 detour 放行)。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)

    stream = StreamBus()
    # facet=False 在场, 但 flag OFF; 裁决是 followup 而非 detour → legacy 开火。
    context = _detour_context(
        user_message="帮我总结主体结构高频考点",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=False,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"


# ---------------------------------------------------------------------------
# WP3 复审必修（指挥官裁决③）: facet=False 不得越过显式格式确定性逻辑。
# 正典层序: 显式格式/解锁 → 窄 SEV 兜底表 → facet(flag) → canonical detour → legacy。
# (a) 判定器把显式 reveal 误标 false 不得触发 redaction——显式 reveal 轮必须拿到
#     完整题面材料（owner"不能不输出"）;
# (b) "第N题"序数指代的确定性无答案重渲染 handler 优先于 facet 放行。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facet_false_never_degrades_explicit_reveal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """flag ON + facet=False(判定器误标) + 显式 reveal("直接告诉我答案") →
    零 redaction、reveal 流不降级: 显式解锁优先于 facet, LLM 拿完整题目上下文。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    stream = StreamBus()
    context = _detour_context(
        user_message="直接告诉我答案",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=False,
    )

    await TutorBotCapability().run(context, stream)

    # 显式 reveal → should_block=False → 照常放行主 LLM。
    assert manager.sent_messages == 1
    session_metadata = manager.calls[0]["session_metadata"]
    # 零 redaction: 题目上下文原样带给 LLM, 显式 reveal 流不降级。
    assert "question_context_redacted_for_safe_study_aid" not in session_metadata
    assert "anti_peek_release_reason" not in session_metadata
    assert session_metadata["active_object"] != {}


@pytest.mark.asyncio
async def test_facet_false_does_not_bypass_ordinal_deterministic_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """flag ON + facet=False(判定器误标) + "第2题再讲讲"(序数指代未答题) →
    第N题确定性无答案重渲染 handler 仍开火——显式格式确定性逻辑零改动红线。"""

    manager = _LeakingManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    stream = StreamBus()
    context = _detour_context(
        user_message="第2题再讲讲",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=False,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 0
    payload = _result_payload(stream)
    assert payload.get("execution_path") == "tutorbot_unanswered_reference_reprompt"
    response = str(payload["response"])
    # 确定性重渲染: 第2题题面在场, 答案不在场。
    assert "深基坑支护方案应如何选择" in response
    assert "正确答案是 C" not in response
    assert "答案：C" not in response
    # 确定性 handler 开火轮不 redact(守卫在 redaction 站点同样生效)。
    # (manager 未被调用, 无 session_metadata 可查——由 sent_messages==0 已证不降级。)


@pytest.mark.asyncio
async def test_guarded_facet_false_still_releases_study_aid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """防过修 pin: 确定性守卫(显式 reveal/concession/序数)不误伤正常 facet 放行——
    "帮我总结主体结构高频考点"+facet=False 仍放行+redact。"""

    manager = _MnemonicManager()
    monkeypatch.setattr(tutorbot_capability, "get_tutorbot_manager", lambda: manager)
    _enable_facet_flag(monkeypatch)

    stream = StreamBus()
    context = _detour_context(
        user_message="帮我总结主体结构高频考点",
        followup_context=_unattempted_two_question_followup_context(),
        relation="ask_about_active_object",
        next_action="route_to_followup_explainer",
        facet=False,
    )

    await TutorBotCapability().run(context, stream)

    assert manager.sent_messages == 1
    session_metadata = manager.calls[0]["session_metadata"]
    assert session_metadata["question_context_redacted_for_safe_study_aid"] is True
    assert session_metadata["active_object"] == {}
    assert session_metadata["anti_peek_release_reason"] == "canonical_facet_no_answer_help"
