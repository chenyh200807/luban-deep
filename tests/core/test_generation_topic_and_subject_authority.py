"""WP4 语义完整性战役 — "本轮出题考点"单一权威 + 罐头拒答绝迹 + 科目薄切。

契约（fix/semantic-answering-rootcause-20260712 WP4，对应 contracts/turn.md 出题承接段）：

1. topic 单一 decider = ``deep_question._resolve_generation_topic``（最新优先：
   本轮显式考点 > 对话尾部 > active_object/suspended_stack > session title 仅当无 history）。
2. needs-anchor 判定降级为 trace hint：任何"出题"同义改写都不得再落
   ``practice_generation_blocked`` 罐头（杀 strip 表地鼠：不许靠往 strip 表加词过测）。
3. 仅真冷启动（session 无任何前文）才澄清一次，澄清是提问不是拒答，且绝不写 active_object。
4. coordinator 不再有第二套 topic 推导/域门；anchor 走显式参数，不做字符串反解析；
   ``考(...)`` 提取器只喂单条用户消息，禁喂 transcript。
5. 科目薄切：continuity summary 里 title 降到 conversation_context 之后；
   loop 指令组装带"以用户声明科目为准"行；soul 带"用户声明科目优先"句。

Hermetic：FakeCoordinator 捕获 generate_from_topic kwargs；无 LLM / RAG / 网络。
生产活体病灶镜像：a60e0902（例A 刚梳理完考点被拒答）、5848e6c3（例B 科目翻案）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus

_REPO_ROOT = Path(__file__).resolve().parents[2]
from deeptutor.services.session.turn_runtime import (
    _result_active_object,
    _result_question_followup_context,
)
from deeptutor.tutorbot import teaching_modes

_REFUSAL_CANNED_MARKERS = ("我还没有拿到", "不能只按", "不能直接生成")

_REVIEW_USER_MESSAGE = "帮我梳理一建建筑实务的核心考点"
_REVIEW_ASSISTANT_ANSWER = (
    "一建建筑实务核心考点梳理：网络计划与流水施工是历年考情权重最高的板块，"
    "其次是变形缝构造、屋面防水施工与项目质量计划管理。建议优先攻克网络计划。"
)

_PARAPHRASES = (
    "出几道题目",
    "来几个题目",  # a60a 地鼠：strip 表残渣"目"曾判 False
    "出点题",
    "给我出几道题目练练",
    "出题",
)


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)


async def _collect_events(run_coro) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await run_coro(bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


def _practice_generation_turn_decision() -> dict[str, Any]:
    return {
        "relation_to_active_object": "switch_to_new_object",
        "next_action": "route_to_generation",
        "allowed_patch": "set_active_object",
        "confidence": 0.91,
        "reason": "用户要求基于当前会话主题出题。",
        "target_object_ref": {"object_type": "question_set", "object_id": ""},
    }


def _capturing_coordinator(captured: dict[str, Any]) -> type:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, callback: Any) -> None:
            captured["ws_callback"] = callback

        def set_trace_callback(self, callback: Any) -> None:
            captured["trace_callback"] = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["generate_from_topic"] = kwargs
            return {
                "source": "topic",
                "requested": kwargs.get("num_questions", 0),
                "completed": 0,
                "failed": 0,
                "results": [],
                "trace": {
                    "lightweight_generation": kwargs.get("lightweight_generation", False),
                    "lightweight_counters": {
                        "llm_calls": 0,
                        "retriever_calls": 0,
                        "bank_hits": 0,
                        "lightweight_batch_fallback": "none",
                        "generated_explanation": False,
                    },
                },
            }

        async def generate_from_followup_context(self, **kwargs: Any) -> dict[str, Any]:
            captured["generate_from_followup_context"] = kwargs
            return await self.generate_from_topic(**kwargs)

    return FakeCoordinator


def _wire_capability_env(monkeypatch: pytest.MonkeyPatch, coordinator_cls: type) -> None:
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=coordinator_cls,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )


def _generation_context(
    message: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> UnifiedContext:
    metadata: dict[str, Any] = {
        "question_lifecycle_scene": "practice_generation",
        "selected_mode": "deep",
        "turn_semantic_decision": _practice_generation_turn_decision(),
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    return UnifiedContext(
        user_message=message,
        conversation_history=list(conversation_history or []),
        config_overrides={
            "mode": "custom",
            "topic": message,
            "num_questions": 3,
            "question_type": "choice",
            "force_generate_questions": True,
            "lightweight_generation": False,
        },
        language="zh",
        metadata=metadata,
    )


def _result_event(events: list[StreamEvent]) -> StreamEvent:
    return next(event for event in events if event.type == StreamEventType.RESULT)


# ---------------------------------------------------------------------------
# ① 同义改写表驱动（杀地鼠）：梳理完考点后任何出题说法都必须出题并锚定梳理考点族
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("message", _PARAPHRASES)
async def test_paraphrase_table_generates_anchored_to_reviewed_topic(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    captured: dict[str, Any] = {}
    _wire_capability_env(monkeypatch, _capturing_coordinator(captured))

    context = _generation_context(
        message,
        conversation_history=[
            {"role": "user", "content": _REVIEW_USER_MESSAGE},
            {"role": "assistant", "content": _REVIEW_ASSISTANT_ANSWER},
        ],
    )
    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
    result = _result_event(events)

    # 罐头绝迹：不许出现 blocked reason / 拒答文案。
    assert "practice_generation_blocked_reason" not in result.metadata, message
    response = str(result.metadata.get("response") or "")
    for marker in _REFUSAL_CANNED_MARKERS:
        assert marker not in response, (message, marker)

    # 必须到达 generator，且锚定对话尾部的梳理考点族（不许靠 strip 表加词过测：
    # 本断言对表内所有改写一视同仁地要求 anchor）。
    kwargs = captured.get("generate_from_topic")
    assert kwargs is not None, f"{message!r} 未到达 coordinator"
    assert "网络计划" in str(kwargs.get("user_topic") or ""), message
    # anchor 显式参数传递（非字符串往返）。
    assert "网络计划" in str(kwargs.get("generation_anchor") or ""), message
    # 考(...) 提取器只许喂单条用户消息。
    assert kwargs.get("raw_user_message") == message


# ---------------------------------------------------------------------------
# ① 真冷启动 counterexample：澄清一次（提问语气），绝不写 active_object
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_true_cold_start_clarifies_once_without_canned_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NeverReached:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("true cold start must clarify before coordinator")

    _wire_capability_env(monkeypatch, NeverReached)

    context = _generation_context("出几道题目")
    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
    result = _result_event(events)

    response = str(result.metadata.get("response") or "")
    # 澄清（问围绕哪个考点），不是罐头拒答。
    assert "考点" in response
    for marker in _REFUSAL_CANNED_MARKERS:
        assert marker not in response, marker
    # 澄清仍标记 blocked reason（turn_runtime 依此拒写 active_object）。
    assert result.metadata.get("practice_generation_blocked_reason") == "missing_topic_anchor"
    assert result.metadata.get("question_followup_context") == {}
    assert result.metadata.get("active_object") == {}

    # turn_runtime 保护（既有，补测试）：澄清文案绝不落成 active question。
    persisted_shape = {
        "response": response,
        "practice_generation_blocked_reason": "missing_topic_anchor",
        "question_followup_context": {
            "question_id": "q_blocked",
            "question": response,
            "question_type": "written",
        },
        "active_object": {
            "object_type": "single_question",
            "object_id": "q_blocked",
            "state_snapshot": {"question_id": "q_blocked", "question": response},
        },
    }
    assert _result_question_followup_context(persisted_shape) is None
    assert _result_active_object(persisted_shape) is None


@pytest.mark.asyncio
async def test_out_of_scope_refused_before_coordinator_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SAFETY belt（指挥官 WP4 复审必补）：入口域门覆盖全部生产生成路径。

    WP4 删的是 coordinator 里那份冗余 out_of_scope 门,拒答一直在 deep_question
    入口门(4536-4573),且发生在 AgentCoordinator 构造之前。这条端到端 belt 把
    "off-domain 主题在 coordinator 被构造前就拒答"钉成不变量——防 4526 的
    should_enforce 条件未来被收窄时,off-domain 生成静默绕过入口门回归(owner
    最痛恨行为的 SAFETY 面)。NeverReached 在构造即 raise,测试通过=门确在
    coordinator 之前拦下。
    """

    class NeverReached:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError(
                "out_of_scope 主题必须在 coordinator 构造前被入口门拒答"
            )

    _wire_capability_env(monkeypatch, NeverReached)

    context = _generation_context("围绕法国首都出三道题")
    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
    result = _result_event(events)

    # SAFETY:off-domain 拒答(非罐头 needs-anchor,而是 out_of_scope),且不出题。
    assert result.metadata.get("practice_generation_blocked_reason") == "out_of_scope_topic"
    assert (
        result.metadata.get("practice_generation_topic_domain_status")
        == "out_of_scope_topic"
    )
    # 不铸活跃题:off-domain 拒答绝不写 active_object。
    assert result.metadata.get("question_followup_context") == {}
    assert result.metadata.get("active_object") == {}


@pytest.mark.asyncio
async def test_clarification_then_topic_reply_generates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """澄清→承接闭环：澄清后用户回具体考点（如"变形缝"）必须直接出题。"""
    captured: dict[str, Any] = {}
    _wire_capability_env(monkeypatch, _capturing_coordinator(captured))

    context = _generation_context(
        "变形缝",
        conversation_history=[
            {"role": "user", "content": "出几道题目"},
            {"role": "assistant", "content": "想围绕哪个考点练？例如变形缝、网络计划、屋面防水。"},
        ],
    )
    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
    result = _result_event(events)

    assert "practice_generation_blocked_reason" not in result.metadata
    kwargs = captured.get("generate_from_topic")
    assert kwargs is not None
    assert "变形缝" in str(kwargs.get("user_topic") or "")


# ---------------------------------------------------------------------------
# ① 最新优先：对话尾部最新考点 > suspended/active > session title
# ---------------------------------------------------------------------------


def test_latest_reviewed_topic_beats_session_title() -> None:
    history = [
        {"role": "user", "content": "帮我梳理屋面防水的核心考点"},
        {"role": "assistant", "content": "屋面防水核心考点：卷材防水与涂膜防水的构造要求。"},
        {"role": "user", "content": "再帮我梳理网络计划"},
        {"role": "assistant", "content": "网络计划核心考点：双代号网络图、关键线路与总时差计算。"},
    ]
    suspended_stack = [
        {
            "object_type": "open_chat_topic",
            "object_id": "topic-1",
            "state_snapshot": {"title": "帮我梳理屋面防水的核心考点"},
        }
    ]
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="出几道题目",
        active_object=None,
        suspended_object_stack=suspended_stack,
        followup_question_context=None,
        conversation_context_text=deep_question_module._conversation_history_context_text(history),
    )
    assert "网络计划" in topic, topic
    # session title（当前会话主题：...）不得压过对话尾部。
    assert "当前会话主题" not in topic, topic


def test_session_title_used_only_when_no_history() -> None:
    suspended_stack = [
        {
            "object_type": "open_chat_topic",
            "object_id": "topic-1",
            "state_snapshot": {"title": "帮我梳理屋面防水的核心考点"},
        }
    ]
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="出几道题目",
        active_object=None,
        suspended_object_stack=suspended_stack,
        followup_question_context=None,
        conversation_context_text="",
    )
    assert "屋面防水" in topic, topic


def test_conversation_anchor_clips_tail_not_head() -> None:
    """名叫"最近对话摘要"就必须取最新（尾部），不是最旧 240 字。"""
    oldest = "用户: 帮我梳理屋面防水的核心考点。" + "助手: 屋面防水构造细节铺垫。" * 20
    newest = "用户: 再帮我梳理网络计划\n助手: 网络计划核心考点是关键线路与总时差。"
    anchor = deep_question_module._conversation_generation_anchor(oldest + "\n" + newest)
    assert "网络计划" in anchor, anchor
    assert "屋面防水的核心考点" not in anchor, anchor


def test_active_object_grounding_when_conversation_empty() -> None:
    """context 降级分支（I3 不确定性 b）：conversation 为空时用 active_object 锚点，
    不落 ""（"" 只保留给真冷启动澄清）。"""
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="出几道题目",
        active_object={
            "object_type": "open_chat_topic",
            "object_id": "topic-1",
            "state_snapshot": {"compressed_summary": "刚梳理了流水施工与网络计划的高频考法"},
        },
        suspended_object_stack=[],
        followup_question_context=None,
        conversation_context_text="",
    )
    assert topic != ""
    assert "流水施工" in topic


# ---------------------------------------------------------------------------
# ① 域门只判 out_of_scope；needs_anchor 降级为 trace hint（单一权威映射收口）
# ---------------------------------------------------------------------------


def test_block_decision_needs_anchor_downgraded_to_allow() -> None:
    assert (
        teaching_modes.practice_generation_topic_block_decision("needs_context_anchor")
        == "allow"
    )
    assert (
        teaching_modes.practice_generation_topic_block_decision("out_of_scope_topic")
        == "block_out_of_scope"
    )


def test_coordinator_second_topic_deciders_deleted() -> None:
    """coordinator 不得再有第二套 topic 推导/lightweight 锚点门/字符串反解析。"""
    for name in (
        "_extract_embedded_generation_anchor",
        "_resolve_practice_topic_with_context",
        "_should_block_unresolved_lightweight_anchor",
    ):
        assert not hasattr(AgentCoordinator, name), name


def test_label_extractor_never_fed_transcript() -> None:
    """考(...) 提取器只喂单条用户消息：transcript 里的"考情权重"不得变成标签。"""
    transcript_anchor = (
        "最近对话摘要：用户: 帮我梳理一建建筑实务的核心考点 "
        "助手: 网络计划是考情权重最高的板块，其次是变形缝。"
    )
    payload = AgentCoordinator._base_lightweight_anchor_payload(
        user_topic="出几道题目\n\n请严格围绕以下当前学习锚点出题：\n" + transcript_anchor,
        generation_anchor=transcript_anchor,
        raw_user_message="出几道题目",
    )
    assert "情权重" not in str(payload.get("concentration") or "")
    assert str(payload.get("knowledge_context") or "") == transcript_anchor
    assert payload.get("anchor_source") == "resolved_topic_anchor"


# ---------------------------------------------------------------------------
# 例A 金标回归（a60e0902）：梳理→"出几道题目"→必须出题
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_example_a_gold_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _wire_capability_env(monkeypatch, _capturing_coordinator(captured))

    context = _generation_context(
        "出几道题目",
        conversation_history=[
            {"role": "user", "content": _REVIEW_USER_MESSAGE},
            {"role": "assistant", "content": _REVIEW_ASSISTANT_ANSWER},
        ],
        metadata_extra={
            "suspended_object_stack": [
                {
                    "object_type": "open_chat_topic",
                    "object_id": "topic-a60e0902",
                    "state_snapshot": {"title": _REVIEW_USER_MESSAGE},
                }
            ],
        },
    )
    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
    result = _result_event(events)

    assert "practice_generation_blocked_reason" not in result.metadata
    response = str(result.metadata.get("response") or "")
    for marker in _REFUSAL_CANNED_MARKERS:
        assert marker not in response, marker
    kwargs = captured.get("generate_from_topic")
    assert kwargs is not None, "例A 必须出题，不许再拒答"
    assert "网络计划" in str(kwargs.get("user_topic") or "")


# ---------------------------------------------------------------------------
# ② 科目薄切（例B 5848e6c3 缓解层）：结构断言，LLM 行为归 live 探针
# ---------------------------------------------------------------------------


def test_continuity_summary_title_demoted_below_conversation_context() -> None:
    summary = teaching_modes._coerce_continuity_summary(
        active_object={
            "object_type": "open_chat_topic",
            "state_snapshot": {"title": "一建建筑实务核心考点梳理"},
        },
        conversation_context_text="用户正在梳理一建机电实务考点，最近一轮聊的是机电。",
    )
    assert summary.startswith("用户正在梳理一建机电实务考点"), summary

    # compressed_summary 仍最高；title 只在无 conversation_context 时兜底。
    with_summary = teaching_modes._coerce_continuity_summary(
        active_object={
            "object_type": "open_chat_topic",
            "state_snapshot": {
                "compressed_summary": "正在梳理机电实务",
                "title": "旧标题",
            },
        },
        conversation_context_text="conversation 尾部",
    )
    assert with_summary == "正在梳理机电实务"

    title_only = teaching_modes._coerce_continuity_summary(
        active_object={
            "object_type": "open_chat_topic",
            "state_snapshot": {"title": "一建建筑实务核心考点梳理"},
        },
        conversation_context_text="",
    )
    assert title_only == "一建建筑实务核心考点梳理"


def test_subject_declaration_instruction_exists_and_wired_into_loop() -> None:
    instruction = teaching_modes.get_subject_declaration_instruction()
    assert "用户最近" in instruction
    assert "科目" in instruction
    assert "不得" in instruction  # 不得纠正用户的科目选择
    assert "边界" in instruction  # 知识库不覆盖时诚实声明边界

    loop_source = (_REPO_ROOT / "deeptutor/tutorbot/agent/loop.py").read_text(encoding="utf-8")
    assert "get_subject_declaration_instruction(" in loop_source


def test_construction_soul_declares_user_subject_priority() -> None:
    from deeptutor.services.tutorbot.manager import TutorBotManager

    souls = TutorBotManager._default_souls()
    coach = next(s for s in souls if s.get("id") == "construction-exam-coach")
    content = str(coach.get("content") or "")
    assert "用户声明" in content and "优先" in content
