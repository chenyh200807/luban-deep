"""L1 瘦身检索在 TutorBot 直通判分轮上的不变量（contracts/rag.md 44）。

管线侧的「lean 与 full 的 exact payload / 分母逐字段相同」由
`tests/services/rag/test_case_grading_identity_profile.py` 守；本文件守 loop 侧的
四条：

1. **身份链不得断在 loop**：lean 下 pipeline 不再拼装正文，`tools.execute("rag")`
   返回空串是正常终态；旧的「空正文 → 直接 return」短路会在
   `consume_trace_metadata()` **之前**退出，把 `exact_question` 一起丢掉 ——
   那等于 tier3 回落。空正文必须仍落 `_prefetched_exact_question`。
2. **正文不注入**：直通轮不传 on_tool_call/on_tool_result，正文只会落进
   `role:tool` 消息，而 `session/manager.stable_messages()` 丢弃一切非
   user/assistant 角色、永不回放。lean 一条消息都不加。
3. **饱和台账不被毒化**（陷阱①）：`_source_overlap` 对空集合恒返回 `None`，
   播种一个空 sources 的 prefetch 轮会让紧随其后的 in-loop 轮拿到不可比基线
   （round_index=2 但 overlap=None）→ 该轮的重复 query 永远判不出饱和。
   身份轮不占台账一格，fell-through 轮回到「首个 in-loop 轮 = round 1」。
4. **kill switch**：`LUBAN_CASE_DIRECT_LEAN_RAG=off` 逐字节回旧形状（注入 tool
   消息 + 播种台账），marker 落 `"full"`。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.rag.retrieval_profiles import (
    RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
)
from deeptutor.tutorbot.agent.loop import AgentLoop


class _Ctx:
    def build_messages(self, *, history, current_message, **_kwargs):
        return [{"role": "system", "content": ""}, *history, {"role": "user", "content": current_message}]

    def add_assistant_message(self, messages, content, **kwargs):
        item = {"role": "assistant", "content": content}
        if kwargs.get("tool_calls") is not None:
            item["tool_calls"] = kwargs["tool_calls"]
        return [*messages, item]

    def add_tool_result(self, messages, tool_call_id, tool_name, result):
        return [
            *messages,
            {"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result},
        ]


def _prefetch_loop(*, tool_result: str, trace_metadata: dict):
    """只用到 prefetch 路径上的静态/实例方法 —— 不需要完整构造 AgentLoop。"""
    loop = AgentLoop.__new__(AgentLoop)

    class _RagTool:
        def preview_args(self, params):
            return dict(params)

        def consume_trace_metadata(self):
            return dict(trace_metadata)

    class _Tools:
        def __init__(self) -> None:
            self.seen_args: list[dict] = []

        def get(self, name):
            return _RagTool() if name == "rag" else None

        async def execute(self, name, args):
            assert name == "rag"
            self.seen_args.append(dict(args))
            return tool_result

    loop.tools = _Tools()
    loop.context = _Ctx()
    loop._build_rag_preview_args = lambda *_a, **_k: {"query": "题干", "kb_name": "construction-exam"}
    return loop


_EXACT = {
    "answer_kind": "case_study",
    "question_id": 9348,
    "stem": "【背景资料】某工程…【问题】1. 指出不妥之处。",
    "covered_subquestions": [
        {"display_index": "1", "prompt": "指出不妥之处", "authoritative_answer": "答案一"},
    ],
    "covered_indexes": ["1"],
}


@pytest.mark.asyncio
async def test_lean_prefetch_keeps_exact_authority_when_content_is_empty() -> None:
    """① 身份链不得断在 loop：空正文仍必须落 _prefetched_exact_question。"""
    loop = _prefetch_loop(
        tool_result="",  # lean 下 pipeline 不拼正文 —— 这是正常终态，不是失败
        trace_metadata={"sources": [], "exact_question": dict(_EXACT), "retrieval_profile": "case_grading_identity"},
    )
    md: dict = {}
    messages = await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "题干+作答"}],
        current_message="题干+作答",
        runtime_metadata=md,
        force_authority_fetch=True,
        tool_query_override="题干",
        retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )

    assert md.get("_prefetched_exact_question") == _EXACT
    # ② 一条消息都不加（正文进死存储，注入没有消费者）
    assert messages == [{"role": "user", "content": "题干+作答"}]
    assert not [m for m in messages if m.get("role") == "tool"]
    # profile 透传到了 pipeline 入参
    assert loop.tools.seen_args[-1]["retrieval_profile"] == RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    # 陷阱②：空 sources 不得点亮降级闸
    assert "rag_retrieval_degraded" not in md


@pytest.mark.asyncio
async def test_lean_prefetch_does_not_seed_the_saturation_ledger() -> None:
    """③ 陷阱①：空 sources 轮不进饱和台账，否则下一轮的 overlap 基线不可比。"""
    loop = _prefetch_loop(
        tool_result="",
        trace_metadata={"sources": [], "exact_question": dict(_EXACT)},
    )
    md: dict = {}
    await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "题干"}],
        current_message="题干",
        runtime_metadata=md,
        force_authority_fetch=True,
        retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )
    trace = md.get("_latest_rag_trace_metadata") or {}
    # agent loop 的播种判据正是 isinstance(trace["rag_round"], dict)。
    assert "rag_round" not in trace
    assert "rag_rounds" not in trace

    # 反证：同一条路径在 full 模式下**必须**播种（这条才是旧行为，别一起砍掉）。
    full_loop = _prefetch_loop(
        tool_result="题库原题正文",
        trace_metadata={"sources": [{"chunk_id": "q-9348"}], "exact_question": dict(_EXACT)},
    )
    full_md: dict = {}
    await full_loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "题干"}],
        current_message="题干",
        runtime_metadata=full_md,
        force_authority_fetch=True,
    )
    full_trace = full_md.get("_latest_rag_trace_metadata") or {}
    assert isinstance(full_trace.get("rag_round"), dict)


@pytest.mark.asyncio
async def test_kill_switch_off_restores_the_old_tool_message_shape() -> None:
    """④ kill switch off：直通轮不再声明 profile，prefetch 回旧形状（注入 tool 消息）。"""
    loop = _prefetch_loop(
        tool_result="【题目】题库原题\n【答案】…",
        trace_metadata={"sources": [{"chunk_id": "q-9348"}], "exact_question": dict(_EXACT)},
    )
    md: dict = {}
    messages = await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "题干"}],
        current_message="题干",
        runtime_metadata=md,
        force_authority_fetch=True,
        retrieval_profile=None,
    )
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "full 模式必须保持旧的 tool 消息注入形状"
    assert "题库原题" in tool_msgs[-1]["content"]
    assert md.get("_prefetched_exact_question") == _EXACT
    assert "retrieval_profile" not in loop.tools.seen_args[-1]


def _direct_loop(tmp_path):
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class _P(LLMProvider):
        async def chat(self, *_a, **_k):
            return LLMResponse(content="占位")

        def get_default_model(self):
            return "fake"

    return AgentLoop(
        bus=MessageBus(),
        provider=_P(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )


async def _run_direct(tmp_path, monkeypatch) -> tuple[dict, dict]:
    from deeptutor.tutorbot.bus.events import InboundMessage

    loop = _direct_loop(tmp_path)
    seen: dict = {}

    async def _fake_prefetch(*, initial_messages, current_message, runtime_metadata, **kwargs):
        seen["retrieval_profile"] = kwargs.get("retrieval_profile")
        return initial_messages

    async def _fake_plan(*, runtime_metadata, user_message, **_kwargs):
        return {"final_text": "## 批改\n占位判分正文", "score_first": "占位"}

    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _fake_prefetch)
    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_plan)
    monkeypatch.setattr(loop, "_is_case_grading_scene", lambda _md: True)

    md: dict = {"question_lifecycle_scene": "case_grading", "default_kb": "construction-exam"}
    msg = InboundMessage(channel="test", sender_id="u", chat_id="c", content="题干…作答…")
    await loop._run_case_grading_direct(
        msg=msg,
        session=SimpleNamespace(metadata={}, key="k", messages=[], last_consolidated=0),
        history=[],
        current_message="【背景资料】某工程…【问题】1. 指出不妥之处。\n我的答案：…",
        runtime_metadata=md,
        runtime_instruction="",
    )
    return md, seen


@pytest.mark.asyncio
async def test_direct_round_declares_lean_profile_and_exports_the_marker(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("LUBAN_CASE_DIRECT_LEAN_RAG", raising=False)
    md, seen = await _run_direct(tmp_path, monkeypatch)
    assert seen["retrieval_profile"] == RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    assert md.get("case_direct_rag_profile") == "lean"


@pytest.mark.asyncio
async def test_direct_round_kill_switch_off_declares_no_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_DIRECT_LEAN_RAG", "off")
    md, seen = await _run_direct(tmp_path, monkeypatch)
    assert seen["retrieval_profile"] is None
    assert md.get("case_direct_rag_profile") == "full"


def test_marker_is_on_the_single_case_grading_export_authority() -> None:
    """marker 必须进 CASE_GRADING_AUTHORITY_EXPORT_KEYS —— 漏一张名单 = 该 sink
    永久 0 命中（2026-07-30 倾向四收权的既有教训），live 验收就没有分组依据。"""
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_GRADING_AUTHORITY_EXPORT_KEYS,
    )

    assert "case_direct_rag_profile" in CASE_GRADING_AUTHORITY_EXPORT_KEYS
